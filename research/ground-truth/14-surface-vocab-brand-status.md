# Ground Truth 14 — Surface Contract, Vocabulary, Brand, Gaps/Status Reconciliation

Date: 2026-05-30. Branch: arclink. Source of truth: the code listed below, verified by running
`python3 tests/test_arclink_surface_contract.py` (both tests PASS today) and direct reads.

This reader is the **gap/status source of truth** for the documentation swarm. The authoritative
current GAP-* ledger status, the cross-surface finish gate, the canonical vocabulary, and the
DOC_STATUS classification are all consolidated below.

---

## A. What is actually implemented today (local-real)

### A1. The cross-surface finish gate (`python/arclink_surface_contract.py`, 152 lines)

This is the real, enforced "professional finish gate" in code (the `professional-finish-gate.md`
doc is only prose; the *executable* gate lives here). It is a pure, no-secret, no-network linter.

Public API:
- `SurfaceSample` (frozen dataclass): fields `name, text, audience, channel, state,
  required_terms, proof_gates, forbidden_terms, allow_captain_technical_terms, max_chars=2400,
  max_line_chars=360, metadata`.
- `surface_contract_issues(sample) -> list[str]` — returns human-readable violations.
- `assert_surface_contract(samples)` — raises `AssertionError("ArcLink surface contract
  violations:\n...")` if any sample fails.
- `visible_text_from_html(html) -> str` — strips `<script>`/`<style>` and returns visible text
  (used to lint the rendered product-surface HTML).

Type aliases (the canonical taxonomy of surfaces):
- `SurfaceAudience = Literal["captain", "operator", "agent", "mixed"]`
- `SurfaceChannel = Literal["chat", "dashboard", "plugin", "cli", "tui", "api", "web", "docs"]`
- `SurfaceState = Literal["normal", "blocked", "proof_gated"]`

Checks performed by `surface_contract_issues` (all real, line-cited):
1. Empty-text rejection (L96-97).
2. `max_chars` / `max_line_chars` budget enforcement (L99-103).
3. **Secret redaction** via `_SECRET_VALUE_PATTERNS` (L16-26): Stripe `sk_live/test_`,
   `whsec_`, Slack `xox[baprs]-`, Notion `ntn_`, GitHub `ghp_`/`github_pat_`, a Telegram-token
   shape `\d{6,}:[A-Za-z0-9_-]{20,}`, `secret://`, and PEM `-----BEGIN ... PRIVATE KEY-----`.
4. **Raw traceback refusal** via `_TRACEBACK_PATTERNS` (L28-32): `Traceback (most recent call
   last)`, `File "...", line N`, and `*Error:`/`*Exception:` shapes.
5. **Chat-channel hygiene** (L114-118): unbalanced backticks rejected; literal HTML tags
   (`<br`, `</`) rejected in `channel == "chat"` copy.
6. **Captain-audience vocabulary enforcement** via `_CAPTAIN_FORBIDDEN_PATTERNS` (L34-39),
   skipped only when `allow_captain_technical_terms=True`:
   - the word "deployment(s)" -> message "Captain-facing copy should say ArcPod or Pod, not
     deployment."
   - "user(s)"/"buyer(s)" -> "...should say Captain, not user or buyer."
   - "operator(s)" -> "Operator is reserved for admin/deploy surfaces."
   - **lower-case** `agent|agents|pod|pods|crew` (case-sensitive regex, no IGNORECASE) ->
     "Product terms should be capitalized as Agent, Agents, Pod, Pods, and Crew." This is why
     Captain copy must capitalize Agent/Pod/Crew.
7. `required_terms`, `proof_gates` (must appear verbatim in text), and `forbidden_terms`
   (case-insensitive) enforcement (L125-134).
8. **Blocked/proof-gated copy must offer a concrete next action** (L136-140): if `state` is
   `blocked`/`proof_gated` OR the text matches `blocked|proof-gated|proof still required|not
   active yet|disabled until`, then `_NEXT_ACTION_RE` (L41-43) must match — i.e. copy must
   contain one of `Next|Use|Open|Run|Register|Complete|Send|Tap|Choose|Check|Retry|Operator|
   dashboard|checkout|proof|PG-[A-Z-]+`. Otherwise it flags "lacks a concrete next action or
   proof gate."

### A2. The cross-surface gate test (`tests/test_arclink_surface_contract.py`, 299 lines)

Two tests, both PASS today (verified by running the file):
- `test_surface_contract_lints_common_regressions` — feeds a deliberately bad Captain/chat sample
  (traceback + `sk_test_...` + "deployment" + "operator") and asserts the four expected messages
  fire.
- `test_cross_surface_contract_uses_real_local_surfaces` — the load-bearing one. It seeds a real
  in-memory control DB and exercises **real local surfaces** (no mocks of the surface text):
  - `arclink_public_bots.handle_arclink_public_bot_turn(...)` for Captain Raven `/start`
    (happy) and `/connect_notion` after forcing `status='provisioning_failed'` (blocked).
  - `arclink_operator_raven.dispatch_operator_raven_command(conn, "/operator_status", ...)` for
    Operator Raven status.
  - `arclink_dashboard.control_node_provisioning_readiness(...)` for dashboard readiness.
  - `arclink_product_surface.handle_arclink_product_surface_request(conn, GET "/")` rendered HTML,
    passed through `visible_text_from_html`.
  - `bin/deploy.sh` readiness lines (CLI copy) via `deploy_readiness_text()`.
  - Drive/Code/Terminal plugin `status()` payloads via `plugin_status_samples()` (loads
    `plugins/hermes-agent/{drive,code,terminal}/dashboard/plugin_api.py` against a temp HOME).
  - Final guard (L287): `captain_start.reply` must contain **no** `\bdeployments?\b` (case-insens).

  The samples encode the **canonical required-term contract** per surface (exact strings):
  - `captain-raven-start` (audience captain, chat): requires `Captain, Raven, ArcPod, Agent, Crew`.
  - `captain-raven-blocked` (captain, chat, blocked): requires `ArcLink support`.
  - `operator-raven-status` (operator, chat, proof_gated): requires `Operator Raven, ArcPod,
    Next:`; proof_gates `PG-PROD, PG-BOTS, PG-PROVISION, PG-UPGRADE`.
  - `dashboard-readiness-blocked` (operator, dashboard, blocked): requires `ArcPod provisioning,
    next_action`; proof_gate `PG-FLEET/PG-PROVISION`.
  - `product-surface-home` (captain, web): requires `Captain, ArcPod, Raven`.
  - `deploy-readiness-cli-copy` (operator, cli, blocked): requires `ArcPod provisioning, control
    register-worker, ready to provision ArcPods`.

### A3. The local product surface (`python/arclink_product_surface.py`, 816 lines)

A stdlib-only WSGI **prototype** (explicitly "local no-secret ArcLink product surface", L797).
NOT production. The production customer-facing app is the Next.js `web/` app + hosted WSGI API
(`arclink_hosted_api.py`). This module:
- Entry: `handle_arclink_product_surface_request(conn, *, method, path, params, stripe_client,
  env)` returning `ArcLinkSurfaceResponse(status, body, content_type, headers)`.
- WSGI factory `make_arclink_product_surface_app(...)`; CLI `main()` serving on
  `127.0.0.1:8088` (env: `ARCLINK_PRODUCT_SURFACE_DB/HOST/PORT`).
- Routes (real, local-only): `GET /`, `GET /favicon.ico`, `GET /checkout/{success,cancel}`,
  `POST /onboarding/start`, `GET /onboarding/{id}`, `POST /onboarding/{id}/{answer,checkout,
  cancel}`, `GET /user`, `GET /admin`, `POST /admin/actions`, plus JSON `GET /api/onboarding/{id}`,
  `GET /api/user`, `GET /api/admin`, `POST /api/admin/actions`.
- Uses `FakeStripeClient` by default (L647, L807). Admin actions route through
  `queue_admin_action_api` (real CSRF/session/idempotency path); the admin page renders the
  `action_execution_readiness` matrix with **disabled** options for `pending_not_implemented`
  actions ("disabled until worker wiring lands", L529).
- Brand is applied inline in `_layout()` (L190-308) and the favicon SVG (L46-51). The CSS palette
  exactly matches `brand-system.md`: `--jet:#080808; --carbon:#0F0F0E; --soft:#E7E6E6;
  --signal:#FB5005; --blue:#2075FE; --green:#1AC153;`, fonts Space Grotesk (headings) +
  Inter/Satoshi (body), orange right-arrow buttons (`Start &gt;`).
- Captain-facing copy now uses the canon: hero "Your AI workforce. Deployed.", "Raven helps each
  Captain start an ArcPod...", nav "Captain Dashboard", table empty-states "No ArcPods yet.",
  metrics "ArcPod records" / "Live provider mutations: 0", checkout copy "your ArcLink agent moves
  into the launch queue."

### A4. Canonical vocabulary as enforced by code

`docs/arclink/vocabulary.md` is the canon, and the surface gate enforces its core rules at the
Captain boundary. Captain/Operator/ArcPod/Crew/Raven all appear as real, load-bearing terms in
the gate's `required_terms` and `_CAPTAIN_FORBIDDEN_PATTERNS`. "Raven" is the public bot/onboarding
persona (real in `arclink_public_bots.py`); "Operator Raven" is the chat operator console
(`arclink_operator_raven.py`, real but first-slice; see GAP-029). "ArcPod"/"Pod" replace
"deployment" on Captain surfaces; the schema name stays `arclink_deployments` (operator canon).

---

## B. Proof-gated / fake-adapter / local-only (what is NOT product-real)

- **The whole product surface module** is a local prototype. It defaults to `FakeStripeClient`,
  seeds a fake fixture (`seed_arclink_product_surface_fixture`, with `docker_dry_run` jobs and a
  `secret://not-rendered` placeholder dashboard password in the test seed), and runs on loopback.
  No live Stripe/Docker/provider mutation happens here.
- **The finish gate itself proves only local copy quality.** It checks rendered/read **local**
  surface text. It does NOT prove how Telegram/Discord actually render markdown, how dashboard or
  plugin panels lay out in a browser, or how CLI/TUI wrap on a real terminal. Those are
  `GAP-033`'s open proof gates: `PG-PROD`, `PG-BOTS`, `PG-HERMES`.
- Operator Raven status, dashboard readiness, and deploy-readiness copy that the gate samples are
  themselves **proof-gated / blocked** surfaces (they cite `PG-PROD/PG-BOTS/PG-PROVISION/
  PG-UPGRADE/PG-FLEET`). The gate proves the *copy is honest about being gated*, not that the
  underlying live action works.
- Brand kit source `docs/arclink/brand/ArcLink Brandkit.pdf` exists (667 KB). The brand-system doc
  is "Version 1.0, May 2026" — descriptive of intent; only the palette/typography are mechanically
  proven (by matching the product-surface CSS).

---

## C. Exact module / table / service / command / route / proof-gate names (canonical vocabulary)

- Modules: `python/arclink_surface_contract.py`, `python/arclink_product_surface.py`. Real
  surfaces sampled: `arclink_public_bots.py`, `arclink_operator_raven.py`, `arclink_dashboard.py`,
  plus `plugins/hermes-agent/{drive,code,terminal}/dashboard/plugin_api.py`.
- Test: `tests/test_arclink_surface_contract.py`.
- Public functions/classes: `SurfaceSample`, `surface_contract_issues`, `assert_surface_contract`,
  `visible_text_from_html`; `handle_arclink_product_surface_request`,
  `make_arclink_product_surface_app`, `open_arclink_product_surface_db`,
  `seed_arclink_product_surface_fixture`, `ArcLinkSurfaceResponse`.
- Surface taxonomy literals: audiences `captain|operator|agent|mixed`; channels
  `chat|dashboard|plugin|cli|tui|api|web|docs`; states `normal|blocked|proof_gated`.
- Canonical product vocabulary (from `vocabulary.md`, enforced at Captain boundary):
  Captain-facing — **Raven, ArcPod, Pod, Hermes Agent, Captain, Crew, Comms, Comms Console,
  ArcPod Fuel, ArcPod Refueling, Crew Training, Crew Recipe, ArcLink Wrapped**;
  Operator-facing — **Operator, deployment (`arclink_deployments`), user (`arclink_users`),
  fleet host (`arclink_fleet_hosts`), inventory machine (`arclink_inventory_machines`), ASU**.
- Brand palette (verbatim, matches code): Jet Black `#080808`, Carbon `#0F0F0E`, Soft White
  `#E7E6E6`, Signal Orange `#FB5005`, Electric Blue `#2075FE`, Neon Green `#1AC153`.
- Proof-gate IDs touching this subsystem: `PG-PROD`, `PG-BOTS`, `PG-HERMES` (GAP-033's gates),
  and the gate samples additionally cite `PG-PROVISION`, `PG-UPGRADE`, `PG-FLEET`.
- Env vars: `ARCLINK_PRODUCT_SURFACE_DB`, `ARCLINK_PRODUCT_SURFACE_HOST`,
  `ARCLINK_PRODUCT_SURFACE_PORT` (default loopback `127.0.0.1:8088`).

---

## D. Undocumented / newer-than-docs in code

1. **The executable finish gate is undocumented as such in `professional-finish-gate.md`.** That
   doc describes the *concept* (Product/Admin/Engineering/Brand finish) but never names
   `arclink_surface_contract.py` or its concrete checks. The symphony doc and GAPS.md DO name it;
   the dedicated finish-gate doc does not.
2. **The exact surface taxonomy** (audiences captain/operator/agent/mixed; 8 channels; 3 states)
   exists only in code — no doc enumerates these literals.
3. **The blocked/proof-gated "must have a next action" rule** and the `_NEXT_ACTION_RE` keyword
   set are code-only; docs describe the intent ("explicit next actions after errors") but not the
   enforced keyword list.
4. **The specific secret/traceback regex inventory** (Slack `xox`, Notion `ntn_`, GitHub PAT
   shapes, Telegram-token shape, PEM) is code-only.
5. **DOC_STATUS.md does not classify `brand-system.md`, `professional-finish-gate.md`, or
   `sovereign-control-node-symphony.md`** — three docs this subsystem owns are absent from the
   status map (verified by grep: 0 hits each). The map's own maintenance rule says new public docs
   must be classified.
6. The product surface's `_ADMIN_ACTION_LABELS` (L503-516) and readiness-matrix rendering are
   newer than `brand-system.md`/`professional-finish-gate.md` (which predate the action-matrix work).

---

## E. Per-doc staleness verdicts and specific corrections

| Doc | DOC_STATUS class | Staleness | Specific correction needed |
| --- | --- | --- | --- |
| `docs/arclink/vocabulary.md` (May 30) | Canonical | **fresh** | Accurate and matches the gate. Minor: it does not mention `arclink_surface_contract.py` as the enforcing surface; the "Cross-references" section points to `RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` (exists) and `IMPLEMENTATION_PLAN.md` (exists, but DOC_STATUS marks it Historical). Could add a line naming the finish gate as the mechanical enforcer of the Captain canon. |
| `docs/arclink/brand-system.md` (May 4) | (unclassified) | **light** | Palette/typography/voice all still match the product-surface CSS, so content is fresh. Two fixes: (1) add it to `docs/DOC_STATUS.md` (currently absent). (2) Note the product surface uses the brand voice lines "Your AI workforce. Deployed." and "Private AI infrastructure" but NOT the documented short promise "Built once. Runs forever." (drift between brand canon and shipped copy). |
| `docs/arclink/professional-finish-gate.md` (May 6) | (unclassified) | **heavy (missing the executable gate)** | The doc is prose-only and predates `arclink_surface_contract.py`. Add a section naming the real enforced gate (`python/arclink_surface_contract.py` + `tests/test_arclink_surface_contract.py`), its audience/channel/state taxonomy, the Captain-vocabulary lint, secret/traceback refusal, and the blocked-copy "next action" rule. Also add it to DOC_STATUS. |
| `docs/arclink/document-phase-status.md` (May 30) | Historical | **heavy** | Last dated note is 2026-05-16. It never records the 2026-05-27 GAP-033-A surface-contract slice, GAP-034 Academy work, or GAP-029 Operator Raven slice. Its embedded matrix totals are stale at "100/98 real" in older sub-sections; the current matrix is 101 real / 15 proof-gated / 5 policy-question. Treat as a historical log; if updated, append a 2026-05-27+ note for the finish gate. |
| `docs/arclink/CHANGELOG.md` (May 8) | Historical | **heavy** | Stops at "Native Hermes Workspace Plugins (2026-05-05)" / Foundation. No entry for the surface contract gate, Operator Raven, Academy Trainer, LLM router, fleet phases, or Wrapped. Last entry predates ~30 GAP rows. If refreshed, add the cross-surface finish gate and the GAP-029/033/034 slices. |
| `GAPS.md` (May 29) | (research, Historical by `research/*` rule — but it is at repo root, not under research/) | **fresh for GAP-033; internally consistent** | GAP-033 accurately reflects the code (names `arclink_surface_contract.py`, status quality-gap/proof-gated, gates PG-PROD/PG-BOTS/PG-HERMES). Header claims matrix totals "101 real, 0 partial, 0 gap, 15 proof-gated, 5 policy-question" and GAP-012 says "121 parsed rows" — verified consistent (101+15+5=121) against the matrix table. No correction needed for this subsystem's rows. |
| `mission_status.md` (May 27) | (root) | **fresh** | The "GAP-033-A Cross-Surface Product Finish Contract" section (L196+) matches code exactly: file list, validation commands, and "1342 passed, 6 skipped" suite result. No correction. |
| `USER_JOURNEY.md` (May 27) | (root) | **light** | References GAP-033 across joints; consistent with COVERAGE_MATRIX. Not re-audited line-by-line here, but no contradiction surfaced. |
| `research/COVERAGE_MATRIX.md` (May 27) | Historical | **fresh** | Correctly maps `tests/test_arclink_surface_contract.py` to J-01, J-03, J-04, J-13, J-14, J-19, J-24, J-27 — exactly matching GAP-033's journey joints. No correction. |
| `research/PRODUCT_REALITY_MATRIX.md` (May 22) | Historical | **light** | Header totals "101 real, 0 partial, 0 gap, 15 proof-gated, 5 policy-question" are verified accurate against actual table-row counts (101 real / 15 proof-gated / 5 policy-question; the only "partial/gap" grep hits are prose, not status cells). Dated May 22, so it predates the May 27 finish-gate slice; a surface-contract / cross-surface-finish row is not individually called out, though GAP-033 covers it. |

Cross-doc note: `docs/DOC_STATUS.md` is itself the classifier the prompt calls "DOC_STATUS." It
classifies vocabulary.md (Canonical), document-phase-status.md (Historical), CHANGELOG.md
(Historical), CREATIVE_BRIEF.md (Speculative), and the research/* tree (Historical), but **omits
brand-system.md, professional-finish-gate.md, and sovereign-control-node-symphony.md** entirely —
the single highest-value correction for the swarm.

---

## F. Authoritative current GAP-* ledger status (source of truth)

`GAPS.md` defines GAP-001..GAP-034 (GAP-008 absent; numbering otherwise contiguous). Verified
current status lines (grep of `^- Status:` paired with headers):

| GAP | Title (abbrev) | Status (current, per GAPS.md) | Notes for swarm |
| --- | --- | --- | --- |
| GAP-001 | Production live E2E unproven | proof-gated | P0 launch gate (`PG-PROD`). |
| GAP-002 | Live Stripe checkout/portal/webhook/refuel | proof-gated | `PG-STRIPE`. |
| GAP-003 | Live Telegram/Discord Raven delivery | proof-gated | `PG-BOTS`. |
| GAP-004 | Live executor/fleet/Cloudflare/Tailscale apply | proof-gated | `PG-PROVISION`, `PG-INGRESS`. |
| GAP-005 | Hermes/Drive/Code/Terminal live browser proof | proof-gated | `PG-HERMES`. |
| GAP-006 | Provider live behavior + self-service policy | proof-gated, policy-question | `PG-PROVIDER`. |
| GAP-007 | Notion setup is preparation, not completed | proof-gated | `PG-NOTION`. |
| GAP-009 | Browser proof tokens session-only | **real** (closed locally). |
| GAP-010 | Web preferred-channel copy aligned | **real** (closed locally). |
| GAP-011 | Foundation docs align with Control Node | **real** (closed locally; guarded by `tests/test_documentation_truths.py`). |
| GAP-012 | Product matrix rows locally guarded | **real** (closed locally; matrix = 101 real / 15 proof-gated / 5 policy-question / 121 total). |
| GAP-013 | Raven backup prep stops before key setup | partial, ux-gap, ops-gap | `PG-BACKUP`. |
| GAP-014 | Browser share needs live broker/adapter | partial, policy-question. |
| GAP-015 | Share approval can silently wait (no linked channel) | proof-gated. |
| GAP-016 | Linked copy/duplicate policy aligned | **real** (closed locally). |
| GAP-017 | Captain-initiated Pod migration disabled by policy | policy-question (`ARCLINK_CAPTAIN_MIGRATION_ENABLED=0` default). |
| GAP-018 | Admin action live side effects modeled not proven | proof-gated, ops-gap | readiness matrix local-real (rendered by product surface admin page). |
| GAP-019 | Docker socket/root services P0 trusted-host boundary | security-risk, ops-gap | Largest row: sub-items A..BD; many local hardenings landed, next closure needs more helper/process isolation or accepted residual risk. |
| GAP-020 | Backup/DR documented not proofed | partial, proof-gated, ops-gap. |
| GAP-021 | Cloud provider fleet creation | proof-gated. |
| GAP-022 | Crew Training live LLM generation | proof-gated. |
| GAP-023 | Public selected-agent streaming explicitly unvalidated | proof-gated (`ARCLINK_PUBLIC_AGENT_BRIDGE_STREAMING=1` opt-in). |
| GAP-024 | Provider changes visible not self-service | policy-question, ux-gap. |
| GAP-025 | Broad local Python suite green | **real** (closed locally; `python3 -m pytest -q tests`). |
| GAP-026 | Live upgrade proof unproven | proof-gated, ops-gap | `PG-UPGRADE`. |
| GAP-027 | Discord Curator operator-action authority policy | policy-question, security-risk, doc-gap, test-gap. |
| GAP-028 | Shared Host install/enrollment smoke not current | proof-gated, ops-gap | `PG-SHARED-HOST`. |
| GAP-029 | Operator Raven not full-service control plane | product-gap, security-sensitive, local-gap | First read-only/dry-run slice exists in `arclink_operator_raven.py`; mutation gated. |
| GAP-030 | Sovereign worker readiness live proof | proof-gated | `PG-FLEET`/`PG-PROVISION`. |
| GAP-031 | LLM Router fallback cascade live proof | proof-gated. |
| GAP-032 | Control Node rolling Hermes/ArcPod updates | product-gap, proof-gated. |
| **GAP-033** | **Cross-surface experience finish gate** | **quality-gap, proof-gated** | **THIS SUBSYSTEM.** GAP-033-A landed: `arclink_surface_contract.py` + test are the local enforced gate. Remains open ONLY for authorized `PG-PROD`/`PG-BOTS`/`PG-HERMES` browser/chat/workspace proof. Joints J-01,03,04,13,14,19,24,27. |
| GAP-034 | Academy Trainer corpus + continuing education | partial, product-gap, policy-question, data-governance-gap, provider-proof-gated | Sub-items A..E landed locally (`arclink_academy_trainer.py`); no-write/no-network; needs `PG-PROVIDER`/`PG-HERMES`. |

**True status this subsystem must convey to others:**
- **GAP-033 is NOT closed.** Its local source slice (GAP-033-A) is done, tested, and green, but
  the gap stays `quality-gap, proof-gated` pending live `PG-PROD`/`PG-BOTS`/`PG-HERMES`.
- **GAP-011, GAP-012, GAP-025, GAP-009, GAP-010, GAP-016 are the "closed locally / real" rows** —
  do not let a doc resurrect them as open. The two header-level "closed locally" callouts in
  GAPS.md are GAP-011 (docs align) and GAP-025 (suite green).
- The matrix is the status SSOT for the *product claims*; GAPS.md is the SSOT for *gap taxonomy/
  severity/proof gates*. Current matrix: **101 real, 0 partial, 0 gap, 15 proof-gated, 5
  policy-question (121 rows)** — guarded by `tests/test_documentation_truths.py`.
</content>
