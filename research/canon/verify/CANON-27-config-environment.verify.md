# CANON-27 — Config & Environment — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing file
and re-derived each cited line; executed `bin/pins.sh` functions live. Code wins over
comments/docstrings/prior docs. Default verdict = refuted unless re-confirmed in code.

## HEADLINE
The record's CORE structural claims (pins.json is a real dual-consumer SoT; model-providers
overlays defaults; traefik mount is wired; the ALMANAC alias contract is vapor) hold up.
But the record's **headline MEDIUM risk is INVERTED** (it reads the precedence backwards),
its **`container_user` "both-ends-verified" claim is false** (never parsed from compose),
its **pepper citation is wrong**, its **academy-source-lanes "no code reads it / drift is
silent" claim is false** (a test golden-fixtures it field-by-field), and the record MISSED
two real defects: a **fail-open data-corruption path in `pins_set`** (no jq exit check before
`mv`) and a **broken documented `pins_get extras.0` example** (jq crashes). Net: the record is
PARTIALLY TRUSTWORTHY for structure but its risk register is mis-calibrated and several
"both-ends-verified" stamps are overstated.

---

## REFUTATIONS (claim → finding)

### R1 — MEDIUM risk "env-file ref can silently pin an OLDER Hermes commit than pins.json" — REFUTED (precedence inverted)
Record CODE-PATH TRACE step 3 (line 63): "env override wins (the `:-` default), else the pin."
Record RISK (line 106): `bin/common.sh:553` lets the env value win.

CODE: `bin/common.sh:553`
`ARCLINK_HERMES_AGENT_REF="$(__pins_get_or_default hermes-agent ref "${ARCLINK_HERMES_AGENT_REF:-ce0891...}")"`.
`__pins_get_or_default` (`bin/common.sh:542-552`): `value="$(pins_get "$1" "$2")"` (PIN), and
**only** `if [[ -z "$value" ]]; then value="$3"` (the env fallback). So `pins_get hermes-agent
ref` → `042c1d6...` (pins.json:11) WINS; the env var `3c231eb...` is merely positional arg `$3`,
used ONLY when jq is missing or pins.json is unreadable.
The `${ARCLINK_HERMES_AGENT_REF:-...}` selects WHICH fallback string is passed, not the result.
Corroborated by the template's own comment `arclink.env.example:118-119` ("Hermes upstream pin
**fallback for early bootstrap**. config/pins.json is the **source of truth** once the repo is
present.") and `bin/bootstrap-userland.sh:48-49,64-71` ("env vars still provide **fallback**
values"; qmd refuses to install if pin unreadable). The record read it backwards.
=> The MEDIUM risk is wrong in the happy path. Real residual exposure exists ONLY in the
degraded path (no jq / no pins.json), which is INFO-grade, not MEDIUM.

### R2 — "config/academy-source-lanes.example.json produces NOTHING at runtime / no code reads it; drift would be silent" — REFUTED
Record OUTPUT CONTRACT (line 42), CONTRACT #7 (line 81), RISK (line 113), self-check #2 (line 94).
CODE: `tests/test_arclink_academy_trainer.py:256` reads the file:
`example = json.loads((REPO / "config" / "academy-source-lanes.example.json").read_text(...))`
and `:268` asserts `set(example["lanes"]) == registry keys`, and `:287` asserts, **field-by-field**
for every lane (label, permission_policy, raw_storage_policy, deletion_policy, live_proof_boundary,
required_metadata, quality_weight, ...), `example_lane.get(field) == registry[lane].to_dict()[field]`.
=> The file is a DRIFT-GUARDED GOLDEN FIXTURE, not decorative. The record's "no code path reads
it" and "drift would be silent" are both false; the record's own self-check #2 claimed the grep
"covered .py" yet a `.py` test consumes it. The "documentation-only" / INFO-decorative label is wrong.

### R3 — CONTRACT #4: `container_user` "both-ends verified against parsed compose surface" — REFUTED (never parsed from compose)
Record CONTRACT #4 (line 78) lists the both-ends-verified structured block as including `container_user`.
CODE: `compose_docker_authority_surface()` (`tests/test_arclink_docker.py:413-419`) emits ONLY
`{docker_socket, explicit_root, linux_capabilities, compose_networks, block}`. `container_user` is
NOT derived from compose. The test only checks `boundary.get("container_user") == "root"` for
explicit-root services (`:1775`) and `== "arclink"` for write+non-root (`:1785`) — both are literal
constants, not compose-derived values. So `container_user` is an inventory self-claim that is never
cross-checked against the real compose user line for the general case.
=> "both-ends-verified for container_user" is overstated.

### R4 — Pepper citation `arclink_hosted_api.py:189-197` — REFUTED (wrong file)
Record TOUCH POINTS (line 49): `ARCLINK_SESSION_HASH_PEPPER[_REQUIRED]` "read by
`arclink_hosted_api.py:189-197`."
CODE: `grep SESSION_HASH_PEPPER python/` → ZERO hits in `arclink_hosted_api.py`. Real readers:
`arclink_api_auth.py:272,281` and `arclink_control.py:6703`. Lines 189-197 of hosted_api read
CORS/cookie vars only (verified `:189-192`). The pepper cite does not say what the record claims.
(CORS/cookie cites at :189-192 ARE correct; the pepper was incorrectly bundled in.)

### R5 — CONTRACT #1: "component keys in pins.json ... match MANAGED_COMPONENTS exactly" — REFUTED (subset, not equal)
Record CONTRACT #1 (line 75) and PIECE summary (lines 7-17) present pins.json as the 8 managed
components and claim they "match MANAGED_COMPONENTS exactly."
CODE: `config/pins.json` has **13** components (adds `python`, `uv`, `tailscale`, `quarto` —
`pins.json:45,78,84,91`). `MANAGED_COMPONENTS` (`arclink_pin_upgrade_check.py:58-67`) is the 8.
The detector loops `for name in MANAGED_COMPONENTS` (`:675`) — a SUBSET read. The relation is
MANAGED_COMPONENTS ⊂ pins.json components, NOT equality. The contract is still satisfiable (the 8
are present), but the record's "match exactly" is false and the PIECE summary never discloses the
extra 4 components.

### R6 — "arclink.env.example:103-105 has the same tautological wording" — REFUTED (only env.example:4 is tautological)
Record DRIFT (line 85).
CODE: `arclink.env.example:103-105` reads "ARCLINK_* values take precedence over **legacy aliases**
when non-empty" — generic "legacy aliases", NOT "legacy ARCLINK_* aliases". It is NOT tautological.
Only `env.example:4` ("legacy **ARCLINK_*** aliases") is the copy/paste tautology. The record
conflated the two templates.

---

## CONFIRMATIONS (independently re-verified — record was correct)

- C1 — ALMANAC alias contract is VAPOR. `ARCLINK_ENV_ALIASES: dict = {}` (`arclink_product.py:12`);
  `grep -rln ALMANAC` over .py/.sh/.yaml/.json/.ts (excl. canon docs) = ZERO; no call site passes a
  non-empty `legacy_key=` (only internal refs in arclink_product.py:61,65,66). `resolve_env`
  (`:42-66`) is real but never fed an alias. CONFIRMED; resolves OPEN-FOR-CODEX #1.
- C2 — `model-providers.yaml version:1` is decorative. `load_model_providers` reads only
  `data.get("providers")` (`arclink_model_providers.py:62`), merges via `base.update(value)` (`:70`).
  Wrong version silently ignored. CONFIRMED.
- C3 — Inventory "writeable Docker socket" prose drift (DISSECT M5) is REAL. operator-upgrade-broker
  prose at `docker-authority-inventory.json:205,2269,2306,2419` says "writeable Docker socket" while
  structured `docker_socket:"none"` (`:2229`); drift test only checks prose for `docker_socket=="write"`
  (`tests/test_arclink_docker.py:1776`), so the no-socket prose is unguarded. CONFIRMED LOW.
- C4 — Inventory egress prose drift is REAL. `:316` claims operator-upgrade-broker "receive[s]
  single-service outbound egress networks"; structured `egress_networks:[]` (`:2245`); the egress
  test (`tests/test_arclink_docker.py:851-853`) only validates `agent-process-helper-egress-net`,
  NOT operator-upgrade-broker. CONFIRMED LOW.
- C5 — `pins_set*` are lock-free (no flock) — `bin/pins.sh:79-85,90-99`. CONFIRMED (but see G1/G2).
- C6 — `.env.live.example` is UNTRACKED — `git ls-files .env.live.example` empty; file on disk
  `-rw------- 957 bytes`. CONFIRMED INFO.
- C7 — traefik wiring: flag `--providers.file.filename=...` at `compose.yaml:621`; mount
  `./config/traefik-control.yaml:...:ro` present in traefik volumes; all 4 upstream services
  (`notion-webhook:537`, `control-api:546`, `control-llm-router:566`, `control-web:602`) ARE defined
  compose services with ports 8283/8900/8090/3000 matching `traefik-control.yaml:31,35,39,43`. The
  record's self-check #3 was an UNDER-claim — the upstreams DO exist. Routers/priorities 200/180/150/1
  match (`traefik-control.yaml:7,13,19,25`). CONFIRMED (stronger than recorded).
- C8 — CONTRACT #6 team-resources: clone script parses `IFS='|' read -r SLUG URL BRANCH NOTE_TEXT`
  (`clone-team-resources.sh:54`), comment skip `:64`. 4 fields, `|` delimiter match example. CONFIRMED.
- C9 — `pins_validate` omits `release-asset` (and others). jq array has 7 kind-checks
  (`bin/pins.sh:130-136`); schema enumerates 8 with `release-asset`→`repo` required
  (`pins.schema.json:110-111`). CONFIRMED, but see note in N1 (calibration).

---

## NEW GAPS (neither record nor prior docs flagged)

### G1 — HIGH-adjacent / MEDIUM: `pins_set`/`pins_set_raw` are FAIL-OPEN — no jq exit check before `mv` → pins.json corruption
`bin/pins.sh:81-85` (and `:95-99`): `jq ... "$ARCLINK_PINS_FILE" > "$tmp"` then `mv "$tmp"
"$ARCLINK_PINS_FILE"` with NO check of jq's exit status. If jq fails (malformed pins.json, bad
expression, disk-full mid-write), `$tmp` is empty/truncated and the unconditional `mv` CLOBBERS the
real pins.json with broken/empty content. pins.sh has no `set -e`; even a caller's `set -e` cannot
help because the failing step is jq writing to a redirect, and the subsequent `mv` of the bad temp
file SUCCEEDS. This destroys the single source of truth for every dependency pin. The record only
flagged the missing LOCK, not this corruption path.

### G2 — LOW/MEDIUM: `mktemp` without `-p` breaks the "atomic mv" claim across filesystems
`bin/pins.sh:80,94` use bare `mktemp` → temp file in `$TMPDIR` (default /tmp), typically a DIFFERENT
filesystem from the repo `config/`. `mv` across filesystems is copy+unlink, NOT atomic; a crash mid-mv
leaves a partial pins.json. The record asserts `mktemp`+`mv` is "atomic per-write" (record lines
25,36,57,97) — false when TMPDIR != config/ filesystem. Fix: `mktemp -p "$(dirname "$ARCLINK_PINS_FILE")"`.

### G3 — LOW: documented `pins_get <c> extras.0` example is BROKEN (jq crash, rc=5)
Live test: `pins_get hermes-agent extras.0` →
`jq: error: Cannot index array with string "0"` rc=5. Cause: `pins_get` does
`($p|split(".")) as $parts | getpath($parts)` (`bin/pins.sh:46-47`); `split(".")` yields string
parts `["extras","0"]`, but jq `getpath` needs integer index 0 to enter an array. The DOCSTRING's
own advertised example `pins_get hermes-agent extras.0` (`bin/pins.sh:39`) does not work, and the
function does NOT return "" for array-index paths (it errors to stderr, rc=5). The record's INPUT
CONTRACT (line 23) repeats the docstring's claim without testing it. (`pins_get hermes-agent extras`
DOES work, returning the whole array as compact JSON, confirming the object/array re-emit claim — it
is specifically INDEX access that breaks.)

### G4 — INFO: `.tsv` extension is a misnomer — file is PIPE-separated
`config/team-resources.example.tsv` uses `|` not TAB (`team-resources.example.tsv:1,5-7`); consumer
splits on `IFS='|'` (`clone-team-resources.sh:54`). Harmless but the name lies. Record didn't flag.

### G5 — INFO: drift test never cross-checks 7 structured inventory fields against compose
Beyond `container_user` (R3): `egress_networks`, `internal_request_networks`, `private_state_mounts`,
`host_repo_bind_includes_private_state`, `global_container_secrets_mount`, `inherits_broad_app_env`,
`child_process_env_allowlist` are NOT derived in `compose_docker_authority_surface`
(`tests/test_arclink_docker.py:413-419`). Per-service tests (e.g. `:1685-1688`) assert these against
HARDCODED expected booleans, not against parsed compose — so a compose change can diverge from the
inventory's claimed values silently as long as the inventory keeps the hardcoded value the test wants.
The record's CONTRACT #4 "both-ends verified YES for the structured block" overstates coverage to all
structured fields; in reality only 5 fields (socket, root, caps, networks, default-network) are
compose-cross-checked.

---

## SEAM MISMATCHES
- CANON-02 (config → hosted-api session): record's pepper producer→consumer cite points at the wrong
  file; pepper crosses into `arclink_api_auth.py:272,281` / `arclink_control.py:6703`, not
  `arclink_hosted_api.py:189-197`. Seam shape (env name) is right; the cited consumer is wrong.
- CANON-12/25 (inventory → drift test): only 5 of 12+ `compose_boundary` keys are actually a
  both-ends seam; the rest are one-ended inventory assertions (G5).
- CANON-17 (academy lanes): the example file IS a seam (test golden fixture), contradicting the
  record's "no producer/consumer" stamp (R2).

## SEVERITY RE-CALIBRATION
- Record MEDIUM "env-ref override" → DOWNGRADE to INFO (R1: pins.json wins in happy path).
- Record INFO "academy-source-lanes decorative/silent-drift" → UPGRADE/RECLASSIFY: it is test-guarded;
  the real (LOW) risk is the inverse — the example must be kept in sync or CI fails (R2).
- NEW G1 (pins.json corruption on jq failure) is the most under-rated issue: MEDIUM, fail-open.

## VERDICT
**PARTIALLY TRUSTWORTHY — do not adopt the risk register as written.** The record's structural
spine (schema-backed pins SoT, provider overlay, traefik mount, ALMANAC-vapor, M5/egress prose drift)
is correct and several confirmations are even stronger than recorded (C7). But the record (1) inverts
the precedence of its own headline MEDIUM risk (R1), (2) mislabels a drift-guarded test fixture as
decorative (R2), (3) overstates `container_user`/structured both-ends coverage (R3, G5), (4) cites the
wrong file for the pepper (R4), (5) misstates pins.json↔MANAGED_COMPONENTS as equality (R5), and
(6) MISSES a fail-open pins.json corruption path (G1) and a broken documented example (G3). Fix the
risk register and the four bad citations before treating CANON-27 as canon.
