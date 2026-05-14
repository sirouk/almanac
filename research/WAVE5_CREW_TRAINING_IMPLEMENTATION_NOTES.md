# Wave 5 Crew Training Implementation Notes

## Rationale

- Centralized lifecycle logic in `python/arclink_crew_recipes.py` so API, bot,
  and dashboard surfaces share validation, fallback, unsafe-output rejection,
  archival, audit, and projection behavior.
- Reused the existing Chutes boundary for live generation eligibility instead
  of adding a new provider rail. If the boundary is unavailable, Crew Training
  falls back to a deterministic preset-only recipe and labels that mode.
- Reused the memory synthesizer unsafe-output patterns for URLs, shell command
  prompts, and instruction override text. Unsafe provider output is retried up
  to two times before deterministic fallback.
- Applied persona changes only through the existing managed-context identity
  projection file. Crew Training does not rewrite memory/session files and does
  not restart Hermes gateways.

## Live Gates Skipped

No live Chutes inference, public bot command registration, payment flow,
production deploy, Docker install/upgrade, or service restart was run for this
build slice.
