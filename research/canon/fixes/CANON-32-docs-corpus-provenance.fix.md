<<<CODEX-FIX-START CANON-32>>>
## CANON-32 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: GAPS.md, docs/API_REFERENCE.md, docs/arclink/architecture.md, research/ARCLINK_GROUND_TRUTH_BRIEF.md, tests/test_documentation_truths.py
TESTS: 5 files run: 4 pass / 1 NEEDS-REVIEW (`tests/test_public_repo_hygiene.py` fails on pre-existing `CANON.md` + `tests/test_arclink_evidence.py` provider-name hits outside my changed files)

### Fixed (severity — what — path:line)
- MEDIUM — canonical module map now reflects 87 modules and includes `arclink_operator_upgrade_host_runner`, `arclink_upgrade_policy`, and `arclink_skill_enablement` — `docs/arclink/architecture.md:18`, `docs/arclink/architecture.md:75`, `docs/arclink/architecture.md:79`, `docs/arclink/architecture.md:166`; `research/ARCLINK_GROUND_TRUTH_BRIEF.md:91`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:143`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:148`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:220`
- MEDIUM — canonical table counts/lists now reflect 45 `arclink_*` tables and 10 `academy_*` tables, including `arclink_agent_skill_enablement` and `academy_source_crawl_observations` — `docs/arclink/architecture.md:283`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:244`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:246`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:256`
- LOW — GTB hosted API route counts updated from stale 69/67 wording to 71 `_ROUTES`, 69 hosted suffixes, 71 OpenAPI path objects — `research/ARCLINK_GROUND_TRUTH_BRIEF.md:293`
- LOW — OpenAPI “byte-identical” overclaim replaced with canonical JSON/content parity wording in all current canonical docs — `docs/API_REFERENCE.md:375`, `docs/arclink/architecture.md:303`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:300`
- LOW — GAP-016 stale `copy_duplicate_policy` string replaced with live MCP constant and detail — `GAPS.md:745`, `research/ARCLINK_GROUND_TRUTH_BRIEF.md:548`
- INFO — GAP-008 wording clarified as no open `### GAP-008` header, with closed local references still present — `research/ARCLINK_GROUND_TRUTH_BRIEF.md:530`
- MEDIUM/LOW guards — added regression coverage for module inventory, table inventory, route counts, OpenAPI wording, and GAP-016 policy string — `tests/test_documentation_truths.py:158`, `tests/test_documentation_truths.py:173`, `tests/test_documentation_truths.py:201`, `tests/test_documentation_truths.py:220`, `tests/test_documentation_truths.py:237`

### Skipped (risk-accepted / standing / out-of-scope — why)
- `research/canon/**`, `CANON.md`, and `DISSECT.md` — immutable SPEC per instruction.
- Historical `research/ground-truth/*` snapshot drift — left unchanged because `docs/DOC_STATUS.md` classifies `research/*` as Historical; current canonical truth now lives in the refreshed GTB plus guarded docs.
- Public-hygiene “untracked files invisible” risk — skipped as refuted by reconciliation; unignored untracked files are already scanned, ignored scratch files remain excluded by design.

### NEEDS-DECISION (ambiguous; left for human)
- `python3 tests/test_public_repo_hygiene.py` currently fails on provider-name hits in immutable/current spec text (`CANON.md`) and unrelated `tests/test_arclink_evidence.py`. Fixing that requires a hygiene policy/allowlist decision outside CANON-32’s repair scope.

### Cross-piece edits made (if any) + tests added
- Cross-piece edits: none.
- Tests added: new guards in `tests/test_documentation_truths.py`.
- Passing verification: `python3 tests/test_documentation_truths.py`; `python3 tests/test_arclink_schema.py`; `python3 tests/test_arclink_mcp_schemas.py`; `python3 tests/test_arclink_hosted_api.py`; `git diff --check`.
<<<CODEX-FIX-END CANON-32>>>
