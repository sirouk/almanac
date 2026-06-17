# CANON-02 — Hosted API & Transport — DECIDED (final adjudication)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation, DECISION mode.
Codex proposal: `research/canon/decisions/CANON-02-hosted-api-transport.codex.md`.
Method: independent view formed against the symphony north star + re-opened code, THEN reconciled with Codex.
Every cite below was re-read by this adjudicator at the named `path:line`.

Both deferred items are genuine MEDIUM deployment-topology footguns that the
reconciled record already ratified. Neither is a HIGH. Both are fixable
source-side and both move code toward the symphony while failing closed. I
**agree with Codex's direction on both**, refine Decision 1 slightly (IPv6
loopback + explicit blank-raise), and refine Decision 2's rollout (one genuine
product fork on the unset-`ARCLINK_TRUSTED_PROXY_CIDRS` default that the operator
must pick).

================================================================================
## DECISION 1 — Unset `ARCLINK_BASE_DOMAIN` must not fall through to the fixed dev pepper
================================================================================

### [VERDICT] refine (agree with Codex's direction; tighten the local-domain set and the blank-raise)

### The question
`_session_hash_pepper()` (`python/arclink_api_auth.py:275-287`) returns the
publicly-known constant `"arclink-dev-session-hash-pepper"` whenever no explicit
pepper is set, `ARCLINK_SESSION_HASH_PEPPER_REQUIRED` is falsy, AND
`ARCLINK_BASE_DOMAIN` does not look production-like. A **blank/unset**
`ARCLINK_BASE_DOMAIN` makes `production_domain=False` (`:280-284`), so a
production deploy that forgets the domain *and* the required flag silently runs
with a forgeable, world-known HMAC pepper. Should unset-domain fail closed?

### Independent reasoning (formed before reconciling)
Re-read `python/arclink_api_auth.py:275-287`: the gate raises only when
`_truthy_env("ARCLINK_SESSION_HASH_PEPPER_REQUIRED")` OR `production_domain`.
`production_domain` is `bool(base_domain and base_domain not in {localhost,
127.0.0.1, example.test} and not endswith(".test"))`. With `base_domain == ""`,
the leading `and base_domain` short-circuits to `False` — so blank is treated as
"not production" and falls through to the dev constant. That is exactly
backwards: a blank domain is *less* certain to be dev than an explicit
`localhost`, yet it gets the same lenient treatment.

The symphony is unambiguous here. `Secrets, Keys, And Rotation` (`:1050`):
"Every credential should have status without disclosure: missing, present,
invalid, expiring, stale, rotated, revoked, live-proof pending, or blocked." A
world-known pepper has no honest status — it is "present but invalid." And
`Configuration, Schema, And Migration` (`:1076`): generated config should
"detect stale, missing, deprecated, or incompatible values before services
start." An unset base domain on the session-hash path is precisely a missing
value that should be caught at start, not silently substituted with a footgun.

Blast radius is small and the deploy lanes already protect themselves. I re-read
all canonical lanes: compose.yaml:78 pins `ARCLINK_SESSION_HASH_PEPPER_REQUIRED:
${...:-1}`; `bin/docker-entrypoint.sh:521` writes `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`
and `:728/:731` generate the pepper + force the flag; `bin/deploy.sh:2306` and
`:8471` both default the required flag to `1` and randomize/preserve the pepper.
So **no canonical Docker/deploy path is affected** — the required flag already
makes them raise on a missing pepper regardless of domain. The only surface that
changes is a *direct* `python` runner (dev/CI/ad-hoc) that sets neither the
pepper, nor the required flag, nor a recognizable local domain. That runner
*should* fail closed; convenience there is not worth a production-shaped footgun.

### Where I agree / differ from Codex
AGREE: the core fix — allow the fixed dev pepper only when the pepper is absent,
the required flag is false, AND the domain is an *explicit* local/test value;
blank/unset raises `ArcLinkApiAuthError` like production. AGREE: update
`tests/test_arclink_api_auth.py` (blank/unset → raise; explicit-local → fallback)
and `docs/API_REFERENCE.md` + env examples to state the dev fallback now requires
an explicitly-declared local/test domain.

REFINE (two small adjustments):
1. Codex's explicit local set is `{localhost, 127.0.0.1, ::1, example.test, *.test}`.
   The current code's local set is `{localhost, 127.0.0.1, example.test}` + `.test`
   suffix and is **missing `::1`** (IPv6 loopback). Add `::1` so an IPv6
   loopback dev box does not get wrongly classed as production. This is a real
   correctness gain, not just cosmetic.
2. Be explicit that the change is "blank → raise," i.e. flip the logic so the
   dev fallback is *opt-in by an allow-listed local domain*, not *opt-out by
   absence of a production-looking domain*. The current structure ("not in the
   known-local set AND not .test") happens to let blank slip through; the fix
   should be structured as `is_local = base_domain in LOCAL_SET or
   base_domain.endswith(".test")` then `if required or not is_local: raise`. With
   blank, `is_local` is `False` → raise. This phrasing removes the
   short-circuit footgun by construction.

### FINAL PLAN
In `python/arclink_api_auth.py:_session_hash_pepper()`:
- Define `LOCAL_DEV_DOMAINS = {"localhost", "127.0.0.1", "::1", "example.test"}`.
- Compute `is_local_dev = bool(base_domain) and (base_domain in LOCAL_DEV_DOMAINS
  or base_domain.endswith(".test"))`.
- Raise `ArcLinkApiAuthError("ArcLink session hash pepper is not configured")`
  when `_truthy_env("ARCLINK_SESSION_HASH_PEPPER_REQUIRED")` OR `not is_local_dev`.
  This makes blank/unset domain raise (because `bool("")` is `False` → not local
  dev → raise), while preserving the dev constant only for an explicitly declared
  local/test domain.
- Tests: extend `tests/test_arclink_api_auth.py` with (a) blank `ARCLINK_BASE_DOMAIN`,
  no pepper, no required flag → raises; (b) `ARCLINK_BASE_DOMAIN=localhost` (and
  `::1`) → returns the dev constant; (c) an explicit `.test` domain → dev constant;
  (d) any non-local domain → raises (already covered, re-assert).
- Docs: `docs/API_REFERENCE.md` + env examples — state the dev pepper fallback
  applies only with an explicit local/test `ARCLINK_BASE_DOMAIN`; unset/blank now
  fails closed exactly like production.

### Symphony anchor (quoted)
- `Secrets, Keys, And Rotation` (`docs/arclink/sovereign-control-node-symphony.md:1050`):
  "Every credential should have status without disclosure: missing, present,
  invalid, expiring, stale, rotated, revoked, live-proof pending, or blocked."
- `Configuration, Schema, And Migration` (`:1076`): generated config should
  "detect stale, missing, deprecated, or incompatible values before services start."
- North-star traversal (`:158-161`): every step must say "how it fails closed."
  An unset secret-source must fail closed, not substitute a known constant.

### Effort + blast-radius
EFFORT: **low**. Blast radius: one function in `python/arclink_api_auth.py`,
focused auth tests, `docs/API_REFERENCE.md` + env examples. **No canonical
deploy lane changes** — all already set `ARCLINK_SESSION_HASH_PEPPER_REQUIRED=1`
(verified compose.yaml:78, docker-entrypoint.sh:521/731, deploy.sh:2306/8471).
Only behavior change is for direct/dev runners with a blank domain, which is the
intended fail-closed outcome. No live-proof gate required (pure local logic +
regression); local regression IS the proof.

================================================================================
## DECISION 2 — Split trusted-proxy CIDRs from admin/client CIDRs; missing XFF behind a trusted proxy must fail closed
================================================================================

### [VERDICT] refine (agree the split is mandatory; refine the rollout + surface one product fork)

### The question
`ARCLINK_BACKEND_ALLOWED_CIDRS` is overloaded as BOTH (a) the set of peers whose
forwarded headers are trusted and (b) the final admin/client allowlist
(`python/arclink_hosted_api.py:649-660`). When the direct peer is a trusted proxy
(in the CIDR set) but sends **no** `X-Forwarded-For`/`X-Real-IP`,
`_remote_ip_from_headers` returns `direct` — the proxy IP itself (`:650-653`) —
which then passes `_backend_client_allowed` because the proxy is in the same
allowlist. The CIDR gate collapses to "is the request coming through the proxy,"
not "who is the client." How should proxy-trust be separated from client-allow,
and what happens with a missing XFF?

### Independent reasoning (formed before reconciling)
Re-read `python/arclink_hosted_api.py:633-660`. The post-repair code already
fixed the empty-`REMOTE_ADDR` half: blank `direct` now returns `""` (`:645-646`)
instead of falling back to `x-real-ip`/loopback. Good. But the *trusted-proxy-
without-XFF* half remains: when `direct` is a real proxy IP inside
`backend_allowed_cidrs`, and there is no forwarded header, line 653 returns
`direct` and `_backend_client_allowed(direct)` is `True` — so admin routes are
reachable by anyone who can route a request through the proxy without setting XFF.

This is live, not theoretical. I traced the Docker topology:
- `compose.yaml:53` defaults `ARCLINK_BACKEND_ALLOWED_CIDRS=172.16.0.0/12` — the
  Docker bridge network, i.e. the *proxy* range, not a client range.
- The web tier reaches the admin API through `web/next.config.ts:7-12`, a Next
  `rewrites()` that proxies `/api/v1/:path*` to `ARCLINK_API_INTERNAL_URL`
  (`http://127.0.0.1:8900` / internal). A Next rewrite does **not**
  authoritatively forward a client `X-Forwarded-For` the Python API can trust.
- `web/src/lib/api.ts:157-174` calls `/admin/dashboard`, `/admin/audit`, etc.
  with `kind:"admin"` — i.e. CIDR-protected admin routes are served *through the
  web proxy*. So the trusted peer the gate sees is the Next container's bridge IP
  (in `172.16.0.0/12` → allowed), and with no XFF the gate passes on the proxy IP
  alone. The admin CIDR gate is effectively a no-op for the proxied admin path.
- The existing test proves the overload directly: `tests/test_arclink_hosted_api.py:5264`
  sets `ARCLINK_BACKEND_ALLOWED_CIDRS="203.0.113.0/24,172.16.0.0/12"` — a client
  range AND the bridge/proxy range in one variable — and `:5301-5312` asserts
  trusted-proxy + XFF=allowed-client → 200. There is **no** test asserting
  trusted-proxy + *no* XFF → 403; under current code that case erroneously 200s.

The symphony mandates the split. `API, Webhook, And Extension Contracts` (`:1153`):
"Whenever a new surface is added, it should declare whether it is Captain-facing,
Operator-facing, Agent-facing, worker-facing, or internal-only. That declaration
should decide auth, audit, redaction, rate limiting, docs, and tests." A proxy
peer and an admin client are two different surfaces with two different trust
declarations; one variable cannot carry both honestly. `Identity, Access, And
Session Governance` (`:1022`): "Admin and Operator actions should never trust
client-asserted privilege ... without server-side authorization" — the current
gate trusts the *path* (came-through-proxy) as if it were *identity*. And the
north star (`:160-161`): a step must say "what state it reads ... and how it
fails closed" — missing XFF behind a declared proxy must deny, not widen.

The reconciled record already ratified this exact broadening: "RISK BROADER than
'empty only': trusted-proxy-WITHOUT-XFF also collapses gate to proxy IP — codex —
`python/arclink_hosted_api.py:635-641`." So the diagnosis is federation-settled;
this decision is about the fix shape.

### Where I agree / differ from Codex
AGREE (the spine): introduce `ARCLINK_TRUSTED_PROXY_CIDRS` as the *only* source
of peers whose forwarded headers are trusted; redefine
`ARCLINK_BACKEND_ALLOWED_CIDRS` as the resolved admin/client allowlist; rewrite
`_remote_ip_from_headers` so that (1) if `remote_addr` is a trusted proxy, it
*requires* a parseable `X-Forwarded-For` and returns its first IP, else returns
no client (gate 403s); (2) if the peer is not a trusted proxy, forwarded headers
are ignored and `remote_addr` is evaluated directly. AGREE: deploy/Compose
rendering must write both values explicitly; the Next rewrite must be
replaced/proven to forward a trustworthy `X-Forwarded-For` (source-owned, not
assumed); add local regressions for proxy-without-XFF denial, proxy-with-XFF
allow/deny, and untrusted-spoof rejection; gate real ingress under `PG-INGRESS`
(a real named gate, verified at `:283`).

REFINE / EXTEND:
1. **Loopback stays trusted.** Keep `is_loopback_ip(direct) → True` as a peer
   that may carry XFF, OR (cleaner) treat loopback as a trusted proxy implicitly.
   Direct loopback admin calls (e.g. operator on the host, CLI, `main()` default
   bind `127.0.0.1:8900`) must keep working — they are the operator-owns-host
   path. Do NOT require XFF from a loopback direct caller that is itself the
   admin client; only require XFF when loopback is acting as a *forwarding proxy*.
   Concretely: if `direct` is a trusted proxy (incl. loopback-as-proxy) AND a XFF
   is present, use the XFF; if `direct` is a trusted proxy and NO XFF, the client
   IS the direct peer — but a *proxy* should not be a valid admin client. The
   clean rule: a trusted-proxy peer with no XFF yields no client → 403 for
   CIDR-gated routes. A loopback peer that is the genuine admin client (operator
   on host) is handled by listing loopback in the *client* allowlist too, so it
   passes the final gate on its own IP. Spell this out so the operator-on-host
   golden path is not broken by the tightening.
2. **Make the conflation impossible to reintroduce.** `_backend_client_allowed`
   must evaluate the *client* allowlist only; add a distinct
   `_trusted_proxy_peer(config, ip)` predicate against `trusted_proxy_cidrs`.
   Parse both in `HostedApiConfig.__init__` next to `:215`.
3. **Carry the `/auth/login` admin-enable path too.** `hosted_api:4031-4038`
   (`allow_admin=_backend_client_allowed(cfg, login_client_ip)` with
   `login_client_ip=_remote_ip_from_headers(...)`) shares this resolver. The new
   resolver fixes it for free, but the regression suite must assert
   trusted-proxy-without-XFF does NOT enable admin login (the record flags this
   as a CONFIRMED LOW that rides the same footgun).
4. **PRODUCT FORK — unset `ARCLINK_TRUSTED_PROXY_CIDRS` default behavior.** This
   is a real fork the operator must pick (recorded in standingDisagreements):
   - **Option A (fail-closed, recommended):** if `ARCLINK_TRUSTED_PROXY_CIDRS` is
     unset, NO peer is a trusted proxy — every request is evaluated on its direct
     `remote_addr` against the client allowlist, and ALL forwarded headers are
     ignored. This is the strictest, most symphony-aligned ("fails closed")
     default. Risk: an existing deploy that today relies on the bridge range in
     `ARCLINK_BACKEND_ALLOWED_CIDRS` to trust the proxy will, after upgrade, stop
     trusting XFF and may 403 legitimate browser admin traffic until the operator
     sets `ARCLINK_TRUSTED_PROXY_CIDRS`. Mitigation: deploy rendering writes the
     bridge range into the new var automatically on `reconfigure`/`upgrade`, so
     canonical lanes self-heal; only hand-rolled deploys need manual action.
   - **Option B (one-release migration shim):** if `ARCLINK_TRUSTED_PROXY_CIDRS`
     is unset, fall back to treating `ARCLINK_BACKEND_ALLOWED_CIDRS` as the proxy
     set for ONE release, emit a loud config-health "deprecated overload"
     warning, and require explicit `ARCLINK_TRUSTED_PROXY_CIDRS` next release.
     Lower upgrade risk, but keeps the footgun alive for a release.
   My recommendation: **Option A**, because the canonical lanes can render the
   split automatically (the operator owns the host/policy and deploy.sh already
   owns CIDR rendering at `:8488`), making the fail-closed default safe for the
   blessed path while leaving only hand-rolled deploys to adjust — which is the
   correct place for the friction. But A vs B is genuinely the operator's call
   because it trades upgrade smoothness against one more release of a known
   MEDIUM bypass.

### FINAL PLAN
1. `python/arclink_hosted_api.py`:
   - `HostedApiConfig.__init__` (near `:215`): add
     `self.trusted_proxy_cidrs = str(e.get("ARCLINK_TRUSTED_PROXY_CIDRS","")).strip()`.
   - Add `_trusted_proxy_peer(config, ip) -> bool`: `is_loopback_ip(ip) or
     is_ip_in_cidrs(ip, config.trusted_proxy_cidrs)`.
   - Rewrite `_remote_ip_from_headers`: `direct = remote_addr.strip()`; if not
     `direct` → `""`; if `_trusted_proxy_peer(config, direct)`: parse first XFF IP,
     return it if present/parseable, else return `""` (no client → CIDR gate 403);
     else (untrusted peer) ignore forwarded headers and return `direct`.
   - Keep `_backend_client_allowed` evaluating ONLY `backend_allowed_cidrs`
     (client allowlist). Loopback remains allowed as a *client* for the
     operator-on-host golden path.
   - Decision-2 default behavior follows the chosen fork (A recommended): when
     `trusted_proxy_cidrs` is empty, no peer (except loopback, if you keep
     loopback-as-trusted-proxy) is trusted to carry XFF.
2. Deploy/Compose rendering: `compose.yaml`, `bin/deploy.sh` (CIDR render block
   near `:8488`), `bin/docker-entrypoint.sh` — write `ARCLINK_TRUSTED_PROXY_CIDRS`
   (default the Docker bridge `172.16.0.0/12`) and re-scope
   `ARCLINK_BACKEND_ALLOWED_CIDRS` to the admin/operator client allowlist
   (loopback + operator admin CIDRs), so the two surfaces are rendered distinctly.
3. Web proxy: replace/prove `web/next.config.ts:7-12`. Either (a) move the
   API-proxy hop to a source-owned forwarder that sets a trustworthy
   `X-Forwarded-For: <real client>` toward the Python API, or (b) prove the Next
   standalone server forwards it and document/test that. Until proven, the admin
   path through the proxy must be treated as untrusted-XFF and rely on the
   operator reaching admin via loopback/SSH-tunnel, which is the
   operator-owns-host model anyway.
4. Tests (`tests/test_arclink_hosted_api.py`): split the seed config into two
   variables; add (a) trusted-proxy + no XFF → 403; (b) trusted-proxy + XFF
   allowed-client → 200; (c) trusted-proxy + XFF disallowed-client → 403; (d)
   untrusted direct peer with spoofed XFF → 403; (e) loopback direct admin client
   → 200; (f) the same matrix for `/auth/login` admin-enable. Update the existing
   `:5301-5322` assertions to the new contract.
5. Docs: `docs/API_REFERENCE.md` + env examples — document
   `ARCLINK_TRUSTED_PROXY_CIDRS` (proxy-trust surface) vs
   `ARCLINK_BACKEND_ALLOWED_CIDRS` (admin/client surface), with the surface
   declaration (operator/internal) per the API-contracts section.
6. Config-health/diagnostics: surface a check that flags overlap or
   misclassification between the two CIDR sets (a proxy CIDR that is also a client
   CIDR is suspicious), so the residual "operator misclassifies proxy CIDRs" risk
   is visible — matching `Secrets/Config` "detect ... incompatible values before
   services start."
7. Live-proof: gate real proxy-forwarding ingress behavior under **`PG-INGRESS`**
   (`docs/arclink/sovereign-control-node-symphony.md:283`).

### Symphony anchor (quoted)
- `API, Webhook, And Extension Contracts` (`docs/arclink/sovereign-control-node-symphony.md:1153`):
  "Whenever a new surface is added, it should declare whether it is Captain-facing,
  Operator-facing, Agent-facing, worker-facing, or internal-only. That declaration
  should decide auth, audit, redaction, rate limiting, docs, and tests." — proxy
  peer vs admin client are two surfaces; one CIDR variable cannot declare both.
- `Identity, Access, And Session Governance` (`:1022`): "Admin and Operator
  actions should never trust client-asserted privilege ... without server-side
  authorization." — came-through-proxy is not identity.
- North-star traversal (`:160-161`): a step must define "what state it reads,
  what state it writes, and how it fails closed." Missing XFF behind a declared
  proxy fails closed (no client → 403) with redacted 403 evidence.

### Effort + blast-radius
EFFORT: **med**. Blast radius: hosted API IP resolution + config (`python/arclink_hosted_api.py`),
Compose/deploy/entrypoint env rendering (`compose.yaml`, `bin/deploy.sh`,
`bin/docker-entrypoint.sh`), web proxy (`web/next.config.ts` and/or a new
forwarder), hosted-api + web transport tests, `docs/API_REFERENCE.md`. The
operator-on-host (loopback) golden path is explicitly preserved. Real ingress
forwarding behavior is `PG-INGRESS`-gated; local regression (the proxy/XFF matrix
above) is the in-repo proof. Residual: operator CIDR misclassification — made
visible via the config-health check (item 6).

================================================================================
## STANDING DISAGREEMENTS (genuine product forks the operator must pick)
================================================================================
- **Decision 2 — unset `ARCLINK_TRUSTED_PROXY_CIDRS` default:** Option A
  (fail-closed: unset → trust no proxy, ignore all XFF; canonical deploy lanes
  auto-render the bridge range so blessed paths self-heal, hand-rolled deploys
  must set it) — RECOMMENDED — vs Option B (one-release migration shim: unset →
  keep treating `ARCLINK_BACKEND_ALLOWED_CIDRS` as the proxy set with a loud
  deprecation warning, require the explicit var next release). Trades a smoother
  upgrade against one more release carrying the known MEDIUM proxy-without-XFF
  bypass. Adjudicator recommends A; the choice is the operator's because it is a
  policy/upgrade-smoothness tradeoff, not a code-correctness question.
