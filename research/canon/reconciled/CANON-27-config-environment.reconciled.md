# CANON-27 — Config & Environment — RECONCILED (both-model-signed)

Adjudicator: Claude Opus 4.8 (1M) final reconciliation over Claude record + Claude
adversarial verify + Codex (GPT-5.5 xhigh) verdict. Method: every disputed point
re-opened against live code (Read / rg / jq / git). Code wins over any comment, name,
or prior claim.

- Codex SIGN-OFF: OBJECT(5)
- Federation SIGN-OFF: **BOTH-MODEL-AGREED** (every material point reconciled to one code-grounded truth; no standing disagreements)

---

## RESOLUTION TABLE (disputed points — winner + deciding cite)

| Point | Winner | Deciding cite (re-opened) |
|---|---|---|
| Env-ref MEDIUM "env override silently pins OLDER Hermes commit" — precedence inverted | both (verifier+codex over record) | `bin/common.sh:545-552` `__pins_get_or_default` reads `pins_get` FIRST, uses `$3` env-fallback ONLY when pin empty; `bin/pins.sh:40-50`; `config/pins.json:11` `042c1d6...` wins. Record was backwards. → INFO. |
| academy-source-lanes "produces NOTHING / no code reads / drift silent" | both (verifier+codex over record) | `tests/test_arclink_academy_trainer.py:256` loads file; `:268` set-equal; `:287` field-by-field `example_lane==registry.to_dict()`. It is a drift-guarded golden fixture, not decorative. |
| CONTRACT #4 `container_user` "both-ends-verified from parsed compose" | both (verifier+codex over record) | `tests/test_arclink_docker.py:413-419` emits only socket/root/caps/networks/block; `container_user` checked vs LITERALS `"root"`/`"arclink"` at `:1775,:1785`, never parsed from compose. Overstated. |
| Pepper cite `arclink_hosted_api.py:189-197` | both (verifier+codex over record) | `grep SESSION_HASH_PEPPER python/` → readers are `arclink_api_auth.py:272,281` + `arclink_control.py:6703`; ZERO in hosted_api. `:189-197` reads CORS/cookie only. Record's pepper cite wrong (CORS/cookie cite itself is correct). |
| pins.json↔MANAGED_COMPONENTS "match exactly" | codex (over record AND verifier on count) | `jq '.components\|keys\|length'` = **12** (not 13 as verifier said). `MANAGED_COMPONENTS` = 8 (`arclink_pin_upgrade_check.py:58-67`); loop is subset (`:675`). Relation is `MANAGED ⊂ pins`, not equality. Codex's 12 is correct; verifier's 13 is wrong. |
| Tautology "arclink.env.example:103-105 same as env.example:4" | both (verifier+codex over record) | `env.example:4` "legacy **ARCLINK_*** aliases" (tautology). `arclink.env.example:103-105` "legacy aliases" (generic, NOT tautological). Record conflated. |
| pins_set fail-open (no jq exit check before mv) | both (verifier G1 + codex CONFIRM) | `bin/pins.sh:81-85` `jq ... > "$tmp"` then unconditional `mv "$tmp" "$ARCLINK_PINS_FILE"`; same at `:94-99`. No exit check, no `set -e` rescue. SoT corruption path. → MEDIUM (highest CANON-27 risk). |
| pins_get extras.0 broken example | both (verifier G3 + codex CONFIRM) | `bin/pins.sh:46-47` `split(".")` → `["extras","0"]`; `getpath` cannot index array with string "0"; live rc=5. Docstring `:39` advertises it. → LOW. |
| ALMANAC alias contract is vapor | both (record + verifier C1 + codex) | `arclink_product.py:12` `ARCLINK_ENV_ALIASES={}`; `grep -rln ALMANAC` (excl. canon) = 0; no non-empty `legacy_key=` call site (`:42-66`). Resolves OPEN-FOR-CODEX #1. RATIFIED. |
| model-providers.yaml `version` decorative | both | `arclink_model_providers.py:62` reads only `data.get("providers")`, merge `:70`. RATIFIED. |
| Inventory "writeable Docker socket" prose drift (M5) | both | prose `config/docker-authority-inventory.json:205` vs structured `:2229 docker_socket:"none"`; drift test only checks prose when socket=="write" (`tests/test_arclink_docker.py:1776`). LOW. RATIFIED. |
| Inventory egress prose drift | both | prose `:316` "single-service outbound egress" vs structured `:2245 egress_networks:[]`; egress test (`tests/test_arclink_docker.py:851-853`) only validates `agent-process-helper-egress-net`. LOW. RATIFIED. |
| Traefik wiring stronger than recorded | both | mount/flag `compose.yaml:621,632`; 4 upstreams (notion-webhook/control-api/control-llm-router/control-web) defined with ports 8283/8900/8090/3000 matching `traefik-control.yaml:31,35,39,43`. RATIFIED (record self-check #3 under-claimed). |
| team-resources pipe-delimited despite .tsv | both | `team-resources.example.tsv:1-7` `\|`; `clone-team-resources.sh:54` `IFS='\|'`. RATIFIED. |
| pins_validate omits release-asset | both | `bin/pins.sh:130-136` (7 kind-checks, no release-asset); `pins.schema.json:110-111` requires repo. LOW. RATIFIED. |
| pins_set lock-free | both | `bin/pins.sh:79-85,90-99` no flock; concurrent last-writer-wins. LOW. RATIFIED (subsumed by the bigger fail-open G1). |
| .env.live.example untracked | both | `git ls-files .env.live.example` empty; ALSO git-ignored `git check-ignore` → `.gitignore:8 .env.*`. INFO. RATIFIED (Codex cite `.gitignore:8` is the more precise reason). |

## CONFIRMED Codex NEW FINDINGS (re-verified true in code → net-new federation risks)

| Finding | Sev | Deciding cite |
|---|---|---|
| Nextcloud/Postgres/Redis image pins are pins-as-DEFAULT, not hard SoT — existing `ARCLINK_*_IMAGE/TAG` env overrides the pin before compose interpolation | LOW | `bin/common.sh:1577-1582` `export ARCLINK_POSTGRES_IMAGE="${ARCLINK_POSTGRES_IMAGE:-$_postgres_image}"` (env wins); `compose.yaml:261,272,281` interpolate `${ARCLINK_POSTGRES_IMAGE:-...}`. CONFIRMED. |
| Hosted-API config-file merge does NOT feed session-pepper enforcement — config loaded into `HostedApiConfig.env`, but auth reads only `os.environ` | LOW | `arclink_hosted_api.py:295-329` merges config into `.env`; `arclink_api_auth.py:271-282` `_session_hash_pepper` reads `os.environ` only. Direct/non-compose invocation can split; Docker happy path sets env directly. CONFIRMED. |

## CONFIRMED verifier NEW GAPS (also net-new federation risks)

| Gap | Sev | Deciding cite |
|---|---|---|
| G1 pins_set fail-open corruption (see table) | MEDIUM | `bin/pins.sh:81-85,94-99` |
| G2 bare `mktemp` (no `-p`) → cross-filesystem `mv` is copy+unlink, NOT atomic; "atomic mv" claim false when TMPDIR≠config/ fs | LOW | `bin/pins.sh:80,94` bare `mktemp`; `mv` `:85,:99`. CONFIRMED (mitigates to LOW: real corruption window only on crash mid-copy). |
| G3 pins_get extras.0 broken (see table) | LOW | `bin/pins.sh:46-47` |
| G4 .tsv is pipe-separated (name misnomer) | INFO | `team-resources.example.tsv:1-7`; `clone-team-resources.sh:54` |
| G5 only 5 of 12+ compose_boundary keys are compose-cross-checked; rest asserted vs hardcoded booleans | INFO/LOW | `tests/test_arclink_docker.py:413-419` (only socket/root/caps/networks derived); per-service hardcoded asserts. CONFIRMED — record's "both-ends YES for the structured block" overstates to all fields. |

## REJECTED findings

(None. Every Codex new finding and every confirmed verifier gap held in code. The only
factual error among the inputs was the VERIFIER's "13 components" claim — corrected to 12
by `jq` and adopted from Codex; that is a within-input correction, not a rejected finding.)

## SEVERITY CHANGES (code-supported only)

| Risk | From | To | Cite |
|---|---|---|---|
| Env-file ref override pins older Hermes commit | MEDIUM | INFO | `bin/common.sh:545-552` (pin wins; env only on degraded jq/pins-missing path) |
| pins_set fail-open pins.json corruption | (unrecorded) | MEDIUM | `bin/pins.sh:81-85,94-99` — now the highest CANON-27 risk |
| academy-source-lanes "decorative / silent drift" | INFO (decorative) | LOW (test-guarded; must stay in sync or CI fails) | `tests/test_arclink_academy_trainer.py:256,268,287` |
| pins.json↔MANAGED_COMPONENTS "match exactly" (12 comps, subset of 8 managed) | (record: equality / verifier: 13) | corrected to 12, subset | `jq` length=12; `arclink_pin_upgrade_check.py:58-67` |

## STANDING DISAGREEMENTS

None. Every material point reconciled to a single code-grounded truth. Where the two
Claude passes and Codex initially differed (env-ref severity, academy fixture, container_user,
pepper cite, component count, tautology), the code settled each unambiguously and all three
end at the same verdict.

## FINAL BOTH-MODEL VERDICT

CANON-27's structural spine is sound and now stronger than the original record claimed:
`config/pins.json` is a real schema-backed dual-consumer (Bash + Python) pin SoT; the
12 components are a superset of the 8 the upgrade detector manages; `model-providers.yaml`
overlays hardcoded defaults (`version` decorative); `traefik-control.yaml` is correctly
mounted/selected with all 4 upstreams + ports verified in compose; the inventory's
*structured* compose_boundary is drift-guarded for 5 keys (socket/root/caps/networks/
default-network) — though NOT for `container_user` or the other ~7 fields; the
"ARCLINK_* over ALMANAC_*" alias contract is provably vapor (`ARCLINK_ENV_ALIASES={}`).

The original record's RISK REGISTER was mis-calibrated and is corrected here: its headline
MEDIUM (env-ref override) is INVERTED → INFO; its INFO "decorative academy fixture" is
actually a test-guarded LOW; four citations were wrong (pepper file, component-equality,
13-count, both-tautology). The real top risk — missed by the record, caught by the verifier,
confirmed by Codex — is the **fail-open `pins_set` corruption path (MEDIUM)**: jq writes to a
temp with no exit check before an unconditional `mv`, so any jq failure clobbers the pin SoT.
Net-new LOW federation risks: image-pin env override, hosted-api/auth pepper env split,
cross-fs non-atomic mktemp, and 7 inventory fields not cross-checked against compose.

Federation sign-off: **BOTH-MODEL-AGREED.**
