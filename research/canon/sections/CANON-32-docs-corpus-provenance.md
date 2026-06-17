# CANON-32 — Documentation Corpus & Federation Provenance

## PIECE

This piece audits the ArcLink **documentation corpus as a subject**: what each
major doc claims to be authoritative about, which docs are STALE or drift from
code, and how the corpus's own provenance machinery (the Ground Truth Brief, the
`research/ground-truth/` records, `docs/DOC_STATUS.md`, the GAP-* ledger, and the
product-reality matrix) reconciles itself with the real code. It does **not**
re-audit subsystem code; it audits the **docs about** that code against the
per-piece ground truth.

Files owned (all tracked unless noted), enumerated via `git ls-files`:
- **Top-level docs (10 tracked):** `AGENTS.md`, `README.md`, `USER_JOURNEY.md`,
  `GAPS.md`, `mission_status.md`, `IMPLEMENTATION_PLAN.md`,
  `FUTURE_SHARED_ARCLINK.md`, `SECURITY.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`.
- **`docs/**` (40 tracked):** `docs/API_REFERENCE.md`, `docs/DOC_STATUS.md`,
  `docs/org-profile.md`, `docs/docker.md`, `docs/openapi/arclink-v1.openapi.json`,
  31 `docs/arclink/*.md` canonical/runbook/brief docs (+ `brand/ArcLink Brandkit.pdf`,
  `hermes-qmd-config.yaml`), and misc (`docs/curator-onboarding-transcript-notes.md`,
  `docs/managed-memory-stubs-example.md`).
- **`research/**` (67 tracked):** the central anchor `ARCLINK_GROUND_TRUTH_BRIEF.md`,
  14 `research/ground-truth/*.md` subsystem-truth records, 32 `RALPHIE_*` steering
  briefs, audit/matrix docs (`PRODUCT_REALITY_MATRIX.md`, `COVERAGE_MATRIX.md`,
  `CONTRACT_AUDIT_20260510.md`, `ARCLINK_ARCHITECTURE_MAP.md`, `CODEBASE_MAP.md`,
  etc.), and seed drafts.
- **Two UNTRACKED files listed in my scope:** `DISSECT.md` and `analyze_vuln.md`
  exist on disk but are NOT git-tracked (`git ls-files` returns nothing; `git
  status` shows `?? DISSECT.md` and `analyze_vuln.md` is untracked). They are
  prior Federation artifacts, not part of the canonical corpus.

What this piece "does": it is the corpus's reconciliation layer. It does no
runtime work; its job is met when every authoritative-claim doc agrees with code,
and when stale docs are explicitly flagged. The verdict here is therefore about
**doc-vs-code truth**, not program behavior.

## INPUT CONTRACT (code-verified)

The documentation corpus has no `def`/signature input contract; its "inputs" are
the code facts the docs claim to describe, plus the small set of **machine-checked**
doc contracts. The real, executable input contracts touching this piece are:

1. **Product-reality-matrix total declaration** — `tests/test_documentation_truths.py:40-44`
   reads `research/PRODUCT_REALITY_MATRIX.md`, regex-parses the line
   `Current row totals: (?P<totals>.*?`policy-question`)\.` and requires it to
   exist (`expect(bool(match), ...)`). Input shape: a markdown line of the form
   `N \`status\`` tokens. The matrix declares
   `101 \`real\`, 0 \`partial\`, 0 \`gap\`, 15 \`proof-gated\`, and 5 \`policy-question\``
   (`research/PRODUCT_REALITY_MATRIX.md:19`). Sum = 121 rows, matching GTB §6
   (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:524-526`).
2. **Per-row status vocabulary** — `tests/test_documentation_truths.py:10`
   restricts statuses to `{"real","partial","gap","proof-gated","policy-question"}`;
   `:112-118` requires every `proof-gated`/`policy-question` row to carry a PG-/policy
   anchor. Input shape: `| claim | status | source | note |` table rows.
3. **Brief assertions** — `tests/test_documentation_truths.py:189-190` requires the
   literal strings `"live workspace verification stays proof-gated"` and
   `"live runtime\n  access stays proof-gated"` to appear in a brief doc. This is the
   only test that pins specific brief prose.
4. **Public-repo hygiene allowlist** — `tests/test_public_repo_hygiene.py:92` lists
   `docs/openapi/arclink-v1.openapi.json` as an allowed-to-publish path.

Who may "call": no caller — docs are read by humans and by the four doc-truth tests
above. There is **no test** that validates the architecture.md module/table counts,
the DOC_STATUS classifications, or byte-parity of the committed OpenAPI spec
(see RISKS).

## OUTPUT CONTRACT (code-verified)

The corpus's "outputs" are authoritative claims. The load-bearing ones, and their
code-verified truth:

- **GTB §3 module count = 84** (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:89`,
  `docs/arclink/architecture.md:18`). **CODE: 87** `python/arclink_*.py`
  (`git ls-files 'python/arclink_*.py' | wc -l` = 87). **DRIFT.**
- **GTB §4 / architecture.md table counts = 44 `arclink_*` + 9 `academy_*`**
  (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:239,241`; `docs/arclink/architecture.md:280-284`).
  **CODE: 45 `arclink_*` + 10 `academy_*`** (`grep -c 'CREATE TABLE IF NOT EXISTS
  arclink_'` over `python/arclink_control.py` distinct = 45; `academy_` distinct = 10).
  **DRIFT (both off by one).**
- **GTB §6 GAP range = GAP-001..GAP-034, "GAP-008 absent"**
  (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:524`). **CODE/DOC: GAPS.md** highest is
  GAP-034 (`grep -oE 'GAP-0[0-9][0-9]' GAPS.md | sort -u | tail`); GAP-008 *is*
  referenced 3× as "closed locally" (`GAPS.md:1590,2315,2383`). "Absent" is true only
  in the narrow sense of "no open `### GAP-008` ledger entry"; the identifier exists.
  **PARTIAL DRIFT (nuance).**
- **GTB §5.1 OpenAPI = "byte-identical to the code-generated spec"**
  (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:295-296`). **CODE: content-parity TRUE,
  byte-parity UNVERIFIABLE/false under naive serialization.** Generated
  `build_arclink_openapi_spec()` (`python/arclink_hosted_api.py:3689`) and the
  committed `docs/openapi/arclink-v1.openapi.json` both expose **71 paths**, identical
  path sets (diff = ∅), `openapi: 3.1.0`. But raw byte-equality under
  `json.dumps(..., indent=2[, sort_keys])` is **False** (same 70653-byte length →
  ordering/whitespace differs from my guesses). There is **NO test** that diffs the
  committed file against generated output (only existence checks at
  `tests/test_hermes_docs_sync.py:73` and a served-spec sanity check at
  `tests/test_arclink_hosted_api.py:5434-5455`). **DRIFT: "byte-identical" + "keep the
  parity test" overstates — there is no enforcing parity test.**
- **GTB §5.1 route count = "69 _ROUTES entries, 67 unique paths"**
  (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:289`). **CODE: 71 route entries, 71 OpenAPI
  paths** (`grep -cE '^\s*\("(GET|POST|...)"' arclink_hosted_api.py` = 71; generated
  spec paths = 71). **DRIFT (freshness; routes grew since GTB authored 2026-05-30).**
- **GAP-016 policy string** quoted by `GAPS.md:746` =
  `accepted_linked_resources_copy_to_owned_vault_or_workspace_only`. **CODE emits**
  `accepted_linked_resources_writable_in_place_without_reshare_or_git_mutation`
  (`python/arclink_mcp_server.py:120`). **DRIFT — GTB §6/§8 flagged this; the stale
  string is STILL in GAPS.md.**

Side effects / writes: this piece writes nothing at runtime. Its only "write" is the
human edit of these markdown files; truth is enforced (weakly) by the four
doc-truth tests.

## TOUCH POINTS

- **Env vars:** none read by the corpus itself. Docs *describe* env vars; the GTB
  §2 `_NEXT_ACTION_RE` / vocabulary mirror real code constants (verified:
  `python/arclink_surface_contract.py:41-43` regex is character-identical to GTB
  lines 82-83; `_CAPTAIN_FORBIDDEN_PATTERNS` at `:34-39`).
- **DB tables:** none read/written by docs. Docs *enumerate* tables; the canonical
  count lives in `python/arclink_control.py` DDL (`CREATE TABLE IF NOT EXISTS ...`).
- **Files/paths:** `tests/test_documentation_truths.py` reads
  `research/PRODUCT_REALITY_MATRIX.md` and a brief; `tests/test_hermes_docs_sync.py`
  syncs `docs/**` into a vault and asserts `docs/openapi/arclink-v1.openapi.json`
  exists (`:73`); `tests/test_public_repo_hygiene.py:92` allowlists the OpenAPI file.
- **Secrets handling:** the corpus is secret-free by policy (GTB §9.1,
  `research/ARCLINK_GROUND_TRUTH_BRIEF.md:689`). `tests/test_public_repo_hygiene.py`
  is the gate that keeps it so. The surface-contract secret regexes
  (`python/arclink_surface_contract.py:16-26`) enforce no-secret rendering on
  *product copy*, not on docs.
- **No sockets/ports/subprocess/locks/external services** are owned by this piece.

## CODE-PATH TRACE

End-to-end dataflow for the corpus's one machine-checked output (the product matrix
total, which is the only doc claim with an executable contract):

1. `research/PRODUCT_REALITY_MATRIX.md:19` declares
   `Current row totals: 101 \`real\`, 0 \`partial\`, 0 \`gap\`, 15 \`proof-gated\`,
   and 5 \`policy-question\`.`
2. `tests/test_documentation_truths.py:40` opens that file, `:41-44` regex-extracts
   the totals substring up to `` `policy-question` `` and `expect`s a match.
3. `:45` parses `(\d+)\s+\`([^`]+)\`` into a dict
   `{real:101, partial:0, gap:0, proof-gated:15, policy-question:5}`.
4. The per-row scan (`:108-134`) walks the matrix table, validates each status is in
   the allowed set, and that proof-gated/policy-question rows carry an anchor.
5. The test does **NOT** sum the per-row counts and compare to the declared totals,
   and does **NOT** cross-check against the real module count — so a stale total or a
   miscounted module map passes silently (RISK).
6. GTB §6 (`:524-526`) restates the same 121-row totals as the SSOT, closing the
   provenance loop: matrix → GTB → docs all cite the same numbers — which are
   *internally consistent* even where one of them (module/table counts) is
   *externally stale vs code*.

Second trace (provenance chain for a STALE claim, architecture.md module count):

1. `research/ground-truth/*.md` (14 records, 2026-05-30) feed the GTB.
2. GTB §3 (`:87-93`) declares "**84** `python/arclink_*.py`" as the authoritative
   inventory and tells every doc to cite it.
3. `docs/arclink/architecture.md:18,280` copies the 84/44/9 figures.
4. `docs/DOC_STATUS.md:26` classifies architecture.md as **Canonical / "Current
   module map"**.
5. Code reality: `git ls-files 'python/arclink_*.py'` = **87**; DDL = 45 + 10.
6. The newest module, `python/arclink_operator_upgrade_host_runner.py`, was added
   **2026-06-12** (commit `63a42c8`), **after** the GTB/architecture.md were authored,
   and appears in **0** tracked docs (`grep -rl operator_upgrade_host_runner docs/
   research/RALPHIE* README.md AGENTS.md` → none). The drift is unguarded by any test.

## CROSS-PIECE CONTRACTS (both ends verified)

This piece's seams are doc-claims-about-other-pieces. For each, I opened BOTH the doc
(producer of the claim) and the code (the adjacent piece) and checked the bytes/shape:

- **Seam → CANON-01 (Control Plane & Schema): table inventory.** Doc producer:
  `research/ARCLINK_GROUND_TRUTH_BRIEF.md:251-270` + `docs/arclink/architecture.md:280`.
  Code consumer/source: `python/arclink_control.py` `CREATE TABLE IF NOT EXISTS`
  statements. Contract = exact table-name set + count. **BOTH ENDS VERIFIED: drift.**
  Code has `arclink_agent_skill_enablement` (the 45th) and `academy_source_crawl_observations`
  (the 10th); neither appears in GTB §4's enumerated lists.
- **Seam → CANON-03 (Surface Contract): vocabulary + next-action regex.** Doc
  producer: GTB §2 (`:49,81-83`). Code consumer: `python/arclink_surface_contract.py:34-43`.
  Contract = `_CAPTAIN_FORBIDDEN_PATTERNS` terms + `_NEXT_ACTION_RE` alternation.
  **BOTH ENDS VERIFIED: MATCH** — the regex `(?:Next|Use|Open|...|PG-[A-Z-]+)` is
  byte-identical between doc line 82-83 and `:41-43`.
- **Seam → CANON-02 (Hosted API): OpenAPI artifact.** Doc producer:
  `docs/openapi/arclink-v1.openapi.json` (committed, 71 paths). Code source:
  `build_arclink_openapi_spec()` (`python/arclink_hosted_api.py:3689`), served at
  `/api/v1/openapi.json` (`:3825,4160-4161`). Contract = identical path set + schema.
  **BOTH ENDS VERIFIED: content MATCH (path sets identical, version 3.1.0), byte
  MATCH UNCONFIRMED** (no diff test; GTB's "byte-identical" is content-true,
  serialization-unverified).
- **Seam → CANON-15 (Operator Upgrade Pipeline): DISSECT.md.** `DISSECT.md` (untracked)
  is a prior Federation dissection scoped ONLY to the operator-upgrade pipeline
  (`DISSECT.md:1` "ArcLink Operator-Upgrade Pipeline, Federated Code-Path Dissection";
  claims 8 pieces audited by Opus 4.8 + GPT-5.5). Contract = it covers CANON-15's
  subject, not the corpus. **BOTH ENDS: it is NOT a corpus-wide canon; it is an
  adjacent-piece artifact that happens to live at repo root and is untracked.**
- **Seam → CANON-07/20 (Billing/Sharing): GAP-016 string.** Doc producer:
  `GAPS.md:746`. Code source: `python/arclink_mcp_server.py:120`. Contract = the exact
  `copy_duplicate_policy` string. **BOTH ENDS VERIFIED: DRIFT** (GAPS.md quotes the old
  string; code emits the new one).

## CODE vs COMMENT/DOC/NAME DRIFT

1. **`research/ARCLINK_GROUND_TRUTH_BRIEF.md:89` + `docs/arclink/architecture.md:18`:
   "84 modules"** — CODE = 87. Off by 3. Driven (at least) by post-GTB additions incl.
   `arclink_operator_upgrade_host_runner.py` (commit `63a42c8`, 2026-06-12). **CODE WINS.**
2. **`research/ARCLINK_GROUND_TRUTH_BRIEF.md:239` + `docs/arclink/architecture.md:280`:
   "44 arclink_* tables"** — CODE = 45 (missing `arclink_agent_skill_enablement`,
   owned by CANON-19's `arclink_skill_enablement.py`). **CODE WINS.**
3. **`research/ARCLINK_GROUND_TRUTH_BRIEF.md:241-245` + `architecture.md:281-284`:
   "9 academy_* tables"** — CODE = 10 (missing `academy_source_crawl_observations`).
   **CODE WINS.**
4. **`docs/DOC_STATUS.md:26` classifies `architecture.md` as "Canonical / Current
   module map"** — but the module map is provably stale (items 1-3). A doc labeled
   *Canonical* that drifts from code; DOC_STATUS has a `Stale` label (`:15`) it should
   apply. **MISCLASSIFICATION.**
5. **`GAPS.md:746` GAP-016 policy string** is the pre-change value; live code
   (`arclink_mcp_server.py:120`) emits the new value. GTB §6 (`:542-545`) and §8 (`:683`
   region) both flagged this as "STALE, use the current string" — yet it was never
   fixed in GAPS.md. **CODE WINS; GTB's own correction was not propagated.**
6. **`research/ARCLINK_GROUND_TRUTH_BRIEF.md:295-296`: OpenAPI "byte-identical… Keep
   the parity test"** — content-parity holds (71/71 paths), but **no byte-diff parity
   test exists** in `tests/`; the only checks are existence + served-shape. The named
   "parity test" is not real. **DOC OVERSTATES.**
7. **`research/ARCLINK_GROUND_TRUTH_BRIEF.md:289`: "69 _ROUTES / 67 paths"** — CODE =
   71/71. **CODE WINS (freshness).**
8. **`research/ARCLINK_GROUND_TRUTH_BRIEF.md:524`: "GAP-008 absent"** — GAP-008 is
   referenced 3× as "closed locally" in GAPS.md (`:1590,2315,2383`). "Absent" is only
   true for "no open ledger entry"; the identifier is alive. **NUANCE DRIFT.**
9. **MEMORY.md (user memory, not a tracked doc) "84 modules"** — same 84 figure as GTB;
   now stale at 87. Out of repo-file scope but worth noting as the figure's origin.

## ADVERSARIAL SELF-CHECK

Claims I am least sure of, and what would falsify each:

1. **"87 is the right module count; 84 is wrong."** Falsifier: if any of the 87
   `arclink_*.py` are vendored/test-only shims the GTB intentionally excluded. I
   counted `git ls-files 'python/arclink_*.py'` = 87 (all under `python/`, all
   tracked). The GTB itself says "84 (includes helpers/legacy)" — so it was a full
   count at authoring time; the delta is genuine new modules, not a definitional
   difference. Confidence: high.
2. **"OpenAPI is content-identical but not byte-identical."** Falsifier: the repo may
   regenerate with a specific `json.dumps` signature (e.g. a custom encoder or trailing
   newline) that *does* reproduce the committed bytes — I tried 3 common forms, all
   False, but did not exhaustively search for the canonical generator invocation. The
   *content* parity (71 identical paths, same version) is firmly verified; only the
   "byte-identical" word and the "parity test exists" claim are challenged. Confidence:
   medium-high on "no enforcing test", medium on "not byte-reproducible".
3. **"`arclink_agent_skill_enablement` and `academy_source_crawl_observations` are the
   two extra tables."** Falsifier: a renamed/dropped table elsewhere could make the net
   count coincidental. I diffed the code DDL set against GTB §4's enumerated names and
   these two were the only `arclink_*`/`academy_*` names present in code but absent
   from the brief's lists; counts (45/10) corroborate. Confidence: high.
4. **"DISSECT.md and analyze_vuln.md are not part of the canonical corpus."** Falsifier:
   they could be intentionally-staged untracked drafts about to be committed. They are
   untracked today (`git ls-files` empty; `git status` `??`); DISSECT.md is scoped to
   one subsystem; analyze_vuln.md is a single-function TOCTOU note. Treating them as
   provenance artifacts rather than canon is defensible. Confidence: high on tracking
   status, medium on intent.
5. **"No test guards the architecture.md module/table counts."** Falsifier: a test in a
   file I didn't grep could assert `len(modules)==87`. I grepped
   `tests/test_documentation_truths.py` for `architecture.md|84|87` (none) and the
   doc-truth test only validates the matrix-total *string* and per-row anchors.
   Confidence: high that the count is unguarded.

## OPEN FOR CODEX FEDERATION

Worth an independent GPT-5.5 cross-check:

1. **Exact OpenAPI byte-reproduction.** Find the canonical generator invocation (script
   or test) that is *supposed* to produce `docs/openapi/arclink-v1.openapi.json` and
   confirm whether the committed bytes are reproducible at all. If yes, the GTB
   "byte-identical" claim is salvageable; if no, it is dead text. (Generator:
   `build_arclink_openapi_spec`, `python/arclink_hosted_api.py:3689`.)
2. **Full module-map reconciliation.** Independently diff `git ls-files
   'python/arclink_*.py'` (87) against architecture.md's 84 listed rows and GTB §3, and
   enumerate every missing module (I confirmed `operator_upgrade_host_runner`,
   `skill_enablement` missing from architecture.md; verify there are not more).
3. **Whether the 121-row product matrix totals are arithmetically self-consistent**
   (per-row counts == declared 101/0/0/15/5) — `tests/test_documentation_truths.py`
   does NOT check this, so the declared total could itself drift from the table body.
4. **GAP ledger completeness:** confirm GAPS.md actually defines GAP-001..GAP-034 with
   GAP-008 having no open entry, and that no doc resurrects a closed gap or claims an
   open one closed (GTB §9.7, `:705-707`).

## RISKS (severity-ranked, code-cited)

- **MEDIUM — Canonical-labeled module/table map is stale and unguarded.**
  `docs/arclink/architecture.md:18,280` claim 84/44/9; code is 87/45/10;
  `docs/DOC_STATUS.md:26` still labels it "Canonical / Current module map." No test
  catches it (`tests/test_documentation_truths.py` has no count assertion). A reader
  trusting the labeled-Canonical map gets wrong figures and misses
  `operator_upgrade_host_runner`/`skill_enablement`/`agent_skill_enablement`/
  `academy_source_crawl_observations`.
- **MEDIUM — GTB "byte-identical OpenAPI parity test" is fictional.**
  `research/ARCLINK_GROUND_TRUTH_BRIEF.md:295-296` instructs maintainers to "keep the
  parity test," but no test diffs the committed `docs/openapi/arclink-v1.openapi.json`
  against `build_arclink_openapi_spec()` (`python/arclink_hosted_api.py:3689`). The
  committed spec could silently drift out of byte-parity (content parity currently
  holds: 71/71 paths) and nothing would fail.
- **LOW — GAP-016 stale policy string persists.** `GAPS.md:746` quotes the old
  `copy_duplicate_policy` value; code emits the new one
  (`python/arclink_mcp_server.py:120`). GTB flagged it and it was never fixed; an
  operator citing GAPS.md verbatim mis-states the live policy.
- **LOW — Untracked Federation artifacts at repo root.** `DISSECT.md` (248 KB) and
  `analyze_vuln.md` are untracked (`git status` `??`/untracked) yet listed as
  corpus-scope files. Untracked docs are invisible to public-repo hygiene
  (`tests/test_public_repo_hygiene.py`) and DOC_STATUS; their provenance/secret-safety
  is unaudited by the corpus gates.
- **INFO — GTB freshness boundary.** The GTB is dated 2026-05-30
  (`research/ARCLINK_GROUND_TRUTH_BRIEF.md:3`); the codebase advanced to 2026-06-16.
  Its self-described "single source of coherence" status is internally consistent but
  externally lagging on counts/routes (84→87, 67→71 paths). It remains the best
  prose anchor; its *numbers* must be re-derived from code.

## VERDICT

**Provably does its job — with caveats.** The documentation corpus is internally
coherent and unusually honest: the GTB (`research/ARCLINK_GROUND_TRUTH_BRIEF.md`)
is a genuine, code-cited anchor whose load-bearing qualitative claims hold up against
code — the surface-contract vocabulary/next-action regex is byte-identical to
`python/arclink_surface_contract.py:34-43`; the OpenAPI is content-parity (71/71
paths); the product matrix totals (121 rows) are consistent across matrix→GTB→docs and
are weakly machine-guarded (`tests/test_documentation_truths.py`). The "honesty rule"
(local-real vs proof-gated vs policy-accepted) is real and pervasive.

**Real weaknesses, all doc-vs-code drift the meta-piece is supposed to catch:** the
*quantitative* spine is stale and unguarded. The authoritative module map (84) and
table counts (44/9) are wrong against code (87/45/10), the newest module
(`operator_upgrade_host_runner`, 2026-06-12) is undocumented, the GAP-016 string GAPS.md
quotes is stale, and the "byte-identical OpenAPI parity test" the GTB tells maintainers
to keep does not exist. Crucially, `docs/DOC_STATUS.md:26` brands the stale
architecture.md "Canonical," and **no test** validates module/table counts or OpenAPI
byte-parity — so the corpus's accuracy depends on manual diligence that has already
lapsed by 3 modules / 2 tables / 4 routes since the GTB was authored. The piece's job
(reconcile docs with code) is **partially unmet**: it self-flags many drifts (and is
right to), but its own headline numbers now require regeneration from code.
