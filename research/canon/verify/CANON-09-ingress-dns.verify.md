# CANON-09 — Ingress & DNS — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened `python/arclink_ingress.py` and every
adjacent file at the cited lines; ran the test suite; grepped for callers/writers. CODE WINS over
doc/comment/name. Default = refuted-when-uncertain.

VERDICT: **TRUSTWORTHY (with additions).** The record's load-bearing claims hold under independent
re-read. Every both-ends seam I re-opened matched. I did NOT refute any core claim. I add two gaps
the record missed (lingering torn-down rows make the global UNIQUE index a latent crash surface;
executor teardown silently counts never-deleted hostnames as removed) and one severity nuance.

---

## RE-CONFIRMED CLAIMS (independently re-verified in code)

- **Sole tracked file / 284 lines.** `wc -l` = 284; `git ls-files | grep ingress` shows
  `python/arclink_ingress.py` as the only code member (others are docs/tests/ground-truth). CONFIRMED.
- **Three `cloudflare`-object wrappers have ZERO production callers.** `rg` for
  `provision_arclink_dns|reconcile_arclink_dns|teardown_arclink_dns` across `python/ bin/ tests/`
  hits ONLY their defs (ingress.py:114,192,207) and `tests/test_arclink_ingress.py:49,86,115,122,147,151`.
  The sovereign worker import (sovereign_worker.py:67) pulls only
  `arclink_dns_records_for_teardown, mark_arclink_dns_torn_down, persist_arclink_dns_records`.
  provisioning.py:25 / action_worker.py:31 import only `desired_arclink_ingress_records`
  (+`render_traefik_dynamic_labels`). CONFIRMED — the MEDIUM "dead/divergent API surface" risk is real.
- **`desired_*` always CNAME + proxied=True, only dashboard/hermes roles.** ingress.py:39-43 +
  adapters.py:228-238 (4 hostnames) filtered by `ARCLINK_HOST_ROLES=("dashboard","hermes")` (ingress.py:19,42).
  Files/code dropped. CONFIRMED.
- **Upsert omits `provider_record_id`; relies on schema default `''`.** Schema control.py:1144
  `provider_record_id TEXT NOT NULL DEFAULT ''`; INSERT column list ingress.py:74-77 has no
  `provider_record_id`; ON CONFLICT update (ingress.py:79-91) never touches it. `rg provider_record_id
  python/arclink_ingress.py` shows only the teardown SELECT/read (ingress.py:174,186). CONFIRMED — ingress
  never writes it; CANON-08 `_mark_dns_provisioned` (sovereign_worker.py:2011-2023) does.
- **Status-preservation upsert.** ingress.py:82-89 preserves `'provisioned'` only when
  hostname/UPPER(record_type)/target all unchanged; else resets to `excluded.status` (`'desired'`).
  Re-verified by the passing test `test_dns_persist_preserves_provisioned_status_for_unchanged_record`.
  CONFIRMED.
- **`_mark_dns_status` bulk-updates ALL rows for a deployment.** ingress.py:145-148 WHERE clause is
  `deployment_id = ?` only — no per-record discrimination. CONFIRMED (record self-check #4 right).
- **append_arclink_event signature / event columns.** control.py:3870-3889 kw-only
  subject_kind/subject_id/event_type/metadata; ingress calls match (ingress.py:127-133,150-156).
  CONFIRMED.
- **No env vars, no os import, no sockets/subprocess/files.** No `import os`; imported adapter helpers
  (adapters.py:228-374) are pure (no `os.environ`). CONFIRMED for this piece.
- **6 tests pass.** `python3 tests/test_arclink_ingress.py` -> "PASS all 6 ArcLink ingress tests".
  CONFIRMED.

## CROSS-PIECE SEAMS — RE-OPENED BOTH ENDS

- **Seam #1 (-> CANON-08 desired-records).** Producer ingress.py:46-60 emits `dict[role, DnsRecord]`.
  Consumers re-project `.hostname/.record_type/.target/.proxied`: provisioning.py:1744-1752 and
  action_worker.py:220-228 — both read EXACTLY those 4 fields. BOTH-ENDS-VERIFIED: confirmed.
- **Seam #2 (-> CANON-08 persist).** `_persist_dns_from_intent` (sovereign_worker.py:1981-1992) reads
  `record["hostname"]/["record_type"]/["target"]` (subscript) + `record.get("proxied", True)`, rebuilds
  DnsRecord, calls `persist_arclink_dns_records`. Producer dict shape provisioning.py:1744-1752 supplies
  all keys. `proxied` IS read here but then DROPPED by persist (not a DB column). BOTH-ENDS-VERIFIED:
  confirmed, with the noted `proxied` drop.
- **Seam #3 (-> CANON-11 teardown shape).** ingress.py:182-188 emits `{hostname, record_type,
  provider_record_id}`. Path: `CloudflareDnsTeardownRequest.records` -> `_clean_cloudflare_teardown_record`
  (executor.py:2522-2530, `.get()` on all three, requires non-empty hostname) ->
  `_cloudflare_delete_dns_records` reads `record.get("provider_record_id")` (executor.py:2584), falls
  back to `_cloudflare_find_dns_record` which reads `record["record_type"]` and `record["hostname"]`
  via SUBSCRIPT (executor.py:2625-2626). Ingress always supplies both keys, so no KeyError.
  BOTH-ENDS-VERIFIED: confirmed.
- **Seam #4 (<- provider_record_id backfill).** Writer `_mark_dns_provisioned` (sovereign_worker.py:2006-2023)
  consumes `dns_result.metadata["provider_record_ids"]` (executor.py:1174) and `dns_result.records`
  (hostnames, executor.py:1168), `zip()`-aligned. Both tuples derive from the same
  `_plan_cloudflare_dns_records(request.dns)` iteration order in `cloudflare_dns_apply` (executor.py:1156,
  1168,1174) so alignment is sound. Skipped for tailscale/skipped-apply (sovereign_worker.py:1208-1218);
  teardown then relies on the executor find-by-name fallback. BOTH-ENDS-VERIFIED: confirmed.
- **Seam #5 (events/schema).** control.py:1138-1149 vs ingress INSERT columns; append_arclink_event sig.
  CONFIRMED.
- **Seam #6 (adapters render fns).** adapters.py:322-374 render_traefik_http_labels /
  _http_path_labels return `dict[str,str]`; ingress consumes (ingress.py:259-283). CONFIRMED.

## DRIFT CLAIMS — RE-CHECKED

- D2 (wrappers test-only dead code): CONFIRMED via grep above.
- D3 (unused tailscale params in `desired_arclink_ingress_records`): CONFIRMED — tailscale branch returns
  `{}` (ingress.py:59) without reading them.
- D4 (`proxied` dropped on persist): CONFIRMED — not a column; `FakeCloudflareClient.drift` (adapters.py:209)
  is the only place proxied is compared, and it is test-only.
- D5 (`except Exception` retry breadth): CONFIRMED ingress.py:228 catches bare `Exception`. (Dead code, so
  impact is academic.)

## NEW GAPS THE RECORD MISSED

- **GAP-A (MEDIUM) — Lingering torn-down rows turn the global UNIQUE index into a latent crash surface.**
  `idx_arclink_dns_records_host_type` is a GLOBAL unique index on `(LOWER(hostname), UPPER(record_type))`
  with NO partial `WHERE status != 'torn_down'` filter (control.py:2077-2078, re-read: no WHERE clause).
  There is NO `DELETE FROM arclink_dns_records` anywhere in `python/` (`rg` = zero hits) — teardown only
  sets `status='torn_down'` (ingress.py:146,168). So torn-down rows persist forever and still occupy the
  hostname index. `persist_arclink_dns_records` handles conflicts ONLY via `ON CONFLICT(record_id)`
  (ingress.py:78). If any future deployment ever lands the same `(hostname, record_type)` with a DIFFERENT
  `record_id` (i.e. prefix reuse across deployments — including reuse of a torn-down deployment's prefix),
  the ON-CONFLICT clause does NOT catch the hostname-index collision and `INSERT` raises an unhandled
  `sqlite3.IntegrityError`, crashing persist with no recovery. The record's self-check #3 only said "I did
  not prove prefix uniqueness"; it did NOT surface that torn-down rows are never reaped, which is what makes
  the index permanently loaded against history. Mitigation in practice: prefix reservation in
  `arclink_deployments` (control.py:3569) is CANON-08-owned and unverified here.
  Cite: python/arclink_ingress.py:78, python/arclink_control.py:2077-2078, python/arclink_ingress.py:146.

- **GAP-B (LOW) — Executor teardown counts never-deleted hostnames as "removed", and ingress records them
  as torn down.** `cloudflare_dns_teardown` returns `records=tuple(record["hostname"] for record in records)`
  (executor.py:1045) — the hostnames it *attempted*, NOT what was actually deleted. Inside
  `_cloudflare_delete_dns_records`, a record with empty `provider_record_id` whose find-by-name returns
  nothing is silently `continue`'d (executor.py:2588-2589) and never appears in the real
  `provider_records`. So `removed_dns` at sovereign_worker.py:1364 over-reports, and `mark_arclink_dns_torn_down`
  (ingress.py:159-168) writes those hostnames into the `dns_teardown` event metadata `removed` list as if
  removed. A DNS record that never existed in Cloudflare is reported as torn down. This is a cross-piece
  silent-no-op straddling CANON-11/CANON-08/CANON-09; ingress is the final recorder of the false signal.
  Cite: python/arclink_executor.py:1045, python/arclink_executor.py:2588-2589, python/arclink_ingress.py:167.

- **GAP-C (INFO) — `persist_arclink_dns_records({})` still commits.** In tailscale mode
  `desired_arclink_ingress_records` returns `{}`; `_persist_dns_from_intent` builds an empty dict and calls
  persist, whose for-loop runs zero times but still issues `conn.commit()` (ingress.py:104). Harmless
  no-op (empty transaction commit) but confirms the function has no early-return guard for empty input.
  Cite: python/arclink_ingress.py:70-104.

## SEVERITY NUANCE

- The record rates "Dead/divergent DNS API surface" MEDIUM. Given the wrappers are pure dead code with no
  production reachability and a clean test harness, the *operational* risk is LOW; the MEDIUM is justified
  only as a doc-trust/clarity hazard (the prior ground-truth doc treated them as the live path). Calibration
  is defensible; I leave it as a residual disagreement rather than a refutation.

## MINOR IMPRECISIONS (not refutations)

- Output-contract line 24 lists `created_at` among "Columns written" on the upsert. CODE: `created_at` is
  written only on INSERT; the ON-CONFLICT update (ingress.py:78-91) does NOT update `created_at` (it
  updates last_checked_at + updated_at only). The record's parenthetical is loose but the surrounding claim
  (provider_record_id preserved on conflict) is correct.

## REFUTATIONS

None of the record's load-bearing claims were refuted. Every seam marked both-ends-verified was
re-opened at both ends and matched. The record is unusually careful (its self-checks #3-#5 anticipate the
right edges); my additions extend, not contradict, it.
