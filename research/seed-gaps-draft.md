# ArcLink Gaps

> REFERENCE DRAFT — NOT GROUND TRUTH. A quick v0 seed kept only as input for the
> Ralphie journey/gaps audit. CRITICAL: the matrix counts quoted below ("0 gap,
> 0 partial") are an UNVERIFIED CLAIM TO DISPROVE, not a starting truth. The
> audit independently regenerates the root `GAPS.md`, derives every row from
> fresh source evidence, and must hunt for net-new gaps the matrix missed.

This register compares the `USER_JOURNEY.md` product story against the current
public repository evidence. The latest product matrix reports 101 `real`, 0
`partial`, 0 `gap`, 15 `proof-gated`, and 5 `policy-question` rows. This file
starts from that source truth and gives Ralphie's journey audit a sharper place
to keep non-real, under-proven, and decision-owned work.

## Taxonomy

| Status | Meaning |
| --- | --- |
| `gap` | The intended behavior is absent or contradicted by source evidence. |
| `partial` | Some implementation exists, but the end-to-end journey is incomplete. |
| `proof-gated` | Local code exists or intent is clear, but live/external proof is required. |
| `policy-question` | Product, security, pricing, or operations choice cannot be decided by code. |
| `test-gap` | Code may exist, but local regression proof is missing or too weak. |
| `doc-gap` | User/operator documentation is absent, misleading, or stale. |
| `ux-gap` | Behavior exists but the user-facing surface is confusing or too hidden. |
| `ops-gap` | Operational path is unclear, manual, or missing safe runbook coverage. |
| `security-risk` | A path could violate isolation, secret safety, payment trust, or authority boundaries. |
| `real` | Source evidence and tests support the claim locally. |

Severity:

| Severity | Meaning |
| --- | --- |
| P0 | Blocks trust, user isolation, payment, provisioning, data safety, or secret safety. |
| P1 | Blocks a core Captain journey or operator journey. |
| P2 | Causes degraded behavior, confusing recovery, or incomplete confidence. |
| P3 | Polish, scale hardening, future product option, or documentation depth. |

## Current Non-Real Register

| ID | Severity | Status | Journey joint | Expected behavior | Current evidence | Missing proof or decision | Next repair |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LIVE-STRIPE-001 | P0 | `proof-gated` | Checkout and entitlement | Live Stripe checkout and signed webhooks advance entitlement before provisioning. | `research/PRODUCT_REALITY_MATRIX.md:51`; hosted routes exist in `python/arclink_hosted_api.py`. | Authorized Stripe test/live credentials and webhook proof. | Run credentialed live proof, capture evidence, keep public copy proof-gated until then. |
| LIVE-HERMES-001 | P1 | `proof-gated` | Dashboard handoff | Stored Hermes dashboard link lands in the real deployed Hermes dashboard. | `research/PRODUCT_REALITY_MATRIX.md:59`; provisioning renders dashboard service and scoped links locally. | Authorized deployed Pod/browser proof. | Add live browser smoke evidence after control/worker deploy. |
| MEM-POLICY-001 | P2 | `policy-question` | Multi-agent memory | Scoped self-model or peer-awareness cards are safe and useful for Crew work. | `research/PRODUCT_REALITY_MATRIX.md:114`. | Operator policy for cross-agent awareness, redaction, audit, and transcript exclusion. | Decide product policy before implementing peer-awareness cards. |
| NOTION-PROOF-001 | P1 | `proof-gated` | Notion setup alternate model | User-shared page to integration/control identity works reliably. | `research/PRODUCT_REALITY_MATRIX.md:124`. | Authorized Notion workspace permission proof. | Keep shared-root SSOT as canonical unless proof changes the lane. |
| NOTION-PROOF-002 | P2 | `proof-gated` | Notion setup alternate model | User-owned integration token/OAuth can be a viable optional lane. | `research/PRODUCT_REALITY_MATRIX.md:125`. | Product choice plus OAuth/integration proof. | Build/prove only if this becomes an approved lane. |
| LIVE-STRIPE-002 | P0 | `proof-gated` | Billing truth | Stripe payments are the live system of record. | `research/PRODUCT_REALITY_MATRIX.md:140`; local webhook/state paths exist. | Live Stripe account proof. | Tie live proof to payment-gated provisioning journey. |
| SHARE-UX-001 | P1 | `policy-question` | Browser sharing | Drive/Code right-click can generate a living ArcLink share link. | `research/PRODUCT_REALITY_MATRIX.md:155`; browser share UI is disabled while MCP/API share grants exist. | Decide and prove ArcLink browser broker or Nextcloud/WebDAV-backed adapter. | Keep disabled until a backed adapter is implemented, tested, and enabled. |
| INGRESS-CF-001 | P1 | `proof-gated` | Domain ingress | Cloudflare verifies zone/domain control before ready. | `research/PRODUCT_REALITY_MATRIX.md:171`; fake ingress tests exist. | Authorized Cloudflare zone/token proof. | Run live DNS proof with redacted evidence. |
| INGRESS-TS-001 | P1 | `proof-gated` | Tailscale ingress | Tailscale verifies connectivity, certificates, and serve/funnel readiness. | `research/PRODUCT_REALITY_MATRIX.md:172`. | Authorized tailnet proof. | Run live Tailscale proof and record accepted modes. |
| CHUTES-POLICY-001 | P1 | `policy-question` | Provider account model | Per-user Chutes OAuth/delegated account is the canonical provider path. | `research/PRODUCT_REALITY_MATRIX.md:197`. | Operator product decision and live OAuth inference proof. | Choose canonical provider lane; keep OAuth surfaces disabled/proof-gated until proven. |
| CHUTES-LIVE-001 | P1 | `proof-gated` | Provider key lifecycle | Operator account can create per-user Chutes keys after approved handshake. | `research/PRODUCT_REALITY_MATRIX.md:198`. | External Chutes account/API proof. | Verify against authorized account/docs; keep fail-closed adapter. |
| CHUTES-POLICY-002 | P1 | `policy-question` | Provider threshold recovery | Raven/dashboard advises a safe continuation path near utilization threshold. | `research/PRODUCT_REALITY_MATRIX.md:201`. | Policy for refill, fallback, suspension, or user action. | Decide threshold continuation before adding actionable copy. |
| PROVIDER-POLICY-001 | P2 | `policy-question` | Provider settings | User can add another provider via Hermes `/provider` or ArcLink settings. | `research/PRODUCT_REALITY_MATRIX.md:202`; dashboard does not collect raw provider tokens. | Policy for self-service provider mutation and credential handoff. | Decide dashboard vs Hermes vs operator-managed provider flow. |
| REFUEL-LIVE-001 | P1 | `proof-gated` | ArcPod Refueling | Captain can buy ArcPod fuel through live Refueling. | `research/PRODUCT_REALITY_MATRIX.md:203`; local credit accounting exists. | Live payment/provider proof. | Keep purchase copy proof-gated; prove checkout and credit application. |
| REFUEL-LIVE-002 | P1 | `proof-gated` | ArcPod Refueling | Live purchase and credit application are proven. | `research/PRODUCT_REALITY_MATRIX.md:205`. | Authorized Stripe/Chutes proof run. | Capture live proof after local SKU path and provider policy are stable. |
| CHUTES-LIVE-002 | P1 | `proof-gated` | Chutes OAuth | Live Chutes OAuth connect and delegated inference are proven. | `research/PRODUCT_REALITY_MATRIX.md:206`; local fake OAuth harness exists. | Authorized Chutes OAuth account and inference proof. | Run live OAuth proof with secret refs and redacted evidence. |
| CHUTES-LIVE-003 | P2 | `proof-gated` | Provider usage sync | Personal provider usage, quota, billing, discounts, and price overrides sync from the model provider. | `research/PRODUCT_REALITY_MATRIX.md:207`; fixture-backed provider adapter exists. | Live provider account response proof and scope confirmation. | Keep fixture-backed boundary until authorized live sync. |
| CHUTES-LIVE-004 | P1 | `proof-gated` | Chutes value movement | Balance transfer or direct provider-balance application is proven. | `research/PRODUCT_REALITY_MATRIX.md:208`. | Explicit live-mutation authorization and Chutes account proof. | Treat ArcPod Refueling as internal credit until external transfer proof exists. |
| CHUTES-LIVE-005 | P1 | `proof-gated` | Provider metering | Live Chutes per-key utilization is verified. | `research/PRODUCT_REALITY_MATRIX.md:209`. | Live per-key metering capability proof. | Use per-user account/OAuth fallback if per-key metering cannot be proven. |
| CHUTES-LIVE-006 | P1 | `proof-gated` | Provider key lifecycle | Live Chutes key creation, rotation, and removal are verified. | `research/PRODUCT_REALITY_MATRIX.md:210`; fail-closed adapter and fake tests exist. | Authorized Chutes key-management proof. | Verify API capability; preserve redaction and fail-closed behavior. |

## Not Gaps / Already Real

These surfaces are important enough to record as checked, not because they need
no future maintenance, but because the current product matrix marks the local
source contract as real:

| Surface | Current posture |
| --- | --- |
| Website, Telegram, and Discord onboarding start | Real locally through hosted API and public bot adapters. |
| Payment-gated provisioning | Real locally; unpaid sessions and deployments stay blocked. |
| Credential handoff acknowledgement and hiding | Real locally through user API/dashboard behavior. |
| Raven as post-onboarding control conduit | Real locally for status, roster, switching, channel linking, selected-agent routing, and share approval controls. |
| qmd/vault/PDF/Notion indexing rails | Real locally through MCP, qmd, SSOT, webhook, and batcher surfaces. |
| Managed context recall stubs and retrieval guidance | Real locally, including compact recall and preferred MCP tools. |
| Drive/Code/Terminal dashboard plugin installation | Real locally, including independent plugin behavior. |
| Linked resources as read-only roots | Real locally, including no reshare and copy/duplicate into owned space. |
| Single-operator owner policy | Real locally. |
| User/admin isolation for dashboards and health | Real locally through scoped API/read-model tests. |
| Component pins and ArcLink upgrade rails | Real locally; live host upgrade remains an operator-authorized operation. |
| Refuel local ledger | Real locally; live purchase/provider application remains proof-gated. |

## Proof Gates

Before moving proof-gated rows to `real`, capture redacted evidence for:

- Stripe checkout, signed webhooks, invoice/renewal states, and entitlement
  transitions.
- A deployed Pod's Hermes dashboard landing in a real browser.
- Cloudflare domain/zone verification and DNS mutation.
- Tailscale serve/funnel/cert/connectivity verification.
- Notion permission behavior for non-canonical user-share/OAuth alternatives.
- Chutes OAuth, delegated inference, usage/quota/billing sync, key lifecycle,
  per-key metering, and any balance transfer or provider-balance application.
- ArcPod Refueling live purchase and credit application.

## Policy Questions

| ID | Decision needed |
| --- | --- |
| MEM-POLICY-001 | Should ArcLink build scoped self-model or peer-awareness cards for multi-agent work, and what redaction/audit boundaries are mandatory? |
| SHARE-UX-001 | Should browser right-click sharing use a native ArcLink broker, Nextcloud/WebDAV/OCS adapter, or stay disabled until a later release? |
| CHUTES-POLICY-001 | Is per-user Chutes OAuth the canonical provider model now, or should operator-scoped keys remain primary with OAuth as future proof? |
| CHUTES-POLICY-002 | What should Raven/dashboard tell Captains near provider utilization threshold: refuel, pause, fallback, contact operator, or something else? |
| PROVIDER-POLICY-001 | Should users self-service provider changes in ArcLink settings, Hermes `/provider`, operator-managed config, or a secure credential handoff flow? |

## Test Plan

Focused local checks for future gap work should include:

- `python3 tests/test_arclink_hosted_api.py`
- `python3 tests/test_arclink_public_bots.py`
- `python3 tests/test_arclink_telegram.py`
- `python3 tests/test_arclink_discord.py`
- `python3 tests/test_arclink_provisioning.py`
- `python3 tests/test_arclink_entitlements.py`
- `python3 tests/test_arclink_chutes_and_adapters.py`
- `python3 tests/test_arclink_chutes_oauth.py`
- `python3 tests/test_arclink_plugins.py`
- `python3 tests/test_arclink_mcp_schemas.py`
- `python3 tests/test_memory_synthesizer.py`
- `python3 tests/test_notion_ssot.py`
- `python3 tests/test_deploy_regressions.py`
- `git diff --check`

Web validation, when web dependencies are installed, should include:

- `cd web && npm run lint`
- `cd web && npm test`
- `cd web && npm run build`
- `cd web && npm run test:browser`

Live proof commands must remain credential-gated and operator-authorized.

## Ralphie Follow-Up

Run the special mission with:

```bash
./ralphie.sh --arclink-user-journey-audit --no-resume
```

That mode writes focused prompts, requires both Codex and Claude to be healthy,
uses high-rigor consensus, and deepens this register against the actual code,
tests, services, config, and docs.
