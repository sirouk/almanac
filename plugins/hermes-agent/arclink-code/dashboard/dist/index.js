(function () {
  "use strict";

  const PLUGIN = "arclink-code";
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
          "arclink-code-fileicon " +
          (item.kind === "folder" ? "folder" : "file") +
          " " +
          fileKindClass(item) +
          (label.length > 3 ? " long-ext" : ""),
        style: item.kind === "folder" ? null : { "--file-accent": extensionColor(item) },
        title: item.kind === "folder" ? "Folder" : label ? label + " file" : "File",
      },
      item.kind === "folder" ? null : h("span", { className: "arclink-code-fileext" }, label)
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
    return api("/download?path=" + encodeURIComponent(item.path || ""));
  }

  function changeSort(a, b) {
    return String(a.path).localeCompare(String(b.path));
  }

  function CodePage() {
    const statePair = useState({
      loading: true,
      status: null,
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
      tree: null,
      expanded: { "/": true },
      contextMenu: null,
      searchQuery: "",
      searchResults: [],
      searchBusy: false,
      lastGitResult: null,
      theme: "dark",
      sourcePickerOpen: false,
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

    function loadItems(nextPath) {
      const targetPath = nextPath || state.path;
      patch({ loading: true, path: targetPath, errorMessage: "" });
      fetchJSON(api("/items?path=" + encodeURIComponent(targetPath)))
        .then(function (data) {
          patch({ loading: false, path: data.path || targetPath, items: data.items || [] });
          loadTree();
        })
        .catch(function (error) {
          patch({ loading: false, items: [], errorMessage: error.message || "Unable to load files" });
        });
    }

    function loadTree() {
      fetchJSON(api("/tree?path=" + encodeURIComponent("/") + "&depth=3"))
        .then(function (data) {
          patch(function (current) {
            const expanded = Object.assign({ "/": true }, current.expanded || {});
            return { tree: data.tree || null, expanded: expanded };
          });
        })
        .catch(function () {
          patch({ tree: null });
        });
    }

    function loadSource(repoPath) {
      if (!repoPath) return;
      patch({ sourceBusy: true, errorMessage: "" });
      fetchJSON(api("/git/status?repo=" + encodeURIComponent(repoPath)))
        .then(function (data) {
          patch({ sourceBusy: false, source: data });
        })
        .catch(function (error) {
          patch({ sourceBusy: false, source: null, errorMessage: error.message || "Unable to load source control" });
        });
    }

    function openRepo(repo) {
      patch({ repo: repo, leftPanel: "source", gitMessage: "", source: null, sourcePickerOpen: false, sourcePickerMessage: "" });
      loadSource(repo.path);
    }

    function closeRepo() {
      patch({ repo: null, source: null, gitMessage: "" });
    }

    function loadRepos(selectFirst) {
      fetchJSON(api("/repos"))
        .then(function (data) {
          const repos = data.repos || [];
          const currentRepo = state.repo && repos.filter(function (repo) { return repo.path === state.repo.path; })[0];
          const nextRepo = currentRepo || (selectFirst && repos.length ? repos[0] : null);
          patch({ repos: repos, repo: nextRepo });
          if (nextRepo) loadSource(nextRepo.path);
        })
        .catch(function (error) {
          patch({ repos: [], repo: null, source: null, errorMessage: error.message || "Unable to scan repositories" });
        });
    }

    function openSourcePicker() {
      patch({ sourcePickerOpen: true, sourcePickerPath: state.repo ? state.repo.path : "/", sourcePickerMessage: "" });
      if (!state.tree) loadTree();
    }

    function openRepositoryFromPicker(path) {
      const targetPath = path || state.sourcePickerPath || "/";
      patch({ sourceBusy: true, sourcePickerMessage: "" });
      fetchJSON(api("/repos/open"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: targetPath }),
      })
        .then(function (data) {
          const repo = data.repo;
          patch(function (current) {
            const repos = (current.repos || []).filter(function (candidate) {
              return candidate.path !== repo.path;
            });
            repos.push(repo);
            repos.sort(function (a, b) {
              return String(a.path).localeCompare(String(b.path));
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
          patch({ status: status, loading: false });
          if (status.available) {
            loadItems("/");
            loadRepos(true);
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
          return tab.path === file.path;
        })[0] || {};
        let tabs = (current.fileTabs || []).filter(function (tab) {
          return tab.path !== file.path;
        });
        const isPinned = !!(pinned || existing.pinned || existing.dirty);
        if (!isPinned) {
          tabs = tabs.filter(function (tab) {
            return tab.pinned || tab.dirty;
          });
        }
        tabs.push({
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
            return tab.path === path ? Object.assign({}, tab, { dirty: dirty }) : tab;
          }),
        };
      });
    }

    function updateTabBuffer(path, content, dirty) {
      patch(function (current) {
        return {
          fileTabs: (current.fileTabs || []).map(function (tab) {
            return tab.path === path ? Object.assign({}, tab, { content: content, dirty: dirty }) : tab;
          }),
        };
      });
    }

    function pinTab(path) {
      patch(function (current) {
        return {
          fileTabs: (current.fileTabs || []).map(function (tab) {
            return tab.path === path ? Object.assign({}, tab, { pinned: true }) : tab;
          }),
        };
      });
    }

    function closeTab(tab, event) {
      if (event) event.stopPropagation();
      if (tab.dirty && !window.confirm("Close " + tab.name + " without saving?")) return;
      patch(function (current) {
        const tabs = (current.fileTabs || []).filter(function (candidate) {
          return candidate.path !== tab.path;
        });
        const active = current.openFile && current.openFile.path === tab.path;
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
      const path = event.dataTransfer && event.dataTransfer.getData("text/arclink-code-path");
      if (!path || path === "/") return;
      openItem({ path: path, name: basename(path), kind: "file", text: true }, true);
    }

    function openPreviewFile(item, pinned) {
      const kind = item.previewKind || previewKind(item);
      if (!kind) {
        patch({ errorMessage: "No preview available for " + (item.name || item.path || "this file") });
        return;
      }
      const previewFile = Object.assign({}, item, {
        kind: "file",
        name: item.name || basename(item.path),
        editable: false,
        previewKind: kind,
        previewUrl: item.previewUrl || downloadUrl(item),
        previewContent: item.previewContent,
      });
      patch(function (current) {
        let tabs = (current.fileTabs || []).filter(function (tab) {
          return tab.path !== previewFile.path;
        });
        const existing = (current.fileTabs || []).filter(function (tab) {
          return tab.path === previewFile.path;
        })[0] || {};
        const isPinned = !!(pinned || existing.pinned);
        if (!isPinned) {
          tabs = tabs.filter(function (tab) {
            return tab.pinned || tab.dirty;
          });
        }
        tabs.push({
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
        fetch(downloadUrl(item), { credentials: "same-origin" })
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
        loadItems(item.path);
        patch(function (current) {
          const expanded = Object.assign({}, current.expanded || {});
          expanded[item.path] = true;
          return { expanded: expanded };
        });
        return;
      }
      const previewable = previewKind(item);
      if (["pdf", "image", "audio", "video"].indexOf(previewable) !== -1) {
        openPreviewFile(Object.assign({}, item, { previewKind: previewable }), pinned);
        return;
      }
      const existingTab = (state.fileTabs || []).filter(function (tab) {
        return tab.path === item.path;
      })[0];
      if (existingTab) {
        if (pinned) pinTab(existingTab.path);
        patch({
          openFile: Object.assign({}, existingTab, { editable: existingTab.editable !== false }),
          content: existingTab.content || "",
          savedContent: existingTab.savedContent || "",
          dirty: !!existingTab.dirty,
          diff: null,
        });
        return;
      }
      fetchJSON(api("/file?path=" + encodeURIComponent(item.path)))
        .then(function (data) {
          const content = data.content || "";
          const file = Object.assign({ kind: "file" }, data);
          const kind = previewKind(file);
          patch(function (current) {
            let tabs = (current.fileTabs || []).filter(function (tab) {
              return tab.path !== data.path;
            });
            if (!pinned) {
              tabs = tabs.filter(function (tab) {
                return tab.pinned || tab.dirty;
              });
            }
            tabs.push({
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
              previewUrl: downloadUrl(data),
              previewMode: false,
            });
            return {
              fileTabs: tabs.slice(-8),
              openFile: Object.assign({}, data, { kind: "file", editable: true, previewKind: kind, previewUrl: downloadUrl(data), previewMode: false }),
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
        body: JSON.stringify({ path: state.openFile.path, content: state.content, expected_hash: state.openFile.hash || "" }),
      })
        .then(function (data) {
          patch(function (current) {
            return {
              busy: false,
              savedContent: current.content,
              dirty: false,
              openFile: Object.assign({}, current.openFile, { hash: data.hash, modified: data.modified }),
              fileTabs: (current.fileTabs || []).map(function (tab) {
                return current.openFile && tab.path === current.openFile.path
                  ? Object.assign({}, tab, { dirty: false, content: current.content, savedContent: current.content, hash: data.hash })
                  : tab;
              }),
            };
          });
          loadItems(state.path);
          if (state.repo) loadSource(state.repo.path);
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
      patch(function (current) {
        const tabs = (current.fileTabs || []).filter(function (tab) {
          return tab.path !== path;
        });
        tabs.push({ path: path, name: name, dirty: true, pinned: true, content: "", savedContent: "", hash: "", language: "plaintext", editable: true });
        return {
          fileTabs: tabs.slice(-8),
          openFile: { path: path, name: name, language: "plaintext", editable: true },
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
          if (endpoint === "/ops/trash" && state.openFile && payload.path === state.openFile.path) {
            patch(function (current) {
              return {
                openFile: null,
                content: "",
                savedContent: "",
                dirty: false,
                diff: null,
                fileTabs: (current.fileTabs || []).filter(function (tab) { return tab.path !== payload.path; }),
              };
            });
          }
          loadItems(state.path);
          loadTree();
          if (state.repo) loadSource(state.repo.path);
          if (state.searchQuery) runSearch(state.searchQuery);
        })
        .catch(function (error) {
          patch({ busy: false, errorMessage: error.message || "File operation failed" });
        });
    }

    function renameItem(item) {
      const name = (window.prompt("Rename", item.name) || "").trim();
      if (!name || name === item.name) return;
      fileOperation("/ops/rename", { path: item.path, name: name });
    }

    function moveItem(item) {
      const destination = (window.prompt("Move to path", joinPath(parentPath(item.path), item.name)) || "").trim();
      if (!destination || destination === item.path) return;
      fileOperation("/ops/move", { path: item.path, destination: destination }, "Move " + item.path + " to " + destination + "?");
    }

    function duplicateItem(item) {
      fileOperation("/ops/duplicate", { path: item.path });
    }

    function trashItem(item) {
      fileOperation("/ops/trash", { path: item.path, confirm: true }, "Move " + item.path + " to trash?");
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
          className: "arclink-code-context-menu",
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

    function findTreeNode(path, node) {
      if (!node) return null;
      if (node.path === path) return node;
      const children = node.children || [];
      for (let index = 0; index < children.length; index += 1) {
        const found = findTreeNode(path, children[index]);
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
        body: JSON.stringify({ path: joinPath(state.path, name) }),
      })
        .then(function () {
          patch({ busy: false });
          loadItems(state.path);
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
        body: JSON.stringify(Object.assign({ repo: state.repo.path }, payload || {})),
      })
        .then(function (data) {
          patch({ sourceBusy: false, source: data.status || state.source, lastGitResult: data.last_git_result || null });
          loadItems(state.path);
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
            return current.openFile && tab.path === current.openFile.path ? Object.assign({}, tab, { previewMode: nextMode }) : tab;
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
        nodes.push(line.trim() ? h("p", { key: "p:" + index }, line) : h("div", { key: "sp:" + index, className: "arclink-code-markdown-space" }));
      });
      flushCode("tail");
      return h("div", { className: "arclink-code-markdown-preview" }, nodes);
    }

    function renderPreviewBody(file) {
      const kind = file.previewKind || previewKind(file);
      const url = file.previewUrl || downloadUrl(file);
      const content = file.previewContent !== undefined ? file.previewContent : state.content;
      if (file.previewMessage) return h("div", { className: "arclink-code-preview-empty" }, file.previewMessage);
      if (kind === "markdown") return renderMarkdownPreview(content);
      if (kind === "text") return h("pre", { className: "arclink-code-text-preview" }, content || "");
      if (kind === "pdf") {
        return h(
          "object",
          { className: "arclink-code-pdf-preview", data: url, type: "application/pdf" },
          h("a", { href: url, target: "_blank", rel: "noreferrer" }, "Open PDF")
        );
      }
      if (kind === "image") return h("img", { className: "arclink-code-media-preview", src: url, alt: file.name || "Preview" });
      if (kind === "audio") return h("audio", { className: "arclink-code-audio-preview", src: url, controls: true });
      if (kind === "video") return h("video", { className: "arclink-code-media-preview", src: url, controls: true });
      return h("div", { className: "arclink-code-preview-empty" }, "Preview unavailable");
    }

    function renderCodePreview(file) {
      const kind = file.previewKind || previewKind(file);
      return h(
        "div",
        { className: "arclink-code-preview" },
        h(
          "div",
          { className: "arclink-code-preview-head" },
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
        { className: "arclink-code-preview-fullscreen", role: "dialog", "aria-modal": "true", "aria-label": "File preview" },
        h(
          "div",
          { className: "arclink-code-preview-fullbar" },
          h("strong", null, state.openFile.name || basename(state.openFile.path)),
          h("button", { type: "button", onClick: function () { patch({ previewFullscreen: false }); } }, "Close")
        ),
        renderPreviewBody(state.openFile)
      );
    }

    function renderDiff(diff) {
      return h(
        "div",
        { className: "arclink-code-diff" },
        h(
          "div",
          { className: "arclink-code-diff-head" },
          h("strong", null, diff.path),
          h("span", null, diff.mode)
        ),
        h(
          "div",
          { className: "arclink-code-diff-panes" },
          h("pre", null, diff.before || ""),
          h("pre", null, diff.after || "")
        ),
        h("pre", { className: "arclink-code-diff-unified" }, diff.diff || "No text diff available")
      );
    }

    function toggleExplorerNode(path) {
      patch(function (current) {
        const expanded = Object.assign({}, current.expanded || {});
        expanded[path] = !expanded[path];
        return { expanded: expanded };
      });
    }

    function renderExplorer() {
      const openFile = state.openFile;
      function renderTreeNode(item, depth) {
        const isSelected = openFile && openFile.path === item.path;
        const children = item.children || [];
        const isFolder = item.kind === "folder";
        const isExpanded = !!state.expanded[item.path];
        const displayName = item.path === "/" ? "Workspace" : item.name;
        return h(
          "div",
          { key: item.path, className: "arclink-code-tree-node-wrap" },
          h(
            "div",
            {
              className: "arclink-code-item arclink-code-tree-node " + (isSelected ? "selected" : ""),
              draggable: item.path !== "/",
              onContextMenu: function (event) {
                openContextMenu(event, item);
              },
              onDragStart: function (event) {
                event.dataTransfer.setData("text/arclink-code-path", item.path);
              },
              onDragOver: function (event) {
                if (item.kind === "folder") event.preventDefault();
              },
              onDrop: function (event) {
                const sourcePath = event.dataTransfer.getData("text/arclink-code-path");
                if (!sourcePath || item.kind !== "folder" || sourcePath === item.path) return;
                event.preventDefault();
                fileOperation(
                  "/ops/move",
                  { path: sourcePath, destination: joinPath(item.path, basename(sourcePath)) },
                  "Move " + sourcePath + " into " + item.path + "?"
                );
              },
            },
            h(
              "button",
              {
                type: "button",
                className: "arclink-code-item-open",
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
                      className: "arclink-code-caret",
                      onClick: function (event) {
                        event.stopPropagation();
                        toggleExplorerNode(item.path);
                      },
                    },
                    isExpanded ? "v" : ">"
                  )
                : h("span", { className: "arclink-code-caret spacer" }),
              renderFileIcon(item),
              h("span", { className: "arclink-code-item-name" }, displayName),
              h("span", { className: "arclink-code-item-lang" }, item.kind === "folder" ? (children.length ? children.length : "") : item.language)
            )
          ),
          isFolder && isExpanded && children.length ? h("div", { className: "arclink-code-tree-children" }, children.map(function (child) { return renderTreeNode(child, depth + 1); })) : null
        );
      }
      return h(
        React.Fragment,
        null,
        h(
          "div",
          { className: "arclink-code-treebar" },
          h("button", { type: "button", onClick: function () { loadItems(parentPath(state.path)); }, disabled: state.path === "/" }, "Up"),
          h("button", { type: "button", onClick: function () { loadItems(state.path); } }, "Refresh")
        ),
        h("div", { className: "arclink-code-path" }, state.path),
        h(
          "div",
          { className: "arclink-code-items", onClick: function () { if (state.contextMenu) patch({ contextMenu: null }); } },
          state.loading
            ? h("div", { className: "arclink-code-empty" }, "Loading")
            : state.tree
              ? renderTreeNode(state.tree, 0)
              : h("div", { className: "arclink-code-empty" }, "No files")
        ),
        renderContextMenu()
      );
    }

    function renderSearchBox() {
      return h(
        "form",
        {
          className: "arclink-code-search",
          onSubmit: function (event) {
            event.preventDefault();
            runSearch(state.searchQuery);
          },
        },
        h("input", {
          value: state.searchQuery,
          placeholder: "Search workspace",
          onChange: function (event) {
            scheduleSearch(event.target.value);
          },
        })
      );
    }

    function renderSearch() {
      return h(
        "div",
        { className: "arclink-code-search-results" },
        state.searchBusy
          ? h("div", { className: "arclink-code-empty" }, "Searching")
          : state.searchResults.length
            ? state.searchResults.map(function (item) {
                return h(
                  "button",
                  {
                    key: item.path,
                    type: "button",
                    className: "arclink-code-search-result",
                    onClick: function () {
                      openItem(item);
                    },
                  },
                  renderFileIcon(Object.assign({ kind: "file" }, item)),
                  h("span", null, item.path),
                  h("small", null, item.match || "")
                );
              })
            : h("div", { className: "arclink-code-empty" }, "No search results")
      );
    }

    function renderChangeGroup(title, changes, mode) {
      const sorted = changes.slice().sort(changeSort);
      return h(
        "section",
        { className: "arclink-code-source-group" },
        h("div", { className: "arclink-code-source-group-title" }, h("span", null, title), h("strong", null, sorted.length)),
        sorted.length
          ? sorted.map(function (change) {
              const dir = dirname(change.path);
              return h(
                "button",
                {
                  key: title + ":" + change.path + ":" + change.status,
                  type: "button",
                  className: "arclink-code-change",
                  onClick: function () {
                    openChange(change);
                  },
                },
                h("span", { className: "arclink-code-change-status" }, change.status.trim() || change.status),
                h(
                  "span",
                  { className: "arclink-code-change-name" },
                  dir ? h("small", null, dir + "/") : null,
                  h("span", null, basename(change.path)),
                  change.old_path ? h("small", null, " from " + change.old_path) : null
                ),
                h(
                  "span",
                  { className: "arclink-code-change-actions" },
                  mode === "staged"
                    ? h("span", { onClick: function (event) { event.stopPropagation(); gitAction("/git/unstage", { path: change.path }); } }, "-")
                    : h("span", { onClick: function (event) { event.stopPropagation(); gitAction("/git/stage", { path: change.path }); } }, "+"),
                  mode === "staged"
                    ? null
                    : h(
                        React.Fragment,
                        null,
                        change.untracked
                          ? h("span", { onClick: function (event) { event.stopPropagation(); gitAction("/git/ignore", { path: change.path }); } }, "Ignore")
                          : null,
                        h("span", {
                          onClick: function (event) {
                            event.stopPropagation();
                            gitAction(
                              "/git/discard",
                              { path: change.path, untracked: change.untracked, confirm: true },
                              "Discard changes in " + change.path + "?"
                            );
                          },
                        }, "Undo")
                      )
                )
              );
            })
          : h("div", { className: "arclink-code-source-empty" }, "No files")
      );
    }

    function renderSourceControl() {
      const source = state.source || { staged: [], unstaged: [], untracked: [], clean: true };
      const hasStaged = source.staged && source.staged.length;
      const hasChanges = (source.staged || []).length + (source.unstaged || []).length + (source.untracked || []).length;
      return h(
        React.Fragment,
        null,
        h(
          "div",
          { className: "arclink-code-repo-row" },
          h(
            "select",
            {
              value: state.repo ? state.repo.path : "",
              onChange: function (event) {
                const repo = state.repos.filter(function (candidate) {
                  return candidate.path === event.target.value;
                })[0];
                if (repo) openRepo(repo);
              },
            },
            h("option", { value: "" }, state.repos.length ? "Select source" : "No open sources"),
            state.repos.map(function (repo) {
              return h("option", { key: repo.path, value: repo.path }, repo.path + "  " + repo.branch);
            })
          ),
          h("button", { type: "button", onClick: openSourcePicker }, "Open Source"),
          h("button", { type: "button", onClick: function () { loadRepos(false); } }, "Refresh"),
          h("button", { type: "button", onClick: closeRepo, disabled: !state.repo }, "Close")
        ),
        state.repo
          ? h(
              React.Fragment,
              null,
              h("div", { className: "arclink-code-source-head" }, h("strong", null, state.repo.path), h("span", null, source.branch || state.repo.branch || "")),
              h(
                "div",
                { className: "arclink-code-source-actions" },
                h("button", { type: "button", onClick: function () { loadSource(state.repo.path); }, disabled: state.sourceBusy }, "Refresh"),
                h("button", { type: "button", onClick: function () { gitAction("/git/stage", { all: true }); }, disabled: state.sourceBusy || !hasChanges }, "Stage All"),
                h("button", { type: "button", onClick: function () { gitAction("/git/unstage", { all: true }); }, disabled: state.sourceBusy || !hasStaged }, "Unstage All"),
                h("button", {
                  type: "button",
                  onClick: function () {
                    gitAction("/git/pull", { confirm: true }, "Pull with fast-forward only?");
                  },
                  disabled: state.sourceBusy,
                }, "Pull"),
                h("button", {
                  type: "button",
                  onClick: function () {
                    gitAction("/git/push", { confirm: true }, "Push committed changes to the configured remote?");
                  },
                  disabled: state.sourceBusy,
                }, "Push"),
                h("button", {
                  type: "button",
                  onClick: function () {
                    gitAction("/git/discard", { all: true, confirm: true }, "Discard all unstaged and untracked changes?");
                  },
                  disabled: state.sourceBusy || !hasChanges,
                }, "Discard All")
              ),
              h(
                "div",
                { className: "arclink-code-commit" },
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
                ? h("div", { className: "arclink-code-last-git-result" }, state.lastGitResult.command + ": " + state.lastGitResult.summary)
                : null,
              state.sourceBusy ? h("div", { className: "arclink-code-source-empty" }, "Refreshing") : null,
              source.clean
                ? h("div", { className: "arclink-code-source-empty" }, "No pending changes")
                : h(
                    React.Fragment,
                    null,
                    renderChangeGroup("Staged", source.staged || [], "staged"),
                    renderChangeGroup("Changes", source.unstaged || [], "unstaged"),
                    renderChangeGroup("Untracked", source.untracked || [], "untracked")
                  )
            )
          : h(
              "div",
              { className: "arclink-code-empty" },
              state.repos.length ? "Open a source to view changes" : "No open sources"
            )
      );
    }

    function renderSourcePicker() {
      if (!state.sourcePickerOpen) return null;
      const roots = [{ label: "Workspace", path: "/" }];
      if (status.vault_display_path && status.vault_display_path !== "/") {
        roots.push({ label: "Vault", path: status.vault_display_path });
      }
      function renderPickerNode(item, depth, label) {
        const children = (item.children || []).filter(function (child) {
          return child.kind === "folder";
        });
        const isExpanded = !!state.expanded[item.path];
        const isSelected = state.sourcePickerPath === item.path;
        return h(
          "div",
          { key: "picker:" + item.path, className: "arclink-code-picker-node-wrap" },
          h(
            "button",
            {
              type: "button",
              className: "arclink-code-picker-node " + (isSelected ? "selected" : ""),
              style: { paddingLeft: 0.4 + depth * 0.8 + "rem" },
              onClick: function () {
                patch({ sourcePickerPath: item.path, sourcePickerMessage: "" });
              },
              onDoubleClick: function () {
                openRepositoryFromPicker(item.path);
              },
            },
            item.kind === "folder"
              ? h(
                  "span",
                  {
                    className: "arclink-code-caret",
                    onClick: function (event) {
                      event.stopPropagation();
                      toggleExplorerNode(item.path);
                    },
                  },
                  isExpanded ? "v" : ">"
                )
              : h("span", { className: "arclink-code-caret spacer" }),
            renderFileIcon(Object.assign({}, item, { kind: "folder" })),
            h("span", { className: "arclink-code-item-name" }, label || item.name || item.path)
          ),
          isExpanded && children.length
            ? h("div", { className: "arclink-code-picker-children" }, children.map(function (child) {
                return renderPickerNode(child, depth + 1);
              }))
            : null
        );
      }
      return h(
        "div",
        { className: "arclink-code-modal-backdrop", role: "presentation" },
        h(
          "section",
          { className: "arclink-code-modal", role: "dialog", "aria-modal": "true", "aria-label": "Open source repository" },
          h("h2", null, "Open Source"),
          h("p", null, "Choose a Workspace or Vault folder that contains a .git directory."),
          h(
            "div",
            { className: "arclink-code-picker" },
            roots.map(function (root) {
              const node = findTreeNode(root.path, state.tree) || { kind: "folder", path: root.path, name: root.label, children: [] };
              return renderPickerNode(Object.assign({}, node, { name: root.label }), 0, root.label);
            })
          ),
          h("div", { className: "arclink-code-picker-path" }, state.sourcePickerPath || "/"),
          state.sourcePickerMessage ? h("div", { className: "arclink-code-picker-message" }, state.sourcePickerMessage) : null,
          h(
            "div",
            { className: "arclink-code-modal-actions" },
            h("button", { type: "button", onClick: function () { patch({ sourcePickerOpen: false, sourcePickerMessage: "" }); } }, "Cancel"),
            h("button", { type: "button", onClick: function () { openRepositoryFromPicker(state.sourcePickerPath); }, disabled: state.sourceBusy }, "Open")
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
      { className: "arclink-code arclink-code-theme-" + state.theme },
      h(
        "header",
        { className: "arclink-code-toolbar" },
        h(
          "div",
          { className: "arclink-code-title" },
          h("h1", null, "ArcLink Code"),
          h("p", null, status.workspace_root || "Workspace")
        ),
        h(
          "div",
          { className: "arclink-code-actions" },
          h("button", {
            type: "button",
            onClick: function () {
              patch({ theme: state.theme === "dark" ? "light" : "dark" });
            },
          }, state.theme === "dark" ? "Light" : "Dark"),
          h("button", { type: "button", onClick: createFile, disabled: !status.available }, "New File"),
          h("button", { type: "button", onClick: createFolder, disabled: !status.available }, "New Folder"),
          h("button", { type: "button", onClick: saveFile, disabled: !openFile || !state.dirty || state.busy }, "Save"),
          status.url ? h("a", { href: status.url, target: "_blank", rel: "noreferrer" }, "Full IDE") : null
        )
      ),
      state.errorMessage ? h("div", { className: "arclink-code-error" }, state.errorMessage) : null,
      status.available
        ? h(
            "div",
            { className: "arclink-code-main" },
            h(
              "aside",
              { className: "arclink-code-tree" },
              renderSearchBox(),
              h(
                "div",
                { className: "arclink-code-panel-tabs" },
                h("button", { type: "button", className: state.leftPanel === "explorer" ? "active" : "", onClick: function () { patch({ leftPanel: "explorer" }); } }, "Explorer"),
                h("button", { type: "button", className: state.leftPanel === "source" ? "active" : "", onClick: function () { patch({ leftPanel: "source" }); } }, "Sources")
              ),
              state.searchQuery.trim() ? renderSearch() : state.leftPanel === "source" ? renderSourceControl() : renderExplorer()
            ),
            h(
              "section",
              { className: "arclink-code-editor" },
              state.diff
                ? renderDiff(state.diff)
                : openFile
                ? h(
                    React.Fragment,
                    null,
	                    h(
	                      "div",
	                      { className: "arclink-code-tab" },
	                      h(
	                        "div",
	                        {
	                          className: "arclink-code-tab-list",
	                          onDragOver: function (event) {
	                            if (event.dataTransfer && event.dataTransfer.types && Array.prototype.slice.call(event.dataTransfer.types).indexOf("text/arclink-code-path") !== -1) {
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
	                              key: tab.path,
	                              className: "arclink-code-tab-item " + (openFile.path === tab.path ? "active" : "") + (tab.pinned ? " pinned" : " preview"),
	                            },
	                            h(
	                              "button",
	                              {
	                                type: "button",
	                                className: "arclink-code-tab-button",
	                                title: tab.pinned ? "Pinned tab" : "Preview tab. Double-click to pin.",
	                                onClick: function () {
	                                  openItem({ path: tab.path, name: tab.name, kind: "file", text: true });
	                                },
	                                onDoubleClick: function () {
	                                  pinTab(tab.path);
	                                },
	                              },
	                              (tab.dirty || (tab.path === openFile.path && state.dirty) ? "* " : "") + tab.name
	                            ),
	                            h(
	                              "button",
	                              {
	                                type: "button",
	                                className: "arclink-code-tab-close",
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
	                      { className: "arclink-code-save-note" },
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
                          className: "arclink-code-textarea",
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
                : h("div", { className: "arclink-code-empty full" }, "Open a file"),
              h(
                "div",
                { className: "arclink-code-statusbar" },
                h("span", null, openFile ? openFile.language || "plaintext" : "No file"),
                h("span", null, state.repo ? state.repo.path : "No repository"),
                h("span", null, state.dirty ? "Dirty" : "Manual save")
              )
            )
          )
        : h("div", { className: "arclink-code-empty full" }, "ArcLink Code is not available"),
      renderSourcePicker(),
      renderFullscreenPreview()
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN, CodePage);
})();
