<<<CODEX-VERDICT-START CANON-17>>>
## CANON-17 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: Record is materially right: Academy/Crew/SOUL is built and the top risks stand; I object only to four refinements around PG-PROVIDER enforcement, mutation flags, marker semantics, and a validation fail-open.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM HIGH live-default risk: CE crawl defaults enabled in code and compose runs the weekly job; Trainer live defaults on in compose. `python/arclink_academy_scheduler.py:625`, `python/arclink_academy_scheduler.py:882`, `compose.yaml:97`, `compose.yaml:793`
- CONFIRM HIGH DNS-rebinding/TOCTOU: guard resolves/validates host, then `urlopen()` reconnects by hostname without pinning. `python/arclink_academy_scheduler.py:195`, `python/arclink_academy_scheduler.py:202`, `python/arclink_academy_scheduler.py:219`, `python/arclink_academy_scheduler.py:222`
- CONFIRM MEDIUM proposal TOCTOU: consumer does SELECT then INSERT with no `IntegrityError` recovery; final schema unique index is `(trainee_id, proposal_kind, origin_url)`. `python/arclink_academy_programs.py:755`, `python/arclink_academy_programs.py:791`, `python/arclink_control.py:1757`
- CONFIRM MEDIUM apply blast radius: live `academy_apply` is env+adapter gated, but materializes SOUL, vault files, memory/skill state, and post-apply refresh state. `python/arclink_action_worker.py:1083`, `python/arclink_academy_programs.py:2938`, `python/arclink_action_worker.py:2094`, `python/arclink_action_worker.py:2102`, `python/arclink_action_worker.py:2160`, `python/arclink_action_worker.py:2181`
- REFINE §A12 mutation claim: verifier is correct that Crew staging returns `mutation_performed=True`; Academy staging returns false, and materialized apply returns true. `python/arclink_crew_recipes.py:373`, `python/arclink_crew_recipes.py:953`, `python/arclink_academy_programs.py:2993`, `python/arclink_action_worker.py:2227`
- REFINE Contract #2 marker: producer emits `academy_soul_marker`, but consumer ignores that field and relies on hardcoded matching markers in `merge_academy_overlay`. `python/arclink_academy_programs.py:2984`, `python/arclink_action_worker.py:2087`, `python/arclink_org_profile.py:26`, `python/arclink_org_profile.py:1745`
- CONFIRM seams: MCP passes owner-validated proposal args to matching consumer; public bots call enroll/open/end; org overlay is marker-bounded; provisioning consumes `metadata_json["academy_training"]`; CE compose invokes scheduler. `python/arclink_mcp_server.py:2157`, `python/arclink_academy_programs.py:683`, `python/arclink_public_bots.py:29`, `python/arclink_public_bots.py:5816`, `python/arclink_org_profile.py:1713`, `python/arclink_provisioning.py:274`, `compose.yaml:793`
- CONFIRM producer-only router seam remains not BEV: Academy posts OpenAI-compatible `/chat/completions`; I did not cross-prove CANON-16 consumer behavior here. `python/arclink_academy_programs.py:2175`, `python/arclink_academy_programs.py:2191`
- REFINE §B34 env-matrix open item: tracked defaults prove shipped behavior is on; an operator-private env override remains outside this read-only proof. `python/arclink_academy_scheduler.py:625`, `python/arclink_academy_scheduler.py:868`, `compose.yaml:97`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM — `academy_apply` advertises `PG-PROVIDER` but does not enforce live provider proof before writes: deterministic Trainer review stamps `reviewed_at` with `live_enrichment_status="pending_pg_provider"`, and writes require only live adapter + `ARCLINK_ACADEMY_APPLY_LIVE` + review flags. `python/arclink_academy_programs.py:2302`, `python/arclink_academy_programs.py:2311`, `python/arclink_academy_programs.py:2875`, `python/arclink_academy_programs.py:2938`, `python/arclink_academy_programs.py:2991`
- LOW — source-lane validation is not strictly fail-closed: if the trainer registry import/load fails, `_validate_source_lanes` accepts lanes as-is. `python/arclink_academy_programs.py:3071`, `python/arclink_academy_programs.py:3075`
- LOW — crawl observation IDs can collide on same source/trainee/second and the INSERT has no conflict handler; scheduler timestamps are second-granularity. `python/arclink_control.py:66`, `python/arclink_academy_scheduler.py:430`, `python/arclink_academy_scheduler.py:458`

### Claude citations re-confirmed or corrected
- CONFIRMED schema has 10 `academy_*` tables plus `arclink_crew_recipes`; corrected proposal-index cite is the post-DDL drop/recreate migration, not only the table DDL block. `python/arclink_control.py:1476`, `python/arclink_control.py:1493`, `python/arclink_control.py:1686`, `python/arclink_control.py:1757`
- CONFIRMED one-open-session race handling via partial unique index + `IntegrityError` rollback. `python/arclink_control.py:1552`, `python/arclink_academy_programs.py:536`
- CONFIRMED `organization_private` is excluded from central sharing. `python/arclink_academy_trainer.py:649`, `python/arclink_academy_programs.py:1646`, `python/arclink_academy_programs.py:1741`
- CONFIRMED stale apply contract fail-closes before writes. `python/arclink_academy_programs.py:2850`, `python/arclink_academy_programs.py:2927`
- CONFIRMED latent `Sequence` annotation bug. `python/arclink_crew_recipes.py:11`, `python/arclink_crew_recipes.py:776`

### Residual disagreement with the Claude half (for final reconciliation)
- No material disagreement with the verifier. I do not ratify the auditor wording that all piece functions return `mutation_performed=False`, that Contract #2 is field-read, or that `PG-PROVIDER` is enforced by `academy_apply`; code makes those weaker than stated.
<<<CODEX-VERDICT-END CANON-17>>>
