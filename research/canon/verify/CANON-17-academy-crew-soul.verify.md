# CANON-17 — Academy / Crew / SOUL — ADVERSARIAL VERIFY

Verifier: independent adversarial skeptic. Method: re-opened every load-bearing file
and re-derived each cited line; ran live Python to confirm/refute concurrency, import,
and DNS-rebinding claims. Default posture: refute unless independently re-confirmed.

Verdict files reviewed against actual code at:
- python/arclink_academy_programs.py (3122 lines)
- python/arclink_academy_scheduler.py (1068 lines)
- python/arclink_academy_trainer.py (2380 lines)
- python/arclink_crew_recipes.py (1509 lines)
- templates/{CREW_RECIPE,SOUL,SOUL.operator}.md.tmpl
- cross-piece: arclink_action_worker.py, arclink_org_profile.py, arclink_control.py,
  arclink_mcp_server.py, compose.yaml, research/ground-truth/06-academy-crew-soul.md

## OVERALL VERDICT: TRUSTWORTHY (with corrections)

The record is materially accurate. Every CROSS-PIECE CONTRACT it marks both-ends-verified
holds at both ends in code. Every DRIFT claim against the prior ground-truth doc is correct.
The two HIGH risks (live crawler/trainer default-ON; DNS-rebinding TOCTOU) and the MEDIUM
`Sequence` import bug are all independently re-confirmed in code and via live execution.
I found NO refutation of a load-bearing structural claim. I found a small set of
overstatements/imprecisions and several gaps neither doc mentions (below).

## CLAIMS RE-CONFIRMED (refuted = false)

1. Schema = 10 academy tables + arclink_crew_recipes. CONFIRMED at arclink_control.py:
   1476 (crew_recipes), 1493/1512/1536/1560/1597/1624/1643/1654/1670/1686 (10 academy
   tables incl. academy_source_crawl_observations:1686). Record's "10 tables, prior doc
   undercounted (missed crawl_observations)" is correct: prior doc lists only 9 academy
   tables at research/ground-truth/06-academy-crew-soul.md "Tables:" line.

2. Live crawler + live trainer ship default-ON. CONFIRMED: scheduler.py:625
   (`ARCLINK_ACADEMY_CE_LIVE_CRAWL` default=True) and compose.yaml:97
   (`ARCLINK_ACADEMY_TRAINER_LIVE: ${ARCLINK_ACADEMY_TRAINER_LIVE:-1}`). This is the
   single biggest canon correction and it is real.

3. SOUL apply seam (Contract #2). Producer stage_academy_apply emits keys at
   programs.py:2958-2996; consumer _materialize_academy_apply reads them at
   action_worker.py:2068-2186. Marker `ARCLINK ACADEMY SPECIALIST` is hardcoded both
   sides (org_profile.py:26 BEGIN_ACADEMY_MARKER; merge at action_worker.py:2098 via
   merge_academy_overlay, org_profile.py:1745). NOTE: consumer does NOT actually read the
   `academy_soul_marker` value the producer emits — it imports merge_academy_overlay which
   hardcodes the same marker. Both sides agree, but the seam is "marker matches by
   convention," not "consumer reads producer's marker field." Record says "reads exactly
   those keys" — true for the load-bearing keys; the marker is an exception (hardcoded, not
   read). Not a refutation; the markers are identical.

4. org_profile overlay (Contract #5). render/merge/remove_academy_overlay at
   org_profile.py:1713/1745/1755 are the only marker-block mutators; merge preserves the
   human SOUL body (slices [:start] and [end:]). CONFIRMED marker-bounded, additive.

5. MCP producer (Contract #4). mcp_server.py:2162 calls record_academy_resource_proposal
   with keyword args deployment_id/lane_id/proposal_kind/target_source_uid/title/origin_url/
   summary/relevance/citations/proposed_by — matches consumer signature programs.py:683.
   CONFIRMED. (Producer passes owner["deployment_id"], i.e. the validated owner deployment,
   not the raw argument — stronger than the record implies; auth is enforced before the call.)

6. `Sequence` import bug (DRIFT #5 / MEDIUM risk). CONFIRMED via live execution:
   crew_recipes.py imports only Any/Mapping/Protocol (line 11); `Sequence` is used at
   crew_recipes.py:776; `typing.get_type_hints(_academy_rollup_status)` raises
   `NameError: name 'Sequence' is not defined`. Runtime-safe under PEP 563 today.

7. DNS-rebinding / TOCTOU (HIGH risk). CONFIRMED: _url_allowed_for_live_crawl resolves +
   validates via getaddrinfo (scheduler.py:196-204); _default_fetch_url re-opens by
   hostname `urllib.request.Request(str(url))` (scheduler.py:219) with no IP pinning
   (no create_connection / pinned HTTPConnection). Second DNS resolution at fetch time =
   genuine rebinding window. No-redirect opener + https-only are the only mitigations.

8. stage_academy_apply fail-closed contract. CONFIRMED: the writes_enabled=True branch
   (programs.py:2938) is only reachable after `if not contract_ok` (2927) and
   `elif not contract_fresh` (2931) early-return — so a stale Major edit yields
   `stale_requires_regraduation`, writes_enabled=False. _materialize_academy_apply gates
   solely on writes_enabled (action_worker.py:1995) but that flag already encodes
   contract_fresh AND live_adapter AND live_authorized AND trainer_review_ready. Fail-closed.

9. organization_private never promoted. CONFIRMED: SHARE_INELIGIBLE_SOURCE_LANES=
   {"organization_private"} (trainer.py:649); promotion skips non-eligible lanes
   (programs.py:1741) and the has_candidate guard (programs.py:1657) prevents creating an
   empty central specialist for private-only trainees.

10. 64/64 tests pass. CONFIRMED by running the 4 listed test files.

## REFUTATIONS / CORRECTIONS (record overstates)

R1. (LOW) "This piece's own functions are all `mutation_performed=False`" (CODE-PATH TRACE,
    record line 50). PARTIALLY REFUTED: crew_recipes.stage_crew_academy_review and
    _persist_academy_agent_status return `mutation_performed=True` (crew_recipes.py:373,953)
    because they mutate arclink_crew_recipes.soul_overlay_json, arclink_deployments.
    metadata_json, and arclink_users. The blanket "all ... mutation_performed=False" is
    false; only workspace_mutation_performed=False holds universally. The intended claim
    (no Agent-FILE writes) is correct, but as written it is contradicted by code.

R2. (INFO) Prior-doc index drift the record did NOT flag. The real unique index is
    `idx_academy_resource_proposals_trainee_origin ON (trainee_id, proposal_kind,
    origin_url) WHERE origin_url != ''` (verified live from sqlite_master). The prior
    ground-truth doc and the record's own TOUCH POINTS describe it loosely; the
    proposal_kind column in the key is load-bearing (it lets add_resource and
    discontinue_resource for the same URL coexist). Not a refutation of the record, but
    the record never states the index includes proposal_kind, which matters for R-gap G1.

## NEW GAPS (neither record nor prior doc mention)

G1. (MEDIUM) record_academy_resource_proposal INSERT is a TOCTOU with NO IntegrityError
    handler. programs.py:755-760 SELECTs existing by (trainee_id, proposal_kind,
    origin_url); if none, INSERTs at programs.py:791 with NO try/except. The unique index
    (trainee_id, proposal_kind, origin_url) raises sqlite3.IntegrityError on a concurrent
    duplicate. Live-confirmed: a second INSERT of the same (trainee, kind, url) raises
    `UNIQUE constraint failed`. Unlike open_academy_mode (which catches IntegrityError and
    returns the race winner, programs.py:536-543), this path has no recovery. The MCP
    surface commits per call (mcp_server.py:2162, commit defaults True), so two agent
    turns / two MCP calls racing the same URL crash the loser with an unhandled exception
    instead of the idempotent dedup the docstring (programs.py:698-705) promises. Mitigated
    but not eliminated by single-writer SQLite (two connections/processes still interleave).

G2. (LOW) Per-trainee crawl can be made UNBOUNDED by config. _env_int for
    ARCLINK_ACADEMY_CE_CRAWL_LIMIT has minimum=0 (scheduler.py:638-644); the gate is
    `if limit and ... >= limit` (scheduler.py:667), so limit=0 disables the per-trainee cap
    entirely, leaving only the per-host cap. A 0-misconfig silently removes the total bound.

G3. (LOW) robots.txt 4xx/5xx fails OPEN. _robots_allowed returns (True, "") for any
    `status >= 400` except 401/403 (scheduler.py:288-293). A site returning 500 on
    /robots.txt is treated as "crawl allowed." Defensible policy, but it is fail-open and
    is not called out anywhere; combined with G-DNS it widens the crawl surface.

G4. (LOW) run_academy_trainer_review live failure is swallowed silently into the
    deterministic engine with only `review["live_error"]` recorded on enrichment_json
    (programs.py:2296-2299). A persistently failing live router (auth/timeouts) downgrades
    every weekly review to deterministic with no audit-row / notification surfacing — the
    Captain sees no signal that PG-PROVIDER inference is broken. Best-effort by design but
    unobservable.

G5. (INFO) academy_continuing_education docstring (programs.py:3008) says observed_sources
    are populated "behind PG-PROVIDER," but the scheduler populates them via the live
    crawler gated only on ARCLINK_ACADEMY_CE_LIVE_CRAWL (default True), with NO PG-PROVIDER
    check. The record flags this as DRIFT #7 (LOW) already — re-confirmed; listing here as
    an environment-gate-vs-proof-gate mismatch the code resolves in favor of the env flag.

## SEAM MISMATCHES
None that break the contract. The one nuance (Contract #2 marker is hardcoded both sides,
not field-read by consumer) does not produce a mismatch because the literal is identical.

## RESIDUAL DISAGREEMENTS
- The record's Adversarial Self-Check #1 explicitly defers reading config/*.env* for a
  CE/trainer override. I did not find such an override either; the compose default
  (`:-1`/default-True) stands as the shipped behavior, so the HIGH risk is real unless a
  deploy-lane env file flips it. CANON-27 should confirm (OPEN item #1 is valid).
- Contract #8 (LLM router) is producer-only verified in both the record and here; the
  router response-shape contract is not cross-read. Agreed-open.
