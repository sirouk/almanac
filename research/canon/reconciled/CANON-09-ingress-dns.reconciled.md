# CANON-09 — Ingress & DNS — RECONCILED (both-model truth)

- Piece: CANON-09 (Ingress & DNS) — sole tracked code member `python/arclink_ingress.py` (284 lines)
- Claude record: research/canon/sections/CANON-09-ingress-dns.md
- Claude adversarial verify: research/canon/verify/CANON-09-ingress-dns.verify.md
- Codex (GPT-5.5 xhigh) verdict: research/canon/codex/CANON-09-ingress-dns.codex.md
- **Codex SIGN-OFF: OBJECT(2)** (one severity refine + one new MEDIUM finding)
- **Adjudicator: Claude Opus 4.8 (1M).** Method: every disputed/new/REFINE point re-opened in code (Read/rg/sed). Code wins over comment/name/prior claim.
- **FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.** Every material point reconciled to one code-grounded truth. No standing disagreements survive: Codex's prefix-collision REFINE is code-correct AND Claude's underlying mechanical observation is code-correct — they reconcile to one statement (real latent gap, reachability gated by CANON-08 prefix reservation -> LOW). Both new Codex findings re-verified.

---

## RESOLUTION TABLE (disputed / REFINE / new — each re-decided by adjudicator)

| Point | Winner | Deciding cite (adjudicator re-opened) |
|---|---|---|
| Desired DNS = dashboard/hermes CNAME + proxied=True; files/code filtered | both | ingress.py:39-43,19,42; adapters.py:228-239 |
| Live provisioning seam (desired -> intent projection -> persist) | both | provisioning.py:1487-1494, **1744-1752** (Codex correction over Claude `~1505`); sovereign_worker.py:1981-1992 |
| Three `cloudflare`-object wrappers have ZERO production callers (dead/divergent API) | both | rg over python/+bin/ non-test/non-def = empty (exit 1); ingress.py:114,192,207 |
| Dead-API-surface severity: MEDIUM vs operational-LOW | both (reconciled) | Wrappers are pure dead code (no prod reachability); MEDIUM stands ONLY as doc-trust/clarity hazard, operational risk LOW. ingress.py:114,192,207; tests/test_arclink_ingress.py:49,86,122 |
| `_mark_dns_status` bulk-clobbers ALL rows for a deployment (teardown after partial apply) | both | ingress.py:145-148 (`WHERE deployment_id = ?` only); sovereign_worker.py:1365 |
| Prefix-collision -> unhandled DNS-index IntegrityError in persist | codex (Claude obs. code-true, reachability refined) | NO `DELETE FROM arclink_deployments`/`arclink_dns_records` anywhere in python/ (rg=0); prefix reserved once via UNIQUE `idx_arclink_deployments_prefix` (control.py:1947-1948), never deleted/mutated; reuse rejected at reserve (control.py:3614-3615) BEFORE persist. DNS index global no-WHERE (control.py:2077-2078); persist only `ON CONFLICT(record_id)` (ingress.py:78). -> real but bypass/corruption-only -> LOW |
| `provider_record_id` is out-of-piece state (read in teardown, never written by ingress) | both | ingress.py:74-77 (no col in INSERT), 174-186 (read); sovereign_worker.py:2011-2023 writes it from executor.py:1174 |
| Live teardown over-reports attempted hostnames as "removed" on silent no-op | both | executor.py:1045 (returns attempted hostnames), 2588-2589 (silent `continue` when not found); ingress.py:166-168 records them as torn down |
| `proxied` applied live from intent but never persisted; no live persisted-proxied drift detector | both | executor.py:2515,2555; ingress.py:74-77 (not a column); adapters.py:202-210 (only test-only FakeCloudflareClient.drift compares it) |
| `provision_arclink_dns` retry catches bare `except Exception` | both | ingress.py:221-231 (dead code; impact academic) |
| `created_at` written on INSERT only, not on conflict-update | both | ingress.py:74-91 (conflict update sets last_checked_at + updated_at; not created_at) — Claude verify already flagged as minor imprecision; Codex correction ratified |

## CODEX CONFIRM ITEMS (ratified, both models already agreed)
- Desired-records role set + CNAME/proxied — ratified (ingress.py:35-43; adapters.py:228-238).
- Live provisioning seam — ratified (provisioning.py:1487-1494,1744-1752; sovereign_worker.py:1981-1992).
- Dead/divergent API surface exists — ratified (ingress.py:114,192,207; importers provisioning.py:25, action_worker.py:31, sovereign_worker.py:67 pull only desired/render/persist/read/mark).
- Bulk status clobber — ratified (ingress.py:145-148; sovereign_worker.py:1365-1377).
- provider_record_id out-of-piece — ratified (ingress.py:74-77,174-186; sovereign_worker.py:2011-2023).
- Teardown over-reports (== Claude verify GAP-B) — ratified (executor.py:1041-1050,2584-2589; ingress.py:166-168).
- proxied not persisted, no live drift detector — ratified.
- Test-only retry catches all Exceptions — ratified (ingress.py:221-231).

## CONFIRMED CODEX NEW FINDINGS (re-verified true -> net-new federation risks)
1. **MEDIUM — `dns_repair` can apply DNS with NO DB tracking.** CONFIRMED. `_resolve_dns_repair` returns explicit DNS (action_worker.py:169-179) or computed DNS when no rows exist (action_worker.py:209-231); the `dns_repair` handler calls `executor.cloudflare_dns_apply` and returns at action_worker.py:880 with **no** `persist_arclink_dns_records`, **no** status/`provider_record_id` backfill (rg of action_worker.py shows only the apply call — none of those symbols present). Teardown reads only `arclink_dns_records` (ingress.py:171-189), so apply via the explicit-DNS or no-rows branch creates Cloudflare records untracked in the control DB; later row-driven teardown will not see them (relies on executor find-by-name fallback). Adds a new seam/risk to CANON-09's register. Cite: action_worker.py:168-179,209-231,858-880; ingress.py:171-189.
2. **INFO — Dead `teardown_arclink_dns` passes all 4 hostnames to the fake client.** CONFIRMED. `arclink_hostnames` returns dashboard/files/code/hermes (adapters.py:233-239); `teardown_arclink_dns` passes `list(hostnames.values())` — all 4 — to `cloudflare.teardown_records` (ingress.py:201-203), even though provisioning only ever creates dashboard/hermes. Harmless because the wrapper is non-production dead code. Cite: ingress.py:201-203; adapters.py:233-238.

## REJECTED CODEX NEW FINDINGS
- None. Both new findings re-verified true in code.

## SEVERITY CHANGES (code-supported only)
| Risk | From | To | Cite |
|---|---|---|---|
| Prefix-collision -> unhandled DNS-index IntegrityError (Claude verify GAP-A) | MEDIUM | LOW | Reachability gated by CANON-08 prefix reservation: prefix reserved once via UNIQUE index, never released/deleted (control.py:1947-1948,3614-3615); no DELETE of deployments/dns rows in python/ (rg=0). Normal redeploy/torn-down-reuse blocked at reserve, before persist (ingress.py:78). Bypass/manual-corruption only. |
| Dead/divergent DNS API surface | MEDIUM (record) | MEDIUM-as-doc-hazard / LOW-operational (annotated) | Pure dead code, no production reachability (ingress.py:114,192,207; zero prod callers). MEDIUM retained ONLY for doc-trust/clarity; operational risk LOW. |
| dns_repair untracked-apply (NEW) | — | MEDIUM | action_worker.py:858-880,169-179,209-231; ingress.py:171-189 |
| Dead teardown_arclink_dns 4-hostname overshoot (NEW) | — | INFO | ingress.py:201-203; adapters.py:233-238 |

## STANDING DISAGREEMENTS
None. Codex OBJECT(2) is fully absorbed: the prefix-collision REFINE is adopted as a severity downgrade (MEDIUM->LOW) that BOTH the mechanical fact (Claude) and the reachability gating (Codex) support from the same code; the dns_repair MEDIUM finding is confirmed and added to the risk register.

## FINAL BOTH-MODEL VERDICT
CANON-09 provably does its core job: compute desired domain-mode dashboard/hermes CNAME (proxied) records, persist them into `arclink_dns_records` with a desired->provisioned->torn_down state machine (status-preserving upsert), emit matching `arclink_events`, and render Traefik domain/tailscale router labels. Every live seam to CANON-08 (provisioning intent, persist, teardown-read), CANON-11 (executor request/result shapes), and CANON-01 (events/schema) is both-ends-verified and code-consistent; 6 tests pass. Reconciled risk register: (1) MEDIUM doc-trust dead/divergent `cloudflare`-object API surface (operational LOW); (2) MEDIUM bulk status clobber on partial-deployment teardown; (3) **NEW MEDIUM** `dns_repair` untracked-apply (Cloudflare write with no DB row -> teardown blind spot); (4) LOW provider_record_id out-of-piece coupling; (5) LOW prefix-collision DNS-index IntegrityError (downgraded from MEDIUM — bypass/corruption only, gated by CANON-08 prefix reservation); (6) LOW `except Exception` retry breadth (dead code); (7) INFO teardown over-report of never-deleted hostnames as removed; (8) INFO unused tailscale params, per-call/mid-deployment commits, empty-dict commit, dead 4-hostname teardown overshoot. None break the happy path. FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-09-ingress-dns.fix.md`](../fixes/CANON-09-ingress-dns.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `31e7d39` committed.
- Summary: 7 fixed / 1 skipped / 4 needs-decision.
- Tests: 4 pass / 2 environment-blocked. Passed: `tests/test_arclink_ingress.py`, `tests/test_arclink_action_worker.py`, `tests/test_arclink_provisioning.py`, `tests/test_arclink_admin_actions.py`, plus `py_compile` and targeted executor teardown regression. Blocked: full `tests/test_arclink_executor.py` and `tests/test_arclink_sovereign_worker.py` hit pre-existing `/arcdata/...` permission errors after/before the touched paths.
- Representative fixes:
  - MEDIUM — `dns_repair` now persists validated DNS rows before Cloudflare apply, then marks provisioned rows and backfills provider IDs after success. `python/arclink_action_worker.py:236`, `python/arclink_action_worker.py:889`, `python/arclink_action_worker.py:911`; `python/arclink_ingress.py:191`
  - MEDIUM — DNS teardown/provision status marking is now hostname-scoped, so partial teardown no longer bulk-clobbers every deployment DNS row. `python/arclink_ingress.py:153`, `python/arclink_ingress.py:219`
  - LOW — live Cloudflare teardown now returns only actually deleted/found records, not every attempted hostname. `python/arclink_executor.py:1036`, `python/arclink_executor.py:2572`
- Needs decision:
  - Torn-down-row/global DNS unique-index collision: left unchanged because the normal path is gated by CANON-08 prefix reservation, and changing the index/delete semantics is a schema/contract decision. `python/arclink_control.py:2077`
  - Persisted `proxied` drift: left unchanged because fixing it needs a DB schema and live drift contract change, not a surgical CANON-09 patch. `python/arclink_ingress.py:74`
  - Public unused `tailscale_dns_name` / `tailscale_host_strategy` args on `desired_arclink_ingress_records`: left unchanged because removing or repurposing them is a public signature decision. `python/arclink_ingress.py:46`
  - Non-empty internal commits in DNS helpers remain; removing them would change caller transaction semantics outside the narrow empty-record no-op.
<!-- CANON-REPAIR-STATUS:END -->
