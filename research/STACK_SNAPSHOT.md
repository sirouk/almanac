# Stack Snapshot

- generated_at: 2026-05-14T05:05:00Z
- project_root: .
- primary_stack: Python
- primary_score: 092/100
- confidence: high

## Deterministic Scoring Inputs

Repository-level public signals, excluding private state and generated caches:

| signal | count / evidence |
| --- | --- |
| Python source files | 177 |
| Shell scripts | 77 |
| TypeScript / TSX files | 7 |
| Runtime manifests | `requirements-dev.txt`, `compose.yaml`, `Dockerfile`, `deploy.sh`, `test.sh`, `web/package.json` |
| Wave 3 implementation target | `python/arclink_pod_migration.py`, `python/arclink_control.py`, `python/arclink_action_worker.py`, `python/arclink_executor.py` |

Scoring rule:

- Python receives base weight from source majority plus direct ownership of the
  Wave 3 control-plane path.
- Shell receives operational weight from canonical deploy and job wrappers.
- Node.js receives UI weight from the Next.js web surface, but Wave 3 does not
  require a Captain-facing UI unless a disabled route is added.
- SQLite and Compose are runtime components, not standalone primary stacks for
  this mission.

## Project Stack Ranking

| rank | stack | score | evidence |
| --- | --- | --- | --- |
| 1 | Python | 092 | 177 Python files; control DB, migration orchestrator, executor, action worker, provisioning, fleet, and tests are Python-led. |
| 2 | Bash / POSIX shell | 056 | 77 shell scripts; canonical deploy/control wrappers and optional job-loop integration. |
| 3 | Docker Compose | 048 | `compose.yaml`, `Dockerfile`, executor apply/lifecycle surfaces. |
| 4 | SQLite | 046 | Control-plane schema in `python/arclink_control.py`; Wave 3 adds `arclink_pod_migrations`. |
| 5 | Node.js / Next.js | 034 | `web/package.json`, TypeScript app/admin UI, web tests; secondary for Wave 3. |
| 6 | External services | 012 | Stripe, Telegram, Discord, Cloudflare, Tailscale, Hetzner, Linode, Chutes, and Notion are present but proof-gated and out of local PLAN scope. |

## Ranked Stack Hypotheses

1. **Python control-plane application with SQLite state and executor-managed
   Docker Compose runtime**: selected. This matches Wave 3 implementation,
   schema, tests, and action-worker dispatch.
2. **Shell-first operator automation around Python helpers**: plausible for
   deploy/upgrade work, but not the right primary path for migration replay,
   rollback, manifests, or schema drift checks.
3. **Next.js product/admin application backed by Python APIs**: true for the
   public surface, but Wave 3 initial rollout is Operator-only and does not
   require Captain-facing migration UI.

## Alternatives

| alternative | fit for Wave 3 | decision |
| --- | --- | --- |
| Add a new transfer service or infrastructure dependency | Low | Avoid. Existing Python + executor seams are enough for local proof. |
| Implement migration mostly in shell/rsync scripts | Medium for host work, low for replay/audit | Reject for primary implementation; shell can wrap GC later if needed. |
| Implement migration as a web/UI feature first | Low | Captain migration remains disabled by default behind `ARCLINK_CAPTAIN_MIGRATION_ENABLED=0`. |

## Confidence

Deterministic confidence score: **92/100**.

Confidence is high because repository structure, manifests, and the Wave 3
target files all point to Python as the primary implementation stack. The
remaining uncertainty is live host transfer behavior, which is intentionally
proof-gated and outside local PLAN validation.
