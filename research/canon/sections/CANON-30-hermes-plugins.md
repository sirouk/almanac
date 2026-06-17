# CANON-30 — Hermes Plugins & Bridges

## PIECE
This piece owns the six native ArcLink Hermes dashboard/agent plugins under
`plugins/hermes-agent/` plus the three shell installers/sync scripts that copy
them into a Hermes workspace home. The plugins are: **drive** (file manager tab),
**code** (code editor + git source-control tab), **terminal** (managed-pty/tmux
terminal tab), **arclink-crew** (header-right Crew switcher dropdown, new since
prior doc 07), **arclink-theme** (no-tab; installs/defaults the ArcLink dashboard
theme), and **arclink-managed-context** (no-tab agent plugin: two Hermes hooks
`pre_llm_call`/`pre_tool_call` + one `/start` command). Each tabbed plugin is a
FastAPI `APIRouter` in `dashboard/plugin_api.py` (with no-op stub fallback classes
when FastAPI is absent), a `dashboard/manifest.json`, and a prebuilt
`dashboard/dist/index.js` (+`style.css`). The installers are
`bin/install-arclink-plugins.sh` (the real engine: rsync plugin dirs into
`$HERMES_HOME/plugins`, mutate `$HERMES_HOME/config.yaml` plugins/dashboard
sections, render+install dashboard themes, install the telegram-start hook),
`bin/install-hermes-workspace-plugins.sh` (thin wrapper that installs only
`drive code terminal` with hooks skipped), and `bin/sync-hermes-bundled-skills.sh`
(invokes the external Hermes-runtime `tools/skills_sync.py` to sync bundled
skills — a runtime, not a plugin). Tracked files actually covered are listed in
filesClaimed.

## INPUT CONTRACT (code-verified)
**install-arclink-plugins.sh** — `argv: <repo-dir> <hermes-home> [plugin-name ...]`
(`bin/install-arclink-plugins.sh:4-11`). `<2 args` -> usage to stderr, exit 2
(`:4-7`). With zero plugin names it defaults to `drive code terminal arclink-theme
arclink-managed-context arclink-crew` (`:13-21`). `normalize_plugin_name` folds
legacy aliases (`arclink-code/codespace/code-space/arclink-code-space`->`code`;
`arclink-drive/knowledge-vault/arclink-knowledge-vault`->`drive`;
`arclink-terminal`->`terminal`) (`:36-43`). Env inputs read by the script:
`INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS` (`:657`), `ARCLINK_DASHBOARD_THEME` (`:648`),
and theme-render labels `ARCLINK_DASHBOARD_AGENT_LABEL`/`ARCLINK_AGENT_NAME`,
`ARCLINK_DASHBOARD_THEME_LABEL`, `ARCLINK_DASHBOARD_ACCENT_HEX` (`:486-488`).

**install-hermes-workspace-plugins.sh** — `argv: <repo-dir> <hermes-home>
[plugin ...]` (`:4-11`); zero names -> `drive code terminal` (`:13-15`); execs
install-arclink-plugins.sh with `INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS=1` (`:17-18`).

**sync-hermes-bundled-skills.sh** — `argv: <hermes-home> [runtime-dir]` (`:4-12`);
also reads env `RUNTIME_DIR`, `ARCLINK_HERMES_BIN` to locate the runtime
(`:10,18-21`). Probes candidates for `hermes-agent-src/tools/skills_sync.py` +
`hermes-agent-src/skills` (`:28`); if none found it prints a skip notice and
**exits 0** (no-op, fail-open) (`:34-37`).

**drive/code/terminal/crew plugin_api routers** — FastAPI route handlers. Callers
are the Hermes dashboard backend (external runtime) reverse-proxied by
`arclink_dashboard_auth_proxy.py` (CANON-19). HTTP inputs validated per route:
drive `_clean_relative_path` rejects `..` -> 400 (`drive…:1040-1052`);
`_assert_accessible_path` -> 403 outside-root (`drive…:1168-1181`);
`_assert_not_sensitive` -> 403 (`drive…:612-614`). Code git mutations gate on
`confirm is True` (`code…:1559,1602,1612,1862`) and Linked-id -> 403
(`code…:1092-1093`). Terminal create gates on `_runtime_user_safe()` (no root
unless `TERMINAL_ALLOW_ROOT=1`) (`terminal…:304-307`).

**arclink-managed-context hooks** — `register(ctx)` calls
`ctx.register_hook("pre_llm_call", _pre_llm_call)`,
`ctx.register_hook("pre_tool_call", _pre_tool_call)`, and (if available)
`register_command("start", _start_command, ...)` (`…/__init__.py:1903-1912`).
Caller is the Hermes agent runtime (external). `_pre_llm_call` keyword args:
`session_id, user_message, conversation_history, is_first_turn, model, platform,
sender_id` (`:1666-1675`). `_pre_tool_call` keyword args: `tool_name, args,
session_id, task_id, tool_call_id` (`:1833-1840`). `args` must be a dict else
`{"action":"block",...}` (`:1844-1848`).

## OUTPUT CONTRACT (code-verified)
**install-arclink-plugins.sh** side-effects:
(1) rsync/cp each plugin dir from `$REPO/plugins/hermes-agent/<n>` to
`$HERMES_HOME/plugins/<n>`, deleting stale files and excluding `__pycache__`/
`*.pyc`/caches (`:580-598`); aborts if src lacks `plugin.yaml`+`__init__.py`
(`:575-578`) or dst lacks them post-copy (`:600-603`).
(2) `cleanup_legacy_plugins` deletes `$HERMES_HOME/plugins/{arclink-code-space,
arclink-knowledge-vault,arclink-code,arclink-drive,arclink-terminal}` (`:27-33,
45-51,625`).
(3) Mutates `$HERMES_HOME/config.yaml`: `sync_plugin_config` adds names to
`plugins.enabled`, strips legacy names from enabled/disabled (`:53-167,652`);
`sync_dashboard_theme_config` sets `dashboard.theme: <theme>` (`:169-261,653`);
`sync_dashboard_visible_plugins_config` removes drive/code/terminal from
`dashboard.hidden_plugins` (`:374-456,654`); `sync_dashboard_hidden_plugins_config`
adds `example` to `dashboard.hidden_plugins` (`:263-372,655`).
(4) Installs themes: renders `dashboard-themes/*.yaml` from the plugin into
`$HERMES_HOME/dashboard-themes/` substituting `__ARCLINK_AGENT_LABEL__`/
`__ARCLINK_THEME_LABEL__`/`__ARCLINK_THEME_ACCENT_HEX__` (`:483-511`), and for
`arclink-theme` generates 5 colour variants (arclink-violet/matrix/blue/gold/
crimson) (`:513-546`).
(5) Unless `INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS==1`, installs hook
`arclink-telegram-start` from `$REPO/hooks/hermes-agent/` to `$HERMES_HOME/hooks/`
(`:606-623,657-659`).

**Plugin runtime outputs** (JSON over HTTP, consumed by the dashboard JS bundle):
drive routes return file listings/previews/trash/share results; `/status` returns
`version:"1.0.0"`, roots, capabilities, backend (`drive…:1669-1705,1686`). Drive
`/share/request` POSTs to the external broker and returns nonce/copy_text
(`drive…:1707-1721`). Code `/status` `version:"1.0.0"` (`code…:1417,1427`);
git/save/ops side-effect the local filesystem via repo-confined `git -C`
(`code…:1113-1129`) and atomic writes. Terminal `/status` `version:"0.4.0"` with
**placeholder** `workspace_root:"[workspace]"`/`hermes_state:"[hermes-state]"`
(`terminal…:1087,1091,1093`) — never the real path. Crew `/crew` returns
`{crew, refreshed_at, count}` (max 24 https links) (`crew…:52-72`); `/status`
returns presence + a guidance summary (`crew…:75-87`).

**arclink-managed-context outputs**: `_pre_llm_call` returns `{"context": <str>}`
or `None` (`…/__init__.py:1713,1716,1729`). `_pre_tool_call` returns `None`
(allow, after mutating `args["token"]`) or `{"action":"block","message":...}`
(`:1842-1896`). Writes JSONL telemetry to
`$HERMES_HOME/state/arclink-context-telemetry.jsonl`, rotated at 1 MB
(`:1078-1105`). `_start_command` returns a greeting string (`:1899-1900`).

## TOUCH POINTS
**Env vars** — drive root discovery: `ARCLINK_WORKSPACE_ROOT, DRIVE_ROOT,
KNOWLEDGE_VAULT_ROOT, AGENT_VAULT_DIR, VAULT_DIR, HOME` (vault, `drive…:513-531`);
`ARCLINK_WORKSPACE_ROOT, DRIVE_WORKSPACE_ROOT, ARCLINK_DRIVE_ROOT, DRIVE_ROOT,
…, ARCLINK_CODE_WORKSPACE_ROOT, CODE_WORKSPACE_ROOT` (workspace, `:534-554`);
`DRIVE_LINKED_ROOT, ARCLINK_LINKED_RESOURCES_ROOT` (`:557-566`);
`DRIVE_FLEET_SHARED_ROOT, ARCLINK_FLEET_SHARED_ROOT` (`:569-578`);
`HERMES_HOME` (`:184`). Drive share-request:
`DRIVE/ARCLINK_SHARE_REQUEST_BROKER_URL`, `..._BROKER_TOKEN_FILE`,
`DRIVE/ARCLINK/ARCLINK_OWNER_DEPLOYMENT_ID`, `ARCLINK_DEPLOYMENT_ID`
(`:617-650`). Terminal: `TERMINAL_WORKSPACE_ROOT, CODE_WORKSPACE_ROOT,
DRIVE_WORKSPACE_ROOT` (`:206`), `TERMINAL_MAX_SESSIONS` (`:284`),
`TERMINAL_ALLOW_ROOT` (`:307`), `TERMINAL_DISABLE_TMUX` (`:311`),
`ARCLINK_TERMINAL_TMUX_SOCKET`-style override at `_tmux_socket_path` (`:331-337`).
Managed-context: `HERMES_HOME` (`:627`), `ARCLINK_BOOTSTRAP_TOKEN_FILE/_PATH`
(`:630-638`), `ARCLINK_MANAGED_CONTEXT_RECALL_BUDGET` (`:59`),
`ARCLINK_CONTEXT_TELEMETRY` (`:1073`). Crew: `HERMES_HOME` (`crew…:28`).

**Files/paths** — `$HERMES_HOME/plugins/<n>`, `$HERMES_HOME/config.yaml`,
`$HERMES_HOME/dashboard-themes/`, `$HERMES_HOME/hooks/` (installer);
`$HERMES_HOME/state/drive-meta.json` (`drive…:991-992`),
per-root `.drive-trash` (`drive…:121`), `.arclink-linked-resources.json`
(`drive…:122`); `$HERMES_HOME/state/terminal/{sessions.json,tmux.sock}`
(`terminal…:134,331-337`); `$HERMES_HOME/secrets/arclink-bootstrap-token`
(`mc…:638`); `$HERMES_HOME/state/{arclink-vault-reconciler.json,
arclink-web-access.json,arclink-recent-events.json,arclink-identity-context.json,
arclink-context-telemetry.jsonl}` (`mc…:12-15,704-709,1078`);
`$HERMES_HOME/state/arclink-web-access.json` (crew, `crew…:31-33`).

**Sockets/subprocess** — code runs `git -C <repo> …` (subprocess, 30s timeout)
(`code…:1113-1129`); terminal uses stdlib `pty`/`tmux -S <socket>` (`terminal…:
331-350`); drive share-request uses `urllib.request.urlopen(..., timeout=10)` to
the broker (`drive…:965-979`).

**Secrets handling** — bootstrap token read from `secrets/arclink-bootstrap-token`,
cached by mtime, never logged (`mc…:641-664`); broker token validated/cleaned
(printable ≤4096 bytes), never logged (`drive…:626-642`); drive
`_is_sensitive_path` blocks `.ssh`, ssh keys (`id_rsa/id_ed25519/id_ecdsa/id_dsa`),
`.env*`, `*bootstrap-token*`, `.arclink-operator.env`, arclink-priv env files, and
anything under `$HERMES_HOME/{secrets,state}` (`drive…:589-609,125-133`); terminal
status reports placeholder paths (`terminal…:1087,1091`).

**DB tables** — none written by this piece directly. Indirect via the broker seam:
`arclink_share_claim_nonces` written by the hosted-API consumer
(`arclink_api_auth.py:3691-3713`).

## CODE-PATH TRACE
Drive "Request Share" end-to-end:
1. Dashboard JS POSTs `/drive/share/request` with `{root, path, display_name}`.
   `share_request` reads JSON body (`drive…:1707-1710`).
2. Linked root is rejected -> 403 (`drive…:1712-1713`).
3. `_resolve_local` confines the path: `_clean_relative_path` rejects `..`
   (`drive…:1040-1052`), `_assert_accessible_path` confines to root
   (`drive…:1168-1181`), `_assert_not_sensitive` (`drive…:612-614`).
4. `_share_request_payload` builds the wire body with `contract:
   "arclink-share-grants"`, `source_plugin:"drive"`, `owner_deployment_id`,
   `resource_root`, `resource_path`, `resource_kind:"drive"`, `item_kind`,
   `display_name`, `requested_access:"read_write"`, `share_mode:"claim_nonce"`,
   `reshare_allowed:False` (`drive…:919-936`). Missing owner id -> 503 (`:921-922`).
5. `_share_request_broker_url` (env) — empty -> 503 (`drive…:1716-1718`).
   `_share_request_auth_headers` adds `X-ArcLink-Share-Request-Broker-Token`,
   missing token -> 503 (`drive…:653-657`).
6. `_submit_share_request_to_broker` POSTs JSON (sorted keys) to the broker URL,
   10s timeout; non-2xx/invalid JSON/`ok:false` -> 502 (`drive…:965-988`).
7. Consumer: hosted API route `("POST","/user/share-grants/broker")` ->
   `_handle_user_share_grant_broker_create` reads the header token + body keys and
   calls `create_user_share_grant_from_broker_api`
   (`arclink_hosted_api.py:3794,1732-1759`). It validates
   `contract=="arclink-share-grants"` (`api_auth…:3525-3526`) and
   `share_mode in {"owner_approval","claim_nonce"}` (`:3527-3528`), rejects
   reshare (`:3530-3531`), then `mint_share_claim_nonce_for_owner` inserts into
   `arclink_share_claim_nonces` and returns `{ok, mode:"claim_nonce", broker,
   nonce, accept_command, copy_text, expires_at, expires_in_hours, …}`
   (`api_auth…:3739-3758`).
8. `_share_request_response` reads `nonce` (missing -> 502), `expires_in_hours`,
   `copy_text`, `accept_command`, `expires_at` and returns the dashboard payload
   (`drive…:939-962`).

## CROSS-PIECE CONTRACTS (both ends verified)
1. **Drive/Code `/share/request` -> CANON-02 hosted API broker.** Contract:
   POST to `…/user/share-grants/broker` with header
   `x-arclink-share-request-broker-token` and JSON body keys `contract,
   owner_deployment_id, resource_root, resource_path, resource_kind, item_kind,
   display_name, requested_access, share_mode, reshare_allowed, source_plugin`.
   Producer `drive…:919-988`; consumer `arclink_hosted_api.py:1741-1757` +
   `arclink_api_auth.py:3525-3531`. Response keys `ok, mode, broker, nonce,
   accept_command, copy_text, expires_at, expires_in_hours` produced at
   `api_auth…:3739-3758`, consumed at `drive…:939-962`. Header constants match
   (`api_auth…:102`, `hosted_api…:136`). BOTH-ENDS-VERIFIED: yes.
2. **arclink-managed-context `_pre_tool_call` -> CANON-18 MCP rail.** Contract:
   plugin sets `args["token"] = <bootstrap-token>` for ArcLink MCP tools
   (`mc…:1879`); MCP server reads `arguments.get("token")` and `validate_token`s
   (`arclink_mcp_server.py:1052,2045,…`). Tool-name set
   `_TOKEN_TOOL_NAMES` (dotted + `mcp_arclink_mcp_*`) (`mc…:276-302`). MCP schema
   declares a `token` prop, doc string says "arclink-managed-context fills it"
   (`arclink_mcp_server.py:166`). BOTH-ENDS-VERIFIED: yes.
3. **arclink-crew `/crew` -> CANON-08 sovereign worker web-access state.**
   Producer `arclink_sovereign_worker.py:1787-1788` writes `crew_dashboards`
   (list) + `crew_dashboards_refreshed_at` into
   `state/arclink-web-access.json`; entries are built at
   `arclink_provisioning.py:842-855` with keys `label,title,status,url,
   dashboard_url,hermes_url,current,theme_label`. Consumer `_clean_link` reads
   exactly `label, hermes_url|url|dashboard_url, title, status, current,
   theme_label` and requires `url.startswith("https://")` (`crew…:35-49,63-67`).
   BOTH-ENDS-VERIFIED: yes.
4. **arclink-managed-context `_pre_llm_call` -> Hermes agent runtime (EXTERNAL).**
   Contract: return `{"context": <str>}` or `None`; runtime injects the context
   block per-turn. Producer cite `mc…:1713,1716,1729`. Consumer is the external
   Hermes runtime (not in repo). BOTH-ENDS-VERIFIED: no (consumer not in repo).
5. **Installer -> Hermes dashboard config (`$HERMES_HOME/config.yaml`
   plugins/dashboard keys) — EXTERNAL runtime consumer.** Producer mutates
   `plugins.enabled`, `dashboard.theme`, `dashboard.hidden_plugins`
   (`install…:652-655`). README states Hermes reads `plugins.enabled`
   (`plugins/hermes-agent/README.md:29-30`). Consumer is the external Hermes
   runtime. BOTH-ENDS-VERIFIED: no (consumer not in repo).
6. **`sync-hermes-bundled-skills.sh` -> external Hermes runtime
   `tools/skills_sync.py`.** Producer execs it with env `HERMES_HOME`,
   `HERMES_BUNDLED_SKILLS` (`:48-52`). The script is NOT in the repo (confirmed
   via `git ls-files`). BOTH-ENDS-VERIFIED: no (consumer is runtime-only).
7. **Installers consumed by CANON-24/06/28 deploy scripts.** Callers:
   `bin/init.sh:296,317`, `bin/install-deployment-hermes-home.sh:18,20`,
   `bin/refresh-agent-install.sh:525-547`, `bin/install-agent-user-services.sh:
   148-150`, `bin/bootstrap-curator.sh:1002,1021`, `bin/ci-install-smoke.sh:
   1230,1829`. Argv contract `<repo-dir> <hermes-home> [...]`. Both ends
   verified for callers in repo: yes.

## CODE vs COMMENT/DOC/NAME DRIFT
- **Prior doc 07 is stale on terminal version.** It claimed `plugin.yaml 0.2.0`
  and status `0.3.0`. Code now has `version: 0.4.0` in plugin.yaml
  (`terminal/plugin.yaml:2`), manifest.json (`:6`), AND status payload
  (`terminal…:1087`) — version drift is resolved; prior doc lies.
- **Prior doc 07 predates `arclink-crew`.** The Crew plugin (header-right
  switcher, `arclink-crew/`) is real and in the default install set
  (`install…:20`) but absent from doc 07's enumeration.
- **Default install set grew to 6.** Doc 07/README say "drive, code, terminal,
  arclink-theme, arclink-managed-context"; the installer also installs
  `arclink-crew` (`install…:13-21`).
- **README "default to `$HOME`" vs code.** `plugins/hermes-agent/README.md:32`
  now says plugins default to `ARCLINK_WORKSPACE_ROOT` then vault/legacy — but the
  Drive/Code workspace fallback is `$HERMES_HOME/workspace`, not `$HOME`
  (`drive…:549-553`). README also omits `arclink-crew` from its bullet list
  (`README.md:5-12`).
- **Drive README/doc omit the Fleet root.** Code exposes a first-class `fleet`
  root (`drive…:155-161,569-578`); README bullets list only Workspace/Fleet/Linked
  in the top description (`README.md:5`) but per-plugin drive README historically
  omitted it (prior-doc finding D.1 still applies).
- **Name vs behavior: terminal `ssh` mode is a LOCAL machine shell.** Mode name
  `ssh` (`terminal…:454-456`) but it resolves a local machine cwd
  (`_resolve_machine_cwd`, `:498-513`), not a remote dial-out — name lies about
  remoteness (matches prior doc, still true).
- **WebDAV code is dead.** Large `_dav_request`/`_propfind`/`nextcloud-webdav`
  surface exists but `_dav_request` hard-raises 501 and `_nextcloud_surface`
  returns `available:False` (`drive…:503-510,1563`) — every WebDAV branch is
  unreachable; the "nextcloud-webdav" backend name is vestigial.

## ADVERSARIAL SELF-CHECK
1. *"The share-request seam fully matches end-to-end."* Verified producer keys
   (`drive…:919-936`) against consumer reads (`hosted_api…:1741-1757`) and the
   contract/share_mode validation (`api_auth…:3525-3531`). Falsifier: if the
   hosted route required additional mandatory body keys the drive payload omits
   (e.g. `recipient_user_id`) it would 4xx. The handler defaults those to ""
   (`hosted_api…:1744-1746`) and the claim-nonce path does not require a
   recipient (minting is approval), so the happy path holds — but I did not
   execute a live request.
2. *"Crew `_clean_link` always accepts producer entries."* It requires
   `url.startswith("https://")` (`crew…:41`). If `urls.get("hermes")` is empty
   for an Agent (e.g. pre-DNS), `hermes_url`/`url`/`dashboard_url` may all be ""
   and the entry is silently dropped. Falsifier: a deployment with non-https or
   empty hermes URL -> entry vanishes from the dropdown (a real partial-state
   no-op, not a bug per se).
3. *"`register()` is a true no-op for drive/code/terminal/crew/theme."* Read all
   five: each returns `None` (`drive/__init__.py:4-5`, etc.). Falsifier: if the
   Hermes runtime requires `register` to return a router/manifest, the tab would
   not appear — but the tab is wired via `manifest.json` `entry`/`api`, not the
   `register` return, so no-op is correct.
4. *"Terminal never leaks the real workspace path."* `/status` returns
   placeholders (`terminal…:1087,1091`), but other terminal routes
   (sessions/stream) operate on the real cwd; I did not audit every response for
   path leakage in error strings (`_redact_text` is applied to errors, `:524`).
   Falsifier: a route echoing an unredacted absolute path on error.
5. *"The installer's YAML mutation is idempotent and safe."* The python heredocs
   parse `config.yaml` by indentation regex, not a YAML parser. Falsifier: a
   config.yaml using tabs or unusual nesting could be mis-edited; the code only
   normalizes `\t`->`  ` for indent counting (`install…:84,92`) — non-trivial
   nested YAML could be corrupted. Not executed against adversarial YAML.

## OPEN FOR CODEX FEDERATION
- Verify the full set of mandatory vs optional body keys on
  `create_user_share_grant_from_broker_api` (`arclink_api_auth.py:3507+`) against
  the exact drive/code payloads — confirm no required field is silently empty in
  the claim_nonce path, and confirm broker-token auth (hash compare) actually
  gates the route.
- Confirm `_TOKEN_TOOL_NAMES` (managed-context) is a superset of every ArcLink
  MCP tool that requires a token in `arclink_mcp_server.py`; a missing entry
  means the plugin won't inject the token and the call fails closed (or worse,
  the model is told to "omit token").
- Validate the installer's indentation-regex `config.yaml` editor against real
  Hermes config shapes (tabs, comments, anchors) for corruption risk.
- Confirm the external `tools/skills_sync.py` contract (env `HERMES_HOME`,
  `HERMES_BUNDLED_SKILLS`) matches the actual Hermes runtime expectation — this
  piece cannot prove the consumer since it is not in the repo.

## RISKS (severity-ranked, code-cited)
- **MEDIUM** — `sync-hermes-bundled-skills.sh` fails **open** (exit 0) when the
  runtime/skills source is absent (`bin/sync-hermes-bundled-skills.sh:34-37`); a
  silently-skipped sync leaves stale/missing bundled skills with no error signal
  to the deploy lane.
- **MEDIUM** — installer mutates `config.yaml` with regex-based indentation
  parsing, not a YAML parser (`install…:74-99,191-209`); adversarial or
  tab-indented config could be mis-edited/corrupted. No backup is written before
  in-place rewrite (`:165,259,370,454`).
- **LOW** — Drive sensitive-path block is name/path heuristic
  (`drive…:589-609`): it relies on a fixed filename/dir set; a sensitive file
  with an unlisted name under a root is browsable. Symlink escapes are blocked
  only in copy (`_assert_no_symlink_escape`, `drive…:1383`), and
  `_assert_accessible_path` resolves with `strict=False` (`:1176`) — TOCTOU on a
  symlink swapped between check and use is conceivable.
- **LOW** — Crew links silently drop on empty/non-https URL (`crew…:41`); a
  Captain mid-provisioning sees a partial roster with no explanation in `/crew`
  (the `/status` summary does hint at this, `crew…:84-86`).
- **INFO** — Large dead WebDAV surface in `drive/plugin_api.py` (501-stubbed,
  `:1563`) increases attack/maintenance surface with no live path.
- **INFO** — Managed-context `_pre_tool_call` blocks (fail-closed) when the
  bootstrap token is missing (`mc…:1869-1877`) — correct, but means a missing
  `secrets/arclink-bootstrap-token` disables every ArcLink MCP tool silently from
  the model's perspective (a "block" message, not an error).

## VERDICT
Provably does its job. The six plugins are real, structurally consistent
(plugin.yaml + __init__.py + manifest.json + prebuilt dist), and the installer
correctly rsyncs them, removes legacy variants, wires `config.yaml`, renders
themes, and installs the telegram-start hook. Three cross-piece seams are fully
both-ends-verified in code: the Drive/Code share-request broker call (CANON-02),
the managed-context bootstrap-token injection into the MCP rail (CANON-18), and
the Crew switcher reading sovereign-worker-published `crew_dashboards`
(CANON-08/19). Load-bearing strengths: path confinement and sensitive-file
blocking in Drive/Code, repo-confined git with explicit-confirm + Linked-mutation
403 in Code, root-gated/secret-safe Terminal, and fail-closed token injection in
managed-context. Real weaknesses: the bundled-skills sync fails open silently; the
installer edits YAML by regex without backup; the Drive sensitive-path guard is a
denylist heuristic with `strict=False` resolution (TOCTOU-adjacent). Prior doc 07
is materially stale on this piece — it predates `arclink-crew`, the 6-plugin
default set, and the terminal `0.4.0` version unification.
