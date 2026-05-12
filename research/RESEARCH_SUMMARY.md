# Research Summary

<confidence>94</confidence>

## Scope

This PLAN pass inspected the public ArcLink repository structure, stack
manifests, runtime entrypoints, existing Ralphie artifacts, and the active
Sovereign audit verification backlog:

`research/RALPHIE_SOVEREIGN_AUDIT_VERIFICATION_20260511.md`

It did not inspect private state, live credentials, user Hermes homes, deploy
keys, production services, payment/provider consoles, or external provider
accounts.

## Source Of Truth

The 2026-05-11 audit verification file is the active BUILD backlog.

| Severity | FACT | PARTIAL | FICTION |
| --- | ---: | ---: | ---: |
| Critical | 11 | 0 | 0 |
| High | 23 | 2 | 0 |
| Medium | 24 | 2 | 2 |
| Low | 21 | 3 | 0 |

`ME-11` and `ME-25` are FICTION/outdated and should remain regression-awareness
only. PARTIAL items must follow the corrected ground-truth wording in the audit
file rather than the original overbroad audit wording.

## Immediate Wave

Wave 1 is the first BUILD checkpoint:

- `CR-1`: Telegram webhook secret registration and verification.
- `CR-2`: non-root container runtime and Docker socket scoping.
- `CR-6` and `LOW-1`: auth-before-CSRF ordering for session mutations.
- `CR-7`: Discord timestamp tolerance and replay protection.
- `CR-8` and `ME-4`: hosted API body cap and malformed JSON handling.
- `HI-5` and `HI-6`: CORS on early hosted API returns and route-checked
  `OPTIONS` preflights.
- `CR-9`: backend/admin CIDR enforcement or explicit contract removal.
- `CR-11`: peppered session and CSRF token hashes.
- `HI-1`, `ME-12`, `ME-13`, `LOW-8`, and `LOW-9`: unified secret
  detection/redaction with redact-before-truncate behavior.
- `HI-4`, `HI-7`, `ME-2`, and `ME-3`: browser/API auth extraction, webhook
  rate limits, generic auth errors, and session-kind enforcement.

## Full Backlog Traceability

The BUILD plan and coverage matrix explicitly carry every active FACT or
actionable PARTIAL audit ID. Later waves are planned as:

| Wave | Active IDs |
| --- | --- |
| Wave 2 | `CR-3`, `CR-5`, `CR-10`, `HI-2`, `HI-10`, `HI-11`, `HI-12`, `HI-13`, `HI-15`, `HI-16`, `HI-17`, `ME-6`, `ME-8`, `LOW-11` |
| Wave 3 | `CR-4`, `HI-8`, `HI-9`, `HI-14`, `ME-7`, `ME-9`, `ME-10`, `LOW-6`, `LOW-7`, `LOW-13` |
| Wave 4 | `HI-3`, `HI-18`, `HI-19`, `HI-20`, `HI-21`, `HI-22`, `HI-23`, `HI-24`, `HI-25`, `ME-14`, `ME-26`, `LOW-10`, `LOW-12`, `LOW-15`, `LOW-16`, `LOW-17`, `LOW-18`, `LOW-19` |
| Wave 5 | `ME-1`, `ME-5`, `ME-15`, `ME-16`, `ME-17`, `ME-18`, `ME-19`, `ME-20`, `ME-21`, `ME-22`, `ME-23`, `ME-24`, `ME-27`, `ME-28`, `LOW-2`, `LOW-3`, `LOW-4`, `LOW-5`, `LOW-14`, `LOW-20`, `LOW-21`, `LOW-22`, `LOW-23`, `LOW-24` |

## Repository Finding

ArcLink is a Python-led control platform with Bash operational orchestration,
SQLite control state, Docker Compose runtime lanes, ArcLink-owned Hermes
plugins/hooks, and a compact Next.js web/admin surface.

| Signal | Evidence |
| --- | --- |
| Python control plane | `python/` contains hosted API, auth, control DB, workers, provisioning, fleet, ingress, evidence, bots, Notion, memory, dashboard, and live-proof modules. |
| SQLite state model | `python/arclink_control.py` owns schema/migration and is imported across auth, workers, fleet, provisioning, dashboard, and evidence paths. |
| Operational shell | `deploy.sh`, `bin/deploy.sh`, `bin/arclink-docker.sh`, and many `bin/*.sh` wrappers are canonical host/container lifecycle entrypoints. |
| Container runtime | `Dockerfile` and `compose.yaml` define Shared Host Docker and Sovereign Control Node service topology. |
| Web surface | `web/package.json` uses Next.js 15, React 19, TypeScript 5, ESLint, Tailwind, and Playwright. |
| Runtime pins | `config/pins.json` pins Python preferences, Node 22, qmd, Hermes runtime/docs, and service image lanes. |
| Regression suite | `tests/` contains focused tests for control, hosted API, auth, Docker, bots, workers, provisioning, fleet, evidence, memory, and web-adjacent contracts. |

## Worktree Context

The worktree already contains broad modifications across public code, tests,
web files, and research artifacts. Those edits must be preserved. BUILD should
verify source and focused tests before treating any audit ID as closed; prior
completion notes are context only.

Some Wave 1 mechanisms appear to have local source/test signals already, such
as webhook secret settings, hosted API body/CIDR settings, a shared secret
regex module, Docker hardening tests, and Discord replay/timestamp tests. They
still require direct verification before closure.

## Implementation Path Comparison

| Path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Wave-ordered verification and repair of current worktree | Honors risk order, preserves existing edits, starts with Wave 1, and supports small tested patches | Requires careful review because partial fixes may already exist | Selected. |
| Clean Wave 1 reimplementation from audit text | Simple mental model | High risk of overwriting, duplicating, or fighting dirty-tree work | Rejected. |
| Documentation-only triage | Fast and low runtime risk | Does not fix verified behavior defects | Rejected for FACT/actionable PARTIAL items. |
| Broad smoke validation before focused review | Useful release signal | Can obscure specific boundary failures and may require host state | Deferred. |
| Live provider/deploy proof | Strong production confidence | Blocked by no-secret/no-live-mutation constraints | Requires explicit operator authorization. |

## Assumptions

- Existing dirty-tree changes are user-owned or prior generated work and must
  not be reverted.
- BUILD may edit public ArcLink code, tests, web fixtures, and docs only when
  directly tied to an audit fix.
- Local fake-provider tests, temporary SQLite databases, command shims, and
  static Compose checks are the default validation method.
- Live Stripe, Chutes, DNS/Tailscale/Cloudflare, Telegram, Discord, Notion,
  Docker host mutation, and production deploy proof require named operator
  authorization.

## Risks

- Broad dirty-tree edits increase the risk of mixing unrelated work into a
  BUILD slice.
- Shared auth, hosted API, and secret-redaction changes can affect many routes.
- Container hardening must preserve the services that legitimately need Docker
  socket access.
- Live correctness remains unproved until authorized live proof runs.
- Terminal audit completion is unavailable until every FACT and actionable
  PARTIAL item is fixed or explicitly deferred with operator-facing rationale.

## Verdict

PLAN is ready for no-secret BUILD handoff. The selected handoff is
wave-ordered verification and repair, beginning with Wave 1 trust-boundary and
secret-safety findings and continuing to later waves only after focused tests
support the checkpoint.

Retry repair note: `IMPLEMENTATION_PLAN.md` now keeps Phase 0, Wave 1, later
BUILD phases, and validation checklist items open at PLAN handoff. The stack
snapshot was also corrected from a generic Node-first detection to a
repo-specific Python/Bash/Docker control-plane assessment. Prior local source
signals or historical completion notes are not accepted as completed checklist
state until BUILD re-verifies them.
