(function () {
  "use strict";

  const PLUGIN = "arclink-terminal";
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
    });
    const state = statePair[0];
    const setState = statePair[1];

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

    function createSession() {
      postJSON("/sessions", { name: "Terminal", cwd: "/" })
        .then(function (payload) {
          const session = payload.session || {};
          return loadSessions(session.id || "");
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
        });
    }

    function renameSelected() {
      const selected = state.selected;
      if (!selected) return;
      const name = window.prompt("Session name", selected.name || "Terminal");
      if (name === null) return;
      postJSON("/sessions/" + encodeURIComponent(selected.id) + "/rename", { name: name })
        .then(function () {
          return loadSessions(selected.id);
        })
        .catch(function (error) {
          merge({ errorMessage: String(error.message || error) });
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

    const status = state.status || {};
    const capabilities = status.capabilities || {};
    const selected = state.selected;
    const grouped = groupSessions(state.sessions || []);
    return h(
      "div",
      { className: "arclink-terminal" },
      h(
        "div",
        { className: "arclink-terminal-toolbar" },
        h("div", { className: "arclink-terminal-title" }, h("h1", null, "ArcLink Terminal"), h("p", null, status.backend || "Loading")),
        h(
          "div",
          { className: "arclink-terminal-actions" },
          h("button", { type: "button", onClick: createSession, disabled: !status.available }, "New Session"),
          h("button", { type: "button", onClick: renameSelected, disabled: !selected }, "Rename"),
          h("button", { type: "button", onClick: moveSelectedToFolder, disabled: !selected }, "Folder"),
          h("button", { type: "button", onClick: function () { reorderSelected(-1); }, disabled: !selected }, "Up"),
          h("button", { type: "button", onClick: function () { reorderSelected(1); }, disabled: !selected }, "Down"),
          h("button", { type: "button", className: "danger", onClick: function () { merge({ confirmClose: selected }); }, disabled: !selected }, "Close")
        )
      ),
      state.errorMessage ? h("div", { className: "arclink-terminal-error" }, state.errorMessage) : null,
      state.loading
        ? h("div", { className: "arclink-terminal-empty full" }, "Loading")
        : h(
            "div",
            { className: "arclink-terminal-main" },
            h(
              "aside",
              { className: "arclink-terminal-list" },
              h("div", { className: "arclink-terminal-section" }, "Sessions"),
              grouped.length
                ? grouped.map(function (group) {
                    return h(
                      "div",
                      { key: group.folder, className: "arclink-terminal-group" },
                      h("div", { className: "arclink-terminal-group-label" }, group.folder),
                      group.sessions.map(function (session) {
                        return h(
                          "button",
                          {
                            key: session.id,
                            type: "button",
                            className: "arclink-terminal-session" + (session.id === state.selectedId ? " selected" : ""),
                            onClick: function () {
                              merge({ selectedId: session.id });
                              loadSession(session.id);
                            },
                          },
                          h("strong", null, session.name || "Terminal"),
                          h("span", null, (session.state || "closed") + " · " + (session.cwd || "/"))
                        );
                      })
                    );
                  })
                : h("div", { className: "arclink-terminal-empty" }, status.available ? "No sessions" : "Terminal unavailable")
            ),
            h(
              "section",
              { className: "arclink-terminal-pane" },
              selected
                ? h(
                    "div",
                    { className: "arclink-terminal-screen", "data-session-state": selected.state || "" },
                    selected.scrollback || "$ "
                  )
                : h("div", { className: "arclink-terminal-screen muted" }, status.available ? "$ " : "Terminal backend unavailable"),
              h(
                "form",
                { className: "arclink-terminal-input", onSubmit: sendInput },
                h("input", {
                  value: state.input,
                  disabled: !selected || ["running", "starting"].indexOf(selected.state) === -1,
                  onChange: function (event) {
                    merge({ input: event.target.value });
                  },
                }),
                h("button", { type: "submit", disabled: !selected || !state.input }, "Send")
              ),
              h(
                "div",
                { className: "arclink-terminal-facts" },
                h("span", null, "Workspace: " + (status.workspace_root || "")),
                h("span", null, "Shell: " + (status.shell || "sh")),
                h("span", null, "Transport: " + (state.streaming ? "sse" : ((status.transport && status.transport.mode) || "polling"))),
                h("span", null, "Scrollback: " + ((status.limits && status.limits.scrollback_bytes) || "")),
                h("span", null, "Confirm close: " + (capabilities.confirm_close_or_kill ? "on" : "off"))
              )
            )
          ),
      state.confirmClose
        ? h(
            "div",
            { className: "arclink-terminal-confirm-backdrop", role: "presentation" },
            h(
              "div",
              { className: "arclink-terminal-confirm", role: "dialog", "aria-modal": "true", "aria-label": "Close terminal session" },
              h("h2", null, "Close Session"),
              h("p", null, state.confirmClose.name || "Terminal"),
              h(
                "div",
                { className: "arclink-terminal-confirm-actions" },
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
