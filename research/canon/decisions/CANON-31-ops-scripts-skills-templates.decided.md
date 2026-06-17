# CANON-31 — Ops Scripts, Skills & Templates — DECIDED (Operator Calls)

**Adjudicator:** Claude Opus 4.8 (1M) — FINAL federation DECISION mode.
**Codex proposal:** `research/canon/decisions/CANON-31-ops-scripts-skills-templates.codex.md`
**Method:** Formed an independent view from the symphony + a fresh re-open of the code
(`rg`/`sed`), then converged with Codex. Every code cite below was re-verified in this pass.
**Net verdict:** 1 deferred decision — **AGREE-CODEX with one material REFINE** (wider, code-proven
blast radius + a sharper fail-closed proof obligation than Codex's cite list captured).

---

## DECISION 1 — Retire `ENABLE_TAILSCALE_SERVE` as the active shared-Nextcloud/internal-MCP contract

**[VERDICT: refine]** (right direction; agree with Codex's migration shape and the
deprecate-don't-delete instinct; refine the cite map, the consumer set, and the named proof gate.)

### The question (from NEEDS_DECISION.md, CANON-31)
> Whether to fully remove/rename `ENABLE_TAILSCALE_SERVE` and the related install prompts /
> agent tailnet URL assumptions. The repair campaign stopped the active teardown path, but a
> broader config-contract migration has wider blast radius.

### My independent reasoning (symphony first, then code)

The symphony is unambiguous about what the *truth* must be here:

- **Third-Party Integration Boundaries** — "Cloudflare and Tailscale own ingress primitives;
  ArcLink owns desired-state records, teardown evidence, proof gates, and **clear domain/Tailscale
  mode selection**." And: "Every integration must have three visible states: configured and
  locally valid, configured but live-proof pending, or missing and blocked with the next operator
  action." A flag that is *named* "enable serve" but whose serve script is a pure no-op
  (`tailscale-nextcloud-serve.sh:233-240`) gives the operator a fourth, illegal state:
  *configured-and-claimed-active-but-actually-retired*.
- **Hermes Dashboard And Plugins** — "Drive and Code now live behind the authenticated Hermes
  dashboard." The retired shared rails (raw Nextcloud + internal MCP over Tailscale Serve)
  contradict the post-repair design where Drive/Code belong behind the per-agent authenticated
  dashboard proxy. Captains "own their Pods and Crew, not the host" (**North Star**) — host-level
  shared-MCP/Nextcloud exposure is an operator/host rail, not a Captain rail.
- **Whole-System Traversal** — "every step should have a local source owner... and how it fails
  closed. ... Operator Raven, admin dashboard, CLI, diagnostics, live proof, and evidence rails
  show the **same system truth**." The retired flag breaks same-truth in the worst place: it is fed
  to the *agent* as authoritative.
- **Configuration, Schema, And Migration** — "Generated config includes enough version/release
  context to detect stale, missing, deprecated, or incompatible values before services start." and
  "Reconfigure is safe for changing ports, ingress mode, provider defaults... **without silently
  deleting runtime state**." This is exactly why a blind delete is wrong and a compatibility
  migration is right.

Now the code reality I re-verified (this is where I extend Codex):

1. **The active teardown the reconciled doc warned about is already gone.** `deploy.sh:5570-5571`
   and `5705-5713` no longer call `tailscale-nextcloud-serve.sh`; they call
   `warn_retired_tailscale_nextcloud_serve` (`deploy.sh:397-400`), which only warns and leaves
   config untouched. The serve script itself now early-exits unless the flag==1 and then just
   prints the retirement notice (`tailscale-nextcloud-serve.sh:219-220,233-240`) — it no longer
   un-serves on the install/upgrade path. So the reconciled-doc MEDIUM ("live enable-flag drives
   teardown") was true of the *pre-repair* tree; the residual issue is narrower and different:
   **false expected-rails handed to agents**, not destructive teardown.

2. **The real, live false-rail leak — the heart of this decision — is the agent-facing resource
   map, not the serve script.** With `ENABLE_TAILSCALE_SERVE=1`, `shared_tailnet_host()`
   (`arclink_resource_map.py:10-20`) returns the host, so `shared_resource_lines()`
   (`:46-48`) emits to the agent:
   `QMD MCP retrieval rail: https://{host}:{port}/mcp` and
   `ArcLink MCP control rail: https://{host}:{port}/arclink-mcp` — and `managed_resource_lines`
   labels these "the agent-facing source of truth even when a human-facing message summarizes them
   more narrowly" (`arclink_resource_map.py:120`). These tailnet HTTPS rails are **exactly the
   routes `tailscale-nextcloud-serve.sh` now refuses to publish.** Three Python consumers feed this
   from the retired flag: `arclink_onboarding_completion.py:206`, `arclink_onboarding_flow.py:918`,
   `arclink_control.py:17883`. This is the symphony's same-truth violation, live and pointed at the
   Agent. Codex's proposal correctly targets the deploy.sh URL synthesis but **did not cite these
   three Python `shared_tailnet_host` call sites** — they are the load-bearing leak and must be in
   the migration.

3. **deploy.sh false `expected` MCP/qmd rails — Codex's cite confirmed.** `deploy.sh:1578-1586`
   (qmd) and `1605-1613` (arclink-mcp) promote `AGENT_*_URL` to a tailnet URL with
   `ROUTE_STATUS="expected"` when `ENABLE_TAILSCALE_SERVE==1` even with no live serve. Confirmed
   verbatim. These are written into the agent install payload.

4. **The genuinely-real path that MUST survive: per-agent dashboard/Code Serve.**
   `agent_enable_tailscale_serve` (`arclink_control.py:460,525-528`) drives
   `publish_tailscale_https` for the per-agent **Hermes dashboard + Code plugin** URLs
   (`arclink_enrollment_provisioner.py:1137-1139`; `arclink_agent_access.py:552-554`). This is
   proven real by `tests/test_arclink_agent_access.py:185 (test_access_state_uses_tailscale_port_urls_when_enabled)`
   and `:225 (test_publish_tailscale_https_uses_dashboard_port_for_plugins)`. This is the
   authenticated-dashboard surface the symphony endorses (Hermes Dashboard And Plugins). It must
   NOT be collateral damage. Today it *defaults from* the retired shared flag
   (`arclink_control.py:527`; `common.sh:557`; `deploy.sh:2445`; `bootstrap-system.sh:16`), which is
   the coupling that has to be cut.

5. **Wider consumer set than Codex listed (all re-verified).** Beyond Codex's cites, the retired
   flag also drives: install of the Tailscale binary (`bootstrap-system.sh:179`), a health check
   branch (`health.sh:2298-2299` → `check_retired_tailscale_nextcloud_routes`, `:670-678`), a
   deploy summary "Tailnet HTTPS URL" line (`deploy.sh:3205-3214`), the install prompt copy
   (`deploy.sh:4787` "Enable Tailscale HTTPS proxy for Nextcloud", `:4805`, port prompt `:4809`),
   config emission (`deploy.sh:2445,2448`), `common.sh:464,557` defaulting, `docker-entrypoint.sh:614`
   (forced 0), and `ci-install-smoke.sh:31,98-99,752`. Plus the env example
   (`config/arclink.env.example:95,143-144`). The blast radius is **high**, as Codex said — but the
   reconciled risk is now MEDIUM-false-rail, not MEDIUM-teardown.

### Where I agree with Codex
- Deprecate-don't-delete via a compatibility migration. Correct, and it is what the symphony's
  "without silently deleting runtime state" / "detect... deprecated... values before services
  start" demands. A hard one-release delete would break existing per-agent dashboard URLs — agree.
- Split the flag: a **new explicit narrow flag** for the still-real per-agent dashboard Serve;
  make `ENABLE_TAILSCALE_SERVE` a deprecated, ignored legacy key for shared Nextcloud/internal MCP.
- Stop synthesizing qmd/control-MCP tailnet URLs from the retired flag/MagicDNS
  (`deploy.sh:1578-1586,1605-1613`); remove the legacy "HTTPS proxy for Nextcloud" / internal-MCP
  install prompts (`deploy.sh:4787,4809`); stop writing
  `ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE="$ENABLE_TAILSCALE_SERVE"` (`deploy.sh:2445`).
- Keep `ARCLINK_INGRESS_MODE=tailscale` + `ARCLINK_TAILSCALE_*` as the canonical Control-Node
  ingress contract; external Tailscale readiness stays under **`PG-INGRESS`**, never inferred from
  MagicDNS or a stale env var.
- One-release alias for the old *agent* flag only when the new flag is absent; do NOT keep
  `ENABLE_TAILSCALE_SERVE` as a living alias under a misleading name.
- Make `tailscale-nextcloud-serve.sh` a nonzero retired-command shim; keep `unserve.sh` as the
  explicit operator cleanup command.

### Where I REFINE Codex
1. **Add the three Python `shared_tailnet_host` call sites to the migration** — they are the actual
   live agent-facing false-rail leak (item 2 above) and Codex's cite list omitted them. The clean
   fix is at the seam: gate `shared_tailnet_host()` so the shared Nextcloud/internal-MCP rails are
   emitted **only** when there is a real owner+proof for shared serve (which, post-repair, there is
   not) — i.e. the retired flag must stop producing those two MCP rail lines. The three callers
   (`onboarding_completion.py:206`, `onboarding_flow.py:918`, `control.py:17883`) should pass
   `tailscale_serve_enabled=False` for the retired-shared path, so the agent gets the honest
   loopback rails (`shared_resource_lines` else-branch, `arclink_resource_map.py:50-52`) instead of
   unpublishable tailnet URLs. This is the single highest-value change in the whole decision.
2. **Name the live-proof gate explicitly and make the new agent-dashboard flag fail closed.** The
   symphony requires "configured but live-proof pending" as a *visible* state. The new
   per-agent-dashboard Serve flag must, when set without a verified tailnet, surface
   route-status `expected` (not `live`) and the publish must remain `PG-HERMES`-gated (per-agent
   dashboard live browser proof) — and any shared-MCP/Nextcloud serve remains **blocked** with no
   silent fallback (fails closed). Codex implied this; I am making it a hard acceptance criterion.
3. **Sharpen the same-truth proof obligation.** The new regression must not merely show "old config
   preserves agent-dashboard publication." It must positively assert that a config with the legacy
   `ENABLE_TAILSCALE_SERVE=1` and no new flag **(a)** still publishes the per-agent dashboard/Code
   URLs (alias honored once), **(b)** emits NO shared `QMD MCP retrieval rail`/`ArcLink MCP control
   rail` tailnet line and NO `AGENT_*_ROUTE_STATUS="expected"` tailnet MCP/qmd URL (the false rail
   is gone), and **(c)** logs the deprecation notice. This is the fail-closed evidence the symphony
   names.
4. **Fold in the smaller consumers Codex didn't enumerate** so they don't strand: `health.sh:2298`
   should drop the flag-gated branch (the retirement check is unconditional / keyed off the script
   shim, not the env var); `bootstrap-system.sh:179` should default Tailscale-binary install off the
   new agent flag + `ARCLINK_INGRESS_MODE=tailscale`, not the retired shared flag;
   `deploy.sh:3205-3214` summary line and the install prompts go away; `ci-install-smoke.sh` and the
   env example update to the new key with the legacy key marked deprecated/ignored.

### FINAL PLAN (converged, code-level)

Ship a one-release **compatibility migration**, not a delete:

1. **Introduce `ARCLINK_AGENT_DASHBOARD_TAILSCALE_SERVE_ENABLED`** as the explicit owner of the
   still-real per-agent Hermes-dashboard + Code-plugin Serve path. Wire `Config.from_env`
   (`arclink_control.py:525-528`) to read the new key; accept legacy
   `ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE` as a one-release alias **only when the new key is absent**;
   **do NOT** default either from `ENABLE_TAILSCALE_SERVE`. Update `common.sh:557`, `deploy.sh:2445`,
   `bootstrap-system.sh:16` to stop the `="$ENABLE_TAILSCALE_SERVE"` default.
2. **Demote `ENABLE_TAILSCALE_SERVE` to a deprecated, ignored legacy key** for shared
   Nextcloud/internal-MCP serve. On config load / `deploy.sh` preflight, if it is set to 1, emit a
   single deprecation line (reuse `warn_retired_tailscale_nextcloud_serve`, `deploy.sh:397-400`) and
   then treat it as 0 for all *shared-rail* decisions.
3. **Stop synthesizing shared tailnet rails from the retired flag:**
   - `deploy.sh:1578-1586` (qmd) and `1605-1613` (arclink-mcp): drop `ENABLE_TAILSCALE_SERVE` from
     the predicate; keep tailnet promotion only behind a real verified serve
     (`TAILSCALE_SERVE_HAS_QMD`/`_ARCLINK_MCP`==1), else stay `local`/`local_only`.
   - The three Python callers (`onboarding_completion.py:206`, `onboarding_flow.py:918`,
     `control.py:17883`): pass `tailscale_serve_enabled=False` for the retired shared path so
     `shared_tailnet_host()` returns "" and the agent gets honest loopback rails.
4. **Remove the legacy install prompts** ("Enable Tailscale HTTPS proxy for Nextcloud",
   `deploy.sh:4787`; port prompt `:4809`; the internal-MCP framing) and the deploy summary
   "Tailnet HTTPS URL" branch (`deploy.sh:3205-3214`). `health.sh:2298` branch becomes the
   unconditional retired-routes check (already keyed off the script shim at `:670-678`).
   `bootstrap-system.sh:179` defaults Tailscale-binary install off the new agent flag +
   `ARCLINK_INGRESS_MODE=tailscale`.
5. **Turn `tailscale-nextcloud-serve.sh` into a nonzero retired-command shim** (exit 2 + the
   retirement message); leave `tailscale-nextcloud-unserve.sh` as the explicit operator cleanup.
6. **Env example:** mark `ENABLE_TAILSCALE_SERVE` deprecated/ignored
   (`config/arclink.env.example:95`); replace the `ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE` "follow
   ENABLE_TAILSCALE_SERVE" note (`:143-144`) with the new explicit key and a "legacy alias for one
   release" note.
7. **Regression/dry-run proof (local source owner + named live gate, fails closed):**
   - Update `tests/test_deploy_regressions.py::test_emit_runtime_config_syncs_agent_tailscale_serve_with_global_flag`
     to the new contract (legacy alias once; no global-flag defaulting).
   - Add a deploy-regression that a config with only legacy `ENABLE_TAILSCALE_SERVE=1` produces
     **no** `expected` tailnet qmd/arclink-mcp `AGENT_*_URL` and emits the deprecation notice.
   - Add an `arclink_resource_map`/onboarding test that legacy-flag-on emits **no** shared tailnet
     `QMD MCP retrieval rail`/`ArcLink MCP control rail` line (only loopback rails).
   - Keep `tests/test_arclink_agent_access.py:185,225` green (per-agent dashboard Serve preserved
     under the new/alias flag).
   - **Named live gate:** external Tailscale serve readiness for the per-agent dashboard stays
     `PG-HERMES`/`PG-INGRESS`; nothing in this migration claims `live` without that proof —
     shared-MCP/Nextcloud serve remains blocked (fails closed).

### Symphony anchor (quoted)
> **Third-Party Integration Boundaries** — "Cloudflare and Tailscale own ingress primitives;
> ArcLink owns desired-state records, teardown evidence, proof gates, and clear domain/Tailscale
> mode selection." and "Every integration must have three visible states: configured and locally
> valid, configured but live-proof pending, or missing and blocked with the next operator action."
>
> **Configuration, Schema, And Migration** — "Generated config includes enough version/release
> context to detect stale, missing, deprecated, or incompatible values before services start." and
> "Reconfigure is safe for changing ports, ingress mode, provider defaults... without silently
> deleting runtime state."
>
> **North Star** — "Captains own their Pods and Crew, not the host." and "Operator Raven, admin
> dashboard, CLI, diagnostics, live proof, and evidence rails show the same system truth."

### Effort / blast-radius
- **Effort: high.** Touches `Config.from_env` (`arclink_control.py`), `arclink_agent_access.py`,
  `arclink_enrollment_provisioner.py`, `arclink_resource_map.py` + its 3 Python callers,
  `bin/deploy.sh` (prompts, config emission, URL synthesis, summary), `bin/common.sh`,
  `bin/bootstrap-system.sh`, `bin/health.sh`, both legacy Tailscale scripts,
  `config/arclink.env.example`, `bin/ci-install-smoke.sh`, and the regression corpus
  (`test_deploy_regressions`, `test_arclink_agent_access`, onboarding/resource/completion tests).
- **Blast radius: high but de-risked by the alias.** The only behavior that *changes* for an
  existing operator who set `ENABLE_TAILSCALE_SERVE=1` is the (correct) disappearance of the
  unpublishable shared tailnet MCP/qmd rails from agent context; their per-agent dashboard Serve is
  preserved via the one-release alias. Fails closed: no path silently claims a live shared rail.

---

## STANDING DISAGREEMENTS (genuine operator product forks)

None that block this plan. One narrow operator product choice remains, recorded for completeness:

- **One-release alias window length.** The plan honors legacy `ARCLINK_AGENT_ENABLE_TAILSCALE_SERVE`
  (and, for the agent-dashboard path only, `ENABLE_TAILSCALE_SERVE`) as an alias for exactly one
  release, then drops it. The operator may instead choose a longer (two-release) deprecation window
  if the fleet has many pre-migration configs. This is a rollout-cadence call, not a design fork —
  the symphony's "detect deprecated values before services start" is satisfied either way.
