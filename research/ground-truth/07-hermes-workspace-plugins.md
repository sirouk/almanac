# Ground Truth 07 — Hermes Workspace Plugins (Drive / Code / Terminal), Managed Context, Dashboard Auth Proxy

Scope: `plugins/hermes-agent/` (drive, code, terminal, arclink-managed-context, arclink-theme),
`python/arclink_dashboard_auth_proxy.py`, `python/arclink_nextcloud_access.py`.
Date of mapping: 2026-05-30. Source of truth is the code; doc verdicts at the end.

---

## A. What is actually implemented today

### A.0 Plugin layout / install
All ArcLink Hermes dashboard plugins live under `plugins/hermes-agent/<name>/` with:
`plugin.yaml`, `__init__.py`, and (for tabbed plugins) `dashboard/{manifest.json, plugin_api.py, dist/index.js, dist/style.css}`.
Every `plugin.yaml` declares `minimum_hermes_version: v2026.4.30`.
Default install set (per README + runbook §14): `drive`, `code`, `terminal`, `arclink-theme`, `arclink-managed-context`.
Installer is `bin/install-arclink-plugins.sh` (referenced; not in this subsystem's files). The top-level
`plugins/hermes-agent/README.md` still says plugins "default to `$HOME` for workspace access" — this is now
**only partly true** (see A.1 / E).

The Python plugin_api modules are written to import FastAPI but **fall back to no-op stub classes** when FastAPI
is absent (try/except at top of each `plugin_api.py`), so `py_compile` works without FastAPI installed.

### A.1 Drive (`plugins/hermes-agent/drive/`, status version `1.0.0`, tab path `/drive`, icon `Database`)
Implemented in `drive/dashboard/plugin_api.py` (2027 lines). FastAPI `APIRouter` with routes:
`GET /status`, `POST /share/request`, `GET /items`, `GET /content`, `GET /download`, `GET /preview`,
`POST /mkdir`, `POST /move`, `POST /rename`, `POST /favorite`, `POST /delete`, `GET /trash`,
`POST /restore`, `POST /upload`, `POST /new-file`, `POST /copy`, `POST /duplicate`, `POST /batch`.

Four sibling roots, each a `_root_descriptor`: **Vault**, **Workspace**, **Fleet**, **Linked** (ids `vault`,
`workspace`, `fleet`, `linked`). Root discovery (`_first_existing_dir` over candidate lists):
- Vault: `DRIVE_ROOT`, `KNOWLEDGE_VAULT_ROOT`, `AGENT_VAULT_DIR`, `VAULT_DIR`, `~/Vault`, `$HERMES_HOME/Vault`.
- Workspace: `DRIVE_WORKSPACE_ROOT`, `CODE_WORKSPACE_ROOT`, then `$HERMES_HOME/workspace` (NOT `$HOME` — README §"Roots" still says `$HOME`).
- Fleet: `DRIVE_FLEET_SHARED_ROOT`, `ARCLINK_FLEET_SHARED_ROOT`, `$HERMES_HOME/fleet-shared`.
- Linked: `DRIVE_LINKED_ROOT`, `ARCLINK_LINKED_RESOURCES_ROOT`, `$HERMES_HOME/linked`.
Default selected root is `vault` then `workspace` (`_default_root_id`).

Local backend is the real path (`backend == "local-vault"` / `"local-roots"`). Capabilities per root come from
`_root_capabilities`. Real local behavior: list/search (search walks roots, `_SEARCH_LIMIT=300`,
`followlinks` only for `linked`), text preview (`/content`, `_MAX_TEXT_BYTES=1_000_000`, `_is_text_item` by ext/mime),
binary preview/download (`/preview` inline, `/download` attachment), `mkdir`, `move`, `rename` (rename is a
constrained move), `favorite` (persisted in `state/drive-meta.json`), soft-delete to per-root `.drive-trash`
(`_TRASH_DIR_NAME`), `trash` listing, `restore`, multi-file/folder `upload` (with `keep-both`/`reject` conflict
policy and folder rewrites), `new-file` (text-ext only), `copy`, `duplicate` (keep-both), and `batch`
(trash/favorite/copy/move/restore).

Safety rails in code: `_clean_relative_path` rejects `..`; `_assert_accessible_path` confines to the root (plus
linked-source allowance); `_is_sensitive_path`/`_assert_not_sensitive` block `.ssh`, ssh keys
(`id_rsa`/`id_ed25519`/…), `arclink-bootstrap-token`, `.arclink-operator.env`, `arclink-priv` env files, the
linked manifest file `.arclink-linked-resources.json`, and anything under `HERMES_HOME/secrets` or
`HERMES_HOME/state`. `_SKIP_DIR_NAMES` hides `.git`, `.hg`, `.svn`, `__pycache__`, `node_modules`, `.drive-trash`.
Symlink escapes are blocked in copy (`_assert_no_symlink_escape`, `_copy_confined` skips symlinks/sensitive).

### A.2 Code (`plugins/hermes-agent/code/`, status version `1.0.0`, tab path `/code`, icon `Code`)
Implemented in `code/dashboard/plugin_api.py` (1722 lines). Routes:
`GET /status`, `POST /share/request`, `GET /repos`, `POST /repos/open`, `GET /git/status`, `GET /git/commits`,
`GET /git/diff`, `POST /git/stage`, `POST /git/unstage`, `POST /git/discard`, `POST /git/commit`,
`POST /git/ignore`, `POST /git/pull`, `POST /git/push`, `GET /items`, `GET /tree`, `GET /search`, `GET /file`,
`GET /download`, `GET /preview`, `POST /save`, `POST /mkdir`, `POST /ops/rename`, `POST /ops/move`,
`POST /ops/duplicate`, `POST /ops/trash`, `GET /trash`, `POST /ops/restore`.

Same four roots (`workspace`, `vault`, `fleet`, `linked`) via `_root_descriptors`. Code's Workspace root is
`CODE_WORKSPACE_ROOT`/`DRIVE_WORKSPACE_ROOT` else `$HERMES_HOME/workspace` (again NOT `$HOME`, contradicting
code/README §"Roots" which says "Workspace defaults to `$HOME`"). Vault candidates: `CODE_VAULT_ROOT`,
`DRIVE_ROOT`, `KNOWLEDGE_VAULT_ROOT`, `VAULT_DIR`, `~/Vault`, `$HERMES_HOME/Vault`.

Editor model: `editor: "native"`, `full_ide_available: False`, `monaco_global_available: False`,
`manual_save_only: True`. Saves are explicit and protected by a disk-hash conflict check: `/save` compares
`expected_hash`/`hash` against `_file_hash` and returns **409 "File changed on disk; reload before saving"** on
mismatch; writes are atomic (`_write_text_atomic`).

Git: real, repo-confined `git` via `_run_git` (`subprocess` with `git -C <repo>`, 30s timeout; 503 "git is not
installed", 504 "git command timed out"). Read ops allowed on all roots including Linked: `/git/status`
(porcelain v1 + branch + commit history), `/git/commits`, `/git/diff` (working/staged/untracked unified diffs).
**Mutating git ops** (`stage`, `unstage`, `discard`, `commit`, `ignore`, `pull`, `push`) go through
`_resolve_writable_repo`, which raises **403 "Git mutations are disabled for Linked resources"** when the root id
is `linked`. `pull` is `git pull --ff-only` and `push` is `git push`; **both require `confirm: true`** in the body
(400 otherwise). This is the canonical "git-mutation blocking on Linked" boundary.

### A.3 Terminal (`plugins/hermes-agent/terminal/`, plugin.yaml version `0.2.0`, **status payload version `0.3.0`**, tab path `/terminal`)
Implemented in `terminal/dashboard/plugin_api.py` (1324 lines). Uses stdlib `pty`. Vendored xterm.js assets under
`dashboard/dist/vendor/` (`xterm.js`, `xterm.css`, `addon-fit.js`, `NOTICE.md`). Routes:
`GET /status`, `GET /sessions`, `POST /sessions`, `POST /sessions/{id}/resize`, `POST /sessions/clear-closed`,
`GET /sessions/{id}`, `POST /sessions/{id}/reattach`, `GET /sessions/{id}/stream` (SSE), `POST /sessions/{id}/input`,
`POST /sessions/{id}/rename`, `POST /sessions/{id}/close`.

Two backends: `managed-pty` (`_MANAGED_BACKEND`, in-process pty) and `tmux-pty` (`_TMUX_BACKEND`, when `tmux`
installed and not disabled via `TERMINAL_DISABLE_TMUX=1`). `_preferred_backend()` picks tmux when available. Only
the tmux backend yields `process_survives_dashboard_restart` / `reattach_sessions` (and `can_reattach` per session).
tmux runs under an ArcLink-owned socket at `$HERMES_HOME/state/terminal/tmux.sock`; capture/merge via
`_sync_tmux_capture` + `_merge_scrollback_snapshot`.

Session modes (`_clean_session_mode`): `shell`, `ssh` (machine terminal — `+SSH` opens the machine shell with no
remote target prompt; `_resolve_machine_cwd` allows arbitrary host dirs, still blocks sensitive paths), `tui`
(Hermes TUI via `TERMINAL_TUI_COMMAND`/`HERMES_TUI_COMMAND`, default `hermes`). Note: despite the `ssh` mode name
and `_clean_ssh_target`/`_SSH_TARGET_RE`, the create path sets `target: ""` and `+SSH` opens a local machine
shell, not a remote SSH connection.

Runtime gates: `_runtime_user_safe()` blocks running as **root** unless `TERMINAL_ALLOW_ROOT=1`
(`os.geteuid() != 0 or TERMINAL_ALLOW_ROOT==1`); availability also requires a real, non-sensitive workspace dir.
Shell resolution: `TERMINAL_SHELL`, `$SHELL`, `/bin/bash`, `/bin/sh`. Workspace root: `TERMINAL_WORKSPACE_ROOT`,
`CODE_WORKSPACE_ROOT`, `DRIVE_WORKSPACE_ROOT`, else `$HERMES_HOME/workspace`. Bounds: `TERMINAL_MAX_SESSIONS`
(default `_DEFAULT_MAX_SESSIONS`, 1–24), `TERMINAL_SCROLLBACK_BYTES` (default 8_000_000, 4 KB–50 MB),
`TERMINAL_SCROLLBACK_LINES` (default 50000, 500–200000), `TERMINAL_REATTACH_SCROLLBACK_LINES`. Transport is
**same-origin SSE** (`stream_path: /sessions/{id}/stream`) with **polling fallback** (1000 ms). Session state
persists to `$HERMES_HOME/state/terminal/sessions.json`. Output is scrubbed by `_redact_text`/`_sanitize_scrollback`.
The status payload reports `workspace_root: "[workspace]"` and `hermes_state: "[hermes-state]"` (placeholders, not
real paths) — secret-safe by design.

### A.4 arclink-theme (`plugins/hermes-agent/arclink-theme/`)
No-tab plugin (no `dashboard/manifest.json`). `__init__.register()` is a no-op. `plugin.yaml` carries
`arclink_dashboard_default_theme: arclink`. Ships `dashboard-themes/arclink.yaml` and
`dashboard-assets/hermes-arclink-logo.svg`. Install/refresh scripts (external to these files) copy the theme into
`HERMES_HOME/dashboard-themes/` and set `dashboard.theme: arclink`.

### A.5 arclink-managed-context (`plugins/hermes-agent/arclink-managed-context/`, version `1.0.0`)
Pure-stdlib Hermes plugin (`__init__.py`, 1843 lines). Registers two hooks and one command:
`register()` -> `ctx.register_hook("pre_llm_call", _pre_llm_call)`, `ctx.register_hook("pre_tool_call",
_pre_tool_call)`, and `register_command("start", _start_command, ...)`. Declared in plugin.yaml:
`provides_hooks: [pre_llm_call, pre_tool_call]`, `provides_commands: [start]`.

**State files read** (under `$HERMES_HOME/state/`): `arclink-vault-reconciler.json` (the managed payload),
`arclink-web-access.json` (access overlay), `arclink-recent-events.json` (event nudges),
`arclink-identity-context.json` (identity/org/SOUL). `_bootstrap_token()` reads
`$HERMES_HOME/secrets/arclink-bootstrap-token` (overridable via `ARCLINK_BOOTSTRAP_TOKEN_FILE`/`_PATH`), cached by mtime.

**Hot-injection (`_pre_llm_call`)** builds an ephemeral `{"context": ...}` block. Managed sections (in
`_MANAGED_KEYS` order): `arclink-skill-ref`, `org-profile`, `user-responsibilities`, `team-map`, `vault-ref`,
`resource-ref`, `qmd-ref`, `notion-ref`, `vault-topology`, **`vault-landmarks`**, **`recall-stubs`**,
`notion-landmarks`, `notion-stub`, **`today-plate`**. Local sections (`_LOCAL_KEYS`): `model-runtime`,
`resource-ref-live`, `recent-events`, `identity`. Each section has a char limit (`_SECTION_LIMITS`) trimmed by a
recall-budget tier (`ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET=low|mid|high`, aliases default->`mid`). `low` shrinks
`vault-landmarks`/`recall-stubs`/`notion-landmarks`/`today-plate`; recall-stub trimming preserves guardrail lines
(`_RECALL_STUB_GUARDRAIL_MARKERS`: "Retrieval memory stubs:", "Treat these as awareness cards", path rules, "Quality rule:").

**Injection gating** (`full_context_gate`): first turn, revision change (`_context_revision` per session),
model-runtime change, ArcLink-relevant prompt (`_is_relevant` term list, or `_matches_payload_landmark` against
vault/Notion landmark terms), relevant follow-up, or a recipe that forces full context
(`_FULL_CONTEXT_RECIPE_TOOLS = {"knowledge.search-and-fetch"}`). When no full gate but a recipe matches, only the
compact recipe card is injected.

**Per-turn tool recipe cards** (`_TOOL_RECIPES`, max `_MAX_RECIPES_PER_TURN=2`): trigger-phrase -> compact literal
call shape for `knowledge.search-and-fetch`, `shares.request`, `ssot.write`, `ssot.status`, `ssot.pending`,
`vault.search-and-fetch`, `notion.search-and-fetch`, `notion.fetch`, `notion.query`. These tell the model to call
the brokered MCP rail directly (and that the plugin injects the token; "omit token").

**`_pre_tool_call`**: for ArcLink MCP tools (`_TOKEN_TOOL_NAMES`, both dotted and `mcp_arclink_mcp_*` forms) it
**injects the bootstrap token** into `args["token"]`; blocks if args is not an object or token missing; coerces
string JSON `payload` for `ssot.write`/`ssot.preflight`; and enforces a **`notion.query` per-task budget**
(`_NOTION_QUERY_MAX_PER_TASK=3` in a 10-min window) returning an `action: "block"` with guidance to use
`today-plate` + one bounded `knowledge.search-and-fetch`.

**`/arclink-resources` / `/arclink-links`** (and `_RESOURCE_REQUEST_TERMS`): `_is_resource_request` triggers a
cheap resource-bundle context (dashboard/Drive/Code/Notion URLs, ArcPod prefix, workspace + `~/ArcLink` vault
alias, host helper paths, remote-CLI setup), with **passwords/secrets explicitly omitted**.

**Telemetry**: JSONL at `$HERMES_HOME/state/arclink-context-telemetry.jsonl` (rotates at 1 MB), gated by
`ARCLINK_CONTEXT_TELEMETRY` (on unless 0/off/false/no/disable). Summarized by `bin/arclink-context-telemetry`
(referenced in README). Cadence telemetry tags layers `cheap-resource-request` / `cheap-tool-recipes` /
`expensive-managed-context`.

### A.6 Dashboard auth proxy (`python/arclink_dashboard_auth_proxy.py`)
A standalone signed-session reverse proxy (stdlib `http.server`/`http.client`, threading) in front of a local-only
Hermes dashboard. Launched by `bin/run-hermes-dashboard-proxy.sh`, which starts `hermes dashboard --insecure
--no-open` on a backend port (default `13210`) and runs the proxy on `ARCLINK_HERMES_DASHBOARD_PORT` (default
`3210`), `--target http://127.0.0.1:13210`, `--access-file .../state/arclink-web-access.json`, `--realm Hermes`.

This is the **"signed-session auth proxy, not Basic Auth"** boundary. Key facts from code:
- Cookie name `arclink_dash_session` (+ scoped per-deployment `arclink_dash_session_<16hex>` derived from
  realm/target/deployment_id/prefix/secret/username).
- Tokens are **HS256 JWT-shaped** (`SESSION_TOKEN_AUDIENCE = "hermes-dashboard"`, `SESSION_TOKEN_TTL_SECONDS =
  12h`), signed with `_token_secret` from `access["session_secret"]` (or a derived fallback). `_make_token`/
  `_valid_session_cookie` use `hmac.compare_digest`; cookie is `HttpOnly; SameSite=Lax; Secure`.
- Login at `/__arclink/login` (`LOGIN_PATH`), logout at `/__arclink/logout` (`LOGOUT_PATH`); credentials checked
  with `secrets.compare_digest` against the access file; a dark ArcLink-styled login form is served on 401.
- CSRF: `_csrf_origin_ok` requires Origin/Referer host to match Host for mutating methods
  (`DELETE/PATCH/POST/PUT`); rejects with **403 "Cross-origin dashboard mutation rejected."**.
- **Backend session token forwarding**: the Hermes dashboard behind the proxy still protects `/api/*` with an
  ephemeral in-process token; the proxy scrapes `window.__HERMES_SESSION_TOKEN__` from the backend index
  (`BACKEND_SESSION_TOKEN_RE`) and forwards it as header `X-Hermes-Session-Token` only after the signed-session
  gate passes; refreshes on 401.
- **Mount-prefix rewriting**: when `X-Forwarded-Prefix` is set, the proxy rewrites HTML attrs/srcset/CSS url()/JSON
  public paths and injects a `data-arclink-mount-prefix` runtime script that patches fetch/XHR/anchor/EventSource/
  WebSocket/history to prepend the prefix — so the dashboard works under a path prefix (Tailscale path mode).
- **Plugin deep-link injection**: for GET of `/drive`, `/code`, `/terminal` (`PLUGIN_DEEPLINK_PATHS`) it injects a
  `data-arclink-plugin-deeplink` script that auto-clicks the matching tab link.
- **Managed-lifecycle controls**: when `ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS` is truthy, it (a) injects a
  script hiding "restart gateway"/"update hermes" buttons and (b) intercepts POST to
  `/api/gateway/restart`/`/api/hermes/update` (`MANAGED_LIFECYCLE_ENDPOINTS`), returning **409
  `{"arclink_managed": true, ...}`** ("ArcLink manages Hermes gateway and runtime lifecycle through the Sovereign
  Control Node."). Off by default.
- `--no-auth` flag exists to disable auth while keeping the response helpers.
Tests: `tests/test_arclink_dashboard_auth_proxy.py`.

### A.7 Nextcloud access (`python/arclink_nextcloud_access.py`)
Provisioning-side helper, NOT a dashboard plugin. `sync_nextcloud_user_access` / `delete_nextcloud_user_access`
shell `occ` (`user:add`/`user:resetpassword`/`user:delete`) inside the Nextcloud app container via docker/podman/
compose exec as uid 33, in group `arclink-users` (`NEXTCLOUD_SHARED_GROUP`). Gated entirely behind
`ENABLE_NEXTCLOUD=1` (`_nextcloud_enabled`); returns `{"enabled": False, ... "skipped": "disabled"}` otherwise.
Password validated (no newlines), never logged. This is the *only* live Nextcloud surface that remains — Drive/Code
do **not** use it (see B).

---

## B. Proof-gated / fake-adapter / local-only

- **Live browser proof of Drive/Code/Terminal is proof-gated under `PG-HERMES`.** The local plugin code + READMEs
  are real ("the local shape is real"), but no automated live workspace/browser run is asserted here. The runbook
  workspace journey (`bin/arclink-live-proof --journey workspace --live`) covers it but is operator/live-gated.
- **Nextcloud / WebDAV in Drive is effectively dead/disabled local-only.** Drive still carries a large WebDAV code
  surface (`_dav_request`, `_list_dav`, `_item_from_dav`, `_webdav_*`, `_move_webdav`), but `_nextcloud_surface`
  hard-returns `available: False`, `_webdav_profile` returns `{"available": False}`, and `_dav_request` always
  raises **501 "Nextcloud WebDAV access is disabled; use the local Drive backend."** So every `nextcloud-webdav`
  branch is unreachable in practice; the real backend is always local. Drive README §Roots already says "legacy
  Nextcloud/WebDAV browser access is not required." The standalone `arclink_nextcloud_access.py` (user provisioning)
  is separate and still real but `ENABLE_NEXTCLOUD`-gated.
- **Share-request broker is fail-closed / external.** `/share/request` (Drive and Code) only works when a broker
  URL + token file + owner deployment id are all configured (`_share_request_state().enabled`); otherwise it raises
  503 before any external call and `share_request` capability is False. The actual broker is the hosted
  `/api/v1/user/share-grants/broker` route (control-node provisioned). So the share path itself is local-real but
  its live effect is gated on hosted infra + bot delivery (`PG-BOTS`/`PG-HERMES`).
- **tmux persistence** is only active when `tmux` is installed; otherwise in-process managed-pty with no
  process-survives-restart. `process_survives_dashboard_restart`/`reattach_sessions` are conditional capabilities.
- **Managed-context injection depends on state files written elsewhere.** With no
  `state/arclink-vault-reconciler.json` (and no resource request) `_pre_llm_call` returns `None` — nothing injects.
  Bootstrap-token injection in `_pre_tool_call` requires `secrets/arclink-bootstrap-token` to exist.
- **Managed-lifecycle controls** in the auth proxy are off unless
  `ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS` is set (control-node provisioning sets it).
- **Linked writable-share behavior** depends on a real `.arclink-linked-resources.json` manifest (written by the
  share-grant/linked-resource projection elsewhere). Without it, Linked is read-only/empty in effect.

---

## C. Canonical vocabulary (exact names from code)

- Plugins/dirs: `drive`, `code`, `terminal`, `arclink-theme`, `arclink-managed-context`.
- Root ids: `vault`, `workspace`, `fleet`, `linked` (labels Vault/Workspace/Fleet/Linked).
- Backends: Drive `local-vault` / `local-roots` / `nextcloud-webdav`(disabled); Terminal `managed-pty`
  (`_MANAGED_BACKEND`), `tmux-pty` (`_TMUX_BACKEND`).
- Drive constants: `.drive-trash` (`_TRASH_DIR_NAME`), `.arclink-linked-resources.json` (`_LINKED_MANIFEST_NAME`),
  `state/drive-meta.json`, `_MAX_TEXT_BYTES=1_000_000`, `_SEARCH_LIMIT=300`, `_MAX_CHILD_COUNT=999`.
- Share-request: header `X-ArcLink-Share-Request-Broker-Token` (`_SHARE_REQUEST_BROKER_TOKEN_HEADER`); contract
  `arclink-share-grants`; `share_mode: "claim_nonce"`; `reshare_allowed: false`; envs
  `DRIVE/CODE/ARCLINK_SHARE_REQUEST_BROKER_URL`, `..._BROKER_TOKEN_FILE`, `ARCLINK_DEPLOYMENT_ID`.
- Linked manifest entry fields: `access_mode` (`read_write`), `read_only`, `resource_kind` (`directory`/`file`),
  `source_path`. Writability = `_linked_entry_writable` (`access_mode == read_write` and not `read_only`).
- Code git endpoints: `/git/status|commits|diff|stage|unstage|discard|commit|ignore|pull|push`;
  `_resolve_writable_repo` raises 403 "Git mutations are disabled for Linked resources"; pull = `git pull --ff-only`,
  push = `git push`, both require `confirm: true`.
- Terminal envs: `TERMINAL_WORKSPACE_ROOT`, `TERMINAL_SHELL`, `TERMINAL_ALLOW_ROOT`, `TERMINAL_MAX_SESSIONS`,
  `TERMINAL_SCROLLBACK_BYTES`, `TERMINAL_SCROLLBACK_LINES`, `TERMINAL_REATTACH_SCROLLBACK_LINES`,
  `TERMINAL_DISABLE_TMUX`, `TERMINAL_TUI_COMMAND`/`HERMES_TUI_COMMAND`, `HERMES_TUI_DIR`/`TERMINAL_TUI_DIR`,
  `TERMINAL_TUI_SPLASH_DISABLED`. Session id prefix `term-`; tmux socket `$HERMES_HOME/state/terminal/tmux.sock`;
  `state/terminal/sessions.json`.
- Managed-context: hooks `pre_llm_call`, `pre_tool_call`; command `start`; state files
  `arclink-vault-reconciler.json`, `arclink-web-access.json`, `arclink-recent-events.json`,
  `arclink-identity-context.json`; section keys incl. `recall-stubs`, `vault-landmarks`, `notion-landmarks`,
  `today-plate`, `model-runtime`, `resource-ref-live`; env `ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET`,
  `ARCLINK_CONTEXT_TELEMETRY`, `ARCLINK_BOOTSTRAP_TOKEN_FILE`/`_PATH`; telemetry
  `state/arclink-context-telemetry.jsonl`; recipe tools `knowledge.search-and-fetch`, `vault.search-and-fetch`,
  `notion.search-and-fetch`, `notion.fetch`, `notion.query`, `ssot.write`, `ssot.status`, `ssot.pending`,
  `shares.request`; budget cap `notion.query` = 3/task/10min.
- Auth proxy: cookie `arclink_dash_session`(+scoped); audience `hermes-dashboard`; 12h TTL; paths
  `/__arclink/login`, `/__arclink/logout`; backend header `X-Hermes-Session-Token`; managed-lifecycle endpoints
  `/api/gateway/restart`, `/api/hermes/update`; env `ARCLINK_DASHBOARD_MANAGED_LIFECYCLE_CONTROLS`,
  `ARCLINK_HERMES_DASHBOARD_PORT` (3210), `ARCLINK_HERMES_DASHBOARD_BACKEND_PORT` (13210),
  `ARCLINK_HERMES_DASHBOARD_ACCESS_FILE`; `X-Forwarded-Prefix` mount support; `--no-auth` flag.
- Nextcloud: group `arclink-users` (`NEXTCLOUD_SHARED_GROUP`), env `ENABLE_NEXTCLOUD`,
  `ARCLINK_NEXTCLOUD_CONTAINER_NAME`.

---

## D. Undocumented / newer-than-docs items in code

1. **Fleet root in Drive and Code.** Both plugins expose a 4th `fleet` root (`DRIVE/CODE_FLEET_SHARED_ROOT`,
   `ARCLINK_FLEET_SHARED_ROOT`, `$HERMES_HOME/fleet-shared`). Plugin READMEs for drive/code only document
   Workspace/Vault/Linked and never mention Fleet. The runbook §Linked and the symphony "Drive/Code: browse
   Workspace, Vault, and Linked" lists also omit Fleet in their workspace bullets (Fleet is documented separately
   in the runbook "Fleet shared folder" section).
2. **Managed-lifecycle controls in the auth proxy** (hide restart/update buttons + 409 intercept on
   `/api/gateway/restart` and `/api/hermes/update`) — not described in the workspace doc sections.
3. **Backend session-token scraping/forwarding** (`X-Hermes-Session-Token`, `window.__HERMES_SESSION_TOKEN__`) and
   the **mount-prefix runtime rewriting** / **plugin deep-link auto-click** — implementation detail absent from docs.
4. **Recall-budget tiering** (`ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET=low|mid|high`) and **notion.query per-task
   budget block (3/10min)** and the **cadence telemetry layering** — only the managed-context README mentions the
   recall budget; the symphony/runbook don't.
5. **Tool recipe set is wider than the symphony lists.** Symphony §"Hermes Skills And Tool Recipes" names
   `knowledge.search-and-fetch, vault.search-and-fetch, notion.search-and-fetch, ssot.read, ssot.write,
   shares.request` + bootstrap token. Code's `_TOOL_RECIPES` actually covers `ssot.status`, `ssot.pending`,
   `notion.fetch`, `notion.query` too, and notably has **no `ssot.read` recipe card**.
6. **Terminal version drift**: `terminal/plugin.yaml` says `version: 0.2.0` but `_status_payload` returns
   `version: "0.3.0"`. Capabilities include machine/`ssh` sessions and Hermes TUI sessions, beyond what the doc
   tables imply.
7. **README "default to `$HOME`" is stale** for Drive/Code Workspace root: code defaults to `$HERMES_HOME/workspace`.
8. **`+TUI`/Hermes TUI session warming splash** (`_tui_splash_text`, `TERMINAL_TUI_SPLASH_DISABLED`) is a
   code-level UX feature not in the doc tables.

---

## E. Per-doc staleness verdicts

### `plugins/hermes-agent/README.md` — staleness: **light**
- "plugins default to `$HOME` for workspace access" is now inaccurate: Drive/Code Workspace root resolves to
  `$HERMES_HOME/workspace` (Terminal too) unless `*_WORKSPACE_ROOT` is set. Correct to "$HERMES_HOME/workspace".
- Lists drive/code/terminal/arclink-theme but omits `arclink-managed-context` from the bullet list (it is in the
  install set). Minor.

### `plugins/hermes-agent/drive/README.md` — staleness: **light**
- §Roots: "Workspace defaults to `$HOME`" — wrong; code uses `DRIVE_WORKSPACE_ROOT`/`CODE_WORKSPACE_ROOT` then
  `$HERMES_HOME/workspace`.
- Does not mention the **Fleet** root (`DRIVE_FLEET_SHARED_ROOT`/`ARCLINK_FLEET_SHARED_ROOT`/`$HERMES_HOME/
  fleet-shared`), which the code surfaces as a first-class root. Add it.
- Otherwise accurate: writable-share Linked behavior, no direct share-link, brokered Request Share, no-reshare,
  `.drive-trash`, previews — all match code.

### `plugins/hermes-agent/code/README.md` — staleness: **light**
- §Roots: "Workspace defaults to `$HOME`" — same correction (`$HERMES_HOME/workspace`).
- Omits the **Fleet** root. Add it.
- Accurate on: manual-save + disk-hash conflict (`/save` 409), repo-confined git allowlist, Linked git-mutation
  rejection + shared-folder file saves, duplicate-from-Linked into owned root, no-reshare. Could add that `pull`/
  `push` require explicit `confirm` and pull is `--ff-only`.

### `plugins/hermes-agent/terminal/README.md` — staleness: **fresh→light**
- Matches code on tmux/managed-pty, scrollback bounds, `TERMINAL_ALLOW_ROOT`, SSE+polling, xterm.js, `+SSH`/`+TUI`.
- Version drift: README/plugin.yaml imply 0.2.0 but status reports 0.3.0 (cosmetic). `+SSH` "opens the machine
  shell" is correctly described (it is a local machine shell, not a remote SSH dial-out despite the `ssh` mode name).

### `plugins/hermes-agent/arclink-managed-context/README.md` — staleness: **fresh**
- Accurately describes state file, `pre_llm_call` injection, `[local:model-runtime]`, vault-landmarks,
  recall-stubs, notion-landmarks, today-plate, recall budget, telemetry, sibling-memory rules. Could add the
  `pre_tool_call` token-injection + `notion.query` budget block and the per-turn recipe cards (mentioned briefly)
  for completeness, but no contradictions.

### `docs/arclink/operations-runbook.md` — staleness: **light**
- §"Linked resources" (lines ~156-185): matches code well (writable accepted folders, copy/duplicate into owned
  root, **Linked git mutations remain blocked**, direct browser share-link disabled, brokered Share gated on
  broker URL+token+owner id, `X-ArcLink-Share-Request-Broker-Token` header). Accurate.
- §14 "Native Hermes Workspace Plugins": ownership/status table and install set are correct. The
  Docker-deployment claim "Drive uses `/srv/vault` and Code uses `/workspace`" describes the mounted roots via
  `VAULT_DIR`/`DRIVE_ROOT`/`CODE_WORKSPACE_ROOT`; the plugin default (when those are unset) is `$HERMES_HOME/...`
  — worth a one-line note that those are explicit mounts.
- Does not surface the auth proxy's **managed-lifecycle 409 intercept** or **deep-link/mount-prefix injection** in
  the workspace section; those are implied by GAP-019-* security entries but not described as dashboard behavior.
- Add: Fleet root is surfaced by Drive/Code (the runbook documents the Fleet *folder* but not that it appears as a
  Drive/Code root explicitly in §14's plugin behavior list — it is in the Linked/Fleet section at line ~216).

### `docs/arclink/sovereign-control-node-symphony.md` (dream-shape) — staleness: **light** (aspirational by design)
- §"Hermes Dashboard And Plugins" (549-565): Drive/Code/Terminal bullets match code intent; "prevent Linked git
  mutation while allowing shared-folder file saves" exactly matches `_resolve_writable_repo`/`_assert_linked_
  writable_path`. "Dashboard auth: use ArcLink's signed session/proxy layer, not browser-facing Basic Auth"
  exactly matches `arclink_dashboard_auth_proxy.py`. Correctly flagged "Live browser proof remains part of
  `PG-HERMES`."
- §"Hermes Skills And Tool Recipes" (584-588): recipe list is narrower than code's `_TOOL_RECIPES` (missing
  ssot.status/pending, notion.fetch/query) and lists `ssot.read` which has no recipe card in code. Update list.
- §"Agent Knowledge, Memory, And Docs" (608-609): "Managed context hot-injects recall stubs, vault landmarks,
  Notion landmarks, model/runtime data, and daily plate information" — exactly matches `_MANAGED_KEYS` +
  `model-runtime`. Fresh.

---

## F. GAP-* status touched by this subsystem

This subsystem is primarily proof-gated under **`PG-HERMES`** (live browser proof of Drive/Code/Terminal) — that
is the dominant open item; the local code shape is complete. Related security GAPs (documented in the runbook
GAP-019-* series) constrain the *provisioning/sidecar* path that launches the dashboard + auth proxy, not the
plugin code itself:
- **GAP-019-I** — auth-proxy/dashboard-network sidecar operations routed through `agent-supervisor-broker`
  (removed direct Docker socket from `agent-supervisor`); broker socket remains trusted-host residual risk.
- **GAP-019-Z / GAP-019-AZ / GAP-019-AR** — narrow the dashboard broker's env, private bind-root, and backend-host
  boundaries used when constructing the dashboard auth-proxy `docker run -v` / network. These are landed
  narrowings, still with residual trusted-host risk per the runbook.
True current status: the plugin/auth-proxy/managed-context **source is implemented and unit-tested**
(`tests/test_arclink_dashboard_auth_proxy.py`, `tests/test_arclink_plugins.py`); the remaining open work is the
**live `PG-HERMES` browser/workspace proof** and the residual trusted-host socket risk on the dashboard broker
(GAP-019-I family). No GAP claims this subsystem's local behavior is unimplemented.
