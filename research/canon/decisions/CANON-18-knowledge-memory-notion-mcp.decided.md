# CANON-18 — Knowledge / Memory / Notion / MCP — DECIDED (final adjudication)

- Piece: CANON-18 (Knowledge / Memory / Notion / MCP)
- Adjudicator: Claude Opus 4.8 (1M), DECISION mode — code re-opened for every call
- Codex proposal under review: `research/canon/decisions/CANON-18-knowledge-memory-notion-mcp.codex.md`
- Method: form an independent view from symphony + code first, then converge with Codex.
  Code wins over comment, name, or prior claim. Every cite below was re-opened in this repo.

Both deferred items share one root cause that the reconciled record already fixed in
framing: **under Tailscale Funnel the Notion webhook backend is not a loopback-only
service** — `bin/tailscale-notion-webhook-funnel.sh:290` proxies the *entire* backend
(`http://127.0.0.1:8283`) at root `/`, and `backend_client_allowed` returns True for
loopback (`arclink_control.py` loopback gate), so every public caller that reaches the
Funnel is "loopback" to the handler. HMAC + the operator-armed token state machine are
the real gate, and `/health` + every other path are publicly reachable. Both decisions
must therefore move the code so the **public Funnel surface equals the actual webhook
contract and fails closed**, not merely tighten in-process Python.

---

## DECISION 1 — Notion verification-token first-caller authenticity under public Funnel

[VERDICT: refine] (agree with Codex's direction and both legs; tighten the nonce
mechanism, make confirmation-gating the load-bearing control, and split the effort so
the high-value/low-blast leg ships first.)

### The question
Under public Funnel, "first caller wins" the operator-armed install window is a workflow
trust problem. The NF1 race (two concurrent armed POSTs both see empty `stored` and the
later `ON CONFLICT` write wins — `arclink_notion_webhook.py:224-258`,
`arclink_control.py` `settings` upsert) is fixed by `BEGIN IMMEDIATE`, but an external
caller can still win the window and install *their* token, after which a valid HMAC is
sufficient to drive reindex work. Fully preventing arbitrary first POSTs needs a product
decision (nonce-bearing URL and/or gating signed events on operator confirmation).

### Independent reasoning (symphony + code)
Two distinct exposures, with different blast radius — the fix must address both:

1. **Install-window capture.** While armed, anyone who reaches the Funnel can POST a
   `verification_token` and win. `handle_verification_token_post`
   (`arclink_notion_webhook.py:211-275`) gates only on (a) no token already stored and
   (b) the armed window being open — both are global booleans, nothing ties the POST to
   *this operator's setup act*. The symphony's identity section is explicit that the same
   action "cannot be made safer or more dangerous merely by choosing chat instead of
   dashboard" and demands "nonce/confirmation" consistency. The operator's setup URL
   should be the *local source of authority* (symphony: "every step has a local source
   owner") — today the URL is public and bears no operator-minted proof.

2. **Forged signed events after capture.** This is the larger harm and the code confirms
   it is currently ungated: `store_notion_event` (`arclink_control.py:12409-12423`) and
   `process_pending_notion_events` (`arclink_control.py:19542+`) never read
   `notion_webhook_verified_at`. So `webhook-confirm-verified` is today a *status marker*,
   not an *enforcement gate*. A stored token + valid HMAC alone drives full reindex / qmd
   work. The symphony's Third-Party Integration Boundaries section makes Notion event
   trust ArcLink's to own ("ArcLink owns shared-root expectations, SSOT broker
   permissions, destructive-operation refusal"); accepting and acting on signed events
   before the operator has confirmed the subscription in Notion violates "fails closed"
   and "preserve state by default."

A nonce alone protects install but still lets an *accidentally* armed/installed token
process events without operator confirmation. Confirmation-gating alone stops forged
reindex but still lets a public DoS consume the one install window (re-arm churn). Both
are needed; they are independent and compose. Origin/IP checks are correctly rejected —
Funnel collapses callers to loopback. This matches Codex.

### Where I agree / differ from Codex
- **Agree** on both legs (nonce on the handshake URL; confirmation-gate signed events
  before `store_notion_event`), the symphony anchors, "fail closed," state preservation
  (installed-but-unconfirmed becomes *blocked/warned*, not deleted), and that live proof
  is `PG-NOTION`.
- **Refine 1 (sequencing / blast radius):** the two legs have very different value/risk.
  **Leg B (confirmation-gate) is the high-value, low-blast change** — it closes the
  forged-reindex hole with a single guard and a `412` and no URL/installer rewrite, and
  it makes the *existing* `webhook-confirm-verified` step finally mean something. Ship Leg
  B first. **Leg A (nonce-bearing URL) is medium-blast** — it touches `ctl`, `deploy.sh`
  copy, the public-URL contract, and `do_POST` query parsing, and its residual risk is
  operator leakage of the URL. Treat Leg A as the follow-on, not a prerequisite. Codex
  bundled them as one med item; I split them so the operator can land the safety win
  immediately.
- **Refine 2 (nonce mechanics):** store only the nonce **hash** (Codex says this — keep
  it), enforce **one-shot consumption** (clear on first stored token, which the armed
  state already does) AND a **TTL equal to the armed window** so a leaked URL dies with
  the 30-minute window, and reject on missing/wrong nonce with `412` (not `403`) to match
  the existing not-armed contract and avoid leaking whether a nonce exists. The nonce must
  be compared with `compare_digest` against the stored hash. Do **not** put the raw nonce
  in any `note_refresh_job` note or status output (only "armed with nonce: yes").
- **Refine 3 (don't break the non-nonce lane):** the multi-tenant control-node lane
  (`deploy.sh:11119-11120`) and any existing armed install without a nonce must still
  work. Make the nonce **required only when one was minted** (armed-with-nonce sets a
  `..._armed_nonce_hash` setting; absence == legacy armed-without-nonce still honored).
  This keeps reconfigure/old-state safe per the migration contract.

### FINAL PLAN
Leg B (ship first, low blast):
1. In `arclink_notion_webhook.py do_POST`, on the signed-event path (after HMAC verify,
   before `store_notion_event` at `:384`), read `NOTION_WEBHOOK_VERIFIED_AT_KEY`; if empty,
   return `412 PRECONDITION_FAILED` `{"error":"webhook not operator-confirmed; run
   arclink-ctl notion webhook-confirm-verified"}` and queue nothing. Token is preserved;
   nothing is deleted.
2. Add local tests: signed event rejected (412, no row) before `webhook-confirm-verified`;
   accepted after; existing token state untouched on rejection. Status copy in
   `health.sh:2257` already warns "operator confirmation is still pending" — reuse it.

Leg A (follow-on, med blast):
3. `webhook-arm-install` (`arclink_ctl.py:2708`, `arm_verification_token_install`
   `arclink_notion_webhook.py:123`) mints a high-entropy nonce, stores only
   `sha256(nonce)` in a new `..._armed_nonce_hash` setting, returns a temp public URL
   `…/notion/webhook?install_nonce=…`. `deploy.sh notion-ssot` arms *before* printing the
   exact URL (it already arms then prints — extend it to print the nonce-bearing URL).
4. `do_POST` parses the query string; `handle_verification_token_post` takes the candidate
   nonce; if `..._armed_nonce_hash` is set it must match via `compare_digest` or `412`.
   On successful store, the armed state + nonce hash are cleared as today (one-shot).
5. Tests: nonce required when minted; one-shot consumption; legacy armed-without-nonce
   still installs; wrong/missing nonce → 412.

### Symphony anchor (quoted)
- **Identity, Access, And Session Governance**: "Rate limits, replay protection,
  nonce/confirmation, channel allowlists, and reason capture should be consistent enough
  that the same action cannot be made safer or more dangerous merely by choosing chat
  instead of dashboard."
- **Third-Party Integration Boundaries**: "Notion owns external pages/databases; ArcLink
  owns shared-root expectations, SSOT broker permissions, destructive-operation refusal,
  and user-OAuth limitations." Plus the governing rule "every step … FAILS CLOSED" and
  "preserve state by default."

### Effort / blast-radius
- Leg B: **low** — one guard + one status read + tests; touches `arclink_notion_webhook.py`
  do_POST only; no public-URL or installer change; pure additive fail-closed.
- Leg A: **med** — `arclink_notion_webhook.py:123/211`, `arclink_ctl.py:2708`,
  `bin/deploy.sh:1074-1090` copy, public-URL contract, webhook tests. Residual risk:
  operator URL leakage, bounded by TTL + one-shot. Combined effort: **med**.

---

## DECISION 2 — Webhook `/health` stays pre-auth

[VERDICT: refine] (agree the in-process `/health` route stays pre-auth and the real fix is
exposure, but the concrete code reality is stronger than Codex stated: the dedicated
Funnel script today publishes **root `/`** and the health checker *asserts root* while
*claiming* "only the configured Notion webhook route." That is a same-truth-across-surfaces
violation that must be fixed, not just "stop treating root as public.")

### The question
`/health` is answered before the loopback guard (`arclink_notion_webhook.py:330-333`) and
`tests/test_loopback_service_hardening.py:74-80` pins that order. Changing it would affect
health/monitoring. Should `/health` stay pre-auth?

### Independent reasoning (symphony + code)
Yes, keep the in-process `/health` route pre-auth — it is the boring local/container
liveness contract (`bin/health.sh:2232`, Docker/systemd probes), it returns a static
non-sensitive body (`{"ok": true, "service": "arclink-notion-webhook"}`), and
authenticating it would break loopback/container probes for zero security gain on a
loopback-only socket. The symphony's Observability section wants "Health is layered …
control process health … bot webhook health" — a local liveness route is exactly that.

The real defect is **public exposure of paths other than the webhook**, and the code is
worse than the deferral note implies:
- `bin/tailscale-notion-webhook-funnel.sh:290` runs
  `tailscale funnel … "http://127.0.0.1:${ARCLINK_NOTION_WEBHOOK_PORT:-8283}"` — proxying
  the **whole backend at root `/`**. `verify_funnel_config` (`:205-253`) and
  `ensure_no_conflicting_funnel_service` (`:148-200`) both *require* the handler be at
  `/` proxying the whole backend ("owned" only if `len(handlers)==1 and "/" in handlers`).
- `bin/health.sh:574` likewise matches `handlers.get("/")` and then prints
  `pass "Tailscale Funnel publishes only the configured Notion webhook route"`
  (`:589`). **That pass message is false** — root `/` exposes `/health` and any future
  path publicly. This is precisely the symphony's cardinal sin: "same truth across
  surfaces" broken, and it does **not** fail closed (it silently publishes liveness +
  adjacent paths and reports success).
- Path-scoping is already available and used elsewhere: the multi-path control-node lane
  at `bin/deploy.sh:11119-11120` uses `tailscale funnel … --set-path="$notion_path"
  "http://127.0.0.1:$notion_port$notion_path"`. And the canonical path var already exists:
  `TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH` defaults to `/notion/webhook`
  (`bin/common.sh:269`, `bin/deploy.sh:77`), and `check_notion_webhook_funnel` already
  *accepts* a `funnel_path` argument (`bin/health.sh:524`) — the plumbing is half-built;
  the dedicated funnel script just doesn't use it.

So the fix is not new capability — it is making the dedicated webhook Funnel script use
`--set-path="$TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH"` (default `/notion/webhook`) and
making both verifiers (funnel script + health) assert the **path-scoped** handler, so
root and `/health` are *not* published, and root exposure becomes a **health
warning/failure** instead of a green "only the webhook route" lie.

### Where I agree / differ from Codex
- **Agree**: keep `/health` pre-auth and static; keep the test-asserted order; keep local
  + Docker health unchanged; path-limit the Funnel to `/notion/webhook`; fail strict
  health if root `/` proxies the backend; anchors are right.
- **Refine 1 (the verifiers currently assert the WRONG thing):** Codex frames this as
  "stop treating root as a public Funnel route" and "fail strict health if root `/`
  proxies." Correct — but the concrete work is bigger than copy: the dedicated funnel
  script's publish command AND both of its `python3` verifier blocks
  (`ensure_no_conflicting_funnel_service`, `verify_funnel_config`) currently *hard-code
  root-`/`-proxies-whole-backend as the success condition*. They must be rewritten to
  expect `handlers.get(funnel_path)` proxying `…$funnel_path`, mirroring the working
  deploy.sh:11119 lane and the health.sh path arg. Until those change, switching to
  `--set-path` would make the script's own verify step fail. This is the load-bearing
  detail Codex's plan implies but doesn't name.
- **Refine 2 (health.sh already half-supports path; finish it consistently):**
  `check_notion_webhook_funnel` takes `funnel_path` but its inner matcher still keys on
  `handlers.get("/")` (`bin/health.sh:574`). Change it to `handlers.get(funnel_path)` and
  treat a root-`/` whole-backend proxy as `warn_or_fail("Tailscale Funnel exposes the
  whole webhook backend at / including /health; expected only $funnel_path")`. That makes
  the "only the configured Notion webhook route" pass message *true*.
- **Agree-with-note (residual):** manually configured non-Tailscale ingress can still
  front-expose `/health`; generated configs + health flag root exposure; external ingress
  proof is `PG-INGRESS`, Notion proof `PG-NOTION`. Keep `/health` body minimal (it already
  is — `arclink_notion_webhook.py:332`).

### FINAL PLAN
1. Keep `do_GET` `/health` pre-auth and static (`arclink_notion_webhook.py:330-333`);
   keep `tests/test_loopback_service_hardening.py:74-80` order assertion. No webhook API
   change.
2. `bin/tailscale-notion-webhook-funnel.sh:290`: publish path-scoped —
   `tailscale funnel --bg --yes --https="$port" --set-path="$funnel_path"
   "http://127.0.0.1:${ARCLINK_NOTION_WEBHOOK_PORT:-8283}${funnel_path}"` where
   `funnel_path="${TAILSCALE_NOTION_WEBHOOK_FUNNEL_PATH:-/notion/webhook}"`. Also turn the
   prior root publish "off" (the `… off` line at `:289`) so the migration drops the old
   root handler.
3. Rewrite the two verifier `python3` blocks in the funnel script to expect
   `handlers.get(funnel_path)` proxying `expected_proxy + funnel_path` (and AllowFunnel
   set), and to treat a surviving root `/` whole-backend handler as a conflict/failure.
4. `bin/health.sh check_notion_webhook_funnel`: key on `handlers.get(funnel_path)` not
   `handlers.get("/")`; on a root-`/` backend proxy, `warn_or_fail` that root (and thus
   `/health`) is publicly exposed. Keep the URL match against
   `ARCLINK_NOTION_WEBHOOK_PUBLIC_URL`.
5. Regression tests: a fixture funnel-status JSON with `--set-path /notion/webhook` passes;
   a root-`/` whole-backend JSON now **fails** (was previously a false pass). Reconfigure
   from an old root-exposed host migrates to path-scoped on next install.

### Symphony anchor (quoted)
- **Observability, SLOs, Capacity, And Scale**: "Health is layered: control process
  health, API/web health, bot webhook health, Stripe webhook health … and proof status."
- **Abuse, Safety, And Platform Boundaries**: "ArcLink should assume that public entry
  points will be poked, spammed, and misused." Plus the cardinal **Cross-Surface
  Experience Standard / Governance** rule: same truth across surfaces and every gate
  **FAILS CLOSED** — the current green "publishes only the configured Notion webhook
  route" while exposing root violates both.

### Effort / blast-radius
**med** — touches `bin/tailscale-notion-webhook-funnel.sh:289-292` + its two embedded
verifier scripts (`:148-253`), `bin/health.sh:521-595`, and funnel-status fixture tests.
Webhook service API is unchanged; the change is migration-aware (old root handler turned
off, new path handler published) and strictly fail-closed-tightening. Blast radius is the
deploy/health Funnel lane only; no Python service contract moves.

---

## NET ADJUDICATION

Both decisions converge with Codex's direction. The binding refinements are:
1. **D1 split + reorder:** the confirmation-gate of signed events (Leg B) is the
   high-value/low-blast win and is currently *missing entirely* in code
   (`process_pending_notion_events`/`store_notion_event` never read
   `notion_webhook_verified_at`) — ship it first as a single fail-closed `412` guard; the
   nonce-bearing URL (Leg A) is the medium follow-on, required only when a nonce is minted
   so the existing multi-tenant/legacy lanes keep working.
2. **D2 names the real defect Codex implied:** the dedicated webhook Funnel script and
   *both* its verifiers, plus `health.sh`, currently hard-code root-`/`-proxies-whole-
   backend as success and falsely report "only the configured Notion webhook route." The
   `--set-path` plumbing already exists (`deploy.sh:11119`, `common.sh:269`,
   `health.sh:524`); finish wiring it so the public surface equals `/notion/webhook` and
   root exposure fails closed.

No standing product fork: both are clear fail-closed tightenings the operator should take.
The only genuinely external residuals are live proof (`PG-NOTION`, `PG-INGRESS`) and the
qmd protocol ratification — none of which block these code changes.
