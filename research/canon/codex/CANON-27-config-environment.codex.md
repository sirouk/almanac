<<<CODEX-VERDICT-START CANON-27>>>
## CANON-27 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(5)
ONE-LINE VERDICT: Core CANON-27 spine stands, but the original record needed the verifier’s corrections plus two additional config-path refinements.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- REFUTE §3/§5C env-ref MEDIUM: `pins.json` wins in the normal path. `__pins_get_or_default` calls `pins_get` first and uses the env value only when the pin read is empty; I executed `source bin/common.sh` with stale `ARCLINK_HERMES_AGENT_REF=3c231...` and got `042c1d6...`. Code path: `bin/common.sh:545-553`, `bin/pins.sh:40-49`, `config/pins.json:11`, stale fallback at `config/arclink.env.example:118-120`. Severity: INFO degraded-path fallback, not MEDIUM.
- CONFIRM §3 MEDIUM `pins_set` fail-open: `jq > "$tmp"` is followed by unconditional `mv "$tmp" "$ARCLINK_PINS_FILE"` with no exit check; same bug in raw setter. `bin/pins.sh:80-85`, `bin/pins.sh:94-99`.
- REFINE pins seam: `pins.json` has 12 components, not 13; upgrade detector manages 8 of them, so the relation is subset, not equality. `config/pins.json:7-97`, `python/arclink_pin_upgrade_check.py:58-67`, `python/arclink_pin_upgrade_check.py:675-681`.
- CONFIRM pins consumers: Dockerfile, common.sh, bootstrap, and component-upgrade read pin values. `Dockerfile:74-86`, `bin/common.sh:541-553`, `bin/bootstrap-userland.sh:48-73`, `bin/component-upgrade.sh:181-197`.
- CONFIRM model-provider seam: YAML overlays defaults and `version:` is ignored; Bash fails soft to fallback. `config/model-providers.yaml:1-43`, `python/arclink_model_providers.py:60-72`, `bin/model-providers.sh:30-47`, `bin/init.sh:12-15`.
- REFINE docker-authority seam: compose-cross-checked fields are only socket/root/caps/networks/default-network; `container_user` is asserted as a literal, not parsed from compose. `tests/test_arclink_docker.py:413-419`, `tests/test_arclink_docker.py:1754-1788`.
- CONFIRM stale inventory prose LOW: prose still says writable Docker socket / egress for operator-upgrade-broker, while structured + compose say no socket and only internal broker net. `config/docker-authority-inventory.json:205`, `config/docker-authority-inventory.json:316`, `config/docker-authority-inventory.json:2228-2247`, `compose.yaml:842-872`, `compose.yaml:1173-1174`.
- CONFIRM traefik seam stronger than record: dynamic file is mounted and all 4 upstream services/ports exist. `config/traefik-control.yaml:3-43`, `compose.yaml:537-611`, `compose.yaml:621-632`.
- CONFIRM team-resources seam: file is pipe-delimited despite `.tsv`; consumer splits on `|`. `config/team-resources.example.tsv:1-7`, `bin/clone-team-resources.sh:24-25`, `bin/clone-team-resources.sh:54-64`.
- REFINE academy lanes: no runtime reader found, but the example is not decorative/silent; a test loads it and field-compares it to the hardcoded registry. `tests/test_arclink_academy_trainer.py:253-291`, `python/arclink_academy_trainer.py:537-640`, `python/arclink_academy_programs.py:3067-3080`.
- CONFIRM ALMANAC alias vapor: alias map is empty and product accessors pass no legacy key; tests exercise `ARC_BASE_DOMAIN`, not ALMANAC. `python/arclink_product.py:12`, `python/arclink_product.py:42-66`, `python/arclink_product.py:79-104`.
- CONFIRM LOW `pins_validate` gap: Bash validator omits `release-asset`; schema includes it. `bin/pins.sh:126-137`, `config/pins.schema.json:80-112`.
- CONFIRM LOW `pins_get extras.0` broken: doc advertises it, implementation feeds string `"0"` to `getpath`; executed `pins_get hermes-agent extras.0` returned jq rc=5. `bin/pins.sh:34-49`.

### New findings both Claude passes missed (severity + path:line)
- LOW: Nextcloud/Postgres/Redis image pins are pins-as-default, not hard source of truth; existing `ARCLINK_*_IMAGE/TAG` env overrides the pin before compose interpolation. `bin/common.sh:1557-1582`, `compose.yaml:261`, `compose.yaml:272`, `compose.yaml:281`.
- LOW: Hosted API config-file merge does not feed session pepper enforcement in `arclink_api_auth`; direct/non-compose invocation can load config into `HostedApiConfig.env` while auth still reads only `os.environ`. Docker happy path sets these env vars directly. `python/arclink_hosted_api.py:295-329`, `python/arclink_api_auth.py:271-282`, `compose.yaml:75-78`.

### Claude citations re-confirmed or corrected
- Corrected pepper consumer: not `arclink_hosted_api.py:189-197`; real session pepper reader is `python/arclink_api_auth.py:271-282`, with LLM-router hash fallback at `python/arclink_control.py:6700-6704`.
- Corrected tautology claim: `config/env.example:4` is tautological; `config/arclink.env.example:103-105` says generic legacy aliases, not “legacy ARCLINK_*”.
- Corrected component count: 12 current pin components, 8 managed detector components. `config/pins.json:7-97`, `python/arclink_pin_upgrade_check.py:58-67`.
- Reconfirmed `.env.live.example` is ignored/untracked and contains only blank secret template values. `.gitignore:8`, `.env.live.example:1-3`, `.env.live.example:5-49`.
- Reconfirmed model-provider `version` is decorative. `config/model-providers.yaml:1`, `python/arclink_model_providers.py:60-72`.

### Residual disagreement with the Claude half (for final reconciliation)
- I side with the verifier on env-ref severity: INFO fallback risk, not MEDIUM override.
- I side with the verifier that `pins_set` fail-open is the highest CANON-27 risk.
- I refine the verifier: `pins.json` component count is 12, not 13.
- I add the compose image env-override and hosted-api/auth env split as LOW reconciliation items.
<<<CODEX-VERDICT-END CANON-27>>>
