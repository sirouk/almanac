<<<CODEX-DECISIONS-START CANON-01>>>
## CANON-01 — Codex (GPT-5.5 xhigh) decision recommendations (symphony-anchored)

No deferred operator decisions remain for CANON-01; no `### DECISION` blocks are emitted.

- RECOMMENDATION: Accept `NONE` as the resolution. Do not invent an operator schema/policy call for this piece; keep future schema-ledger work in the normal GAP-032 engineering backlog.
- SYMPHONY ANCHOR: `Configuration, Schema, And Migration` — “Database schema changes are migration-aware, idempotent, reversible where practical”; `Secrets, Keys, And Rotation` — public artifacts “must never contain secret values.”
- CODE GROUNDING: Fix record says `NEEDS-DECISION - NONE`; reconciled status says `9 fixed / 3 skipped / 0 needs-decision`. Reopened code shows fail-closed/defaulting config parsing (`python/arclink_control.py:161`, `:347-395`), secret-rejecting event/notification JSON (`:3318-3321`, `:3964`, `:8199`), guarded raw bypasses (`python/arclink_llm_router.py:705-706`, `:794`, `:1078`; `python/arclink_wrapped.py:138-139`, `:1009`; `python/arclink_chutes.py:460-463`, `:930`), and fail-closed Docker trust guards (`python/arclink_boundary.py:85-97`).
- RATIONALE: The remaining symphony target, versioned/reversible old-state-fixture migrations, is a roadmap engineering gap, not an unresolved operator decision.
- TRADEOFFS & ALTERNATIVES: Rejected promoting org-profile table ownership, schema-ledger timing, or GAP-019 trust acceptance into new CANON-01 decisions; those are already classified as scope correction, future migration architecture, or existing risk acceptance.
- EFFORT / BLAST-RADIUS: Low; no code surfaces should change from this decision pass.

<<<CODEX-DECISIONS-END CANON-01>>>
