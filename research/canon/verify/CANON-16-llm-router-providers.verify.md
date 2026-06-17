# CANON-16 — LLM Router & Providers — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened all five tracked files plus
the cross-piece seams (`arclink_control.py`, `arclink_api_auth.py`, `arclink_sovereign_worker.py`,
`arclink_live_runner.py`, `compose.yaml`, onboarding/headless consumers). Every line below was
read, not trusted from the record.

## VERDICT
The record is **substantially trustworthy** on its load-bearing citations — schema, key verify,
boundary, reservation, fallback, redaction, mock-transport live proof, and all six in-repo
cross-piece producers were independently re-confirmed at the cited lines. BUT the record's
VERDICT and ADVERSARIAL SELF-CHECK **overclaim the allowlist guarantee** and **miss two real
defects**: (1) the model allowlist is enforced ONLY on the literal request string and is escaped
by replacement / auto-promote / fallback routing (auto-promote is upstream-catalog-influenced and
ON by default); (2) `_read_json_body` buffers the entire body into memory before the size check
on chunked/Content-Length-absent requests. Net: keep the record, but add these gaps and downgrade
the "enforces allowlist" language in the VERDICT.

---

## A. REFUTATIONS / CONFIRMATIONS OF LOAD-BEARING CLAIMS

### CONFIRMED (re-verified in code)
- **Key regex / hash / single-row verify** (record :11,:47; CONTRACT #1). `LLM_ROUTER_KEY_RE`
  at `arclink_control.py:6683` matches `^acpod_live_([A-Za-z0-9]{8,32})_([A-Za-z0-9_-]{32,})$`.
  `generate_llm_router_raw_key` `:6688` = `token_hex(6)` (12 hex) + `token_urlsafe(36)`. Verify
  at `:6789` does `WHERE k.key_hash IN (?,?) LIMIT 2`, rejects `len(row)!=1` `:6800`, status≠active
  `:6803`, deployment in {cancelled,torn_down,teardown_complete} `:6805`, user≠active `:6807`.
  Confirmed.
- **`verify_llm_router_key` rewrites `key_hash` on EVERY success** (record :78, RISK :97).
  `:6810-6814` UPDATE+commit unconditional on every verified call, not just legacy rows. Confirmed
  write-on-read-path.
- **Boundary fail-closed chain** (record :52). `arclink_chutes.py:782-819`: `allow_inference`
  starts True, denied for billing_suspended/suspended/oauth-required/missing-secret/invalid-
  secret/unscoped/budget_unconfigured/budget_exhausted. Operator-shared-key rejected via
  isolation_mode `operator_shared_key_rejected` (`:755-756`) and unscoped/plaintext refs rejected
  (`:751-754`). Confirmed.
- **Unlimited lane fail-open** (record :74, RISK :95). `OBSERVE_UNLIMITED_REMAINING_CENTS=10**12`
  at `arclink_chutes.py:18`; set when `budget_policy in {observe_only_unlimited,unlimited}` `:715`;
  short-circuits budget status to "unlimited" `:771-772`; router skips the reservation budget gate
  `arclink_llm_router.py:1149`. Confirmed. IMPORTANT: the unlimited lane bypasses ONLY budget — the
  secret/isolation checks (`:793-808`) still run, so the record's "uncapped" framing is correct and
  bounded to budget.
- **Max-candidate reservation** (record :54, self-check #2). `_fallback_reservation_pricing`
  `:585` picks `max(choices, key=reserved_cents)` with empty-list guard `:573`. Confirmed.
- **Final-model settlement** (record :59). `_record_router_usage` re-prices on FINAL `model` via
  `get_model_catalog_entry(...model_id=model)` `:1329`; `actual_cents` only on success `:1331`.
  Confirmed.
- **No prompt/completion persistence** (record :82). `arclink_llm_usage_events` INSERT `:1372`
  writes token counts + `_safe_upstream_error`→`redact_then_truncate(limit=300)` `:668,:1394` +
  metadata only. No raw body column. Confirmed (residual: a 300-char error string can carry a
  non-secret user fragment — record already flagged).
- **Streaming no-replay-after-first-chunk** (record :22). `:1735` sets next_model only when
  `not yielded_any`; `:1756-1757` labels `unavailable_after_stream_started`. Confirmed.
- **Schema cites** (record :23,:37). `arclink_control.py:1242` (catalog), `:1261` (router_keys),
  `:1275` (usage_events), `:1296` (reservations); status CHECKs at `:1250,:1267,:1287,:1303`.
  Confirmed exactly.
- **CONTRACT #3 (api_auth provider-state).** `_llm_router_provider_state` `arclink_api_auth.py:4601`
  reads `arclink_llm_router_keys` (status COUNT), `arclink_llm_usage_events` (status/tokens/
  estimated_cents/actual_cents/stream/started_at/completed_at), `arclink_llm_budget_reservations`
  (status='reserved', reserved_cents) — all columns exist in schema. Both ends match. Confirmed,
  with one imprecision (see seam mismatch S1).
- **CONTRACT #1/#5/#6/#7/#8 producers.** sovereign_worker mints+registers at
  `arclink_sovereign_worker.py:159(flock),163,1859`; model_providers consumed at
  `onboarding_provider_auth.py:29-30`, `onboarding_flow.py:99,720`, `headless_hermes_setup.py:211,
  263`; live_runner uses `httpx.MockTransport` at `arclink_live_runner.py:580`. All confirmed.
- **No live-proof env var.** `rg ARCLINK_LLM_ROUTER_LIVE_CHUTES_PROOF --type py` → none. Record's
  drift claim (:73) holds.
- **OAuth/live import-only by tests.** `grep` shows importers only in `tests/`; no dynamic
  import of either module. Proof-gates at `chutes_oauth.py:353`, `chutes_live.py:191`. Confirmed.

### REFUTED / OVERCLAIMED
- **R1 — VERDICT "enforces allowlist/replacement/budget/rate/concurrency policy" (record :4,:104)
  is OVERCLAIMED.** The allowlist is checked ONLY on the literal request string
  (`_router_model_allowed(config, model, allowed_models)` at `arclink_llm_router.py:1084`). The
  resolved `upstream_model` (`:1086`) — a catalog `replacement_model_id` (`:614`), an auto-promoted
  `latest_model_in_family` (`:619,:628`), or any `config.fallback_models` candidate (`:655`) — is
  NEVER re-checked against `allowed_models` before being POSTed upstream (`:1452,:1465`;
  streaming `:1646,:1665`). So a deployment scoped to model X can be routed to a different model Y
  outside its allowlist. See GAP-1.
- **R2 — record line 28 "idempotent `:882`" is MISLEADING for the actual router caller.** The
  router always passes `usage_event_id = usage_id = f"llmuse_{uuid4().hex[:24]}"` (`:1334,:1406`),
  which becomes `external_id` in `_usage_event_identity` (`arclink_chutes.py:490-499`). Each call
  has a fresh UUID → the dedup SELECT at `:882` NEVER matches for router-origin events. The
  idempotency mechanism is real for re-submitted external events but is INERT on the router path;
  it neither dedups nor can collide (refutes the Federation open-question #4 about collision —
  collision is impossible because every key is a fresh UUID).
- **R3 — record CONTRACT #3 says api_auth reads column `secret_ref` (:64). It does NOT.** It
  reads `status` and derives `secret_ref_present` from `COUNT(*) > 0` over `arclink_llm_router_keys`
  (`arclink_api_auth.py:4625-4635`). The `secret_ref` column is never selected. Minor; the
  contract shape is otherwise correct.

---

## B. NEW GAPS (neither the record nor prior docs mention)

- **GAP-1 (MEDIUM) — Model allowlist escape via replacement / auto-promote / fallback.**
  Allowlist checked on request string only (`:1084`); `upstream_model` and all fallback candidates
  are forwarded unchecked (`:1086,:1452,:1465`,`:1646,:1665`). `model_auto_promote` defaults TRUE
  (`:194`) and `refresh_model_catalog_on_startup` defaults TRUE (`:198`), and
  `latest_model_in_family` keys off catalog `family`/`version_sort_key` derived from the upstream
  `/models` response (`arclink_control.py:6550-6551`). Therefore an upstream provider publishing a
  new same-family model can silently route a deployment OUT of its allowlist by default. (Operator-
  set `set_model_replacement` and `ARCLINK_LLM_ROUTER_FALLBACK_MODELS` are additional, operator-
  controlled escapes.) This directly contradicts the VERDICT's allowlist-enforcement claim.

- **GAP-2 (LOW/MEDIUM DoS) — Unbounded in-memory body buffering on chunked requests.**
  `_read_json_body` pre-checks the `content-length` header (`arclink_llm_router.py:490`) but then
  calls `await request.body()` (`:492`) which buffers the ENTIRE body before the real
  `len(body) > max_body_bytes` check (`:493`). A chunked / Content-Length-absent / spoofed-low
  request streams an arbitrarily large payload fully into memory before rejection. Default cap is
  1 MiB but the guard does not apply until the whole body is resident. Record's INPUT CONTRACT
  (:9) presents this as fully protected.

- **GAP-3 (INFO) — `to_public()` hardcodes `"limit_enforced": True`** (`arclink_chutes.py:107`)
  even for the `budget_status="unlimited"` lane, where the router demonstrably does NOT enforce a
  limit (`:1149`). The public/admin provider-state surface therefore reports limit-enforced for a
  deployment whose budget gate is disabled — a posture/behavior drift on the observability seam.

- **GAP-4 (INFO) — OAuth callback does not consume state on CSRF mismatch.**
  `complete_chutes_oauth_callback` does `state_store.get(clean_state)` (`arclink_chutes_oauth.py:319`),
  compares CSRF with `compare_digest` (`:324`), and only `pop`s on success (`:329`) or expiry
  (`:327`). A wrong-CSRF attempt leaves the state replayable until its 10-min expiry (`:297`).
  Not practically exploitable (32-byte CSRF, constant-time compare) and module is test-only, but
  it is a real replay-window detail unmentioned.

- **GAP-5 (INFO) — Mid-stream error frame after valid chunks.** When upstream dies after chunks
  were yielded (`yielded_any=True`), the router still appends an `arclink_router` error SSE frame
  (`:1758`) into a stream that already delivered real model output, then returns. A strict OpenAI
  SSE consumer receiving a non-`chat.completion.chunk` error object mid-stream may mishandle it.
  Record frames this only as "no replay," not as a wire-shape concern.

---

## C. SEAM MISMATCHES

- **S1 — CONTRACT #3 column description imprecise.** Record (:64) lists `secret_ref` as a read
  column; api_auth reads only `status` and counts rows (`arclink_api_auth.py:4625-4637`). Both
  ends still functionally agree on the *shape consumed*; the descriptive column list is wrong.
- **S2 — CONTRACT #6/#7 are import-time constants, not per-request.**
  `onboarding_provider_auth.py:29-30` and `headless_hermes_setup.py:211,263` resolve
  `provider_default_model(...)` at module import, so a later YAML edit does not propagate without a
  process restart. Seam shape (preset→string) verified; freshness is not. Not a defect, but the
  "both-ends-verified" label should note the binding time.

## D. RISK RE-CALIBRATION
- Record's "MEDIUM — Budget fail-open via unlimited policy" is correctly rated; the stamping
  producer remains untraced here (CANON-08/CANON-14), so the open question stands.
- Record's "MEDIUM — Reservation is advisory (TOCTOU)" is CONFIRMED: in
  `chat_completions`, the preflight conn (`:1884-1890`) runs `_open_reserved_count` SELECT (`:1129`)
  and the reservation INSERT (`:1180`) as separate autocommit statements with no BEGIN/row-lock;
  two concurrent requests can both pass concurrency/budget before either commits. Bounded by
  default concurrency 4.
- I would ADD GAP-1 at **MEDIUM** (default-on, upstream-influenced allowlist escape) — arguably
  higher operational impact than the unlimited lane because it is on by default for every
  deployment, not just the Operator Pod.

## E. RESIDUAL DISAGREEMENTS
- The record's VERDICT sentence "per-deployment ... enforces allowlist/replacement/budget/rate/
  concurrency policy" should be amended: allowlist enforcement covers the request input only, not
  the routed/upstream model. Until GAP-1 is closed, the allowlist is an input filter, not an
  egress guarantee.
