# CANON-30 — Hermes Plugins & Bridges — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing file
at the cited lines; cross-traced both ends of each "both-ends-verified" seam.

Overall verdict: **MOSTLY TRUSTWORTHY, BUT ONE CROSS-PIECE CONTRACT MARKED
"BOTH-ENDS-VERIFIED: yes" IS REFUTED, AND ONE OUTPUT-CONTRACT FACT IS WRONG.**
The structural / installer / drive-share / crew claims hold. The managed-context →
MCP token-injection seam (contract #2) does NOT cover every token-requiring,
agent-advertised MCP tool, so its "both-ends-verified: yes" stamp is false.

---

## REFUTATIONS (claim → finding)

### R1 [HIGH] Contract #2 ("managed-context `_pre_tool_call` → MCP rail",
"BOTH-ENDS-VERIFIED: yes") is REFUTED — token NOT injected for several
token-requiring, agent-advertised MCP tools.

The plugin only injects `args["token"]` when `_tool_needs_agent_token(tool_name)`
is true (`arclink-managed-context/__init__.py:1842`), which is membership in
`_TOKEN_TOOL_NAMES` (`:667-668`). `_TOKEN_TOOL_NAMES` is built solely from
`_TOKEN_TOOL_SUFFIXES` (22 entries, `:276-302`).

But the MCP server requires `validate_token(arguments.get("token"))` for tools
that are NOT in that set, and which ARE advertised to enrolled agents and declare
the agent-injected token prop:
- `pod_comms.list` → `_agent_pod_comms_owner` → `validate_token` (`arclink_mcp_server.py:1094`); schema declares `"token": AGENT_TOKEN_PROP` (`:399`); advertised in `TOOLS` (`:99`, `tools/list` at `:1787-1796`).
- `pod_comms.send` → same `validate_token` (`:1094`); schema `:407`; advertised `:100`.
- `pod_comms.share-file` → same `validate_token` (`:1094`); schema `:422`; advertised `:101`.
- `agents.register` → `register_agent(..., raw_token=arguments.get("token"))` (`arclink_mcp_server.py:1989-1993`); advertised `:86`.

`AGENT_TOKEN_PROP`'s description is the literal seam contract: "Hermes agents
should omit this field; arclink-managed-context fills it before dispatch"
(`arclink_mcp_server.py:166`). For `pod_comms.*` the producer (the plugin) does
NOT honor that contract: it returns `None` at `__init__.py:1843` and never sets
`args["token"]`. Consequence: an enrolled agent that follows the schema and omits
the token on `pod_comms.send` reaches the MCP server with `token == ""`, and
`validate_token("")` fails. The seam is broken end-to-end.

The record itself flagged "Confirm `_TOKEN_TOOL_NAMES` is a superset of every
ArcLink MCP tool that requires a token" as merely OPEN FOR CODEX, while
simultaneously stamping contract #2 "BOTH-ENDS-VERIFIED: yes." Those two
statements are mutually inconsistent; the superset does NOT hold, so the stamp is
wrong. (Note: `bootstrap.*` correctly use `REGISTRATION_TOKEN_PROP` / capability
gating and are out of scope, but `pod_comms.*` use `AGENT_TOKEN_PROP` and are in
scope.)

### R2 [MEDIUM] OUTPUT-CONTRACT / TOUCH-POINTS fact WRONG: code git timeout is
**15s, not 30s.**

The record (OUTPUT CONTRACT line "subprocess, 30s timeout" and TOUCH POINTS
"code runs `git -C <repo> …` (subprocess, 30s timeout) (`code…:1113-1129`)")
states 30 seconds. The code: `_GIT_TIMEOUT_SECONDS = 15`
(`code/dashboard/plugin_api.py:103`), used at `:1119`. The "30s" claim is refuted
by the source.

### R3 [LOW] DRIFT bullet "terminal `ssh` mode is a LOCAL machine shell" is
UNDERSTATED — the SSH-target validator is fully dead and `ssh` mode launches a
plain local shell.

The record says ssh mode "resolves a local machine cwd … not a remote dial-out."
True, but stronger: `_runtime_argv` for `mode == "ssh"` returns `[shell, "-i"]`
(`terminal/dashboard/plugin_api.py:960-964`) — a local interactive shell. It never
runs the `ssh` binary and never references a remote target. `_clean_ssh_target`
(`:459-462`) and `_SSH_TARGET_RE` (`:62`) are defined but NEVER called anywhere
in the plugin (grep across `terminal/` returns only the def + regex def). So the
"ssh" mode is purely cosmetic and the target-validation surface is dead code — a
gap neither the record nor prior doc 07 names.

---

## CONFIRMATIONS (independently re-verified in code)

- C1 Installer argv/usage/exit-2 (`install-arclink-plugins.sh:4-7`), default
  6-plugin set incl. `arclink-crew` (`:13-21`), `normalize_plugin_name` aliases
  (`:36-43`). VERIFIED.
- C2 Installer rsync `--delete` + excludes (`:582-590`), src guard (`:575-578`),
  dst guard (`:600-603`), legacy cleanup (`:45-51,625`), no-backup in-place YAML
  writes at `:165,259,370,454`. VERIFIED. YAML edited by indentation-regex, not a
  YAML parser. VERIFIED.
- C3 `install-hermes-workspace-plugins.sh` default `drive code terminal`, execs
  engine with `INSTALL_ARCLINK_PLUGINS_SKIP_HOOKS=1` (`:13-18`). VERIFIED.
- C4 `sync-hermes-bundled-skills.sh` fail-OPEN exit 0 when runtime absent
  (`:34-37`); candidate probe requires both `tools/skills_sync.py` + `skills/`
  dir (`:28`). VERIFIED. (Record MEDIUM severity is fair.)
- C5 Drive path confinement: `_clean_relative_path` rejects `..`→400 (`:1049-1050`),
  `_assert_accessible_path` 403 outside-root with `strict=False` resolve at
  `:1176` (`:1168-1181`), `_assert_not_sensitive`→403 (`:612-614`),
  `_is_sensitive_path` denylist incl. `.ssh`/ssh keys/`.env*`/`*bootstrap-token*`/
  hermes secrets+state (`:589-609`). VERIFIED. NOTE: `_assert_not_sensitive` only
  runs when `relative_path` is truthy (`:1189-1190`); the root itself skips it
  (low risk — roots are not per-request user input).
- C6 Drive share-request producer payload keys (`:919-936`), missing owner→503
  (`:921-922`), empty broker URL→503 (`:1717-1718`), missing token→503
  (`:653-656`), broker POST 10s timeout / non-2xx→502 (`:965-988`). VERIFIED.
- C7 Contract #1 (drive/code share → hosted API broker): consumer reads body keys
  at `hosted_api:1741-1757`; validates `contract=="arclink-share-grants"`
  (`api_auth:3525-3526`), `share_mode∈{owner_approval,claim_nonce}` (`:3527-3529`),
  rejects reshare (`:3530-3531`). ADDITIONAL validation the record omitted but is
  present: `source_plugin∈{drive,code}` (`:3532-3534`), resource_kind must match
  source (`:3545-3547`), item_kind∈{file,directory} (`:3548-3549`). Broker-token
  auth IS enforced via `_authenticate_share_request_broker` →
  `_verify_proof_token_hash` using `hmac.compare_digest` (`:2477`, `:248-257`) —
  the record left this as OPEN but it is real and constant-time. Header constants
  match case-insensitively (`_header` lowercases, `api_auth:142-144`); producer
  sends mixed-case `X-ArcLink-…` (`drive:146`), consumer reads lowercase
  (`hosted_api:136`). VERIFIED (contract #1 stands).
- C8 Contract #3 (crew → sovereign worker web-access). `_clean_link` reads
  `label, hermes_url|url|dashboard_url, title, status, current, theme_label`,
  requires `url.startswith("https://")` (`arclink-crew/dashboard/plugin_api.py:39-49`;
  the https check is at :40, record said :41 — off-by-one, harmless). Producer
  keys built at `arclink_provisioning.py:842-855` MATCH. SEAM NUANCE below (S1).
  VERIFIED on keys.
- C9 Terminal root-gate: `_runtime_user_safe()` (`:304-307`) feeds `available`
  (`:1080-1082`); `create_session` rejects 503 when `not available`
  (`:1162-1164`) — so root-gating IS enforced on create, not merely reported.
  Record cite `:304-307` is incomplete (omits enforcement site) but the claim
  holds. Terminal `/status` placeholders `[workspace]`/`[hermes-state]`,
  version 0.4.0 (`:1087,1091,1093`); plugin.yaml + manifest both 0.4.0. Error
  strings redacted via `_redact_text` (`:753,796,870,1060,1323,1359`). VERIFIED.
- C10 Code confirm-gates `payload.get("confirm") is not True`→400 at
  `:1559,1602,1612,1862`; Linked git-mutation 403 (`:1092-1093`); `_run_git`
  `git -C` confined, FileNotFound→503, Timeout→504 (`:1113-1129`). VERIFIED.
- C11 Managed-context hooks register `pre_llm_call`/`pre_tool_call` + optional
  `/start` (`:1903-1912`); `_pre_llm_call` kwargs `:1666-1675` and returns
  `{"context":…}`/`None` (`:1713,1716,1729`); `_pre_tool_call` blocks on non-dict
  args (`:1844-1848`), blocks on missing token (fail-closed, `:1869-1877`), sets
  `args["token"]` (`:1879`); telemetry rotate at 1_000_000 bytes
  (`:576,1082-1092`). VERIFIED.
- C12 WebDAV dead code: `_dav_request` hard-raises 501 (`:1563`),
  `_nextcloud_surface` returns `available:False` (`:503-510`). VERIFIED.
- C13 Drift: README omits `arclink-crew` (`README.md:5-12`), workspace fallback is
  `_hermes_home()/"workspace"` not `$HOME` (`drive:549-553`). Terminal version
  unification 0.4.0. VERIFIED.

---

## NEW GAPS (neither record nor prior docs name)

- G1 [HIGH] Token-injection set is NOT a superset of token-requiring,
  agent-advertised MCP tools (`pod_comms.list/send/share-file`, `agents.register`
  use `validate_token`/registration token but are absent from
  `_TOKEN_TOOL_SUFFIXES`). See R1. Live break for agent-initiated `pod_comms.*`.
- G2 [LOW] Terminal `_clean_ssh_target`/`_SSH_TARGET_RE` are entirely dead;
  `ssh` mode is a local shell (`terminal:459-462,62,960-964`). See R3.
- G3 [LOW] Code `_run_git` returns raw git stderr in the 400 detail (`detail[:500]`,
  `code:1127-1128`) with NO redaction (code plugin has no `_redact_text`), so a
  git error can echo the absolute repo path to the client. The record's self-check
  #4 only checked terminal for path leakage, not code.
- G4 [INFO] Drive `/status` deliberately returns the REAL absolute `local_root`
  path (`drive:1697`) plus nextcloud mount metadata, while terminal hides paths
  behind placeholders. The record asserts terminal "never leaks the real workspace
  path" but does not note drive's `/status` freely exposes it (by design;
  authenticated surface, so INFO only).
- G5 [LOW] `_GIT_TIMEOUT_SECONDS = 15` documented as 30 in the record (R2).

---

## SEAM MISMATCHES

- S1 Contract #3 producer chain is mischaracterized. The record cites
  `arclink_sovereign_worker.py:1787-1788` as if the worker builds/writes the crew
  entries. In reality the worker only round-trips them: it reads
  `intent["environment"]["ARCLINK_CREW_DASHBOARDS_JSON"]`, `json.loads` it, and
  writes verbatim into `crew_dashboards` (`arclink_sovereign_worker.py:1763-1764,
  1787`). The actual producer is `arclink_provisioning.py:842-855` →
  `json.dumps(..., "ARCLINK_CREW_DASHBOARDS_JSON")` (`arclink_provisioning.py:1594`)
  → worker deserialize. Keys still match end-to-end, so the contract is valid, but
  the record's producer citation omits the env-var hop and the json round-trip
  (a place where a malformed/oversized env value would be silently dropped at
  `:1765-1766`).
- S2 Contract #2 token seam: producer (`__init__.py:1879`, gated by
  `_TOKEN_TOOL_NAMES`) does NOT cover consumer `validate_token` call sites for
  `pod_comms.*`/`agents.register` (`arclink_mcp_server.py:1094,1989`). See R1.

---

## RISK RE-CALIBRATION

- Record RISKS that I CONFIRM: sync fail-open (MEDIUM), YAML-by-regex no-backup
  (MEDIUM), drive denylist heuristic + strict=False TOCTOU-adjacent (LOW), crew
  silent drop on non-https/empty url (LOW), WebDAV dead surface (INFO),
  managed-context fail-closed on missing token (INFO). All fairly rated.
- MIS-CALIBRATION: the record buried the `_TOKEN_TOOL_NAMES`-not-a-superset issue
  in "OPEN FOR CODEX" (effectively unrated) while stamping contract #2
  both-ends-verified. It is a real HIGH-severity seam break for agent-initiated
  `pod_comms.*`, not a research to-do.

confirmedRiskCount (record risks I re-confirmed unchanged): 6
