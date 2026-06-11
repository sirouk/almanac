# arclink-crew

A slot-only Hermes dashboard plugin: the **Crew switcher** dropdown in the
top-right header. It lets a Captain jump between their Agents' Hermes
dashboards without leaving the page they are on.

## How it works

- `dashboard/manifest.json` registers a hidden tab plus the `header-right`
  slot; the bundle calls
  `window.__HERMES_PLUGINS__.registerSlot("arclink-crew", "header-right", CrewSwitcher)`.
- `dashboard/plugin_api.py` serves one read-only route, `GET /crew`, which
  reads `crew_dashboards` from `$HERMES_HOME/state/arclink-web-access.json` -
  the rail the ArcLink sovereign worker already refreshes on apply, handoff
  recovery, and teardown. No new state plumbing and no secrets.
- The dropdown renders only when the Captain has two or more Agents; the
  Agent at the helm is marked and non-clickable, every other entry is a plain
  link to that Agent's dashboard. Dashboard credentials are shared across the
  Crew, so the hop lands signed-in wherever the SSO cookie domain applies
  (tailnet/localhost ingress may show the login page - known caveat).

## Install

Shipped by `bin/install-arclink-plugins.sh` into `$HERMES_HOME/plugins/`
(the *user* plugin source, which is one of the two sources whose backend
`api` routers Hermes mounts).
