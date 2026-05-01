# Ralphie Steering: Product Surface Responsive Fix

Status: superseded by `research/RALPHIE_LINT_BLOCKER_REPAIR_STEERING.md`.

The responsive product-surface repair has already been implemented and
browser-smoked in the current ArcLink worktree. Do not treat this file as an
active BUILD request.

Accepted evidence from the current run:

- `/`, `/onboarding/onb_surface_fixture`, `/user`, and `/admin` were checked
  at a narrow mobile viewport around 390px and at desktop width.
- The browser smoke reported no page-level horizontal overflow after the CSS
  containment repair.
- Admin action submission still queues intent and does not mutate DNS/provider
  state.
- The no-secret product-surface and public-bot tests passed with public hygiene,
  compile, and diff checks.

The remaining lint blockers are documentation reconciliation and a minimal
`/favicon.ico` response so future browser gates do not interpret the harmless
404 as a console failure.

Next active work:

1. Follow `research/RALPHIE_LINT_BLOCKER_REPAIR_STEERING.md`.
2. Then continue to production API/auth from
   `research/RALPHIE_FULL_DELIVERY_STEERING.md`.
