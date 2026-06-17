# CANON-32 — Documentation Corpus & Federation Provenance — RECONCILED

Final adjudicator: Claude Opus 4.8 (1M). Method: every disputed point re-opened in
code by this adjudicator (Read / grep / live `build_arclink_openapi_spec()` run).
Code wins over any comment, name, or prior model claim.

## SIGN-OFFS

- **Codex (GPT-5.5 xhigh):** OBJECT(4) — "Drift conclusions mostly stand, but the
  Claude record/verifier are materially wrong about OpenAPI parity-test absence,
  product-matrix guarding, missing-module count, and untracked-artifact hygiene."
- **Claude adversarial verify:** "Conclusions SOUND; drift findings re-confirmed;
  test-coverage narrative UNRELIABLE (hard false A1 + mischaracterizations A3/A4 +
  under-count A2)."
- **Federation sign-off (this file): BOTH-MODEL-AGREED.** Every material point
  reconciles to one code-grounded truth. Codex and the Claude verifier independently
  converged on the same corrections; the original Claude record is the only party
  that was wrong, and on each wrong point the code decides against it. No standing
  disagreement survives code re-examination.

## NET VERDICT

The CANON-32 **drift map is correct and load-bearing**: docs say 84 modules / 44+9
tables; code is 87 / 45+10; the GAP-016 policy string in GAPS.md is stale; route
counts are stale (69/67 → 71/71); "byte-identical" OpenAPI wording is overclaimed in
THREE docs. All re-confirmed. **But the original Claude record's test-coverage
narrative is wrong on its strongest two claims and must be corrected:** (1) the
product-matrix totals ARE row-summed and guarded; (2) a real OpenAPI parity test
EXISTS and PASSES (canonical-JSON equality), so the spec CANNOT silently drift in
content. The Claude verifier caught (1); both Claude passes missed (2) — Codex caught
it. The genuinely unguarded thing is the architecture.md/GTB **module and table
COUNT**, which remains the piece's best finding.

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Disputed point | Winner | Deciding cite (re-opened by adjudicator) |
|---|---|---|---|
| 1 | Product-matrix totals are row-summed & guarded by a test (record said NOT) | **codex + claude-verifier** | `tests/test_documentation_truths.py:76-88` sums `Counter(status...)` and `expect(declared==actual)`. Record FALSE. |
| 2 | A real OpenAPI parity test exists (record/verifier said NONE exists) | **codex** | `tests/test_arclink_hosted_api.py:5496-5507` (`json.dumps(sort_keys=True)` equality); in runner `:6375`. BOTH Claude passes missed it. |
| 3 | OpenAPI is byte-identical to generated spec | **neither (docs overclaim)** | Live run: `json.dumps(gen,indent2[+nl][+sort])` != committed bytes (all False); canonical `sort_keys` == True. Bytes NOT reproducible; content/canonical parity TRUE. |
| 4 | "byte-identical" appears only in GTB | **codex** | Also `docs/API_REFERENCE.md:373-378` and `docs/arclink/architecture.md:297-301` ("kept byte-identical to code by a parity test"). Overclaim is 3-doc-wide. |
| 5 | Missing-from-architecture.md module count (record: 2; off-by-3 in body) | **codex + claude-verifier** | `git ls-files python/arclink_*.py`=87; `grep -c` in `docs/arclink/architecture.md`=0 for `arclink_operator_upgrade_host_runner`, `arclink_skill_enablement`, AND `arclink_upgrade_policy` (`python/arclink_upgrade_policy.py`). THREE missing. |
| 6 | main() runs "four doc-truth tests" | **codex + claude-verifier** | `tests/test_documentation_truths.py:324-336` runs 11; prints "PASS all 11". Record's "four" understates. |
| 7 | Gated-row guard is "PG-/policy anchor" check | **codex + claude-verifier (REFINE)** | `tests/test_documentation_truths.py:112-123` is a language-keyword regex (`authori[sz]ation\|external\|gated\|live\|proof...` / `ask\|choose\|decision...`). No `PG-` token required. |
| 8 | DISSECT.md invisible to public-repo hygiene gate | **codex** | `tests/test_public_repo_hygiene.py:18-23` scans `git ls-files --cached --others --exclude-standard`; `git ls-files --others...` LISTS `DISSECT.md`. It IS scanned. Record's "invisible" FALSE. |
| 9 | analyze_vuln.md hygiene status | **codex** | `.gitignore:24` `*_vuln.md` ignores it; `git check-ignore` confirms; excluded from `--exclude-standard` scan. (So the only invisibility is the deliberately-ignored scratch file.) |
| 10 | Module count 87 vs doc 84 | **claude (CONFIRM)** | `git ls-files python/arclink_*.py`=87 vs `architecture.md:18`/`GTB:89`=84. CODE WINS. |
| 11 | Table counts 45/10 vs 44/9 | **claude (CONFIRM)** | distinct `CREATE TABLE IF NOT EXISTS arclink_`=45, `academy_`=10; `python/arclink_control.py:1686` (`academy_source_crawl_observations`), `:1718` (`arclink_agent_skill_enablement`). CODE WINS. |
| 12 | GAP-016 stale policy string | **claude (CONFIRM)** | `GAPS.md:745-747` quotes `..._copy_to_owned_vault_or_workspace_only`; `python/arclink_mcp_server.py:120` emits `..._writable_in_place_without_reshare_or_git_mutation`. CODE WINS. |
| 13 | Route count 71/71 vs GTB 69/67 | **claude (CONFIRM)** | `grep -cE '^\s*\("(GET\|POST...)"' python/arclink_hosted_api.py`=71; live spec paths=71; `GTB:289`="69/67". Freshness DRIFT. CODE WINS. |
| 14 | GAP-008 "absent" nuance | **claude + codex (CONFIRM)** | No `### GAP-008` header (`GAPS.md` jumps GAP-007 `:469` → GAP-009 `:499`); referenced 3× as locally closed `:1590,2315,2383`. Nuance accurate. |
| 15 | _NEXT_ACTION_RE seam "byte-identical" | **codex + claude-verifier (REFINE)** | `python/arclink_surface_contract.py:41-43` adds `\b...\b` + `(?:...)` vs `GTB:81-83` bare alternation. Alternation-EQUAL, not byte-identical. |
| 16 | DOC_STATUS labels stale map "Canonical" | **claude (CONFIRM)** | `docs/DOC_STATUS.md:26` "Canonical / Current module map"; map is provably stale (pts 5,10,11). Miscclassification stands. |

## CODEX CONFIRM ITEMS (ratified, both models already agreed)

- Canonical module/table map stale & unguarded — ratified (pts 5,10,11,16).
- Route-count freshness drift — ratified (pt 13).
- GAP-016 stale string — ratified (pt 12).
- GAP-008 nuance — ratified (pt 14).

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

**CONFIRMED (re-verified true in code → net-new federation risk):**

- **[LOW] Byte-identity overclaim is 3-doc-wide, not GTB-only.** `docs/API_REFERENCE.md:373-378`
  and `docs/arclink/architecture.md:297-301` both assert "byte-identical," while the
  executable guard (`tests/test_arclink_hosted_api.py:5505-5507`) is canonical-JSON
  equality only. Adjudicator-verified: live run shows raw bytes NOT reproducible;
  canonical equality True. NET-NEW (record only cited GTB).
- **[INFO→LOW] Hygiene mechanism was misstated.** Untracked-but-unignored files ARE
  scanned (`tests/test_public_repo_hygiene.py:18-23`; `DISSECT.md` appears in the
  `--others --exclude-standard` listing); only `.gitignore`-matched scratch files
  (`analyze_vuln.md` via `.gitignore:24` `*_vuln.md`) are excluded. This REJECTS the
  record's "untracked artifacts invisible to public-repo hygiene" risk as stated and
  REPLACES it with the accurate mechanism.

**REJECTED:** none — both Codex new findings hold in code.

**Codex non-finding ratified:** no new HIGH/MED runtime TOCTOU/replay/nonce/lock/secret
defect inside CANON-32's executed paths. Adjudicator agrees — this piece is docs +
doc-truth/static-copy tests; the executed code (`test_documentation_truths.py`,
`test_openapi_spec_matches_static_copy`, `test_public_repo_hygiene.py`) holds no such
surface.

## SEVERITY CHANGES (code-supported only)

| Risk | From | To | Deciding cite |
|---|---|---|---|
| "GTB byte-identical OpenAPI parity test is fictional / spec could silently drift and nothing would fail" | MEDIUM | **LOW** | A real parity test exists and PASSES: `tests/test_arclink_hosted_api.py:5496-5507` (canonical `sort_keys` equality, adjudicator-run = True). Spec CANNOT silently drift in content. Residual issue is only the literal "byte-identical" wording in 3 docs (cosmetic/doc-accuracy). |
| "Untracked Federation artifacts invisible to public-repo hygiene" | LOW | **INFO** | `tests/test_public_repo_hygiene.py:18-23` DOES scan unignored untracked files (`DISSECT.md` is in scope); only `.gitignore:24`-matched `analyze_vuln.md` is excluded by design. Not an invisibility gap. |
| "Canonical-labeled module/table map stale & unguarded" | MEDIUM | **MEDIUM (held; one more module)** | `docs/arclink/architecture.md:18,280`; missing modules are 3 (`arclink_upgrade_policy` added) per `python/arclink_upgrade_policy.py` absent from map. Severity unchanged; scope slightly worse. |

Unchanged: GAP-016 stale string = LOW (`GAPS.md:745-747` vs `arclink_mcp_server.py:120`).

## STANDING DISAGREEMENTS

**None.** Every disputed point was settled from code by this adjudicator. The original
Claude record was wrong on test-coverage (A1/A2/A4 + the parity-test miss); the Claude
verifier and Codex independently converged on the corrected truths; code confirms the
corrected side in each case. No point requires evidence outside the code to resolve.

## FINAL BOTH-MODEL VERDICT

**Provably does its job, with a CORRECTED test-coverage narrative.** The corpus's
qualitative drift map is accurate and useful and its honesty discipline is real. The
quantitative spine (module count 84→87, tables 44/9→45/10, routes 69/67→71/71, GAP-016
string) is genuinely stale vs code and the architecture.md/GTB COUNTS are unguarded —
the piece's best finding. BUT, contrary to the original Claude record: (a) the
product-matrix totals ARE machine-guarded by a row-sum assertion
(`test_documentation_truths.py:76-88`), and (b) a real OpenAPI parity test EXISTS and
PASSES (`test_arclink_hosted_api.py:5496-5507`, canonical-JSON equality) — so the spec
cannot silently drift in content; only the literal word "byte-identical" is overclaimed
across `GTB:295-296`, `docs/API_REFERENCE.md:376`, and `docs/arclink/architecture.md:301`.
The "totals unguarded" and "parity test fictional" MEDIUM framings are downgraded to
reflect the guards that exist. **FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.**

---

<!-- CANON-COVERAGE-REFRESH:START -->
## Coverage refresh status

> Refreshed during the repair-ledger pass. CANON-32 now explicitly owns the canon and
> provenance artifacts themselves: `CANON.md`, `DISSECT.md`, `research/canon/COVERAGE_MATRIX.md`,
> `research/canon/CODEX_OVERLAY_BRIEF.md`, `research/canon/run_codex_overlay.sh`,
> `research/canon/run_codex_fix.sh`, and the `research/canon/{sections,verify,codex,reconciled,fixes}/`
> report trees.

- Current workspace matrix: 766 / 766 corpus rows assigned, including 762 tracked rows and
  4 active untracked, non-ignored repair-workspace rows.
- Ownership decision: canon/provenance/repair artifacts are documentation-corpus artifacts,
  assigned to CANON-32, not product/runtime surfaces.
- Ignored local/operator scratch files such as `.env.live.example` and `analyze_vuln.md`
  remain outside the public corpus matrix because `--exclude-standard` omits them.
<!-- CANON-COVERAGE-REFRESH:END -->
