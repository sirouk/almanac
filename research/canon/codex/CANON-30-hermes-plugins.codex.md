<<<CODEX-VERDICT-START CANON-30>>>
## CANON-30 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: Core CANON-30 holds, but the MCP token-injection seam is still understated: `pod_comms.*` plus `ssot.approve`/`ssot.deny` are broken; `agents.register` is a separate registration-token path.
### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- REFINE S2/A21/B47 token seam: `_TOKEN_TOOL_NAMES` covers only the 22 suffixes at `plugins/hermes-agent/arclink-managed-context/__init__.py:276-302`; it omits `pod_comms.list/send/share-file` even though those schemas use `AGENT_TOKEN_PROP` at `python/arclink_mcp_server.py:397-422` and dispatch validates `arguments["token"]` at `python/arclink_mcp_server.py:1093-1128,2200-2207`.
- REFINE S2/A21/B47 further: Claude missed `ssot.approve`/`ssot.deny`; they are advertised at `python/arclink_mcp_server.py:109-110`, use `AGENT_TOKEN_PROP` at `python/arclink_mcp_server.py:464-479`, and validate token at `python/arclink_mcp_server.py:2614-2635`.
- REFUTE the `agents.register` part of the token-injection dispute: its schema uses `REGISTRATION_TOKEN_PROP`, not `AGENT_TOKEN_PROP`, at `python/arclink_mcp_server.py:275-288`; dispatch passes `raw_token=arguments["token"]` at `python/arclink_mcp_server.py:1989-1994`.
- CONFIRM code git timeout correction: timeout is `15`, not 30, at `plugins/hermes-agent/code/dashboard/plugin_api.py:103,1113-1120`.
- CONFIRM MEDIUM sync fail-open: missing external `skills_sync.py`/`skills` exits 0 after a skip notice at `bin/sync-hermes-bundled-skills.sh:28-36`.
- CONFIRM MEDIUM regex/no-backup config editor: regex indentation parsing and direct rewrites occur at `bin/install-arclink-plugins.sh:74-99,191-209,165,259,370,454`.
- CONFIRM MEDIUM raw git stderr exposure: `_run_git` raises HTTP 400 with unredacted `stderr/stdout[:500]` at `plugins/hermes-agent/code/dashboard/plugin_api.py:1126-1128`.
- CONFIRM share-request broker seam: Drive/Code emit contract payloads at `plugins/hermes-agent/drive/dashboard/plugin_api.py:919-988` and `plugins/hermes-agent/code/dashboard/plugin_api.py:675-744`; hosted API consumes header/body at `python/arclink_hosted_api.py:1732-1759`; broker token HMAC compare is at `python/arclink_api_auth.py:2448-2478`.
- REFINE crew producer seam: worker writes `crew_dashboards` at `python/arclink_sovereign_worker.py:1763-1788`, but the actual entries are built in `python/arclink_provisioning.py:842-855` and serialized into `ARCLINK_CREW_DASHBOARDS_JSON` at `python/arclink_provisioning.py:1594`.
### New findings both Claude passes missed (severity + path:line)
- HIGH: token injection also misses `ssot.approve`/`ssot.deny`, not just `pod_comms.*`; see `plugins/hermes-agent/arclink-managed-context/__init__.py:276-302` vs `python/arclink_mcp_server.py:464-479,2614-2635`.
- LOW: plugin regression default list omits `arclink-crew`, so default-install tests would not catch losing the sixth default plugin; installer includes it at `bin/install-arclink-plugins.sh:13-21`, but test default list stops at `tests/test_arclink_plugins.py:20-26` and helper checks only that tuple at `tests/test_arclink_plugins.py:161-166`.
- LOW: token-injection tests exercise a hand-picked subset and omit `pod_comms.*` plus `ssot.approve/deny`; covered tool names are enumerated at `tests/test_arclink_plugins.py:4038-4180`, while server exposure of `ssot.approve/deny` is only text-checked at `tests/test_deploy_regressions.py:3833-3838`.
### Claude citations re-confirmed or corrected
- Reconfirmed installer argv/default/copy/hooks/config paths at `bin/install-arclink-plugins.sh:4-21,569-659`; workspace wrapper at `bin/install-hermes-workspace-plugins.sh:4-18`.
- Reconfirmed Drive confinement/sensitive checks at `plugins/hermes-agent/drive/dashboard/plugin_api.py:589-614,1040-1052,1168-1191`; root selection filters sensitive roots at `plugins/hermes-agent/drive/dashboard/plugin_api.py:682-686`.
- Reconfirmed terminal `ssh` mode is local-shell cosmetic: mode accepted at `plugins/hermes-agent/terminal/dashboard/plugin_api.py:454-463`, but runtime argv returns `[shell,"-i"]` at `plugins/hermes-agent/terminal/dashboard/plugin_api.py:958-964`.
- Corrected broad “git mutations require confirm”: discard/pull/push/trash do at `plugins/hermes-agent/code/dashboard/plugin_api.py:1556-1563,1599-1615,1859-1863`; stage/unstage/commit/gitignore mutate without confirm at `plugins/hermes-agent/code/dashboard/plugin_api.py:1525-1553,1575-1596`.
### Residual disagreement with the Claude half (for final reconciliation)
- Remove `agents.register` from the managed-context bootstrap-token seam; keep it as registration-token flow. Add `ssot.approve`/`ssot.deny` to the HIGH token-superset break.
- External Hermes `tools/skills_sync.py` remains unratifiable from this repo; public code only proves the caller contract and fail-open skip at `bin/sync-hermes-bundled-skills.sh:28-36,48-51`.
<<<CODEX-VERDICT-END CANON-30>>>
