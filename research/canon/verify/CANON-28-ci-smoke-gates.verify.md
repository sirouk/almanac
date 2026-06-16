# CANON-28 — CI, Smoke & Quality Gates — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every cited file at path:line;
did not trust the record's citations. Verdict at bottom.

## SUMMARY
The record is **substantially trustworthy**. Its core load-bearing claim — "CI gates exactly
three things on every push/PR" — is correct, and the heavily-cited line numbers are accurate to
a degree that is unusual (I spot-checked ~40 citations; all landed on the claimed code). Every
both-ends-verified cross-piece contract holds at both ends in code, and two of them (seam 4 and
the pdf-ingest status seam) are actually *stronger* than the record cautiously claimed. I found
NO refutation that changes the verdict. I did find several precision defects and two genuine new
gaps the record and prior docs missed (backend-precedence coupling; the docker producer of
live-agent-tool-smoke is NOT `-x`-guarded, contradicting seam 5's stated contract).

## CITATION RE-VERIFICATION (load-bearing claims)
- `install-smoke.yml`: triggers `arclink/master/main` + `pull_request` (`:5-9`); python 3.11
  (`:23`); `requirements-dev.txt` install (`:26`); nullglob + `tests/test_*.py` glob (`:32-33`);
  fail-closed `exit 1` on zero files (`:34-37`); `python3 "$test_file"` loop, NO pytest (`:38-41`);
  `set -euo pipefail` (`:31`); web lint/test/build (`:64-67`); node 22 (`:54`); install-smoke
  `./test.sh` (`:78`); no `needs:`. ALL CONFIRMED.
- `test.sh`: `set -euo pipefail` (`:2`); tailscale-gated env export (`:7-10`); preflight (`:12`);
  `exec sudo env … ci-install-smoke.sh` (`:14`). CONFIRMED.
- `ci-preflight.sh`: `main "$@"` (`:967`); "preflight checks passed" (`:964`); shell lint via
  `rg --files bin -g '*.sh'` + `test.sh` (`:185-195`); py_compile of exactly 3 modules
  (`:197-203`); systemd skip (`:208-211`) / verify (`:214-216`); status.json asserts
  (`:262-264`,`:284-285`,`:308-310`); vision asserts incl. `Bearer fake-secret-key` (`:385`) and
  `image_url` (`:387`); trap cleanup (`:24`) + child-PID kill + `rm -rf TMP_ROOT` (`:8-22`).
  CONFIRMED.
- `ci-install-smoke.sh`: 2607 lines (CONFIRMED, record said "2607"); root check `EUID != 0`
  exit 1 (`:39-42`); `write_answers()` (`:44-123`) with `chmod 600` (`:122`);
  `load_answers_into_env()` (`:125-130`); port defaults 8181/18080/8282/8283 (`:22-25`);
  `NEXTCLOUD_ADMIN_PASSWORD=arclink-ci-admin` (~`:95`); `trap 'on_exit $?' EXIT` (`:2492`);
  install with the 3 skip env vars (`:2499-2503`); teardown `--apply-remove || true` (`:2443`);
  user/home-removed asserts (`:2595-2603`); success line (`:2607`); `wait_for_port` (`:132`);
  Nextcloud `/status.php` host `arclink-ci.local` (`:2569-2570`). ALL CONFIRMED.
- `arclink-restore-smoke.sh`: kind validation (`:61-71`); local-only source guard (`:74-78`);
  existence (`:79`); restore-dir empty (`:86-88`); containment guards (`:93-102`); JSON keys
  `ok/kind/source/restore_dir/file_count/checks` (`:258-265`); secrets/logs rejection
  (`:221-222`); nested-git rejection (`:173-178`). CONFIRMED.
- `live-agent-tool-smoke.sh`: `--tail` numeric>=1 (`:48-54`); positional user (`:66-74`);
  unknown `--*` exit 2 (`:61-65`); timeout env int>=30 (`:83-86`); hermes binary check
  (`:88-91`); no-agent skip+exit0 (`:132-135`); telemetry match `session_id`+
  `tool_token_injected is True` (`:312-314`); retry self-exec (`:467-473`). CONFIRMED.
- `pytest.ini` (`:1-8`) + `.github/` = ONLY `install-smoke.yml` (`git ls-files`). CONFIRMED.
- `requirements-dev.txt`: pyflakes `:12`, ruff `:13`. CONFIRMED.

## REFUTATIONS / PARTIAL REFUTATIONS

### R1 — Seam 5 "guarded by `-x`" is FALSE for the docker producer (PARTIAL REFUTATION)
Record §CROSS-PIECE CONTRACTS seam 5 states the SEAM CONTRACT as "an optional best-effort live
check guarded by `-x`. BOTH-ENDS-VERIFIED: YES for the existence/guard." Only the deploy.sh
producers are `-x`-guarded (`bin/deploy.sh:5609` `if [[ -x … ]]`, `:5748` same). The docker
producer is NOT: `bin/arclink-docker.sh:2692-2693`
`docker_live_agent_smoke() { compose_supervisor_command ./bin/live-agent-tool-smoke.sh "$@"; }`
runs unconditionally — no `-x` test. The seam's stated contract is therefore inaccurate for one
of the two producers it names. Functional impact is low (the docker path dispatches through a
compose supervisor and the script self-skips when no agent exists, `:132-135`), but the
"guarded by `-x`" framing is wrong as written.

### R2 — Drift #2 parenthetical wording: minor inaccuracy, conclusion still holds (NOT REFUTED)
Record drift #2 says `rg ruff|pyflakes` over `bin/ .github/ test.sh` finds zero invocations
"(only `install-arclink-plugins.sh` excludes `.ruff_cache/`)". I independently confirmed via
`git grep -i -E 'ruff|pyflakes|flake8'` across ALL tracked files: the ONLY hits are
`.ruff_cache` *cleanup/exclusion* patterns in `bin/install-arclink-plugins.sh:588,596` and
`.dockerignore:29`, plus the requirements-dev pins. So there is genuinely NO ruff/pyflakes
*invocation* anywhere, including `tests/**` (this resolves the record's own OPEN-FOR-CODEX #1 in
the record's favor). The drift #2 claim is CONFIRMED; the conclusion "no Python lint/style gate
in CI" stands. NOT a refutation.

## NEW GAPS (neither record nor prior docs mention)

### G1 — preflight pdf-ingest `backend=="pdftotext"` assert is environment-coupled (LOW)
`ci-preflight.sh:262` asserts `status["backend"] == "pdftotext"`, but the fixture sets
`PDF_INGEST_EXTRACTOR=auto` (`ci-preflight.sh:250`) and `pdf-ingest.py:resolve_backend()` under
`auto` checks **`docling` FIRST, then `pdftotext`** (`bin/pdf-ingest.py:68-72`). The fixture
only installs a fake `pdftotext` (`setup_fake_pdftotext`), never docling, so the assertion holds
ONLY because docling is absent on the runner. If any runner image / dev machine has `docling`
installed (or on PATH), `resolve_backend()` returns `"docling"` and the preflight assert at
`:262` FAILS even though pdf-ingest is healthy. This is a silent environment coupling the record
presents as a clean "REAL pipeline" assertion. Severity LOW (ubuntu-22.04 has no docling today),
but it is a real determinism gap.

### G2 — install-smoke failure path has NO post-teardown removal assertion (INFO)
The record RISK (MEDIUM) frames the teardown `|| true` as "teardown failures are swallowed". The
nuance both directions: in the HAPPY path, a teardown that fails to remove the user IS caught by
the independent asserts at `ci-install-smoke.sh:2595-2603` (`id -u "$ARCLINK_USER"` -> exit 1),
so removal failures are NOT silently passed there (the record's risk wording overstates the
happy-path danger). Conversely, on the FAILURE path, `trap on_exit` -> `teardown`
(`--apply-remove || true`) -> `exit $status` runs NO removal assertion, so a failed run that also
fails cleanup leaves residue undetected. Both nuances are absent from the record. Severity INFO
because the GitHub `ubuntu-22.04` runner is ephemeral (residue is discarded).

### G3 — restore-smoke `validate_tar_members` does not screen symlink members (LOW)
`arclink-restore-smoke.sh:104-114` rejects tar members with `..`/absolute paths, but does not
inspect for symlink entries. A crafted tar with a symlink member pointing outside the
restore-dir followed by a write-through member is the classic tar symlink-escape. The OUTPUT
CONTRACT claim "It never writes outside the restore-dir" (record §OUTPUT, `:132-134`) relies on
`tar`'s own protections, not on `validate_tar_members`. GNU tar generally refuses to extract
through a symlink it just created, so exploitability is low and the input is operator-supplied
local backup artifacts (not adversarial), but the record asserts the guard is what enforces
containment — the guard does NOT cover symlinks. Severity LOW.

## SEAMS — re-verified at BOTH ends
- Seam 2 (web): `web/package.json` scripts `lint`=`eslint src next.config.ts playwright.config.ts
  --max-warnings=0`, `test`=`node --test tests/test_page_smoke.mjs tests/test_api_client.mjs`,
  `build`=`next build`; both `.mjs` files exist on disk. BOTH ENDS MATCH. CONFIRMED.
- Seam 3 (deploy): producer `ci-install-smoke.sh:2503`/`:2443` passes `ARCLINK_INSTALL_ANSWERS_FILE`
  + `--apply-install`/`--apply-remove`; consumer `deploy.sh:24` reads the env var, `:757`/`:768`
  dispatch the subcommands. ARG NAMES MATCH EXACTLY. CONFIRMED.
- Seam 4 (restore-smoke under test): UPGRADED from record's "PARTIAL" to FULL. Consumers
  `tests/test_agent_backup_regressions.py:361-364` assert `payload["ok"]`, `["kind"]=="agent-home"`,
  `"agent_manifest_json" in checks`, `"agent_secret_exclusion" in checks`; producer emits all of
  these (`arclink-restore-smoke.sh:259,260,219,223,258-265`).
  `tests/test_backup_git_regressions.py:402-406` assert `"git_archive_head"`/`"sqlite_quick_check"`/
  `"shared_layout"` in checks; producer emits at `:120,:198,:203`. BOTH ENDS MATCH EXACTLY.
- Seam 6 (managed-context telemetry): producer
  `plugins/hermes-agent/arclink-managed-context/__init__.py:575` `_TELEMETRY_FILENAME=
  "arclink-context-telemetry.jsonl"`, path built `:1079` (`_hermes_home()/"state"/…`),
  emits `{"session_id": str(session_id or "__global__"), "tool_token_injected": True}` (`:1885-1890`);
  consumer `live-agent-tool-smoke.sh:163,312,314` reads the same path and matches `session_id`
  + `tool_token_injected is True`. KEY NAMES/TYPE/PATH MATCH. (Latent quirk: producer falls back
  to `"__global__"` on empty session_id, a different namespace than the consumer's `Session:`
  regex — not exploitable in normal Hermes flow, but a fragile coupling.)
- Seam 7 (pdf-ingest status.json): producer `pdf-ingest.py:604-625` builds dict with all 12
  keys the record lists (incl. `vision_pages_captioned`/`vision_pages_failed`), `write_status_file`
  at `:583` called at `:628`/`:835`; consumer asserts on exactly those keys
  (`ci-preflight.sh:262-264,284-285,308-310,378-388,416-419`). BOTH ENDS MATCH EXACTLY.

## RISK SEVERITY RE-CALIBRATION
- The record's MEDIUM "no Python lint/style gate" is correctly calibrated and independently
  confirmed (zero ruff/pyflakes invocations anywhere).
- The record's MEDIUM "python-regressions delegates quality to CANON-29 / a `__main__`-less file
  no-ops to exit 0" is correctly calibrated. (128 `tests/test_*.py` exist, so the gate is
  non-empty; the no-op-per-file risk is real and CANON-29's to enforce.)
- The record's MEDIUM "install-smoke mutates real host / `|| true` swallows teardown" should be
  softened on the happy-path side per G2: the script DOES assert user/home removal at
  `:2595-2603` after teardown, so removal failures are NOT silently passed on success.
- No risk is mis-calibrated in a way that flips the verdict.

## VERDICT
**TRUSTWORTHY.** Citations are accurate, the three CI gates are proven, and all both-ends seams
verify in code (two stronger than claimed). The single contract inaccuracy (R1: docker producer
is not `-x`-guarded) and three new gaps (G1 backend-precedence coupling; G2 failure-path
teardown asymmetry; G3 tar symlink screening) are precision/robustness defects, not
falsifications of the record's core claims. The record's own VERDICT — "the piece does its job
for what it gates, but its name promises more quality enforcement than the code delivers" — is
sound. Confirmed risk count: 8 (the record's 8 enumerated risks all stand). Recommend folding
R1, G1, G2, G3 into the record.
