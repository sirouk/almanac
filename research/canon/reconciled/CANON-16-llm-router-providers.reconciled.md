# CANON-16 — LLM Router & Providers — RECONCILED (both-model-signed)

- **Codex (GPT-5.5 xhigh) SIGN-OFF:** OBJECT(4) — "Core record is ratifiable, but keep the verifier's allowlist/body-buffer objections and merge four additional router hardening findings."
- **Claude adjudicator FEDERATION SIGN-OFF:** BOTH-MODEL-AGREED.
- **Method:** every DISPUTED point, every Codex REFINE/REFUTE, and every Codex new finding was re-opened in code by the adjudicator (Read/rg/sed). Codex CONFIRM items where both models already agreed are ratified one-line. Code wins over comment/name/prior claim.

Net: there is **no rejection-level disagreement between the two models.** Codex objected only to *expand* the record (keep both Claude-verify gaps + add four findings), not to overturn it. All four Codex new findings re-verified TRUE in code. Federation reconciles to one truth.

---

## Resolution table (point | winner | deciding cite)

| # | Point | Winner | Deciding cite |
|---|-------|--------|---------------|
| 1 | Router routes/auth/body/preflight/stream split exact | both (ratify) | `arclink_llm_router.py:1837,1845,1871,1876,1879,1895` |
| 2 | Key regex / HMAC / single-row verify / write-on-auth | both (ratify) | `arclink_control.py:6683,6688,6708,6789,6800,6810` |
| 3 | Allowlist is INPUT-ONLY; resolved/fallback model never re-checked vs allowlist before upstream POST | both (Claude R1/GAP-1 = Codex CONFIRM) | request check `arclink_llm_router.py:1084`; resolution `:1086,:614,:619`; unchecked POST `:1465` (non-stream), `:1646,:1665` (stream) |
| 4 | Budget fail-open via `unlimited` is real; **only** non-test literal writer is the Operator-agent stamp; router trusts metadata without provenance re-check | codex (REFINE accepted) | producer `arclink_operator_agent.py:150`; gate `arclink_chutes.py:711,767`; consumer `arclink_llm_router.py:1149` |
| 5 | Reservation/concurrency gate is advisory (TOCTOU) — check and INSERT are separate autocommit statements | both (ratify) | read `arclink_llm_router.py:1129`/`:834`; insert `:1180`/`:846` |
| 6 | Chunked/no-Content-Length body DoS — `await request.body()` buffers entire body before real length check (GAP-2) | both (ratify) | `arclink_llm_router.py:490` (header precheck) → `:492` (full buffer) → `:493` (real check) |
| 7 | Router-path Chutes-usage idempotency collision is NOT credible — fresh `llmuse_<uuid>` is the first identity field, so dedup SELECT never matches; collision impossible | both (Claude R2 = Codex REFUTE) | identity prefers `usage_event_id` `arclink_chutes.py:490-491`; router supplies fresh uuid `arclink_llm_router.py:1406`; dedup SELECT `arclink_chutes.py:882` |
| 8 | CONTRACT #3 mis-names `secret_ref` as a read column — api_auth selects `status` and derives presence from row COUNT, never selects `secret_ref` | both (Claude R3/S1 = Codex REFINE) | `arclink_api_auth.py:4625` (COUNT/status); no `secret_ref` select |
| 9 | GAP-031 = no live PROOF, not no live ROUTE — production router posts to real Chutes when no mock transport injected; live proof injects `httpx.MockTransport` | codex (REFINE accepted; sharpens record's wording) | live POST path `arclink_llm_router.py:1463`; mock injection `arclink_live_runner.py:580` |
| 10 | Fuel-notice producer→consumer seam is now BOTH-END verified (record had it "partial") | codex (CONFIRM accepted — status upgrade) | producer `arclink_llm_router.py:940`; delivery `arclink_notification_delivery.py:1286,1348`; telegram strip `arclink_telegram.py:1072`; map `/refuel` `arclink_public_bots.py:828` |
| 11 | `to_public()` hardcodes `"limit_enforced": True` even for `unlimited` lane (GAP-3) | both (Claude GAP-3 = Codex "Corrected") | `arclink_chutes.py:107` (literal True) vs gate disabled `arclink_llm_router.py:1149` |
| 12 | Schema tables/status-CHECKs, no prompt/completion persistence, final-model settlement, stream no-replay, YAML merge, compose port/budget defaults | both (ratify) | `arclink_control.py:1234,1242,1261,1275,1296`; `arclink_llm_router.py:1372,1329,1756`; `compose.yaml:584,597` |

---

## Codex NEW FINDINGS — confirmed vs rejected (all re-verified in code)

**CONFIRMED (net-new federation risks):**

- **NF-1 (MEDIUM) — Key-specific allowlist bypassed by the global default-model exception.** `_router_model_allowed` returns True whenever `clean_model == config.default_model` (a single GLOBAL on RouterConfig), regardless of whether that string is in the *key's* `allowed_models`. A key scoped to `["model-X"]` can still request the global default. Cite: `arclink_llm_router.py:650` (`config.default_model and clean_model == config.default_model`); per-key allowlist source `:1083`; default_model is global field `:94`.
- **NF-2 (MEDIUM) — Settlement exception leaks a permanent `reserved` row.** On the success path `_record_router_usage` calls `record_chutes_usage_event` (`:1401`) BEFORE `_release_budget_reservation` (`:1432`). `record_chutes_usage_event` can raise `ValueError`/`KeyError`/`PermissionError` (`arclink_chutes.py:861,867,871`). The `chat_completions` handler wraps `_forward_non_streaming` with NO try/except (`arclink_llm_router.py:1906`); the inner `try/finally` only closes the conn (`:1631`), it does not release. There is NO reservation-aging/expiry path anywhere (grep over router+control found only the status CHECK `arclink_control.py:1303`, no expirer). The orphaned `reserved` row counts forever against `_open_reserved_count` (`:834`) → permanent concurrency-slot leak. CONFIRMED.
- **NF-3 (LOW) — Rate limits are advisory (same TOCTOU class as reservation).** `_check_rate_limit` reads the count (`arclink_llm_router.py:811`, called `:1124`) and `_record_rate_limits` inserts+commits later (`:831`/`:1159`, each `record_rate_limit_event` commits independently `arclink_control.py:6948`). Concurrent bursts can both pass the same 60s window. CONFIRMED.
- **NF-4 (LOW, with corrected failure-mode) — External `record_chutes_usage_event` idempotency is sequential, not race-safe.** SELECT-existing (`arclink_chutes.py:882`) precedes UPDATE (`:913`)+INSERT (`:917`) with no IntegrityError handler. CONFIRMED as not-race-safe. **Adjudicator correction to Codex's framing:** `arclink_events.event_id` is `TEXT PRIMARY KEY` (`arclink_control.py:1234`), so a true concurrent re-ingest does NOT double-count — the second INSERT raises `sqlite3.IntegrityError`. The real defect is an *unhandled exception* under race, not a ledger corruption. Net severity LOW (router path is single-use uuids anyway; only the external/replayed-event path is exposed).

**REJECTED:** none. All four Codex new findings hold in code.

---

## Severity changes (code-supported only)

| Risk | From | To | Cite |
|------|------|----|------|
| Model allowlist escape (replacement/auto-promote/fallback, GAP-1) | record VERDICT implied "enforces allowlist" (no risk row) | **MEDIUM** (default-on, upstream-catalog-influenced egress escape) | escape default-on: `model_auto_promote` default True `arclink_llm_router.py:194`; family keyed off upstream catalog `arclink_control.py:6550`; unchecked POST `:1465,:1646` |
| Key default-model allowlist bypass (NF-1) | not in record | **MEDIUM** (net-new) | `arclink_llm_router.py:650` |
| Reserved-row leak on settlement exception (NF-2) | not in record | **MEDIUM** (net-new; permanent concurrency leak, no aging path) | `arclink_llm_router.py:1401→1432`, handler no-catch `:1906` |
| Body-buffer DoS (GAP-2) | record INPUT CONTRACT presented `/chat/completions` body as fully size-protected | **LOW/MEDIUM** (resident-before-reject on chunked/absent CL) | `arclink_llm_router.py:492` |
| Rate-limit advisory (NF-3) | not in record | **LOW** | `arclink_llm_router.py:811,831` |
| External usage idempotency race (NF-4) | not in record | **LOW** (corrected: IntegrityError, not double-count) | `arclink_chutes.py:882`; PK `arclink_control.py:1234` |
| `limit_enforced:True` for unlimited lane (GAP-3) | not in record | **INFO** | `arclink_chutes.py:107` |
| OAuth state replayable on CSRF mismatch (GAP-4) | not in record | **INFO** (test-only module, 32-byte CSRF, ≤10-min window) | `arclink_chutes_oauth.py:324` (raise w/o pop) vs `:329` (pop on success) |
| Mid-stream error SSE frame after valid chunks (GAP-5) | record framed as "no replay" only | **INFO** (wire-shape concern) | `arclink_llm_router.py:1756-1758` |

Record's own MEDIUM (budget fail-open via unlimited) and MEDIUM (reservation TOCTOU) are RATIFIED at MEDIUM — no change.

---

## Standing disagreements

**NONE.** Every material point reconciled to a single code-grounded truth. The only adjudicator divergence from Codex was a *refinement of failure mode* on NF-4 (IntegrityError, not double-count) — not a disagreement on whether the finding holds. Codex itself recorded "No rejection-level disagreement."

---

## FINAL BOTH-MODEL VERDICT

CANON-16 provably does its job as a **local-real** inference control plane: per-deployment `acpod_live_` HMAC keys with single-row status-gated verify; a fail-closed Chutes credential/budget boundary that rejects operator-shared keys, plaintext, and unscoped secret refs; max-candidate budget reservation with final-model settlement; rate/concurrency caps; a full non-streaming + pre-stream-fallback cascade with explicit no-replay-after-first-chunk labeling; and sanitized usage rows that never persist prompts or completions. The model-providers registry cleanly serves CANON-04/CANON-19 with deterministic preset→target/model resolution.

The federation **amends the record's allowlist language**: the allowlist is an INPUT filter, not an EGRESS guarantee — request strings are checked, but replacement / auto-promote (default-on, upstream-catalog-influenced) / fallback candidates AND the global default-model exception all route around it (NF-1 + GAP-1, both MEDIUM). Other reconciled weaknesses: the `observe_only_unlimited` budget fail-open is Operator-stamped but router-trusted without provenance re-check (MEDIUM); reservation/rate gates are advisory TOCTOU (MEDIUM/LOW); a settlement exception leaks a permanent `reserved` row with no aging path (MEDIUM, net-new); chunked body buffering precedes the size reject (LOW/MEDIUM); and the live Chutes relay is never exercised live — GAP-031 is genuinely open (the only "proof" uses `httpx.MockTransport`; the prior doc's named live-proof env gate does not exist). The OAuth + live adapters are import-only by tests, secret-safe, and proof-gated.

**FEDERATION SIGN-OFF: BOTH-MODEL-AGREED** — every material point reconciled to one truth; four Codex findings confirmed net-new; zero standing disagreements.
