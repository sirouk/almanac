(function () {
  "use strict";

  const PLUGIN = "terminal";
  const SDK = window.__HERMES_PLUGIN_SDK__;
  const React = SDK.React;
  const useEffect = SDK.hooks.useEffect;
  const useRef = SDK.hooks.useRef || React.useRef;
  const useState = SDK.hooks.useState;
  const VENDOR_BASE = "/dashboard-plugins/" + PLUGIN + "/dist/vendor/";

  let terminalVendorPromise = null;

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

  function loadStylesheetOnce(href) {
    if (document.querySelector('link[href="' + href + '"]')) return Promise.resolve();
    return new Promise(function (resolve, reject) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.onload = resolve;
      link.onerror = function () {
        reject(new Error("Could not load " + href));
      };
      document.head.appendChild(link);
    });
  }

  function loadScriptOnce(src, globalReady) {
    if (globalReady && globalReady()) return Promise.resolve();
    const existing = document.querySelector('script[src="' + src + '"]');
    if (existing) {
      return new Promise(function (resolve, reject) {
        if (globalReady && globalReady()) {
          resolve();
          return;
        }
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", function () { reject(new Error("Could not load " + src)); }, { once: true });
      });
    }
    return new Promise(function (resolve, reject) {
      const script = document.createElement("script");
      script.src = src;
      script.async = false;
      script.onload = resolve;
      script.onerror = function () {
        reject(new Error("Could not load " + src));
      };
      document.body.appendChild(script);
    });
  }

  function ensureTerminalVendor() {
    if (terminalVendorPromise) return terminalVendorPromise;
    terminalVendorPromise = loadStylesheetOnce(VENDOR_BASE + "xterm.css")
      .then(function () {
        return loadScriptOnce(VENDOR_BASE + "xterm.js", function () {
          return !!window.Terminal;
        });
      })
      .then(function () {
        return loadScriptOnce(VENDOR_BASE + "addon-fit.js", function () {
          return !!(window.FitAddon && window.FitAddon.FitAddon);
        });
      })
      .then(function () {
        if (!window.Terminal) throw new Error("xterm.js did not expose Terminal");
        return {
          Terminal: window.Terminal,
          FitAddon: window.FitAddon && window.FitAddon.FitAddon ? window.FitAddon.FitAddon : null,
        };
      });
    return terminalVendorPromise;
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

  function sessionIsWritable(session) {
    return !!session && ["running", "starting"].indexOf(session.state) !== -1;
  }

  function scrollbackLines(status) {
    const value = Number(status && status.limits && status.limits.scrollback_lines);
    return Number.isFinite(value) && value > 0 ? value : 10000;
  }

  function terminalTheme() {
    return {
      background: "#05090d",
      foreground: "#d1fae5",
      cursor: "#d1fae5",
      cursorAccent: "#05090d",
      selectionBackground: "#1d4ed8aa",
      black: "#0b1118",
      red: "#f87171",
      green: "#34d399",
      yellow: "#fbbf24",
      blue: "#60a5fa",
      magenta: "#c084fc",
      cyan: "#22d3ee",
      white: "#e5e7eb",
      brightBlack: "#64748b",
      brightRed: "#fca5a5",
      brightGreen: "#86efac",
      brightYellow: "#fde68a",
      brightBlue: "#93c5fd",
      brightMagenta: "#d8b4fe",
      brightCyan: "#67e8f9",
      brightWhite: "#f8fafc",
    };
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
      terminalReady: false,
    });
    const state = statePair[0];
    const setState = statePair[1];
    const hostRef = useRef(null);
    const vendorRef = useRef(null);
    const stateRef = useRef(state);
    const terminalRef = useRef({ term: null, fit: null, sessionId: "", written: "", disposables: [] });
    const resizeTimerRef = useRef(null);
    const resizeSignatureRef = useRef("");
    const selectionRef = useRef("");
    const freshSessionRef = useRef({});

    useEffect(function () {
      stateRef.current = state;
    });

    function merge(next) {
      setState(function (current) {
        return Object.assign({}, current, next);
      });
    }

    function loadSessions(selectId) {
      return fetchJSON(api("/sessions"))
        .then(function (payload) {
          const sessions = payload.sessions || [];
          const nextId = selectId || stateRef.current.selectedId || (sessions[0] && sessions[0].id) || "";
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

    function disposeTerminal() {
      const current = terminalRef.current || {};
      (current.disposables || []).forEach(function (item) {
        try {
          if (item && typeof item.dispose === "function") item.dispose();
        } catch (_error) {}
      });
      if (current.term && typeof current.term.dispose === "function") {
        try {
          current.term.dispose();
        } catch (_error) {}
      }
      terminalRef.current = { term: null, fit: null, sessionId: "", written: "", disposables: [] };
      resizeSignatureRef.current = "";
    }

    function writeInputTo(sessionId, text) {
      const current = stateRef.current;
      const selected = current.selected;
      if (!selected || selected.id !== sessionId || !sessionIsWritable(selected) || !text) return;
      postJSON("/sessions/" + encodeURIComponent(sessionId) + "/input", { input: text })
        .then(function (payload) {
          const latest = stateRef.current;
          if (latest.selectedId === sessionId) {
            merge({ selected: payload.session || selected, errorMessage: "" });
          }
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function resizeSession(sessionId, rows, cols) {
      const cleanRows = Math.max(8, Math.min(200, Number(rows) || 32));
      const cleanCols = Math.max(20, Math.min(400, Number(cols) || 132));
      const signature = sessionId + ":" + cleanRows + "x" + cleanCols;
      if (resizeSignatureRef.current === signature) return;
      resizeSignatureRef.current = signature;
      postJSON("/sessions/" + encodeURIComponent(sessionId) + "/resize", { rows: cleanRows, cols: cleanCols })
        .then(function (payload) {
          const latest = stateRef.current;
          if (latest.selectedId === sessionId) {
            merge({ selected: payload.session || latest.selected, errorMessage: "" });
          }
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function fitTerminal() {
      const current = terminalRef.current || {};
      if (!current.term || current.sessionId !== stateRef.current.selectedId) return;
      if (current.fit && typeof current.fit.fit === "function") {
        try {
          current.fit.fit();
        } catch (_error) {}
      }
      resizeSession(current.sessionId, current.term.rows, current.term.cols);
    }

    function writeTerminalOutput(current, text, acceptReports) {
      if (!text || !current || !current.term) return;
      const previousDisableStdin = !!current.term.options.disableStdin;
      current.acceptReports = !!acceptReports;
      if (!acceptReports) current.term.options.disableStdin = true;
      try {
        current.term.write(text, function () {
          if (terminalRef.current !== current) return;
          current.acceptReports = false;
          if (!acceptReports) current.term.options.disableStdin = previousDisableStdin;
        });
      } catch (_error) {
        current.acceptReports = false;
        if (!acceptReports) current.term.options.disableStdin = previousDisableStdin;
      }
    }

    function syncTerminalOutput(session) {
      const current = terminalRef.current || {};
      if (!current.term || !session || current.sessionId !== session.id) return;
      const raw = String(session.scrollback || "");
      const previous = String(current.written || "");
      if (!raw && previous) {
        current.term.reset();
        current.written = "";
        return;
      }
      if (raw.indexOf(previous) === 0) {
        const delta = raw.slice(previous.length);
        if (delta) writeTerminalOutput(current, delta, current.allowInitialReports || !!previous);
      } else {
        current.term.reset();
        if (raw) writeTerminalOutput(current, raw, !!current.allowInitialReports);
      }
      current.allowInitialReports = false;
      current.written = raw;
      try {
        current.term.scrollToBottom();
      } catch (_error) {}
    }

    function openTerminal(session) {
      const vendor = vendorRef.current;
      const host = hostRef.current;
      if (!vendor || !host || !session) return;
      const current = terminalRef.current || {};
      if (current.term && current.sessionId === session.id) {
        syncTerminalOutput(session);
        return;
      }
      disposeTerminal();
      host.innerHTML = "";
      const term = new vendor.Terminal({
        allowTransparency: true,
        convertEol: false,
        cursorBlink: true,
        cursorStyle: "block",
        drawBoldTextInBrightColors: true,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        fontSize: 13,
        lineHeight: 1.22,
        macOptionIsMeta: true,
        rightClickSelectsWord: true,
        scrollback: scrollbackLines(stateRef.current.status),
        theme: terminalTheme(),
        windowsMode: true,
      });
      const fit = vendor.FitAddon ? new vendor.FitAddon() : null;
      if (fit) term.loadAddon(fit);
      term.open(host);
      const disposables = [];
      if (term.parser && typeof term.parser.registerCsiHandler === "function") {
        disposables.push(
          term.parser.registerCsiHandler({ final: "n" }, function (params) {
            const first = Array.isArray(params && params[0]) ? params[0][0] : params && params[0];
            if (first !== 6) return false;
            const currentTerminal = terminalRef.current || {};
            if (currentTerminal.sessionId === session.id && currentTerminal.acceptReports) {
              const activeBuffer = term.buffer && term.buffer.active;
              const row = ((activeBuffer && activeBuffer.cursorY) || 0) + 1;
              const col = ((activeBuffer && activeBuffer.cursorX) || 0) + 1;
              writeInputTo(session.id, "\x1b[" + row + ";" + col + "R");
            }
            return true;
          })
        );
      }
      disposables.push(
        term.onData(function (data) {
          writeInputTo(session.id, data);
        }),
        term.onResize(function (size) {
          resizeSession(session.id, size.rows, size.cols);
        }),
        term.onSelectionChange(function () {
          const text = term.getSelection ? String(term.getSelection() || "") : "";
          if (!text || text === selectionRef.current || !navigator.clipboard) return;
          selectionRef.current = text;
          navigator.clipboard.writeText(text).catch(function () {});
        })
      );
      const allowInitialReports = !!freshSessionRef.current[session.id];
      delete freshSessionRef.current[session.id];
      terminalRef.current = { term: term, fit: fit, sessionId: session.id, written: "", disposables: disposables, acceptReports: false, allowInitialReports: allowInitialReports };
      fitTerminal();
      syncTerminalOutput(session);
      term.focus();
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

      let cancelled = false;
      ensureTerminalVendor()
        .then(function (vendor) {
          if (cancelled) return;
          vendorRef.current = vendor;
          merge({ terminalReady: true });
        })
        .catch(function (error) {
          if (!cancelled) merge({ errorMessage: String(error.message || error) });
        });
      return function () {
        cancelled = true;
        disposeTerminal();
      };
    }, []);

    useEffect(
      function () {
        let timer = null;
        let stream = null;
        let closed = false;

        function startPolling() {
          if (timer) return;
          timer = setInterval(function () {
            const selectedId = stateRef.current.selectedId;
            if (selectedId) {
              loadSession(selectedId);
              loadSessions(selectedId);
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
              merge({ selected: payload.session || null, selectedId: stateRef.current.selectedId, streaming: true, errorMessage: "" });
              loadSessions(stateRef.current.selectedId);
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

    useEffect(
      function () {
        if (!state.terminalReady) return undefined;
        if (!state.selected) {
          disposeTerminal();
          return undefined;
        }
        openTerminal(state.selected);
        return undefined;
      },
      [state.terminalReady, state.selected && state.selected.id]
    );

    useEffect(
      function () {
        if (!state.terminalReady || !state.selected) return undefined;
        syncTerminalOutput(state.selected);
        return undefined;
      },
      [state.terminalReady, state.selected && state.selected.id, state.selected && state.selected.scrollback]
    );

    useEffect(
      function () {
        const host = hostRef.current;
        if (!host || !state.terminalReady || !state.selected) return undefined;
        fitTerminal();
        if (!window.ResizeObserver) return undefined;
        const observer = new ResizeObserver(function () {
          if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current);
          resizeTimerRef.current = window.setTimeout(fitTerminal, 120);
        });
        observer.observe(host);
        return function () {
          observer.disconnect();
          if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current);
        };
      },
      [state.terminalReady, state.selected && state.selected.id]
    );

    function createSession(mode) {
      const sessionMode = mode || "shell";
      const current = terminalRef.current || {};
      postJSON("/sessions", {
        name: sessionMode === "ssh" ? "Machine Terminal" : sessionMode === "tui" ? "Hermes TUI" : "Terminal",
        cwd: "/",
        mode: sessionMode,
        target: "",
        rows: current.term ? current.term.rows : 32,
        cols: current.term ? current.term.cols : 132,
      })
        .then(function (payload) {
          const session = payload.session || {};
          if (session.id) freshSessionRef.current[session.id] = true;
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
                  h("button", { type: "button", title: "Open Hermes TUI", onClick: function () { createSession("tui"); }, disabled: !capabilities.hermes_tui_sessions }, "+TUI")
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
                              merge({ selectedId: session.id, contextMenu: null });
                              loadSession(session.id);
                            },
                          },
                          h(
                            "span",
                            { className: "hermes-terminal-session-name-row" },
                            state.editingSessionId === session.id
                              ? h("input", {
                                  className: "hermes-terminal-session-rename",
                                  value: state.editingSessionName,
                                  autoFocus: true,
                                  onClick: function (event) { event.stopPropagation(); },
                                  onChange: function (event) { merge({ editingSessionName: event.target.value }); },
                                  onKeyDown: function (event) {
                                    if (event.key === "Enter") commitRenameSession(session.id);
                                    if (event.key === "Escape") cancelRenameSession();
                                  },
                                  onBlur: function () { commitRenameSession(session.id); },
                                })
                              : h("strong", null, session.name || "Terminal"),
                            h(
                              "span",
                              {
                                className: "hermes-terminal-session-close",
                                title: "Close session",
                                onClick: function (event) {
                                  event.preventDefault();
                                  event.stopPropagation();
                                  merge({ confirmClose: session, contextMenu: null });
                                },
                              },
                              "x"
                            )
                          ),
                          h("span", { className: "hermes-terminal-session-meta" }, (session.state || "closed") + " · " + (session.cwd || "/"))
                        );
                      })
                    );
                  })
                : h("div", { className: "hermes-terminal-empty" }, "No sessions")
            ),
            h(
              "section",
              { className: "hermes-terminal-pane" },
              selected
                ? h("div", { ref: hostRef, className: "hermes-terminal-screen", "data-session-state": selected.state || "" })
                : h("div", { ref: hostRef, className: "hermes-terminal-screen muted" }, status.available ? "$ " : "Terminal backend unavailable"),
              h(
                "div",
                { className: "hermes-terminal-statusbar" },
                h("span", null, "Workspace: " + (status.workspace_root || "[workspace]")),
                h("span", null, "Shell: " + (selected && selected.shell ? selected.shell : status.shell || "")),
                h("span", null, "Transport: " + ((status.transport && status.transport.mode) || "sse")),
                h("span", null, "Scrollback: " + ((status.limits && status.limits.scrollback_lines) || "") + " lines"),
                h("span", null, "History cap: " + ((status.limits && status.limits.scrollback_bytes) || "") + " bytes"),
                h("span", null, "Confirm close: on")
              )
            )
          ),
      renderSessionMenu(),
      state.confirmClose
        ? h(
            "div",
            { className: "hermes-terminal-confirm", role: "dialog", "aria-modal": "true" },
            h("div", { className: "hermes-terminal-confirm-card" },
              h("h2", null, "Close terminal session?"),
              h("p", null, "The session will stop after confirmation."),
              h("div", { className: "hermes-terminal-confirm-actions" },
                h("button", { type: "button", onClick: function () { merge({ confirmClose: null }); } }, "Cancel"),
                h("button", { type: "button", onClick: closeSelected }, "Close")
              )
            )
          )
        : null
    );
  }

  window.__HERMES_PLUGINS__.register(PLUGIN, TerminalPage);
})();
