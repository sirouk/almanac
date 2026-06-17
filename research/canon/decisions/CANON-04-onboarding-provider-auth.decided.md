# CANON-04 — Onboarding & Provider Auth — DECIDED (final adjudication)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, DECISION mode.
Method: formed an independent view per decision against the symphony north star and the
re-opened code, THEN reconciled with Codex (GPT-5.5). Every code claim re-grounded this
session (sed/rg). Symphony is intent; code is reality; the plan moves code toward the
symphony while failing closed.

Inputs read: `research/canon/NEEDS_DECISION.md` (CANON-04),
`research/canon/decisions/CANON-04-onboarding-provider-auth.codex.md`,
`research/canon/reconciled/CANON-04-onboarding-provider-auth.reconciled.md`,
`research/canon/sections/CANON-04-onboarding-provider-auth.md`,
`docs/arclink/sovereign-control-node-symphony.md` (Public Web/Checkout, Captains,
Billing/Entitlements, Third-Party Boundaries, Secrets/Keys/Rotation, Config/Schema/Migration).

---

## DECISION 1 — NEW onboarding should reach a real terminal `completed` state

**[VERDICT: refine]** (right direction; tighten the mechanism and shrink the blast radius)

### The question
`record_arclink_onboarding_first_agent_contact` writes `status="first_contacted"`
(`python/arclink_onboarding.py:887-895`), which is the furthest-forward status the NEW
machine ever assigns. `completed` is declared in the status enum
(`python/arclink_control.py:1389`) and the active partial unique index treats
`first_contacted` as still-active (`python/arclink_control.py:2310-2322`), but no code
ever sets `completed`. Should NEW onboarding transition to a real terminal `completed`?
This is a public state-contract + index behavior change.

### My independent reasoning (code-grounded)
The symphony wants "the same truth across surfaces" and a session that "cannot be
hijacked without the required proof token." Leaving a successfully-launched Captain
forever in an *active* status is a live defect, not cosmetic: the active partial unique
index `idx_arclink_onboarding_active_identity` (`arclink_control.py:2310`) includes
`first_contacted`, so a launched session permanently **occupies the active identity slot**
for `(channel, channel_identity)`. That blocks `force_new=False` resume/re-onboard for
the same channel identity (e.g. a Captain buying an Additional Agent later on the same
Telegram account) — the dead-but-active row is a real contract bug.

Crucially, I re-opened the routing code to bound the blast radius, and it is *smaller*
than Codex's report implies:
- `arclink_dashboard.py:1641` already treats BOTH `first_contacted` and `completed` as
  "first contact made" (`str(session["status"]) in {"first_contacted", "completed"}`).
  The dashboard already tolerates the move.
- The public-bot post-launch router `_latest_session_for_contact`
  (`arclink_public_bots.py:1982-2030`) ranks a session **rank 0 when the JOINed
  DEPLOYMENT status is ready** (`d.status IN ready_placeholders`, i.e. `active` /
  `first_contacted` — a *deployment* status, `arclink_public_bots.py:280`), independent
  of the *session* status. So a session moved to terminal `completed` still wins
  selection via its ready deployment. Routing degrades gracefully, it does not break.
- The CASE orderings at `arclink_public_bots.py:2061` and `:2178` operate on
  `arclink_deployments.status`, NOT session status — moving the session terminal does not
  touch them.

So the only behaviors that genuinely change are (a) the active-identity index frees the
slot once a session is `completed` (the desired fix), and (b) anything that *reads
session status expecting `first_contacted`*. The migration must therefore keep `completed`
recognized everywhere `first_contacted` is recognized as "done" — which the dashboard
already does; the audit just has to confirm `_latest_session_for_contact` still resolves.

Where I refine Codex: Codex says "On first contact, **require a paid/provisioning-ready
linked deployment** [and] write `status='completed'`." Requiring a strict precondition
inside the first-contact callback risks **failing closed too hard** on the legitimate
launch path — if the deployment row already advanced to `active` (past
`provisioning_ready`) by the time first-contact fires, a naive "must equal
provisioning_ready" check rejects a real launch. The right guard is: the session must be
non-terminal AND must have a linked deployment that is in a *provisioned-or-beyond* state
(`provisioning_ready`, `provisioning`, `first_contacted`, or `active` — i.e.
`arclink_deployment_can_provision` already passed). Fail closed on a terminal session
(no resurrection — this also fixes N3), but do not fail closed on a session whose
deployment is *further* along than `provisioning_ready`.

### Agree / differ from Codex
- AGREE: `completed` is the canonical terminal success; keep `first_agent_contact` as the
  event/`current_step`; set `completed_at`; drop `first_contacted` from the active index;
  add an old-state migration; cover `_latest_session_for_contact`, dashboard bot-contact,
  worker callback, and old-state fixtures. (The `completed_at` column already exists,
  `arclink_control.py:1405` — no column add needed.)
- DIFFER (refine): replace Codex's "require provisioning-ready linked deployment" with a
  **terminal-guard + provisioned-or-beyond** precondition so the launch path cannot be
  starved by a deployment that legitimately advanced past `provisioning_ready`. Add the
  terminal guard inside `record_arclink_onboarding_first_agent_contact` (it currently
  calls `_update_session` directly with no `_active_session_or_error`, resurrecting
  terminal sessions — this is the open N3 fail-mode; fixing it here is the same edit).
- DIFFER (scope): do NOT drop `payment_pending`/`paid` from the index/enum in this
  decision — they are separately dead (no NEW write sets them) and removing them is a
  distinct enum-narrowing change; keep this decision surgically about
  `first_contacted → completed`.

### FINAL PLAN
1. In `record_arclink_onboarding_first_agent_contact` (`python/arclink_onboarding.py:880`):
   - Load the session via `_active_session_or_error` (or an explicit terminal check) so a
     terminal/expired session **raises** instead of being silently resurrected to an
     active status (closes N3).
   - Look up the linked deployment; require it to be provisioned-or-beyond
     (`arclink_deployment_can_provision` already true OR `d.status IN
     {provisioning_ready, provisioning, first_contacted, active}`). If not, fail closed
     with a redacted event (do not write `completed`).
   - Write `status="completed"`, `completed_at=now`, keep `current_step="first_agent_contact"`,
     and keep recording the existing `first_agent_contact` event. Leave the deployment row
     unchanged (deployment lifecycle is CANON-08's).
2. Schema/index (`python/arclink_control.py:2310-2322`): drop `first_contacted` from
   `idx_arclink_onboarding_active_identity` so a completed/launched session frees the
   active identity slot. Keep the enum CHECK (`:1389`) unchanged — `completed` is already
   allowed.
3. Migration (idempotent, old-state-fixture-tested): backfill existing
   `status='first_contacted'` rows that have a ready/launched deployment to
   `status='completed'` with `completed_at` set from the `first_agent_contact` event
   timestamp (or `updated_at` fallback); preserve user/deployment/metadata. Recreate the
   active-identity index without `first_contacted`. Because the schema mechanism today is
   a single idempotent `ensure_schema()` with `*__new` rebuild migrations (symphony
   Config/Schema section), implement this as an in-place backfill + index drop/recreate
   guarded to run once, consistent with the existing rebuild-migration pattern.
4. Tests: old-state fixture (a `first_contacted` row → migrates to `completed`),
   `_latest_session_for_contact` still resolves a completed-session/ready-deployment to
   rank 0, dashboard `bot_contact` still reports contacted, terminal-guard rejects
   resurrection, worker callback writes `completed` end-to-end.
5. Docs/OpenAPI: update the onboarding status contract to name `completed` (not
   `first_contacted`) as terminal success, in lock-step with the release.

### Symphony anchor
"Configuration, Schema, And Migration" — *"Database schema changes are migration-aware,
idempotent, reversible where practical, and tested against old-state fixtures."* Also
"Public Web, Account, And Checkout" — *"Onboarding ... creates a claimable session that
cannot be hijacked"* (a never-terminal session keeps the identity slot occupied,
undermining clean re-claim/resume).

### Effort / blast-radius
**med.** Blast radius: the index + the one callback + the migration + status-contract
docs. Bounded by the fact that dashboard already accepts `completed` and the public-bot
router selects on deployment status, not session status, on the post-launch path.

---

## DECISION 2 — OLD completion must stop putting the dashboard password in chat

**[VERDICT: agree-codex]** (with one mechanism precision: reuse the existing reveal rail,
do not invent a parallel one)

### The question
`completion_message_bundle` puts the plaintext shared dashboard password into `full_text`
for Discord/Telegram/web (`python/arclink_onboarding_completion.py:411-432,440-456`),
relying on a best-effort scrub-on-ack (user clicks a button; the bot edits the message).
If ack never fires, the password persists in chat history. Replacing this needs a product
flow decision.

### My independent reasoning (code-grounded)
The symphony is unambiguous and absolute here: *"Public docs, chat transcripts, logs,
evidence artifacts, command arguments, and generated markdown must never contain secret
values"* and *"Secret references move through provisioning instead of plaintext values."*
Scrub-on-ack is a best-effort mitigation of a contract violation — the secret is in the
transcript the instant the message is sent, and chat platforms retain history regardless
of a later edit. This fails the "fail closed" and "never in chat transcripts" tests. It
must change.

The decisive code reality (which makes this *much* cheaper than Codex's "high / generalize
schema" framing): **the correct rail already exists and already has the exact shape the
symphony demands.** `arclink_credential_handoffs` (`arclink_control.py:1110-1126`) already
carries `secret_ref`, `status IN (available|removed|expired)`, `expires_at`,
`revealed_at`, `acknowledged_at`, `removed_at`, `metadata_json`. The Raven reveal flow
(`arclink_public_bots.py:3551-3760`) already: binds reveal to a **private channel**
(rejects non-private with `credentials_reveal_unavailable`), is **reveal-once**
(`revealed_at` gate, `:3657`), resolves the secret from a host secret-ref path rather than
storing it in the row (`_resolve_revealable_credential_secret`,
`arclink_api_auth.py:1931-1947`), records a **redacted** event
(`public_bot:dashboard_credential_revealed`, `:3711`), and supports ack/remove + TTL
expiry (`expire_revealable_user_material`). This is the symphony's "status without
disclosure" + "reference moves through provisioning" rail, already proven for the NEW
public-Raven path. The OLD path should converge onto it, not grow a second one.

The one real gap is the **subject/key mismatch**, which I verified:
- The Raven rail keys on `arclink_credential_handoffs.deployment_id` (NOT NULL) +
  `credential_kind`, unique index `(deployment_id, credential_kind)`
  (`arclink_control.py:2092-2093`). The OLD curator path is **agent-based**: the bundle is
  built from `session["linked_agent_id"]`, the agent's `unix_user`, and `hermes_home`
  (`arclink_onboarding_completion.py:464-510`), and the password is read live from
  `access-state.json` on disk (`access = load_access_state(hermes_home)`,
  `arclink_onboarding_completion.py:475` via `arclink_agent_access.py:36-42`) — already a
  0600, agent-owned private file, NOT a `secret://...` ref the NEW resolver reads.
- So reuse needs: (a) a non-null subject for the OLD path — either a deployment surrogate
  or a generalized `subject_kind`/`subject_id` (e.g. `agent_id`) — and (b) a resolver
  branch in `_resolve_revealable_credential_secret` that, for the OLD/agent subject,
  reads the password from the agent's `access-state.json` (or a written `secret://`
  file) instead of the dashboard-user password path.

Because the password is **already in private on-disk state**, the change is "stop copying
it into chat text + point a handoff row at it," not "build a secret store." That is the
load-bearing simplification over Codex's "high effort / generalize schema" estimate —
though I keep Codex's verdict because the cross-surface wiring (Telegram + Discord
callbacks + curator flow + tests + PG-BOTS live proof) is genuinely broad.

### Agree / differ from Codex
- AGREE: remove `access["password"]` from `full_text`; replace scrub-on-ack with a
  reveal/ack/audit handoff record; private-channel bound; TTL; `revealed_at`/
  `acknowledged_at`/`removed_at`; add a reissue/rotate path rather than reopening removed
  handoffs; cover completion-message tests + bot live proof under `PG-BOTS`.
- AGREE-AND-SHARPEN: "Generalize `arclink_credential_handoffs` beyond deployment-only
  targets" — yes, but the minimal generalization is a nullable/aliased subject
  (`subject_kind` defaulting to `deployment`, plus `agent_id`/`unix_user` columns, or a
  synthetic deployment surrogate) **plus** a resolver branch reading the OLD password from
  `access-state.json`. Do NOT fork a second handoff table/helper — converge on the
  existing rail so both surfaces have "the same truth."
- No disagreement on direction or severity.

### FINAL PLAN
1. `arclink_onboarding_completion.py:completion_message_bundle` (`:307`): stop emitting the
   password. Remove the `Shared password: <password>` lines from `full_text`
   (`:411-432,440-456`); the message instead tells the Captain to reveal credentials in a
   private chat (Telegram private / Discord ephemeral), matching the NEW Raven copy. Keep
   `scrubbed_text` as the only persisted completion text.
2. Create/ensure a credential-handoff row for the OLD completion: generalize
   `arclink_credential_handoffs` to a non-deployment subject (add `subject_kind TEXT
   DEFAULT 'deployment'` + `agent_id`/`unix_user`, or mint a deployment surrogate for the
   curator agent), so the OLD `linked_agent_id` Hermes-home password gets a row with
   `credential_kind='dashboard_password'`, TTL, `available` status. Idempotent migration,
   old-state fixtures (symphony Config/Schema contract).
3. `_resolve_revealable_credential_secret` (`arclink_api_auth.py:1931`): add a branch for
   the OLD/agent subject that resolves the password from the agent's `access-state.json`
   (`load_access_state(hermes_home)["password"]`) — or, preferably, write that password to
   the same `secret://arclink/dashboard/.../password` file shape the NEW resolver already
   reads, so one code path serves both. Keep the reveal-once + private-only + redacted-
   event guarantees unchanged.
4. Reuse the existing reveal/ack/remove flow (`arclink_public_bots.py:3640-3760`) and its
   private-channel enforcement for the OLD curator surfaces; add a `/credentials`-style
   reveal entry to the curator completion message and Telegram/Discord callbacks.
5. Reissue/rotate path: a `removed`/expired handoff is re-mintable (new row) rather than
   reopened, matching Codex's recovery-friction mitigation.
6. Tests: completion bundle no longer contains the password (assert absence in
   `full_text`); reveal works only in private; reveal-once; ack/remove; event is redacted.
   Live bot reveal under `PG-BOTS`.

### Symphony anchor
"Secrets, Keys, And Rotation" — *"Public docs, chat transcripts, logs, evidence artifacts,
command arguments, and generated markdown must never contain secret values"* and *"Secret
references move through provisioning instead of plaintext values."* Reinforced by
"Third-Party Integration Boundaries" — *"No third-party credential should be printed in
chat ... Every integration must have three visible states: configured and locally valid,
configured but live-proof pending, or missing and blocked"* (the reveal rail's
`available`/`removed`/`expired` + private-only reveal is exactly status-without-disclosure).

### Effort / blast-radius
**high.** Blast radius: curator completion message + Telegram/Discord callbacks +
credential-handoff schema generalization + resolver branch + completion-message tests +
PG-BOTS live proof. Lowered from "build a secret store" because the password is already in
private on-disk state and the reveal rail already exists — the work is convergence, not
greenfield.

---

## DECISION 3 — Checkout reserves locally, but materializes deployments only after paid Stripe proof

**[VERDICT: refine]** (Codex's split is correct; refine the compat surface and the
fail-closed ordering, and fold in the already-landed webhook-atomicity fix)

### The question
`open_arclink_onboarding_checkout` calls `prepare_arclink_onboarding_deployment` BEFORE
Stripe (`python/arclink_onboarding.py:656`), and the reserve helpers commit
`arclink_deployments` rows at `entitlement_required` immediately
(`prepare...` writes rows then `open...` calls Stripe). If Stripe `create_checkout_session`
throws (`:664`, no try/except — N4), the run leaves orphan `entitlement_required`
deployment rows with no checkout. Should checkout reserve locally but materialize
deployments only after paid Stripe proof?

### My independent reasoning (code-grounded)
The symphony's Billing section: *"Entitlement state gates provisioning and provider
continuation"*; Public Web: *"Checkout, cancellation, success, portal, failed payment,
refund/cancel, and refuel all resolve into entitlement state before provisioning can
continue."* And the ownership split in Third-Party Boundaries: *"Stripe owns payment
collection and subscription events; ArcLink owns entitlement interpretation, idempotency,
gating, audit, and recovery."* The current code violates "fail closed + leave redacted
evidence" on the unhappy path: a Stripe failure mid-checkout leaves a half-materialized
`entitlement_required` deployment with no intent record explaining it.

I independently reach the same architecture Codex proposes: a durable **checkout-intent /
prefix-reservation** record committed before Stripe, with deployment-row materialization
deferred to the paid webhook. Reasons the alternatives fail:
- "Wrap `prepare` in rollback": if Stripe *succeeds* but the local rollback already ran
  (or a crash interleaves), you get a paid Stripe session with no local deployment — worse
  than an orphan. Rejected.
- "Stripe first, no local row": a crash after Stripe creation loses local ownership
  evidence (which prefix/user/plan the checkout was for). Rejected.
- A durable intent row before Stripe preserves crash recovery AND ownership evidence
  without minting `entitlement_required` deployments that may never be paid for.

Where I refine Codex:
1. **Prefix reservation is the subtle part.** `prepare...` today reserves the *prefix*
   (`reserve_arclink_deployment_prefix` / `reserve_generated_...`,
   `arclink_onboarding.py:614-635`) as part of creating the deployment row at
   `entitlement_required`. Moving materialization to the webhook means the **prefix must
   still be reserved at intent time** (so the Captain's chosen subdomain isn't taken by
   someone else between checkout and payment), but the *deployment row* must not be the
   thing holding it. So the intent row (or a lightweight prefix-reservation row) owns the
   prefix; the webhook promotes it into real `arclink_deployments` rows. This keeps
   CANON-09 ingress uniqueness honest without orphaning deployments. Codex implies this
   ("checkout-intent/prefix-reservation row") — I'm making the prefix-holding explicit as
   the load-bearing detail.
2. **Compat field.** Tests/callers currently read `deployment_id` off the session during
   checkout (`open...` returns it; web checkout status surfaces it). Codex's
   `planned_deployment_id` compat is right; I add: the deterministic deployment ids are
   already `_stable_id("arcdep", session_id, ...)` (`arclink_onboarding.py:589,598`), so
   the intent can carry the **same deterministic `planned_deployment_id`** that the webhook
   will later materialize — zero id churn, the compat field is the real future id, just
   flagged `materialized=false` until paid proof.
3. **Fail-closed ordering in the webhook.** Materialization in the paid webhook must be
   atomic with entitlement-set + gate-advance in the **same commit** — and this is exactly
   the N1 atomicity fix the repair campaign already landed for the *sync* side
   (reconciled repair-status: "stopped stale-expiry from committing inside caller-owned
   webhook transactions" + "kept onboarding entitlement sync atomic by making the
   deployment gate update part of the same final sync commit",
   `arclink_onboarding.py:355,844,851`). Decision 3's webhook materialization must inherit
   that same single-commit discipline: create deployment rows → set entitlement → advance
   gate → mark intent materialized → advance session to `provisioning_ready`, all in one
   transaction; missing/conflicting intent fails closed with a redacted event and does NOT
   provision.
4. **Idempotency / replay.** The Stripe metadata already carries
   `arclink_onboarding_session_id` and will carry `checkout_intent_id`; the webhook must
   be replay-safe (re-delivery of `checkout.session.completed` must not double-materialize
   — key on intent id + `materialized` flag). This is CANON-07's idempotency contract
   meeting CANON-04's intent.

### Agree / differ from Codex
- AGREE: split checkout-intent/reservation from `arclink_deployments`; commit intent
  before Stripe with `onboarding_session_id` + `checkout_intent_id`; on paid webhook
  atomically create deployments, set entitlement, advance to `provisioning_ready`, mark
  intent materialized; preserve a compat `planned_deployment_id` labeled not-materialized;
  fail closed on missing/conflicting intent with redacted evidence; broad test surface +
  PG-STRIPE live proof.
- DIFFER (refine): make the **prefix reservation** explicitly owned by the intent row (not
  the deployment row) so subdomain uniqueness survives the deferral without orphaning
  deployments; use the **existing deterministic `_stable_id` deployment id** as the compat
  `planned_deployment_id` (no separate id space); and explicitly require the webhook
  materialization to inherit the **already-landed single-commit atomicity** discipline so
  this doesn't reintroduce the N1 partial-commit class.
- No disagreement on direction or that this is high effort.

### FINAL PLAN
1. New durable table (or reuse the session row + a dedicated intent table) for
   **checkout intent**: `intent_id`, `onboarding_session_id`, `user_id`, `plan_id`,
   `planned_deployment_id` (deterministic `_stable_id("arcdep", session_id, ...)`),
   reserved prefix(es), `status IN (open|materialized|cancelled|expired)`, timestamps.
   Idempotent migration + old-state fixtures.
2. Refactor `open_arclink_onboarding_checkout` (`arclink_onboarding.py:645`): replace the
   pre-Stripe `prepare_arclink_onboarding_deployment` call with: `upsert_arclink_user` +
   **prefix reservation only** + commit a checkout-intent row, THEN call
   `stripe_client.create_checkout_session(...)` with metadata including
   `arclink_onboarding_session_id` AND `arclink_checkout_intent_id`. Wrap the Stripe call
   so a failure leaves the intent row in a recoverable `open` state with a redacted
   failure event (closes N4 — no orphan `entitlement_required` deployment).
3. Move deployment-row materialization into the paid path: extend/replace
   `sync_arclink_onboarding_after_entitlement` (`arclink_onboarding.py:799`) so that, on
   `checkout.session.completed` with a valid bound intent, it (in ONE commit) materializes
   the `arclink_deployments` rows from the intent, sets entitlement, advances the gate to
   `provisioning_ready`, marks the intent `materialized`, and advances the session to
   `provisioning_ready`. Inherit the landed single-commit atomicity (no
   `expire_stale(commit=True)` inside the webhook txn).
4. Compat: keep returning `planned_deployment_id` (= the deterministic future id) on the
   checkout response, flagged `materialized=false`; web checkout-status and bot direct
   checkout read it but must not treat it as a live deployment until the webhook lands.
5. Idempotency: webhook re-delivery keys on `checkout_intent_id` + `materialized` so paid
   replay is a no-op, satisfying CANON-07's idempotency ownership.
6. Tests: Stripe-failure path leaves no orphan deployment (intent recoverable); paid
   webhook materializes + gates atomically; replay is idempotent; web/bot checkout status
   shows planned-not-materialized; fake E2E; provisioning dry-run; PG-STRIPE live proof.

### Symphony anchor
"Billing, Entitlements, And Refuel" — *"Entitlement state gates provisioning and provider
continuation."* Reinforced by "Public Web, Account, And Checkout" — *"Checkout,
cancellation, success ... all resolve into entitlement state before provisioning can
continue"* and "Third-Party Integration Boundaries" — *"Stripe owns payment collection and
subscription events; ArcLink owns entitlement interpretation, idempotency, gating, audit,
and recovery."*

### Effort / blast-radius
**high.** Blast radius: new intent schema + onboarding checkout API + Stripe
metadata/webhook sync + public-bot direct checkout + web checkout status + fake E2E +
PG-STRIPE live + provisioning dry-run tests. This is a checkout-ordering redesign, not a
surgical patch — correctly deferred by the repair campaign; ship it as a dedicated change
behind PG-STRIPE.

---

## STANDING DISAGREEMENTS / PRODUCT FORKS FOR THE OPERATOR

None are blocking forks — all three decisions converge to a single recommended plan. The
two operator-facing product judgments worth surfacing (both with a clear recommended
default already baked into the plans above):

- **Decision 2 reveal UX:** whether the OLD curator completion should auto-mint a
  reveal-on-demand handoff (recommended) vs. require the Captain to type a `/credentials`
  command to reveal. Recommended default: auto-mint the row, reveal only on explicit
  private-channel request — never auto-push the secret. This is a copy/UX choice, not a
  security fork.
- **Decision 3 prefix-hold TTL:** how long a reserved prefix is held for an unpaid
  checkout intent before expiry frees the subdomain. Recommended default: reuse the
  existing 24h session TTL so prefix-hold and session expiry stay aligned. This is a
  tuning choice, not an architectural fork.
