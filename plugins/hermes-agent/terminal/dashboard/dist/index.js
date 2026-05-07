(function () {
  "use strict";

  const PLUGIN = "terminal";
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

  function postJSON(path, payload) {
    return fetchJSON(api(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  }

  function groupSessions(sessions) {
    const groups = {};
    sessions.forEach(function (session) {
      const folder = session.folder || "Sessions";
      groups[folder] = groups[folder] || [];
      groups[folder].push(session);
    });
    return Object.keys(groups)
      .sort()
      .map(function (folder) {
        return { folder: folder, sessions: groups[folder] };
      });
  }

  function displayScrollback(text) {
    const stripped = String(text || "")
      .replace(new RegExp("\\x1b\\][^\\x07]*(\\x07|\\x1b\\\\)", "g"), "")
      .replace(new RegExp("\\x1b\\[[0-?]*[ -/]*[@-~]", "g"), "");
    const lines = [""];
    let row = 0;
    let col = 0;
    for (let index = 0; index < stripped.length; index += 1) {
      const char = stripped[index];
      if (char === "\r") {
        col = 0;
        continue;
      }
      if (char === "\n") {
        row += 1;
        lines[row] = lines[row] || "";
        col = 0;
        continue;
      }
      if (char === "\b" || char === "\x7f") {
        if (col > 0) {
          const line = lines[row] || "";
          lines[row] = line.slice(0, col - 1) + line.slice(col);
          col -= 1;
        }
        continue;
      }
      if (char < " " && char !== "\t") continue;
      const line = lines[row] || "";
      if (col >= line.length) {
        lines[row] = line + " ".repeat(col - line.length) + char;
      } else {
        lines[row] = line.slice(0, col) + char + line.slice(col + 1);
      }
      col += char === "\t" ? 4 : 1;
    }
    return lines.join("\n");
  }

  function TerminalPage() {
    const statePair = useState({
      loading: true,
      status: null,
      sessions: [],
      selectedId: "",
      selected: null,
      input: "",
      errorMessage: "",
      confirmClose: null,
      streaming: false,
      showClosed: false,
      contextMenu: null,
      editingSessionId: "",
      editingSessionName: "",
    });
    const state = statePair[0];
    const setState = statePair[1];
    const screenRef = useRef(null);

    function merge(next) {
      setState(function (current) {
        return Object.assign({}, current, next);
      });
    }

    function loadSessions(selectId) {
      return fetchJSON(api("/sessions"))
        .then(function (payload) {
          const sessions = payload.sessions || [];
          const nextId = selectId || state.selectedId || (sessions[0] && sessions[0].id) || "";
          merge({ sessions: sessions, selectedId: nextId, errorMessage: "" });
          if (nextId) {
            return loadSession(nextId);
          }
          merge({ selected: null });
          return null;
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function loadSession(sessionId) {
      if (!sessionId) return Promise.resolve(null);
      return fetchJSON(api("/sessions/" + encodeURIComponent(sessionId)))
        .then(function (payload) {
          merge({ selected: payload.session || null, selectedId: sessionId, errorMessage: "" });
          return payload.session || null;
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
          return null;
        });
    }

    useEffect(function () {
      SDK.fetchJSON(api("/status"))
        .then(function (status) {
          merge({ loading: false, status: status });
          return loadSessions("");
        })
        .catch(function () {
          merge({ loading: false, status: { available: false, capabilities: {} } });
        });
    }, []);

    useEffect(
      function () {
        let timer = null;
        let stream = null;
        let closed = false;

        function startPolling() {
          if (timer) return;
          timer = setInterval(function () {
            if (state.selectedId) {
              loadSession(state.selectedId);
              loadSessions(state.selectedId);
            }
          }, 1000);
        }

        if (
          state.selectedId &&
          state.status &&
          state.status.capabilities &&
          state.status.capabilities.streaming_output &&
          window.EventSource
        ) {
          stream = new EventSource(api("/sessions/" + encodeURIComponent(state.selectedId) + "/stream"), { withCredentials: true });
          stream.addEventListener("open", function () {
            if (!closed) merge({ streaming: true });
          });
          stream.addEventListener("session", function (event) {
            if (closed) return;
            try {
              const payload = JSON.parse(event.data || "{}");
              merge({ selected: payload.session || null, selectedId: state.selectedId, streaming: true, errorMessage: "" });
              loadSessions(state.selectedId);
            } catch (_error) {
              startPolling();
            }
          });
          stream.addEventListener("error", function () {
            if (stream) stream.close();
            if (!closed) merge({ streaming: false });
            startPolling();
          });
          startPolling();
        } else {
          merge({ streaming: false });
          startPolling();
        }

        return function () {
          closed = true;
          if (stream) stream.close();
          if (timer) clearInterval(timer);
        };
      },
      [state.selectedId, state.status && state.status.capabilities && state.status.capabilities.streaming_output]
    );

    function createSession(mode) {
      const sessionMode = mode || "shell";
      postJSON("/sessions", {
        name: sessionMode === "ssh" ? "Machine Terminal" : sessionMode === "tui" ? "Hermes TUI" : "Terminal",
        cwd: "/",
        mode: sessionMode,
        target: "",
      })
        .then(function (payload) {
          const session = payload.session || {};
          return loadSessions(session.id || "");
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function startRenameSession(session) {
      const target = session || state.selected;
      if (!target) return;
      merge({
        contextMenu: null,
        selectedId: target.id,
        editingSessionId: target.id,
        editingSessionName: target.name || "Terminal",
      });
      loadSession(target.id);
    }

    function cancelRenameSession() {
      merge({ editingSessionId: "", editingSessionName: "" });
    }

    function commitRenameSession(sessionId) {
      const name = String(state.editingSessionName || "").trim();
      const selectedId = sessionId || state.editingSessionId;
      if (!selectedId) return;
      if (!name) {
        cancelRenameSession();
        return;
      }
      postJSON("/sessions/" + encodeURIComponent(selectedId) + "/rename", { name: name })
        .then(function () {
          merge({ editingSessionId: "", editingSessionName: "" });
          return loadSessions(selectedId);
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error), editingSessionId: "", editingSessionName: "" });
        });
    }

    function moveSelectedToFolder() {
      const selected = state.selected;
      if (!selected) return;
      const folder = window.prompt("Folder", selected.folder || "");
      if (folder === null) return;
      postJSON("/sessions/" + encodeURIComponent(selected.id) + "/rename", { folder: folder })
        .then(function () {
          return loadSessions(selected.id);
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function reorderSelected(delta) {
      const selected = state.selected;
      if (!selected) return;
      postJSON("/sessions/" + encodeURIComponent(selected.id) + "/rename", { order: Number(selected.order || 0) + delta })
        .then(function () {
          return loadSessions(selected.id);
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function sendInput(event) {
      event.preventDefault();
      const selected = state.selected;
      if (!selected || !state.input) return;
      const body = { input: state.input.slice(-1) === "\n" ? state.input : state.input + "\n" };
      merge({ input: "" });
      postJSON("/sessions/" + encodeURIComponent(selected.id) + "/input", body)
        .then(function (payload) {
          merge({ selected: payload.session || selected, errorMessage: "" });
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function writeInput(text) {
      const selected = state.selected;
      if (!selected || ["running", "starting"].indexOf(selected.state) === -1 || !text) return;
      postJSON("/sessions/" + encodeURIComponent(selected.id) + "/input", { input: text })
        .then(function (payload) {
          merge({ selected: payload.session || selected, errorMessage: "" });
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function keyInput(event) {
      if (event.altKey || event.metaKey) return "";
      if (event.ctrlKey) {
        const key = event.key.toLowerCase();
        if (key >= "a" && key <= "z") {
          return String.fromCharCode(key.charCodeAt(0) - 96);
        }
        if (key === " ") return "\x00";
        return "";
      }
      const special = {
        Enter: "\r",
        Backspace: "\x7f",
        Tab: "\t",
        Escape: "\x1b",
        ArrowUp: "\x1b[A",
        ArrowDown: "\x1b[B",
        ArrowRight: "\x1b[C",
        ArrowLeft: "\x1b[D",
        Home: "\x1b[H",
        End: "\x1b[F",
        Delete: "\x1b[3~",
        PageUp: "\x1b[5~",
        PageDown: "\x1b[6~",
      };
      if (special[event.key]) return special[event.key];
      return event.key && event.key.length === 1 ? event.key : "";
    }

    function handleTerminalKey(event) {
      if (event.defaultPrevented) return;
      const text = keyInput(event);
      if (!text) return;
      event.preventDefault();
      writeInput(text);
    }

    useEffect(
      function () {
        const node = screenRef.current;
        if (!node || !state.selected) return undefined;
        function onNativeKeyDown(event) {
          const text = keyInput(event);
          if (!text) return;
          event.preventDefault();
          writeInput(text);
        }
        node.addEventListener("keydown", onNativeKeyDown);
        return function () {
          node.removeEventListener("keydown", onNativeKeyDown);
        };
      },
      [state.selected && state.selected.id, state.selected && state.selected.state]
    );

    function copySelection() {
      const selection = window.getSelection && window.getSelection();
      const text = selection ? String(selection.toString() || "") : "";
      if (!text.trim() || !navigator.clipboard) return;
      navigator.clipboard.writeText(text).catch(function () {});
    }

    function focusScreen() {
      window.setTimeout(function () {
        if (screenRef.current) screenRef.current.focus();
      }, 0);
    }

    function clearClosedSessions() {
      postJSON("/sessions/clear-closed", {})
        .then(function () {
          merge({ contextMenu: null });
          return loadSessions(state.selectedId);
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error), contextMenu: null });
        });
    }

    function closeSelected() {
      const selected = state.confirmClose;
      if (!selected) return;
      postJSON("/sessions/" + encodeURIComponent(selected.id) + "/close", { confirm: true })
        .then(function () {
          merge({ confirmClose: null, selected: null, selectedId: "" });
          return loadSessions("");
        })
        .catch(function (error) {
          merge({ confirmClose: null, errorMessage: String(error.message || error) });
        });
    }

    function openSessionMenu(event, session) {
      event.preventDefault();
      event.stopPropagation();
      merge({ selected: Object.assign({}, state.selected || {}, session), selectedId: session.id, contextMenu: { session: session, x: event.clientX, y: event.clientY } });
      loadSession(session.id);
    }

    function renderSessionMenu() {
      if (!state.contextMenu || !state.contextMenu.session) return null;
      const session = state.contextMenu.session;
      function closeThen(action) {
        merge({ contextMenu: null });
        if (action) action();
      }
      return h(
        "div",
        {
          className: "hermes-terminal-context",
          role: "menu",
          style: { left: state.contextMenu.x + "px", top: state.contextMenu.y + "px" },
          onClick: function (event) {
            event.stopPropagation();
          },
        },
        h("button", { type: "button", role: "menuitem", onClick: function () { closeThen(function () { startRenameSession(session); }); } }, "Rename"),
        h("button", { type: "button", role: "menuitem", onClick: function () { closeThen(moveSelectedToFolder); } }, "Folder"),
        h("button", { type: "button", role: "menuitem", onClick: function () { closeThen(function () { reorderSelected(-1); }); } }, "Move Up"),
        h("button", { type: "button", role: "menuitem", onClick: function () { closeThen(function () { reorderSelected(1); }); } }, "Move Down"),
        h("button", { type: "button", role: "menuitem", onClick: function () { closeThen(clearClosedSessions); } }, "Clear Closed"),
        h("button", { type: "button", role: "menuitem", onClick: function () { closeThen(function () { merge({ confirmClose: session }); }); } }, "Close")
      );
    }

    useEffect(function () {
      const element = screenRef.current;
      if (element) element.scrollTop = element.scrollHeight;
    }, [state.selected && state.selected.scrollback, state.selectedId]);

    const status = state.status || {};
    const capabilities = status.capabilities || {};
    const selected = state.selected;
    const visibleSessions = (state.sessions || []).filter(function (session) {
      return state.showClosed || session.state !== "closed";
    });
    const grouped = groupSessions(visibleSessions);
    return h(
      "div",
      {
        className: "hermes-terminal",
        onClick: function () {
          if (state.contextMenu) merge({ contextMenu: null });
        },
      },
      h(
        "div",
        { className: "hermes-terminal-toolbar" },
        h("div", { className: "hermes-terminal-title" }, h("h1", null, "Terminal"), h("p", null, status.backend || "Loading"))
      ),
      state.errorMessage ? h("div", { className: "hermes-terminal-error" }, state.errorMessage) : null,
      state.loading
        ? h("div", { className: "hermes-terminal-empty full" }, "Loading")
        : h(
            "div",
            { className: "hermes-terminal-main" },
            h(
              "aside",
              { className: "hermes-terminal-list" },
              h(
                "div",
                { className: "hermes-terminal-section" },
                h("span", null, "Sessions"),
                h(
                  "div",
                  { className: "hermes-terminal-session-tools" },
                  h("button", { type: "button", title: "New machine terminal", onClick: function () { createSession("ssh"); }, disabled: !(capabilities.machine_terminal_sessions || capabilities.ssh_sessions) }, "+SSH"),
                  h("button", { type: "button", title: "Open Hermes TUI", onClick: function () { createSession("tui"); }, disabled: !capabilities.hermes_tui_sessions }, "+ TUI")
                )
              ),
              h(
                "div",
                { className: "hermes-terminal-list-actions" },
                h(
                  "button",
                  {
                    type: "button",
                    onClick: function () {
                      merge({ showClosed: !state.showClosed });
                    },
                  },
                  state.showClosed ? "Hide Closed" : "Show Closed"
                ),
                h("button", { type: "button", onClick: clearClosedSessions }, "Clear Closed")
              ),
              grouped.length
                ? grouped.map(function (group) {
                    return h(
                      "div",
                      { key: group.folder, className: "hermes-terminal-group" },
                      group.folder && group.folder !== "Sessions" ? h("div", { className: "hermes-terminal-group-label" }, group.folder) : null,
                      group.sessions.map(function (session) {
                        return h(
                          "button",
                          {
                            key: session.id,
                            type: "button",
                            className: "hermes-terminal-session" + (session.id === state.selectedId ? " selected" : ""),
                            onContextMenu: function (event) {
                              openSessionMenu(event, session);
                            },
                            onClick: function () {
                              merge({ selectedId: session.id });
                              loadSession(session.id);
                              focusScreen();
                            },
                          },
                          h("span", { className: "hermes-terminal-session-top" },
                            state.editingSessionId === session.id
                              ? h("input", {
                                  className: "hermes-terminal-session-rename",
                                  value: state.editingSessionName,
                                  autoFocus: true,
                                  onClick: function (event) {
                                    event.stopPropagation();
                                  },
                                  onChange: function (event) {
                                    merge({ editingSessionName: event.target.value });
                                  },
                                  onBlur: function () {
                                    commitRenameSession(session.id);
                                  },
                                  onKeyDown: function (event) {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      commitRenameSession(session.id);
                                    }
                                    if (event.key === "Escape") {
                                      event.preventDefault();
                                      cancelRenameSession();
                                    }
                                  },
                                })
                              : h("strong", null, session.name || "Terminal"),
                            h("span", {
                              className: "hermes-terminal-session-close",
                              onClick: function (event) {
                                event.stopPropagation();
                                merge({ confirmClose: session });
                              },
                            }, "x")
                          ),
                          h("span", null, (session.state || "closed") + " · " + (session.cwd || "/"))
                        );
                      })
                    );
                  })
                : h("div", { className: "hermes-terminal-empty" }, status.available ? "No sessions" : "Terminal unavailable")
            ),
            h(
              "section",
              { className: "hermes-terminal-pane" },
              selected
                ? h(
                    "pre",
                    {
                      ref: screenRef,
                      className: "hermes-terminal-screen",
                      "data-session-state": selected.state || "",
                      tabIndex: 0,
                      onKeyDown: handleTerminalKey,
                      onMouseUp: copySelection,
                      onClick: function (event) {
                        event.currentTarget.focus();
                      },
                    },
                    displayScrollback(selected.scrollback || "$ "),
                    ["running", "starting"].indexOf(selected.state) !== -1 ? h("span", { className: "hermes-terminal-cursor" }, " ") : null
                  )
                : h("pre", { ref: screenRef, className: "hermes-terminal-screen muted", tabIndex: 0 }, status.available ? "$ " : "Terminal backend unavailable"),
              h(
                "div",
                { className: "hermes-terminal-facts" },
                h("span", null, "Workspace: " + (status.workspace_root || "")),
                h("span", null, "Shell: " + (status.shell || "sh")),
                h("span", null, "Transport: " + (state.streaming ? "sse" : ((status.transport && status.transport.mode) || "polling"))),
                h("span", null, "Scrollback: " + ((status.limits && status.limits.scrollback_bytes) || "")),
                h("span", null, "Confirm close: " + (capabilities.confirm_close_or_kill ? "on" : "off"))
              )
            )
          ),
      renderSessionMenu(),
      state.confirmClose
        ? h(
            "div",
            { className: "hermes-terminal-confirm-backdrop", role: "presentation" },
            h(
              "div",
              { className: "hermes-terminal-confirm", role: "dialog", "aria-modal": "true", "aria-label": "Close terminal session" },
              h("h2", null, "Close Session"),
              h("p", null, state.confirmClose.name || "Terminal"),
              h(
                "div",
                { className: "hermes-terminal-confirm-actions" },
                h("button", { type: "button", onClick: function () { merge({ confirmClose: null }); } }, "Cancel"),
                h("button", { type: "button", className: "danger", onClick: closeSelected }, "Close")
              )
            )
          )
        : null
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN, TerminalPage);
})();
