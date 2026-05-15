(function () {
  "use strict";

  const PLUGIN = "drive";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const React = SDK.React;
  const useEffect = SDK.hooks.useEffect;
  const useRef = SDK.hooks.useRef || React.useRef;
  const useState = SDK.hooks.useState;

  function h(type, props) {
    const children = Array.prototype.slice.call(arguments, 2);
    return React.createElement.apply(React, [type, props].concat(children));
  }

  function api(path) {
    return "/api/plugins/" + PLUGIN + path;
  }

  const PREVIEW_FULLSCREEN_CLASS = "hermes-plugin-preview-fullscreen-active";
  const PREVIEW_FULLSCREEN_STYLE_ID = "hermes-plugin-preview-fullscreen-style";
  const PREVIEW_FULLSCREEN_CSS =
    "html." + PREVIEW_FULLSCREEN_CLASS + ",body." + PREVIEW_FULLSCREEN_CLASS + "{overflow:hidden!important;}" +
    "body." + PREVIEW_FULLSCREEN_CLASS + " aside," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " nav," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " [role='navigation']," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " [data-sidebar]," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " [data-testid*='sidebar' i]," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " [class*='sidebar' i]," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " [class*='Sidebar']{" +
    "visibility:hidden!important;pointer-events:none!important;}" +
    "body." + PREVIEW_FULLSCREEN_CLASS + " .hermes-drive-preview-fullscreen," +
    "body." + PREVIEW_FULLSCREEN_CLASS + " .hermes-code-preview-fullscreen{" +
    "z-index:2147483000!important;}";

  function previewFullscreenDocuments() {
    const docs = [document];
    try {
      if (window.parent && window.parent !== window && window.parent.document) docs.push(window.parent.document);
    } catch (error) {
      // Cross-origin plugin hosts cannot be patched; the local overlay z-index still applies.
    }
    return docs;
  }

  function setPreviewFullscreenChrome(active) {
    previewFullscreenDocuments().forEach(function (doc) {
      try {
        if (!doc) return;
        let style = doc.getElementById(PREVIEW_FULLSCREEN_STYLE_ID);
        if (!style && doc.head) {
          style = doc.createElement("style");
          style.id = PREVIEW_FULLSCREEN_STYLE_ID;
          style.textContent = PREVIEW_FULLSCREEN_CSS;
          doc.head.appendChild(style);
        }
        if (doc.documentElement) doc.documentElement.classList.toggle(PREVIEW_FULLSCREEN_CLASS, !!active);
        if (doc.body) doc.body.classList.toggle(PREVIEW_FULLSCREEN_CLASS, !!active);
      } catch (error) {
        // Best-effort chrome suppression must never break preview rendering.
      }
    });
  }

  function displaySize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return Math.round(bytes / 102.4) / 10 + " KB";
    return Math.round(bytes / 1024 / 102.4) / 10 + " MB";
  }

  function joinPath(parent, name) {
    const base = !parent || parent === "/" ? "" : parent.replace(/\/$/, "");
    return base + "/" + String(name || "").replace(/^\/+/, "");
  }

  function parentPath(path) {
    if (!path || path === "/") return "/";
    const parts = path.replace(/^\/+|\/+$/g, "").split("/");
    parts.pop();
    return parts.length ? "/" + parts.join("/") : "/";
  }

  function nameFromPath(path) {
    const parts = String(path || "").replace(/^\/+|\/+$/g, "").split("/");
    return parts[parts.length - 1] || "";
  }

  function normalizeFolder(path) {
    const clean = String(path || "/").trim().replace(/\\/g, "/");
    if (!clean || clean === ".") return "/";
    return clean.charAt(0) === "/" ? clean.replace(/\/+$/g, "") || "/" : "/" + clean.replace(/\/+$/g, "");
  }

  function transferTypes(event) {
    return Array.prototype.slice.call((event.dataTransfer && event.dataTransfer.types) || []);
  }

  function hasFiles(event) {
    return transferTypes(event).indexOf("Files") !== -1;
  }

  function normalizeUploadRelativePath(rawPath, fallbackName) {
    const fallback = String(fallbackName || "upload").replace(/\\/g, "/").split("/").filter(Boolean).pop() || "upload";
    const text = String(rawPath || fallback).replace(/\\/g, "/").replace(/^\/+/, "");
    const parts = text
      .split("/")
      .map(function (part) {
        return part.trim();
      })
      .filter(function (part) {
        return part && part !== "." && part !== "..";
      });
    return parts.join("/") || fallback;
  }

  function normalizeUploadEntries(filesOrEntries) {
    return Array.prototype.slice.call(filesOrEntries || [])
      .map(function (entry) {
        const file = entry && entry.file ? entry.file : entry;
        if (!file) return null;
        const path = (entry && entry.relativePath) || file.webkitRelativePath || file.name;
        return {
          file: file,
          relativePath: normalizeUploadRelativePath(path, file.name),
        };
      })
      .filter(Boolean);
  }

  function uploadTopName(entry) {
    return String((entry && entry.relativePath) || (entry && entry.file && entry.file.name) || "")
      .split("/")[0];
  }

  function flattenUploadGroups(groups) {
    const payload = { files: [], directories: [] };
    (groups || []).forEach(function (group) {
      (group.files || []).forEach(function (entry) {
        payload.files.push(entry);
      });
      (group.directories || []).forEach(function (directory) {
        payload.directories.push(directory);
      });
    });
    payload.directories = Array.from(new Set(payload.directories.filter(Boolean)));
    return payload;
  }

  function readDirectoryEntries(reader) {
    return new Promise(function (resolve, reject) {
      const entries = [];
      function readNextBatch() {
        reader.readEntries(
          function (batch) {
            if (!batch.length) {
              resolve(entries);
              return;
            }
            entries.push.apply(entries, batch);
            readNextBatch();
          },
          reject
        );
      }
      readNextBatch();
    });
  }

  function collectEntryUploads(entry, parentPath) {
    const currentPath = normalizeUploadRelativePath(parentPath ? parentPath + "/" + entry.name : entry.name, entry.name);
    if (entry.isFile) {
      return new Promise(function (resolve, reject) {
        entry.file(
          function (file) {
            resolve({
              files: [{ file: file, relativePath: currentPath }],
              directories: [],
            });
          },
          reject
        );
      });
    }
    if (entry.isDirectory) {
      return readDirectoryEntries(entry.createReader()).then(function (children) {
        return Promise.all(
          children.map(function (child) {
            return collectEntryUploads(child, currentPath);
          })
        ).then(function (groups) {
          const payload = flattenUploadGroups(groups);
          payload.directories.unshift(currentPath);
          return payload;
        });
      });
    }
    return Promise.resolve({ files: [], directories: [] });
  }

  function collectDroppedUploadItems(dataTransfer) {
    const items = Array.prototype.slice.call((dataTransfer && dataTransfer.items) || []);
    const files = Array.prototype.slice.call((dataTransfer && dataTransfer.files) || []);
    const entries = items
      .map(function (item) {
        if (!item) return null;
        if (typeof item.getAsEntry === "function") return item.getAsEntry();
        if (typeof item.webkitGetAsEntry === "function") return item.webkitGetAsEntry();
        return null;
      })
      .filter(Boolean);
    if (!entries.length) {
      return Promise.resolve({
        files: normalizeUploadEntries(files),
        directories: [],
      });
    }
    return Promise.all(
      entries.map(function (entry) {
        return collectEntryUploads(entry, "");
      })
    ).then(flattenUploadGroups);
  }

  function fetchJSON(url, options) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, options || {})).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (text) {
          throw new Error(text || "request failed");
        });
      }
      return response.json();
    });
  }

  function DrivePage() {
    const fileInput = useRef(null);
    const folderInput = useRef(null);
    const confirmResolver = useRef(null);
    const statePair = useState({
      loading: true,
      status: null,
      roots: [],
      root: "",
      path: "/",
      location: "files",
      query: "",
      favoritesOnly: false,
      view: "list",
      sortKey: "name",
      items: [],
      trashItems: [],
      selected: null,
      selectedPaths: {},
      selectionAnchor: null,
      preview: null,
      previewFullscreen: false,
      treeNodes: {},
      expanded: {},
      searchResults: [],
      searching: false,
      busy: false,
      contextMenu: null,
      draggingItem: null,
      dropActive: false,
      uploadMenuOpen: false,
      errorMessage: "",
      confirmDialog: null,
      destinationDialog: null,
    });
    const state = statePair[0];
    const setState = statePair[1];

    function patch(next) {
      setState(function (current) {
        return Object.assign({}, current, typeof next === "function" ? next(current) : next);
      });
    }

    function requestJSON(path, payload) {
      const body = Object.assign({}, payload || {});
      if (!body.root && state.root) body.root = state.root;
      patch({ busy: true, errorMessage: "" });
      return fetchJSON(api(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
        .then(function (data) {
          patch({ busy: false, contextMenu: null });
          return data;
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "Request failed", contextMenu: null });
        });
    }

    function askConfirm(options) {
      return new Promise(function (resolve) {
        confirmResolver.current = resolve;
        patch({
          confirmDialog: Object.assign(
            {
              title: "Confirm action",
              message: "",
              confirmLabel: "Confirm",
              cancelLabel: "Cancel",
              expectedText: "",
              typedText: "",
              destructive: false,
            },
            options || {}
          ),
        });
      });
    }

    function resolveConfirm(accepted) {
      const dialog = state.confirmDialog || {};
      if (accepted && dialog.expectedText && dialog.typedText !== dialog.expectedText) return;
      const resolver = confirmResolver.current;
      confirmResolver.current = null;
      patch({ confirmDialog: null });
      if (resolver) resolver(!!accepted);
    }

    function cancelConfirm() {
      const resolver = confirmResolver.current;
      confirmResolver.current = null;
      patch({ confirmDialog: null });
      if (resolver) resolver(false);
    }

    function batchFailureMessage(data, label) {
      const failed = ((data && data.results) || []).filter(function (item) {
        return !item.ok;
      });
      if (!failed.length) return "";
      return failed.length + " " + label + " item(s) failed: " + failed.slice(0, 3).map(function (item) {
        return (item.path || "item") + " - " + (item.detail || "failed");
      }).join("; ");
    }

    function rootSortValue(root) {
      const value = String((root && (root.id || root.label)) || "").toLowerCase();
      if (value.indexOf("workspace") !== -1) return "0-" + value;
      if (value.indexOf("vault") !== -1) return "1-" + value;
      return "2-" + value;
    }

    function orderedRoots(roots) {
      return (roots || []).slice().sort(function (a, b) {
        return rootSortValue(a).localeCompare(rootSortValue(b));
      });
    }

    function rootById(rootId) {
      return (state.roots || []).filter(function (root) {
        return root.id === rootId;
      })[0] || {};
    }

    function rootCanReceiveCopy(root) {
      return !!(root && root.available && !root.read_only && (!root.capabilities || root.capabilities.copy !== false));
    }

    function destinationRootsFor(action, sourceRoot) {
      if (action === "copy" && sourceRoot === "linked") {
        return orderedRoots(state.roots).filter(rootCanReceiveCopy);
      }
      return orderedRoots(state.roots).filter(function (root) {
        return root.id === sourceRoot;
      });
    }

    function treeKey(rootId, path) {
      return String(rootId || "") + ":" + normalizeFolder(path || "/");
    }

    function itemRoot(item) {
      return (item && item.root) || state.root;
    }

    function itemSelectionKey(item) {
      return itemRoot(item) + "|" + (item && item.path ? item.path : "");
    }

    function itemKey(item) {
      return itemRoot(item) + ":" + (item && item.path ? item.path : "");
    }

    function decorateItems(rootId, items) {
      return (items || []).map(function (item) {
        return Object.assign({}, item, { root: rootId || item.root || state.root });
      });
    }

    function loadTreeNode(rootId, path) {
      const folder = normalizeFolder(path || "/");
      const key = treeKey(rootId, folder);
      const params = new URLSearchParams({ root: rootId || state.root, path: folder, query: "" });
      return fetchJSON(api("/items?" + params.toString()))
        .then(function (data) {
          patch(function (current) {
            const nextNodes = Object.assign({}, current.treeNodes || {});
            nextNodes[key] = decorateItems(rootId, data.items || []);
            return { treeNodes: nextNodes };
          });
          return data;
        })
        .catch(function (error) {
          patch({ errorMessage: error.message || "Unable to load Drive tree" });
        });
    }

    function toggleTree(rootId, path) {
      const key = treeKey(rootId, path);
      const expanded = !state.expanded[key];
      patch(function (current) {
        const nextExpanded = Object.assign({}, current.expanded || {});
        nextExpanded[key] = expanded;
        return { expanded: nextExpanded };
      });
      if (expanded && !state.treeNodes[key]) loadTreeNode(rootId, path);
    }

    function selectFolder(rootId, path) {
      const folder = normalizeFolder(path || "/");
      patch({
        root: rootId,
        path: folder,
        query: "",
        favoritesOnly: false,
        location: "files",
        selected: null,
        selectedPaths: {},
        selectionAnchor: null,
        preview: null,
      });
      loadTreeNode(rootId, folder);
      loadItems(folder, "", false, rootId);
    }

    function setDestinationFolder(rootId, path) {
      const folder = normalizeFolder(path || "/");
      patch(function (current) {
        if (!current.destinationDialog) return {};
        return {
          destinationDialog: Object.assign({}, current.destinationDialog, {
            root: rootId,
            path: folder,
          }),
        };
      });
      loadTreeNode(rootId, folder);
    }

    function refreshFolder(rootId, path) {
      const folder = normalizeFolder(path || state.path || "/");
      const activeRoot = rootId || state.root;
      loadTreeNode(activeRoot, folder);
      loadTreeNode(activeRoot, parentPath(folder));
      loadItems(folder, state.query, state.favoritesOnly, activeRoot);
    }

    function loadItems(nextPath, nextQuery, nextFavorites, nextRoot) {
      const targetPath = nextPath || state.path;
      const targetRoot = nextRoot || state.root;
      const query = typeof nextQuery === "string" ? nextQuery : state.query;
      const favoritesOnly = typeof nextFavorites === "boolean" ? nextFavorites : state.favoritesOnly;
      patch({ loading: true, root: targetRoot, path: targetPath, location: "files", query: query, favoritesOnly: favoritesOnly, errorMessage: "" });
      const params = new URLSearchParams({ path: targetPath, query: query });
      if (targetRoot) params.set("root", targetRoot);
      if (favoritesOnly) params.set("favorites_only", "true");
      fetchJSON(api("/items?" + params.toString()))
        .then(function (data) {
          patch({ loading: false, items: decorateItems(targetRoot, data.items || []), path: data.path || targetPath, location: "files", selected: null, selectedPaths: {}, selectionAnchor: null, preview: null, searchResults: query ? state.searchResults : [] });
        })
        .catch(function (error) {
          patch({ loading: false, items: [], selected: null, preview: null, errorMessage: error.message || "Unable to load Drive" });
        });
    }

    function searchAllRoots(query, favoritesOnly) {
      const clean = String(query || "").trim();
      patch({ query: clean, favoritesOnly: !!favoritesOnly, location: "files", errorMessage: "" });
      if (!clean) {
        patch({ searchResults: [], searching: false });
        loadItems(state.path, "", !!favoritesOnly, state.root);
        return;
      }
      patch({ searching: true, loading: false, selected: null, selectedPaths: {}, selectionAnchor: null });
      Promise.all(
        orderedRoots(state.roots).map(function (root) {
          const params = new URLSearchParams({ root: root.id, path: "/", query: clean });
          if (favoritesOnly) params.set("favorites_only", "true");
          return fetchJSON(api("/items?" + params.toString()))
            .then(function (data) {
              return decorateItems(root.id, data.items || []);
            })
            .catch(function () {
              return [];
            });
        })
      ).then(function (groups) {
        const results = [];
        groups.forEach(function (items) {
          items.forEach(function (item) {
            results.push(item);
          });
        });
        patch({ searching: false, searchResults: results });
      });
    }

    function loadTrash() {
      patch({ loading: true, location: "trash", favoritesOnly: false, query: "", selected: null, selectedPaths: {}, selectionAnchor: null, preview: null, errorMessage: "" });
      const params = new URLSearchParams();
      if (state.root) params.set("root", state.root);
      fetchJSON(api("/trash?" + params.toString()))
        .then(function (data) {
          const items = (data.items || []).map(function (record) {
            return {
              trashed: true,
              kind: "file",
              name: nameFromPath(record.original_path),
              path: record.original_path,
              original_path: record.original_path,
              trash_path: record.trash_path,
              deleted_at: record.deleted_at,
            };
          });
          patch({ loading: false, location: "trash", trashItems: decorateItems(state.root, items), selected: null, selectedPaths: {}, selectionAnchor: null, preview: null });
        })
        .catch(function (error) {
          patch({ loading: false, location: "trash", trashItems: [], selected: null, preview: null, errorMessage: error.message || "Unable to load trash" });
        });
    }

    function loadStatus() {
      SDK.fetchJSON(api("/status"))
        .then(function (status) {
          const roots = orderedRoots((status.roots || []).filter(function (root) { return root.available; }));
          const preferredRoot = roots.filter(function (candidate) {
            return String(candidate.id || candidate.label || "").toLowerCase().indexOf("workspace") !== -1;
          })[0];
          const root = (preferredRoot && preferredRoot.id) || status.default_root || (roots[0] && roots[0].id) || "";
          patch({ status: status, roots: roots, root: root, loading: false, expanded: {} });
          if (status.available) {
            const params = new URLSearchParams({ path: "/", query: "" });
            if (root) params.set("root", root);
            fetchJSON(api("/items?" + params.toString()))
              .then(function (data) {
                patch({ loading: false, items: decorateItems(root, data.items || []), path: data.path || "/", location: "files", selected: null, selectedPaths: {}, selectionAnchor: null, preview: null });
              })
              .catch(function (error) {
                patch({ loading: false, items: [], selected: null, preview: null, errorMessage: error.message || "Unable to load Drive" });
              });
          }
        })
        .catch(function () {
          patch({ status: { available: false }, loading: false });
        });
    }

    function openItem(item) {
      patch({ contextMenu: null });
      if (item.trashed) {
        patch({ selected: item, preview: null });
        return;
      }
      if (item.kind === "folder") {
        selectFolder(itemRoot(item), item.path);
        return;
      }
      patch({ root: itemRoot(item), selected: item, preview: null });
    }

    function selectItemOnly(item) {
      patch({
        selected: item,
        selectedPaths: {},
        selectionAnchor: null,
        preview: null,
        contextMenu: null,
      });
    }

    function selectRootOnly(root) {
      const rootId = root.id;
      selectItemOnly({
        root: rootId,
        kind: "folder",
        name: root.label || rootId,
        path: "/",
        mime: "folder",
        size: 0,
      });
    }

    function openUploadFiles() {
      patch({ uploadMenuOpen: false, contextMenu: null });
      fileInput.current && fileInput.current.click();
    }

    function openUploadFolder() {
      patch({ uploadMenuOpen: false, contextMenu: null });
      folderInput.current && folderInput.current.click();
    }

    function uploadFiles(files, targetPath, targetRoot, options) {
      const uploadEntries = normalizeUploadEntries(files);
      const directories = ((options && options.directories) || []).map(function (directory) {
        return normalizeUploadRelativePath(directory, directory);
      });
      if (!uploadEntries.length && !directories.length) return;
      const targetFolder = normalizeFolder(targetPath || state.path);
      const rootId = targetRoot || state.root;
      let conflict = "reject";
      if (targetFolder === normalizeFolder(state.path)) {
        const existingNames = {};
        (state.items || []).forEach(function (item) {
          existingNames[item.name] = true;
        });
        const conflictEntries = uploadEntries.concat(
          directories.map(function (directory) {
            return { relativePath: directory };
          })
        );
        const conflicts = conflictEntries.filter(function (entry) {
          return existingNames[uploadTopName(entry)];
        });
        if (conflicts.length) {
          askConfirm({
            title: "Keep both uploads?",
            message: conflicts.length + " uploaded item(s) already exist in " + targetFolder + ". Drive can keep both copies with safe copy names.",
            confirmLabel: "Keep Both",
          }).then(function (confirmed) {
            if (!confirmed) {
              patch({ dropActive: false, contextMenu: null });
              return;
            }
            startUpload(uploadEntries, targetFolder, "keep-both", rootId, directories);
          });
          return;
        }
      }
      startUpload(uploadEntries, targetFolder, conflict, rootId, directories);
    }

    function uploadDroppedItems(dataTransfer, targetPath, targetRoot) {
      collectDroppedUploadItems(dataTransfer)
        .then(function (payload) {
          uploadFiles(payload.files, targetPath, targetRoot, { directories: payload.directories });
        })
        .catch(function (error) {
          patch({ busy: false, dropActive: false, errorMessage: (error && error.message) || "Upload failed" });
        });
    }

    function startUpload(uploadEntries, targetFolder, conflict, rootId, directories) {
      const body = new FormData();
      body.append("path", targetFolder);
      if (rootId) body.append("root", rootId);
      body.append("conflict", conflict);
      body.append("relative_paths", JSON.stringify(uploadEntries.map(function (entry) { return entry.relativePath; })));
      body.append("directories", JSON.stringify(directories || []));
      uploadEntries.forEach(function (entry) {
        body.append("files", entry.file, entry.file.name);
      });
      patch({ busy: true, dropActive: false, errorMessage: "" });
      fetchJSON(api("/upload"), { method: "POST", body: body })
        .then(function () {
          patch({ busy: false });
          refreshFolder(rootId, targetFolder);
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "Upload failed" });
        });
    }

    function createFolder() {
      const name = (window.prompt("Folder name") || "").trim();
      if (!name) return;
      requestJSON("/mkdir", { root: state.root, path: state.path, name: name }).then(function (data) {
        if (data) refreshFolder(state.root, state.path);
      });
    }

    function createFile() {
      const name = (window.prompt("File name") || "").trim();
      if (!name) return;
      requestJSON("/new-file", { root: state.root, path: state.path, name: name, content: "" }).then(function (data) {
        if (data) refreshFolder(state.root, state.path);
      });
    }

    function renameItem(item) {
      const name = (window.prompt("Rename", item.name) || "").trim();
      if (!name || name === item.name) {
        patch({ contextMenu: null });
        return;
      }
      requestJSON("/rename", { root: itemRoot(item), path: item.path, name: name }).then(function (data) {
        if (data) refreshFolder(itemRoot(item), parentPath(item.path));
      });
    }

    function moveItemToFolder(item, destinationFolder) {
      const folder = normalizeFolder(destinationFolder);
      if (item.kind === "folder" && (folder === item.path || folder.indexOf(item.path + "/") === 0)) {
        window.alert("A folder cannot be moved into itself.");
        return;
      }
      const destination = joinPath(folder, item.name);
      if (destination === item.path) {
        patch({ contextMenu: null });
        return;
      }
      askConfirm({
        title: "Move item?",
        message: "Move " + item.name + " to " + folder + "?",
        confirmLabel: "Move",
      }).then(function (confirmed) {
        if (!confirmed) {
          patch({ contextMenu: null });
          return;
        }
        requestJSON("/move", { root: itemRoot(item), path: item.path, destination_path: destination }).then(function (data) {
          if (data) refreshFolder(itemRoot(item), state.path);
        });
      });
    }

    function openDestinationDialog(action, options) {
      const subject = options || {};
      const item = subject.item || null;
      const paths = subject.paths || (item ? [item.path] : selectedPathList());
      if (!paths.length) return;
      const sourceRoot = subject.root || (item ? itemRoot(item) : state.root);
      const roots = destinationRootsFor(action, sourceRoot);
      if (!roots.length) {
        patch({ errorMessage: "No writable destination is available.", contextMenu: null });
        return;
      }
      const initialRoot = roots[0].id;
      const initialPath = normalizeFolder(initialRoot === sourceRoot && item ? parentPath(item.path) : state.path || "/");
      patch({
        contextMenu: null,
        destinationDialog: {
          action: action,
          mode: item ? "item" : "selection",
          item: item,
          paths: paths,
          sourceRoot: sourceRoot,
          root: initialRoot,
          path: initialPath,
        },
      });
      loadTreeNode(initialRoot, "/");
      loadTreeNode(initialRoot, initialPath);
    }

    function closeDestinationDialog() {
      patch({ destinationDialog: null });
    }

    function duplicateItem(item) {
      requestJSON("/duplicate", { root: itemRoot(item), path: item.path }).then(function (data) {
        if (data) refreshFolder(itemRoot(item), parentPath(item.path));
      });
    }

    function copyItemWithPrompt(item) {
      openDestinationDialog("copy", { item: item, root: itemRoot(item), paths: [item.path] });
    }

    function moveItemWithPrompt(item) {
      openDestinationDialog("move", { item: item, root: itemRoot(item), paths: [item.path] });
    }

    function moveDraggedPath(sourcePath, destinationFolder, sourceRoot) {
      const item = (state.items || []).concat(state.searchResults || []).filter(function (candidate) {
        return candidate.path === sourcePath && (!sourceRoot || itemRoot(candidate) === sourceRoot);
      })[0] || { root: sourceRoot || state.root, path: sourcePath, name: nameFromPath(sourcePath), kind: "file" };
      moveItemToFolder(item, destinationFolder);
    }

    function deleteItem(item) {
      askConfirm({
        title: "Move to trash?",
        message: "Type the item name to move " + item.name + " to trash.",
        expectedText: item.name,
        confirmLabel: "Move to Trash",
        destructive: true,
      }).then(function (confirmed) {
        if (!confirmed) {
          patch({ contextMenu: null });
          return;
        }
        requestJSON("/delete", { root: itemRoot(item), path: item.path }).then(function (data) {
          if (data) refreshFolder(itemRoot(item), parentPath(item.path));
        });
      });
    }

    function restoreItem(item) {
      if (!item || !item.trashed) return;
      requestJSON("/restore", { root: itemRoot(item), trash_path: item.trash_path || item.path }).then(function (data) {
        if (data) loadTrash();
      });
    }

    function selectedPathList() {
      return Object.keys(state.selectedPaths || {})
        .filter(function (key) {
          return state.selectedPaths[key];
        })
        .map(function (key) {
          return key.split(":").slice(1).join(":") || "/";
        });
    }

    function selectListItem(item, event, index, list) {
      const additive = !!(event && (event.ctrlKey || event.metaKey));
      const ranged = !!(event && event.shiftKey && state.selectionAnchor);
      const items = list || [];
      let next = (additive || ranged) ? Object.assign({}, state.selectedPaths || {}) : {};
      const selectedKey = itemKey(item);
      const selectedRoot = itemRoot(item);
      if (Object.keys(next).some(function (key) { return key.split(":")[0] !== selectedRoot; })) {
        next = {};
      }
      if (ranged) {
        const anchorPath = state.selectionAnchor.key || state.selectionAnchor.path;
        const anchorIndex = items.findIndex(function (candidate) {
          return itemKey(candidate) === anchorPath || candidate.path === anchorPath;
        });
        const start = Math.max(0, Math.min(anchorIndex === -1 ? index : anchorIndex, index));
        const end = Math.max(anchorIndex === -1 ? index : anchorIndex, index);
        for (let cursor = start; cursor <= end; cursor += 1) {
          if (items[cursor]) next[itemKey(items[cursor])] = true;
        }
      } else if (additive) {
        if (next[selectedKey]) {
          delete next[selectedKey];
        } else {
          next[selectedKey] = true;
        }
      } else {
        next[selectedKey] = true;
      }
      patch({
        root: selectedRoot || state.root,
        selectedPaths: next,
        selected: item,
        selectionAnchor: ranged ? state.selectionAnchor : { key: selectedKey, path: item.path, index: index },
        preview: null,
      });
    }

    function handleListItemClick(item, event, index, list) {
      selectListItem(item, event, index, list);
    }

    function codeEditUrl(item) {
      if (!item || item.kind !== "file") return "";
      const params = new URLSearchParams({ root: itemRoot(item) || state.root || "", path: item.path || "" });
      return "/code?" + params.toString();
    }

    function trashSelected() {
      const paths = selectedPathList();
      if (!paths.length) return;
      askConfirm({
        title: "Move selected to trash?",
        message: "This will move " + paths.length + " selected item(s) to trash. Type trash to continue.",
        expectedText: "trash",
        confirmLabel: "Move to Trash",
        destructive: true,
      }).then(function (confirmed) {
        if (!confirmed) return;
      requestJSON("/batch", { action: "trash", root: state.root, paths: paths }).then(function (data) {
        if (data) {
          const message = batchFailureMessage(data, "trash");
          refreshFolder(state.root, state.path);
            if (message) patch({ errorMessage: message, selectedPaths: {} });
          }
        });
      });
    }

    function restoreSelected() {
      const paths = selectedPathList();
      if (!paths.length) return;
      requestJSON("/batch", { action: "restore", root: state.root, paths: paths }).then(function (data) {
        if (data) {
          const message = batchFailureMessage(data, "restore");
          loadTrash();
          if (message) patch({ errorMessage: message, selectedPaths: {} });
        }
      });
    }

    function confirmDestinationDialog() {
      const dialog = state.destinationDialog;
      if (!dialog) return;
      const action = dialog.action === "move" ? "move" : "copy";
      const targetRoot = dialog.root;
      const targetFolder = normalizeFolder(dialog.path || "/");
      const sourceRoot = dialog.sourceRoot || state.root;
      const item = dialog.item || null;
      const paths = dialog.paths || [];
      if (item && action === "move" && item.kind === "folder" && (targetFolder === item.path || targetFolder.indexOf(item.path + "/") === 0)) {
        patch({ errorMessage: "A folder cannot be moved into itself.", destinationDialog: null });
        return;
      }
      patch({ destinationDialog: null });
      if (item) {
        const destination = joinPath(targetFolder, item.name || nameFromPath(item.path));
        const payload = {
          root: sourceRoot,
          path: item.path,
          destination_root: targetRoot,
          destination_path: destination,
        };
        if (action === "copy") payload.conflict = "keep-both";
        requestJSON(action === "copy" ? "/copy" : "/move", payload).then(function (data) {
          if (data) refreshFolder(state.root, state.path);
        });
        return;
      }
      requestJSON("/batch", {
        action: action,
        root: sourceRoot,
        paths: paths,
        destination_root: targetRoot,
        destination_folder: targetFolder,
        conflict: "keep-both",
      }).then(function (data) {
        if (data) {
          const message = batchFailureMessage(data, action);
          refreshFolder(state.root, state.path);
          if (message) patch({ errorMessage: message });
          if (action === "move" && !message) patch({ selectedPaths: {} });
        }
      });
    }

    function copySelectedWithPrompt() {
      const paths = selectedPathList();
      if (!paths.length) return;
      openDestinationDialog("copy", { root: state.root, paths: paths });
    }

    function moveSelectedWithPrompt() {
      const paths = selectedPathList();
      if (!paths.length) return;
      openDestinationDialog("move", { root: state.root, paths: paths });
    }

    function switchRoot(rootId) {
      selectFolder(rootId, "/");
    }

    function sortedItems() {
      const items = (state.location === "trash" ? state.trashItems || [] : state.query ? state.searchResults || [] : state.items || []).slice();
      if (state.location === "trash") {
        items.sort(function (a, b) {
          return String(b.deleted_at || "").localeCompare(String(a.deleted_at || "")) || String(a.name).localeCompare(String(b.name));
        });
        return items;
      }
      const key = state.sortKey || "name";
      items.sort(function (a, b) {
        const folderSort = (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1);
        if (key === "kind" && folderSort) return folderSort;
        if (key === "size") return (a.size || 0) - (b.size || 0) || String(a.name).localeCompare(String(b.name));
        if (key === "modified") return String(b.modified || "").localeCompare(String(a.modified || "")) || String(a.name).localeCompare(String(b.name));
        return folderSort || String(a.name).localeCompare(String(b.name));
      });
      return items;
    }

    function breadcrumbs() {
      const parts = String(state.path || "/").replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
      const rootLabel = currentRoot.label || state.root || "Drive";
      const nodes = [
        h("button", { key: "root", type: "button", onClick: function () { loadItems("/", "", false, state.root); } }, rootLabel),
      ];
      if (state.location === "trash") {
        nodes.push(h("button", { key: "trash", type: "button", onClick: loadTrash }, "Trash"));
        return nodes;
      }
      let current = "";
      parts.forEach(function (part) {
        current += "/" + part;
        nodes.push(h("button", { key: current, type: "button", onClick: function () { loadItems(current, "", false, state.root); } }, part));
      });
      return nodes;
    }

    function openContextMenu(item, event) {
      event.preventDefault();
      event.stopPropagation();
      patch({
        selected: item,
        contextMenu: {
          item: item,
          mode: selectedPathList().length > 1 && state.selectedPaths[itemKey(item)] ? "selection" : "item",
          x: event.clientX,
          y: event.clientY,
        },
      });
    }

    function openBackgroundContextMenu(event) {
      event.preventDefault();
      event.stopPropagation();
      patch({
        contextMenu: {
          item: null,
          mode: "background",
          x: event.clientX,
          y: event.clientY,
        },
      });
    }

    function fileExtension(item) {
      if (!item || item.kind === "folder") return "";
      const name = String(item.name || "");
      const parts = name.split(".");
      if (parts.length < 2) return "";
      return parts.pop().slice(0, 12).toLowerCase();
    }

    function fileExtLabel(item) {
      const ext = fileExtension(item);
      if (!ext) return "";
      return ext.length > 4 ? ext.slice(0, 3) + "." : ext.toUpperCase();
    }

    function extensionColor(item) {
      if (!item || item.kind === "folder") return "";
      const ext = fileExtension(item) || String(item.name || item.path || "file").toLowerCase();
      let hash = 0;
      for (let index = 0; index < ext.length; index += 1) {
        hash = (hash * 31 + ext.charCodeAt(index)) >>> 0;
      }
      const hues = [14, 32, 48, 142, 172, 205, 232, 266, 304, 332];
      const hue = hues[hash % hues.length] + ((hash >> 4) % 9) - 4;
      const saturation = 62 + ((hash >> 8) % 14);
      const lightness = 61 + ((hash >> 12) % 10);
      return "hsl(" + hue + " " + saturation + "% " + lightness + "%)";
    }

    function fileKindClass(item) {
      if (!item || item.kind === "folder") return "kind-folder";
      const ext = fileExtension(item);
      const mime = String(item.mime || "").toLowerCase();
      const code = ["css", "env", "go", "html", "java", "js", "jsx", "php", "py", "rb", "rs", "sh", "sql", "ts", "tsx"].indexOf(ext) !== -1;
      const docs = ["doc", "docx", "md", "mdx", "pdf", "rtf", "txt"].indexOf(ext) !== -1;
      const data = ["csv", "json", "toml", "tsv", "xml", "yaml", "yml"].indexOf(ext) !== -1;
      const image = mime.indexOf("image/") === 0 || ["gif", "jpeg", "jpg", "png", "svg", "webp"].indexOf(ext) !== -1;
      const media = mime.indexOf("audio/") === 0 || mime.indexOf("video/") === 0 || ["mp3", "mp4", "mov", "wav", "webm"].indexOf(ext) !== -1;
      const archive = ["7z", "gz", "rar", "tar", "tgz", "zip"].indexOf(ext) !== -1;
      if (code) return "kind-code";
      if (data) return "kind-data";
      if (image) return "kind-image";
      if (media) return "kind-media";
      if (archive) return "kind-archive";
      if (docs) return ext === "pdf" ? "kind-pdf" : "kind-doc";
      return "kind-file";
    }

    function renderFileIcon(item) {
      const ext = fileExtension(item);
      const label = fileExtLabel(item);
      return h(
        "span",
        {
          className:
            "hermes-drive-fileicon " +
            (item.kind === "folder" ? "folder" : "file") +
            " " +
            fileKindClass(item) +
            (label.length > 3 ? " long-ext" : ""),
          style: item.kind === "folder" ? null : { "--file-accent": extensionColor(item) },
          title: item.kind === "folder" ? "Folder" : ext ? ext.toUpperCase() + " file" : "File",
        },
        item.kind === "folder" ? null : h("span", { className: "hermes-drive-fileext" }, label)
      );
    }

    function previewKind(item) {
      if (!item || item.kind !== "file") return "";
      const ext = fileExtension(item);
      const mime = String(item.mime || "").toLowerCase();
      if (ext === "pdf" || mime === "application/pdf") return "pdf";
      if (mime.indexOf("image/") === 0 || ["gif", "jpeg", "jpg", "png", "svg", "webp"].indexOf(ext) !== -1) return "image";
      if (mime.indexOf("audio/") === 0 || ["mp3", "wav", "ogg", "m4a"].indexOf(ext) !== -1) return "audio";
      if (mime.indexOf("video/") === 0 || ["mov", "mp4", "webm"].indexOf(ext) !== -1) return "video";
      if (item.text || mime.indexOf("text/") === 0 || ["css", "csv", "env", "html", "ini", "js", "json", "log", "md", "mdx", "py", "sh", "sql", "toml", "ts", "txt", "xml", "yaml", "yml"].indexOf(ext) !== -1) {
        return ext === "md" || ext === "mdx" ? "markdown" : "text";
      }
      return "";
    }

    function downloadUrl(item) {
      return api("/download?path=" + encodeURIComponent(item.path) + "&root=" + encodeURIComponent(itemRoot(item) || ""));
    }

    function previewUrl(item) {
      return api("/preview?path=" + encodeURIComponent(item.path) + "&root=" + encodeURIComponent(itemRoot(item) || ""));
    }

    function renderPreviewBody(preview) {
      if (!preview) return h("div", { className: "hermes-drive-preview-empty" }, "Select a previewable file.");
      if (preview.kind === "loading") return h("div", { className: "hermes-drive-preview-empty" }, "Loading preview");
      if (preview.kind === "unsupported") return h("div", { className: "hermes-drive-preview-empty" }, preview.message || "No preview available for this file type.");
      if (preview.kind === "text" || preview.kind === "markdown") {
        return h("pre", { className: "hermes-drive-text-preview" }, preview.content || "");
      }
      if (preview.kind === "pdf") {
        return h(
          "iframe",
          { className: "hermes-drive-pdf-preview", src: preview.url, title: preview.name || "PDF preview" },
          h("a", { href: preview.url, target: "_blank", rel: "noreferrer" }, "Open PDF")
        );
      }
      if (preview.kind === "image") return h("img", { className: "hermes-drive-media-preview", src: preview.url, alt: preview.name || "Preview" });
      if (preview.kind === "audio") return h("audio", { className: "hermes-drive-audio-preview", src: preview.url, controls: true });
      if (preview.kind === "video") return h("video", { className: "hermes-drive-media-preview", src: preview.url, controls: true });
      return h("div", { className: "hermes-drive-preview-empty" }, "Preview unavailable");
    }

    function renderPreviewPanel() {
      const preview = state.preview;
      if (!preview || !preview.kind) return null;
      const canFullscreen = ["text", "markdown", "pdf", "image", "audio", "video"].indexOf(preview.kind) !== -1;
      return h(
        "section",
        { className: "hermes-drive-preview" },
        h(
          "div",
          { className: "hermes-drive-preview-head" },
          h("strong", null, preview.kind === "markdown" ? "Markdown Preview" : preview.kind.charAt(0).toUpperCase() + preview.kind.slice(1) + " Preview"),
          h(
            "span",
            null,
            preview.name || (state.selected && state.selected.name) || ""
          ),
          canFullscreen ? h("button", { type: "button", onClick: function () { patch({ previewFullscreen: true }); } }, "Maximize") : null
        ),
        renderPreviewBody(preview)
      );
    }

    function renderFullscreenPreview() {
      if (!state.previewFullscreen || !state.preview) return null;
      const preview = state.preview;
      return h(
        "div",
        {
          className: "hermes-drive-preview-fullscreen",
          role: "dialog",
          "aria-modal": "true",
          "aria-label": "File preview",
          tabIndex: -1,
          onKeyDown: function (event) {
            if (event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
              patch({ previewFullscreen: false });
            }
          },
        },
        h(
          "div",
          { className: "hermes-drive-preview-fullbar" },
          h("strong", null, preview.name || "Preview"),
          h("button", { type: "button", onClick: function () { patch({ previewFullscreen: false }); } }, "Close")
        ),
        renderPreviewBody(preview)
      );
    }

    function renderDestinationBreadcrumbs(dialog) {
      const parts = normalizeFolder(dialog.path || "/").replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
      const nodes = [
        h(
          "button",
          {
            key: "root",
            type: "button",
            className: dialog.path === "/" ? "active" : "",
            onClick: function () { setDestinationFolder(dialog.root, "/"); },
          },
          rootById(dialog.root).label || dialog.root || "Drive"
        ),
      ];
      let cursor = "";
      parts.forEach(function (part) {
        cursor = joinPath(cursor || "/", part);
        nodes.push(h("span", { key: cursor + "-sep" }, "/"));
        nodes.push(
          h(
            "button",
            {
              key: cursor,
              type: "button",
              className: cursor === dialog.path ? "active" : "",
              onClick: function () { setDestinationFolder(dialog.root, cursor); },
            },
            part
          )
        );
      });
      return nodes;
    }

    function renderDestinationDialog() {
      const dialog = state.destinationDialog;
      if (!dialog) return null;
      const action = dialog.action === "move" ? "move" : "copy";
      const actionLabel = action === "copy" ? "Copy" : "Move";
      const roots = destinationRootsFor(action, dialog.sourceRoot);
      const currentRoot = rootById(dialog.root);
      const folderKey = treeKey(dialog.root, dialog.path || "/");
      const children = state.treeNodes[folderKey];
      const folders = children
        ? children.filter(function (item) { return item.kind === "folder"; }).sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); })
        : null;
      const count = dialog.mode === "item" ? 1 : (dialog.paths || []).length;
      const subject = dialog.mode === "item" && dialog.item ? dialog.item.name : count + " selected item" + (count === 1 ? "" : "s");
      return h(
        "div",
        {
          className: "hermes-drive-destination-backdrop",
          role: "presentation",
          onClick: closeDestinationDialog,
        },
        h(
          "section",
          {
            className: "hermes-drive-destination",
            role: "dialog",
            "aria-modal": "true",
            "aria-label": actionLabel + " destination",
            onClick: function (event) { event.stopPropagation(); },
          },
          h(
            "div",
            { className: "hermes-drive-destination-head" },
            h(
              "div",
              null,
              h("h2", null, actionLabel + " destination"),
              h("p", null, subject)
            ),
            h("button", { type: "button", onClick: closeDestinationDialog }, "Close")
          ),
          h(
            "div",
            { className: "hermes-drive-destination-body" },
            h(
              "aside",
              { className: "hermes-drive-destination-roots", "aria-label": "Destination roots" },
              roots.map(function (root) {
                return h(
                  "button",
                  {
                    key: root.id,
                    type: "button",
                    className: root.id === dialog.root ? "active" : "",
                    onClick: function () { setDestinationFolder(root.id, "/"); },
                  },
                  root.label || root.id
                );
              })
            ),
            h(
              "div",
              { className: "hermes-drive-destination-picker" },
              h("div", { className: "hermes-drive-destination-path" }, renderDestinationBreadcrumbs(dialog)),
              h(
                "div",
                { className: "hermes-drive-destination-list" },
                dialog.path !== "/"
                  ? h(
                      "button",
                      { type: "button", className: "hermes-drive-destination-row", onClick: function () { setDestinationFolder(dialog.root, parentPath(dialog.path)); } },
                      renderFileIcon({ kind: "folder", name: ".." }),
                      h("span", null, "Up")
                    )
                  : null,
                folders === null
                  ? h("div", { className: "hermes-drive-destination-empty" }, "Loading")
                  : folders.length
                    ? folders.map(function (folder) {
                        return h(
                          "button",
                          {
                            key: folder.path,
                            type: "button",
                            className: "hermes-drive-destination-row",
                            onClick: function () { setDestinationFolder(dialog.root, folder.path); },
                          },
                          renderFileIcon(folder),
                          h("span", null, folder.name)
                        );
                      })
                    : h("div", { className: "hermes-drive-destination-empty" }, "No folders here")
              )
            )
          ),
          h(
            "div",
            { className: "hermes-drive-destination-actions" },
            h("span", null, (currentRoot.label || dialog.root || "Drive") + " " + normalizeFolder(dialog.path || "/")),
            h("button", { type: "button", onClick: closeDestinationDialog }, "Cancel"),
            h("button", { type: "button", onClick: confirmDestinationDialog, disabled: state.busy }, actionLabel)
          )
        )
      );
    }

    function renderCaret(rootId, item, depth) {
      const path = item ? item.path : "/";
      const key = treeKey(rootId, path);
      const isFolder = !item || item.kind === "folder";
      if (!isFolder) return h("span", { className: "hermes-drive-caret spacer" });
      return h(
        "button",
        {
          key: "caret",
          type: "button",
          className: "hermes-drive-caret",
          onClick: function (event) {
            event.stopPropagation();
            toggleTree(rootId, path);
          },
          "aria-label": state.expanded[key] ? "Collapse" : "Expand",
        },
        state.expanded[key] ? "v" : ">"
      );
    }

    function renderTreeChildren(rootId, path, depth) {
      const key = treeKey(rootId, path);
      if (!state.expanded[key]) return null;
      const children = state.treeNodes[key];
      if (!children) return h("div", { className: "hermes-drive-tree-loading", style: { paddingLeft: (depth + 1) * 18 + "px" } }, "Loading");
      const sorted = children.slice().sort(function (a, b) {
        const folderSort = (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1);
        return folderSort || String(a.name).localeCompare(String(b.name));
      });
      if (!sorted.length) return null;
      return h(
        "div",
        { className: "hermes-drive-tree-children" },
        sorted.map(function (item) {
          return renderTreeNode(Object.assign({}, item, { root: rootId }), depth + 1);
        })
      );
    }

    function renderTreeNode(item, depth) {
      const rootId = itemRoot(item);
      const selectedTree = state.root === rootId && state.path === item.path && item.kind === "folder" && state.location !== "trash" && !state.query;
      const selectedItem = state.selected && itemRoot(state.selected) === rootId && state.selected.path === item.path;
      return h(
        "div",
        { key: rootId + item.path, className: "hermes-drive-tree-node-wrap" },
        h(
          "button",
          {
            type: "button",
            draggable: true,
            className: "hermes-drive-tree-node " + (selectedTree ? "active " : "") + (selectedItem ? "selected" : ""),
            style: { paddingLeft: 0.2 + depth * 0.9 + "rem" },
            onClick: function () {
              if (item.kind === "folder") {
                selectFolder(rootId, item.path);
              } else {
                selectItemOnly(Object.assign({}, item, { root: rootId }));
              }
            },
            onDoubleClick: function () {
              if (item.kind === "folder") {
                toggleTree(rootId, item.path);
              } else {
                openItem(Object.assign({}, item, { root: rootId }));
              }
            },
            onContextMenu: function (event) {
              openContextMenu(item, event);
            },
            onDragStart: function (event) {
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("application/x-hermes-drive-path", item.path);
              event.dataTransfer.setData("application/x-hermes-drive-root", rootId);
              event.dataTransfer.setData("text/plain", item.path);
              patch({ draggingItem: item.path });
            },
            onDragEnd: function () {
              patch({ draggingItem: null, dropActive: false });
            },
          },
          renderCaret(rootId, item, depth),
          renderFileIcon(item),
          h("span", { className: "hermes-drive-tree-name" }, item.name)
        ),
        item.kind === "folder" ? renderTreeChildren(rootId, item.path, depth) : null
      );
    }

    function renderRootTree(root) {
      const rootId = root.id;
      const active = state.root === rootId && state.path === "/" && state.location !== "trash" && !state.query;
      const selectedRoot = state.selected && itemRoot(state.selected) === rootId && state.selected.path === "/";
      return h(
        "div",
        { key: rootId, className: "hermes-drive-tree-root" },
        h(
          "button",
          {
            type: "button",
            className: "hermes-drive-tree-node root " + (active ? "active " : "") + (selectedRoot ? "selected" : ""),
            style: { paddingLeft: "0.2rem" },
            onClick: function () {
              selectFolder(rootId, "/");
            },
            onDoubleClick: function () {
              toggleTree(rootId, "/");
            },
          },
          renderCaret(rootId, null, 0),
          renderFileIcon({ kind: "folder", name: root.label || rootId }),
          h("span", { className: "hermes-drive-tree-name" }, root.label || rootId)
        ),
        renderTreeChildren(rootId, "/", 0)
      );
    }

    function renderDetailsPanel() {
      if (!selected) {
        return h("div", { className: "hermes-drive-details empty" }, "Select a file or folder to see details.");
      }
      const detailRoot = rootById(itemRoot(selected));
      return h(
        "div",
        { className: "hermes-drive-details" },
        h("div", { className: "hermes-drive-details-title" }, renderFileIcon(selected), h("strong", null, selected.name)),
        h(
          "div",
          { className: "hermes-drive-file-facts" },
          h("span", null, detailRoot.label || itemRoot(selected) || "Drive"),
          h("span", null, selected.kind || "item"),
          h("span", null, selected.mime || "file"),
          h("span", null, displaySize(selected.size)),
          h("span", null, selected.modified || selected.deleted_at || ""),
          h("span", null, selected.path || "")
        ),
        h(
          "div",
          { className: "hermes-drive-preview-actions" },
          selected.trashed
            ? h("button", { type: "button", onClick: function () { restoreItem(selected); } }, "Restore")
            : null,
          !selected.trashed && selected.kind === "file"
            ? h("a", { href: api("/download?path=" + encodeURIComponent(selected.path) + "&root=" + encodeURIComponent(itemRoot(selected) || "")), target: "_blank", rel: "noreferrer" }, "Download")
            : null,
          selected.trashed ? null : h("button", { type: "button", onClick: function () { duplicateItem(selected); } }, "Duplicate"),
          selected.trashed ? null : h("button", { type: "button", onClick: function () { copyItemWithPrompt(selected); } }, "Copy"),
          selected.trashed ? null : h("button", { type: "button", onClick: function () { renameItem(selected); } }, "Rename"),
          selected.trashed ? null : h("button", { type: "button", onClick: function () { moveItemWithPrompt(selected); } }, "Move")
        ),
        renderPreviewPanel()
      );
    }

    useEffect(
      function () {
        const selected = state.selected;
        if (!selected || selected.kind !== "file" || selected.trashed) {
          if (state.preview) patch({ preview: null, previewFullscreen: false });
          return undefined;
        }
        const kind = previewKind(selected);
        const name = selected.name || nameFromPath(selected.path);
        if (!kind) {
          patch({ preview: { kind: "unsupported", name: name, message: "No preview available for this file type." }, previewFullscreen: false });
          return undefined;
        }
        if (kind === "text" || kind === "markdown") {
          const rootId = itemRoot(selected) || state.root;
          let cancelled = false;
          patch({ preview: { kind: "loading", name: name }, previewFullscreen: false });
          fetchJSON(api("/content?path=" + encodeURIComponent(selected.path) + "&root=" + encodeURIComponent(rootId)))
            .then(function (data) {
              if (!cancelled) patch({ preview: { kind: kind, name: name, content: data.content || "", modified: data.modified || "" } });
            })
            .catch(function (error) {
              if (!cancelled) patch({ preview: { kind: "unsupported", name: name, message: error.message || "Preview unavailable" } });
            });
          return function () {
            cancelled = true;
          };
        }
        patch({ preview: { kind: kind, name: name, url: previewUrl(selected) }, previewFullscreen: false });
        return undefined;
      },
      [state.selected && state.selected.path, state.selected && itemRoot(state.selected)]
    );

    useEffect(function () {
      loadStatus();
    }, []);

    useEffect(function () {
      setPreviewFullscreenChrome(state.previewFullscreen);
      if (state.previewFullscreen) {
        window.setTimeout(function () {
          const node = document.querySelector(".hermes-drive-preview-fullscreen");
          if (node && node.focus) node.focus({ preventScroll: true });
        }, 0);
      }
      return function () {
        setPreviewFullscreenChrome(false);
      };
    }, [state.previewFullscreen]);

    useEffect(function () {
      function closeFullscreen(event) {
        if (event.key !== "Escape" || !state.previewFullscreen) return;
        event.preventDefault();
        event.stopPropagation();
        patch({ previewFullscreen: false });
      }
      const docs = previewFullscreenDocuments();
      docs.forEach(function (doc) {
        doc.addEventListener("keydown", closeFullscreen, true);
      });
      return function () {
        docs.forEach(function (doc) {
          doc.removeEventListener("keydown", closeFullscreen, true);
        });
      };
    }, [state.previewFullscreen]);

    useEffect(function () {
      function closeMenu(event) {
        if (event.key === "Escape") {
          patch({ contextMenu: null, confirmDialog: null, uploadMenuOpen: false });
          if (confirmResolver.current) {
            const resolver = confirmResolver.current;
            confirmResolver.current = null;
            resolver(false);
          }
        }
      }
      window.addEventListener("keydown", closeMenu);
      return function () {
        window.removeEventListener("keydown", closeMenu);
      };
    }, []);

    const status = state.status || {};
    const selected = state.selected;
    const contextItem = state.contextMenu && state.contextMenu.item;
    const selectedCount = selectedPathList().length;
    const currentRoot = (state.roots || []).filter(function (root) { return root.id === state.root; })[0] || {};
    const canWrite = !state.busy && state.location !== "trash" && status.available && (!currentRoot.capabilities || currentRoot.capabilities.upload !== false);
    const visibleItems = sortedItems();
    const confirmDialog = state.confirmDialog;
    const confirmBlocked = !!(confirmDialog && confirmDialog.expectedText && confirmDialog.typedText !== confirmDialog.expectedText);

    return h(
      "section",
      {
        className: "hermes-drive" + (state.dropActive ? " dropping" : ""),
        onClick: function () {
          if (state.contextMenu || state.uploadMenuOpen) patch({ contextMenu: null, uploadMenuOpen: false });
        },
      },
      h(
        "header",
        { className: "hermes-drive-toolbar" },
        h(
          "div",
          { className: "hermes-drive-title" },
          h("h1", null, "Drive"),
          h("div", { className: "hermes-drive-path" }, breadcrumbs()),
          h("p", null, currentRoot.label ? currentRoot.label + " - " + (currentRoot.path || "/") : status.backend ? status.backend + " - " + (status.local_root || status.mount || "/") : "Agent knowledge")
        ),
        h(
          "div",
          { className: "hermes-drive-actions" },
          h("button", { type: "button", onClick: createFolder, disabled: !canWrite }, "New Folder"),
          h("button", { type: "button", onClick: createFile, disabled: !canWrite }, "New File"),
          h(
            "div",
            {
              className: "hermes-drive-upload-control",
              onClick: function (event) {
                event.stopPropagation();
              },
            },
            h("button", { type: "button", onClick: function () { patch({ uploadMenuOpen: !state.uploadMenuOpen, contextMenu: null }); }, disabled: !canWrite }, "Upload"),
            state.uploadMenuOpen
              ? h(
                  "div",
                  { className: "hermes-drive-upload-menu", role: "menu" },
                  h("button", { type: "button", role: "menuitem", onClick: openUploadFiles, disabled: !canWrite }, "Files"),
                  h("button", { type: "button", role: "menuitem", onClick: openUploadFolder, disabled: !canWrite }, "Folder")
                )
              : null
          ),
          h("button", { type: "button", onClick: function () { loadItems(state.path, "", false, state.root); }, disabled: !status.available }, "Refresh"),
          h("input", {
            ref: fileInput,
            type: "file",
            multiple: true,
            className: "hermes-drive-hidden",
            onChange: function (event) {
              uploadFiles(event.target.files, state.path, state.root);
              event.target.value = "";
            },
          }),
          h("input", {
            ref: folderInput,
            type: "file",
            multiple: true,
            webkitdirectory: "true",
            directory: "true",
            className: "hermes-drive-hidden",
            onChange: function (event) {
              uploadFiles(event.target.files, state.path, state.root);
              event.target.value = "";
            },
          })
        )
      ),
      state.errorMessage ? h("div", { className: "hermes-drive-error" }, state.errorMessage) : null,
      status.available
        ? h(
            "div",
            { className: "hermes-drive-main" },
            h(
              "aside",
              { className: "hermes-drive-browser" },
              h("div", { className: "hermes-drive-panel-label" }, "Files"),
              state.location === "trash"
                ? null
                : h("input", {
                    className: "hermes-drive-search",
                    value: state.query,
                    placeholder: "Search Workspace and Vault",
                    onChange: function (event) {
                      const value = event.target.value;
                      patch({ query: value });
                      window.clearTimeout(DrivePage._timer);
                      DrivePage._timer = window.setTimeout(function () {
                        searchAllRoots(value, state.favoritesOnly);
                      }, 180);
                    },
                  }),
              h("div", { className: "hermes-drive-tree" }, orderedRoots(state.roots).map(renderRootTree)),
              selectedCount
                ? h("div", { className: "hermes-drive-selection" },
                    h("span", { className: "hermes-drive-selection-count" }, selectedCount + " selected"),
                    h(
                      "div",
                      { className: "hermes-drive-selection-actions" },
                      state.location === "trash"
                        ? h("button", { type: "button", onClick: restoreSelected }, "Restore")
                        : h(React.Fragment, null,
                            h("button", { type: "button", onClick: copySelectedWithPrompt }, "Copy"),
                            h("button", { type: "button", onClick: moveSelectedWithPrompt }, "Move"),
                            h("button", { type: "button", onClick: trashSelected }, "Trash")
                          ),
                      h("button", { type: "button", onClick: function () { patch({ selectedPaths: {} }); } }, "Clear")
                    )
                  )
                : null,
              h(
                "div",
                { className: "hermes-drive-tree-tools" },
                h("button", { type: "button", className: state.location === "trash" ? "active" : "", onClick: loadTrash }, "Trash"),
                h("button", { type: "button", onClick: function () { switchRoot(state.root); }, disabled: !state.root }, "Refresh")
              )
            ),
            h(
              "section",
              {
                className: "hermes-drive-content" + (selected ? " has-selection" : ""),
                onDragOver: function (event) {
                  if (state.location !== "trash" && (hasFiles(event) || state.draggingItem)) {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = hasFiles(event) ? "copy" : "move";
                  }
                },
                onDragEnter: function (event) {
                  if (state.location !== "trash" && hasFiles(event)) patch({ dropActive: true });
                },
                onDragLeave: function (event) {
                  if (!event.currentTarget.contains(event.relatedTarget)) patch({ dropActive: false });
                },
                onDrop: function (event) {
                  event.preventDefault();
                  if (state.location === "trash") {
                    patch({ dropActive: false });
                    return;
                  }
                  const sourcePath = event.dataTransfer.getData("application/x-hermes-drive-path");
                  const sourceRoot = event.dataTransfer.getData("application/x-hermes-drive-root") || state.root;
                  patch({ dropActive: false });
                  if (sourcePath) {
                    if (sourceRoot !== state.root) {
                      patch({ errorMessage: "Move between Drive roots is not enabled yet. Copy between roots instead." });
                      return;
                    }
                    moveDraggedPath(sourcePath, state.path, sourceRoot);
                    return;
                  }
                  uploadDroppedItems(event.dataTransfer, state.path, state.root);
                },
              },
              h(
                "div",
                { className: "hermes-drive-content-head" },
                h(
                  "div",
                  null,
                  h(
                    "p",
                    { className: "hermes-drive-current-summary" },
                    state.location === "trash"
                      ? "Deleted items for " + (currentRoot.label || state.root || "Drive")
                      : state.query
                        ? "Search across Workspace and Vault"
                        : (currentRoot.label || state.root || "Drive") + " " + (state.path || "/")
                  )
                ),
                h(
                  "div",
                  { className: "hermes-drive-filters" },
                  h("button", { type: "button", onClick: function () { selectFolder(state.root, parentPath(state.path)); }, disabled: state.path === "/" || state.location === "trash" }, "Up"),
                  h("select", { value: state.sortKey, onChange: function (event) { patch({ sortKey: event.target.value }); } },
                    h("option", { value: "name" }, "Name"),
                    h("option", { value: "kind" }, "Kind"),
                    h("option", { value: "modified" }, "Modified"),
                    h("option", { value: "size" }, "Size")
                  ),
                  h("button", { type: "button", onClick: function () { patch({ view: state.view === "list" ? "grid" : "list" }); } }, state.view === "list" ? "Grid" : "List")
                )
              ),
              h(
                "div",
                { className: "hermes-drive-items " + state.view, onContextMenu: openBackgroundContextMenu },
                state.loading || state.searching
                  ? h("div", { className: "hermes-drive-empty" }, "Loading")
                  : visibleItems.length
                    ? visibleItems.map(function (item, index) {
                        return h(
                          "button",
                          {
                            key: itemKey(item),
                            type: "button",
                            draggable: true,
                            className:
                              "hermes-drive-item " +
                              (selected && itemKey(selected) === itemKey(item) ? "selected " : "") +
                              (state.selectedPaths[itemKey(item)] ? "checked " : "") +
                              (state.draggingItem === item.path ? "dragging" : ""),
                            onClick: function (event) {
                              handleListItemClick(item, event, index, visibleItems);
                            },
                            onDoubleClick: function () {
                              openItem(item);
                            },
                            onContextMenu: function (event) {
                              openContextMenu(item, event);
                            },
                            onDragStart: function (event) {
                              event.dataTransfer.effectAllowed = "move";
                              event.dataTransfer.setData("application/x-hermes-drive-path", item.path);
                              event.dataTransfer.setData("application/x-hermes-drive-root", itemRoot(item));
                              event.dataTransfer.setData("text/plain", item.path);
                              patch({ draggingItem: item.path });
                            },
                            onDragEnd: function () {
                              patch({ draggingItem: null, dropActive: false });
                            },
                            onDragOver: function (event) {
                              if (item.kind === "folder" && (state.draggingItem || hasFiles(event))) {
                                event.preventDefault();
                                event.dataTransfer.dropEffect = hasFiles(event) ? "copy" : "move";
                              }
                            },
                            onDrop: function (event) {
                              if (item.kind !== "folder") return;
                              event.preventDefault();
                              event.stopPropagation();
                              const sourcePath = event.dataTransfer.getData("application/x-hermes-drive-path");
                              const sourceRoot = event.dataTransfer.getData("application/x-hermes-drive-root") || itemRoot(item);
                              if (sourcePath) {
                                if (sourceRoot !== itemRoot(item)) {
                                  patch({ errorMessage: "Move between Drive roots is not enabled yet. Copy between roots instead." });
                                  return;
                                }
                                moveDraggedPath(sourcePath, item.path, sourceRoot);
                                return;
                              }
                              patch({ dropActive: false });
                              uploadDroppedItems(event.dataTransfer, item.path, itemRoot(item));
                            },
                          },
                          renderFileIcon(item),
                          h("span", { className: "hermes-drive-name" }, item.name),
                          state.query ? h("span", { className: "hermes-drive-root-chip" }, (rootById(itemRoot(item)).label || itemRoot(item) || "Drive")) : null,
                          h("span", { className: "hermes-drive-meta" }, item.trashed ? "Deleted " + (item.deleted_at || "") : item.kind === "folder" ? "Folder" : displaySize(item.size)),
                          item.trashed
                            ? h("span", { className: "hermes-drive-row-action", onClick: function (event) { event.stopPropagation(); restoreItem(item); } }, "Restore")
                            : null
                        );
                      })
                    : h("div", { className: "hermes-drive-empty" }, state.query ? "No search results" : "Empty")
              ),
              renderDetailsPanel()
            )
          )
        : h("div", { className: "hermes-drive-empty full" }, "Drive is not available"),
      state.dropActive ? h("div", { className: "hermes-drive-drop-overlay" }, "Drop files or folders to upload") : null,
      renderFullscreenPreview(),
      renderDestinationDialog(),
      confirmDialog
        ? h(
            "div",
            { className: "hermes-drive-confirm-backdrop", role: "presentation" },
            h(
              "section",
              { className: "hermes-drive-confirm", role: "dialog", "aria-modal": "true", "aria-label": confirmDialog.title },
              h("h2", null, confirmDialog.title),
              confirmDialog.message ? h("p", null, confirmDialog.message) : null,
              confirmDialog.expectedText
                ? h(
                    "label",
                    null,
                    h("span", null, "Confirmation text"),
                    h("input", {
                      value: confirmDialog.typedText || "",
                      onChange: function (event) {
                        patch({ confirmDialog: Object.assign({}, confirmDialog, { typedText: event.target.value }) });
                      },
                      autoFocus: true,
                    })
                  )
                : null,
              h(
                "div",
                { className: "hermes-drive-confirm-actions" },
                h("button", { type: "button", onClick: cancelConfirm }, confirmDialog.cancelLabel || "Cancel"),
                h(
                  "button",
                  {
                    type: "button",
                    className: confirmDialog.destructive ? "danger" : "",
                    disabled: confirmBlocked,
                    onClick: function () { resolveConfirm(true); },
                  },
                  confirmDialog.confirmLabel || "Confirm"
                )
              )
            )
          )
        : null,
      state.contextMenu
        ? h(
            "div",
            {
              className: "hermes-drive-context",
              role: "menu",
              style: { left: state.contextMenu.x + "px", top: state.contextMenu.y + "px" },
              onClick: function (event) {
                event.stopPropagation();
              },
            },
            state.contextMenu.mode === "background"
              ? h(React.Fragment, null,
                  h("span", { className: "hermes-drive-context-label" }, currentRoot.label || "Drive"),
                  h("button", { type: "button", role: "menuitem", onClick: createFolder, disabled: !canWrite }, "New Folder"),
                  h("button", { type: "button", role: "menuitem", onClick: createFile, disabled: !canWrite }, "New File"),
                  h("button", { type: "button", role: "menuitem", onClick: openUploadFiles, disabled: !canWrite }, "Upload Files"),
                  h("button", { type: "button", role: "menuitem", onClick: openUploadFolder, disabled: !canWrite }, "Upload Folder"),
                  h("button", { type: "button", role: "menuitem", onClick: function () { loadItems(state.path); } }, "Refresh")
                )
              : state.contextMenu.mode === "selection"
                ? h(React.Fragment, null,
                    h("span", { className: "hermes-drive-context-label" }, selectedCount + " selected"),
                    state.location === "trash"
                      ? h("button", { type: "button", role: "menuitem", onClick: restoreSelected }, "Restore Selected")
                      : h(React.Fragment, null,
                          h("button", { type: "button", role: "menuitem", onClick: copySelectedWithPrompt }, "Copy"),
                          h("button", { type: "button", role: "menuitem", onClick: moveSelectedWithPrompt }, "Move"),
                          h("button", { type: "button", role: "menuitem", onClick: trashSelected }, "Trash Selected")
                        ),
                    h("button", { type: "button", role: "menuitem", onClick: function () { patch({ selectedPaths: {}, contextMenu: null }); } }, "Clear Selection")
                  )
                : h(React.Fragment, null,
                    contextItem.trashed ? h("button", { type: "button", role: "menuitem", onClick: function () { restoreItem(contextItem); } }, "Restore") : null,
                    !contextItem.trashed && contextItem.kind === "file"
                      ? h("a", { role: "menuitem", href: codeEditUrl(contextItem) }, "Edit in Code")
                      : null,
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { renameItem(contextItem); } }, "Rename"),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { duplicateItem(contextItem); } }, "Duplicate"),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { copyItemWithPrompt(contextItem); } }, "Copy"),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { moveItemWithPrompt(contextItem); } }, "Move"),
                    !contextItem.trashed && contextItem.kind === "file"
                      ? h("a", { role: "menuitem", href: api("/download?path=" + encodeURIComponent(contextItem.path) + "&root=" + encodeURIComponent(itemRoot(contextItem) || "")), target: "_blank", rel: "noreferrer" }, "Download")
                      : null,
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { deleteItem(contextItem); } }, "Move to Trash")
                  )
          )
        : null
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN, DrivePage);
})();
