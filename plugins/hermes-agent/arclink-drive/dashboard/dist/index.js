(function () {
  "use strict";

  const PLUGIN = "arclink-drive";
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
      preview: null,
      busy: false,
      contextMenu: null,
      draggingItem: null,
      dropActive: false,
      errorMessage: "",
      confirmDialog: null,
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

    function loadItems(nextPath, nextQuery, nextFavorites) {
      const targetPath = nextPath || state.path;
      const query = typeof nextQuery === "string" ? nextQuery : state.query;
      const favoritesOnly = typeof nextFavorites === "boolean" ? nextFavorites : state.favoritesOnly;
      patch({ loading: true, path: targetPath, location: "files", query: query, favoritesOnly: favoritesOnly, errorMessage: "" });
      const params = new URLSearchParams({ path: targetPath, query: query });
      if (state.root) params.set("root", state.root);
      if (favoritesOnly) params.set("favorites_only", "true");
      fetchJSON(api("/items?" + params.toString()))
        .then(function (data) {
          patch({ loading: false, items: data.items || [], path: data.path || targetPath, location: "files", selected: null, selectedPaths: {}, preview: null });
        })
        .catch(function (error) {
          patch({ loading: false, items: [], selected: null, preview: null, errorMessage: error.message || "Unable to load Drive" });
        });
    }

    function loadTrash() {
      patch({ loading: true, location: "trash", favoritesOnly: false, query: "", selected: null, selectedPaths: {}, preview: null, errorMessage: "" });
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
          patch({ loading: false, location: "trash", trashItems: items, selected: null, selectedPaths: {}, preview: null });
        })
        .catch(function (error) {
          patch({ loading: false, location: "trash", trashItems: [], selected: null, preview: null, errorMessage: error.message || "Unable to load trash" });
        });
    }

    function loadStatus() {
      SDK.fetchJSON(api("/status"))
        .then(function (status) {
          const roots = (status.roots || []).filter(function (root) { return root.available; });
          const root = status.default_root || (roots[0] && roots[0].id) || "";
          patch({ status: status, roots: roots, root: root, loading: false });
          if (status.available) {
            const params = new URLSearchParams({ path: "/", query: "" });
            if (root) params.set("root", root);
            fetchJSON(api("/items?" + params.toString()))
              .then(function (data) {
                patch({ loading: false, items: data.items || [], path: data.path || "/", location: "files", selected: null, selectedPaths: {}, preview: null });
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
        loadItems(item.path, "", false);
        return;
      }
      patch({ selected: item, preview: null });
      if (!item.text) return;
      const params = new URLSearchParams({ path: item.path });
      if (state.root) params.set("root", state.root);
      fetchJSON(api("/content?" + params.toString()))
        .then(function (data) {
          patch({ preview: data });
        })
        .catch(function () {
          patch({ preview: { path: item.path, content: "" } });
        });
    }

    function uploadFiles(files, targetPath) {
      if (!files || !files.length) return;
      const fileList = Array.prototype.slice.call(files);
      const targetFolder = normalizeFolder(targetPath || state.path);
      let conflict = "reject";
      if (targetFolder === normalizeFolder(state.path)) {
        const existingNames = {};
        (state.items || []).forEach(function (item) {
          existingNames[item.name] = true;
        });
        const conflicts = fileList.filter(function (file) {
          return existingNames[file.name];
        });
        if (conflicts.length) {
          askConfirm({
            title: "Keep both uploads?",
            message: conflicts.length + " uploaded file(s) already exist in " + targetFolder + ". ArcLink can keep both copies with safe copy names.",
            confirmLabel: "Keep Both",
          }).then(function (confirmed) {
            if (!confirmed) {
              patch({ dropActive: false, contextMenu: null });
              return;
            }
            startUpload(fileList, targetFolder, "keep-both");
          });
          return;
        }
      }
      startUpload(fileList, targetFolder, conflict);
    }

    function startUpload(fileList, targetFolder, conflict) {
      const body = new FormData();
      body.append("path", targetFolder);
      if (state.root) body.append("root", state.root);
      body.append("conflict", conflict);
      fileList.forEach(function (file) {
        body.append("files", file, file.name);
      });
      patch({ busy: true, dropActive: false, errorMessage: "" });
      fetchJSON(api("/upload"), { method: "POST", body: body })
        .then(function () {
          patch({ busy: false });
          loadItems(state.path);
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "Upload failed" });
        });
    }

    function createFolder() {
      const name = (window.prompt("Folder name") || "").trim();
      if (!name) return;
      requestJSON("/mkdir", { path: state.path, name: name }).then(function (data) {
        if (data) loadItems(state.path);
      });
    }

    function createFile() {
      const name = (window.prompt("File name") || "").trim();
      if (!name) return;
      requestJSON("/new-file", { path: state.path, name: name, content: "" }).then(function (data) {
        if (data) loadItems(state.path);
      });
    }

    function toggleFavorite(item, event) {
      if (event) event.stopPropagation();
      requestJSON("/favorite", { path: item.path, favorite: !item.favorite }).then(function (data) {
        if (data) loadItems(state.path);
      });
    }

    function renameItem(item) {
      const name = (window.prompt("Rename", item.name) || "").trim();
      if (!name || name === item.name) {
        patch({ contextMenu: null });
        return;
      }
      requestJSON("/rename", { path: item.path, name: name }).then(function (data) {
        if (data) loadItems(state.path);
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
        requestJSON("/move", { path: item.path, destination_path: destination }).then(function (data) {
          if (data) loadItems(state.path);
        });
      });
    }

    function duplicateItem(item) {
      requestJSON("/duplicate", { path: item.path }).then(function (data) {
        if (data) loadItems(state.path);
      });
    }

    function copyItemWithPrompt(item) {
      const destination = window.prompt("Copy to path", joinPath(parentPath(item.path), nameFromPath(item.path)));
      if (destination === null) {
        patch({ contextMenu: null });
        return;
      }
      requestJSON("/copy", { path: item.path, destination_path: destination, conflict: "keep-both" }).then(function (data) {
        if (data) loadItems(state.path);
      });
    }

    function moveItemWithPrompt(item) {
      const folder = window.prompt("Move to folder path", parentPath(item.path));
      if (folder === null) {
        patch({ contextMenu: null });
        return;
      }
      moveItemToFolder(item, folder);
    }

    function moveDraggedPath(sourcePath, destinationFolder) {
      const item = state.items.filter(function (candidate) {
        return candidate.path === sourcePath;
      })[0] || { path: sourcePath, name: nameFromPath(sourcePath), kind: "file" };
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
        requestJSON("/delete", { path: item.path }).then(function (data) {
          if (data) loadItems(state.path);
        });
      });
    }

    function restoreItem(item) {
      if (!item || !item.trashed) return;
      requestJSON("/restore", { trash_path: item.trash_path || item.path }).then(function (data) {
        if (data) loadTrash();
      });
    }

    function selectedPathList() {
      return Object.keys(state.selectedPaths || {}).filter(function (path) {
        return state.selectedPaths[path];
      });
    }

    function toggleSelected(item, event) {
      event.stopPropagation();
      const next = Object.assign({}, state.selectedPaths || {});
      if (next[item.path]) {
        delete next[item.path];
      } else {
        next[item.path] = true;
      }
      patch({ selectedPaths: next, selected: item });
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
        requestJSON("/batch", { action: "trash", paths: paths }).then(function (data) {
          if (data) {
            const message = batchFailureMessage(data, "trash");
            loadItems(state.path);
            if (message) patch({ errorMessage: message, selectedPaths: {} });
          }
        });
      });
    }

    function restoreSelected() {
      const paths = selectedPathList();
      if (!paths.length) return;
      requestJSON("/batch", { action: "restore", paths: paths }).then(function (data) {
        if (data) {
          const message = batchFailureMessage(data, "restore");
          loadTrash();
          if (message) patch({ errorMessage: message, selectedPaths: {} });
        }
      });
    }

    function favoriteSelected(favorite) {
      const paths = selectedPathList();
      if (!paths.length) return;
      requestJSON("/batch", { action: "favorite", paths: paths, favorite: favorite }).then(function (data) {
        if (data) {
          const message = batchFailureMessage(data, "favorite");
          loadItems(state.path);
          if (message) patch({ errorMessage: message });
        }
      });
    }

    function copySelectedWithPrompt() {
      const paths = selectedPathList();
      if (!paths.length) return;
      const folder = window.prompt("Copy selected item(s) to folder path", state.path);
      if (folder === null) return;
      requestJSON("/batch", { action: "copy", paths: paths, destination_folder: folder, conflict: "keep-both" }).then(function (data) {
        if (data) {
          const message = batchFailureMessage(data, "copy");
          loadItems(state.path);
          if (message) patch({ errorMessage: message });
        }
      });
    }

    function moveSelectedWithPrompt() {
      const paths = selectedPathList();
      if (!paths.length) return;
      const folder = window.prompt("Move selected item(s) to folder path", state.path);
      if (folder === null) return;
      askConfirm({
        title: "Move selected?",
        message: "Move " + paths.length + " selected item(s) to " + folder + "?",
        confirmLabel: "Move",
      }).then(function (confirmed) {
        if (!confirmed) return;
        requestJSON("/batch", { action: "move", paths: paths, destination_folder: folder }).then(function (data) {
          if (data) {
            const message = batchFailureMessage(data, "move");
            loadItems(state.path);
            if (message) patch({ errorMessage: message, selectedPaths: {} });
          }
        });
      });
    }

    function switchRoot(rootId) {
      patch({ root: rootId, path: "/", location: "files", query: "", favoritesOnly: false, selected: null, selectedPaths: {}, preview: null });
      const params = new URLSearchParams({ root: rootId, path: "/", query: "" });
      fetchJSON(api("/items?" + params.toString()))
        .then(function (data) {
          patch({ loading: false, items: data.items || [], path: data.path || "/", location: "files", selected: null, selectedPaths: {}, preview: null });
        })
        .catch(function (error) {
          patch({ loading: false, items: [], selected: null, preview: null, errorMessage: error.message || "Unable to load Drive" });
        });
    }

    function sortedItems() {
      const items = (state.location === "trash" ? state.trashItems || [] : state.items || []).slice();
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
        h("button", { key: "drive", type: "button", onClick: function () { loadItems("/", "", false); } }, "Drive"),
        h("button", { key: "root", type: "button", onClick: function () { loadItems("/", "", false); } }, rootLabel),
      ];
      if (state.location === "trash") {
        nodes.push(h("button", { key: "trash", type: "button", onClick: loadTrash }, "Trash"));
        return nodes;
      }
      let current = "";
      parts.forEach(function (part) {
        current += "/" + part;
        nodes.push(h("button", { key: current, type: "button", onClick: function () { loadItems(current, "", false); } }, part));
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
          mode: selectedPathList().length > 1 && state.selectedPaths[item.path] ? "selection" : "item",
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

    useEffect(function () {
      loadStatus();
    }, []);

    useEffect(function () {
      function closeMenu(event) {
        if (event.key === "Escape") {
          patch({ contextMenu: null, confirmDialog: null });
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
        className: "arclink-drive" + (state.dropActive ? " dropping" : ""),
        onClick: function () {
          if (state.contextMenu) patch({ contextMenu: null });
        },
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
          const sourcePath = event.dataTransfer.getData("application/x-arclink-drive-path");
          patch({ dropActive: false });
          if (sourcePath) {
            moveDraggedPath(sourcePath, state.path);
            return;
          }
          uploadFiles(event.dataTransfer.files, state.path);
        },
      },
      h(
        "header",
        { className: "arclink-drive-toolbar" },
        h(
          "div",
          { className: "arclink-drive-title" },
          h("h1", null, "ArcLink Drive"),
          h("p", null, currentRoot.label ? currentRoot.label + " - " + (currentRoot.path || "/") : status.backend ? status.backend + " - " + (status.local_root || status.mount || "/") : "Agent knowledge")
        ),
        h(
          "div",
          { className: "arclink-drive-actions" },
          h("button", { type: "button", onClick: createFolder, disabled: !canWrite }, "New Folder"),
          h("button", { type: "button", onClick: createFile, disabled: !canWrite }, "New File"),
          h("button", { type: "button", onClick: function () { fileInput.current && fileInput.current.click(); }, disabled: !canWrite }, "Upload"),
          h("button", { type: "button", onClick: function () { loadItems(state.path); }, disabled: !status.available }, "Refresh"),
          status.url
            ? h("a", { href: status.url, target: "_blank", rel: "noreferrer" }, "Open")
            : null,
          h("input", {
            ref: fileInput,
            type: "file",
            multiple: true,
            className: "arclink-drive-hidden",
            onChange: function (event) {
              uploadFiles(event.target.files, state.path);
              event.target.value = "";
            },
          })
        )
      ),
      state.errorMessage ? h("div", { className: "arclink-drive-error" }, state.errorMessage) : null,
      status.available
        ? h(
            "div",
            { className: "arclink-drive-main" },
            h(
              "aside",
              { className: "arclink-drive-browser" },
              h(
                "div",
                { className: "arclink-drive-roots" },
                (state.roots || []).map(function (root) {
                  return h("button", { key: root.id, type: "button", className: state.root === root.id ? "active" : "", onClick: function () { switchRoot(root.id); } }, root.label);
                })
              ),
              h(
                "div",
                { className: "arclink-drive-filters" },
                h("button", { type: "button", onClick: function () { loadItems(parentPath(state.path), "", false); }, disabled: state.path === "/" }, "Up"),
                h("button", { type: "button", className: state.favoritesOnly ? "active" : "", onClick: function () { loadItems(state.path, state.query, !state.favoritesOnly); } }, "Favorites"),
                h("button", { type: "button", className: state.location === "trash" ? "active" : "", onClick: loadTrash }, "Trash"),
                h("select", { value: state.sortKey, onChange: function (event) { patch({ sortKey: event.target.value }); } },
                  h("option", { value: "name" }, "Name"),
                  h("option", { value: "kind" }, "Kind"),
                  h("option", { value: "modified" }, "Modified"),
                  h("option", { value: "size" }, "Size")
                ),
                h("button", { type: "button", onClick: function () { patch({ view: state.view === "list" ? "grid" : "list" }); } }, state.view === "list" ? "Grid" : "List")
              ),
              selectedCount
                ? h("div", { className: "arclink-drive-selection" },
                    h("span", null, selectedCount + " selected"),
                    state.location === "trash"
                      ? h("button", { type: "button", onClick: restoreSelected }, "Restore")
                      : h(React.Fragment, null,
                          h("button", { type: "button", onClick: function () { favoriteSelected(true); } }, "Favorite"),
                          h("button", { type: "button", onClick: function () { favoriteSelected(false); } }, "Unfavorite"),
                          h("button", { type: "button", onClick: copySelectedWithPrompt }, "Copy To..."),
                          h("button", { type: "button", onClick: moveSelectedWithPrompt }, "Move To..."),
                          h("button", { type: "button", onClick: trashSelected }, "Trash")
                        ),
                    h("button", { type: "button", onClick: function () { patch({ selectedPaths: {} }); } }, "Clear")
                  )
                : null,
              state.location === "trash"
                ? null
                : h("input", {
                    className: "arclink-drive-search",
                    value: state.query,
                    placeholder: "Search",
                    onChange: function (event) {
                      const value = event.target.value;
                      patch({ query: value });
                      window.clearTimeout(DrivePage._timer);
                      DrivePage._timer = window.setTimeout(function () {
                        loadItems("/", value, state.favoritesOnly);
                      }, 180);
                    },
                  }),
              h("div", { className: "arclink-drive-path" }, breadcrumbs()),
              state.location === "trash"
                ? null
                : h(
                    "div",
                    { className: "arclink-drive-drop-hint", onContextMenu: openBackgroundContextMenu },
                    "Drop files here to upload, or drag Drive items onto folders to move them after confirmation."
                  ),
              h(
                "div",
                { className: "arclink-drive-items " + state.view, onContextMenu: openBackgroundContextMenu },
                state.loading
                  ? h("div", { className: "arclink-drive-empty" }, "Loading")
                  : visibleItems.length
                    ? visibleItems.map(function (item) {
                        return h(
                          "button",
                          {
                            key: item.path,
                            type: "button",
                            draggable: true,
                            className:
                              "arclink-drive-item " +
                              (selected && selected.path === item.path ? "selected " : "") +
                              (state.selectedPaths[item.path] ? "checked " : "") +
                              (state.draggingItem === item.path ? "dragging" : ""),
                            onClick: function () {
                              openItem(item);
                            },
                            onContextMenu: function (event) {
                              openContextMenu(item, event);
                            },
                            onDragStart: function (event) {
                              event.dataTransfer.effectAllowed = "move";
                              event.dataTransfer.setData("application/x-arclink-drive-path", item.path);
                              event.dataTransfer.setData("text/plain", item.path);
                              patch({ draggingItem: item.path });
                            },
                            onDragEnd: function () {
                              patch({ draggingItem: null, dropActive: false });
                            },
                            onDragOver: function (event) {
                              if (item.kind === "folder" && state.draggingItem) {
                                event.preventDefault();
                                event.dataTransfer.dropEffect = "move";
                              }
                            },
                            onDrop: function (event) {
                              if (item.kind !== "folder") return;
                              event.preventDefault();
                              event.stopPropagation();
                              const sourcePath = event.dataTransfer.getData("application/x-arclink-drive-path");
                              if (sourcePath) {
                                moveDraggedPath(sourcePath, item.path);
                                return;
                              }
                              uploadFiles(event.dataTransfer.files, item.path);
                            },
                          },
                          h("input", {
                            type: "checkbox",
                            checked: !!state.selectedPaths[item.path],
                            onChange: function (event) { toggleSelected(item, event); },
                            onClick: function (event) { event.stopPropagation(); },
                          }),
                          h("span", { className: "arclink-drive-icon" }, item.kind === "folder" ? "DIR" : "FILE"),
                          h("span", { className: "arclink-drive-name" }, item.name),
                          h("span", { className: "arclink-drive-meta" }, item.trashed ? "Deleted " + (item.deleted_at || "") : item.kind === "folder" ? "Folder" : displaySize(item.size)),
                          item.trashed
                            ? h("span", { className: "arclink-drive-star", onClick: function (event) { event.stopPropagation(); restoreItem(item); } }, "Restore")
                            : h("span", { className: "arclink-drive-star", onClick: function (event) { toggleFavorite(item, event); } }, item.favorite ? "Fav" : "Mark")
                        );
                      })
                    : h("div", { className: "arclink-drive-empty" }, "No items")
              )
            ),
            h(
              "section",
              { className: "arclink-drive-preview" },
              selected
                ? h(
                    React.Fragment,
                    null,
                    h(
                      "div",
                      { className: "arclink-drive-preview-head" },
                      h("div", null, h("h2", null, selected.name), h("p", null, selected.path)),
                      h(
                        "div",
                        { className: "arclink-drive-preview-actions" },
                        selected.trashed
                          ? h("button", { type: "button", onClick: function () { restoreItem(selected); } }, "Restore")
                          : null,
                        !selected.trashed && selected.kind === "file"
                          ? h("a", { href: api("/download?path=" + encodeURIComponent(selected.path) + "&root=" + encodeURIComponent(state.root || "")), target: "_blank", rel: "noreferrer" }, "Download")
                          : null,
                        selected.trashed ? null : h("button", { type: "button", onClick: function () { duplicateItem(selected); } }, "Duplicate"),
                        selected.trashed ? null : h("button", { type: "button", onClick: function () { copyItemWithPrompt(selected); } }, "Copy"),
                        selected.trashed ? null : h("button", { type: "button", onClick: function () { renameItem(selected); } }, "Rename"),
                        selected.trashed ? null : h("button", { type: "button", onClick: function () { moveItemWithPrompt(selected); } }, "Move"),
                        selected.trashed ? null : h("button", { type: "button", onClick: function (event) { toggleFavorite(selected, event); } }, selected.favorite ? "Unfavorite" : "Favorite"),
                        selected.trashed ? null : h("button", { type: "button", onClick: function () { deleteItem(selected); } }, "Move to Trash")
                      )
                    ),
                    state.preview
                      ? h("pre", { className: "arclink-drive-text-preview" }, state.preview.content)
                      : h("div", { className: "arclink-drive-file-facts" }, h("span", null, currentRoot.label || state.root || "Drive"), h("span", null, selected.kind || "item"), h("span", null, selected.mime || "file"), h("span", null, displaySize(selected.size)), h("span", null, selected.modified || ""), h("span", null, selected.path || ""))
                  )
                : h("div", { className: "arclink-drive-empty" }, "Select an item")
            )
          )
        : h("div", { className: "arclink-drive-empty full" }, "ArcLink Drive is not available"),
      state.dropActive ? h("div", { className: "arclink-drive-drop-overlay" }, "Drop to upload") : null,
      confirmDialog
        ? h(
            "div",
            { className: "arclink-drive-confirm-backdrop", role: "presentation" },
            h(
              "section",
              { className: "arclink-drive-confirm", role: "dialog", "aria-modal": "true", "aria-label": confirmDialog.title },
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
                { className: "arclink-drive-confirm-actions" },
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
              className: "arclink-drive-context",
              role: "menu",
              style: { left: state.contextMenu.x + "px", top: state.contextMenu.y + "px" },
              onClick: function (event) {
                event.stopPropagation();
              },
            },
            state.contextMenu.mode === "background"
              ? h(React.Fragment, null,
                  h("span", { className: "arclink-drive-context-label" }, currentRoot.label || "Drive"),
                  h("button", { type: "button", role: "menuitem", onClick: createFolder, disabled: !canWrite }, "New Folder"),
                  h("button", { type: "button", role: "menuitem", onClick: createFile, disabled: !canWrite }, "New File"),
                  h("button", { type: "button", role: "menuitem", onClick: function () { fileInput.current && fileInput.current.click(); patch({ contextMenu: null }); }, disabled: !canWrite }, "Upload"),
                  h("button", { type: "button", role: "menuitem", onClick: function () { loadItems(state.path); } }, "Refresh")
                )
              : state.contextMenu.mode === "selection"
                ? h(React.Fragment, null,
                    h("span", { className: "arclink-drive-context-label" }, selectedCount + " selected"),
                    state.location === "trash"
                      ? h("button", { type: "button", role: "menuitem", onClick: restoreSelected }, "Restore Selected")
                      : h(React.Fragment, null,
                          h("button", { type: "button", role: "menuitem", onClick: function () { favoriteSelected(true); } }, "Favorite Selected"),
                          h("button", { type: "button", role: "menuitem", onClick: function () { favoriteSelected(false); } }, "Unfavorite Selected"),
                          h("button", { type: "button", role: "menuitem", onClick: copySelectedWithPrompt }, "Copy Selected To..."),
                          h("button", { type: "button", role: "menuitem", onClick: moveSelectedWithPrompt }, "Move Selected To..."),
                          h("button", { type: "button", role: "menuitem", onClick: trashSelected }, "Trash Selected")
                        ),
                    h("button", { type: "button", role: "menuitem", onClick: function () { patch({ selectedPaths: {}, contextMenu: null }); } }, "Clear Selection")
                  )
                : h(React.Fragment, null,
                    h("button", { type: "button", role: "menuitem", onClick: function () { openItem(contextItem); } }, "Open"),
                    contextItem.trashed ? h("button", { type: "button", role: "menuitem", onClick: function () { restoreItem(contextItem); } }, "Restore") : null,
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { renameItem(contextItem); } }, "Rename"),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { duplicateItem(contextItem); } }, "Duplicate"),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { copyItemWithPrompt(contextItem); } }, "Copy To..."),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { moveItemWithPrompt(contextItem); } }, "Move To..."),
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function (event) { toggleFavorite(contextItem, event); } }, contextItem.favorite ? "Unfavorite" : "Favorite"),
                    !contextItem.trashed && contextItem.kind === "file"
                      ? h("a", { role: "menuitem", href: api("/download?path=" + encodeURIComponent(contextItem.path) + "&root=" + encodeURIComponent(state.root || "")), target: "_blank", rel: "noreferrer" }, "Download")
                      : null,
                    contextItem.trashed ? null : h("button", { type: "button", role: "menuitem", onClick: function () { deleteItem(contextItem); } }, "Move to Trash")
                  )
          )
        : null
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN, DrivePage);
})();
