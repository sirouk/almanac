# CANON-11 — Executor — FINAL ADJUDICATED DECISIONS

**Adjudicator:** Claude Opus 4.8 (1M) — final federation adjudicator, DECISION mode.
**Codex (GPT-5.5 xhigh) proposal:** `research/canon/decisions/CANON-11-executor.codex.md`.
**Method:** Independent view formed first by re-opening the post-repair code (`python/arclink_executor.py`, `python/arclink_action_worker.py`, `python/arclink_sovereign_worker.py`, `python/arclink_control.py`, `bin/deploy.sh`, `python/arclink_dashboard.py`), then reconciled against Codex and anchored to `docs/arclink/sovereign-control-node-symphony.md`. Code is reality; the symphony is intent; the plan moves code toward intent while failing closed.

**Convergence summary:** I AGREE with Codex on the direction of all three decisions. I REFINE Decision 1 (the action-worker target resolution is asymmetric — `cancel` already resolves a subscription, `refund` does not resolve a charge, so the fix is narrower and more pointed than "refund-by-customer" implies) and REFINE Decision 3 (the pinning infrastructure already exists in `deploy.sh` and the steady-state fail-closed switch is a smaller, higher-value first move than the full re-attest ceremony). Decision 2 I AGREE with as written, with one schema-grounding refinement. One genuine product fork is recorded under standing disagreements (Stripe cancel default: period-end vs immediate).

---

## DECISION 1 — Production Chutes/Stripe admin clients + refund/cancel semantics

**[VERDICT: refine]**

### The question
Live Chutes key management and Stripe refund/cancel are not production-wired. The post-repair executor now fails closed twice (requires an injected client AND a durable `operation_conn`), but the real client implementations, the Chutes-vs-router authority split, and the Stripe refund/cancel resolution semantics are provider/product decisions.

### My independent reasoning (code-grounded)
Re-opening the code, the fail-closed shape Codex describes is real and already in place post-repair:
- `chutes_key_apply` raises if `chutes_client is None` AND raises if `operation_conn is None` (`python/arclink_executor.py:1217`, `:1219`). `stripe_action_apply` mirrors this (`:1342`, `:1344`).
- `executor_for_fleet_host` now injects `operation_conn=_operation_conn_from_env(env)` from `ARCLINK_DB_PATH` (`python/arclink_executor.py:160`), but **never** injects `chutes_client=` or `stripe_client=`. So live provider-admin mutation is unreachable today — exactly the latent-not-current re-scoping the reconciliation reached.

The load-bearing new finding is in the **action worker target resolution**, which Codex's framing under-specifies. Reading `_resolve_stripe_action` (`python/arclink_action_worker.py:360-406`):
- `refund` resolves only to a Stripe **customer** (`customer_ref = secret://arclink/stripe/customer/{user_id}`, `:387`) and raises if no `stripe_customer_id` (`:388`). It does **not** resolve a charge / payment_intent / invoice. A refund executed against a customer alone is genuinely underspecified and can hit the wrong charge — Codex is right here.
- `cancel`, by contrast, **already** resolves and requires a `stripe_subscription_id` (`:390`). So Codex's "cancel should default to period-end" is the right policy, but the target-resolution defect Codex implies for cancel does not exist — the subscription is already pinned. The real cancel gap is only the **period-end-vs-immediate** default, not target resolution.
- The `StripeActionClient.refund/cancel` protocol (`python/arclink_executor.py:434-465`) passes only `deployment_id, customer_ref, idempotency_key, metadata` — there is no field for a charge/payment_intent/invoice id or a cancel-timing flag. So wiring a real client requires a **protocol signature change**, not just an implementation.

The dashboard already labels these `PG-PROVIDER` / `PG-STRIPE` (`python/arclink_dashboard.py:77`, `:87`) and the refund `local_contract` already says "after resolving the target through the control DB" — the surfaces are honest that this is live-proof-pending. That satisfies the symphony's three-state integration rule (configured-and-locally-valid / live-proof-pending / missing-and-blocked).

The Chutes-key-rotation-as-Operator-maintenance-lane point is correct and matters: per the symphony, "ArcLink owns router keys ... budget enforcement," and Pods consume inference through the **router**, not a per-Pod provider key. So `chutes_key_apply` is an Operator compatibility/rotation surface, not the default Pod inference path — keep router credentials as the inference path.

### Where I agree / differ from Codex
- AGREE: keep live provider mutation fail-closed; inject clients only when DB opens, mutation is explicitly enabled, secret refs present, and `PG-PROVIDER`/`PG-STRIPE` green; webhooks remain entitlement source of truth; Chutes rotation is an Operator lane not the Pod path.
- REFINE: the Stripe fix is **asymmetric**. Refund needs a resolvable **charge/payment_intent/invoice** (new protocol field + action-worker resolution from `arclink_payments`/charge rows), and must refuse refund-by-customer-only. Cancel already pins a subscription; its only open call is the **period-end (default) vs immediate (explicit confirmation)** flag (new protocol field + confirmation metadata). Don't conflate the two under one "refund-by-customer" rejection.
- REFINE: add the protocol-signature change explicitly to the plan — `StripeActionClient.refund(... charge_ref=...)` / `.cancel(... at_period_end: bool, ...)` — because without it the live client cannot express the resolved target, and the symphony's API-contract section requires the action-worker contract to define `target` and `confirmation` fields.

### FINAL PLAN
1. **Keep fail-closed; gate injection.** Leave `chutes_client`/`stripe_client` un-injected by default. Add a single explicit enable gate (e.g. `ARCLINK_EXECUTOR_PROVIDER_MUTATION_ENABLED`) checked in `executor_for_fleet_host` before constructing a live client; with DB-open + secret-refs-present + the gate, inject `ExecutorChutesKeyClient` / `LiveStripeActionClient`. Without all of them, the current double fail-closed (`:1217-1220`, `:1342-1345`) stands.
2. **Chutes client** = an Operator maintenance/compatibility lane wrapping the existing `ChutesLiveAdapter` proof-gated key mutation (`python/arclink_chutes_live.py`). Pods keep router credentials; `chutes_key_apply` is operator-triggered rotate/revoke only.
3. **Stripe refund** — extend `StripeActionClient.refund` and `_resolve_stripe_action` to resolve and require a **charge / payment_intent / invoice** (or a policy-approved explicit amount), reading the charge row from the control DB; **refuse** refund when only a customer is known. Block known forged/cross-customer targets via the existing `_validate_explicit_target` rail (`python/arclink_action_worker.py:382-385`).
4. **Stripe cancel** — add an `at_period_end` flag to the protocol and action-worker metadata; default to **period-end**; require explicit confirmation metadata for immediate cancel. (Period-end-vs-immediate default is an operator fork — see standing disagreements.)
5. **Proof + tests.** Prove the whole surface behind `FakeSecretResolver`/fake-client tests (digest-bound idempotency already exists for the live path via `operation_conn`), then a NAMED live gate: `PG-PROVIDER` (Chutes) and `PG-STRIPE` (refund/cancel) with redacted evidence rows. Webhooks remain the entitlement source of truth; the executor never re-derives entitlement.

### Symphony anchor
> "Stripe owns payment collection and subscription events; ArcLink owns entitlement interpretation, idempotency, gating, audit, and recovery copy." ... "Chutes or other providers own model execution; ArcLink owns router keys, model allowlists, fallback policy, budget enforcement, sanitized usage rows, and incident visibility." — *Third-Party Integration Boundaries*

Also: > "Action-worker contracts that define actor, action, target, reason, status, audit, dry-run, confirmation, retry, timeout, and rollback fields." — *API, Webhook, And Extension Contracts* (the refund `target` resolution and cancel `confirmation` flag are exactly these required fields).

### Effort / blast-radius
**high.** Touches executor factory + `StripeActionClient`/`ChutesKeyClient` protocols, action-worker `_resolve_stripe_action` charge resolution, admin readiness copy, proof/evidence rows, and fake-client tests. Blast radius is contained behind the un-injected-by-default gate: nothing changes for existing fleets until an operator turns provider mutation on with green proof gates.

---

## DECISION 2 — Replay ledger contract for compose, lifecycle, and DNS

**[VERDICT: agree-codex]** (with a schema-grounding refinement)

### The question
The live compose/DNS/lifecycle paths execute without a durable ArcLink-side replay reservation; only Chutes/Stripe use `arclink_operation_idempotency`. A naive generic key ledger would break legitimate re-applies because compose keys are deployment-id-scoped and reused across updates.

### My independent reasoning (code-grounded)
Confirmed in code:
- The live `docker_compose_apply` (non-fake) path has **no** `_reserve`/`_replay` call — it validates, materializes, and runs `up -d` (`python/arclink_executor.py:912-924`). Only the **fake** path does digest-bound replay and rejects key-reuse-with-different-digest (`python/arclink_executor.py:1064-1067`).
- The reuse hazard is real: `arclink_sovereign_worker.py` mints **deployment-id-scoped** keys — `arclink:sovereign:compose:{deployment_id}` (`:1252`), `:dns:` (`:1226`), `:compose-teardown:` (`:1356`), `:dns-teardown:` (`:1371`). The same key recurs across every legitimate re-apply/upgrade of a deployment. So binding all updates to the deployment-only key would break re-apply — Codex's rejection of that alternative is correct.
- The schema already carries `intent_digest` and PKs on `(operation_kind, idempotency_key)` (`python/arclink_control.py:1464-1477`). There is **no** generation/supersession column today. So Codex's "content/generation key" is the right shape, and the existing `intent_digest` field is the natural discriminator.

This is precisely the fake guard promoted to live: "same key + same digest replays, same key + different digest fails closed" is already the fake behavior at `:1064-1067`; the work is to make the live path call `_reserve_operation_idempotency` keyed by content/generation. The DNS Cloudflare per-zone lock added in the repair (`python/arclink_executor.py:2563`) is the right floor; ledger desired-state on top by `deployment_id + zone + dns_digest`.

### Where I agree / differ from Codex
- AGREE fully: typed replay contract, not a naive generic ledger; compose key becomes `arclink:sovereign:compose:{deployment_id}:{intent_digest}` (or reserve on the existing key but treat a different digest as a new generation that supersedes, never a collision-fail of a legitimate update); DNS ledgered by `deployment_id + zone + dns_digest` on top of the existing lock; lifecycle deduped by action-intent id with teardown carrying `remove_volumes` + confirmation metadata; build on `arclink_operation_idempotency`.
- REFINE (grounding only): the cleanest path given the existing schema is **NOT** to fold the digest into the `idempotency_key` string (that loses the "this is the same logical operation, newer generation" relationship and makes supersession invisible). Prefer reserving on the stable `idempotency_key` and using `intent_digest` as the generation discriminator: same key + same digest → replay; same key + different digest → **mint a new generation** (supersede the prior `succeeded` row, do not fail the operator's legitimate re-apply). That needs a small schema add (a `generation`/`superseded_at` field or a status that allows controlled re-reservation), which is the "extend only if needed" path Codex already left open. Residual: Docker's non-transactional partial apply is handled by health/reconcile evidence, not fake atomicity — agreed, do not pretend atomicity.

### FINAL PLAN
1. **Compose (live):** before `up -d`, `_reserve_operation_idempotency(conn, operation_kind="docker_compose_apply", idempotency_key="arclink:sovereign:compose:{deployment_id}", intent={...,intent_digest})`. Same key + same `intent_digest` → replay the recorded result (crash-after-`up` safety). Same key + **different** `intent_digest` → controlled new generation (legitimate update), recorded as superseding the prior row — never a hard collision-fail. Complete/fail on the way out, mirroring the existing Chutes/Stripe pattern (`:1224-1316`).
2. **DNS (live):** keep the per-zone Cloudflare advisory lock (`python/arclink_executor.py:2563`); add a desired-state ledger keyed by `deployment_id + zone + dns_digest` so stale retries replay and superseded records are evidenced.
3. **Lifecycle:** dedupe by action-intent id; teardown intent records `remove_volumes` + confirmation metadata so the destructive path is auditable and idempotent.
4. **Schema:** extend `arclink_operation_idempotency` minimally with a generation/supersession marker (a column + index), migration-aware and old-state-fixture tested per the Configuration/Schema/Migration contract. Keep it create-if-absent and reversible-where-practical.
5. **Proof:** local replay/regression tests (the fake digest guard already proves the contract shape); NAMED live gates `PG-PROVISION` (compose), `PG-INGRESS` (DNS), `PG-FLEET` (worker), each leaving redacted evidence.

### Symphony anchor
> "Action-worker contracts that define actor, action, target, reason, status, audit, dry-run, confirmation, retry, timeout, and rollback fields." — *API, Webhook, And Extension Contracts*

> "Rollback preserves state by default and only deletes volumes with explicit destructive metadata and confirmation." — *Fleet, Provisioning, Ingress, And Recovery* (teardown-intent `remove_volumes` + confirmation in the ledger).

Also: > "Database schema changes are migration-aware, idempotent, reversible where practical, and tested against old-state fixtures." — *Configuration, Schema, And Migration* (the generation-field add).

### Effort / blast-radius
**high.** Touches executor (live compose/DNS/lifecycle), sovereign worker key minting, action worker linkage, control schema + migration fixtures, DNS marking, local replay tests, and `PG-PROVISION`/`PG-INGRESS`/`PG-FLEET` proof expectations. Blast radius is bounded because the contract preserves legitimate re-applies/upgrades by design (new generation, not collision-fail) — the failure mode it removes is stale-retry/crash-after-apply double-execution, not normal operation.

---

## DECISION 3 — SSH TOFU default for fleet executor/bootstrap

**[VERDICT: refine]**

### The question
The fleet SSH default is `StrictHostKeyChecking=accept-new` (TOFU). Tightening it affects first-contact fleet bootstrap policy.

### My independent reasoning (code-grounded)
The TOFU default is widespread on the **fleet executor / steady-state** lane:
- Executor factory: `ssh_options = [... "StrictHostKeyChecking=accept-new"]` (`python/arclink_executor.py:138`).
- `SshDockerComposeRunner` default: same (`python/arclink_executor.py:550`).
- Also `arclink_inventory.py:497`, `arclink_provisioning.py`, `arclink_fleet_inventory_worker.py` (grep: 4 python modules carry `accept-new`).

But the **backup/upstream git** lanes already fail closed correctly: `deploy.sh:3838` renders `StrictHostKeyChecking=yes` with a pinned `UserKnownHostsFile`, and `deploy.sh:3949` ssh-keyscans-then-pins. So the codebase already knows how to do steady-state pinning — the fleet executor lane is the outlier.

Crucially, the **pinning infrastructure already exists** for the fleet lane too:
- `ensure_control_fleet_ssh_key` creates the fleet `known_hosts` file (`deploy.sh:8642`, `:8645`) and threads `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE` (`:8652`/`:8654`).
- The fleet smoke test ssh-keyscans the host into that known_hosts (`deploy.sh:9469-9471`) — yet then still passes `StrictHostKeyChecking=accept-new` (`deploy.sh:9483`) even with the file present.
- The executor already wires `UserKnownHostsFile` when `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE` is set (`python/arclink_executor.py:144-145`).

So the symphony violation is concrete: steady-state fleet ops accept new/changed host keys silently when a pinned known_hosts already exists. Operators own fleet admission (north star), so first contact may be a deliberate ceremony — but ongoing executor/probe/image-sync/inventory SSH should fail closed on unknown or changed keys.

### Where I agree / differ from Codex
- AGREE: split first-contact from steady-state. Steady-state executor SSH should be `StrictHostKeyChecking=yes` requiring a pinned known_hosts; keep TOFU only inside the explicit bootstrap/register-worker ceremony with fingerprint display + operator confirmation + pinned write + redacted evidence; host-key changes fail closed and require an explicit re-attest/rotate-host-key flow.
- REFINE (sequencing/grounding): the **highest-value, lowest-risk first move** is to make the executor and the four fleet modules use `StrictHostKeyChecking=yes` **whenever a known_hosts file is present** (which `ensure_control_fleet_ssh_key` already guarantees on the canonical lane), and `accept-new` **only** when no known_hosts is configured (true fresh bootstrap). That single conditional flips steady-state to fail-closed without breaking fresh-worker admission, and it lands before the full re-attest ceremony. The canonical deploy lane already pins a known_hosts, so on the supported path this is fail-closed immediately. The full fingerprint-display/confirm/`--host-key-sha256` ceremony in `register-worker` is the second, larger move.
- AGREE: this is `med`, not low — it touches executor SSH options, the four fleet modules, deploy bootstrap/register-worker, fleet-share SSH command rendering, docs, and regression tests.

### FINAL PLAN
1. **Steady-state fail-closed (first move):** in `executor_for_fleet_host` (`python/arclink_executor.py:138`), `SshDockerComposeRunner` default (`:550`), and the inventory/provisioning/fleet_inventory_worker SSH option builders, set `StrictHostKeyChecking=yes` and require `ARCLINK_FLEET_SSH_KNOWN_HOSTS_FILE` when present; only fall back to `accept-new` when no known_hosts is configured (genuine first contact). On the canonical deploy lane, `ensure_control_fleet_ssh_key` already pins a known_hosts, so steady-state is fail-closed immediately. Also flip the deploy.sh smoke test (`:9483`) to `yes` once it has keyscanned into the pinned file.
2. **Bootstrap ceremony (second move):** confine TOFU to `deploy.sh control register-worker --bootstrap-remote`. Scan and **display** the host-key fingerprint, require operator confirmation or `--host-key-sha256`, write the pinned key under `arclink-priv/secrets/ssh/known_hosts`, and record redacted evidence. (The keyscan-then-pin pattern already exists at `deploy.sh:3949` and `:9469` — reuse it with a confirmation gate.)
3. **Host-key change = fail closed:** a changed key must abort steady-state ops and require an explicit re-attest/rotate-host-key flow (operator-owned), with redacted evidence. Document the re-attestation path.
4. **Proof:** regression tests that assert (a) steady-state SSH uses `yes` + pinned known_hosts, (b) missing/unpinned known_hosts fails closed at steady-state, (c) bootstrap displays fingerprint and requires confirmation. NAMED live gate stays `PG-FLEET`.

### Symphony anchor
> "Operators own the universe: hosts, secrets, fleet, policy, upgrades, backups, live proof, emergency repair, and product rollout." — *North Star* (first contact is the operator's deliberate admission ceremony; steady state must not silently re-admit).

> "Stripe, Telegram, Discord, Chutes/provider, Cloudflare, Tailscale, SSH ... credentials are stored only in private state or provider-owned stores." and "Bot and provider tokens should be validated with the smallest safe live call and should fail closed if validation cannot run." — *Secrets, Keys, And Rotation* (a pinned host key is fleet admission truth; it must fail closed on change).

### Effort / blast-radius
**med.** Touches executor SSH options + four fleet modules, deploy register-worker/bootstrap, fleet smoke test, fleet-share SSH command rendering, docs, and regression tests. Blast radius: the first move is low-risk on the canonical lane (known_hosts already pinned) but will fail closed any out-of-band lane that relied on silent `accept-new` without a pinned file — that surfacing is the intended behavior, and the bootstrap ceremony is the supported way to (re)pin.

---

## Convergence note
All three decisions converge with Codex on direction. The refinements are: (1) Stripe fix is asymmetric — refund needs charge resolution + protocol-signature change, cancel only needs a period-end flag; (2) replay should use `intent_digest` as a generation discriminator (small schema add) rather than folding the digest into the key string, to keep supersession visible and never collision-fail a legitimate re-apply; (3) the steady-state `yes`-when-known_hosts-present switch is the high-value first move and is already fail-closed on the canonical deploy lane. Every plan fails closed and leaves a NAMED live-proof gate with redacted evidence.
