# ArcLink Professional Finish Gate

ArcLink is not finished when a local phase reports `done`. ArcLink is finished
when it can be sold, deployed, observed, operated, recovered, and used end to
end with honest evidence.

The criteria below (Product / Admin / Engineering / Brand finish) describe the
*intent* of the finish bar. The *executable* gate that mechanically enforces a
slice of it lives in code — see the next section. This doc is the concept; the
code is the contract.

> DOC_STATUS: this file is classified Canonical in `docs/DOC_STATUS.md`
> (alongside `brand-system.md`). Treat it as the conceptual companion to the
> code-enforced gate below.

## The Executable Finish Gate (cross-surface copy contract)

The mechanically enforced "finish gate" for surface copy is
`python/arclink_surface_contract.py`, validated by
`tests/test_arclink_surface_contract.py` (both tests green locally). It is a
pure, no-secret, no-network linter — it proves **local copy quality only**, not
how live channels render. This is GAP-033-A: the local source slice landed and
is tested, but **GAP-033 is NOT closed.** Live browser/chat/workspace render
proof remains open behind `PG-PROD`, `PG-BOTS`, and `PG-HERMES`. See `GAPS.md`
for the gap taxonomy.

What it is (implemented and tested locally):

- A `SurfaceSample` frozen dataclass plus `surface_contract_issues(sample)`
  (returns human-readable violations) and `assert_surface_contract(samples)`
  (raises on any violation). `visible_text_from_html(html)` strips
  `<script>`/`<style>` so rendered HTML can be linted as visible text.
- A canonical surface taxonomy expressed as type literals:
  - `SurfaceAudience` = `captain | operator | agent | mixed`
  - `SurfaceChannel` = `chat | dashboard | plugin | cli | tui | api | web | docs`
  - `SurfaceState` = `normal | blocked | proof_gated`

What it checks (every check is line-cited in the module):

- **Budget:** non-empty text; `max_chars` (default 2400) and `max_line_chars`
  (default 360) limits.
- **Secret refusal:** `_SECRET_VALUE_PATTERNS` rejects secret-shaped values
  (Stripe `sk_live_`/`sk_test_`/`whsec_`, Slack `xox*-`, Notion `ntn_`, GitHub
  `ghp_`/`github_pat_`, a Telegram-token shape, `secret://`, and PEM
  `-----BEGIN ... PRIVATE KEY-----`). No real secret is ever placed in copy or
  examples — this gate fails closed if one leaks.
- **Traceback refusal:** `_TRACEBACK_PATTERNS` rejects raw `Traceback (most
  recent call last)`, `File "...", line N`, and `*Error:`/`*Exception:` shapes.
- **Chat hygiene** (`channel == "chat"`): unbalanced backticks and literal HTML
  tags are rejected.
- **Captain-vocabulary lint** (`audience == "captain"`, unless
  `allow_captain_technical_terms=True`): `_CAPTAIN_FORBIDDEN_PATTERNS` rejects
  operator-internal words on Captain copy — "deployment(s)" (say ArcPod or Pod),
  "user(s)"/"buyer(s)" (say Captain), "operator(s)" (reserved for admin/deploy
  surfaces), and lower-case `agent|agents|pod|pods|crew` (product terms must be
  capitalized as Agent, Agents, Pod, Pods, Crew). The schema canon keeps the
  technical names (`arclink_deployments`, `arclink_users`); the lint only
  governs the Captain boundary.
- **Required/forbidden terms and proof gates:** `required_terms` and
  `proof_gates` must appear verbatim; `forbidden_terms` must not (case-insens).
- **Blocked-copy "next action" rule:** when `state` is `blocked`/`proof_gated`
  (or the text reads `blocked`/`proof-gated`/`proof still required`/`not active
  yet`/`disabled until`), `_NEXT_ACTION_RE` must match — the copy must offer a
  concrete next action or name a gate (`Next|Use|Open|Run|Register|Complete|
  Send|Tap|Choose|Check|Retry|Operator|dashboard|checkout|proof|PG-[A-Z-]+`).
  This is how blocked surfaces are kept honest: they must name the proof gate
  and a way forward, not dead-end.

What the test proves (`tests/test_arclink_surface_contract.py`):

- `test_surface_contract_lints_common_regressions` feeds a deliberately bad
  Captain/chat sample and asserts the secret, traceback, and Captain-vocabulary
  messages fire.
- `test_cross_surface_contract_uses_real_local_surfaces` (load-bearing) seeds a
  real in-memory control DB and lints **real local surface text** — Captain
  Raven `/start` (happy) and a `provisioning_failed` `/connect_notion` (blocked),
  Operator Raven `/operator_status`, dashboard
  `control_node_provisioning_readiness`, the local product-surface home HTML, the
  `bin/deploy.sh` readiness lines, and the Drive/Code/Terminal plugin `status()`
  payloads. The operator/dashboard/CLI samples are themselves proof-gated and
  cite `PG-PROD`/`PG-BOTS`/`PG-PROVISION`/`PG-UPGRADE`/`PG-FLEET`: the gate
  proves the copy is honest about being gated, not that the live action works.

What it does NOT do: it does not prove how Telegram/Discord render markdown, how
dashboard or plugin panels lay out in a browser, or how CLI/TUI wrap on a real
terminal. Those are GAP-033's open gates (`PG-PROD`, `PG-BOTS`, `PG-HERMES`).
The voice split it enforces — Captain copy in the ArcLink lore voice (Raven
persona), Operator copy in a precise/auditable voice — mirrors the canon in
`docs/arclink/vocabulary.md`.

## Product Finish

- A user can start from the website, Telegram, or Discord and enter the same
  onboarding state machine.
- Checkout, entitlement, provisioning intent, service visibility, support
  guidance, and billing portal state are all visible from the user dashboard.
- The user dashboard shows ArcLink's real technology without hiding it:
  Hermes, qmd, Chutes inference provider state, vaults, memory stubs, skills,
  Nextcloud, dashboard-native Code, bots, service health, and deployment state.
- Fake/local adapters are labeled as fake/local. Live claims require live E2E
  proof.
- Mobile views prioritize status, alerts, search, and primary recovery
  actions.

## Admin Finish

- Operators can see onboarding funnel state, users, payments, provisioning
  queue, service health, host health, domain/Tailscale ingress drift, bot state,
  provider state, audit, and guarded actions.
- Mutating actions require auth, role, CSRF or webhook signature, reason,
  idempotency, and audit.
- Reconciliation drift is visible: Stripe versus local entitlement, active DNS
  versus active deployments, provider state versus configured deployments, and
  healthy services versus billed users.

## Engineering Finish

- Focused deterministic tests exist for each changed layer.
- Browser claims are proven with Playwright or an equivalent browser check on
  desktop and narrow mobile viewports.
- Live external calls are gated behind explicit E2E switches and documented
  credentials.
- No plaintext secrets appear in code, docs, tests, logs, rendered compose, or
  generated specs.
- Documentation states what is real, what is fake/local, what is live-gated,
  and which external credentials remain blocked.

## Brand Finish

Use `docs/arclink/brand-system.md` and the source brand kit. ArcLink should
feel like premium private AI infrastructure: jet black, carbon, soft white,
signal orange, precise status blue/green, Space Grotesk, Inter or Satoshi,
minimal operational interfaces, direct operator language, and visible workflows.

Do not use generic AI imagery, broad decorative gradients, vague marketing
copy, or placeholder dashboards.
