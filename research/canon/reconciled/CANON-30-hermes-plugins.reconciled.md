# CANON-30 — Hermes Plugins & Bridges — RECONCILED (both-model-signed)

- Piece: CANON-30 (Hermes Plugins & Bridges)
- Codex (GPT-5.5 xhigh) SIGN-OFF: **OBJECT(3)** — core holds; token-injection seam understated (pod_comms.* + ssot.approve/deny broken; agents.register is a separate registration-token path).
- Adjudicator: Claude Opus 4.8 final adjudicator. Method: re-opened every disputed cite in source; code wins over comment/name/prior claim.
- Federation SIGN-OFF: **BOTH-MODEL-AGREED**. Every material point reconciled to one code-grounded truth. No standing disagreements.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Point | Winner | Deciding cite |
|---|-------|--------|---------------|
| 1 | Token-injection seam (Contract #2) is broken: `_TOKEN_TOOL_NAMES` is NOT a superset of token-requiring, agent-advertised tools | **codex** (extends claude-verify) | `arclink-managed-context/__init__.py:276-302` (22 suffixes, no pod_comms/ssot.approve/deny) vs `arclink_mcp_server.py:397-422,464-479` (AGENT_TOKEN_PROP) + dispatch validate at `:1094,2615,2634`; advertised unconditionally at `:1787-1796`; plugin returns `None` (no token set) at `__init__.py:1843` |
| 2 | Scope of the break: which tools | **codex** | `pod_comms.list/send/share-file` (`mcp:1094,2200-2207`) + `ssot.approve`/`ssot.deny` (`mcp:2614-2644`) — all AGENT_TOKEN_PROP, all absent from suffix set |
| 3 | `agents.register` is part of the bootstrap-token seam break | **codex** (REFUTE) — claude-verify R1 wrongly included it | `arclink_mcp_server.py:275-288` uses `REGISTRATION_TOKEN_PROP`, dispatch `:1989-1994` passes `raw_token`; out of the AGENT_TOKEN_PROP seam |
| 4 | Contract #2 "BOTH-ENDS-VERIFIED: yes" stamp | **codex/claude-verify** (stamp is FALSE) | superset does not hold (cite #1); record itself listed superset as merely "OPEN FOR CODEX" while stamping yes — self-inconsistent |
| 5 | Code git subprocess timeout = 30s | **claude-verify/codex** (record WRONG: 15s) | `code/dashboard/plugin_api.py:103` (`_GIT_TIMEOUT_SECONDS = 15`), used `:1119` |
| 6 | "Code git mutations gate on `confirm is True`" (overbroad) | **codex** (REFINE) | confirm-gated: discard `:1559`, pull `:1602`, push `:1612`, trash `:1862`; NOT gated: stage `:1525-1534`, unstage `:1537-1553`, commit `:1575-1583`, gitignore `:1586-1596`. (`:1862` is `/ops/trash`, a filesystem op, not git.) Linked-403 still applies to all via `_resolve_writable_repo:1092-1093` |
| 7 | Crew producer is `arclink_sovereign_worker.py:1787-1788` | **codex/claude-verify** (REFINE) | worker only round-trips: reads `ARCLINK_CREW_DASHBOARDS_JSON`, json.loads, writes verbatim (`sovereign_worker:1763-1764,1787`). Real producer builds entries at `arclink_provisioning.py:842-855` and serializes at `:1594`. Keys still match end-to-end -> contract valid |
| 8 | Crew https check line cite (record `:41`) | **codex/claude-verify** (cite fix) | actual check at `arclink-crew/dashboard/plugin_api.py:40`; harmless off-by-one, no severity impact |
| 9 | Terminal `ssh` mode = local shell; SSH-target validator | **codex/claude-verify** (REFINE, stronger) | argv `[shell,"-i"]` at `terminal:958-964`; `_clean_ssh_target` `:459` / `_SSH_TARGET_RE` `:62` defined but never called (rg shows only defs) -> dead code |
| 10 | Broker-token auth gates the share route (record left OPEN) | **claude-verify/codex** (CONFIRM, resolves OPEN) | `_authenticate_share_request_broker` -> `_verify_proof_token_hash` uses `hmac.compare_digest` at `api_auth:255,257`; called from share route. Constant-time, real |
| 11 | Sync fail-open (MEDIUM) | **both** (CONFIRM) | `sync-hermes-bundled-skills.sh:28,34-37` exit 0 when runtime/skills absent |
| 12 | YAML-by-regex, no-backup (MEDIUM) | **both** (CONFIRM) | indent regex `install:84,92`; in-place `write_text` no backup `:165,259,370,454` |
| 13 | Share-request seam contract #1 holds end-to-end | **both** (CONFIRM) | producer drive `:919-988` + code `:675-744`; consumer `hosted_api:1732-1759` + `api_auth:3525-3534,3545-3549` |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (re-verified true in code -> net-new federation risks)

- **HIGH — token injection also misses `ssot.approve`/`ssot.deny`** (not just `pod_comms.*`). `__init__.py:276-302` lacks both; `arclink_mcp_server.py:464-479` declares `AGENT_TOKEN_PROP`; `:2614-2644` validates the token. Advertised at `:109-110` + unconditional `tools/list` `:1787-1796`. An enrolled agent that omits the token (as the schema instructs) reaches the server with `token==""` and `validate_token("")` fails -> live break. This MERGES with claude-verify R1/G1; the federation HIGH break is the union: `pod_comms.list/send/share-file` + `ssot.approve` + `ssot.deny`.
- **MEDIUM — raw git stderr exposed unredacted** (Codex CONFIRM of claude-verify G3). `code/dashboard/plugin_api.py:1126-1128` raises HTTP 400 with `detail[:500]` from raw `result.stderr`; code plugin has no `_redact_text` (rg: only terminal defines it at `terminal:524`). A git error can echo the absolute repo path to the client.
- **LOW — default-install regression test omits `arclink-crew`.** Installer default set includes it (`install:13-21`); test `DEFAULT_PLUGIN_NAMES` stops at 5 (`tests/test_arclink_plugins.py:20-26`); helper only checks that tuple (`:161-166`). Dropping the 6th default plugin would not be caught.
- **LOW — token-injection tests omit `pod_comms.*` + `ssot.approve/deny`.** Covered names enumerated at `tests/test_arclink_plugins.py:4038-4180` (notion/knowledge/vault/ssot.write/preflight/status/shares/academy only); server exposure of `ssot.approve/deny` is merely text-checked at `tests/test_deploy_regressions.py:3833-3838`. No test guards the seam, so the HIGH break above is invisible to CI.

### REJECTED

- **`agents.register` as part of the bootstrap-token-injection break** — REJECTED. Schema uses `REGISTRATION_TOKEN_PROP` (`arclink_mcp_server.py:275-288`), dispatch passes `raw_token=arguments["token"]` (`:1989-1994`). It is a registration-token flow, correctly NOT in `AGENT_TOKEN_PROP`. claude-verify R1 wrongly included it; Codex's REFUTE wins.

---

## SEVERITY CHANGES (code-supported only)

| Risk | From | To | Cite |
|------|------|----|------|
| Token-injection seam not a superset (record buried it in "OPEN FOR CODEX", effectively unrated; Contract #2 stamped "BOTH-ENDS-VERIFIED: yes") | UNRATED / "yes" | **HIGH** | `__init__.py:1843,276-302` vs `arclink_mcp_server.py:1094,2615,2634`; scope = pod_comms.* + ssot.approve + ssot.deny |
| Raw git stderr path leak in code `/git/*` 400 detail | not in record | **MEDIUM** (net-new) | `code/dashboard/plugin_api.py:1126-1128` (no `_redact_text` in code plugin) |
| Code git timeout doc fact | "30s" (record) | corrected to **15s** (fact, not a risk) | `code/dashboard/plugin_api.py:103` |

All record-original risks (sync fail-open MEDIUM, YAML-by-regex no-backup MEDIUM, drive denylist + strict=False TOCTOU-adjacent LOW, crew silent-drop LOW, WebDAV dead surface INFO, managed-context fail-closed-on-missing-token INFO) are re-confirmed at their original severities.

---

## STANDING DISAGREEMENTS

None. Every material point reconciled to one code-grounded truth.

Note (not a disagreement): the external Hermes `tools/skills_sync.py` consumer and the external Hermes config.yaml / `_pre_llm_call` runtime consumer remain unratifiable from this repo — both models agree these are runtime-only seams (BOTH-ENDS-VERIFIED: no, correctly marked in the record). The repo only proves the caller contract and the fail-open skip (`sync-hermes-bundled-skills.sh:28-37,48-51`).

---

## FINAL BOTH-MODEL VERDICT

CANON-30 provably does its job: the six native plugins are real and structurally consistent; the installer rsyncs them, removes legacy variants, wires `config.yaml`, renders themes, and installs the telegram-start hook. Share-request broker seam (CANON-02, contract #1) and the crew switcher seam (CANON-08/19, contract #3) are both-ends-verified, including constant-time broker-token auth.

The one material correction both models force: **Contract #2 (managed-context token injection -> MCP rail) is NOT both-ends-verified.** `_TOKEN_TOOL_NAMES` omits `pod_comms.list/send/share-file`, `ssot.approve`, and `ssot.deny` — all advertised to enrolled agents with `AGENT_TOKEN_PROP` ("omit; the plugin fills it") and all validating the token server-side. The plugin returns `None` without setting `args["token"]` for these, so an agent that follows the schema fails closed at the server (`validate_token("")`). This is a **HIGH** live seam break, uncaught by CI. `agents.register` is correctly excluded (registration-token path).

Secondary confirmed facts: code git timeout is **15s** (not 30s); code `/git/*` leaks raw git stderr (incl. absolute paths) unredacted (**MEDIUM**); `stage/unstage/commit/gitignore` mutate without a confirm gate (Linked-403 still applies); terminal `ssh` mode is a cosmetic local shell with fully dead target-validation code; the crew producer is `arclink_provisioning.py:842-855` + the `ARCLINK_CREW_DASHBOARDS_JSON` env hop, not the worker.

**FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-30-hermes-plugins.fix.md`](../fixes/CANON-30-hermes-plugins.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `c5cec97` committed.
- Summary: 8 fixed / 5 skipped / 2 needs-decision.
- Tests: 2 focused test files run, both pass; `bash -n deploy.sh bin/*.sh test.sh` pass; `py_compile` pass; `git diff --check` pass. Note: bare `python3 tests/test_arclink_plugins.py` hit sandbox tmux `Operation not permitted`; rerun with `TERMINAL_DISABLE_TMUX=1` passed.
- Representative fixes:
  - HIGH — managed-context now injects bootstrap tokens for `pod_comms.list/send/share-file` and `ssot.approve/deny`; `agents.register` remains excluded as registration-token flow — plugins/hermes-agent/arclink-managed-context/__init__.py:288
  - MEDIUM — Code git 400 details now redact repo/workspace/home paths and `token/password/secret/key=` fragments before returning stderr/stdout — plugins/hermes-agent/code/dashboard/plugin_api.py:286, plugins/hermes-agent/code/dashboard/plugin_api.py:1141
  - MEDIUM — bundled Hermes skills sync now fails closed when runtime skills source is missing, with explicit opt-out only for development no-op runs — bin/sync-hermes-bundled-skills.sh:34
- Needs decision:
  - Full replacement of installer regex/indentation YAML edits with a comment-preserving YAML parser. I added backups, but parser replacement needs dependency/formatting policy because current tests intentionally preserve comments and future nested config.
  - Full Drive denylist/TOCTOU redesign. I fixed the empty-root guard, but complete mitigation likely needs fd-anchored file operations or an allowlist policy that changes file-manager behavior.
<!-- CANON-REPAIR-STATUS:END -->
