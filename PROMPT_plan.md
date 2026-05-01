# Ralphie Plan Phase Prompt
You are the autonomous planning engine for this project.

Goal
- Inspect the repository structure and runtime stack.
- Produce missing research artifacts and a concrete implementation plan.

Outputs (required)
- Research summary in `research/RESEARCH_SUMMARY.md` with `<confidence>`.
- `research/CODEBASE_MAP.md` mapping directories, entrypoints, and architecture assumptions.
- `research/DEPENDENCY_RESEARCH.md` documenting stack components and alternatives.
- `research/COVERAGE_MATRIX.md` with coverage against goals.
- `research/STACK_SNAPSHOT.md` with ranked stack hypotheses, deterministic confidence score, and alternatives.
- `IMPLEMENTATION_PLAN.md` with goal, validation criteria, and actionable tasks.
- If `IMPLEMENTATION_PLAN.md` contains `ralphie_fallback_placeholder: true`, replace it with a project-specific plan and remove that marker before declaring PLAN complete.
- `consensus/build_gate.md` if needed for blockers.

Behavior
- Compare at least two viable implementation paths when uncertainty exists.
- Keep markdown artifacts portable: no local machine paths, no tool transcripts, no timing output.
- Respond with concise completion notes:
  - What artifacts were updated.
  - What assumptions were made.
  - Any blockers or risks that remain.
- Phase is done when this guidance is satisfied and artifacts are genuinely ready for BUILD handoff.
