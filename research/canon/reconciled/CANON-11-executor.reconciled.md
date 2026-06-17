# CANON-11 — Executor — Federation Reconciliation

**Piece:** CANON-11 (Executor) — `python/arclink_executor.py` (2947 lines, sole `*executor*` source)
**Adjudicator:** Claude Opus 4.8 (1M) — final federation adjudicator. Method: every disputed point re-opened in code; code wins over comment/name/prior claim.
**Codex (GPT-5.5 xhigh) sign-off:** `OBJECT(7)` — "core executor/broker/path gating real, but record overstates live provider execution: Chutes/Stripe clients not production-wired, Cloudflare Access/rollback apply are no-ops, materialization edges need refinement."
**Federation sign-off:** `BOTH-MODEL-AGREED`

The Codex OBJECT is sustained on the merits. After re-opening the code I confirm: the live Chutes/Stripe path raises before any provider mutation because production never injects the clients; `cloudflare_access_apply` and `rollback_apply` return `status="applied"` with no external side effect; and several materialization edges (non-atomic env/compose writes, unconstrained local volume bind sources, secret-target aliasing) hold in code. These refine — but do not overturn — the Claude record's core verdict. Both models agree on the reconciled truth below; no point is left unsettled by code.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Disputed point | Winner | Deciding cite (my re-open) |
|---|----------------|--------|----------------------------|
| 1 | Mutators live-gated; dry-run is the sole ungated method | both (ratify) | `arclink_executor.py:876` (dry-run no gate) vs `:891,950,1032,1155,1179,1197,1313,1427` (all gate first) |
| 2 | Broker wire contract matches byte-for-byte | both (ratify) | producer `:796-813`; server `arclink_deployment_exec_broker.py:96-99,108-114,117-120,291-295` |
| 3 | `operation_conn` durable idempotency inert in production | both | factory returns `ArcLinkExecutor(config,secret_resolver,docker_runner)` only `:142`; all 4 prod ctors (`:96,142`, `action_worker.py:2306`, `sovereign_worker.py:1333`) omit `operation_conn`; helpers no-op on `None` `:2708,2730,2755,2781` |
| 4 | "double-execute Stripe/Chutes is a CURRENT production risk" | codex | live non-fake path raises on missing client BEFORE any provider call: `:1204-1205`, `:1327-1328`; client never injected (no `chutes_client=`/`stripe_client=` ctor anywhere — grep returns only `self.x=` at `:857`). Risk is conditional on FUTURE client wiring. |
| 5 | "`arclink_operation_idempotency` table written ONLY by tests" (record line 59/71) | codex | table IS production-used: `arclink_inventory.py:746,759,824,876` and `arclink_pod_migration.py:1006,1079,1167,1189`. Dead path is specifically `ArcLinkExecutor.operation_conn`, not the table. |
| 6 | Live Docker (local/SSH) is root-equivalent (GAP-019) | both (ratify) | `:503,605`; root bind-prepare `docker run --user root` `:2384-2407` |
| 7 | Lifecycle project-override lets the project LABEL diverge but not the file paths | both | `:1879` `require_expected=...not allow_project_override`; `:1881-1894` `_validate_deployment_config_paths` still pins root to `_safe_deployment_root_prefix(request.deployment_id)` |
| 8 | Compose/DNS/lifecycle/access have no ArcLink-side replay ledger; only Chutes/Stripe attempt it | both (ratify) | `:890-947` (compose, no reserve/replay), `:1031-1052` (dns), `:1154-1194` (access); only chutes/stripe call `_reserve/_replay` `:1210,1332` |
| 9 | Cloudflare DNS upsert is find-then-create TOCTOU, no lock/idempotency key | both (ratify; Claude-verify G2 + Codex agree) | `_cloudflare_upsert_dns_records` GET-then-POST/PUT `:2538-2569`; raw `_cloudflare_request` `:2634-2655` |
| 10 | SSH `read_text_file`/`write_text_file` fail-open on omitted `allowed_root` | both (ratify; Claude-verify G3 + Codex agree) | `:702-708` containment only `if clean_allowed_root and not _remote_path_within(...)`; default `allowed_root=""`; prod callers pass non-empty `sovereign_worker.py:1780,1793` |
| 11 | Bind-prepare injection neutralized but symlink/TOCTOU remains | both | `$`-reject + `_IMAGE_REF_RE` `:2249`; `shlex.quote` `:2201`; `_remote_prepare_path_allowed` string-normalizes only, no `lstat` before chown/chmod `:2254-2263,2355-2412` |
| 12 | `cloudflare_access_apply` performs a real Cloudflare mutation | codex | `:1183-1194` returns `live=True,status="applied"` with NO `_cloudflare_request` call; no production import of `CloudflareAccessApplyRequest` (grep: zero) |
| 13 | `rollback_apply` performs a real mutation / has a production caller | codex (+ record already conceded no caller) | `:1431-1443` returns `status="applied"`, no subprocess/provider side effect; no production import of `RollbackApplyRequest` (grep: zero) |
| 14 | Atomic 0600 write claim applies to rendered env/compose/remote-prepare | codex | those use plain `write_text()+chmod` `:1991-1992,2006-2007,2015-2016`; `_write_private_file_atomic` `:1898` used only for secret temp files `:209` |
| 15 | Low risks (broker sends ignored keys; SSH TOFU; symlinked-secret-root cleanup) | both (ratify) | `:802-803` vs server `:111-113`; `accept-new` `:122,529`; symlinked-root unhandled `:2133-2136` |

---

## CONFIRMED Codex new-findings (re-verified true → net-new federation risks)

- **HIGH — Live Chutes/Stripe admin actions are not production-wired; non-fake actions raise before any provider mutation.** `chutes_key_apply`/`stripe_action_apply` raise `ArcLinkExecutorError` when the client is `None` (`:1204-1205`, `:1327-1328`). No production code constructs `ArcLinkExecutor(chutes_client=...)` or `(stripe_client=...)` — the only `chutes_client`/`stripe_client` assignment is `self.x =` in `__init__` `:857`, and `executor_for_fleet_host` `:142` never passes them. The sovereign teardown even guards on `getattr(executor,"chutes_client",None) is not None` (`sovereign_worker.py:1514`), which is therefore always `False` on non-fake adapters → chutes revoke reports `skipped_no_chutes_client` (`sovereign_worker.py:1392`). Net effect: live provider admin mutation is unreachable today; this also re-scopes the Claude HIGH (the double-execution hazard is latent, not current). CONFIRMED.

- **MEDIUM — `cloudflare_access_apply` is a no-op that reports success.** `:1183-1194` returns `live=True,status="applied"` without any `_cloudflare_request`/subprocess call; no production caller imports `CloudflareAccessApplyRequest`. The record's PIECE/VERDICT framing of "provider mutations (… Cloudflare Access …)" overstates the live surface. CONFIRMED.

- **MEDIUM — Local/broker compose apply creates arbitrary absolute bind-source directories from intent.** For non-SSH adapters `_compose_volume_root_mode` returns `"all"` `:2162-2165`, so `_ensure_volume_roots(services)` runs with `allowed_root=None` `:1981`; the containment `relative_to` is then skipped `:2182` and any absolute `volume.source` (kind != "file") is `mkdir(parents=True)`'d `:2189`. Config paths are contained but volume source roots are not. CONFIRMED (note: effect is directory creation from intent, not arbitrary file write).

- **LOW — Rendered `arclink.env`/`compose.yaml`/`remote-prepare.json` are non-atomic, non-locked `write_text()+chmod`.** `:1991-1992,2006-2007,2015-2016`. `_write_private_file_atomic` (flock+tmp+fsync+replace) is only used for secret temp files `:209`. The record's "atomic 0600 secret/file materialization with flock" generalizes a guarantee that holds only for secrets. CONFIRMED.

- **LOW — Duplicate compose secret targets can alias in the resolver.** `_materialize_compose_secrets` `:1759-1764` does not reject two secrets sharing the same `target`; `FileMaterializingSecretResolver.materialize` writes to `materialization_root / Path(clean_target).name` `:208`, so two distinct `secret_ref`s with the same `target` basename overwrite each other in the materialization root (last-writer-wins). CONFIRMED. (Note: the compose-tree copy at `_materialize_compose_secret_file` `:2101` keys on the unique secret NAME, so the aliasing is at the resolver layer, not the compose `secrets/` dir.)

## REJECTED Codex new-findings
- None. All five new findings re-verified true in code.

---

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Cite |
|------|------|----|------|
| Claude HIGH "durable idempotency inert → retried Stripe refund/cancel could double-execute against the provider" | HIGH (current double-execute hazard) | HIGH (re-scoped: latent — live client never injected, so non-fake path raises before any provider call; hazard activates only if/when a client is wired) | `:1204-1205,1327-1328`; no `chutes_client=`/`stripe_client=` prod ctor; `:142` |
| Record DRIFT bullet "`arclink_operation_idempotency` written ONLY by tests" | (claim) | FALSE — table is production-used by inventory + pod migration; only `ArcLinkExecutor.operation_conn` is dead | `arclink_inventory.py:746,759,824`; `arclink_pod_migration.py:1006,1079` |

No severity was raised or lowered beyond these two re-scopings; the MEDIUM/LOW/INFO risks in the record are correctly calibrated and ratified. The two CONFIRMED MEDIUMs (Access no-op, unconstrained local volume bind sources) are net-new and added to the ledger at MEDIUM.

---

## STANDING DISAGREEMENTS
None. Every material point reconciled to a single code-grounded truth. The bind-prepare and resolve-then-use-raw symlink/TOCTOU items (#11, and Claude self-check #4) are agreed by both models to be genuine host-local races that cannot be proven safe or unsafe from Python alone — but that shared agreement is itself the reconciled position, not a disagreement.

---

## FINAL BOTH-MODEL VERDICT
The Executor is a genuinely fail-closed (`_require_live_enabled` on every mutator except dry-run), dependency-injected step engine with strong code-enforced path containment for deployment config files (root/`arclink.env`/`compose.yaml`/`arclink-{id}` project), atomic 0600 **secret** materialization with flock, exception-time secret cleanup, topological service ordering with cycle detection, secret-redacted errors, and a broker wire contract verified byte-for-byte against CANON-12. The reconciliation sustains Codex's OBJECT: the **live provider-mutation surface is thinner than the record's prose implies** — live Chutes/Stripe raise before any provider call (clients never injected), `cloudflare_access_apply` and `rollback_apply` are success-reporting no-ops with no production callers, the durable idempotency ledger is dead on the executor's `operation_conn` (though the table itself is used elsewhere), rendered env/compose/remote-prepare files are non-atomic, and local/broker volume bind sources are unconstrained. The Claude HIGH stands but is re-scoped from a current double-execution hazard to a latent one. Net: a well-built, correctly-gated engine that **ships a richer live API than production wires or exercises**, with the strongest idempotency guarantee being the one production silently disables and the live provider-admin paths being either unreachable or no-ops today.

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-11-executor.fix.md`](../fixes/CANON-11-executor.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `bf7e201` committed.
- Summary: 9 fixed / 3 skipped / 3 needs-decision.
- Tests: 1 test file run, all pass (60/60); py_compile pass; git diff --check pass
- Representative fixes:
  - HIGH — wired production factory to inject `operation_conn` from `ARCLINK_DB_PATH`, with schema ensured. `python/arclink_executor.py:80`, `python/arclink_executor.py:158`
  - HIGH — live Chutes/Stripe provider actions now fail closed if an injected client lacks durable operation idempotency DB. `python/arclink_executor.py:1217`, `python/arclink_executor.py:1342`
  - MEDIUM — Cloudflare DNS upsert now serializes per zone/type/hostname with an advisory file lock around find-then-create/update. `python/arclink_executor.py:2563`, `python/arclink_executor.py:2603`
- Needs decision:
  - Live Chutes/Stripe admin clients are still not production-implemented/wired. Executor now requires durable DB before any injected client can run, but real Chutes key management and Stripe refund/cancel semantics need provider/product decisions.
  - Generic ArcLink replay ledger for compose/lifecycle/DNS beyond the DNS lock needs a contract decision; current compose apply keys can be reused across legitimate deployment updates, so naive replay would break re-apply flows.
  - SSH TOFU default (`StrictHostKeyChecking=accept-new`) left unchanged; tightening it would affect first-contact fleet bootstrap policy.
<!-- CANON-REPAIR-STATUS:END -->
