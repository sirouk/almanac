# CANON-32 — Documentation Corpus & Federation Provenance — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened every load-bearing
citation in code; re-derived all counts; attempted byte-reproduction of the
OpenAPI; read the full doc-truth test, not just the lines the record cites.

## VERDICT (one line)

**Record is DIRECTIONALLY CORRECT on the drift findings but contains at least one
hard FALSE central claim** — it asserts (in 3 places) that the product-matrix
totals are NOT row-summed/guarded by a test, when
`tests/test_documentation_truths.py:76-88` provably DOES sum the rows and assert
declared==actual. It also under-counts the undocumented modules (says 2,真 = 3),
mischaracterizes the gated-row test as a "PG-/policy anchor" check (it is a
language-keyword check), and mis-states the guard surface as "four doc-truth tests"
when `main()` runs 11. The headline drift numbers (87/45/10 vs 84/44/9), the
GAP-016 string drift, and the OpenAPI "no byte-parity test / not byte-reproducible"
findings all RE-CONFIRM in code. Net: **trustworthy on the conclusions, NOT
trustworthy on the test-coverage narrative** — its strongest RISK ("totals
unguarded") is partly self-contradicted by code it did not fully read.

---

## A. REFUTATIONS (claim → code → refuted?)

### A1. REFUTED — "the test does NOT sum per-row counts vs declared totals"
Record CODE-PATH-TRACE step 5 (line 146-148): "The test does **NOT** sum the
per-row counts and compare to the declared totals". Also OPEN-FOR-CODEX #3
(line 280-282): "`tests/test_documentation_truths.py` does NOT check this".
CODE: `tests/test_documentation_truths.py:76-88`
`test_product_matrix_totals_match_rows_and_statuses_are_known()`:
- `:77` `rows = _product_matrix_rows()`
- `:80` `statuses = Counter(status for _, _, status, _, _ in rows)`
- `:83` `actual_totals = {status: statuses.get(status,0) for status in PRODUCT_MATRIX_STATUSES}`
- `:84-86` `expect(_product_matrix_declared_totals() == actual_totals, ...)`
This is EXACTLY a row-sum-vs-declared-total assertion. **The record's claim is
FALSE.** The 121-row arithmetic self-consistency the record asks CODEX to verify is
already machine-guarded. (The drift the record DID find is module/table COUNTS,
which are genuinely unguarded — a different thing the record conflated.)

### A2. REFUTED (partial / under-count) — "2 modules missing from architecture.md"
Record OPEN-FOR-CODEX #2 (line 276-279) names only `operator_upgrade_host_runner`
and `skill_enablement` as missing, and asks to "verify there are not more."
CODE: `comm -23` of `git ls-files python/arclink_*.py` (87) vs the 84 modules
architecture.md enumerates yields THREE missing modules:
`arclink_operator_upgrade_host_runner`, `arclink_skill_enablement`, **and
`arclink_upgrade_policy`** (the third the record never names; tracked at
`python/arclink_upgrade_policy.py`, added in commits `9fdc844`/`9f458ef`/`63a42c8`,
absent from GTB §3 and from architecture.md's map). The record's enumeration is
INCOMPLETE — there is one more.

### A3. REFUTED (mischaracterization) — INPUT-CONTRACT #2 "PG-/policy anchor"
Record INPUT-CONTRACT #2 (line 52-55): "`:112-118` requires every
`proof-gated`/`policy-question` row to carry a PG-/policy anchor."
CODE: `tests/test_documentation_truths.py:112-123` does NOT check for a "PG-/policy
anchor". It checks that proof-gated rows contain one of the LANGUAGE keywords
`authori[sz]ation|external|gated|live|proof|prove|run only|sandbox` and that
policy-question rows contain `ask|choose|decision|disabled|operator|policy|
product-owned|question`. No `PG-` token is required. The record invented an anchor
requirement that is not in the code.

### A4. REFUTED (mis-count of guard surface) — "the four doc-truth tests"
Record INPUT-CONTRACT (line 63-64): "docs are read by humans and by the four
doc-truth tests above"; echoed in TOUCH POINTS and VERDICT.
CODE: `tests/test_documentation_truths.py` defines 11 test functions and `main()`
(`:323-339`) runs all 11, printing "PASS all 11 documentation truth tests". Plus
`tests/test_hermes_docs_sync.py` and `tests/test_public_repo_hygiene.py`. The
guard surface is ~13 doc tests, not four. The record's "four" understates and is
the same reading miss that produced A1.

### A5. NOT REFUTED (re-confirmed) — module count 87 vs doc 84
`git ls-files 'python/arclink_*.py'` = 87; `docs/arclink/architecture.md:18` and
`research/ARCLINK_GROUND_TRUTH_BRIEF.md:89` say 84; architecture.md enumerates
exactly 84 distinct `arclink_*.py` mentions. DRIFT confirmed. CODE WINS.

### A6. NOT REFUTED (re-confirmed) — table counts 45/10 vs 44/9
`grep CREATE TABLE IF NOT EXISTS arclink_ | sort -u` = 45;
`academy_` = 10. GTB §4 (`:239,251-270`) enumerates 44 + lists 9 academy
(`:241-245`); architecture.md `:280-284` copies 44/9. The 45th
`arclink_agent_skill_enablement` and 10th `academy_source_crawl_observations` are
present in code (`python/arclink_control.py`, 5 hits for the academy one) and
ABSENT from the GTB entirely (`grep -c` = 0 each). DRIFT confirmed.

### A7. NOT REFUTED (re-confirmed) — GAP-016 stale policy string
`GAPS.md:746` quotes `..._copy_to_owned_vault_or_workspace_only`; live code
`python/arclink_mcp_server.py:120`
`_LINKED_COPY_DUPLICATE_POLICY = "..._writable_in_place_without_reshare_or_git_mutation"`.
DRIFT confirmed. CODE WINS.

### A8. NOT REFUTED (re-confirmed) — OpenAPI: content parity, no byte-parity test,
not naively byte-reproducible
I loaded `python/arclink_hosted_api.py` correctly (the record's "70653-byte length"
guess was reached via a module-load that silently FAILED on first attempt — caveat
below) and re-derived:
- `build_arclink_openapi_spec()` (`:3689`) and committed
  `docs/openapi/arclink-v1.openapi.json` both have **71 paths**, `openapi 3.1.0`,
  and are **deep structurally identical (order-insensitive)** — stronger than the
  record's "path sets identical" wording.
- `json.dumps(gen, indent=2, sort_keys=True)+"\n"` is **70653 bytes (== committed
  length)** but NOT byte-equal: the committed file has SOME nested objects in
  insertion order (e.g. the host-fields object: `wireguard_private_ip`,
  `wireguard_private_cidr`, `wireguard_public_key`...) while the sorted dump orders
  them alphabetically. So the committed bytes are NOT reproducible by a uniform
  serialization → "byte-identical" (GTB `:295-296`) is NOT salvageable.
- NO test diffs committed vs generated. Only `tests/test_hermes_docs_sync.py:73`
  (existence) and `tests/test_arclink_hosted_api.py:5434-5455` (served-shape: every
  `_ROUTES` entry appears, version==3.1.0). The "keep the parity test" instruction
  references a test that does not exist. CONFIRMED.
NOTE: the record's own confidence note (self-check #2) flags this as medium — fair.

### A9. NOT REFUTED — route count 71/71 vs GTB "69/67"
`grep -cE '^\s*\("(GET|POST|...)"' python/arclink_hosted_api.py` = 71; generated
spec paths = 71; GTB `:289` says "69 `_ROUTES`, 67 unique". Freshness DRIFT
confirmed. CODE WINS.

### A10. NOT REFUTED — GAP-008 "absent" nuance
GTB `:524` "GAP-008 absent"; `grep -oE 'GAP-0[0-9][0-9]' GAPS.md | sort -u` =
GAP-001..GAP-034 (no `### GAP-008` ledger entry), but GAP-008 referenced 3× at
`GAPS.md:1590,2315,2383` as "closed locally / closed at the local contract level".
Record's "nuance drift" framing is accurate. (Side note: GTB `:526` separately says
the two header-level "closed locally" CALLOUTS are GAP-011 and GAP-025 — a
different sentence; no conflict with the record.)

### A11. NOT REFUTED — DISSECT.md / analyze_vuln.md untracked
`git ls-files` returns nothing for both; `git status` shows `?? DISSECT.md`;
`analyze_vuln.md` untracked. Sizes: DISSECT.md = 248147 bytes (record's "248 KB"
correct), analyze_vuln.md = 3308 bytes. `operator_upgrade_host_runner` appears 60×
in DISSECT.md but 0× in any TRACKED doc — record's "0 tracked docs" scoping holds.

---

## B. NEW GAPS (neither record nor prior docs flagged)

### B1. MEDIUM — record's headline RISK ("totals unguarded") is self-contradicting
The record's CODE-PATH-TRACE step 5 and OPEN-FOR-CODEX #3 assert the matrix totals
are unchecked; `tests/test_documentation_truths.py:76-88` checks them. A reader
acting on the record would re-implement a guard that already exists, OR distrust a
real guarantee. The actually-unguarded thing is the module/table COUNT in
architecture.md/GTB — which IS real and IS the record's better finding. The record
muddled "matrix totals" (guarded) with "module map counts" (unguarded).

### B2. LOW — third undocumented module `arclink_upgrade_policy`
See A2. Real tracked module, in 7 tracked docs (`README.md`, 5 `docs/arclink/*.md`,
`GAPS.md`) but NOT in architecture.md's authoritative module map nor GTB §3. The
"Canonical" map at `docs/arclink/architecture.md:18` is off by 3, not the implied 2.

### B3. LOW — schema test does a SUBSET check, not a count assertion
`tests/test_arclink_schema.py:41` `test_arclink_schema_creates_expected_tables...`
`:78 expect(expected <= names, ...)` — only asserts 27 named tables are a SUBSET of
actual `arclink_%` tables. It would NOT catch the 44→45 drift or a dropped table.
The record said "no test validates table counts" (true) but never mentioned this
test exists and is a subset-only guard — relevant for anyone trying to add a count
guard (it's the natural home).

### B4. INFO — record's "advanced to 2026-06-16" is loose
RISKS INFO line says codebase "advanced to 2026-06-16"; the latest commit in tree
is `63a42c8` dated 2026-06-12. The 06-16 is the audit date, not a code date. Minor,
non-load-bearing.

---

## C. SEAM MISMATCHES (cross-piece contracts the record marked both-ends-verified)

- **Seam → CANON-02 (OpenAPI artifact).** Record says "content MATCH (path sets
  identical), byte MATCH UNCONFIRMED". RE-VERIFIED BOTH ENDS: it is FULL deep
  content parity (stronger), and byte parity is provably NOT reproducible (mixed
  key ordering in nested objects). Record under-claims the content side and is
  correct on the byte side. No mismatch in the record's conclusion, but its
  "path sets identical" wording undersells verified deep-equality.
- **Seam → CANON-03 (surface-contract regex).** Record: `_NEXT_ACTION_RE` is
  "byte-identical between doc line 82-83 and `:41-43`". RE-VERIFIED: GTB
  `:82-83` prose lists the same alternation as
  `python/arclink_surface_contract.py:41-43`
  `Next|Use|Open|Run|Register|Complete|Send|Tap|Choose|Check|Retry|Operator|
  dashboard|checkout|proof|PG-[A-Z-]+`. MATCH holds. (Pedantic: GTB wraps the
  alternation across lines and omits the `\b...\b` and `(?:...)`; it is
  alternation-identical, not literally byte-identical, but semantically equal.)
- **Seam → CANON-01 (table inventory).** RE-VERIFIED both ends: the 45th/10th
  tables are in code, absent from GTB. MATCH with record's drift call.

---

## D. RISK RE-CALIBRATION

- Record RISK "MEDIUM — module/table map stale & unguarded": **UPHELD** (and
  slightly worse — 3 missing modules, not 2; `arclink_upgrade_policy` added).
- Record RISK "MEDIUM — byte-identical OpenAPI parity test fictional": **UPHELD**
  (byte-reproduction independently shown impossible under naive serialization).
- Record RISK "LOW — GAP-016 stale string": **UPHELD**.
- Record RISK "LOW — untracked artifacts": **UPHELD**.
- NEW: the record's own narrative defect (A1/A3/A4) is a MEDIUM credibility risk on
  the record itself — its central "totals unguarded" RISK rests on a misread test.

## OVERALL

Conclusions: SOUND. Drift findings: RE-CONFIRMED. But the record's
test-coverage/provenance narrative contains a hard false claim (A1) plus two
mischaracterizations (A3, A4) and an under-count (A2/B2). Treat the record's drift
TABLE as trustworthy; treat its "what is/ isn't guarded by tests" statements as
UNRELIABLE until corrected against `tests/test_documentation_truths.py:76-88`.
