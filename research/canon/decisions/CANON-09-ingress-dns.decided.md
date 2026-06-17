# CANON-09 — Ingress & DNS — DECIDED (Opus 4.8 final adjudication)

> Federation DECISION mode. Codex (GPT-5.5 xhigh) proposed symphony-anchored
> resolutions in `research/canon/decisions/CANON-09-ingress-dns.codex.md`. This file
> is the Opus 4.8 final adjudication: each deferred operator call independently
> re-grounded in current code (Read/grep), then converged with Codex into one
> recommended plan. Code wins over comment/name/prior claim. The symphony is intent;
> the code is reality; the plan moves code toward the symphony while failing closed.

Code re-verified at: `python/arclink_ingress.py`, `python/arclink_control.py`
(schema 1214-1225, DNS unique index 2153-2155, prefix reserve 3647-3695,
`_ensure_column` 3018-3022, `append_arclink_event(..., commit=)` 3948-3967),
`python/arclink_action_worker.py` (dns_repair 916-952, `_resolve_dns_repair`
148-237), `python/arclink_executor.py` (live upsert 2563-2596, proxied apply 2582),
`python/arclink_provisioning.py` (live ingress seam 1431-1572), `python/arclink_sovereign_worker.py`
(persist 2003, teardown 1376-1383), `python/arclink_adapters.py` (tailscale validator 246-259).

Repair-campaign note: three of the four CANON-09 reconciled MEDIUMs were ALREADY
fixed by the campaign (hostname-scoped `_mark_dns_status`, dns_repair persist-before-apply,
teardown returns only deleted records). The four items below are the genuinely
deferred operator calls.

---

## DECISION 1 — Torn-down-row / global DNS unique-index collision  `[VERDICT: agree-codex]`

**Question.** `arclink_dns_records` has a GLOBAL unique index
`idx_arclink_dns_records_host_type ON (LOWER(hostname), UPPER(record_type))`
(`control.py:2153-2155`), but `persist_arclink_dns_records` only handles
`ON CONFLICT(record_id)` (`ingress.py:80`). If a hostname is ever owned by a
different `record_id`/deployment, the INSERT raises a raw SQLite `IntegrityError`
instead of a sanitized error. Should the index become partial, should torn-down
rows be recycled/deleted, or should the namespace stay permanently reserved?

**Independent reasoning.** I re-confirmed in code that this collision is
**unreachable on the normal path**: a prefix is reserved exactly once via the
UNIQUE `idx_arclink_deployments_prefix` (`control.py:2023`), and
`reserve_arclink_deployment_prefix` catches the duplicate and raises a clean typed
`ValueError("...prefix is already reserved...")` BEFORE any DNS persist
(`control.py:3692-3693`). There is NO `DELETE FROM arclink_deployments` or
`DELETE FROM arclink_dns_records` anywhere in `python/` (grep = 0), so torn-down
DNS rows are never recycled and hostnames embed the unique prefix
(`u-<prefix>`, `hermes-<prefix>`). The collision is therefore reachable only by
manual DB corruption or a *future* code path that deletes a deployment while
leaving (or re-creating) DNS rows. That matches the reconciled severity: real
latent gap, LOW because gated by CANON-08 prefix reservation.

The symphony is unambiguous about which way to resolve this: Operators own the
host namespace as durable policy, teardown must leave evidence, and rollback
preserves state by default. Making the index partial (`WHERE status != 'torn_down'`),
auto-deleting torn-down rows, or auto-recycling prefixes would all trade
teardown evidence and namespace stability for convenience — exactly the wrong
direction. The right move is to keep permanent reservation and convert the one
remaining raw-`IntegrityError` footgun into a fail-closed sanitized error.

**Agree / differ from Codex.** Full agreement. Codex keeps permanent reservation,
rejects partial uniqueness / auto-delete / auto-recycle, and adds a preflight in
`persist_arclink_dns_records` that raises a sanitized typed error on a
cross-`record_id` hostname owner before SQLite emits the raw error, plus a
regression that seeds a conflicting torn-down row and proves fail-closed /
state-unchanged. My code reading supports every step. One refinement of emphasis:
the preflight must check ownership by `(LOWER(hostname), UPPER(record_type))`
mapping to a DIFFERENT `record_id` (not merely "a different deployment"), because
that is the exact tuple the index enforces and the exact thing
`ON CONFLICT(record_id)` cannot catch.

**FINAL PLAN.**
1. Keep `idx_arclink_dns_records_host_type` global and non-partial. Keep torn-down
   rows. Do not delete/recycle DNS rows or prefixes by default.
2. In `persist_arclink_dns_records` (`ingress.py:63`), before the upsert loop body
   for each record, `SELECT record_id FROM arclink_dns_records WHERE
   LOWER(hostname)=LOWER(?) AND UPPER(record_type)=UPPER(?)`; if a row exists with
   a `record_id != f"dns_{deployment_id}_{role}"`, raise a sanitized typed error
   (e.g. `ArcLinkIngressError("DNS hostname already reserved by another deployment;
   operator DB repair required")` — no raw hostname/secret leakage beyond the
   already-public hostname) before any write. This fails closed with operator-
   actionable copy instead of a raw `IntegrityError`.
3. Add a regression in `tests/test_arclink_ingress.py` (or the campaign's existing
   runnable file) that seeds a conflicting torn-down row under a different
   `record_id`, calls persist, asserts the typed error AND that no row was mutated
   (state unchanged / fail-closed).
4. Do NOT add any live Cloudflare hostname-release workflow now. If an operator
   later wants explicit hostname release, that is a separate `PG-INGRESS`-gated
   action with its own confirmation + evidence — out of scope here.

**Symphony anchor.** `Fleet, Provisioning, Ingress, And Recovery`: "Ingress is
either domain/Cloudflare/Traefik with wildcard subdomains or Tailscale path
routing, with clear teardown evidence." and "Rollback preserves state by default
and only deletes volumes with explicit destructive metadata and confirmation."
Also `Whole-System Traversal` step 10: teardown should "preserve state by default
and leave redacted evidence." Permanent reservation + fail-closed preflight
satisfies all three.

**Effort: med. Blast radius:** `python/arclink_ingress.py` (one preflight SELECT +
typed error), one ingress regression, and provisioning/action failure copy. No
schema change, no index change, no live Cloudflare mutation.

---

## DECISION 2 — Persisted `proxied` drift  `[VERDICT: refine]`

**Question.** `DnsRecord.proxied` is part of the desired ingress contract and the
live executor applies it to Cloudflare (`executor.py:2582`), but
`arclink_dns_records` has NO `proxied` column (`control.py:1214-1225`) so persist
silently drops it (`ingress.py:74-77`). Consequences: the row-driven dns_repair
read hard-codes `"proxied": True` (`action_worker.py:205`) regardless of what was
actually applied, and there is no durable record to drift-detect against. Should
`proxied` be persisted, and how far should the fix reach?

**Independent reasoning.** I confirmed the drift is real and durable: the in-memory
intent carries `proxied` correctly all the way to `persist_arclink_dns_records`
(`sovereign_worker.py:1998`), but it dies at the DB boundary. Any later read
(dns_repair row branch at `action_worker.py:195-207`, any future drift/dashboard
view) must invent `proxied=True`. Today every ArcLink record is created proxied,
so the invented value happens to be correct — but that is a coincidence of current
policy, not a contract. The symphony's migration section demands schema be the
"local source owner" with migration-aware, idempotent, old-state-tested changes,
and the secrets/integration section demands provider state show real
configured/applied status, not a hard-coded guess. So `proxied` SHOULD be
persisted.

Where I REFINE Codex: Codex bundles two changes of very different blast radius
into one `high` recommendation: (A) add the column + write/read it (pure CANON-09
+ CANON-01, low-risk, idempotent via the existing `_ensure_column` helper), and
(B) have the LIVE executor verify Cloudflare's RETURNED `proxied` matches desired
and otherwise leave rows `desired` and fail closed. (B) is a real CANON-11 change:
`_cloudflare_upsert_dns_records` currently returns only `provider_ids`
(`executor.py:2574-2596`) and does NOT surface the applied `proxied` from
`result["result"]["proxied"]`. Folding (B) into this decision drags in the
executor return shape, the apply-result metadata contract, and `PG-INGRESS`
live-proof expectations — and it can FAIL CLOSED on a deployment that is actually
healthy if Cloudflare's echo races or normalizes the flag. The symphony's "fail
closed" is about not over-claiming success, but bouncing a live-applied record
back to `desired` purely on a proxied echo mismatch risks a false-negative that
blocks healthy deployments — the opposite of "boringly reliable underneath."

So I split: do (A) now as the converged plan; record (B) as a smaller, explicitly
`PG-INGRESS`-gated follow-up that surfaces a proxied DRIFT signal (owner-visible
state + repair path) rather than auto-demoting the row. Drift detection, not
auto-rollback, is what `Notifications, Incidents, And Evidence` actually asks for.

**Agree / differ from Codex.** Agree on the core: add `proxied INTEGER NOT NULL
DEFAULT 1`, write it on persist, read stored `proxied` instead of the hard-coded
`True` at `action_worker.py:205`, and only preserve `provisioned` status when
hostname+type+target+proxied all match. Differ on packaging: do NOT make the live
executor auto-demote rows to `desired` on a proxied echo mismatch as part of this
decision; instead emit a `dns_proxied_drift` event/owner-visible state and leave
the existing status, under `PG-INGRESS`. This keeps the schema fix low-risk and
shippable while still moving proxied from "incidental" to "durable provider state,"
and it avoids a fail-closed regression on healthy live Pods.

**FINAL PLAN.**
1. Schema (CANON-01): add `proxied INTEGER NOT NULL DEFAULT 1` to
   `arclink_dns_records` (`control.py:1214-1225`) via the existing idempotent
   `_ensure_column(conn, "arclink_dns_records", "proxied", "INTEGER NOT NULL
   DEFAULT 1")` migration helper (`control.py:3018`). Old rows default proxied=1,
   which exactly matches current behavior (no behavioral break, old-state-safe).
2. Persist (CANON-09): add `proxied` to the INSERT column list and the
   `excluded`/conflict-update in `persist_arclink_dns_records` (`ingress.py:74-94`),
   writing `1 if record.proxied else 0`. Extend the status-preservation CASE so
   `provisioned` is preserved only when hostname AND type AND target AND proxied
   all match; a proxied flip resets to `desired` (it is a real desired change).
3. Read (CANON-14): in `_resolve_dns_repair` row branch
   (`action_worker.py:195-207`), replace the hard-coded `"proxied": True` with
   `bool(row["proxied"])` from the stored column.
4. Tests: an old-state-fixture migration test (seed a row without the column, run
   `ensure_schema`, assert column added with default 1) + a persist/read regression
   proving a `proxied=False` desired record round-trips and that a flip demotes
   `provisioned` to `desired`.
5. FOLLOW-UP (separate, `PG-INGRESS`-gated, NOT this decision): teach
   `_cloudflare_upsert_dns_records` to surface `result["result"]["proxied"]` and
   emit a `dns_proxied_drift` event + owner-visible state when applied != desired,
   WITHOUT auto-demoting the row. Document it as live-proof-pending.

**Symphony anchor.** `Configuration, Schema, And Migration`: "Database schema
changes are migration-aware, idempotent, reversible where practical, and tested
against old-state fixtures." `Secrets, Keys, And Rotation` / integration state:
"Every credential should have status without disclosure... live-proof pending, or
blocked" — generalized here to provider DNS state showing real applied `proxied`,
not a hard-coded guess. `Notifications, Incidents, And Evidence`: "Every important
background path should have an owner-visible state, a retry or repair path, and
evidence" — satisfied by the drift event rather than a brittle auto-demote.

**Effort: med (schema+persist+read); the live drift follow-up is med-separate.
Blast radius:** `control.py` (one `_ensure_column` line), `ingress.py`
(persist column + status CASE), `action_worker.py` (one read), CANON-09/CANON-01
schema tests. Executor untouched in this decision; the follow-up is the only piece
that touches CANON-11 / `PG-INGRESS`.

---

## DECISION 3 — Public unused `tailscale_dns_name` / `tailscale_host_strategy` args  `[VERDICT: refine]`

**Question.** `desired_arclink_ingress_records` accepts `tailscale_dns_name` and
`tailscale_host_strategy` (`ingress.py:50-53`) but never reads them — the tailscale
branch returns `{}` (`ingress.py:58-59`). Remove them (signature break), repurpose
them, or leave them inert?

**Independent reasoning.** I re-confirmed both production callers and found the
gap is narrower than "direct callers get a false-success empty DNS plan":
- `provisioning.py:1483-1484` — the LIVE path — already calls
  `arclink_tailscale_hostnames(prefix, clean_tailscale_dns_name,
  strategy=clean_tailscale_strategy)` BEFORE/around the
  `desired_arclink_ingress_records` call, which validates and fails closed on an
  invalid strategy/empty host (`adapters.py:250-259`). So the live path is already
  protected; the args being inert inside ingress is harmless there.
- `action_worker.py:216-223` (dns_repair) passes the tailscale args in but does NOT
  separately validate; however for `ingress_mode=="tailscale"` the function returns
  `{}` and `_resolve_dns_repair` then raises "found no domain DNS records"
  (`action_worker.py:235-236`) — also fail-closed.

So there is NO current caller that gets a silent false-success from an invalid
tailscale shape. Codex's framing ("lets direct callers pass an invalid Tailscale
shape and get a false-success empty DNS plan") is therefore true only for a
*hypothetical future direct caller*, not for the two live callers. That refines —
not refutes — the recommendation: the change is honest-signature + defense-in-depth
for future callers, not a live-exploit fix. The symphony's contract section
("contracts should be stable enough for ... future integrations to evolve without
hidden breakage") squarely supports making the accepted args meaningful and
fail-closed rather than inert.

**Agree / differ from Codex.** Agree on the mechanism: keep the public signature
(no break), and in the `tailscale` branch call
`arclink_tailscale_hostnames(prefix, tailscale_dns_name or base_domain,
strategy=tailscale_host_strategy)` purely to VALIDATE, then still return `{}`
(there are genuinely no Cloudflare DNS records to persist for path routing). Reject
synthesizing fake Tailscale DNS records — that would mix Cloudflare persistence
with Tailscale path routing and risk accidental provider mutation. Differ only on
the stated severity/justification: present it as honest-signature + defense-in-depth
(current callers already fail closed elsewhere), so the operator understands this
is hardening, not an active-bug fix — and so it is correctly rated low priority.

**FINAL PLAN.**
1. In `desired_arclink_ingress_records` (`ingress.py:46-60`), `tailscale` branch:
   call `arclink_tailscale_hostnames(prefix, tailscale_dns_name or base_domain,
   strategy=tailscale_host_strategy)` for its validation side-effect (it raises
   `ValueError` on empty host / invalid strategy / `subdomain`), then `return {}`.
   Import the helper (already imported pattern in adapters consumers).
2. Update the docstring/comment to state the args are validated for tailscale mode
   and that the function intentionally persists no Cloudflare records for path
   routing.
3. Add focused ingress tests proving: tailscale + invalid strategy (`subdomain`)
   raises; tailscale + empty host raises; tailscale + valid path returns `{}`.
4. Keep the args; do NOT remove/rename until a versioned API break.

**Symphony anchor.** `API, Webhook, And Extension Contracts`: contracts should be
"stable enough for web, bots, workers, plugins, and future integrations to evolve
without hidden breakage," and "Compatibility tests that prove old clients fail
clearly or continue safely." Validation-only use keeps the signature stable AND
makes mode selection honest + fail-closed for any future direct caller.

**Effort: low. Blast radius:** `python/arclink_ingress.py` (one validating call +
docstring), focused ingress tests. No caller changes; no schema; no live mutation.

---

## DECISION 4 — Non-empty internal commits in DNS helpers  `[VERDICT: refine]`

**Question.** `persist_arclink_dns_records` commits per call (`ingress.py:106`) and
`_mark_dns_status` commits the row UPDATE then separately calls
`append_arclink_event` (which commits again by default) — a status-without-event
split window (`ingress.py:162-188`). Remove the internal commits, keep them, or
make them explicit?

**Independent reasoning.** I confirmed no current caller wraps these helpers in an
outer transaction expecting atomicity: `sovereign_worker.py:2003` and the teardown
calls at `1376-1383` invoke them standalone, and the action_worker dns_repair path
calls them in sequence without an outer `BEGIN IMMEDIATE`. So removing the commits
wholesale would silently push durability onto every caller across a network
boundary (Cloudflare apply/teardown sit between these DB writes) — and on a crash
you could LOSE the desired-intent row or the teardown evidence. The symphony wants
exactly the opposite: every background path leaves "owner-visible state ... and
evidence," and teardown "preserves state by default and leaves redacted evidence."
The phase model that satisfies this is: commit desired rows BEFORE the Cloudflare
mutation, commit provision/teardown evidence AFTER the provider result — a crash
then leaves visible state, never lost intent. So the commits are CORRECT; the only
real defect is the status-without-event split in `_mark_dns_status` (the UPDATE
commits, then if the process dies before/inside `append_arclink_event` you have a
torn_down/provisioned row with NO matching event — evidence loss the symphony
forbids).

Where I REFINE Codex: Codex's headline is "add keyword-only `commit: bool = True`
to DNS DB helpers" so callers can opt into `commit=False`. That is fine but is the
LOWER-value half. The MAIN, must-do fix is collapsing the
`_mark_dns_status` split into one atomic commit, which is already trivially
available because `append_arclink_event` accepts `commit=False`
(`control.py:3948-3967`): do the row UPDATE without committing, call
`append_arclink_event(..., commit=False)`, then ONE `conn.commit()`. That closes
the evidence-loss window with zero new public surface. The `commit: bool=True`
parameterization of `persist_arclink_dns_records` is optional polish — I keep it as
a SHOULD (explicit, documented local-only), not the load-bearing change, to avoid
new footguns (`commit=False` misuse holding a DB transaction across a network call
is itself an anti-pattern the docstring must warn against).

**Agree / differ from Codex.** Agree: do NOT remove internal commits; codify the
phase model; the residual risk is caller misuse of `commit=False` (mark it
local-only in docstrings/tests). Differ on priority ordering: the atomic
status+event commit in `_mark_dns_status` is the required fix (closes a real
evidence-loss window); the `commit` keyword on `persist_arclink_dns_records` is
optional hardening, not required, and should be gated behind a documented
local-only contract so it does not invite cross-network-call transactions.

**FINAL PLAN.**
1. REQUIRED — refactor `_mark_dns_status` (`ingress.py:153-188`) so the row UPDATE
   and the event insert commit together: run the UPDATE without `conn.commit()`,
   call `append_arclink_event(conn, ..., commit=False)`, then a single
   `conn.commit()`. Same for `mark_arclink_dns_provisioned`'s provider-id UPDATE
   (`ingress.py:204-216`) — fold its commit into the same atomic block so status,
   event, and provider_record_id land or roll back together. This removes the
   status-without-event / status-without-provider-id windows.
2. OPTIONAL (SHOULD) — add keyword-only `commit: bool = True` to
   `persist_arclink_dns_records` (and `_mark_dns_status` if a caller ever needs it);
   default `True` keeps every current live caller's behavior identical. Docstring +
   a test must mark `commit=False` as caller-owned-local-transaction ONLY, never to
   be held across a Cloudflare network call.
3. Keep the existing phase model: persist desired rows (committed) before the
   executor's Cloudflare apply, mark provisioned/torn-down (committed atomically
   with event) after the provider result.
4. Add a regression proving a `_mark_dns_status` call writes BOTH the status row and
   the matching `arclink_events` row in one transaction (e.g. assert both present,
   and that a simulated failure of the event insert leaves the status unchanged).

**Symphony anchor.** `Notifications, Incidents, And Evidence`: "Every important
background path should have an owner-visible state, a retry or repair path, and
evidence that can be shared without secrets." `Whole-System Traversal` step 10 /
`Fleet, Provisioning, Ingress, And Recovery`: teardown should "preserve state by
default and leave redacted evidence." Atomic status+event commit guarantees the
evidence row can never be lost relative to the status it documents.

**Effort: med. Blast radius:** `python/arclink_ingress.py` (`_mark_dns_status` +
`mark_arclink_dns_provisioned` atomic-commit refactor; optional `commit` kw),
transaction/evidence regressions. Live callers in `action_worker.py` /
`sovereign_worker.py` only change if they opt into `commit=False` (they need not).

---

## STANDING DISAGREEMENTS (genuine operator forks)

None. All four decisions converge to a single recommended plan. The only
operator-visible CHOICES embedded above are sequencing, not forks: Decision 2's
live proxied-drift detection (step 5) and Decision 4's optional `commit` keyword
(step 2) are explicitly scoped as separate, lower-priority follow-ups so the
operator can land the load-bearing, low-risk core (schema column + atomic
status/event commit + preflight + tailscale validation) first without committing to
the heavier `PG-INGRESS` executor work.
