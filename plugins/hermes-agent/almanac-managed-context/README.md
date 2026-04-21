# almanac-managed-context

Hermes plugin shipped by Almanac.

Purpose:
- read the locally applied Almanac managed-memory state from `HERMES_HOME/state/almanac-vault-reconciler.json`
- inject compact refreshed context into relevant future turns via the `pre_llm_call` hook
- avoid mutating Hermes core or depending on live built-in `MEMORY.md` prompt rebuilds

Design notes:
- uses only stdlib
- does not persist anything to session DB
- keeps context ephemeral and attached to the current user turn
- injects on first turn, on revision change, and on Almanac-relevant prompts
