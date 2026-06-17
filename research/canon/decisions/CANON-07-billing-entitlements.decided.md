<<<DECIDED CANON-07>>>
# CANON-07 — Billing & Entitlements — FINAL ADJUDICATED DECISIONS

Final adjudicator: Claude Opus 4.8 (1M). Federation DECISION mode — independent view
formed first against `docs/arclink/sovereign-control-node-symphony.md` + re-opened
code, then converged with Codex (GPT-5.5 xhigh)
`research/canon/decisions/CANON-07-billing-entitlements.codex.md`.

Code re-opened to ground every call: `python/arclink_entitlements.py:236-271,416-496,
699-859`; `python/arclink_onboarding.py:655-708`; `python/arclink_control.py:1385-1408,
3835-3932`; `tests/test_arclink_entitlements.py:1202-1257,1569-1600`.

Scope note: the repair campaign already landed 8 fixes (durable-`received` reprocess,
payment-status verification, `mirror_status='none'` mapping, `_assert_entitlement_account`
conflict guard). Exactly ONE item was deferred to the operator: the **first-binding
forged-metadata policy**. That is the only decision below.

---

## DECISION 1 — Forged-metadata first-binding policy when no Stripe customer/subscription is locally bound

[VERDICT: refine] (agree with Codex's direction and almost all of the plan; two
concrete refinements that keep the dominant real path working and make the
fail-closed boundary crisper)

### The question
Today the non-refuel entitlement branch resolves the owning user **metadata-first**
(`_stripe_user_id_or_empty(obj)` then DB fallback, `arclink_entitlements.py:736-743`).
A signed event whose `metadata.arclink_user_id` names a user with NO local binding will:
(a) auto-create that user as `paid` via `set_arclink_user_entitlement` →
`upsert_arclink_user` (`arclink_control.py:3924-3932`), and/or (b) move entitlement and
repoint owned rows through the email merge (`arclink_entitlements.py:758-792` →
`arclink_control.py:3848-3865`). The landed `_assert_entitlement_account`
(`arclink_entitlements.py:433-479`, called `:794-801`) only blocks a *conflict* — a
customer/subscription already bound to a DIFFERENT account. It does NOT stop metadata
from **originating** a first binding to an arbitrary user. Only the webhook HMAC stands
between attacker-influenced (or misconfigured) metadata and an entitlement write. Should
ArcLink keep the wide "any signed event's metadata may first-bind" contract, or require
a local source owner for the first binding?

### My independent reasoning (symphony + code)
The symphony is unambiguous about who interprets Stripe. `Third-Party Integration
Boundaries` states: *"Stripe owns payment collection and subscription events; ArcLink
owns entitlement interpretation, idempotency, gating, audit, and recovery copy."* Stripe
metadata is a *Stripe-side, mutable field* — letting it originate a Captain<->entitlement
binding hands ArcLink's interpretation job to Stripe's metadata. That inverts the
boundary. The North Star reinforces it: *"every step should have a local source owner …
and how it fails closed."* A first binding with no local source owner has no owner and
cannot fail closed — it fabricates one.

The code shows ArcLink already HAS the local source owner for the only legitimate
first-binding path. `open_arclink_onboarding_checkout` writes `user_id`,
`deployment_id`, `client_reference_id=user_id`, and (when the explicit checkout flow
runs) `checkout_session_id` into `arclink_onboarding_sessions` BEFORE Stripe ever fires
the webhook (`arclink_onboarding.py:666-707`; table at `arclink_control.py:1385-1408`,
unique index on `checkout_session_id` at `:2327`). So `checkout.session.completed` can
be proven against local state instead of trusted from metadata. Every *subsequent*
lifecycle event (`invoice.*`, `customer.subscription.*`) arrives after that checkout,
when the subscription mirror (`arclink_entitlements.py:803-819`) and
`arclink_users.stripe_customer_id` are locally bound — so `_stripe_user_id_from_local_state`
(`:236-271`) already resolves them without metadata. The ONLY events that need metadata
to originate a binding are pre-checkout subscription/invoice events, and those should
fail closed and replay until the checkout binds — Stripe redelivers, the row is left
replayable (`_mark_webhook_failed_replayable`), so this is lossless.

Therefore I independently reach Codex's conclusion: **first binding must be
local-source-owned, not metadata-owned.** Metadata may corroborate an existing local
owner; it must never originate or move ownership.

Two refinements emerge from re-opening the code:

- **Refinement A — bind on the onboarding-session link, not strictly on `obj.id ==
  checkout_session_id`.** The dominant real happy path
  (`tests/test_arclink_entitlements.py:1202-1257`) binds via the
  `arclink_onboarding_session_id` metadata key (`:1232`), and the local
  `checkout_session_id` is empty until the webhook *syncs* it
  (`sync_arclink_onboarding_after_entitlement`). Binding strictly on
  `obj.id == arclink_onboarding_sessions.checkout_session_id` (as Codex's first sentence
  reads literally) would reject that path. The proof must accept a match on EITHER (1)
  `obj.id == checkout_session_id` of a local session, OR (2)
  `metadata.arclink_onboarding_session_id` resolving to a local
  `arclink_onboarding_sessions` row, in BOTH cases requiring the local row's `user_id`
  (and, where present, `client_reference_id`/`deployment_id`) to agree with the resolved
  `user_id`. This is still local-source-owned — the onboarding session is local truth;
  metadata only points into it.

- **Refinement B — close the auto-create path explicitly.** The sharp edge is
  `set_arclink_user_entitlement` minting a brand-new `paid` user from a metadata-only
  id (`arclink_control.py:3924-3932`). The rule should be: for a FIRST binding (no local
  user/subscription/customer owner found by DB resolution), entitlement may be written
  ONLY when a local onboarding/checkout owner is proven per Refinement A; otherwise fail
  closed. An existing local user (resolved by DB, or named in metadata AND already
  present locally) keeps working unchanged — metadata corroborating an existing row is
  fine.

### Agreement / difference vs Codex
Agree with Codex on: keep the conflict guard; make `customer.subscription.*` / `invoice.*`
unable to first-bind from metadata alone; existing `arclink_subscriptions` /
`arclink_users.stripe_customer_id` bindings stay authoritative; mismatch fails closed
with redacted evidence (not silent reassign); move the email merge
(`arclink_entitlements.py:758-792`; repoint `arclink_control.py:3848-3865`) BEHIND the
local-source-owner proof because merge is powerful state movement; add an OPERATOR-ONLY
typed recovery action (dry-run + reason + redacted audit) for legitimate imports rather
than an env flag that lets metadata write entitlement; keep live ordering/payload under
`PG-STRIPE`; accept temporary 400/replay for out-of-order pre-checkout subscription
events. I independently re-derived each of these.

Differ from Codex only in the two refinements above: (A) the binding key must be the
onboarding-session link (not strictly `obj.id == checkout_session_id`) or the real happy
path breaks; (B) name the auto-create path (`set_arclink_user_entitlement` →
`upsert_arclink_user`) as the explicit thing to gate, so the fix is unambiguous to the
implementer. These are tightenings of Codex's plan, not disagreements with its
direction.

### FINAL PLAN (converged, code-level)
1. **Add a first-binding resolver split in the entitlement branch** (around
   `arclink_entitlements.py:736-748`). Resolve the owner in this priority:
   (a) DB owner via `_stripe_user_id_from_local_state` (existing subscription mirror or
   `stripe_customer_id`); (b) a proven local onboarding/checkout owner — match on
   `obj.id == arclink_onboarding_sessions.checkout_session_id` OR
   `metadata.arclink_onboarding_session_id` → local session, requiring that session's
   `user_id` to agree with any metadata `arclink_user_id` and with
   `client_reference_id`. Metadata `arclink_user_id` is accepted as the owner ONLY when
   it equals a locally-resolved owner from (a) or (b), or names a user that already
   exists locally. If none of these prove an owner → raise `ArcLinkEntitlementError`
   (fail closed, replayable via the existing `failed`-row path
   `arclink_entitlements.py:617-632`,`:910-919`).
2. **Restrict first-binding to `checkout.session.completed`.** Unbound
   `customer.subscription.*` / `invoice.*` events that cannot resolve a local owner must
   not create or move entitlement; they 400/replay until the checkout binds the
   subscription mirror.
3. **Gate the email merge behind the proof.** Run `merge_arclink_user_identity_by_email`
   (`:758-792`) only after a local owner is proven, so a metadata-supplied candidate can
   never trigger a row repoint as a side effect of a first contact.
4. **Forbid metadata-only auto-create.** Ensure the
   `set_arclink_user_entitlement`/`upsert_arclink_user` path
   (`arclink_control.py:3924-3932`) is reached only with a proven local owner; never mint
   a `paid` user from a metadata id alone.
5. **Keep `_assert_entitlement_account` as the conflict backstop** (unchanged); it now
   runs after a proven owner and still rejects cross-account customer/subscription
   collisions with redacted evidence.
6. **Add an operator-only typed recovery action** (dry-run, reason capture, redacted
   audit, no secrets) for legitimate Stripe-side imports/repairs — the same-truth
   surface (`Operator Raven should see the same state and be able to trigger safe
   recovery actions without seeing secrets`). NOT an env flag.
7. **Tests** (extend `tests/test_arclink_entitlements.py`): unbound subscription
   metadata rejected; locally-opened checkout (both binding-by-`obj.id` and
   binding-by-`onboarding_session_id`) first-binds and stays green
   (`:1202-1257` must still pass); out-of-order `customer.subscription.created` 400s then
   succeeds after checkout binds; metadata-only id does NOT auto-create a paid user;
   customer/subscription cross-account mismatch still fails (`:1569-1600` must still
   pass); operator recovery action binds with audit.

### Symphony anchor (quoted)
- `Third-Party Integration Boundaries` (`docs/arclink/sovereign-control-node-symphony.md:909-910`):
  *"Stripe owns payment collection and subscription events; ArcLink owns entitlement
  interpretation, idempotency, gating, audit, and recovery copy."*
- `North Star` (`:116-118`,`:158-161`): *"Operators own the universe … Captains own their
  Pods and Crew, not the host."* and *"Every step should have a local source owner … how
  it fails closed."*
- `Billing, Entitlements, And Refuel` (`:892`,`:897-898`): *"Entitlement state gates
  provisioning and provider continuation."* and *"Operator Raven should see the same
  state and be able to trigger safe recovery actions without seeing secrets."*

### Effort / blast radius
Effort: med. Blast radius: `python/arclink_entitlements.py` (owner-resolution split,
merge gating); focused entitlement/onboarding webhook tests + any hosted-API Stripe
webhook fixtures that bypass real checkout state and must now establish a local
onboarding/checkout owner first; one operator recovery action (+ its dry-run/audit docs).
No schema change required — the local source owner (`arclink_onboarding_sessions`,
`arclink_subscriptions`, `arclink_users.stripe_customer_id`) and the unique
`checkout_session_id` index already exist. Live Stripe ordering/payload shape remains
`PG-STRIPE`.

---

## CONVERGENCE SUMMARY
- 1 deferred item → 1 decision. Verdict: **refine** (Codex's direction adopted; binding
  key broadened to the onboarding-session link, and the auto-create path named
  explicitly so the fix is unambiguous and the dominant real path stays green).
- Net effect: first binding becomes local-source-owned and fails closed; metadata may
  corroborate but never originate or move ownership; legitimate imports get an
  operator-only audited recovery action instead of a metadata loophole.

## STANDING DISAGREEMENTS (genuine product forks for the operator)
None that block the plan. One scoping choice the operator may tune (does NOT change the
fail-closed posture): how strict the onboarding-session field agreement must be — minimal
(require `user_id` agreement only) vs strict (require `user_id` AND `client_reference_id`
AND `deployment_id` agreement). The FINAL PLAN takes the strict-where-present stance
(agree on every field that is locally non-empty), which is the safer default and still
passes the real happy-path test.

<<<DECIDED-END CANON-07>>>
