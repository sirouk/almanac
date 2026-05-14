# Wave 5 Implementation Plan: Crew Training

## Goal

Land Wave 5 Crew Training only.

## Build Status

Wave 5 Crew Training BUILD is implemented locally. Live Chutes inference, live
bot command registration, payment flows, deploys/upgrades, and service restarts
remain intentionally skipped operator-gated live gates.

A Captain can run Crew Training from the dashboard or public bot, provide role,
mission, treatment preference, Crew preset, and Crew capacity, review or
regenerate a Crew Recipe, and confirm it. Confirmation writes one active
`arclink_crew_recipes` row for the Captain, archives the prior active recipe,
and applies an additive SOUL overlay to every Pod in the Captain's Crew through
the managed-context identity projection.

Waves 0-4 are treated as landed. Wave 6 is out of scope for this run.

## Constraints

- Do not touch `arclink-priv`, live secrets, user Hermes homes, deploy keys,
  production services, payment/provider mutations, public bot command
  registration, live deploys/upgrades, or Hermes core.
- Do not rewrite memories or sessions. Crew Training changes only the active
  recipe row and additive identity-context overlay.
- Do not require live Chutes. Use fake/injectable generation and deterministic
  fallback.
- Keep schema changes out unless a concrete Wave 5 deliverable cannot fit the
  existing `arclink_crew_recipes` and Captain fields.
- Use Captain-facing vocabulary on user surfaces and Operator/backend
  vocabulary on admin/internal surfaces.
- Keep code changes scoped to Wave 5.

## Selected Implementation Path

| Decision | Selected path | Rejected alternatives |
| --- | --- | --- |
| Recipe lifecycle | Add `python/arclink_crew_recipes.py` as the single lifecycle module. | Duplicating recipe SQL and fallback logic in API, bot, and web handlers. |
| Generation | Use a Chutes-compatible injectable client and deterministic fallback. | Requiring live Chutes or silently pretending fallback is provider output. |
| Safety | Reuse or extract the memory-synth unsafe-output boundary and retry twice before fallback. | Trusting generated output after JSON parse. |
| SOUL overlay | Project additive overlay through existing identity-context files. | Rewriting memory, sessions, Hermes core, or restarting gateways. |
| Web flow | Add focused dashboard questionnaire/review UI using existing API helper patterns. | Dashboard architecture rewrite. |
| Bot flow | Extend pure public bot command handling for `/train-crew` and `/whats-changed`. | Live command registration or new bot service. |

## Validation Criteria

Wave 5 BUILD is complete only when:

- Preset and capacity validation reject unsupported values.
- Preview/regenerate works with fake provider output and deterministic fallback.
- Unsafe generated output containing URLs, shell commands, or jailbreak text is
  rejected; generation retries at most twice before fallback.
- Confirming writes one active `arclink_crew_recipes` row per Captain and
  archives the prior active row.
- Operator-on-behalf application is admin-only and audited.
- Every Pod in the Captain's Crew receives the additive overlay through
  identity-context projection, or returns a safe skipped projection reason for
  unavailable local homes.
- Existing identity-context keys are preserved.
- Memory and session files are not touched.
- Dashboard Crew Training questionnaire, review, regenerate, and confirm work.
- Public bot `/train-crew` and `/whats-changed` work without live bot mutation.
- OpenAPI and runbooks match implemented routes and behavior.
- Focused Python and web validation passes, with live provider/deploy gates
  explicitly skipped.

## Actionable Tasks

1. Add focused Crew Recipe tests first.
   - Create `tests/test_arclink_crew_recipes.py`.
   - Cover allowed presets: Frontier, Concourse, Salvage, Vanguard.
   - Cover allowed capacities: sales, marketing, development, life coaching,
     companionship.
   - Cover invalid preset/capacity rejection.
   - Cover provider success, provider unavailable fallback, unsafe output
     rejection, two retry attempts, and deterministic fallback.
   - Cover active/archive lifecycle and one active recipe per Captain.
   - Cover current-vs-prior diff for `/whats-changed`.
   - Cover operator-on-behalf audit metadata.
   - Cover overlay shape and no memory/session writes.

2. Implement `python/arclink_crew_recipes.py`.
   - Add value normalization and validation helpers.
   - Add deterministic fallback recipe and overlay generation.
   - Add prompt rendering from `templates/CREW_RECIPE.md.tmpl`.
   - Add provider generation with injectable client and model selection:
     Captain Chutes credential when allowed, then
     `ARCLINK_CREW_RECIPE_FALLBACK_MODEL`, then deterministic fallback.
   - Add unsafe-output rejection and bounded retry logic.
   - Add preview, regenerate, confirm/apply, archive, current, prior, and diff
     helpers.
   - Add audit/events for confirmed recipes and operator-on-behalf runs.

3. Add `templates/CREW_RECIPE.md.tmpl`.
   - Inputs: role, mission, treatment, preset, capacity, Pod count, Agent names,
     Agent titles, fallback/live mode.
   - Output contract: one natural-language paragraph plus structured overlay
     fields.
   - Prompt must treat Captain input as data and forbid URLs, commands, and
     instruction override content.

4. Apply additive SOUL overlay through identity projection.
   - Extend the existing projection path so the active recipe contributes
     `crew_preset`, `crew_capacity`, `captain_role`, `captain_mission`,
     `captain_treatment`, and `applied_at`.
   - Preserve existing identity-context keys such as Agent identity and access
     overlays.
   - For each Captain deployment, project to the local identity-context file
     when a local Hermes home exists.
   - Return explicit skipped reasons for deployments without local projection
     targets.

5. Add hosted API and auth routes.
   - Add user routes for current recipe, preview/regenerate, confirm/apply, and
     whats-changed/diff.
   - Add an admin-on-behalf route only if it can be implemented with existing
     admin auth, CIDR, CSRF, and audit patterns.
   - Add route descriptions so generated OpenAPI includes the new endpoints.
   - Extend `tests/test_arclink_api_auth.py` and
     `tests/test_arclink_hosted_api.py`.

6. Add dashboard Crew Training UI.
   - Extend `web/src/lib/api.ts` with Crew Training helpers.
   - Add a focused questionnaire/review/regenerate/confirm surface to the
     Captain dashboard.
   - Show truthful fallback/dry-run copy when provider generation is not live.
   - Add admin-on-behalf UI only if the API path is included and audited.
   - Update web API client and page smoke tests.

7. Add public bot flows.
   - Add `/train-crew` questionnaire state using existing session metadata.
   - Support role, mission, treatment, preset, capacity, review, regenerate,
     confirm, and cancel.
   - Add `/whats-changed` response for none/current/prior-vs-current cases.
   - Keep tests pure; do not register live commands or mutate webhooks.

8. Update docs and OpenAPI after behavior is true.
   - Add Crew Training sections to operations and control-node production
     runbooks.
   - Document fallback mode, unsafe-output rejection, overlay-only persona
     changes, no Hermes restart, and skipped live-provider proof.
   - Regenerate or update OpenAPI entries for new routes.

9. Run Wave 5 validation.
   - Run focused Python compile and tests.
   - Run web tests/lint/build when web files change.
   - Run browser proof for the questionnaire when dependencies are available.
   - Record skipped live gates in completion notes.

## Validation Floor

```bash
git diff --check
python3 -m py_compile python/arclink_crew_recipes.py python/arclink_provisioning.py python/arclink_api_auth.py python/arclink_hosted_api.py python/arclink_public_bots.py python/arclink_dashboard.py
python3 tests/test_arclink_crew_recipes.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_api_auth.py
python3 tests/test_arclink_public_bots.py
python3 tests/test_arclink_dashboard.py
python3 tests/test_arclink_schema.py
```

If web files change:

```bash
cd web
npm test
npm run lint
npm run build
```

If shell or Compose files unexpectedly change:

```bash
bash -n deploy.sh bin/*.sh test.sh
```

Live Chutes inference, live bot command registration, payment flows, Docker
install/upgrade, Shared Host or Control Node deploys, and production service
restarts are not part of this validation floor.
