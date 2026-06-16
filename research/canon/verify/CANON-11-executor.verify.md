# CANON-11 Executor — Adversarial Verification

Verifier: independent Opus 4.8 skeptic. Method: re-opened `python/arclink_executor.py`
(2948 lines per Read / 2947 per `wc -l`), every cited caller, the CANON-12 broker, and the
CANON-01 control schema. Every load-bearing claim below was re-read at path:line; I did not
trust the record's citations.

## OVERALL VERDICT: TRUSTWORTHY (with additions)

The record is unusually accurate. I independently re-confirmed all six both-ends-verified
cross-piece contracts, the HIGH `operation_conn`-dead-in-production risk, the
`rollback_apply`-has-no-caller claim, the fail-closed `_require_live_enabled` gating on every
mutator except dry-run, and the byte-level broker wire contract. I could NOT manufacture a
refutation of any of its core claims. I did find FIVE gaps the record under-states or misses,
none of which overturn the verdict but two of which deserve their own ledger entries.

---

## REFUTATIONS ATTEMPTED (claim -> result)

1. **"operation_conn is never set in production; durable idempotency is inert" (HIGH risk).**
   RE-CONFIRMED, not refuted. `grep operation_conn python/` outside the executor returns ZERO
   hits. The two production constructions — `arclink_sovereign_worker.py:1333-1335` and
   `arclink_action_worker.py:2306-2309` — and the factory `executor_for_fleet_host`
   (`arclink_executor.py:96,142`) all omit `operation_conn`, so it defaults `None`
   (`:852,859`). All four `_*_operation_idempotency` helpers short-circuit on `None`
   (`:2708,2730,2755,2781`). I additionally checked whether the action worker writes the durable
   ledger ITSELF around the call: it does NOT — `_link_action_operation`
   (`arclink_action_worker.py:1303-1321`) writes `arclink_action_operation_links`, a DIFFERENT
   table, never `arclink_operation_idempotency`. So the ledger is genuinely written by nothing
   in production. Risk is correctly calibrated HIGH.

2. **"docker_compose_dry_run is the only method lacking _require_live_enabled."**
   RE-CONFIRMED. I enumerated every public method of `ArcLinkExecutor` and read each first
   statement: `docker_compose_apply:891`, `docker_compose_lifecycle:950`,
   `cloudflare_dns_teardown:1032`, `cloudflare_dns_apply:1155`, `cloudflare_access_apply:1179`,
   `chutes_key_apply:1197`, `stripe_action_apply:1313`, `rollback_apply:1427` all call
   `_require_live_enabled` first. `docker_compose_dry_run:876` does not. Claim holds.

3. **Broker wire contract "both-ends-verified byte-for-byte."** RE-CONFIRMED.
   Producer `BrokeredDockerComposeRunner.run` (`arclink_executor.py:796-830`) sends
   `{deployment_id, operation, project_name, env_file, compose_file, remove_volumes,
   include_all}` with header constant `executor.DEPLOYMENT_EXEC_BROKER_TOKEN_HEADER`
   (`:45,810`). Server `arclink_deployment_exec_broker.py`: auth via `hmac.compare_digest`
   (`:96-99`), `ALLOWED_OPERATIONS={compose_up,compose_ps,compose_down}` (`:32`) matches the
   exact strings the producer emits from `_broker_operation_from_compose_args`
   (`arclink_executor.py:759-771`); re-derives args via `_compose_args_for_operation` (`:102-114`)
   that mirrors the producer's reverse mapping; returns `{"ok":True,"result":{...}}` on success
   (`:293`) / `{"ok":False,"error":...}` on failure (`:295`). Producer reads
   `payload.get("ok") is not True` and `payload.get("result")` (`:826-830`). All keys, the
   header constant, and the ok/result/error envelope match. No mismatch found.

4. **Path containment "deployment-scoped, env==arclink.env, compose==compose.yaml,
   project==arclink-{id}."** RE-CONFIRMED in `_validate_deployment_config_paths:1817-1847` and
   `_require_compose_project_name:1790-1797`. I attacked the resolve-then-use-raw seam: the
   validator resolves with `resolve(strict=False)` while the runner is handed the unresolved
   `plan["env_file"]/["compose_file"]` strings (`:922-923`). Because docker re-resolves the same
   string the validator resolved, this is only exploitable as a symlink-swap TOCTOU between
   validate and run — narrow, host-local, and already acknowledged by the record's self-check #4.
   Not a clean refutation.

5. **"rollback_apply has no production caller."** RE-CONFIRMED. `grep rollback_apply|
   RollbackApplyRequest python/ bin/` returns only the executor and (per record) tests. Pod
   migration uses `docker_compose_lifecycle teardown` for rollback
   (`arclink_pod_migration.py:1118`). Claim holds.

6. **CANON-01 schema/function citations.** RE-CONFIRMED. `arclink_operation_idempotency` schema
   at `arclink_control.py:1388-1401` (PK `(operation_kind, idempotency_key)`, status CHECK
   `IN ('reserved','running','succeeded','failed')`, intent_digest/result_json/provider_refs_json/
   error columns). Functions `reserve/replay/complete/fail_arclink_operation_idempotency` at
   `:3299/3333/3352/3397` exactly as cited.

---

## NEW GAPS (record + prior docs both missed)

G1. **MEDIUM — Live `docker_compose_apply` has NO idempotency guard at all (not even the
    in-process dict).** The record's HIGH risk is scoped to chutes/stripe, but I confirmed the
    live (non-fake) compose path (`:890-947`) calls NONE of `_reserve/_complete/_replay`, has no
    `intent_digest` check, and no `_live_*_runs` entry. Same for `cloudflare_dns_apply` (live),
    `cloudflare_dns_teardown`, `cloudflare_access_apply`, `docker_compose_lifecycle`, and
    `rollback_apply` live paths. Compose `up -d` is naturally idempotent so this is benign for
    compose; but it means the entire live mutation surface EXCEPT chutes/stripe relies on the
    underlying provider operation being idempotent, with no ArcLink-side replay record. The
    record frames idempotency as a chutes/stripe-specific weakness; in fact only chutes/stripe
    even ATTEMPT ArcLink-side idempotency, and that attempt is the one that's dead (G-link to
    the HIGH risk). Cite: `python/arclink_executor.py:890-947,1031-1052,1154-1194`.

G2. **MEDIUM — Live Cloudflare DNS upsert is a find-then-create TOCTOU race.**
    `_cloudflare_upsert_dns_records:2538-2569` does GET (`_cloudflare_find_dns_record`) then
    POST-if-absent / PUT-if-present per record. Two concurrent applies for the same hostname
    both find nothing and both POST, creating duplicate Cloudflare records. No lock, no
    provider-side idempotency key on the Cloudflare call. Reachable when sovereign + action
    workers (or two action workers) race the same deployment's DNS. The record never mentions
    this race. Cite: `python/arclink_executor.py:2538-2569,2623-2631`.

G3. **MEDIUM — `SshDockerComposeRunner.write_text_file` is FAIL-OPEN on its containment check.**
    `write_text_file(path, content, *, allowed_root="", mode="0600")` (`:702-738`) only enforces
    root containment `if clean_allowed_root and not _remote_path_within(...)` (`:707-708`). With
    the DEFAULT `allowed_root=""`, the containment check is SKIPPED ENTIRELY and the method writes
    to ANY absolute path on the remote trusted host (same for `read_text_file:663-700`). Both
    current production callers pass a non-empty `allowed_root`
    (`arclink_sovereign_worker.py:1780,1793`), so it is not exploitable today — but it is a
    fail-open default on a remote-host arbitrary-file-write primitive, defended only by every
    future caller remembering to pass `allowed_root`. The record lists these methods under
    TOUCH POINTS/subprocess but never flags the fail-open default. Cite:
    `python/arclink_executor.py:702-708,663-669`.

G4. **LOW — `_cleanup_materialized_secret_root` is safe against a symlinked CHILD but not a
    symlinked ROOT.** Self-check #5 proves a symlinked child is unlinked (link removed, not
    target) — correct. But if `{config}/secrets` ITSELF is a symlink to e.g. `/etc`,
    `clean_root = root.resolve()` (`:2133`) becomes `/etc`, which is NOT in the refused set
    `{"/", "/run/secrets"}` (`:2136`), and the function then `iterdir()`s and `unlink()`s every
    non-dir child of the target directory. Requires winning a race to swap the just-created
    `secrets` dir for a symlink before the failure-cleanup runs, so narrow, but the refused-path
    allowlist is incomplete and the symlinked-root case is unhandled. Cite:
    `python/arclink_executor.py:2131-2150,926`.

G5. **LOW/INFO — `_validated_docker_compose_lifecycle_paths` project-override is reachable with
    operator-supplied action metadata.** The record's MEDIUM `allow_lifecycle_project_override`
    risk is correct; I confirmed the PRODUCER side: `arclink_action_worker.py:851` passes
    `project_name` straight from action `metadata` via `_lifecycle_path_overrides`
    (`:106-122`), gated by the same env flag. Nuance the record overstates: even with override,
    `env_file`/`compose_file` overrides are still constrained by
    `_validate_deployment_config_paths(deployment_id=request.deployment_id,...)` to a root dir
    whose name starts with THIS deployment's prefix (`:1837-1839`), so the compose/env files
    cannot escape the deployment's own directory — only the project LABEL can diverge. Impact is
    therefore "wrong docker project label on this deployment's files," slightly narrower than
    "target a different arclink-* project." Severity MEDIUM stands but with reduced blast radius.
    Cite: `python/arclink_executor.py:1870-1895`, `python/arclink_action_worker.py:106-122,851`.

---

## SEAM MISMATCHES
None that break the contract. The only asymmetry (already flagged by the record's self-check #3)
is that the producer always sends `remove_volumes`/`include_all` while the server honors them
per-operation only (`_compose_args_for_operation:108-113`). Harmless. Confirmed.

## RISK SEVERITY CALIBRATION
- HIGH (operation_conn inert): CORRECT. Strengthened — action worker does not back-fill the
  ledger either.
- MEDIUM (SSH/local root-equivalent GAP-019): CORRECT.
- MEDIUM (lifecycle project-override): CORRECT severity; blast radius slightly narrower than
  stated (see G5).
- LOW (broker sends ignored keys) / LOW (StrictHostKeyChecking=accept-new TOFU) / INFO (fake
  idempotency in-memory): all CORRECT.

## RESIDUAL DISAGREEMENTS
- The record's HIGH risk should be widened: the missing idempotency is not merely "chutes/stripe
  rests on a volatile dict" — it is that ArcLink-side idempotency is ATTEMPTED only for
  chutes/stripe and is dead there, while compose/dns/lifecycle have NO ArcLink-side idempotency
  by design (G1, G2).
- The fail-open default on `read_text_file`/`write_text_file` (G3) is a latent trusted-host
  arbitrary-file primitive the record does not surface.
