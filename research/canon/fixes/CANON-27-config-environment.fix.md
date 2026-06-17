<<<CODEX-FIX-START CANON-27>>>
## CANON-27 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: .gitignore, .env.live.example, bin/common.sh, bin/pins.sh, config/arclink.env.example, config/env.example, python/arclink_api_auth.py, python/arclink_model_providers.py, tests/test_arclink_api_auth.py, tests/test_arclink_pins.py, tests/test_arclink_product_config.py, tests/test_model_providers.py
TESTS: 4 focused files run, all pass; bash syntax + py_compile pass; 1 additional hygiene file NEEDS-REVIEW for pre-existing CANON.md/tests provider-context failures

### Fixed (severity — what — path:line)
- MEDIUM — `pins_set`/`pins_set_raw` now fail closed on jq/mv failure, clean temp files, use same-directory temp files, and serialize writes with `flock` — `bin/pins.sh:54`, `bin/pins.sh:61`, `bin/pins.sh:74`, `bin/pins.sh:91`, `bin/pins.sh:131`
- LOW — documented `pins_get hermes-agent extras.0` now works by converting numeric dotted-path segments to jq array indexes — `bin/pins.sh:47`
- LOW — `pins_validate` now rejects malformed `release-asset` components missing `repo` — `bin/pins.sh:173`
- INFO — stale Hermes degraded-path fallback refs in `config/arclink.env.example` now match `config/pins.json` — `config/arclink.env.example:121`, `config/arclink.env.example:126`
- LOW — Nextcloud/Postgres/Redis image env values are now degraded-path fallbacks, not overrides over pins — `bin/common.sh:1608`
- LOW — hosted API/session-pepper config split fixed by reading pepper/base-domain/required through `config_env_value` — `python/arclink_api_auth.py:25`, `python/arclink_api_auth.py:271`
- INFO — `model-providers.yaml` `version` is no longer decorative; unsupported versions do not overlay defaults — `python/arclink_model_providers.py:64`
- LOW — env-template ALMANAC/legacy-alias claim corrected to match current code — `config/env.example:4`, `config/arclink.env.example:103`
- INFO — `.env.live.example` is no longer ignored, and its newly visible provider heading is hygiene-safe — `.gitignore:9`, `.env.live.example:25`

### Skipped (risk-accepted / standing / out-of-scope — why)
- GAP-019 trusted-host/root-equivalence residual language left intact; canon explicitly marks that class as risk-accepted/out-of-scope for this repair pass.
- Inventory stale operator-upgrade-broker socket/egress prose cited by CANON-27 was already absent in the current tree; no patch needed.

### NEEDS-DECISION (ambiguous; left for human)
- `config/team-resources.example.tsv` remains pipe-delimited despite `.tsv`; renaming is a public/operator contract change.
- Expanding docker-authority inventory tests to derive every structured field from Compose crosses CANON-12/25 boundaries and needs owner agreement.

### Cross-piece edits made (if any) + tests added
- Cross-piece: `python/arclink_api_auth.py` for config-file session pepper enforcement; `bin/common.sh` for shared pinned image env resolution; `.gitignore` for public template tracking.
- Tests added/updated: pins regressions for array paths, fail-closed writes, lock/temp contract, release-asset validation, Hermes fallback refs, image-pin precedence; model-provider version enforcement; API-auth config-file pepper; product/config `.env.live.example` unignore.
- Passing: `python3 tests/test_arclink_pins.py`, `python3 tests/test_model_providers.py`, `python3 tests/test_arclink_api_auth.py`, `python3 tests/test_arclink_product_config.py`, `bash -n bin/pins.sh bin/common.sh`, and py_compile.
- NEEDS-REVIEW: `python3 tests/test_public_repo_hygiene.py` still fails on existing `CANON.md` and `tests/test_arclink_evidence.py` provider-context entries; `.env.live.example` is no longer in that failure list.
<<<CODEX-FIX-END CANON-27>>>
