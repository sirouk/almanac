(function () {
  "use strict";

  const PLUGIN = "code";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const React = SDK.React;
  const useEffect = SDK.hooks.useEffect;
  const useState = SDK.hooks.useState;

  function h(type, props) {
    const children = Array.prototype.slice.call(arguments, 2);
    return React.createElement.apply(React, [type, props].concat(children));
  }

  function api(path) {
    return "/api/plugins/" + PLUGIN + path;
  }

  function parentPath(path) {
    if (!path || path === "/") return "/";
    const parts = path.replace(/^\/+|\/+$/g, "").split("/");
    parts.pop();
    return parts.length ? "/" + parts.join("/") : "/";
  }

  function joinPath(parent, name) {
    const base = !parent || parent === "/" ? "" : parent.replace(/\/$/, "");
    return base + "/" + String(name || "").replace(/^\/+/, "");
  }

  function basename(path) {
    const parts = String(path || "").replace(/^\/+|\/+$/g, "").split("/");
    return parts[parts.length - 1] || "/";
  }

  function itemRoot(item) {
    return String((item && (item.root || item.root_id)) || "workspace");
  }

  function itemKey(item) {
    return itemRoot(item) + ":" + String((item && item.path) || "/");
  }

  function pathKey(root, path) {
    return String(root || "workspace") + ":" + String(path || "/");
  }

  function repoKey(repo) {
    return String((repo && (repo.root_id || repo.root)) || "workspace") + ":" + String((repo && repo.path) || "/");
  }

  function dirname(path) {
    const clean = String(path || "").replace(/^\/+|\/+$/g, "");
    const parts = clean ? clean.split("/") : [];
    parts.pop();
    return parts.join("/");
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

  function fileExtension(item) {
    const name = String((item && (item.name || item.path)) || "");
    const match = /\.([A-Za-z0-9]+)$/.exec(name);
    return match ? match[1].slice(0, 12).toLowerCase() : "";
  }

  function fileIcon(item) {
    if (item.kind === "folder") return "";
    const language = String(item.language || "").toLowerCase();
    const byLanguage = {
      css: "CSS",
      html: "HTM",
      javascript: "JS",
      json: "JSN",
      markdown: "MD",
      python: "PY",
      shell: "SH",
      sql: "SQL",
      toml: "TOM",
      typescript: "TS",
      xml: "XML",
      yaml: "YML",
    };
    if (byLanguage[language]) return byLanguage[language];
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
    const language = String(item.language || "").toLowerCase();
    const name = String(item.name || item.path || "").toLowerCase();
    const ext = fileExtension({ name: name });
    if (["css", "html", "javascript", "python", "shell", "sql", "typescript"].indexOf(language) !== -1) return "kind-code";
    if (["json", "toml", "xml", "yaml"].indexOf(language) !== -1) return "kind-data";
    if (["md", "mdx", "markdown", "txt"].indexOf(language) !== -1 || ["md", "mdx", "txt"].indexOf(ext) !== -1) return "kind-doc";
    if (ext === "pdf") return "kind-pdf";
    if (["gif", "jpg", "jpeg", "png", "svg", "webp"].indexOf(ext) !== -1) return "kind-image";
    if (["m4a", "mov", "mp3", "mp4", "ogg", "wav", "webm"].indexOf(ext) !== -1) return "kind-media";
    if (["7z", "gz", "rar", "tar", "tgz", "zip"].indexOf(ext) !== -1) return "kind-archive";
    return "kind-file";
  }

  function renderFileIcon(item) {
    const label = fileIcon(item);
    return h(
      "span",
      {
        className:
          "hermes-code-fileicon " +
          (item.kind === "folder" ? "folder" : "file") +
          " " +
          fileKindClass(item) +
          (label.length > 3 ? " long-ext" : ""),
        style: item.kind === "folder" ? null : { "--file-accent": extensionColor(item) },
        title: item.kind === "folder" ? "Folder" : label ? label + " file" : "File",
      },
      item.kind === "folder" ? null : h("span", { className: "hermes-code-fileext" }, label)
    );
  }

  function previewKind(item) {
    if (!item || item.kind === "folder") return "";
    const ext = fileExtension(item);
    const mime = String(item.mime || "").toLowerCase();
    const language = String(item.language || "").toLowerCase();
    if (ext === "pdf" || mime === "application/pdf") return "pdf";
    if (mime.indexOf("image/") === 0 || ["gif", "jpeg", "jpg", "png", "svg", "webp"].indexOf(ext) !== -1) return "image";
    if (mime.indexOf("audio/") === 0 || ["mp3", "wav", "ogg", "m4a"].indexOf(ext) !== -1) return "audio";
    if (mime.indexOf("video/") === 0 || ["mov", "mp4", "webm"].indexOf(ext) !== -1) return "video";
    if (
      item.text ||
      mime.indexOf("text/") === 0 ||
      ["css", "csv", "env", "html", "ini", "js", "json", "log", "md", "mdx", "py", "sh", "sql", "toml", "ts", "txt", "xml", "yaml", "yml"].indexOf(ext) !== -1 ||
      ["css", "html", "javascript", "json", "markdown", "plaintext", "python", "shell", "sql", "toml", "typescript", "xml", "yaml"].indexOf(language) !== -1
    ) {
      return ext === "md" || ext === "mdx" || language === "markdown" ? "markdown" : "text";
    }
    return "";
  }

  function downloadUrl(item) {
    return api("/download?path=" + encodeURIComponent(item.path || "") + "&root=" + encodeURIComponent(itemRoot(item)));
  }

  function previewUrl(item) {
    return api("/preview?path=" + encodeURIComponent(item.path || "") + "&root=" + encodeURIComponent(itemRoot(item)));
  }

  function changeSort(a, b) {
    return String(a.path).localeCompare(String(b.path));
  }

  function CodePage() {
    const statePair = useState({
      loading: true,
      status: null,
      root: "workspace",
      path: "/",
      items: [],
      openFile: null,
      content: "",
      savedContent: "",
      dirty: false,
      busy: false,
      leftPanel: "explorer",
      repos: [],
      repo: null,
      source: null,
      sourceBusy: false,
      gitMessage: "",
      errorMessage: "",
      diff: null,
      fileTabs: [],
      trees: {},
      expanded: {},
      contextMenu: null,
      searchQuery: "",
      searchResults: [],
      searchBusy: false,
      lastGitResult: null,
      theme: "dark",
      sourcePickerOpen: false,
      sourcePickerRoot: "workspace",
      sourcePickerPath: "/",
      sourcePickerMessage: "",
      previewFullscreen: false,
    });
    const state = statePair[0];
    const setState = statePair[1];

    function patch(next) {
      setState(function (current) {
        return Object.assign({}, current, typeof next === "function" ? next(current) : next);
      });
    }

    function confirmCleanSlate() {
      if (!state.dirty) return true;
      return window.confirm("Discard unsaved edits before opening another file?");
    }

    function loadItems(nextPath, nextRoot) {
      const targetPath = nextPath || state.path;
      const targetRoot = nextRoot || state.root || "workspace";
      patch({ loading: true, root: targetRoot, path: targetPath, errorMessage: "" });
      fetchJSON(api("/items?path=" + encodeURIComponent(targetPath) + "&root=" + encodeURIComponent(targetRoot)))
        .then(function (data) {
          patch({ loading: false, root: data.root || targetRoot, path: data.path || targetPath, items: data.items || [] });
          loadTree(data.root || targetRoot);
        })
        .catch(function (error) {
          patch({ loading: false, items: [], errorMessage: error.message || "Unable to load files" });
        });
    }

    function loadTree(root) {
      const targetRoot = root || state.root || "workspace";
      fetchJSON(api("/tree?path=" + encodeURIComponent("/") + "&root=" + encodeURIComponent(targetRoot) + "&depth=3"))
        .then(function (data) {
          patch(function (current) {
            const trees = Object.assign({}, current.trees || {});
            trees[data.root || targetRoot] = data.tree || null;
            return { trees: trees };
          });
        })
        .catch(function () {
          patch(function (current) {
            const trees = Object.assign({}, current.trees || {});
            trees[targetRoot] = null;
            return { trees: trees };
          });
        });
    }

    function loadSource(repo) {
      if (!repo) return;
      patch({ sourceBusy: true, errorMessage: "" });
      fetchJSON(api("/git/status?repo=" + encodeURIComponent(repo.path || "/") + "&root=" + encodeURIComponent(repo.root_id || repo.root || "workspace")))
        .then(function (data) {
          patch({ sourceBusy: false, source: data });
        })
        .catch(function (error) {
          patch({ sourceBusy: false, source: null, errorMessage: error.message || "Unable to load source control" });
        });
    }

    function openRepo(repo) {
      patch({ repo: repo, leftPanel: "source", gitMessage: "", source: null, sourcePickerOpen: false, sourcePickerMessage: "" });
      loadSource(repo);
    }

    function closeRepo() {
      patch({ repo: null, source: null, gitMessage: "" });
    }

    function loadRepos(selectFirst) {
      fetchJSON(api("/repos"))
        .then(function (data) {
          const repos = data.repos || [];
          const currentRepo = state.repo && repos.filter(function (repo) { return repoKey(repo) === repoKey(state.repo); })[0];
          const nextRepo = currentRepo || (selectFirst && repos.length ? repos[0] : null);
          patch({ repos: repos, repo: nextRepo });
          if (nextRepo) loadSource(nextRepo);
        })
        .catch(function (error) {
          patch({ repos: [], repo: null, source: null, errorMessage: error.message || "Unable to scan repositories" });
        });
    }

    function openSourcePicker() {
      const sourceRoot = state.repo ? (state.repo.root_id || state.repo.root || "workspace") : state.root || "workspace";
      patch({ sourcePickerOpen: true, sourcePickerRoot: sourceRoot, sourcePickerPath: state.repo ? state.repo.path : "/", sourcePickerMessage: "" });
      const roots = (state.status && state.status.roots) || [];
      roots.forEach(function (root) {
        if (root.available) loadTree(root.id);
      });
    }

    function openRepositoryFromPicker(path, root) {
      const targetPath = path || state.sourcePickerPath || "/";
      const targetRoot = root || state.sourcePickerRoot || "workspace";
      patch({ sourceBusy: true, sourcePickerMessage: "" });
      fetchJSON(api("/repos/open"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: targetPath, root: targetRoot }),
      })
        .then(function (data) {
          const repo = data.repo;
          patch(function (current) {
            const repos = (current.repos || []).filter(function (candidate) {
              return repoKey(candidate) !== repoKey(repo);
            });
            repos.push(repo);
            repos.sort(function (a, b) {
              return String(a.root_label + ":" + a.path).localeCompare(String(b.root_label + ":" + b.path));
            });
            return {
              repos: repos,
              repo: repo,
              source: data.status || null,
              sourceBusy: false,
              leftPanel: "source",
              sourcePickerOpen: false,
              sourcePickerMessage: "",
              errorMessage: "",
            };
          });
        })
        .catch(function (error) {
          patch({ sourceBusy: false, sourcePickerMessage: error.message || "That folder is not a git repository" });
        });
    }

    function loadStatus() {
      SDK.fetchJSON(api("/status"))
        .then(function (status) {
          const roots = status.roots || [];
          const defaultRoot = (roots.filter(function (root) { return root.id === "workspace" && root.available; })[0] || roots.filter(function (root) { return root.available; })[0] || {}).id || "workspace";
          patch({ status: status, loading: false, root: defaultRoot });
          if (status.available) {
            roots.forEach(function (root) {
              if (root.available) loadTree(root.id);
            });
            loadItems("/", defaultRoot);
            loadRepos(true);
            const params = new URLSearchParams(window.location.search || "");
            const path = params.get("path");
            const root = params.get("root") || defaultRoot;
            if (path) {
              loadItems(parentPath(path), root);
              openItem({ path: path, root: root, name: basename(path), kind: "file", text: true }, true);
            }
          }
        })
        .catch(function () {
          patch({ status: { available: false }, loading: false });
        });
    }

    function rememberTab(file, pinned) {
      if (!file || !file.path) return;
      patch(function (current) {
        const existing = (current.fileTabs || []).filter(function (tab) {
          return itemKey(tab) === itemKey(file);
        })[0] || {};
        let tabs = (current.fileTabs || []).filter(function (tab) {
          return itemKey(tab) !== itemKey(file);
        });
        const isPinned = !!(pinned || existing.pinned || existing.dirty);
        if (!isPinned) {
          tabs = tabs.filter(function (tab) {
            return tab.pinned || tab.dirty;
          });
        }
        tabs.push({
          root: itemRoot(file),
          path: file.path,
          name: file.name || basename(file.path),
          dirty: !!existing.dirty,
          pinned: isPinned,
          content: existing.content !== undefined ? existing.content : file.content || "",
          savedContent: existing.savedContent !== undefined ? existing.savedContent : file.content || "",
          hash: file.hash || existing.hash || "",
          language: file.language || existing.language || "plaintext",
          editable: file.editable !== false,
          previewKind: file.previewKind || existing.previewKind || previewKind(file),
          previewUrl: file.previewUrl || existing.previewUrl || downloadUrl(file),
          previewContent: file.previewContent !== undefined ? file.previewContent : existing.previewContent,
          previewMode: !!(file.previewMode || existing.previewMode),
        });
        return { fileTabs: tabs.slice(-8) };
      });
    }

    function markTabDirty(path, dirty) {
      patch(function (current) {
        return {
          fileTabs: (current.fileTabs || []).map(function (tab) {
            return tab.path === path && itemRoot(tab) === (state.openFile ? itemRoot(state.openFile) : itemRoot(tab)) ? Object.assign({}, tab, { dirty: dirty }) : tab;
          }),
        };
      });
    }

    function updateTabBuffer(path, content, dirty) {
      patch(function (current) {
        return {
          fileTabs: (current.fileTabs || []).map(function (tab) {
            return tab.path === path && itemRoot(tab) === (current.openFile ? itemRoot(current.openFile) : itemRoot(tab)) ? Object.assign({}, tab, { content: content, dirty: dirty }) : tab;
          }),
        };
      });
    }

    function pinTab(path, root) {
      const targetKey = pathKey(root || (state.openFile && itemRoot(state.openFile)) || state.root || "workspace", path);
      patch(function (current) {
        return {
          fileTabs: (current.fileTabs || []).map(function (tab) {
            return itemKey(tab) === targetKey ? Object.assign({}, tab, { pinned: true }) : tab;
          }),
        };
      });
    }

    function closeTab(tab, event) {
      if (event) event.stopPropagation();
      if (tab.dirty && !window.confirm("Close " + tab.name + " without saving?")) return;
      patch(function (current) {
        const tabs = (current.fileTabs || []).filter(function (candidate) {
          return itemKey(candidate) !== itemKey(tab);
        });
        const active = current.openFile && itemKey(current.openFile) === itemKey(tab);
        const next = active ? tabs[tabs.length - 1] : null;
        return {
          fileTabs: tabs,
          openFile: active && next ? Object.assign({}, next, { editable: next.editable !== false }) : active ? null : current.openFile,
          content: active && next ? next.content || "" : active ? "" : current.content,
          savedContent: active && next ? next.savedContent || "" : active ? "" : current.savedContent,
          dirty: active && next ? !!next.dirty : active ? false : current.dirty,
          diff: active ? null : current.diff,
          previewFullscreen: active ? false : current.previewFullscreen,
        };
      });
    }

    function openDroppedTab(event) {
      event.preventDefault();
      const path = event.dataTransfer && event.dataTransfer.getData("text/hermes-code-path");
      const root = event.dataTransfer && event.dataTransfer.getData("text/hermes-code-root");
      if (!path || path === "/") return;
      openItem({ path: path, root: root || state.root || "workspace", name: basename(path), kind: "file", text: true }, true);
    }

    function openPreviewFile(item, pinned) {
      const kind = item.previewKind || previewKind(item);
      if (!kind) {
        patch({ errorMessage: "No preview available for " + (item.name || item.path || "this file") });
        return;
      }
      const previewFile = Object.assign({}, item, {
        root: itemRoot(item),
        kind: "file",
        name: item.name || basename(item.path),
        editable: false,
        previewKind: kind,
        previewUrl: item.previewUrl || previewUrl(item),
        previewContent: item.previewContent,
      });
      patch(function (current) {
        let tabs = (current.fileTabs || []).filter(function (tab) {
          return itemKey(tab) !== itemKey(previewFile);
        });
        const existing = (current.fileTabs || []).filter(function (tab) {
          return itemKey(tab) === itemKey(previewFile);
        })[0] || {};
        const isPinned = !!(pinned || existing.pinned);
        if (!isPinned) {
          tabs = tabs.filter(function (tab) {
            return tab.pinned || tab.dirty;
          });
        }
        tabs.push({
          root: itemRoot(previewFile),
          path: previewFile.path,
          name: previewFile.name,
          dirty: false,
          pinned: isPinned,
          content: "",
          savedContent: "",
          hash: "",
          language: previewFile.previewKind,
          editable: false,
          previewKind: previewFile.previewKind,
          previewUrl: previewFile.previewUrl,
          previewContent: previewFile.previewContent,
          previewMessage: previewFile.previewMessage,
        });
        return {
          fileTabs: tabs.slice(-8),
          openFile: previewFile,
          content: "",
          savedContent: "",
          dirty: false,
          diff: null,
          errorMessage: "",
        };
      });
    }

    function openReadOnlyPreview(item, pinned, message) {
      const kind = previewKind(item);
      if (!kind) {
        patch({ errorMessage: message || "Unable to open file" });
        return;
      }
      if (kind === "text" || kind === "markdown") {
        fetch(previewUrl(item), { credentials: "same-origin" })
          .then(function (response) {
            if (!response.ok) throw new Error(message || "Text preview unavailable");
            return response.text();
          })
          .then(function (content) {
            openPreviewFile(Object.assign({}, item, { previewKind: kind, previewContent: content }), pinned);
          })
          .catch(function (error) {
            openPreviewFile(Object.assign({}, item, { previewKind: kind, previewContent: "", previewMessage: error.message || message || "Text preview unavailable" }), pinned);
          });
        return;
      }
      openPreviewFile(Object.assign({}, item, { previewKind: kind }), pinned);
    }

    function openItem(item, pinned) {
      patch({ contextMenu: null });
      if (item.kind === "folder") {
        loadItems(item.path, itemRoot(item));
        patch(function (current) {
          const expanded = Object.assign({}, current.expanded || {});
          expanded[itemKey(item)] = true;
          return { expanded: expanded, root: itemRoot(item) };
        });
        return;
      }
      const previewable = previewKind(item);
      if (["pdf", "image", "audio", "video"].indexOf(previewable) !== -1) {
        openPreviewFile(Object.assign({}, item, { previewKind: previewable }), pinned);
        return;
      }
      const existingTab = (state.fileTabs || []).filter(function (tab) {
        return itemKey(tab) === itemKey(item);
      })[0];
      if (existingTab) {
        if (pinned) pinTab(existingTab.path, itemRoot(existingTab));
        patch({
          openFile: Object.assign({}, existingTab, { editable: existingTab.editable !== false }),
          content: existingTab.content || "",
          savedContent: existingTab.savedContent || "",
          dirty: !!existingTab.dirty,
          diff: null,
        });
        return;
      }
      fetchJSON(api("/file?path=" + encodeURIComponent(item.path) + "&root=" + encodeURIComponent(itemRoot(item))))
        .then(function (data) {
          const content = data.content || "";
          const file = Object.assign({ kind: "file" }, data);
          const kind = previewKind(file);
          patch(function (current) {
            let tabs = (current.fileTabs || []).filter(function (tab) {
              return itemKey(tab) !== itemKey(data);
            });
            if (!pinned) {
              tabs = tabs.filter(function (tab) {
                return tab.pinned || tab.dirty;
              });
            }
            tabs.push({
              root: itemRoot(data),
              path: data.path,
              name: data.name || basename(data.path),
              dirty: false,
              pinned: !!pinned,
              content: content,
              savedContent: content,
              hash: data.hash || "",
              language: data.language || "plaintext",
              editable: true,
              previewKind: kind,
              previewUrl: previewUrl(data),
              previewMode: false,
            });
            return {
              fileTabs: tabs.slice(-8),
              openFile: Object.assign({}, data, { kind: "file", editable: true, previewKind: kind, previewUrl: previewUrl(data), previewMode: false }),
              content: content,
              savedContent: content,
              dirty: false,
              diff: null,
              previewFullscreen: false,
            };
          });
        })
        .catch(function (error) {
          openReadOnlyPreview(item, pinned, error.message || "Unable to open file");
        });
    }

    function saveFile() {
      if (!state.openFile) return;
      patch({ busy: true, errorMessage: "" });
      fetchJSON(api("/save"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: state.openFile.path, root: itemRoot(state.openFile), content: state.content, expected_hash: state.openFile.hash || "" }),
      })
        .then(function (data) {
          patch(function (current) {
            return {
              busy: false,
              savedContent: current.content,
              dirty: false,
              openFile: Object.assign({}, current.openFile, { hash: data.hash, modified: data.modified }),
              fileTabs: (current.fileTabs || []).map(function (tab) {
                return current.openFile && itemKey(tab) === itemKey(current.openFile)
                  ? Object.assign({}, tab, { dirty: false, content: current.content, savedContent: current.content, hash: data.hash })
                  : tab;
              }),
            };
          });
          loadItems(state.path, state.root);
          if (state.repo) loadSource(state.repo);
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "Save failed" });
        });
    }

    function createFile() {
      if (!confirmCleanSlate()) return;
      const name = (window.prompt("File name") || "").trim();
      if (!name) return;
      const path = joinPath(state.path, name);
      const root = state.root || "workspace";
      patch(function (current) {
        const tabs = (current.fileTabs || []).filter(function (tab) {
          return itemKey(tab) !== pathKey(root, path);
        });
        tabs.push({ root: root, path: path, name: name, dirty: true, pinned: true, content: "", savedContent: "", hash: "", language: "plaintext", editable: true });
        return {
          fileTabs: tabs.slice(-8),
          openFile: { root: root, path: path, name: name, language: "plaintext", editable: true },
          content: "",
          savedContent: "",
          dirty: true,
          diff: null,
        };
      });
    }

    function fileOperation(endpoint, payload, confirmText) {
      if (confirmText && !window.confirm(confirmText)) return;
      patch({ busy: true, errorMessage: "" });
      fetchJSON(api(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      })
        .then(function () {
          patch({ busy: false });
          if (endpoint === "/ops/trash" && state.openFile && payload.path === state.openFile.path && (payload.root || "workspace") === itemRoot(state.openFile)) {
            patch(function (current) {
              return {
                openFile: null,
                content: "",
                savedContent: "",
                dirty: false,
                diff: null,
                fileTabs: (current.fileTabs || []).filter(function (tab) { return itemKey(tab) !== pathKey(payload.root || "workspace", payload.path); }),
              };
            });
          }
          loadItems(state.path, state.root);
          loadTree(payload.root || state.root);
          if (state.repo) loadSource(state.repo);
          if (state.searchQuery) runSearch(state.searchQuery);
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "File operation failed" });
        });
    }

    function renameItem(item) {
      const name = (window.prompt("Rename", item.name) || "").trim();
      if (!name || name === item.name) return;
      fileOperation("/ops/rename", { path: item.path, root: itemRoot(item), name: name });
    }

    function moveItem(item) {
      const destination = (window.prompt("Move to path", joinPath(parentPath(item.path), item.name)) || "").trim();
      if (!destination || destination === item.path) return;
      fileOperation("/ops/move", { path: item.path, root: itemRoot(item), destination: destination }, "Move " + item.path + " to " + destination + "?");
    }

    function duplicateItem(item) {
      fileOperation("/ops/duplicate", { path: item.path, root: itemRoot(item) });
    }

    function trashItem(item) {
      fileOperation("/ops/trash", { path: item.path, root: itemRoot(item), confirm: true }, "Move " + item.path + " to trash?");
    }

    function openContextMenu(event, item) {
      event.preventDefault();
      patch({
        contextMenu: {
          item: item,
          x: event.clientX,
          y: event.clientY,
        },
      });
    }

    function renderContextMenu() {
      if (!state.contextMenu || !state.contextMenu.item) return null;
      const item = state.contextMenu.item;
      const isRoot = item.path === "/";
      function closeThen(action) {
        patch({ contextMenu: null });
        if (action) action();
      }
      return h(
        "div",
        {
          className: "hermes-code-context-menu",
          style: { left: state.contextMenu.x + "px", top: state.contextMenu.y + "px" },
          role: "menu",
        },
        h("button", { type: "button", onClick: function () { closeThen(function () { openItem(item); }); } }, item.kind === "folder" ? "Open Folder" : "Open File"),
        h("button", { type: "button", disabled: isRoot, onClick: function () { closeThen(function () { renameItem(item); }); } }, "Rename"),
        h("button", { type: "button", disabled: isRoot, onClick: function () { closeThen(function () { moveItem(item); }); } }, "Move"),
        h("button", { type: "button", disabled: isRoot, onClick: function () { closeThen(function () { duplicateItem(item); }); } }, "Duplicate"),
        h("button", { type: "button", disabled: isRoot, onClick: function () { closeThen(function () { trashItem(item); }); } }, "Trash")
      );
    }

    function runSearch(query) {
      const nextQuery = typeof query === "string" ? query : state.searchQuery;
      if (!nextQuery.trim()) {
        patch({ searchQuery: nextQuery, searchResults: [], searchBusy: false });
        return;
      }
      patch({ searchQuery: nextQuery, searchBusy: true, errorMessage: "" });
      fetchJSON(api("/search?q=" + encodeURIComponent(nextQuery) + "&path=" + encodeURIComponent("/")))
        .then(function (data) {
          patch({ searchBusy: false, searchResults: data.results || [] });
        })
        .catch(function (error) {
          patch({ searchBusy: false, searchResults: [], errorMessage: error.message || "Search failed" });
        });
    }

    function scheduleSearch(value) {
      patch({ searchQuery: value });
      window.clearTimeout(CodePage._searchTimer);
      CodePage._searchTimer = window.setTimeout(function () {
        runSearch(value);
      }, 180);
    }

    function findTreeNode(path, root, node) {
      if (!node) return null;
      if (node.path === path && itemRoot(node) === root) return node;
      const children = node.children || [];
      for (let index = 0; index < children.length; index += 1) {
        const found = findTreeNode(path, root, children[index]);
        if (found) return found;
      }
      return null;
    }

    function createFolder() {
      const name = (window.prompt("Folder name") || "").trim();
      if (!name) return;
      patch({ busy: true, errorMessage: "" });
      fetchJSON(api("/mkdir"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: joinPath(state.path, name), root: state.root || "workspace" }),
      })
        .then(function () {
          patch({ busy: false });
          loadItems(state.path, state.root);
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "Folder creation failed" });
        });
    }

    function gitAction(endpoint, payload, confirmText) {
      if (!state.repo) return;
      if (confirmText && !window.confirm(confirmText)) return;
      patch({ sourceBusy: true, errorMessage: "" });
      fetchJSON(api(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ repo: state.repo.path, root: state.repo.root_id || state.repo.root || "workspace" }, payload || {})),
      })
        .then(function (data) {
          patch({ sourceBusy: false, source: data.status || state.source, lastGitResult: data.last_git_result || null });
          loadItems(state.path, state.root);
        })
        .catch(function (error) {
          patch({ sourceBusy: false, errorMessage: error.message || "Git action failed" });
        });
    }

    function commitStaged() {
      const message = state.gitMessage.trim();
      if (!message) return;
      gitAction("/git/commit", { message: message });
      patch({ gitMessage: "" });
    }

    function openChange(change) {
      if (!state.repo) return;
      if (!confirmCleanSlate()) return;
      patch({ sourceBusy: true, errorMessage: "" });
      fetchJSON(
        api(
          "/git/diff?repo=" +
            encodeURIComponent(state.repo.path) +
            "&root=" +
            encodeURIComponent(state.repo.root_id || state.repo.root || "workspace") +
            "&path=" +
            encodeURIComponent(change.path) +
            "&staged=" +
            encodeURIComponent(change.staged && !change.unstaged ? "true" : "false") +
            "&untracked=" +
            encodeURIComponent(change.untracked ? "true" : "false")
        )
      )
        .then(function (data) {
          patch({
            sourceBusy: false,
            diff: data,
            openFile: {
              root: state.repo.root_id || state.repo.root || "workspace",
              name: basename(change.path),
              path: joinPath(state.repo.path, change.path),
              editable: false,
              language: data.language || "plaintext",
            },
            content: "",
            savedContent: "",
            dirty: false,
          });
        })
        .catch(function (error) {
          patch({ sourceBusy: false, errorMessage: error.message || "Unable to open diff" });
        });
    }

    function togglePreviewMode() {
      if (!state.openFile || state.openFile.editable === false) return;
      patch(function (current) {
        const nextMode = !(current.openFile && current.openFile.previewMode);
        return {
          openFile: Object.assign({}, current.openFile, { previewMode: nextMode }),
          fileTabs: (current.fileTabs || []).map(function (tab) {
            return current.openFile && itemKey(tab) === itemKey(current.openFile) ? Object.assign({}, tab, { previewMode: nextMode }) : tab;
          }),
        };
      });
    }

    function canPreviewFile(file) {
      return !!(file && previewKind(file));
    }

    function renderMarkdownPreview(content) {
      const nodes = [];
      const lines = String(content || "").split(/\r?\n/);
      let codeLines = [];
      function flushCode(key) {
        if (!codeLines.length) return;
        nodes.push(h("pre", { key: "code:" + key }, codeLines.join("\n")));
        codeLines = [];
      }
      lines.forEach(function (line, index) {
        if (/^```/.test(line)) {
          if (codeLines.length) flushCode(index);
          else codeLines = [""];
          return;
        }
        if (codeLines.length) {
          codeLines.push(line);
          return;
        }
        const heading = /^(#{1,3})\s+(.+)$/.exec(line);
        if (heading) {
          nodes.push(h("h" + heading[1].length, { key: "h:" + index }, heading[2]));
          return;
        }
        const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
        if (bullet) {
          nodes.push(h("li", { key: "li:" + index }, bullet[1]));
          return;
        }
        nodes.push(line.trim() ? h("p", { key: "p:" + index }, line) : h("div", { key: "sp:" + index, className: "hermes-code-markdown-space" }));
      });
      flushCode("tail");
      return h("div", { className: "hermes-code-markdown-preview" }, nodes);
    }

    function renderPreviewBody(file) {
      const kind = file.previewKind || previewKind(file);
      const url = file.previewUrl || previewUrl(file);
      const content = file.previewContent !== undefined ? file.previewContent : state.content;
      if (file.previewMessage) return h("div", { className: "hermes-code-preview-empty" }, file.previewMessage);
      if (kind === "markdown") return renderMarkdownPreview(content);
      if (kind === "text") return h("pre", { className: "hermes-code-text-preview" }, content || "");
      if (kind === "pdf") {
        return h(
          "object",
          { className: "hermes-code-pdf-preview", data: url, type: "application/pdf" },
          h("a", { href: url, target: "_blank", rel: "noreferrer" }, "Open PDF")
        );
      }
      if (kind === "image") return h("img", { className: "hermes-code-media-preview", src: url, alt: file.name || "Preview" });
      if (kind === "audio") return h("audio", { className: "hermes-code-audio-preview", src: url, controls: true });
      if (kind === "video") return h("video", { className: "hermes-code-media-preview", src: url, controls: true });
      return h("div", { className: "hermes-code-preview-empty" }, "Preview unavailable");
    }

    function renderCodePreview(file) {
      const kind = file.previewKind || previewKind(file);
      return h(
        "div",
        { className: "hermes-code-preview" },
        h(
          "div",
          { className: "hermes-code-preview-head" },
          h("strong", null, kind === "markdown" ? "Markdown Preview" : kind ? kind.charAt(0).toUpperCase() + kind.slice(1) + " Preview" : "Preview"),
          h("span", null, file.name || basename(file.path)),
          canPreviewFile(file)
            ? h("button", { type: "button", onClick: function () { patch({ previewFullscreen: true }); } }, "Maximize")
            : null
        ),
        renderPreviewBody(file)
      );
    }

    function renderFullscreenPreview() {
      if (!state.previewFullscreen || !state.openFile) return null;
      return h(
        "div",
        { className: "hermes-code-preview-fullscreen", role: "dialog", "aria-modal": "true", "aria-label": "File preview" },
        h(
          "div",
          { className: "hermes-code-preview-fullbar" },
          h("strong", null, state.openFile.name || basename(state.openFile.path)),
          h("button", { type: "button", onClick: function () { patch({ previewFullscreen: false }); } }, "Close")
        ),
        renderPreviewBody(state.openFile)
      );
    }

    function renderDiff(diff) {
      return h(
        "div",
        { className: "hermes-code-diff" },
        h(
          "div",
          { className: "hermes-code-diff-head" },
          h("strong", null, diff.path),
          h("span", null, diff.mode)
        ),
        h(
          "div",
          { className: "hermes-code-diff-panes" },
          h("pre", null, diff.before || ""),
          h("pre", null, diff.after || "")
        ),
        h("pre", { className: "hermes-code-diff-unified" }, diff.diff || "No text diff available")
      );
    }

    function toggleExplorerNode(path) {
      const root = arguments.length > 1 && arguments[1] ? arguments[1] : state.root || "workspace";
      patch(function (current) {
        const expanded = Object.assign({}, current.expanded || {});
        expanded[pathKey(root, path)] = !expanded[pathKey(root, path)];
        return { expanded: expanded };
      });
    }

    function renderExplorer() {
      const openFile = state.openFile;
      function renderTreeNode(item, depth) {
        const root = itemRoot(item);
        const selectedKey = pathKey(state.root, state.path);
        const isSelected = (openFile && itemKey(openFile) === itemKey(item)) || (!openFile && selectedKey === itemKey(item));
        const children = item.children || [];
        const isFolder = item.kind === "folder";
        const isExpanded = !!state.expanded[itemKey(item)];
        const displayName = item.path === "/" ? (item.name || item.root_label || "Root") : item.name;
        return h(
          "div",
          { key: itemKey(item), className: "hermes-code-tree-node-wrap" },
          h(
            "div",
            {
              className: "hermes-code-item hermes-code-tree-node " + (isSelected ? "selected" : ""),
              draggable: item.path !== "/",
              onContextMenu: function (event) {
                openContextMenu(event, item);
              },
              onDragStart: function (event) {
                event.dataTransfer.setData("text/hermes-code-path", item.path);
                event.dataTransfer.setData("text/hermes-code-root", root);
              },
              onDragOver: function (event) {
                if (item.kind === "folder") event.preventDefault();
              },
              onDrop: function (event) {
                const sourcePath = event.dataTransfer.getData("text/hermes-code-path");
                const sourceRoot = event.dataTransfer.getData("text/hermes-code-root") || root;
                if (!sourcePath || item.kind !== "folder" || sourcePath === item.path || sourceRoot !== root) return;
                event.preventDefault();
                fileOperation(
                  "/ops/move",
                  { path: sourcePath, root: root, destination: joinPath(item.path, basename(sourcePath)) },
                  "Move " + sourcePath + " into " + item.path + "?"
                );
              },
            },
            h(
              "button",
              {
                type: "button",
                className: "hermes-code-item-open",
                style: { paddingLeft: 0.42 + depth * 0.8 + "rem" },
                onClick: function () {
                  openItem(item);
                },
                onDoubleClick: function () {
                  if (item.kind !== "folder") openItem(item, true);
                },
              },
              isFolder
                ? h(
                    "span",
                    {
                      className: "hermes-code-caret",
                      onClick: function (event) {
                        event.stopPropagation();
                        toggleExplorerNode(item.path, root);
                      },
                    },
                    isExpanded ? "v" : ">"
                  )
                : h("span", { className: "hermes-code-caret spacer" }),
              renderFileIcon(item),
              h("span", { className: "hermes-code-item-name" }, displayName),
              h("span", { className: "hermes-code-item-lang" }, item.kind === "folder" ? (children.length ? children.length : "") : item.language)
            )
          ),
          isFolder && isExpanded && children.length ? h("div", { className: "hermes-code-tree-children" }, children.map(function (child) { return renderTreeNode(child, depth + 1); })) : null
        );
      }
      return h(
        React.Fragment,
        null,
        h(
          "div",
          { className: "hermes-code-treebar" },
          h("button", { type: "button", onClick: function () { loadItems(parentPath(state.path), state.root); }, disabled: state.path === "/" }, "Up"),
          h("button", { type: "button", onClick: function () { loadItems(state.path, state.root); } }, "Refresh")
        ),
        h("div", { className: "hermes-code-path" }, (state.root === "vault" ? "Vault" : "Workspace") + " " + state.path),
        h(
          "div",
          { className: "hermes-code-items", onClick: function () { if (state.contextMenu) patch({ contextMenu: null }); } },
          state.loading
            ? h("div", { className: "hermes-code-empty" }, "Loading")
            : (state.status && state.status.roots || []).filter(function (root) { return root.available; }).length
              ? (state.status.roots || []).filter(function (root) { return root.available; }).map(function (root) {
                  const tree = (state.trees || {})[root.id] || { root: root.id, kind: "folder", path: "/", name: root.label, children: [] };
                  return renderTreeNode(Object.assign({}, tree, { root: root.id, name: root.label }), 0);
                })
              : h("div", { className: "hermes-code-empty" }, "No files")
        ),
        renderContextMenu()
      );
    }

    function renderSearchBox() {
      return h(
        "form",
        {
          className: "hermes-code-search",
          onSubmit: function (event) {
            event.preventDefault();
            runSearch(state.searchQuery);
          },
        },
        h("input", {
          value: state.searchQuery,
          placeholder: "Search Workspace and Vault",
          onChange: function (event) {
            scheduleSearch(event.target.value);
          },
        })
      );
    }

    function renderSearch() {
      return h(
        "div",
        { className: "hermes-code-search-results" },
        state.searchBusy
          ? h("div", { className: "hermes-code-empty" }, "Searching")
          : state.searchResults.length
            ? state.searchResults.map(function (item) {
                return h(
                  "button",
                  {
                    key: itemKey(item),
                    type: "button",
                    className: "hermes-code-search-result",
                    onClick: function () {
                      openItem(item);
                    },
                  },
                  renderFileIcon(Object.assign({ kind: "file" }, item)),
                  h("span", null, (item.root_label || itemRoot(item)) + " " + item.path),
                  h("small", null, item.match || "")
                );
              })
            : h("div", { className: "hermes-code-empty" }, "No search results")
      );
    }

    function sourceIconButton(label, icon, onClick, disabled, className) {
      return h(
        "button",
        {
          type: "button",
          className: "hermes-code-icon-button" + (className ? " " + className : ""),
          title: label,
          "aria-label": label,
          onClick: onClick,
          disabled: !!disabled,
        },
        icon
      );
    }

    function buildChangeTree(changes) {
      const root = { name: "", path: "", folders: {}, files: [] };
      changes.slice().sort(changeSort).forEach(function (change) {
        const parts = String(change.path || "").split("/").filter(Boolean);
        let node = root;
        for (let index = 0; index < Math.max(0, parts.length - 1); index += 1) {
          const part = parts[index];
          const childPath = node.path ? node.path + "/" + part : part;
          node.folders[part] = node.folders[part] || { name: part, path: childPath, folders: {}, files: [] };
          node = node.folders[part];
        }
        node.files.push(change);
      });
      return root;
    }

    function renderChangeActions(change, mode) {
      return h(
        "span",
        { className: "hermes-code-change-actions" },
        mode === "staged"
          ? h("span", { title: "Unstage", onClick: function (event) { event.stopPropagation(); gitAction("/git/unstage", { path: change.path }); } }, "-")
          : h("span", { title: "Stage", onClick: function (event) { event.stopPropagation(); gitAction("/git/stage", { path: change.path }); } }, "+"),
        mode === "staged"
          ? null
          : h(
              React.Fragment,
              null,
              change.untracked
                ? h("span", { title: "Ignore", onClick: function (event) { event.stopPropagation(); gitAction("/git/ignore", { path: change.path }); } }, "I")
                : null,
              h("span", {
                title: "Discard",
                onClick: function (event) {
                  event.stopPropagation();
                  gitAction(
                    "/git/discard",
                    { path: change.path, untracked: change.untracked, confirm: true },
                    "Discard changes in " + change.path + "?"
                  );
                },
              }, "U")
            )
      );
    }

    function renderChangeTreeNode(node, mode, depth) {
      const folderNames = Object.keys(node.folders || {}).sort(function (a, b) { return a.localeCompare(b); });
      return h(
        "div",
        { className: "hermes-code-change-tree-node", key: mode + ":folder:" + node.path },
        node.name
          ? h(
              "div",
              { className: "hermes-code-change-folder", style: { paddingLeft: 0.35 + depth * 0.85 + "rem" } },
              renderFileIcon({ kind: "folder", name: node.name }),
              h("span", null, node.name)
            )
          : null,
        folderNames.map(function (name) {
          return renderChangeTreeNode(node.folders[name], mode, depth + (node.name ? 1 : 0));
        }),
        (node.files || []).map(function (change) {
          return h(
            "button",
            {
              key: mode + ":file:" + change.path + ":" + change.status,
              type: "button",
              className: "hermes-code-change",
              style: { paddingLeft: 0.45 + (depth + (node.name ? 1 : 0)) * 0.85 + "rem" },
              onClick: function () {
                openChange(change);
              },
            },
            h("span", { className: "hermes-code-change-status" }, change.status.trim() || change.status),
            h(
              "span",
              { className: "hermes-code-change-name" },
              h("span", null, basename(change.path)),
              change.old_path ? h("small", null, "from " + change.old_path) : null
            ),
            renderChangeActions(change, mode)
          );
        })
      );
    }

    function renderChangeGroup(title, changes, mode) {
      const sorted = changes.slice().sort(changeSort);
      return h(
        "section",
        { className: "hermes-code-source-group" },
        h("div", { className: "hermes-code-source-group-title" }, h("span", null, title), h("strong", null, sorted.length)),
        sorted.length
          ? h("div", { className: "hermes-code-change-tree" }, renderChangeTreeNode(buildChangeTree(sorted), mode, 0))
          : h("div", { className: "hermes-code-source-empty" }, "No files")
      );
    }

    function renderSourceControl() {
      const source = state.source || { staged: [], unstaged: [], untracked: [], clean: true };
      const hasStaged = source.staged && source.staged.length;
      const hasChanges = (source.staged || []).length + (source.unstaged || []).length + (source.untracked || []).length;
      const repoLabel = state.repo ? (state.repo.root_label || "Workspace") + " " + state.repo.path : "";
      const branchLabel = source.branch || (state.repo && state.repo.branch) || "";
      return h(
        "div",
        { className: "hermes-code-source-panel" },
        h(
          "div",
          { className: "hermes-code-repo-row" },
          h(
            "div",
            { className: "hermes-code-repo-top-actions" },
            h("button", { type: "button", onClick: openSourcePicker }, "Open Source"),
            sourceIconButton("Refresh sources", "↻", function () { loadRepos(false); }, state.sourceBusy),
            sourceIconButton("Close source", "×", closeRepo, !state.repo)
          ),
          h(
            "select",
            {
              value: state.repo ? repoKey(state.repo) : "",
              onChange: function (event) {
                const repo = state.repos.filter(function (candidate) {
                  return repoKey(candidate) === event.target.value;
                })[0];
                if (repo) openRepo(repo);
              },
            },
            h("option", { value: "" }, state.repos.length ? "Select source" : "No open sources"),
            state.repos.map(function (repo) {
              return h("option", { key: repoKey(repo), value: repoKey(repo) }, (repo.root_label || "Workspace") + " " + repo.path + "  " + repo.branch);
            })
          )
        ),
        state.repo
          ? h(
              React.Fragment,
              null,
              h(
                "div",
                { className: "hermes-code-source-actions" },
                sourceIconButton("Refresh status", "↻", function () { loadSource(state.repo); }, state.sourceBusy),
                sourceIconButton("Stage all", "+", function () { gitAction("/git/stage", { all: true }); }, state.sourceBusy || !hasChanges),
                sourceIconButton("Unstage all", "-", function () { gitAction("/git/unstage", { all: true }); }, state.sourceBusy || !hasStaged),
                sourceIconButton("Pull", "↓", function () {
                    gitAction("/git/pull", { confirm: true }, "Pull with fast-forward only?");
                  }, state.sourceBusy),
                sourceIconButton("Push", "↑", function () {
                    gitAction("/git/push", { confirm: true }, "Push committed changes to the configured remote?");
                  }, state.sourceBusy),
                sourceIconButton("Discard all", "!", function () {
                    gitAction("/git/discard", { all: true, confirm: true }, "Discard all unstaged and untracked changes?");
                  }, state.sourceBusy || !hasChanges, "danger")
              ),
              h(
                "div",
                { className: "hermes-code-commit" },
                h("input", {
                  value: state.gitMessage,
                  placeholder: "Commit message",
                  onChange: function (event) {
                    patch({ gitMessage: event.target.value });
                  },
                }),
                h("button", { type: "button", onClick: commitStaged, disabled: !hasStaged || !state.gitMessage.trim() || state.sourceBusy }, "Commit")
              ),
              state.lastGitResult
                ? h("div", { className: "hermes-code-last-git-result" }, state.lastGitResult.command + ": " + state.lastGitResult.summary)
                : null,
              state.sourceBusy ? h("div", { className: "hermes-code-source-empty" }, "Refreshing") : null,
              source.clean
                ? h("div", { className: "hermes-code-source-empty" }, "No pending changes")
                : h(
                    React.Fragment,
                    null,
                    renderChangeGroup("Staged", source.staged || [], "staged"),
                    renderChangeGroup("Changes", source.unstaged || [], "unstaged"),
                    renderChangeGroup("Untracked", source.untracked || [], "untracked")
                  ),
              h("div", { className: "hermes-code-source-head" }, h("strong", null, repoLabel), h("span", null, branchLabel))
            )
          : h(
              "div",
              { className: "hermes-code-empty" },
              state.repos.length ? "Open a source to view changes" : "No open sources"
            )
      );
    }

    function renderSourcePicker() {
      if (!state.sourcePickerOpen) return null;
      const roots = (status.roots || []).filter(function (root) { return root.available; });
      function renderPickerNode(item, depth, label) {
        const root = itemRoot(item);
        const children = (item.children || []).filter(function (child) {
          return child.kind === "folder";
        });
        const isExpanded = !!state.expanded[itemKey(item)];
        const isSelected = state.sourcePickerPath === item.path && state.sourcePickerRoot === root;
        return h(
          "div",
          { key: "picker:" + itemKey(item), className: "hermes-code-picker-node-wrap" },
          h(
            "button",
            {
              type: "button",
              className: "hermes-code-picker-node " + (isSelected ? "selected" : ""),
              style: { paddingLeft: 0.4 + depth * 0.8 + "rem" },
              onClick: function () {
                patch({ sourcePickerRoot: root, sourcePickerPath: item.path, sourcePickerMessage: "" });
              },
              onDoubleClick: function () {
                openRepositoryFromPicker(item.path, root);
              },
            },
            item.kind === "folder"
              ? h(
                  "span",
                  {
                    className: "hermes-code-caret",
                    onClick: function (event) {
                      event.stopPropagation();
                      toggleExplorerNode(item.path, root);
                    },
                  },
                  isExpanded ? "v" : ">"
                )
              : h("span", { className: "hermes-code-caret spacer" }),
            renderFileIcon(Object.assign({}, item, { kind: "folder" })),
            h("span", { className: "hermes-code-item-name" }, label || item.name || item.path)
          ),
          isExpanded && children.length
            ? h("div", { className: "hermes-code-picker-children" }, children.map(function (child) {
                return renderPickerNode(child, depth + 1);
              }))
            : null
        );
      }
      return h(
        "div",
        { className: "hermes-code-modal-backdrop", role: "presentation" },
        h(
          "section",
          { className: "hermes-code-modal", role: "dialog", "aria-modal": "true", "aria-label": "Open source repository" },
          h("h2", null, "Open Source"),
          h("p", null, "Choose a Workspace or Vault folder that contains a .git directory."),
          h(
            "div",
            { className: "hermes-code-picker" },
            roots.map(function (root) {
              const tree = (state.trees || {})[root.id] || { root: root.id, kind: "folder", path: "/", name: root.label, children: [] };
              return renderPickerNode(Object.assign({}, tree, { root: root.id, name: root.label }), 0, root.label);
            })
          ),
          h("div", { className: "hermes-code-picker-path" }, (state.sourcePickerRoot === "vault" ? "Vault" : "Workspace") + " " + (state.sourcePickerPath || "/")),
          state.sourcePickerMessage ? h("div", { className: "hermes-code-picker-message" }, state.sourcePickerMessage) : null,
          h(
            "div",
            { className: "hermes-code-modal-actions" },
            h("button", { type: "button", onClick: function () { patch({ sourcePickerOpen: false, sourcePickerMessage: "" }); } }, "Cancel"),
            h("button", { type: "button", onClick: function () { openRepositoryFromPicker(state.sourcePickerPath, state.sourcePickerRoot); }, disabled: state.sourceBusy }, "Open")
          )
        )
      );
    }

    useEffect(function () {
      loadStatus();
    }, []);

    useEffect(function () {
      function beforeUnload(event) {
        if (!state.dirty) return;
        event.preventDefault();
        event.returnValue = "";
      }
      window.addEventListener("beforeunload", beforeUnload);
      return function () {
        window.removeEventListener("beforeunload", beforeUnload);
      };
    }, [state.dirty]);

    const status = state.status || {};
    const openFile = state.openFile;

    return h(
      "section",
      { className: "hermes-code hermes-code-theme-" + state.theme },
      h(
        "header",
        { className: "hermes-code-toolbar" },
        h(
          "div",
          { className: "hermes-code-title" },
          h("h1", null, "Code"),
          h("p", null, status.workspace_root || "Workspace")
        ),
        h(
          "div",
          { className: "hermes-code-actions" },
          h("button", {
            type: "button",
            onClick: function () {
              patch({ theme: state.theme === "dark" ? "light" : "dark" });
            },
          }, state.theme === "dark" ? "Light" : "Dark"),
          h("button", { type: "button", onClick: createFile, disabled: !status.available }, "New File"),
          h("button", { type: "button", onClick: createFolder, disabled: !status.available }, "New Folder"),
          h("button", { type: "button", onClick: saveFile, disabled: !openFile || !state.dirty || state.busy }, "Save")
        )
      ),
      state.errorMessage ? h("div", { className: "hermes-code-error" }, state.errorMessage) : null,
      status.available
        ? h(
            "div",
            { className: "hermes-code-main" },
            h(
              "aside",
              { className: "hermes-code-tree" },
              renderSearchBox(),
              h(
                "div",
                { className: "hermes-code-panel-tabs" },
                h("button", { type: "button", className: state.leftPanel === "explorer" ? "active" : "", onClick: function () { patch({ leftPanel: "explorer" }); } }, "Explorer"),
                h("button", { type: "button", className: state.leftPanel === "source" ? "active" : "", onClick: function () { patch({ leftPanel: "source" }); } }, "Sources")
              ),
              state.searchQuery.trim() ? renderSearch() : state.leftPanel === "source" ? renderSourceControl() : renderExplorer()
            ),
            h(
              "section",
              { className: "hermes-code-editor" },
              state.diff
                ? renderDiff(state.diff)
                : openFile
                ? h(
                    React.Fragment,
                    null,
	                    h(
	                      "div",
	                      { className: "hermes-code-tab" },
	                      h(
	                        "div",
	                        {
	                          className: "hermes-code-tab-list",
	                          onDragOver: function (event) {
	                            if (event.dataTransfer && event.dataTransfer.types && Array.prototype.slice.call(event.dataTransfer.types).indexOf("text/hermes-code-path") !== -1) {
	                              event.preventDefault();
	                            }
	                          },
	                          onDrop: openDroppedTab,
	                        },
	                        null,
	                        state.fileTabs.map(function (tab) {
	                          return h(
	                            "span",
	                            {
	                              key: itemKey(tab),
	                              className: "hermes-code-tab-item " + (itemKey(openFile) === itemKey(tab) ? "active" : "") + (tab.pinned ? " pinned" : " preview"),
	                            },
	                            h(
	                              "button",
	                              {
	                                type: "button",
	                                className: "hermes-code-tab-button",
	                                title: tab.pinned ? "Pinned tab" : "Preview tab. Double-click to pin.",
	                                onClick: function () {
	                                  openItem({ root: itemRoot(tab), path: tab.path, name: tab.name, kind: "file", text: true });
	                                },
	                                onDoubleClick: function () {
	                                  patch({ openFile: Object.assign({}, tab, { editable: tab.editable !== false }) });
	                                  pinTab(tab.path, itemRoot(tab));
	                                },
	                              },
	                              (tab.dirty || (itemKey(tab) === itemKey(openFile) && state.dirty) ? "* " : "") + tab.name
	                            ),
	                            h(
	                              "button",
	                              {
	                                type: "button",
	                                className: "hermes-code-tab-close",
	                                "aria-label": "Close " + tab.name,
	                                onClick: function (event) {
	                                  closeTab(tab, event);
	                                },
	                              },
	                              "x"
	                            )
	                          );
	                        })
	                      ),
	                      h("strong", { className: state.dirty ? "dirty" : "" }, state.dirty ? "Unsaved" : "Saved")
	                    ),
	                    h(
	                      "div",
	                      { className: "hermes-code-save-note" },
	                      h("span", null, "Auto-save is off. Save writes only when you click Save or press Cmd/Ctrl+S."),
	                      canPreviewFile(openFile) && openFile.editable !== false
	                        ? h("button", { type: "button", onClick: togglePreviewMode }, openFile.previewMode ? "Edit" : "Preview")
	                        : null,
	                      canPreviewFile(openFile)
	                        ? h("button", { type: "button", onClick: function () { patch({ previewFullscreen: true }); } }, "Maximize")
	                        : null
	                    ),
	                    openFile.editable === false || openFile.previewMode
                      ? renderCodePreview(openFile)
                      : h("textarea", {
                          className: "hermes-code-textarea",
                          spellCheck: "false",
                          value: state.content,
                          onChange: function (event) {
                            const value = event.target.value;
                            patch({ content: value, dirty: value !== state.savedContent });
                            updateTabBuffer(openFile.path, value, value !== state.savedContent);
                          },
                          onKeyDown: function (event) {
                            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
                              event.preventDefault();
                              saveFile();
                            }
                          },
                        })
                  )
                : h("div", { className: "hermes-code-empty full" }, "Open a file"),
              h(
                "div",
                { className: "hermes-code-statusbar" },
                h("span", null, openFile ? openFile.language || "plaintext" : "No file"),
                h("span", null, state.repo ? (state.repo.root_label || "Workspace") + " " + state.repo.path : "No repository"),
                h("span", null, state.dirty ? "Dirty" : "Manual save")
              )
            )
          )
        : h("div", { className: "hermes-code-empty full" }, "Code is not available"),
      renderSourcePicker(),
      renderFullscreenPreview()
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN, CodePage);
})();
