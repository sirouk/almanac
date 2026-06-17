<<<DECIDED CANON-16>>>
# CANON-16 — LLM Router & Providers — DECIDED (final adjudicator, Opus 4.8 1M)

- **Mode:** DECISION / convergence with Codex (GPT-5.5 xhigh) proposal
  `research/canon/decisions/CANON-16-llm-router-providers.codex.md`.
- **Method:** formed an independent view per decision against the symphony NORTH STAR
  + re-opened code, THEN reconciled with Codex. Code re-read live (working tree, not the
  reconciled snapshot) — note several CANON-16 hardenings have ALREADY landed since the
  reconciled file was written (see "Already-landed context" below), which sharpens what
  each remaining decision actually has to do.
- **Net:** both decisions converge with Codex. Decision 1 = REFINE (Codex's direction is
  right — provenance from operator-agent settings, not metadata, not a hard-coded id — but
  I tighten the mechanism: keep the boundary a *pure* function and gate it with an explicit
  `observe_unlimited_authorized` flag the DB-aware callers compute, and prefer fail-closed-by-
  *demotion* to a capped lane over a new 403 code as the default behavior). Decision 2 =
  AGREE-CODEX (ratify the v1 in-band terminal-error-frame wire contract; finish the
  remaining test assertions; document it as an ArcLink OpenAI-compat extension).

---

## Already-landed context (working tree, verified live)

These were open in the reconciled file but are **already fixed in code** — I am NOT re-deciding
them, only noting so the two real decisions are scoped correctly:

- `arclink_chutes.py:108` now reads `"limit_enforced": self.budget_status != "unlimited"` —
  the GAP-3 hard-coded `True` is gone.
- `arclink_llm_router.py:1146` wraps preflight in `conn.execute("BEGIN IMMEDIATE")` — the
  reservation/rate TOCTOU (record MEDIUM, NF-3) is now transactional.
- Tests already present: `test_router_usage_settlement_error_releases_reserved_row` (NF-2
  reserved-row leak), `test_key_allowlist_blocks_global_default_replacement_and_fallback_escape`
  (NF-1 + GAP-1), `test_read_json_body_rejects_chunked_body_before_buffering_past_limit` (GAP-2),
  and `test_chat_partial_stream_failure_settles_without_prompt_or_secret_storage` (Decision 2's
  core behavior). The two DEFERRED decisions are precisely the ones that needed a *product /
  provenance rule* (D1) or a *public wire-contract ratification* (D2) — the right things to defer.

---

## DECISION 1 — Budget fail-open provenance for `observe_only_unlimited`  [REFINE]

### The question
The router lets the Operator Pod be "metered but unlimited" by reading
`metadata_json.chutes.budget_policy == observe_only_unlimited` off the authenticated
deployment and skipping the reservation budget gate (`arclink_llm_router.py:1211`,
boundary `arclink_chutes.py:718,770-775`). `evaluate_chutes_deployment_boundary` is a
**pure, no-DB function** — it cannot tell whether the deployment carrying that flag is
actually the one configured Operator identity. So if any Captain Pod's
`metadata_json.chutes.budget_policy` could carry that string, that Pod gets uncapped
inference while still appearing "metered." Changing router acceptance needs a product /
provenance rule that works for a *configurable* operator identity (the id defaults to
`"operator"` but is set in `arclink_settings`, `arclink_operator_agent.py:40,46`).

### My independent reasoning (symphony + code)
The symphony is explicit and two-sided. Inference policy *wants* the unlimited lane to
exist: "letting the Operator remain effectively unlimited but still observable… the Operator
lane is now explicitly **metered but unlimited**… `_preflight_chat_request` skips the
reservation short-circuit for the unlimited lane — so Operator Raven inference is observable
like a Captain Pod yet never silenced by a cap." So rejecting the lane outright is wrong — it
would contradict the North Star and break Operator Raven's "always remedy the stack" recovery
posture. The defect is purely a **trust-source** bug: the privilege is real and intended, but
it is currently asserted by *client-controllable deployment metadata* rather than by
*server-side identity*.

Identity governance settles the mechanism: "Admin and Operator actions should never trust
client-asserted privilege… without server-side authorization and typed action resolution,"
and "the same action cannot be made safer or more dangerous merely by choosing chat instead of
dashboard." The unlimited lane is an Operator privilege; it MUST be authorized server-side. The
canonical server-side truth is the operator-agent identity, not mutable metadata: settings
`operator_agent_deployment_id` + `operator_agent_user_id` (`arclink_operator_agent.py:40-41`,
resolved by `operator_agent_deployment()` `:177`), backed by the one-agent invariant
(`assert_single_operator_agent` `:198`). Code proves this is cheap: every consumer that needs
the decision already holds a DB connection — the router at `_preflight_chat_request`
(`arclink_llm_router.py:1148`, inside its `BEGIN IMMEDIATE`), `record_chutes_usage_event`, and
`api_auth._llm_router_provider_state` (`arclink_api_auth.py:4780`). And it FAILS CLOSED for
free: an unauthorized Pod that loses the unlimited privilege falls back to its real budget —
for a spoofing Captain Pod that is `monthly_budget_cents=0` → `budget_status="unconfigured"`
→ 402, exactly the symphony's "0 means fail-closed-until-a-per-Pod-budget-is-set."

Where I land on mechanism: **keep `evaluate_chutes_deployment_boundary` a pure function** (it
is called from three sites and its purity is a load-bearing property — no DB inside the
boundary). Add an explicit `observe_unlimited_authorized: bool = False` parameter. The boundary
honors `observe_only_unlimited` ONLY when that flag is True; otherwise it ignores the metadata
flag and computes `budget_status` from the real budget. Default False ⇒ fail-closed. The
DB-aware callers compute the flag from the same settings, so all surfaces agree.

### Agree / differ from Codex
- **Agree** on the core: do not trust `metadata_json` alone; source authorization from the
  operator-agent settings (`operator_agent_deployment_id` / `operator_agent_user_id`) + the
  single-operator invariant; do NOT hard-code `deployment_id == "operator"`; keep the Operator
  lane unlimited; write a redacted `llm_router:budget_policy_rejected`/`…_demoted` event; keep
  `used_cents` preserved on the authorized lane; live Chutes stays `PG-PROVIDER`/GAP-031.
- **Differ (refinement 1 — keep the boundary pure):** Codex says "pass `observe_unlimited_authorized`
  into `evaluate_chutes_deployment_boundary(...)`." I agree the flag is passed in — but the
  *authorization computation itself* must stay OUT of the boundary (the boundary has no DB and
  must keep none). The router/api_auth compute `observe_unlimited_authorized` from
  `operator_agent_deployment(conn)` settings and pass the boolean. This is what Codex's helper
  `observe_unlimited_authorized(...)` implies; I'm making the boundary-purity invariant explicit
  so the implementer doesn't smuggle a DB read into the pure function.
- **Differ (refinement 2 — demote, don't 403, as the default):** Codex's default failure is
  `403 budget_policy_not_authorized` with "do not call upstream." I'd make the default
  fail-closed behavior **demotion to the normal capped lane** (strip unlimited; enforce real
  budget). Reasons: (a) it's strictly fail-closed without inventing a new public error code or
  refusing a Pod that happens to have real budget; (b) a spoofing Pod is `budget=0` so it
  *already* gets a clean 402 `budget_unconfigured` from the existing path — no new 403 needed;
  (c) it minimizes blast radius and surface drift. The redacted evidence event is still written.
  (If the operator later wants a louder signal, a 403 can be added as a config-gated mode — but
  it should not be the default.) This is a small, friendly divergence; the observable security
  outcome (no uncapped inference for non-Operator Pods) is identical to Codex's.
- **Differ (refinement 3 — name the cross-surface obligation):** the same-truth principle means
  `api_auth._llm_router_provider_state` (`arclink_api_auth.py:4788`) must compute the SAME
  authorization, or the dashboard/Operator-Raven provider-state would still render
  `budget_status="unlimited"` for a flag-carrying Captain Pod while the router demotes it — a
  surface contradiction. Codex's "provider-state usage callers" line gestures at this; I make it
  a hard requirement and a named test.

### FINAL PLAN
1. **Pure boundary, explicit flag.** Add `observe_unlimited_authorized: bool = False` to
   `evaluate_chutes_deployment_boundary` (`arclink_chutes.py:663`). Change the unlimited gate
   `arclink_chutes.py:718` so `unlimited_budget = (budget_policy in {observe_only_unlimited,
   unlimited}) and observe_unlimited_authorized`. No DB access added to the boundary.
2. **Authorization helper.** Add `observe_unlimited_authorized(conn, deployment_id, user_id) -> bool`
   in `arclink_operator_agent.py` (it already owns the settings + invariant): True iff
   `deployment_id == get_setting(operator_agent_deployment_id)` AND
   `user_id == get_setting(operator_agent_user_id)` AND the resolved row carries
   `metadata.operator_agent is True` AND `assert_single_operator_agent(conn) <= 1`. Empty/missing
   settings ⇒ False (fail-closed).
3. **Wire the three callers** (each already has `conn`): router `_preflight_chat_request`
   (`arclink_llm_router.py:1148`, compute the bool, pass to boundary at `:1149`);
   `record_chutes_usage_event` (`arclink_chutes.py:884,940`); api_auth `_llm_router_provider_state`
   (`arclink_api_auth.py:4788`). Default False everywhere so no caller fails open.
4. **Fail-closed = demote (default).** When the flag is present but unauthorized, the boundary
   ignores it ⇒ real-budget enforcement (a spoofing Pod with budget 0 → 402 `budget_unconfigured`
   on the existing path; no new code path, no upstream call). Write a redacted
   `llm_router:budget_policy_demoted` event (deployment_id, authorized=False, no secrets/prompt).
5. **Regressions (local, fail-closed):** authorized Operator → `unlimited` + inference succeeds +
   `used_cents` preserved; Captain Pod with spoofed `budget_policy=observe_only_unlimited` → NOT
   unlimited, capped, no upstream call, redacted event written; provider-state for the same
   spoofing Pod renders capped (`limit_enforced:true`, not `unlimited`) — same truth as the
   router; missing/empty operator-agent settings → unauthorized (fail-closed). Update the
   existing boundary test `test_chutes_boundary_operator_observe_only_unlimited_is_metered_but_never_blocked`
   (`tests/test_arclink_chutes_and_adapters.py:527`) to pass `observe_unlimited_authorized=True`
   and add an unauthorized companion.
6. **Live:** unchanged — `PG-PROVIDER` / GAP-031; no live Chutes call introduced.

### Symphony anchor
- `Inference And Router Policy`: "letting the Operator remain effectively unlimited but still
  observable… The Operator lane is now explicitly **metered but unlimited**… so Operator Raven
  inference is observable like a Captain Pod yet never silenced by a cap." (Preserve the lane.)
- `Identity, Access, And Session Governance`: "Admin and Operator actions should never trust
  client-asserted privilege… without server-side authorization" and "the same action cannot be
  made safer or more dangerous merely by choosing chat instead of dashboard." (Authorize the
  privilege server-side; keep surfaces in lock-step.)
- Fail-closed default `0 means fail-closed-until-a-per-Pod-budget-is-set` (`Inference And Router
  Policy`) — demotion inherits this for free.

### Effort / blast-radius
**med.** Touches `arclink_chutes.py` (boundary signature + one conditional),
`arclink_operator_agent.py` (one helper), three call sites (`arclink_llm_router.py`,
`arclink_chutes.py` usage-ingest, `arclink_api_auth.py`), the canonical doc
(`docs/arclink/public-agent-gateway.md` / symphony note), and ~4 focused tests. Blast radius
is contained: default-False keeps every non-Operator path fail-closed; the only behavior change
for legitimate traffic is the Operator Pod (which is authorized) — Captain Pods are unaffected
unless one was already (mis)carrying the flag, in which case demotion is the intended fix.

---

## DECISION 2 — Mid-stream error SSE frame after valid chunks  [AGREE-CODEX]

### The question
After valid stream chunks have been yielded, an upstream failure cannot change the already-200
HTTP status. The router currently appends ONE terminal `data:` SSE frame carrying
`{"error":{...}, "arclink_router":{… "streaming_fallback":"unavailable_after_stream_started" …}}`
then returns without `[DONE]` and without replaying fallback (`arclink_llm_router.py:1837-1855`;
no-replay guard `yielded_any` `:1816`). Changing this partial-stream wire shape could break
existing data-frame clients, so it needs an explicit contract decision: ratify as-is, switch to
`event: error`, or close-only.

### My independent reasoning (symphony + code)
The symphony settles the *intent* directly: "once a stream has started, the router labels
fallback as unavailable instead of replaying a partially delivered request" — the current code
is the literal implementation of the North Star. Replaying fallback after chunks is explicitly
forbidden by the symphony (duplicate/partial answers, confused billing) and the code already
forbids it. And `Notifications, Incidents, And Evidence`: "ArcLink should never fail silently"
+ "No raw stack traces, secrets… or prompt/completion payloads in public artifacts." The
current frame is the *non-silent* failure signal, and it is sanitized (`_safe_upstream_error`
→ `redact_then_truncate`, verified no `cpk_live`/prompt leakage in
`test_chat_partial_stream_failure…`), with usage settled `failed` in the `finally` block
(`:1856-1869`) and no leaked reservation (test asserts `open_reservations == 0`).

Weighing the three options against the code reality: HTTP status is irreversibly committed once
the first chunk ships, so an out-of-band failure channel is impossible — the signal MUST be
in-band. **Close-only** is OpenAI-pure but, to a weak client, an early close is indistinguishable
from a successful truncated stream → silent failure, which the symphony forbids. **`event: error`**
is more SSE-native but is a *breaking* change for any existing client parsing `data:` frames —
and the same JSON shape already rides in the `data:` frame, so the SSE-native variant buys
little and costs compatibility. The current `data:`-frame-with-error is explicit, sanitized,
auditable, state-preserving, and OpenAI-compatible enough that a standard client still receives
parseable JSON. The right move is to **ratify v1** and treat it as a documented ArcLink
OpenAI-compat extension; if a strict-client need ever arises, negotiate a NEW mode via header
rather than mutating v1 (this also honors `Configuration, Schema, And Migration`: "bot command
schemas… remain compatible within a release or fail with a clear upgrade requirement").

### Agree / differ from Codex
- **Agree fully.** Codex's recommendation is exactly right and symphony-grounded: ratify the v1
  terminal-`data:`-error-frame contract, do NOT switch to `event: error` or close-only in place,
  strengthen the streaming tests, document as an ArcLink OpenAI-compat extension, and add any
  strict-compat mode later via a negotiated header — never by mutating v1.
- **One concrete addition (not a disagreement):** the current
  `test_chat_partial_stream_failure_settles_without_prompt_or_secret_storage`
  (`tests/test_arclink_llm_router.py:1724`) already asserts the first chunk arrives, the
  terminal `upstream_unavailable` frame is present, failed settlement, no leaked reservation, and
  no secret/prompt persistence — i.e. ~80% of Codex's "strengthen tests" ask is ALREADY landed.
  The genuinely-missing assertions are: (a) **no `[DONE]` sentinel after the error frame**
  (today only success-path tests at `:1379,:1663` assert `[DONE]`; the partial-failure test does
  not assert its absence); (b) **chunk-then-error ordering** (error frame is the LAST frame, after
  the real chunk); (c) the `streaming_fallback == "unavailable_after_stream_started"` label is
  present in the terminal frame's `arclink_router` block. These are small additions to the
  existing test, not new infrastructure.

### FINAL PLAN
1. **Ratify v1 as the wire contract.** Keep `arclink_llm_router.py:1837-1855` as-is: after any
   chunk is yielded, emit exactly one terminal `data:` SSE frame containing an `error` object +
   sanitized `arclink_router` metadata with `streaming_fallback:"unavailable_after_stream_started"`,
   then close. No `[DONE]` after router-side failure. No fallback replay after first chunk.
2. **Finish the test (low effort, additive to the existing test):** assert (a) the error `data:`
   frame is the final frame and NO `data: [DONE]` follows it, (b) chunk precedes the error frame
   (ordering), (c) the terminal frame's `arclink_router.streaming_fallback ==
   "unavailable_after_stream_started"`, plus the existing failed-settlement / no-leaked-reservation /
   no-secret-or-prompt-persistence assertions (already present).
3. **Document it** as an explicit ArcLink OpenAI-compatible streaming extension in
   `docs/API_REFERENCE.md` (and the OpenAPI/router contract note): on post-chunk upstream
   failure the stream terminates with a sanitized in-band `data:` error frame and no `[DONE]`;
   clients should treat a terminal frame carrying `error` as a failed completion.
4. **Future strict-compat (explicitly deferred, not now):** if a strict OpenAI client ever needs
   `event: error` or close-only, add it as a negotiated mode via a request header / new content
   negotiation — never by mutating the v1 default shape.

### Symphony anchor
- `Inference And Router Policy`: "once a stream has started, the router labels fallback as
  unavailable instead of replaying a partially delivered request."
- `Notifications, Incidents, And Evidence`: "ArcLink should never fail silently" and "No raw
  stack traces, secrets… or prompt/completion payloads in public artifacts."
- `Configuration, Schema, And Migration`: "…web clients, bot command schemas… remain compatible
  within a release or fail with a clear upgrade requirement." (Any future change rides a
  negotiated mode, not a silent v1 mutation.)

### Effort / blast-radius
**low.** No schema change, no production code change (ratification of existing behavior); ~3
added assertions to one existing test + doc lines. Blast radius is documentation/contract: it
*pins* a public wire shape that API clients may already depend on, which is the point — pinning
removes the risk of an accidental future mutation.

---

## STANDING DISAGREEMENTS (genuine operator forks)

**NONE that block the plan.** Both decisions converge with Codex. One optional, explicitly-deferred
product knob the operator MAY later choose, recorded so it is not lost:

- **Loudness of the unauthorized-unlimited rejection (Decision 1).** Default is silent demotion
  to the capped lane + a redacted audit event (minimal blast radius, no new public error code).
  If the operator prefers a louder, explicit refusal, a config-gated `403
  budget_policy_not_authorized` (Codex's original default) can be layered on top WITHOUT changing
  the security outcome. This is a UX/operability preference, not a security fork — both options
  fail closed.

<<<DECIDED-END CANON-16>>>
