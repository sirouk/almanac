# CANON-19 — Hermes Workspace & Dashboard — RECONCILED (both-model truth)

- Piece: CANON-19 (Hermes Workspace & Dashboard)
- Codex sign-off: **OBJECT(5)** — GPT-5.5 xhigh
- Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation
- Federation sign-off: **BOTH-MODEL-AGREED**
- Method: every disputed point re-opened in the live tree (Read/grep/sed). Code wins over any name, comment, or prior claim.

The Claude record is a competent, largely code-accurate map of the read-model/queue/proxy
mechanics (C1–C14 reconfirmed by both the verifier and Codex). Its one decisive error — declaring
the auth-proxy SSO path "dead code" — is overturned by both the Claude verifier and Codex, and
confirmed false by direct re-walk of the producer chain. Two net-new dashboard defects from Codex
(provider-hardcode; idempotency race) and one from the verifier (config.yaml dual-writer) are
confirmed. No standing disagreements remain.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Disputed point | Winner | Deciding cite (re-opened by adjudicator) |
|---|----------------|--------|------------------------------------------|
| 1 | "SSO cookie path is dead/dormant; no in-repo producer writes the SSO secret" (record DRIFT#1 / seam#6 / INFO risk) | **codex + claude-verifier (record REFUTED)** | `bin/install-deployment-hermes-home.sh:94-99,163,169-171` writes `sso_session_secret`/`sso_subject` into `arclink-web-access.json`; fed by `bin/arclink-docker.sh:1676-1698` (`sso_secret_for_subject`); consumed live at `python/arclink_dashboard_auth_proxy.py:674-693,701`. SSO is REACHABLE. |
| 2 | SSO is a live cross-deployment, per-user, domain-scoped auth surface | **codex + claude-verifier** | SSO cookie name digest keyed ONLY on `_sso_subject`(user_id)+`sso_session_secret`, NOT deployment/prefix/target (`auth_proxy.py:574-583`); contrast session cookie which includes deployment/prefix/target (`:560-572`). Secret reused per user across siblings (`arclink-docker.sh:1680-1698`). `Path=/; Domain=<base_domain>` (`auth_proxy.py:733-735`). Cross-deployment within one user/Captain CONFIRMED. |
| 3 | SSO severity: INFO (record) vs MEDIUM/HIGH (verifier) vs MEDIUM-not-HIGH (codex) | **codex (MEDIUM)** | Subject = `user_id` (`arclink-docker.sh:1672-1673`); reach is the SAME user's own fleet of sibling dashboards, not a cross-tenant boundary. Fleet-wide SSO is intended; blast radius is one tenant. MEDIUM, not HIGH. |
| 4 | Seam #7 producer argv includes `--agent-title` | **codex + claude-verifier (record overstated)** | `arclink_enrollment_provisioner.py:1409-1422` (full) and `:1579-1589` (identity-only) send NO `--agent-title`; defaults to `""` (`arclink_headless_hermes_setup.py:638-639`). Harmless in effect, but "BOTH-ENDS-VERIFIED yes" on that key is invalid. |
| 5 | `_safe_json` "calls reject_secret_material" citation chain | **both (substance holds, citation refined)** | `dashboard.py:777` calls `json_dumps_safe`, which calls `reject_secret_material` at `arclink_boundary.py:72`. Secret-reject guarantee on queue metadata holds; record skipped one hop. |
| 6 | Seam #10 backup deploy-key has a CANON-22 consumer | **codex (REFINE — no consumer)** | No script reads `backup_deploy_key_private_ref`/`server_state:agent-backup-deploy-key:`. Worker only records `failed_closed` (`arclink_action_worker.py:954-978`). Shipped backup uses a SEPARATE key `AGENT_BACKUP_KEY_PATH=$HOME/.ssh/arclink-agent-backup-ed25519` from `arclink-agent-backup.env` (`bin/backup-agent-home.sh:18,39`, `bin/configure-agent-backup.sh:36,243`). The staged deploy key is an ORPHANED rail. Resolves record OPEN#3. |
| 7 | `request_arclink_backup_write_check` never runs git (DRIFT#2) | **both (CONFIRM)** | Ownership check then unconditional `record_arclink_backup_write_check_failed_closed` (`dashboard.py:1379-1383`); worker side also `failed_closed` only (`action_worker.py:973`). |
| 8 | `build_scale_operations_snapshot` env-coupling scope | **codex + claude-verifier (REFINE — broader)** | Reads `os.environ` at `dashboard.py:705-706,715,748` AND calls `admin_action_execution_readiness()`/`control_node_provisioning_readiness(conn)` without env injection at `:701-702`. Coupling broader than record's framing. Severity MEDIUM (held). |
| 9 | Idempotency: record "same tuple returns existing row" vs concurrent-replay behavior | **both (record correct for serial; codex adds race)** | SELECT-then-INSERT (`dashboard.py:2359-2362,2376`) with no txn between; UNIQUE partial index `idx_arclink_action_intents_idempotency` `WHERE idempotency_key != ''` (`control.py:2269-2271`). Serial replay returns existing row (record correct); concurrent same-key replay raises IntegrityError instead of returning the row (codex LOW correct). Compatible truths. |
| 10 | `queue_arclink_admin_action` validation gauntlet + audit + worker CAS consume | **both (CONFIRM)** | `dashboard.py:2339-2410` (validation/INSERT/audit/backfill/commit); worker consumes `WHERE status='queued'` then CAS `UPDATE ... status='running' ... WHERE ... status='queued'` (`action_worker.py:461-462,474-480`). |
| 11 | Read models SELECT-only and secret-safe | **both (CONFIRM)** | `read_arclink_user_dashboard`/`read_arclink_admin_dashboard` bodies have no INSERT/UPDATE/DELETE/commit; Chutes enrichment emits state names only (`dashboard.py:1743-1763`). |
| 12 | Auth: signed-token checks, CSRF fail-closed, access fail-closed, token-secret fallback | **both (CONFIRM)** | `_valid_token` HMAC+aud+sub+scope+iat/exp (`auth_proxy.py:642-654`); CSRF fail-closed (`:1104-1114`); load fail-closed (`:699-700`); `_token_secret` sha256 fallback when `session_secret` blank (`:86-98`). MEDIUM fallback risk held; producers always set `session_secret` (`agent_access.py:524`, `install-deployment-hermes-home.sh:91`). |
| 13 | Seam #6 port-key producer (prior B36 sub-question) | **codex (REFINE — informational)** | Shared-host producer `ensure_access_state` emits `dashboard_backend_port`/`dashboard_proxy_port` (`agent_access.py:524-525`); `install-agent-user-services.sh:285-286` hard-subscripts them; Docker installer only preserves via `**existing` (`install-deployment-hermes-home.sh:164`). Two producers populate different key subsets. No CANON-19 defect; seam-map refinement. |

CONFIRM items where both models already agreed (ratified, not deep-rechecked): record C1–C14
verifier reconfirmations of queue validation, worker CAS, cookie attrs, Nextcloud `OC_PASS` gate,
skill-enablement atomic line surgery, login throttle process-locality, liveness-file trust.

---

## CONFIRMED Codex new-findings (now net-new federation risks)

1. **MEDIUM — User dashboard hardcodes provider to default Chutes.** `read_arclink_user_dashboard`
   calls `primary_provider({})` with an EMPTY mapping (`dashboard.py:1737`); `primary_provider`
   resolves `ARCLINK_PRIMARY_PROVIDER` against that empty map, finds nothing, returns the default
   `"chutes"` (`arclink_product.py:14-21,87-88`). So `provider == "chutes"` is ALWAYS true and the
   Chutes boundary enrichment (`dashboard.py:1743-1763`) runs even for Codex/Anthropic/custom
   deployments. Per-deployment provider is never consulted in this read model. Secret-safe (only
   state names emitted), but the model card mislabels provider/credential semantics for non-Chutes
   agents. CONFIRMED in code.

2. **LOW — `queue_arclink_admin_action` idempotency race.** SELECT-then-INSERT without a txn
   between the two (`dashboard.py:2359-2362,2376`); the UNIQUE partial index
   (`control.py:2269-2271`) prevents a duplicate ROW but a concurrent same-key replay raises
   `IntegrityError` rather than returning the existing row — the idempotent-return contract is not
   honored under concurrency. CONFIRMED.

3. **LOW — Operator snapshot ignores credential-env alternates.** `build_operator_snapshot`
   computes blockers by checking `step.required_env` directly against `env_source`
   (`dashboard.py:548`), with no awareness of `_ENV_ALTERNATES` (`CLOUDFLARE_API_TOKEN` →
   `CLOUDFLARE_API_TOKEN_REF`) honored by the canonical journey credential check
   (`arclink_live_journey.py:53-61,64-71`). Result: a false-positive `CLOUDFLARE_API_TOKEN` blocker
   in the operator snapshot when only the `_REF` alternate is set. Read-model accuracy bug, operator
   surface only. CONFIRMED (Codex framed as CANON-23→19 seam; net-new defect).

## CONFIRMED verifier new-finding (net-new federation risk)

4. **MEDIUM — config.yaml dual-writer with incompatible strategies, no lock.**
   `arclink_headless_hermes_setup.py` mutates `config.yaml` via `load_config()` + `save_config()`
   (full YAML load-and-re-dump, `:84,90,254,565,599`); `arclink_skill_enablement.py` mutates the
   SAME file via byte-preserving line surgery that assumes byte-stable block-style YAML
   (`:95,118-148,122`). Neither module takes any flock/fcntl lock (grep: zero lock primitives).
   Headless runs at install/refresh; skill-enablement runs every 4h + on `.path` activation. An
   interleave would let the re-dump normalize formatting the line-surgery depends on. CONFIRMED.
   Codex CONFIRM + verifier G1 agree.

## REJECTED Codex/verifier new-findings

(none — all four net-new findings re-verified true in code)

---

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Deciding cite |
|------|------|----|---------------|
| Auth-proxy SSO cookie path | INFO ("dead code") | **MEDIUM** | Live producer chain (`install-deployment-hermes-home.sh:163,169-171`; `arclink-docker.sh:1676-1698`) + live consumer (`auth_proxy.py:674-693,701`); cross-deployment within one user (`auth_proxy.py:574-583`). MEDIUM (not HIGH): reach bounded to the same user's own fleet, subject=`user_id` (`arclink-docker.sh:1672`). |

Held (no change): `_token_secret` fallback (MEDIUM), backup deploy-key persistence/no-rotation
(MEDIUM), scale-snapshot env leak (MEDIUM, scope refined broader), provider-hardcode (new MEDIUM),
config.yaml dual-writer (new MEDIUM), `stripe_customer_id` exposure (LOW), process-local throttle
(LOW), env-derived URLs (LOW), idempotency race (new LOW), operator-snapshot alternate-env
(new LOW), liveness-file trust (INFO).

---

## STANDING DISAGREEMENTS

None. Every material point reconciled to a single code-grounded truth. The only severity spread
(verifier MEDIUM/HIGH vs Codex MEDIUM) is settled by code: the SSO subject is the `user_id` and the
cross-deployment reach is the same user's own fleet, not a cross-tenant escalation — MEDIUM is the
code-supported rating.

---

## FINAL BOTH-MODEL VERDICT

CANON-19 **provably does its job** as a read-model + provisioning surface, with both models in
agreement after reconciliation:

STRENGTHS (code-verified, both models): (1) the two dashboard read models are strictly SELECT-only
and secret-safe; (2) `queue_arclink_admin_action` is a correct idempotent producer with a full
validation gauntlet and a UNIQUE-index-backed contract, both ends of the action-worker seam matched
(CAS consume); (3) the auth proxy is a genuine HS256 signed-session boundary (HttpOnly/Secure,
Origin/Referer CSRF fail-closed, fail-closed access load, managed-lifecycle 409); (4) headless
seeder and skill-enablement are atomic-write and fail-closed.

CORRECTED / NET-NEW (federation): the SSO cookie path is **LIVE in Docker/domain mode, not dead**
(record's single largest error, now MEDIUM, cross-deployment within one user's fleet); the backup
deploy-key staged in this module has **no consumer** (orphaned rail; shipped backup uses a separate
key); the user dashboard **hardcodes provider to Chutes** (`primary_provider({})`), running Chutes
enrichment for all providers (MEDIUM); `queue_arclink_admin_action` has a **concurrent-replay race**
that raises instead of returning the existing row (LOW); the **operator snapshot ignores
`CLOUDFLARE_API_TOKEN_REF`** alternate (false-positive blocker, LOW); and **two sibling modules write
the same config.yaml** with incompatible strategies and no lock (MEDIUM).

Federation sign-off: **BOTH-MODEL-AGREED.**
