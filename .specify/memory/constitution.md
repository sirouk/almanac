# Ralphie Constitution

## Purpose
- Establish deterministic, portable, and reproducible control planes for autonomous execution.
- Define behavior for all phases from planning through documentation.

## Governance
- Keep artifacts machine-readable: avoid local absolute paths, avoid command transcript leakage, and keep logs deterministic.
- Validate phase completion through reviewer-intelligence consensus and execution/build gates; keep semantic checks close to code and outputs.
- Treat gate failures as actionable signals, not terminal failure if bounded retries remain.

## Phase Contracts
- **Plan** produces research artifacts, an explicit implementation plan, and a deterministic stack snapshot.
- **Build** executes plan tasks against evidence in IMPLEMENTATION_PLAN.md.
- **Test** verifies behavior changes and documents validation rationale.
- **Refactor** preserves behavior, reduces complexity, and documents rationale.
- **Lint** enforces deterministic quality and cleanup policies.
- **Document** closes the lifecycle with updated user-facing documentation.

## Recovery and Retry Policy
- Every phase attempt that fails consensus or transition checks is retried within
  `PHASE_COMPLETION_MAX_ATTEMPTS` using feedback from prior blockers.
- Hard stop occurs only after bounded retries are exhausted and gate feedback is persisted.

## Evidence Requirements
- Phase completion is judged by reviewer-intelligence consensus plus execution/build-time gates.
- Plan/research artifacts are reviewed for substantive quality but not by rigid template matching.

## Environment Scope
- Repository-relative paths and relative markdown links are preferred.
- External references are allowed only when version/risk tradeoffs are explicitly documented.
