# CANON-27 — Config & Environment

## PIECE
CANON-27 owns ArcLink's **static configuration surface** and the **environment-variable contract** that the whole control plane reads at boot/deploy time. It contains no long-running process of its own; it is the set of declarative files (env templates, YAML/JSON pins, provider catalogs, the Docker trust-boundary inventory, Traefik dynamic routing) plus two thin Bash readers that other pieces source.

Files owned (all tracked except one, see note):
- `config/arclink.env.example` (149 lines) — the full legacy/deploy env template (paths, QMD, MCP, bootstrap throttles, backup git, Nextcloud, model presets, Hermes pins fallback, SSOT/Notion).
- `config/env.example` (71 lines) — the SaaS-facing env template (product identity, Chutes, hosted-API cookies/CORS/pepper, Stripe price IDs + cents, Cloudflare, Telegram/Discord).
- `config/model-providers.yaml` (43 lines) — provider preset catalog (chutes/opus/codex targets, default/recommended/legacy models) → CANON-16 seam.
- `config/pins.json` (99 lines) + `config/pins.schema.json` (116 lines) — the single dependency-pin source of truth → CANON-15/CANON-24 seam.
- `config/docker-authority-inventory.json` (2831 lines) — the GAP-019 trusted-host Docker socket/root authority inventory → CANON-12/CANON-25 seam.
- `config/traefik-control.yaml` (43 lines) — Traefik dynamic file-provider router/service map → CANON-25 seam.
- `config/academy-source-lanes.example.json` (155 lines) — DECORATIVE example of the Academy lane registry (not loaded by code) → CANON-17 documentation-only.
- `config/team-resources.example.tsv` (7 lines) — example `slug|git-url|branch|note` manifest for `clone-team-resources.sh` (CANON-31).
- `.env.live.example` (49 lines, repo-root) — **UNTRACKED** live-E2E secret template (`git ls-files .env.live.example` returns nothing).
- `bin/model-providers.sh` (61 lines) — Bash reader that shells into `arclink_model_providers.py`.
- `bin/pins.sh` (144 lines) — Bash reader/writer/validator over `config/pins.json` (jq-based).

Note on scope: `config/org-profile*` are tracked under `config/` but belong to **CANON-21**, not here. The env-var *precedence engine* (`resolve_env`) lives in `python/arclink_product.py` (CANON-03); this piece owns the **contract and the templates**, not that function's implementation, but I traced it to settle the ALMANAC claim (see DRIFT).

## INPUT CONTRACT (code-verified)
**bin/pins.sh** (sourced by callers; functions take positional args):
- `pins_get <component> <jq-dotted-path>` (`bin/pins.sh:40`): reads `ARCLINK_PINS_FILE` (default `<script>/../config/pins.json`, `:19`). Returns the value, or `""` if the component/path is missing (`:44-49`). Objects/arrays are re-emitted as compact JSON (`:48`). Requires `jq` and an existing file or returns 1 via `pins_require` (`:22-32`).
- `pins_kind`, `pins_resolve_inherited_ref` (`:54,:59`) — the latter follows `inherits_from` and returns the parent's `ref` (used by hermes-docs → hermes-agent).
- `pins_set <c> <path> <string>` (`:76`) / `pins_set_raw <c> <path> <jq-expr>` (`:90`) — atomic in-place rewrite via `mktemp`+`mv` (`:84-85,:98-99`). `pins_set` quotes via `--arg` (string only); raw uses `--argjson`.
- `pins_components`, `pins_show`, `pins_validate` (`:103,:109,:123`). `pins_validate` checks kind-required fields **for 7 of 8 kinds** — `release-asset` (quarto) is NOT validated (`:131-137`), nor is the npm `version!=null` enforced the same way the schema requires.

**bin/model-providers.sh** (sourced; functions take preset + fallbacks):
- `model_provider_target_or_default <preset> [fallback]` (`:51`), `model_provider_default_model_or_default` (`:55`), `model_provider_resolve_target_or_default <preset> <raw> [fallback]` (`:59`). Each shells `python3` with the repo dir resolved from `BOOTSTRAP_DIR` or the script location (`:4-12`), imports `arclink_model_providers`, and on ANY exception prints the fallback (`:44-47`) — **fail-soft to the literal default string**.

**config/pins.json** input shape is defined by `config/pins.schema.json`: top-level requires `version` (const `1`) + `components` (`pins.schema.json:7,10-13`); each component requires `kind` (one of 8 enum values, `:38-49`) + `description` (`:35,:50`); per-kind required fields enforced by `allOf`/`if/then` (`:80-113`).

**config/model-providers.yaml** input shape: `version: 1` + `providers:` map of preset→`{display_name,target,default_model,recommended_models,legacy_default_targets,legacy_default_models,description}` (`model-providers.yaml:1-43`). `version` is **declared but never read/validated** by `arclink_model_providers.py` (`load_model_providers` only reads `data.get("providers")`, `arclink_model_providers.py:62`).

## OUTPUT CONTRACT (code-verified)
- **bin/pins.sh** outputs to stdout (string values) and mutates `config/pins.json` in place via `pins_set*` (atomic `mv`, `:85,:99`). On missing jq/file: writes to stderr, returns 1 (`:24,:28`).
- **bin/model-providers.sh** outputs a single resolved string to stdout (`:47`), always a non-empty string when a fallback is supplied (fail-soft).
- **config/pins.json** is consumed (read) by `bin/component-upgrade.sh` (`pins_get`, `:185-197`), `bin/common.sh` `__pins_get_or_default` (`:542`, populates `ARCLINK_HERMES_AGENT_REF` `:553`, postgres image/tag `:1563-1564`, etc.), `bin/bootstrap-userland.sh` (`:51-52,:70-71`), and the Python detector `arclink_pin_upgrade_check.py` (`_read_pins`, `:99-100`).
- **config/model-providers.yaml** is read by `arclink_model_providers.py:load_model_providers` (`:60-72`) merged over hardcoded `DEFAULT_MODEL_PROVIDERS` (`:9-34`).
- **config/traefik-control.yaml** is mounted read-only into the traefik container at `/etc/traefik/dynamic/arclink-control.yaml` (`compose.yaml:632`) and selected via `--providers.file.filename=...` (`compose.yaml:621`). It declares 4 routers (notion/llm-router/api/web by PathPrefix priority 200/180/150/1) → 4 services pointing at `notion-webhook:8283`, `control-llm-router:8090`, `control-api:8900`, `control-web:3000` (`traefik-control.yaml:3-43`).
- **config/docker-authority-inventory.json** is the data input to test `test_docker_authority_inventory_matches_compose_boundary` (`tests/test_arclink_docker.py:1720-1788`), asserted equal to the real compose authority surface.
- **config/academy-source-lanes.example.json** produces NOTHING at runtime — no code path reads it (grep-verified: consumers of `source_lanes`/`source_lanes` are `arclink_academy_programs.py`/`arclink_academy_trainer.py` which use a **hardcoded** registry, not this file).
- **config/team-resources.example.tsv** is the template copied (by an operator) to `arclink-priv/config/team-resources.tsv`, then parsed line-by-line `IFS='|'` by `bin/clone-team-resources.sh:54`.

## TOUCH POINTS
**Env vars (templates → who reads):**
- Path/identity (`arclink.env.example:1-17`): `ARCLINK_NAME/USER/HOME/REPO_DIR/PRIV_DIR/...`, `ARCLINK_DB_PATH`, `STATE_DIR`, `VAULT_DIR` — read across bin/* and python (e.g. `ARCLINK_DB_PATH` is the SQLite path the control plane opens; CANON-01).
- Product/provider (`env.example:8-16`, `arclink.env.example:106-117`): `ARCLINK_PRODUCT_NAME/BASE_DOMAIN/PRIMARY_PROVIDER/CHUTES_BASE_URL/CHUTES_DEFAULT_MODEL/MODEL_REASONING_DEFAULT` — read by `arclink_product.py:80-104` via `env_value`. `ARCLINK_MODEL_PRESET_{CODEX,OPUS,CHUTES}` (`arclink.env.example:115-117`) — read by `bin/common.sh:516-518` and `bin/init.sh:13-19,569-572`.
- Hosted-API cookies/CORS/pepper (`env.example:20-25`): `ARCLINK_CORS_ORIGIN`, `ARCLINK_COOKIE_DOMAIN`, `ARCLINK_COOKIE_SECURE`, `ARCLINK_COOKIE_SAMESITE`, `ARCLINK_SESSION_HASH_PEPPER[_REQUIRED]` — read by `arclink_hosted_api.py:189-197` (CANON-02).
- Stripe price IDs / cents (`env.example:27-41`) — CANON-07.
- Pins overrides: `ARCLINK_PINS_FILE` (`pins.sh:19`), `ARCLINK_HERMES_AGENT_REF`/`ARCLINK_HERMES_DOCS_REF` (`arclink.env.example:120,125`, `bin/common.sh:553,564`), `ARCLINK_NVM_TAG/NODE_VERSION/QMD_PACKAGE/QMD_VERSION` (`bin/bootstrap-userland.sh:51-71`).
- Model-providers override: `ARCLINK_MODEL_PROVIDERS_FILE` (`arclink_model_providers.py:39`), `BOOTSTRAP_DIR` (`model-providers.sh:6`).
- Docker trust gate: `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` (inventory `:2254`, enforced in `arclink_boundary.py:require_docker_trusted_host_risk_accepted` per inventory `:2259`).
- Team resources: `ARCLINK_TEAM_RESOURCES_MANIFEST/DIR/VAULT_REPOS_DIR` (`clone-team-resources.sh:24-25`).
- `.env.live.example` secrets: `CLOUDFLARE_*`, `HETZNER_API_TOKEN`, `STRIPE_*`, `CHUTES_API_KEY`, `TELEGRAM_*`, `DISCORD_*`, `NOTION_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `SMTP_*` (`.env.live.example:6-49`) — live-E2E only.

**Files/paths:** `config/pins.json` (rw via pins.sh), `config/model-providers.yaml` (ro), `config/traefik-control.yaml` (ro mount), all `*.example.*` (templates, copied by operator). **Subprocess:** `model-providers.sh` spawns `python3` (`:17`); `pins.sh` spawns `jq` (`:43,:81,:95,etc`). **Locks/atomicity:** `pins_set*` uses `mktemp`+`mv` (non-atomic across concurrent writers — no flock). **Secrets:** templates ship BLANK secret values; `.env.live.example` header instructs `chmod 600` and "Do not commit real values" (`.env.live.example:2-3`).

## CODE-PATH TRACE
Pin → deploy boot (CANON-15/24 seam), end to end:
1. `bin/common.sh:541` sources `bin/pins.sh` (best-effort, `|| true`).
2. `bin/common.sh:542-551` defines `__pins_get_or_default <c> <field> <fallback>` calling `pins_get`.
3. `bin/common.sh:553` `ARCLINK_HERMES_AGENT_REF="$(__pins_get_or_default hermes-agent ref "${ARCLINK_HERMES_AGENT_REF:-ce0891...}")"` — env override wins (the `:-` default), else the pin.
4. `pins_get hermes-agent ref` (`pins.sh:40`) runs `jq` on `ARCLINK_PINS_FILE` → reads `config/pins.json:11` `"ref":"042c1d6bb0543c543ed1a81f009aab4569b0405d"`.
5. That ref propagates to the shared Hermes venv build (CANON-24 consumer). For docs, `pins_resolve_inherited_ref hermes-docs` (`pins.sh:59`) follows `inherits_from:"hermes-agent"` (`pins.json:30`) and returns the agent ref.

Model preset → init (CANON-16 seam):
1. `bin/init.sh:12` checks `declare -f model_provider_resolve_target_or_default` (defined when `model-providers.sh` was sourced, `bin/common.sh:514`).
2. `bin/init.sh:13` `ARCLINK_MODEL_PRESET_CODEX="$(model_provider_resolve_target_or_default codex "${ARCLINK_MODEL_PRESET_CODEX:-}" "openai-codex:gpt-5.5")"`.
3. `model-providers.sh:59` → `__model_provider_python resolve-target codex <raw> <fallback>` → `python3` → `arclink_model_providers.resolve_preset_target("codex", raw, repo_dir)` (`:103`).
4. `resolve_preset_target` loads `config/model-providers.yaml` merged over defaults (`:110`), normalizes legacy aliases (`openai:codex` → `openai-codex:gpt-5.5`, `:118-121`), returns the canonical target `openai-codex:gpt-5.5` (`model-providers.yaml:33`).
5. On any python failure, `model-providers.sh:44-47` prints the fallback `openai-codex:gpt-5.5` — same value, so the failure is invisible.

## CROSS-PIECE CONTRACTS (both ends verified)
1. **CANON-15 (pins → upgrade detector).** Contract: `config/pins.json` JSON with `components.<name>.{kind,ref,tag,version,...}`. Producer = this file. Consumer = `arclink_pin_upgrade_check.py:_read_pins` `json.loads(PINS_PATH.read_text())` (`:99-100`, `PINS_PATH=REPO_ROOT/config/pins.json` `:52`); it reads `kind` (`:103`) and field values (`:107`) for the 8 `MANAGED_COMPONENTS` (`:58-67`). BOTH-ENDS-VERIFIED: **YES** — component keys in pins.json (hermes-agent, hermes-docs, nvm, node, qmd, nextcloud, postgres, redis) match `MANAGED_COMPONENTS` exactly.
2. **CANON-15/24 (pins → Bash readers).** Contract: `pins_get/pins_resolve_inherited_ref` stdout strings. Producer `pins.sh:40,59`. Consumers `component-upgrade.sh:185-197`, `common.sh:553`, `bootstrap-userland.sh:51-71`. BOTH-ENDS-VERIFIED: **YES** — field names (repo/ref/branch/tag/image/package/version/extras) read by consumers all exist in `pins.json`.
3. **CANON-16 (model-providers → router/init).** Contract: preset→target string via `arclink_model_providers`. Producer `model-providers.yaml` + `arclink_model_providers.py:80-122`. Consumer `bin/init.sh:13-15` / `bin/common.sh:516-518`. BOTH-ENDS-VERIFIED: **YES** — presets `codex/opus/chutes` exist in both YAML (`model-providers.yaml:3,18,31`) and `DEFAULT_MODEL_PROVIDERS` (`arclink_model_providers.py:10,18,26`); YAML overlays defaults via `base.update(value)` (`:70`).
4. **CANON-12/25 (docker-authority-inventory → drift test).** Contract: `services[].compose_boundary.{docker_socket,explicit_root,container_user,linux_capabilities,compose_networks,default_network}` must equal the parsed compose surface. Producer `docker-authority-inventory.json:2228-2247`. Consumer `tests/test_arclink_docker.py:1754-1773`. BOTH-ENDS-VERIFIED: **YES for the structured block** (test parses real compose and asserts equality); **NO for prose fields** — `residual_policy_state`/`remaining_gate`/`gap_019_*` strings are never inspected when `docker_socket=="none"` (`:1776` only checks prose when socket=="write"). This is the DISSECT M5 drift.
5. **CANON-25 (traefik-control → traefik container).** Contract: Traefik dynamic file-provider schema (`http.routers`/`http.services`). Producer `traefik-control.yaml:1-43`. Consumer = traefik image via mount `compose.yaml:632` + flag `compose.yaml:621`. BOTH-ENDS-VERIFIED: **PARTIAL** — the mount/flag wiring is verified in compose, but Traefik itself parses the YAML at runtime (no ArcLink code validates it); service hostnames (`notion-webhook`, `control-llm-router`, `control-api`, `control-web`) are compose service names — I confirmed the names appear as upstreams but did not assert each service is defined in compose.yaml (left to CANON-25).
6. **CANON-31 (team-resources.tsv → clone script).** Contract: `slug|git-url|branch|note` pipe-delimited lines. Producer `team-resources.example.tsv:1,5-7`. Consumer `clone-team-resources.sh:54` `IFS='|' read -r SLUG URL BRANCH NOTE_TEXT`. BOTH-ENDS-VERIFIED: **YES** — 4 fields, `|` delimiter, `#`-comment skip (`:64`) match the example header comment.
7. **CANON-17 (academy-source-lanes example).** Contract: NONE — the example file is documentation. Authoritative registry is `arclink_academy_trainer.default_source_lane_registry()` (`:537-...`, hardcoded `SourceLanePolicy` objects). `_validate_source_lanes` (`arclink_academy_programs.py:3067`) validates lane ids against THAT registry's keys, not the JSON file. BOTH-ENDS-VERIFIED: **YES that the file is NOT a producer** — confirmed no code reads `academy-source-lanes`.

## CODE vs COMMENT/DOC/NAME DRIFT
- **The "ARCLINK_* over ALMANAC_* aliases" contract is unsubstantiated by code.** `grep -rln ALMANAC` over all `.py/.sh/.yaml/.json/.ts` source returns ZERO hits (only CANON docs mention it). `arclink_product.py:12` defines `ARCLINK_ENV_ALIASES: dict[str, str] = {}` — an **EMPTY** alias map. The precedence engine `resolve_env` (`arclink_product.py:42-66`) is real and general-purpose (ARCLINK key wins over a `legacy_key`, `:56-65`), but **no alias is ever registered**, so the famous "ALMANAC fallback" is a wired-but-unused mechanism with no live alias.
- **`env.example:4` self-contradicts:** "ARCLINK_* values take precedence over legacy **ARCLINK_*** aliases" — same prefix on both sides (a copy/paste rename leftover from the Almanac→ArcLink transform). `arclink.env.example:103-105` has the same tautological wording. CODE WINS: there are no aliases at all.
- **Inventory stale "writeable Docker socket" prose (DISSECT M5, re-confirmed):** `docker-authority-inventory.json:205,2269,2306,2419` describe the operator-upgrade-broker as having "writeable Docker socket" authority, contradicting the authoritative structured `docker_socket:"none"` (`:2229`) and the real compose (no socket mount). The drift test never inspects these strings for the no-socket case (`tests/test_arclink_docker.py:1776`). Runtime-harmless (machine field + compose are correct), prose-only.
- **Inventory egress-network prose false claim:** `:316` says operator-upgrade-broker "receive[s] single-service outbound egress networks", but structured `egress_networks:[]` (`:2245`) and the only network is `operator-upgrade-broker-net` which is `internal:true`. Prose-only drift.
- **`model-providers.yaml` `version: 1` is decorative** — never read (`arclink_model_providers.py` only reads `data["providers"]`, `:62`). A wrong version is silently ignored.
- **`pins.sh:pins_validate` is weaker than the schema:** it validates 7 kinds but omits `release-asset` and `uv-python`-minimum nuances (`pins.sh:131-137`), so a structurally-broken quarto/uv entry passes `pins_validate` but would fail `pins.schema.json` (`:108-112`).
- **`.env.live.example` is UNTRACKED** despite being a listed CANON-27 file — `git ls-files` returns nothing for it. It exists on disk only.

## ADVERSARIAL SELF-CHECK
1. *"No ALMANAC alias exists anywhere."* — Falsifiable if an alias is injected at runtime (e.g. a caller passes `legacy_key=` to `resolve_env` with an ALMANAC_* name). I grepped source for `legacy_key=` usages indirectly; I did NOT exhaustively trace every `resolve_env`/`env_value` call site for a hardcoded `legacy_key`. A non-empty `legacy_key=` argument somewhere would partially restore the contract.
2. *"academy-source-lanes.example.json is never read."* — Falsifiable if a bin/* script or doc-generator ingests it. My grep covered `.py/.sh`; a Makefile/CI step or a notebook could read it. Low risk but unproven-negative.
3. *"traefik-control.yaml service upstreams are valid."* — I verified the mount and the 4 upstream names but did NOT confirm each (`control-llm-router`, `control-api`, `control-web`, `notion-webhook`) is a defined compose service with those internal ports. Left to CANON-25; a renamed service would silently 404 at Traefik.
4. *"pins.json is the single source of truth."* — Falsifiable by the env fallbacks: `arclink.env.example:120` ships `ARCLINK_HERMES_AGENT_REF=3c231eb...` which DIFFERS from `pins.json:11` `042c1d6...`. The env override wins when set (`common.sh:553` `:-`), so a stale env file can silently pin an older ref than pins.json. I confirmed the values differ; I did not confirm whether any live deploy sets that env var.
5. *"`pins_set` is safe under concurrency."* — It uses `mktemp`+`mv` (`pins.sh:84-85`) which is atomic per-write but has NO lock; two concurrent `pins_set` calls can lose one update (last-writer-wins). I did not find a flock guard.

## OPEN FOR CODEX FEDERATION
- Confirm independently that NO `resolve_env`/`env_value` call site anywhere in `python/**` passes a `legacy_key=` of the form `ALMANAC_*` (or any non-empty legacy key), which would resurrect the alias contract the templates advertise. (`arclink_product.py:42-66`, `ARCLINK_ENV_ALIASES={}` `:12`.)
- Confirm the env-fallback ref drift: `arclink.env.example:120` (`3c231eb...`) vs `pins.json:11` (`042c1d6...`) and whether `bin/common.sh:553`'s `${ARCLINK_HERMES_AGENT_REF:-...}` could let a rendered env file override pins.json with an older Hermes commit in a real deploy.
- Cross-check whether the inventory prose drift (`:205,316,2269,2306,2419`) has any runtime consumer beyond the drift test, or is provably doc-only (DISSECT D1/D2 graded it LOW).
- Validate that `pins_validate` (`pins.sh:123-144`) missing `release-asset`/full schema coverage is acceptable vs the schema's `allOf` (`pins.schema.json:80-113`).

## RISKS (severity-ranked, code-cited)
- **MEDIUM** — Env-file ref override can silently pin an OLDER Hermes commit than pins.json: `arclink.env.example:120` (`3c231eb`) ≠ `pins.json:11` (`042c1d6`); `bin/common.sh:553` lets the env value win. A stale rendered `.env` defeats the "pins.json is source of truth" guarantee for `hermes-agent`/`hermes-docs`.
- **LOW** — Inventory stale "writeable Docker socket" prose contradicts structured `docker_socket:"none"`; not caught by drift test — `config/docker-authority-inventory.json:205,2269,2306,2419` vs `:2229`; `tests/test_arclink_docker.py:1776`.
- **LOW** — Inventory egress-network prose falsely claims operator-upgrade-broker gets an outbound egress net — `config/docker-authority-inventory.json:316` vs `:2245`.
- **LOW** — Misleading env-template comments claim an ALMANAC/legacy alias precedence that has zero implementation (`ARCLINK_ENV_ALIASES={}`) — `env.example:4`, `arclink.env.example:103-105` vs `python/arclink_product.py:12`.
- **LOW** — `pins_set*` has no lock; concurrent rewrites lose updates (last-writer-wins) — `bin/pins.sh:79-85,90-99`.
- **LOW** — `pins_validate` under-validates vs schema (no `release-asset`, partial kinds) so broken pins can pass the Bash gate — `bin/pins.sh:131-137` vs `config/pins.schema.json:108-112`.
- **INFO** — `.env.live.example` is untracked; not enforced/shipped by git — `git ls-files .env.live.example` (empty).
- **INFO** — `config/academy-source-lanes.example.json` and `model-providers.yaml:version` are decorative (no runtime reader) — drift between them and code would be silent.

## VERDICT
CANON-27 provably does its core job: `config/pins.json` is a real, schema-backed, dual-consumer (Bash + Python) source of truth for dependency pins, with both ends verified; `model-providers.yaml` correctly overlays the hardcoded provider defaults and feeds init/router via a fail-soft Bash→Python reader; `traefik-control.yaml` is correctly mounted/selected into Traefik; `docker-authority-inventory.json`'s **structured** boundary is drift-guarded by a real test against compose. The load-bearing strength is that the machine-readable contracts (pins schema, structured compose_boundary, provider presets) are all correct and test-anchored.

Real weaknesses: (1) the advertised "ARCLINK_* over ALMANAC_* aliases" contract is **vapor** — zero aliases registered, self-contradicting template comments, the alias dict is `{}`; (2) the env-file `ARCLINK_HERMES_AGENT_REF` fallback can silently override pins.json with an OLDER commit (MEDIUM); (3) the inventory carries stale "writeable Docker socket" prose the drift test doesn't catch; (4) `pins_set` is lock-free; (5) `academy-source-lanes.example.json`, `model-providers.yaml:version`, and `.env.live.example` are decorative/untracked. None of these break the happy path, but the ALMANAC-precedence and env-override-ref items are documentation/operational hazards worth closing.
