# Ralphie Steering: ArcLink Dream Buildout

## Mission

Turn the ArcLink dream system described in `USER_JOURNEY.md` into working,
tested repository reality, using `GAPS.md` as the implementation queue.

The primary trajectory is the Sovereign Control Node: the paid self-serve
ArcLink universe with public website/API onboarding, Raven, Stripe,
entitlements, fleet placement, ArcPod provisioning, dashboards, Hermes,
knowledge, sharing, inference, upgrades, backups, and operator control.
Shared Host and Shared Host Docker remain valid ArcLink substrates, but for
this mission they are secondary validation/support paths unless they block the
Control Node path, shared install artifacts, or local test truth.

This is an implementation mission, not another atlas pass. Close every
unattended local gap with source changes, tests, and honest documentation
updates. When a row requires live credentials, an external proof window, an
operator policy choice, or explicit residual-risk acceptance, do not fake-close
it and do not quit in confusion; classify it, make local behavior fail closed,
and leave an exact handoff item for the operator.

## Operating Contract

- Read `AGENTS.md`, `docs/arclink/sovereign-control-node-symphony.md`,
  `docs/arclink/academy-trainer.md`, `USER_JOURNEY.md`, `GAPS.md`,
  `IMPLEMENTATION_PLAN.md`, and `research/COVERAGE_MATRIX.md` first.
- Keep the Sovereign Control Node as the center of gravity. Treat Shared Host
  and Shared Host Docker work as supporting validation unless a current gap
  explicitly requires those modes.
- Do not read `arclink-priv/`, user homes, secret files, deploy keys, `.env`
  values, OAuth stores, bot tokens, or live credentials.
- Do not run live deploy/install/upgrade, Docker up/down/reconcile, Stripe,
  Chutes, Telegram, Discord, Notion, Cloudflare, Tailscale, SSH fleet mutation,
  or host mutation unless the operator explicitly authorizes a separate proof
  window later.
- Use ArcLink wrappers, plugins, hooks, generated config, tests, and service
  units. Do not modify Hermes core to make ArcLink behavior work.
- Preserve user/unrelated worktree changes. Do not revert files you did not
  touch for this mission.
- Prefer small, source-owned repair slices with focused validation over huge
  speculative rewrites.
- If a gap requires credentials, live external services, or a product/security
  policy decision, make the local code fail closed and record the exact proof or
  decision needed. Do not fake-close it.
- Keep public docs free of secrets, local private paths, and raw tool
  transcripts.

## Priority Order

1. Refresh the active queue from `GAPS.md` and `IMPLEMENTATION_PLAN.md`. Bucket
   each non-`real` row as `LOCAL`, `LIVE_PROOF`, `POLICY_DECISION`, or
   `RESIDUAL_RISK_ACCEPTANCE`.
2. If `GAP-025` has regressed, repair the broad no-secret local validation
   story first. A broken broad suite undermines every local `real` claim.
3. Prioritize local Sovereign Control Node rows and surfaces: `GAP-029`
   Operator Raven full-service control, `GAP-030` sovereign worker readiness,
   `GAP-031` LLM Router fallback/inference completeness, `GAP-032` rolling
   Hermes/ArcPod update orchestration, `GAP-033` cross-surface experience
   finish, and `GAP-034` Academy Trainer subject-matter corpus/continuing
   education. Pull in `GAP-019` or other security rows when they protect the
   Control Node path.
4. P2/P3 rows that are locally repairable or share code ownership with the
   active Control Node slice.
5. Live proof and policy rows only after the operator explicitly supplies
   credentials, authorization, or a decision in a separate proof window.

## Repair Loop

For each slice:

- Name the gap IDs and journey joints.
- Identify the smallest source files/tests that own the behavior.
- Reproduce the failing or missing proof with a focused local command.
- Patch code/tests/docs with the repo's existing patterns.
- Run focused tests, then broaden only as much as the touched surface warrants.
- Update `GAPS.md`, `USER_JOURNEY.md`, `IMPLEMENTATION_PLAN.md`, and
  `mission_status.md` only when the source truth changed.
- Leave a concise completion note in `research/BUILD_COMPLETION_NOTES.md`.

## Done Rule

Do not route to `done` while `GAPS.md` or `IMPLEMENTATION_PLAN.md` still has an
unchecked local code/test/doc repair that can be completed without live
credentials or a policy decision.

It is acceptable to leave explicit live-proof, policy, and residual-risk rows
open only when all of the following are true:

- They are labeled as proof-gated, policy-question, or residual-risk handoff.
- Local code fails closed or refuses to overclaim.
- `IMPLEMENTATION_PLAN.md`, `mission_status.md`, and
  `research/BUILD_COMPLETION_NOTES.md` name the exact remaining operator action.
- Focused tests and the broad local suite appropriate to the touched surface
  have passed or the remaining failure is documented as an external gate.

If only live/policy/residual-risk rows remain, route through `document` with a
clear handoff, then allow `done` once that document handoff has passed. Do not
keep retrying random local code, and do not stop merely because an authorized
external proof is unavailable.
