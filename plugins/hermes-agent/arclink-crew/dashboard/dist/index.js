(function () {
  "use strict";

  var PLUGIN = "arclink-crew";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__ || typeof window.__HERMES_PLUGINS__.registerSlot !== "function") {
    return;
  }
  var React = SDK.React;
  var useEffect = SDK.hooks.useEffect;
  var useRef = SDK.hooks.useRef || React.useRef;
  var useState = SDK.hooks.useState;

  function h(type, props) {
    var children = Array.prototype.slice.call(arguments, 2);
    return React.createElement.apply(React, [type, props].concat(children));
  }

  function api(path) {
    return "/api/plugins/" + PLUGIN + path;
  }

  function statusHint(status) {
    if (status === "active") return "";
    if (!status) return "";
    return " (" + status.replace(/_/g, " ") + ")";
  }

  function CrewSwitcher() {
    var state = useState({ crew: [], loaded: false });
    var crewState = state[0];
    var setCrewState = state[1];
    var openState = useState(false);
    var open = openState[0];
    var setOpen = openState[1];
    var rootRef = useRef(null);

    useEffect(function () {
      var cancelled = false;
      fetch(api("/crew"), { credentials: "same-origin" })
        .then(function (res) { return res.ok ? res.json() : { crew: [] }; })
        .then(function (payload) {
          if (!cancelled) {
            setCrewState({ crew: (payload && payload.crew) || [], loaded: true });
          }
        })
        .catch(function () {
          if (!cancelled) setCrewState({ crew: [], loaded: true });
        });
      return function () { cancelled = true; };
    }, []);

    useEffect(function () {
      if (!open) return undefined;
      function onDocClick(event) {
        if (rootRef.current && !rootRef.current.contains(event.target)) {
          setOpen(false);
        }
      }
      function onKey(event) {
        if (event.key === "Escape") setOpen(false);
      }
      document.addEventListener("mousedown", onDocClick);
      document.addEventListener("keydown", onKey);
      return function () {
        document.removeEventListener("mousedown", onDocClick);
        document.removeEventListener("keydown", onKey);
      };
    }, [open]);

    var crew = crewState.crew || [];
    // A lone Agent has nowhere to switch to; stay out of the header.
    if (!crewState.loaded || crew.length < 2) {
      return null;
    }
    var current = null;
    for (var i = 0; i < crew.length; i++) {
      if (crew[i].current) { current = crew[i]; break; }
    }
    var currentLabel = (current && current.label) || "Crew";

    return h(
      "div",
      { ref: rootRef, style: { position: "relative", display: "inline-flex", marginRight: "0.5rem" } },
      h(
        "button",
        {
          type: "button",
          "aria-haspopup": "listbox",
          "aria-expanded": open ? "true" : "false",
          "aria-label": "Switch Agent dashboard",
          title: "Switch Agent dashboard",
          onClick: function () { setOpen(!open); },
          style: {
            display: "inline-flex",
            alignItems: "center",
            gap: "0.35rem",
            padding: "0.3rem 0.6rem",
            borderRadius: "0.5rem",
            border: "1px solid var(--border, rgba(127,127,127,0.35))",
            background: "transparent",
            color: "inherit",
            cursor: "pointer",
            fontSize: "0.85rem",
            maxWidth: "14rem",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap"
          }
        },
        h("span", { "aria-hidden": "true" }, "Crew"),
        h("span", { style: { overflow: "hidden", textOverflow: "ellipsis" } }, currentLabel),
        h("span", { "aria-hidden": "true", style: { fontSize: "0.7rem" } }, open ? "^" : "v")
      ),
      open
        ? h(
            "div",
            {
              role: "listbox",
              "aria-label": "Your Agents",
              style: {
                position: "absolute",
                top: "calc(100% + 0.35rem)",
                right: 0,
                minWidth: "16rem",
                maxHeight: "60vh",
                overflowY: "auto",
                zIndex: 1000,
                borderRadius: "0.6rem",
                border: "1px solid var(--border, rgba(127,127,127,0.35))",
                background: "var(--background, #111418)",
                boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
                padding: "0.3rem"
              }
            },
            crew.map(function (item) {
              var isCurrent = !!item.current;
              return h(
                "a",
                {
                  key: item.url,
                  role: "option",
                  "aria-selected": isCurrent ? "true" : "false",
                  "aria-current": isCurrent ? "page" : undefined,
                  href: isCurrent ? "#" : item.url,
                  onClick: isCurrent
                    ? function (event) { event.preventDefault(); setOpen(false); }
                    : undefined,
                  style: {
                    display: "block",
                    padding: "0.45rem 0.6rem",
                    borderRadius: "0.45rem",
                    textDecoration: "none",
                    color: "inherit",
                    background: isCurrent ? "rgba(127,127,127,0.18)" : "transparent",
                    cursor: isCurrent ? "default" : "pointer"
                  }
                },
                h("div", { style: { fontWeight: 600, fontSize: "0.85rem" } },
                  item.label + (isCurrent ? " - at helm" : statusHint(item.status))),
                item.title
                  ? h("div", { style: { fontSize: "0.75rem", opacity: 0.75 } }, item.title)
                  : null
              );
            })
          )
        : null
    );
  }

  window.__HERMES_PLUGINS__.registerSlot(PLUGIN, "header-right", CrewSwitcher);
})();
