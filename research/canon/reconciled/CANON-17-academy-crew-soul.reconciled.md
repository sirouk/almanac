# CANON-17 — Academy / Crew / SOUL — RECONCILED (both-model truth)

- Piece: CANON-17 — Academy / Crew / SOUL
- Codex (GPT-5.5 xhigh) SIGN-OFF: OBJECT(4) — objected only to four refinements (PG-PROVIDER enforcement, mutation flags, Contract #2 marker semantics, source-lane fail-open) + 3 new findings.
- Adjudicator (Claude Opus 4.8, 1M): re-opened every disputed cite; decided by code.
- FEDERATION SIGN-OFF: **BOTH-MODEL-AGREED** — every material point reconciled to one code-grounded truth; no standing disagreement survives re-reading the code.

Method: for each Codex REFUTE/REFINE, each Codex new finding, and each residual disagreement, the cited code was re-opened (Read/rg). Code wins over comment/name/prior claim. Codex CONFIRM items where both models already agree are ratified one-line.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Point | Winner | Deciding cite (re-opened) |
|---|-------|--------|---------------------------|
| 1 | Schema = 10 `academy_*` tables + `arclink_crew_recipes`; prior doc undercounted (missed `academy_source_crawl_observations`) | both | `arclink_control.py:1476` (crew_recipes), `:1686` (crawl_observations table) |
| 2 | HIGH live-default: CE crawl + Trainer live ship default-ON | both | `arclink_academy_scheduler.py:625` (`ARCLINK_ACADEMY_CE_LIVE_CRAWL` default True); `compose.yaml:97` (`ARCLINK_ACADEMY_TRAINER_LIVE:-1`); `compose.yaml:793-800` (weekly job) |
| 3 | HIGH DNS-rebinding/TOCTOU in crawler | both | `arclink_academy_scheduler.py:196` (getaddrinfo validate) → `:219` (`Request(str(url))` re-resolves, no IP pin); mitigations only `:207-209` no-redirect + `:189` https-only |
| 4 | MEDIUM apply blast radius > SOUL+receipt (vault/qmd/skill/state) | both | `arclink_action_worker.py:2094` (SOUL), `:2102-2107` (vault loop); writes-gate at `arclink_academy_programs.py:2938` |
| 5 | REFINE — Claude record's blanket "all this-piece functions return `mutation_performed=False`" is FALSE | codex | `arclink_crew_recipes.py:373` and `:953` return `mutation_performed=True`; `arclink_action_worker.py:2227` (apply) returns True. Only `workspace_mutation_performed=False` is universal. |
| 6 | REFINE — Contract #2 marker: consumer does NOT read producer's `academy_soul_marker` field; relies on hardcoded matching marker in `merge_academy_overlay` | codex | producer emits field `arclink_academy_programs.py:2985`; consumer `arclink_action_worker.py:2087` imports/calls `merge_academy_overlay` and reads only `academy_soul_section` (`:2082`), never the marker field; marker hardcoded `arclink_org_profile.py:26` + `:1745`. Markers identical → no break. |
| 7 | MEDIUM proposal TOCTOU: SELECT-then-INSERT with NO `IntegrityError` recovery; unique index `(trainee_id, proposal_kind, origin_url)` | both | SELECT `arclink_academy_programs.py:754-758`; INSERT `:791-821` (no try/except); index `arclink_control.py:1757-1764` (post-DDL drop/recreate migration — Codex's corrected cite is the right one). Loser raises `UNIQUE constraint failed`. |
| 8 | One-open-session race-safety via partial unique index + IntegrityError rollback | both | index `arclink_control.py:1552-1554`; rollback `arclink_academy_programs.py:536` |
| 9 | `organization_private` excluded from central sharing | both | `arclink_academy_trainer.py:649` (`SHARE_INELIGIBLE_SOURCE_LANES`); skip `arclink_academy_programs.py:1741`; has_candidate guard `:1657` |
| 10 | Stale apply contract fail-closes before writes | both | `arclink_academy_programs.py:2927` (`not contract_ok`) / `:2931` (`not contract_fresh`) early-out before the writes-enabled branch `:2938` |
| 11 | Latent unimported-`Sequence` annotation (NameError on `get_type_hints`) | both | `arclink_crew_recipes.py:11` (imports Any/Mapping/Protocol only), `:776` (uses `Sequence`); PEP 563 keeps runtime safe |
| 12 | Producer-only router seam (CANON-16 consumer not cross-proven) | both | `arclink_academy_programs.py:2175` POST OpenAI-compatible `/chat/completions`; consumer not opened here — agreed-open, not a defect |
| 13 | Cross-piece seams (MCP propose-resource, public-bots enroll/open/end, org overlay marker-bounded, provisioning `metadata_json["academy_training"]`, CE compose invocation) all both-ends-verified | both | `mcp_server.py:2162`↔`programs.py:683`; `public_bots.py:5816`; `org_profile.py:1713/1745`; `provisioning.py:274`; `compose.yaml:793` |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (now net-new federation risks)

**NF-1 (MEDIUM, CONFIRMED) — `academy_apply` advertises `PG-PROVIDER` but does NOT enforce live provider proof before writes.**
Re-opened the full gate. The writes-enabled branch requires `live_adapter and live_authorized and review_ready and trainer_review_ready` (`arclink_academy_programs.py:2938`). Each of those is satisfiable WITHOUT any live LLM-router call:
- `review_ready` (`:2862`) reads `composed["review"]["status"]`, and `composed["review"]` is the purely-deterministic `build_academy_review_status(...)` (`:2733`), whose status derives from the offline evaluation gate (`arclink_academy_trainer.py:1045` returns `ready_for_review` for a policy-clean, quality-scored local corpus — no network).
- `trainer_review_ready` (`:2899`) = non-empty SOUL section AND non-empty `academy_trainer_reviewed_at`. The deterministic Trainer review stamps `reviewed_at` unconditionally (`:2303`) even when it sets `live_enrichment_status="pending_pg_provider"` (`:2311`).
So the only true write requirement is **PG-HERMES** (live adapter + `live_authorized` + `ARCLINK_ACADEMY_APPLY_LIVE`), while the payload still stamps `proof_gate="PG-PROVIDER"` (`:2310`) and lists `PG-PROVIDER` in `proof_gates` (`:2991`). The advertised provider proof gate is cosmetic at the write boundary. CONFIRMED as code-true. (Materiality note: the write is additive, marker-bounded, and still requires PG-HERMES, so this is a labeling/governance gap, not a SOUL-overwrite — hence MEDIUM, not HIGH.)

**NF-2 (LOW, CONFIRMED) — source-lane validation is not strictly fail-closed.**
`_validate_source_lanes` wraps the registry import in `try/except Exception: return lanes` (`arclink_academy_programs.py:3071-3076`) — on registry-load failure it accepts caller lanes unvalidated. CONFIRMED as code-fact. Caveat (re-verified): `default_source_lane_registry` (`arclink_academy_trainer.py:537-555+`) is a pure in-process static dataclass list with no I/O, so the except is reachable only if the trainer module itself fails to import (a deploy-level breakage where most of the subsystem is already dead). Real fail-open, practically unreachable in a healthy stack — confirmed at LOW.

**NF-3 (INFO, CONFIRMED-but-contained — downgraded from Codex LOW) — crawl observation ID can collide; INSERT has no conflict handler.**
`_observation_id` seeds on `(source_ref_kind, source_ref_id, trainee_id, observed_at)` (`arclink_academy_scheduler.py:430-432`) — excludes `source_uid`; `observed_at` is second-granularity (`arclink_control.py:66-67`, `.replace(microsecond=0)`); the INSERT into the `observation_id TEXT PRIMARY KEY` table has no `ON CONFLICT` (`scheduler.py:458-465`, table `arclink_control.py:1687`). HOWEVER, re-reading the loop: `_crawlable_source_rows` dedups by `(source_ref_kind, source_ref_id)` AND by canonical URL (`scheduler.py:601-612`), so NO intra-run, same-trainee duplicate is possible; and the per-trainee body is wrapped in `try/except Exception: errors.append(...); continue` (`scheduler.py:881-903`), so even a cross-run same-second collision would skip one trainee for that run, not crash the job. Collision therefore requires the same trainee+source processed twice within one wall-clock second across two scheduler invocations — outside the weekly single-run-per-specialist rotation. **Reclassified INFO (severity change applied below).**

### REJECTED
None. All three Codex new findings hold in code; NF-3 is reclassified down, not rejected.

---

## CONFIRMED VERIFIER FINDINGS (Claude adversarial-verify, ratified by Codex + adjudicator)

- R1 (LOW) mutation-flag overstatement → same as resolution #5, confirmed.
- R2 (INFO) proposal index includes `proposal_kind` → confirmed at `arclink_control.py:1761`; load-bearing for add/discontinue coexistence.
- G1 (MEDIUM) proposal TOCTOU → resolution #7, confirmed.
- G2 (LOW) per-trainee crawl unbounded when `ARCLINK_ACADEMY_CE_CRAWL_LIMIT=0` → confirmed: `_env_int` minimum=0 (`scheduler.py:642`), gate `if limit and ... >= limit` (`scheduler.py:667`); per-host cap (minimum=1, `:649`) still applies.
- G3 (LOW) robots.txt 4xx/5xx fails OPEN (except 401/403) → confirmed as fail-open policy; widens crawl surface alongside NF-DNS.
- G4 (LOW) live Trainer failure swallowed to deterministic, only `review["live_error"]` recorded, no audit/notification → confirmed `arclink_academy_programs.py:2296-2299`; Captain gets no signal PG-PROVIDER inference is down.
- G5 (INFO) `academy_continuing_education` docstring "behind PG-PROVIDER" vs env-only gate → confirmed (== Claude DRIFT #7).

---

## SEVERITY CHANGES (applied only where code supports)

| Risk | From | To | Cite |
|------|------|----|------|
| Crawl observation ID collision (Codex NF-3) | LOW (Codex) | INFO | `arclink_academy_scheduler.py:601-612` (intra-run dedup) + `:881-903` (per-trainee try/except/continue) make a collision narrow + contained |

No other severity changes: the two HIGH risks (live-default, DNS-rebinding), the MEDIUM risks (apply blast radius, proposal TOCTOU, PG-PROVIDER non-enforcement, `Sequence` import) and the LOW risks all stand at the severities both models assigned.

---

## STANDING DISAGREEMENTS
None. Every material point reconciled to one code-grounded truth. Two items remain *agreed-open* (not disagreements): (a) the CANON-16 router response-shape contract is producer-only verified on both sides — neither model claims otherwise; (b) whether a deploy-private `config/*.env*` flips `ARCLINK_ACADEMY_CE_LIVE_CRAWL`/`ARCLINK_ACADEMY_TRAINER_LIVE` is outside this read-only proof and deferred to CANON-27 — both models agree the shipped tracked defaults are live-ON.

---

## FINAL BOTH-MODEL VERDICT
CANON-17 provably does its job and is materially MORE built than the prior "scaffold-only / UNBUILT" verdict — confirmed by both models in code. Load-bearing strengths hold: race-safe sticky-mode lifecycle, canonical-URL-deduped central corpus that gates `organization_private` out of sharing, a real stable-id fail-closed `stage_academy_apply` contract, marker-bounded additive SOUL apply that never overwrites the human body, and a bounded SSRF/robots-guarded crawler. Reconciled weaknesses, all code-verified: (1) live crawler + live Trainer ship default-ON in compose, contradicting the documented fake-default stance — the single biggest canon correction; (2) apply materializes vault/qmd/skill/state, not just SOUL+receipt; (3) DNS-rebinding TOCTOU window in the crawler; (4) **`academy_apply` advertises `PG-PROVIDER` but enforces only `PG-HERMES` at the write boundary — deterministic review suffices (NF-1)**; (5) proposal SELECT-then-INSERT TOCTOU with no IntegrityError recovery; (6) latent unimported-`Sequence`; (7) source-lane fail-open and crawl-observation-ID collision are real-but-narrow. The Claude record's blanket `mutation_performed=False` claim and its "consumer reads producer's marker field" framing of Contract #2 are corrected per Codex; the subsystem is real, governed, and proof-gated — but the env-flag DEFAULTS say live, and the provider proof gate is cosmetic at apply-write time.

FEDERATION SIGN-OFF: **BOTH-MODEL-AGREED.**

---

<!-- CANON-REPAIR-STATUS:START -->
## Repair status

> Refreshed from [`research/canon/fixes/CANON-17-academy-crew-soul.fix.md`](../fixes/CANON-17-academy-crew-soul.fix.md) (tracked). The audit findings above remain the adjudicated spec; this block records the repair campaign state for this piece.

- Status: `bf7e201` committed.
- Summary: 12 fixed / 3 skipped / 0 needs-decision.
- Tests: 5 test files run, all pass; py_compile pass; git diff --check pass
- Representative fixes:
  - HIGH — Academy live defaults are now opt-in: CE crawl defaults false in code, compose exports `ARCLINK_ACADEMY_CE_LIVE_CRAWL:-0`, and live Trainer compose default is `:-0` — python/arclink_academy_scheduler.py:722, compose.yaml:97
  - HIGH — DNS rebinding TOCTOU closed by carrying the validated public DNS address into pinned HTTP/HTTPS connections instead of reconnecting by hostname — python/arclink_academy_scheduler.py:76, python/arclink_academy_scheduler.py:199, python/arclink_academy_scheduler.py:275
  - MEDIUM — Proposal SELECT/INSERT race now catches `sqlite3.IntegrityError` and returns/updates the race-winner as deduped — python/arclink_academy_programs.py:770, python/arclink_academy_programs.py:842
<!-- CANON-REPAIR-STATUS:END -->
