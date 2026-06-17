<<<CODEX-VERDICT-START CANON-32>>>
## CANON-32 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: Drift conclusions mostly stand, but the Claude record/verifier are materially wrong about OpenAPI parity-test absence, product-matrix guarding, missing-module count, and untracked-artifact hygiene visibility.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- REFUTE: product-matrix totals are unguarded. The test sums row statuses and compares declared totals (`tests/test_documentation_truths.py:76-87`), and `main()` runs 11 doc-truth tests (`tests/test_documentation_truths.py:324-336`), not 4.
- REFINE: gated-row guard is language-keyword based, not PG-/policy-anchor based (`tests/test_documentation_truths.py:112-123`).
- CONFIRM: canonical module/table map is stale and unguarded. Docs claim 84 modules and 44/9 tables (`docs/arclink/architecture.md:18`, `docs/arclink/architecture.md:280-284`; `research/ARCLINK_GROUND_TRUTH_BRIEF.md:89`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:239-245`); code has the omitted modules `arclink_operator_upgrade_host_runner` (`python/arclink_operator_upgrade_host_runner.py:2`), `arclink_skill_enablement` (`python/arclink_skill_enablement.py:2-7`), `arclink_upgrade_policy` (`python/arclink_upgrade_policy.py:2`), plus omitted tables `academy_source_crawl_observations` (`python/arclink_control.py:1686`) and `arclink_agent_skill_enablement` (`python/arclink_control.py:1718`). `DOC_STATUS` still labels the stale map Canonical (`docs/DOC_STATUS.md:26`); schema test is subset-only (`tests/test_arclink_schema.py:41-78`).
- REFINE: OpenAPI byte-identity claim is false, but the “no parity test exists / spec can silently drift” claim is false. A real static-copy parity test canonicalizes generated and committed JSON (`tests/test_arclink_hosted_api.py:5496-5507`) and is in the direct runner (`tests/test_arclink_hosted_api.py:6372-6375`). It proves canonical JSON equality, not raw byte identity. Docs still overclaim byte identity (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:295-296`; `docs/API_REFERENCE.md:375-378`; `docs/arclink/architecture.md:299-301`).
- CONFIRM: route-count freshness drift. GTB says 69 `_ROUTES` / 67 paths (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:289`); current `_ROUTES` includes the newer Academy routes (`python/arclink_hosted_api.py:3754-3825`, especially `:3759`, `:3791`) and the OpenAPI test requires every `_ROUTES` entry in the served spec (`tests/test_arclink_hosted_api.py:5450-5453`).
- CONFIRM: GAP-016 string in `GAPS.md` is stale. GAPS quotes `accepted_linked_resources_copy_to_owned_vault_or_workspace_only` (`GAPS.md:745-747`); code emits `accepted_linked_resources_writable_in_place_without_reshare_or_git_mutation` (`python/arclink_mcp_server.py:120`), matching GTB’s correction (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:541-545`).
- REFINE: `_NEXT_ACTION_RE` seam is alternation-equal, not byte-identical. GTB lists the alternation (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:81-83`); code adds regex boundaries/grouping (`python/arclink_surface_contract.py:41-43`).
- CONFIRM: GAP-008 nuance. There is no open `### GAP-008` header between GAP-007 and GAP-009 (`GAPS.md:469`, `GAPS.md:499`), but `GAP-008` is referenced as locally closed (`GAPS.md:1590`, `GAPS.md:2315`, `GAPS.md:2383`).
- REFINE: untracked-artifact risk. `DISSECT.md` is an untracked root artifact scoped to operator-upgrade (`DISSECT.md:1-6`), but public hygiene scans cached plus unignored untracked files via `git ls-files --cached --others --exclude-standard` (`tests/test_public_repo_hygiene.py:18-23`), so DISSECT is not invisible to that gate. `analyze_vuln.md` is ignored by `.gitignore` (`.gitignore:22-24`) and is excluded from that scan.

### New findings both Claude passes missed (severity + path:line)
- LOW: OpenAPI byte-identity drift is broader than the GTB: canonical docs also assert byte identity in `docs/API_REFERENCE.md:375-378` and `docs/arclink/architecture.md:299-301`, while the executable guard is canonical JSON equality only (`tests/test_arclink_hosted_api.py:5505-5507`).
- LOW: The artifact-hygiene mechanism was misstated: unignored untracked files are scanned (`tests/test_public_repo_hygiene.py:18-23`), but ignored scratch files such as `analyze_vuln.md` are deliberately excluded (`.gitignore:22-24`).
- No new HIGH/MED runtime TOCTOU, replay, nonce, lock, or secret-handling defect found inside CANON-32’s executed code paths; this piece is docs plus doc-truth/static-copy tests.

### Claude citations re-confirmed or corrected
- Re-confirmed: 84/44/9 docs are stale vs current modules/tables (`docs/arclink/architecture.md:18`, `docs/arclink/architecture.md:280-284`; `python/arclink_control.py:1686`, `python/arclink_control.py:1718`).
- Re-confirmed: GAP-016 live policy string is code-wins stale doc drift (`GAPS.md:745-747`; `python/arclink_mcp_server.py:120`).
- Corrected: OpenAPI content parity is not merely “path sets identical”; it is guarded by canonical JSON equality (`tests/test_arclink_hosted_api.py:5496-5507`). Raw byte identity remains unproved/false against the docs’ wording.
- Corrected: missing modules are 3, not 2: `arclink_operator_upgrade_host_runner`, `arclink_skill_enablement`, `arclink_upgrade_policy` (`python/arclink_operator_upgrade_host_runner.py:2`; `python/arclink_skill_enablement.py:2`; `python/arclink_upgrade_policy.py:2`).
- Corrected: product-matrix totals are executable-guarded and documented as locally guarded (`tests/test_documentation_truths.py:76-87`; `GAPS.md:589-596`).

### Residual disagreement with the Claude half (for final reconciliation)
- C53 is resolved against the Claude auditor: matrix totals are guarded; the real unguarded drift is architecture/GTB module and table counts.
- The CANON-32 MEDIUM OpenAPI risk should be downgraded/refined: no byte-diff test exists, but a canonical static-copy parity test does exist and passes.
- The piece should be OBJECT, not REJECT: the qualitative drift map is useful, but the test-coverage narrative cannot be trusted without these corrections.
<<<CODEX-VERDICT-END CANON-32>>>
