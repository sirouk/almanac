# CANON-03 — Web App & Product Surface — DECIDED (Federation final adjudication)

Adjudicator: Claude Opus 4.8 (final, two-model Federation, DECISION mode).
Counterpart proposal: `research/canon/decisions/CANON-03-web-product-surface.codex.md` (Codex GPT-5.5 xhigh).
Method: form my own view from symphony + re-opened code, then converge with Codex.
Every cite re-opened at path:line; code wins over name/comment/prior claim.

North Star anchors used throughout:
- "Operators own the universe: hosts, secrets, fleet, policy, upgrades, backups,
  live proof, emergency repair, and product rollout." (symphony L113–115)
- "Captains own their Pods and Crew, not the host." (L116)
- Whole-System Traversal: "Every step should have a local source owner, a local
  regression or dry-run proof where possible, and a named live proof gate where
  external systems are required. If any step cannot say what surface owns it,
  what state it reads, what state it writes, and how it fails closed, the
  symphony is not complete." (L156–162)
- "Operator Raven, admin dashboard, CLI, diagnostics, live proof, and evidence
  rails show the same system truth." (L148–149)
- Third-Party Integration Boundaries: "Cloudflare and Tailscale own ingress
  primitives; ArcLink owns desired-state records, teardown evidence, proof
  gates, and clear domain/Tailscale mode selection." (L916–919)
- Notifications/Evidence: "preserve state by default and leave redacted evidence
  of what happened." (L151–153)

---

## DECISION 1 — Admin CIDR allowlist must not depend on opaque Next-rewrite XFF behavior

**[VERDICT: refine]** — Codex's direction and end-state are correct. I converge on
Codex's plan with two code-grounded refinements that change the blast-radius and
the framing (one *down*, one *up*).

### The question
The admin-CIDR control's effectiveness depends on whether the Next standalone
rewrite forwards a real client IP via XFF. With no XFF, the API resolves the
direct peer (loopback / Docker-net), `_backend_client_allowed` returns true, and
every CIDR-protected admin route passes for everyone. Fixing it is a
transport-contract change wider than CANON-03 page code. What do we do?

### My independent reasoning (re-opened code)

1. **There is no admin allowlist today — only a backend/proxy-trust list.** The
   CIDR-protected gate is `_backend_client_allowed(cfg, client_ip)`
   (`python/arclink_hosted_api.py:4090-4092`), which is
   `is_loopback_ip(ip) OR is_ip_in_cidrs(ip, backend_allowed_cidrs)`
   (`:656-660`). `backend_allowed_cidrs` defaults to `172.16.0.0/12`
   (`compose.yaml:53`, `bin/docker-entrypoint.sh:455`, `bin/deploy.sh:8488`) —
   the entire Docker bridge range. There is **no** `ARCLINK_ADMIN_ALLOWED_CIDRS`
   in the config object (`:215` defines only `backend_allowed_cidrs`; grep
   confirms no admin variant in `python/`). So "admin CIDR allowlist" is really
   "are you a trusted backend/proxy peer" — proxy-trust and operator-admin-source
   are the **same** boolean. That conflation is the root symphony violation:
   operator network policy ("who may reach admin") is not separable from
   transport plumbing ("which proxy may set XFF"). This is exactly Codex's split.

2. **`_remote_ip_from_headers` trusts XFF whenever the direct peer is
   backend-allowed** (`:632-653`): if `direct` is loopback or in 172.16/12, it
   takes the first XFF hop verbatim. Traefik's `config/traefik-control.yaml` sets
   **no** `forwardedHeaders.trustedIPs` (grep: none). So any peer inside
   172.16/12 — including a co-resident container or a misconfigured upstream —
   can present an arbitrary XFF and have it trusted, and a peer with *no* XFF
   collapses to the direct-peer IP which is itself backend-allowed. Both halves
   fail open toward "admin allowed."

3. **REFINEMENT DOWN — the Next rewrite is already dead in the production `/api`
   path.** Codex frames removing/dev-gating the `next.config.ts` rewrite as a
   risky transport change. In Docker/prod it is not: `control-ingress` (Traefik)
   routes `PathPrefix(/api)` → `http://control-api:8900` at **priority 150**
   (`config/traefik-control.yaml:15-20`), strictly above the `PathPrefix(/)` →
   `control-web:3000` catch-all at **priority 1** (`:21-26`). Traefik binds the
   public web port (`compose.yaml:646-648`, `127.0.0.1:3000:8080`). So in
   prod, `/api/v1/*` never traverses `control-web`/Next at all — Traefik is
   already the source-owned `/api` transport. The Next rewrite (`next.config.ts:7-14`,
   `→ http://127.0.0.1:8900`) only matters in `next dev` or a Next-standalone
   deploy *without* Traefik. That makes "remove or dev-gate the rewrite" cheap and
   correct, not scary: it removes a *fallback* transport contract that competes
   with the real one. Keep the rewrite behind a dev-only flag so local `npm run
   dev` still proxies, but it is never the prod admin path.

4. **REFINEMENT UP — the real fail-open is the missing proxy/admin split AND the
   loopback-always-trusted XFF acceptance, independent of Next.** Even with
   Traefik as the only `/api` transport, the API still trusts XFF from the entire
   Docker bridge and still has no distinct admin allowlist. So fixing this is not
   "prove Next forwards XFF" — it is: (a) make Traefik the only trusted proxy and
   set `forwardedHeaders.trustedIPs` to *just* the ingress, (b) split config into
   `ARCLINK_TRUSTED_PROXY_CIDRS` (who may set XFF) and `ARCLINK_ADMIN_ALLOWED_CIDRS`
   (who may reach admin), (c) trust XFF only from a trusted proxy, and (d)
   gate `_CIDR_PROTECTED_ROUTES` against the *admin* list, not the *backend* list.
   This is precisely Codex's recommendation; my code read strengthens its
   necessity (the defect is structural, not merely "XFF unproven at deploy").

5. **Fails-closed default.** Today the default (`172.16.0.0/12`) is fail-*open*
   for admin (whole bridge = admin). The corrected default must be: admin
   allowlist **empty ⇒ admin reachable only from loopback on the API container**
   (operator on the box), and any XFF from a non-trusted-proxy peer is ignored
   (use direct peer). Operators widen `ARCLINK_ADMIN_ALLOWED_CIDRS` deliberately.
   That satisfies "fails closed" + "operators own policy."

### Where I agree / differ from Codex
- **Agree:** Traefik is the source-owned `/api` transport; split
  `ARCLINK_TRUSTED_PROXY_CIDRS` vs `ARCLINK_ADMIN_ALLOWED_CIDRS`; keep
  `ARCLINK_BACKEND_ALLOWED_CIDRS` as a migration alias with a clear reconfigure
  warning; the four named tests; the `PG-ADMIN-CIDR-XFF` live gate; `/auth/login`
  must obey the same resolved-IP admin policy (it already calls
  `_backend_client_allowed(login_client_ip)` at `:4148`, so it inherits the fix).
- **Differ (down):** removing/dev-gating the Next rewrite is **low**-risk, not a
  scary prod transport change — Traefik already owns prod `/api`. Don't gate the
  *whole* fix on it.
- **Differ (up):** the fix's core is the **proxy/admin config split +
  trusted-proxy-gated XFF**, plus setting Traefik `forwardedHeaders.trustedIPs`.
  Codex implies the variable is "deploy-time Next XFF"; the in-code structural
  fail-open (no admin list; XFF trusted across all of 172.16/12) is the actual
  defect and must be fixed regardless of Next.

### FINAL PLAN
1. **Config split** (`arclink_hosted_api.py` HostedApiConfig, ~`:215`): add
   `trusted_proxy_cidrs` (`ARCLINK_TRUSTED_PROXY_CIDRS`) and `admin_allowed_cidrs`
   (`ARCLINK_ADMIN_ALLOWED_CIDRS`). Keep `backend_allowed_cidrs` read as a
   migration alias: if the new keys are unset and the old key is set, seed
   `trusted_proxy_cidrs` from it and emit a single WARN that names the deprecation
   and tells the operator to reconfigure before claiming the proof gate.
2. **IP resolution** (`_remote_ip_from_headers`, `:632-653`): trust XFF/X-Real-IP
   only when the *direct peer* is in `trusted_proxy_cidrs` (not "loopback OR whole
   bridge"). Loopback stays trusted as a proxy only if explicitly configured;
   default trusted-proxy = the ingress. No XFF from a non-trusted peer ⇒ use the
   direct peer (which then fails the admin check unless it is itself allow-listed).
3. **Admin gate** (`:4090-4092`): gate `_CIDR_PROTECTED_ROUTES` and the
   `/auth/login` admin branch against a new `_admin_client_allowed(cfg, ip)`
   (`is_ip_in_cidrs(ip, admin_allowed_cidrs)`; default empty ⇒ loopback-only),
   **not** `_backend_client_allowed`. Broker/backend-peer routes keep
   `_backend_client_allowed`.
4. **Traefik** (`config/traefik-control.yaml`): add
   `forwardedHeaders.trustedIPs` (and `insecure: false`) scoped to the ingress so
   only Traefik may set XFF that the API trusts; document the ingress CIDR.
5. **Next rewrite** (`web/next.config.ts:7-14`): gate the `/api` rewrite behind a
   dev-only condition (`process.env.NODE_ENV !== "production"` or an explicit
   `ARCLINK_DEV_API_PROXY`), so prod relies solely on Traefik and local `npm run
   dev` still works. Document that Traefik owns prod `/api`.
6. **Deploy/config generation** (`bin/deploy.sh:8488`, `bin/docker-entrypoint.sh:455`):
   emit `ARCLINK_TRUSTED_PROXY_CIDRS` (ingress CIDR) and an empty/loopback-default
   `ARCLINK_ADMIN_ALLOWED_CIDRS`, with operator guidance to widen the admin list.
7. **Tests** (extend `tests/test_loopback_service_hardening.py` or a new
   `tests/test_admin_cidr_xff.py`): (a) no-XFF from loopback to an admin route is
   403 when admin list excludes loopback... [adjust: loopback-only default ⇒ 200
   from API-host loopback, 403 from non-allowed]; precisely: (i) allowed operator
   IP forwarded by trusted proxy ⇒ 200; (ii) spoofed XFF from a non-trusted peer
   ⇒ ignored ⇒ 403; (iii) trusted-proxy peer with no XFF ⇒ direct peer used ⇒ 403
   unless allow-listed; (iv) `/auth/login` cannot mint an admin session without
   the same resolved-IP admin policy.
8. **Live proof:** add `PG-ADMIN-CIDR-XFF` under the ingress/admin proof family,
   asserting that through real Traefik a non-allow-listed source gets 403 on
   admin routes and an allow-listed operator source gets 200, with a redacted
   `api_cidr_denied` evidence row.
9. **Admin-page 403 UX** (companion, `web/src/app/admin/page.tsx:160-164`): map
   403 to a distinct "this network is not on the operator admin allowlist"
   message instead of the generic "Failed to load admin data" — same truth across
   surfaces.

### Symphony anchor
North Star L113–116: "Operators own the universe: hosts, secrets, fleet,
**policy**…" and "Captains own their Pods and Crew, **not the host**." Operator
network/admin policy must live on the operator-owned ingress/API layer with an
explicit allowlist that **fails closed**, never inferred from Captain-facing Next
page behavior. Whole-System Traversal L156–162: a step is incomplete unless it
says "how it fails closed" — today it fails open. L148–149: dashboard, API, CLI,
and proof must "show the same system truth" (hence the 403 UX + named gate).

### Effort / blast-radius
**high** — touches hosted-API IP resolution + auth, Traefik ingress config, Next
config (dev-gate), deploy/config generation, admin-page 403 UX, tests, and a new
live-proof gate. (Net effort slightly below Codex's estimate because the Next
rewrite removal is prod-inert, but still high due to the config-split + proxy
trust + proof surface.)

---

## DECISION 2 — Dynamic ArcPod/fleet dashboard URLs need server-side host policy, not arbitrary `https://`

**[VERDICT: refine]** — Codex's design (a shared, operator-owned access-URL host
policy validating against generated/allowed hosts, fail-closed, preserve state +
redacted evidence) is right and symphony-aligned. I converge on it with a
**severity/effort down-scoping** grounded in the write path, plus a tighter
"single validator, single write boundary" implementation.

### The question
The repair blocks non-`http(s)` schemes, but stored `metadata.access_urls` are
accepted across server surfaces as long as each entry `startswith("https://")`.
Legitimate hosts vary (wildcard domain, Tailscale path/port, worker DNS,
WireGuard/private mesh, future custom domains). Should we add server-side host
policy, and how strict?

### My independent reasoning (re-opened code)

1. **`access_urls` is written in exactly ONE place, from server-generated input,
   not Captain/request data.** The only writer is
   `arclink_sovereign_worker.py:1593`
   (`metadata["access_urls"] = {...}`), and the `urls` it persists come from
   `_access_urls_for_deployment(...)` → `arclink_access_urls(...)`
   (the generator at `arclink_adapters.py:275-323`), driven by operator/worker
   config (`base_domain`, `tailscale_dns_name`, worker config), the control-DNS
   rewrite (`:820-835`). There is **no** code path where a Captain or HTTP request
   body sets `access_urls`. So this is **not** a live open-redirect today — it is
   **defense-in-depth + future-proofing** (custom-domain feature, config
   misconfiguration, DB tampering, restore from a foreign backup). That down-rates
   the *urgency* but not the *correctness* of Codex's design: the symphony wants a
   single owned policy so the control plane is "the one place where fleet and Pod
   state are understood" (L957-959) even as inputs widen.

2. **The `startswith("https://")` filter is duplicated across three readers** with
   identical intent: `arclink_public_bots.py:3422-3431` and `:3439-3452`,
   `arclink_dashboard.py:866-904`, and the provisioning read at
   `arclink_provisioning.py:824`. Duplication is itself a symphony risk: surfaces
   can drift, breaking "same truth across surfaces" (L148-149). A single shared
   validator removes that drift.

3. **The client already has a last-mile guard.** `safeNavigationHref`
   (`web/src/lib/api.ts:9-19`) parses the URL and admits only `http:`/`https:`,
   and React 19 neutralizes `javascript:` for hrefs. So the *web* surface is
   already protected against scheme abuse. The unprotected consumers are the
   **non-web handoff buttons** (Telegram/Discord via `arclink_public_bots.py`) and
   **hosted-API payloads** — exactly Codex's point that client-only is
   insufficient for Raven/bot/API surfaces. Host policy must therefore live
   server-side, shared.

4. **Host policy is an operator/deployment decision, not a hardcoded suffix.**
   Legitimate hosts span domain-mode wildcard hosts, Tailscale path+port hosts,
   worker private-mesh/WireGuard hosts, and operator custom domains. Hardcoding
   one public suffix would break tailnet/private-mesh/custom-domain installs —
   Codex is right to reject that. The validator must derive its allow-set from
   the same generators the system already uses (`arclink_hostnames`,
   `arclink_tailscale_hostnames`, worker DNS, operator custom-domain/suffix
   config) so policy = generation, by construction.

### Where I agree / differ from Codex
- **Agree:** shared server-owned validator around `arclink_access_urls(...)`;
  allow generated domain hosts, generated Tailscale path/port hosts, active
  worker private-mesh hosts, and explicit operator-configured custom
  domains/suffixes; keep the client scheme guard as last-mile; fail closed by
  *withholding* off-policy links (not deleting Pod state); preserve the offending
  URL in private metadata with a redacted policy-block event; surface a "dashboard
  link blocked by URL policy" + operator repair action; same local regressions
  (domain, custom-domain, Tailscale path, Tailscale port, WireGuard/private-mesh,
  hostile `https://evil.example`); add `PG-INGRESS-ACCESS-URLS`.
- **Differ (severity/effort down):** because `access_urls` has a **single
  server-generated writer** and **no request-controlled write path**, this is
  defense-in-depth, not an open vuln. I drop effort from **high** to **med**: the
  primary work is one validator + collapsing three duplicate readers + bot/API
  surfaces; the worker write-boundary change is small (validate the
  already-generated dict before persist at `:1593`).
- **Differ (scope tightening):** enforce at the **single write boundary**
  (`arclink_sovereign_worker.py:1593`, validate before persist) **and** the
  shared **read/render helper** (so legacy/foreign rows are filtered on read).
  Don't scatter the check; centralize it so all surfaces inherit one truth.

### FINAL PLAN
1. **One shared validator** (new `arclink_access_url_policy(...)` in
   `arclink_adapters.py`, beside `arclink_access_urls`): given a candidate URL +
   deployment context (prefix, base_domain, ingress_mode, tailscale dns/strategy,
   worker mesh host, operator custom-domain/suffix allowlist from private config),
   return allow/deny. Allow iff the parsed host equals a generated domain host,
   a generated Tailscale path/port host, an active worker private-mesh host, or
   matches an explicit operator custom-domain/suffix. Scheme must be `https`
   (or `http` only for explicitly-allowed local/dev hosts).
2. **Write boundary** (`arclink_sovereign_worker.py:1593`): validate each
   generated URL before persist; persist only policy-passing URLs as
   `access_urls`, and stash any policy-blocked URL under a private
   `access_urls_blocked` key with a redacted `access_url_policy_blocked` event
   (subject = deployment_id) — preserve state, leave redacted evidence.
3. **Read/render helper** (collapse the three duplicate filters): replace the
   inline `startswith("https://")` checks in `arclink_public_bots.py:3422-3452`,
   `arclink_dashboard.py:866-904`, and `arclink_provisioning.py:824` with the
   shared validator so off-policy stored rows are withheld on read across
   web/Raven/bot/hosted-API.
4. **Operator-visible repair:** where a link is withheld, render "dashboard link
   blocked by URL policy" with an operator repair action (re-resolve from
   generation / fix custom-domain config), consistent across dashboard + Raven +
   bot copy (same truth across surfaces).
5. **Keep client guard:** leave `safeNavigationHref` as the last-mile UI net.
6. **Local regressions:** domain host (allow), custom-domain (allow when
   configured), Tailscale path (allow), Tailscale port (allow), WireGuard/private
   mesh (allow when active), and `https://evil.example` (deny + blocked-evidence +
   withheld from all surfaces).
7. **Live proof:** `PG-INGRESS-ACCESS-URLS` under the ingress proof family —
   prove that a deployed Pod's real generated links pass policy and render, and
   that an injected off-policy row is withheld with redacted evidence.

### Symphony anchor
Third-Party Integration Boundaries L916–919: "Cloudflare and Tailscale own
ingress primitives; **ArcLink owns desired-state records**, teardown evidence,
**proof gates**…" — the access URL is an ArcLink desired-state record and must be
validated against ArcLink-owned host policy, not accepted because a third party
*could* host any `https://`. North Star L116: "Captains own their Pods and Crew,
**not the host**" — Captains/bot buttons must never be handed an off-host link the
operator didn't sanction. Fleet/Provisioning L957–959: "The Control Node should
be the one place where fleet and Pod state are understood." Evidence L151–153 /
L977+: "preserve state by default and leave redacted evidence."

### Effort / blast-radius
**med** — one new shared validator, one write-boundary guard, three duplicate
readers collapsed onto it, bot/dashboard/Raven repair copy, local regressions,
and one live-proof gate. Lower than Codex's "high" because there is a single
server-generated writer and no request-controlled write path (defense-in-depth,
not an open exploit), so no schema/intent changes are required — only validation
+ de-duplication at existing boundaries.

---

## STANDING DISAGREEMENTS / OPERATOR FORKS

None are unsettleable model-vs-model disputes — both decisions converge. Two
**operator policy choices** must be made at configuration time (not code forks):

- **D1:** the default contents of `ARCLINK_ADMIN_ALLOWED_CIDRS`. Recommended
  fail-closed default = loopback-only (operator-on-the-box); operator widens
  deliberately. The operator may instead choose an office/VPN CIDR at install.
- **D2:** whether to expose an operator **custom-domain/host-suffix allowlist**
  now (enabling future Captain custom domains) or keep the validator strictly to
  generated hosts until a custom-domain feature lands. Recommended: ship the
  validator with an *empty* custom-suffix list (generated hosts only), wired so
  the operator can opt in later — no fork in code, a config toggle.
