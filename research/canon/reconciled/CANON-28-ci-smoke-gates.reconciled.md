# CANON-28 — CI, Smoke & Quality Gates — RECONCILED (both-model-signed)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, ArcLink two-model Federation.
Method: every Codex REFINE, every new finding, and every residual disagreement was
re-opened at path:line by the adjudicator (Read/sed/grep). Code wins over name/comment/
prior claim. Codex CONFIRM items where both models already agreed are ratified one-line.

- **Codex (GPT-5.5 xhigh) sign-off:** OBJECT(6) — "Core record ratifies: CI gates three
  direct lanes, but several seam/risk statements need precision corrections."
- **Claude adversarial-verify verdict:** TRUSTWORTHY (8 risks stand; folds in R1/G1/G2/G3).
- **FEDERATION SIGN-OFF:** **BOTH-MODEL-AGREED.** Every material point reconciled to one
  code-grounded truth. Codex states "No material rejection"; all six OBJECT points are
  precision REFINEs/new-findings, each confirmed in code below. No standing disagreements.

## RESOLUTION TABLE (disputed / refined / new points)

| Point | Winner | Deciding cite (adjudicator re-opened) |
|---|---|---|
| Three CI gates (direct py loop, web lint/test/build, host install-smoke); pytest never run | both | `.github/workflows/install-smoke.yml:31-41,64-67,78` |
| Seam 5 contract "guarded by `-x`" is FALSE for the Docker producer | codex+claude-verify | `bin/arclink-docker.sh:2692-2693` (no `-x`) vs `bin/deploy.sh:5609,5748` (`if [[ -x … ]]`) |
| pdf-ingest `backend=="pdftotext"` assert is environment-coupled (auto prefers docling) | codex+claude-verify | `bin/pdf-ingest.py:68-72` (auto: docling first) vs `bin/ci-preflight.sh:250,262` |
| live-agent-tool-smoke opens control DB read-WRITE, not read-only | codex | `bin/live-agent-tool-smoke.sh:102` `sqlite3.connect(db_path)` vs `bin/arclink-restore-smoke.sh:163` `?mode=ro` |
| Orphaned tests (defined, never called by file's runner) silently skip — distinct from "no `__main__`" | codex | executor 51 defs / 49 main calls (orphans `:1550,:1586`); docker 72/70 (`:2953,:4854`); fleet 26 defs / 24 `__main__` calls (`:165,:192`) |
| preflight `bash -n` omits root `deploy.sh` (but root deploy.sh is a 5-line exec shim; real `bin/deploy.sh` IS linted) | codex (LOW, cosmetic) | `bin/ci-preflight.sh:186-195` (lints `test.sh`+`bin/*.sh`); root `deploy.sh` = `exec "$ROOT_DIR/bin/deploy.sh"` |
| Provider-auth/unavailable live-smoke skip exits 0 → fail-open for "smoke passed" interpretation | codex (INFO) | `bin/live-agent-tool-smoke.sh:481-490` (exit 0 on both skips) |
| PROMPT_*.md are not CI gates but NOT globally inert — Ralphie feeds them to engines | codex (correction) | `ralphie.sh:68-72` map, `:9804-9811` `prompt_file_for_mode`, `:6645+` `< "$prompt_file"` |
| Port-default line numbers: record cited `:22-25`, actual `:27-30` | codex (cite fix) | `bin/ci-install-smoke.sh:27-30` (QMD_MCP 8181, NEXTCLOUD 18080, MCP 8282, NOTION 8283) |
| install-smoke teardown `\|\| true`: happy path DOES assert user/home removal; failure path does NOT | codex+claude-verify | `bin/ci-install-smoke.sh:2595-2603` (happy asserts) vs `:2481-2489` on_exit→teardown (`:2443 \|\| true`)→exit, no assert |
| tar member screening rejects path patterns only, not symlink member type | codex+claude-verify | `bin/arclink-restore-smoke.sh:104-114` (`case` on names via `tar -tf`; no type check) |
| §5B #45 — no pytest/coverage workflow cmd (proven); 90m cold-bringup sufficiency NOT statically provable | both (partial) | `.github/workflows/install-smoke.yml:31-41,64-67,71,78`; sufficiency requires a mutating run |
| Seam 4 (restore-smoke under test) UPGRADE record PARTIAL → FULL | claude-verify | `tests/test_agent_backup_regressions.py:361-364` + `tests/test_backup_git_regressions.py:402-406` vs producer keys `:219,223,258-265` |
| Seam 6 telemetry + Seam 7 pdf-status: both ends match exactly | both | `…arclink-managed-context/__init__.py:575,1079,1885-1890` ↔ `live-agent-tool-smoke.sh:163,312-314`; `pdf-ingest.py:604-625` ↔ `ci-preflight.sh:262-264,…` |
| "no Python style/lint gate" MEDIUM — ruff/pyflakes pinned, never invoked | both | `requirements-dev.txt:12-13` pins; `bin/ci-preflight.sh:197-203` only `py_compile`s 3 modules; zero invocations repo-wide |

## CODEX NEW FINDINGS — adjudicated

CONFIRMED (re-verified true in code → net-new federation risks):
1. **LOW — live-agent-tool-smoke opens the control DB read-WRITE.**
   `bin/live-agent-tool-smoke.sh:102` `sqlite3.connect(db_path)` (no URI/`mode=ro`); a
   missing DB path would be created before the SELECT. Contrast the explicit read-only
   `f"file:{path}?mode=ro", uri=True` at `bin/arclink-restore-smoke.sh:163`. A "non-mutating
   live proof" that can create a DB file is a latent contract defect.
2. **LOW — preflight `bash -n` omits the root `deploy.sh`.** `bin/ci-preflight.sh:186-195`
   lints `test.sh` + `rg --files bin -g '*.sh'`; `local-validation.md:22` documents
   `bash -n deploy.sh bin/*.sh test.sh`. Severity LOW (capped): the root `deploy.sh` is a
   5-line `exec "$ROOT_DIR/bin/deploy.sh"` shim and the real `bin/deploy.sh` IS linted, so
   the only un-linted surface is the trivial shim — a doc/coverage drift, not a real gap.
3. **INFO — provider-skip fail-open.** `bin/live-agent-tool-smoke.sh:481-490` exits 0 on
   `provider_auth_failed`/`provider_unavailable`; deploy's `-x`-guarded call then reads
   "live tool smoke passed." Explicit and intentional, but it is fail-open for that
   interpretation. INFO.

(No Codex new finding was REJECTED. All three hold in code.)

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Cite |
|---|---|---|---|
| python-regressions gate quality — "file lacks `__main__`" framing | MEDIUM (no-op file) | MEDIUM (broaden scope: ALSO orphaned tests defined-but-not-called by the runner) | executor `:1550,:1586` orphaned vs `main()` `:2135-2185`; docker `:2953,:4854`; fleet `:165,:192` |
| install-smoke teardown `\|\| true` swallows failures | MEDIUM (overstated happy-path danger) | MEDIUM (re-scoped: happy path DOES assert removal `:2595-2603`; only the FAILURE-path `on_exit` lacks a post-teardown assert) | `bin/ci-install-smoke.sh:2595-2603` vs `:2481-2489` |

Net risk count unchanged at the headline level (8 enumerated risks all stand). The two
changes refine scope/wording, not severity tier. No tier was raised or lowered because the
code supports neither escalation nor de-escalation: the lint gate is still absent (MEDIUM),
the host mutation is still real (MEDIUM), and the orphan/teardown nuances live inside the
existing MEDIUM bands.

## STANDING DISAGREEMENTS

None. Every material point reconciled to one code-grounded truth. The single
not-fully-settled item — §5B #45, whether the 90-minute install-smoke timeout suffices for a
cold Nextcloud+qmd bring-up on a fresh ubuntu-22.04 runner — is **not a disagreement**: both
models agree (a) no pytest/coverage workflow command exists (statically proven,
`install-smoke.yml:31-41,64-67,71,78`), and (b) timeout *sufficiency* is empirically
unprovable in a read-only audit and requires a mutating heavy CI run. That is a shared
acknowledged limit of static analysis, recorded as the existing MEDIUM host-mutation/flake
risk, not a contested point.

## FINAL BOTH-MODEL VERDICT

CANON-28 provably gates exactly three things on every push/PR — (a) each `tests/test_*.py`
run directly under `python3` 3.11 (`install-smoke.yml:38-41`), (b) web `lint`/`test`/`build`
(`:64-67`), and (c) the full host install/health/teardown smoke via
`deploy.sh --apply-install`/`--apply-remove` (`test.sh:14`, `ci-install-smoke.sh:2503,2443`)
— and its cross-piece seams (deploy answers-file, managed-context telemetry, pdf-ingest
status.json, restore-smoke JSON/CLI) match at both ends in code. The piece's real weaknesses
are confirmed and now sharpened: **no Python style/lint gate** (ruff/pyflakes pinned but dead,
`requirements-dev.txt:12-13` vs `ci-preflight.sh:197-203`); the python-regressions gate's
value is bounded by CANON-29's self-executing convention AND by **orphaned tests** that are
defined but never called by their own file runner (executor/docker/fleet each carry ≥2 such
orphans), which silently skip under `python3 file.py`; the heaviest gate (install-smoke) is
host-mutating, sudo-dependent, 90-minute, with a failure-path teardown that runs no
post-removal assertion; and several precision defects — Docker live-smoke producer is NOT
`-x`-guarded, the pdf `pdftotext` assert is docling-precedence-coupled, the live-smoke DB
connect is read-write, root `deploy.sh` shim is un-linted, and provider-skip is fail-open.
Net: the gate does its job for what it gates, but its "quality gate" name promises more
enforcement than the code delivers. **BOTH-MODEL-AGREED.**
