# CANON-28 — CI, Smoke & Quality Gates

## PIECE
This piece is ArcLink's automated-gate surface: what actually runs on every push/PR
and what is merely a local or live-only script. It owns:
- `.github/workflows/install-smoke.yml` — the ONE GitHub Actions workflow (job names
  `python-regressions`, `web-regressions`, `install-smoke`).
- `bin/ci-preflight.sh` — no-secret, no-root preflight (shell lint, py_compile,
  systemd verify, and four end-to-end watcher/PDF-ingest fixture runs).
- `bin/ci-install-smoke.sh` — root-only full host install/health/teardown smoke
  (2607 lines; calls `bin/deploy.sh --apply-install`, runs ~20 control-plane and
  runtime assertions, then `bin/health.sh`, then `--apply-remove`).
- `test.sh` — the 14-line CI entrypoint that runs `ci-preflight.sh` then
  `sudo ci-install-smoke.sh`.
- `pytest.ini` — pytest config (testpaths/norecursedirs) — present but NOT used by CI
  (CI runs each `tests/test_*.py` directly via `python3`, not pytest).
- `requirements-dev.txt` — focused no-secret dependency pin set (includes `ruff` and
  `pyflakes`, which are NOT invoked anywhere in CI or these scripts).
- `bin/arclink-restore-smoke.sh` — standalone backup-restore structural smoke; NOT
  invoked by CI (only by `tests/test_*backup*` and docs).
- `bin/live-agent-tool-smoke.sh` — standalone live Hermes MCP tool smoke; NOT invoked
  by CI (only by `bin/deploy.sh` and `bin/arclink-docker.sh` in live flows).
- `PROMPT_test.md`, `PROMPT_lint.md`, `PROMPT_build.md` — Ralphie agent-loop phase
  prompts (pure documentation/agent-instructions; no executable gate).

Load-bearing truth: **CI gates exactly three things** — (1) each `tests/test_*.py`
run directly under `python3 3.11`, (2) web `lint`/`test`/`build`, and (3) the host
install smoke via `./test.sh`. restore-smoke, live-agent-tool-smoke, ruff, pyflakes,
and pytest are all OUT of the CI gate.

## INPUT CONTRACT (code-verified)

### `.github/workflows/install-smoke.yml`
- Triggers: `push` to branches `arclink`, `master`, `main`; any `pull_request`
  (`.github/workflows/install-smoke.yml:3-9`).
- `python-regressions` (`:12-41`): runner `ubuntu-22.04`, timeout 30m, Python `3.11`
  (`:23`). Installs `requirements-dev.txt` (`:26`). Then a bash step that globs
  `tests/test_*.py` (`nullglob`, `:32-33`), **fails closed** if zero files
  (`exit 1`, `:34-37`), and runs EACH file directly: `python3 "$test_file"`
  (`:38-41`). **It does NOT call `pytest`.** No `-x`/fail-fast; loop has no `|| true`
  so the FIRST failing file aborts the step under the implicit `set -euo pipefail`
  at `:31`.
- `web-regressions` (`:43-67`): runner `ubuntu-22.04`, timeout 20m, Node `22`
  (`:54`), npm cache keyed on `web/package-lock.json` (`:56`). `npm ci` in `web/`
  (`:60`), then `npm run lint`, `npm test`, `npm run build` sequentially (`:64-67`).
- `install-smoke` (`:69-78`): runner `ubuntu-22.04`, timeout 90m, single step
  `./test.sh` (`:78`).
- The three jobs have NO `needs:` dependency — they run in parallel.

### `test.sh`
- No args. `set -euo pipefail` (`:2`). Detects a logged-in tailscale and, only then,
  exports `ARCLINK_SMOKE_ENABLE_TAILSCALE_SERVE=1` +
  `ARCLINK_SMOKE_TAILSCALE_OPERATOR_USER` (`:7-10`). Runs `bin/ci-preflight.sh`
  (`:12`) then `exec sudo env … bin/ci-install-smoke.sh` (`:14`). In GitHub's
  ubuntu-22.04 the runner has passwordless sudo, so `sudo` succeeds.

### `bin/ci-preflight.sh`
- No args used (`main "$@"` at `:967` ignores them). `set -euo pipefail` (`:2`).
  Reads env: `ARCLINK_ALLOW_SCAFFOLD_DEFAULTS` (forced `=1` in each fixture, e.g.
  `:245`), `PATH` (prepends a fakebin), and per-fixture `VAULT_DIR/STATE_DIR/...`.
  Optional tooling probed and SKIPPED (not failed) when absent: `systemd-analyze`
  (`:208-211`), `inotifywait` (`:457-460`, `:541-544`, `:748-751`).
- Caller of preflight: only `test.sh:12` and docs.

### `bin/ci-install-smoke.sh`
- **Must run as root** — `EUID != 0` exits 1 (`:39-42`). Reads many `ARCLINK_SMOKE_*`
  override env vars with defaults (`:6-33`), e.g. `ARCLINK_SMOKE_NAME` (default
  `arclink`), `ARCLINK_SMOKE_USER`, `ARCLINK_SMOKE_HOME`, ports
  (`ARCLINK_SMOKE_QMD_MCP_PORT`=8181, `ARCLINK_SMOKE_NEXTCLOUD_PORT`=18080,
  `ARCLINK_MCP_PORT`=8282, `ARCLINK_NOTION_WEBHOOK_PORT`=8283),
  `ARCLINK_SMOKE_ENABLE_TAILSCALE_SERVE`, `ARCLINK_SMOKE_AUTOPROV_USER`. Writes a
  full answers file (`write_answers`, `:44-123`) with `chmod 600` (`:122`) and
  sources it (`load_answers_into_env`, `:125-130`).

### `bin/arclink-restore-smoke.sh`
- Flags: `--kind shared|agent-home` (required, validated `:61-71`), `--source PATH`
  (required, MUST be local — URL/git schemes rejected `:74-78`, existence checked
  `:79`), `--restore-dir PATH` (optional; if pre-existing must be empty `:86-88`),
  `--json`, `-h/--help`. Unknown arg -> usage + `die` (`:54-57`). Path-containment
  guards reject restore-dir inside source and vice-versa (`:93-102`).

### `bin/live-agent-tool-smoke.sh`
- Flags: `--user/-u UNIX_USER`, `--agent/-a AGENT_ID_OR_NAME`, `--tail LINES`
  (numeric, `>=1`, `:48-54`), `--help`. Positional first arg also taken as
  `TARGET_UNIX_USER` (`:66-74`). Unknown `--*` -> exit 2 (`:61-65`). Reads env:
  `ARCLINK_LIVE_AGENT_SMOKE_RETRY_ATTEMPT` (`:15`),
  `ARCLINK_LIVE_AGENT_SMOKE_TIMEOUT_SECONDS` (default 300, must be int `>=30`,
  `:16`,`:83-86`), `ARCLINK_LIVE_AGENT_SMOKE_PROMPT` (default a vault-search prompt,
  `:17`). Requires `python3` (`:78-81`), a Hermes runtime binary at
  `$RUNTIME_DIR/hermes-venv/bin/hermes` (`:88-91`), and an active enrolled
  `role='user'` agent (else prints "skipping" + `exit 0`, `:132-135`).

### `pytest.ini` / `requirements-dev.txt` / PROMPT_*.md
- `pytest.ini` declares `testpaths = tests` and `norecursedirs` (`.git`, `.ralphie`,
  `arclink-priv`, `logs`, `subrepos`). It is read ONLY by an explicit `pytest`
  invocation, which CI never issues.
- `requirements-dev.txt` is a flat pin list (no executable contract). CI installs it
  (`install-smoke.yml:26`); preflight does not.
- PROMPT_*.md are agent-loop instructions, not code; no parser reads them in this
  piece.

## OUTPUT CONTRACT (code-verified)

### CI workflow
- Exit/return is per-job pass/fail surfaced to GitHub Actions. No artifacts uploaded
  by any job. python-regressions emits per-file `echo "Running ${test_file}"`
  (`:39`).

### `bin/ci-preflight.sh`
- stdout `[preflight] …` log lines (`log()`, `:26-28`). On any assertion failure the
  `set -e` + bare `python3 - <<PY ... assert` heredocs abort with non-zero (e.g.
  status-json asserts `:256-265`,`:278-286`,`:302-311`). Side effects are all under
  a `mktemp -d /tmp/arclink-preflight.XXXXXX` (`:5`) plus `/tmp/arclink-preflight-*.log`
  files; `trap cleanup EXIT` kills child watcher PIDs and `rm -rf "$TMP_ROOT"`
  (`:8-24`). It spawns real background watcher processes (`vault-watch.sh`) and a
  fake vision HTTP server (`:181-182`), all torn down on exit.

### `bin/ci-install-smoke.sh`
- Mutates the REAL host: creates a service user, installs the full ArcLink stack via
  `deploy.sh --apply-install` (`:2503`), brings up qmd + Nextcloud containers,
  exercises the SQLite control plane (`$ARCLINK_DB_PATH`), then tears everything down
  (`teardown`, `:2441-2447`; `--apply-remove` at `:2443`). Final asserts the service
  user and home are GONE (`:2595-2603`). `trap 'on_exit $?' EXIT` (`:2492`) always
  runs teardown + removes the answers file even on failure. Prints
  "Install smoke test completed successfully." on success (`:2607`).

### `bin/arclink-restore-smoke.sh`
- Restores `--source` into `--restore-dir` (or a `mktemp -d`), runs structural
  checks, and on success either prints human lines (`restored_to=`, `file_count=`,
  `checks=`, `:268-272`) or, with `--json`, a single sorted JSON object
  `{ok, kind, source, restore_dir, file_count, checks[]}` (`:250-266`). Any failed
  guard calls `die` -> stderr + `exit 1`. **It never writes outside the restore-dir
  and never touches a live ArcLink path** (enforced by source/restore containment
  guards `:93-102` and the local-only source guard `:74-78`).

### `bin/live-agent-tool-smoke.sh`
- Runs `hermes chat -q "$PROMPT"` as the target agent user under a `timeout`
  (`:173-177`), captures output to a `0600` tmp file, then validates the resulting
  Hermes session JSON + context telemetry. Output is a final status line +
  `validation_result` JSON (`:492-493`). Exit codes: `0` on pass OR on a
  graceful skip (`provider_auth_failed`/`provider_unavailable`, `:481-490`); non-zero
  on validation failure (`:457-465`). It self-`exec`s once for a stale-MCP-transport
  retry (`:467-473`).

## TOUCH POINTS

### Env vars
- Workflow inputs: branch names, `python-version: 3.11`, `node-version: 22`
  (`install-smoke.yml:23,54`).
- `test.sh`: `ARCLINK_SMOKE_ENABLE_TAILSCALE_SERVE`,
  `ARCLINK_SMOKE_TAILSCALE_OPERATOR_USER`, `DEBIAN_FRONTEND` (`test.sh:5-10`).
- `ci-preflight.sh`: `ARCLINK_ALLOW_SCAFFOLD_DEFAULTS`, `PATH`, `ARCLINK_CONFIG_FILE`,
  and the fixture config files write `ARCLINK_REPO_DIR/ARCLINK_PRIV_DIR/VAULT_DIR/
  STATE_DIR/ARCLINK_DB_PATH/PDF_INGEST_*/PDF_VISION_*/VAULT_WATCH_*/OPERATOR_NOTIFY_*`
  etc. (`:243-252`, `:574-599`, `:776-800`).
- `ci-install-smoke.sh`: the full answers file (`:44-121`) including
  `OPERATOR_NOTIFY_CHANNEL_PLATFORM=tui-only`, `ARCLINK_MODEL_PRESET_*`,
  `ENABLE_NEXTCLOUD=1`, `POSTGRES_*`, `NEXTCLOUD_ADMIN_*` (test-only fake creds),
  `REMOVE_*=1` teardown flags. Sets `ARCLINK_ALLOW_NO_USER_BUS=1`,
  `ARCLINK_CURATOR_SKIP_HERMES_SETUP=1`, `ARCLINK_CURATOR_SKIP_GATEWAY_SETUP=1` for
  the install call (`:2499-2503`).
- `live-agent-tool-smoke.sh`: `RUNTIME_DIR`, `ARCLINK_DB_PATH` (from `common.sh`),
  `HOME`, `HERMES_HOME`, `ARCLINK_LIVE_AGENT_SMOKE_*` (`:15-17`).

### DB tables (r/w)
- `ci-preflight.sh` opens the real control DB via `arclink_control.connect_db` and
  INSERTs into `agents`, calls `ensure_default_subscriptions`,
  `set_vault_subscription`, `consume_agent_notifications`, `discover_vault_repo_sources`,
  `sync_vault_repo_mirrors` (`:616-677`, `:697-727`, `:823-879`, `:896-948`). Schema:
  `agents` (`arclink_control.py:659-677`).
- `ci-install-smoke.sh` reads/writes `$ARCLINK_DB_PATH` through `arclink_ctl` /
  `deploy.sh` shells across its ~20 assertions (bootstrap tokens, notifications,
  SSOT, etc.).
- `live-agent-tool-smoke.sh` opens `$ARCLINK_DB_PATH` read-only and SELECTs
  `agent_id, unix_user, hermes_home, display_name` from `agents` WHERE
  `role='user' AND status='active'` (`:104-122`). Columns exist verbatim in the
  schema (`arclink_control.py:660-665`).
- `arclink-restore-smoke.sh` opens any restored `*.sqlite3`/`*.db` read-only with
  `PRAGMA quick_check` (`:153-171`) — it does NOT know the ArcLink schema; pure
  integrity check.

### Files / paths
- preflight tmp root `/tmp/arclink-preflight.XXXXXX`; fixture markdown/status under
  `state/pdf-ingest/...`; copies real `bin/common.sh`, `bin/vault-watch.sh`,
  `bin/pdf-ingest.{sh,py}` into fixture repos (`:463-464`,`:548-551`,`:754-755`).
- restore-smoke: `mktemp -d "${TMPDIR:-/tmp}/arclink-restore-smoke.XXXXXX"` (`:84`);
  reads `MANIFEST.json`/`SOUL.md`/`config.yaml`/... for agent-home (`:206-233`);
  rejects restored `secrets/` and `logs/` (`:221-222`) and nested `.git` (`:173-178`).
- live-agent-tool-smoke: reads `$TARGET_HERMES_HOME/state/arclink-context-telemetry.jsonl`,
  `$TARGET_HERMES_HOME/sessions/session_*.json`, `logs/agent.log` (`:163-165`).

### Sockets / ports
- ci-install-smoke waits on `127.0.0.1` ports: ARCLINK_MCP (8282), notion-webhook
  (8283), qmd-mcp (8181), Nextcloud (18080) via `wait_for_port` (`:132-163`,
  `:2506-2565`). Nextcloud HTTP `/status.php` with `Host: arclink-ci.local`
  (`:2568-2576`).
- preflight starts an ephemeral `ThreadingHTTPServer` on `127.0.0.1:0` (fake vision
  endpoint, `:176-178`) and passes its discovered port back through a port-file.

### Subprocess argv (seams out)
- `test.sh` -> `bin/ci-preflight.sh`; `sudo env … bin/ci-install-smoke.sh`.
- `ci-install-smoke.sh` -> `deploy.sh --apply-install` / `--apply-remove` /
  `agent-payload` (`:2503`,`:2443`,`:1035`); `bin/health.sh` (`:2586,:2588`);
  `bin/qmd-daemon.sh`, `bin/nextcloud-up.sh` (`:2557,:2561`); `arclink_ctl` shells.
- `ci-preflight.sh` -> `bash -n` on `test.sh` + all `bin/*.sh` (`:185-195`);
  `python3 -m py_compile` on `bin/pdf-ingest.py`, `arclink_control.py`,
  `arclink_ctl.py` (`:197-203`); `systemd-analyze verify` (`:214-216`);
  `bin/pdf-ingest.sh`, `bin/vault-watch.sh` fixtures.
- `live-agent-tool-smoke.sh` -> `hermes chat -q` under `timeout --foreground
  --kill-after=30s` (`:177`), via `runuser -u`/`env` (`:147-156`).

### Secrets handling
- No live secrets anywhere. ci-install-smoke uses literal fake creds
  (`NEXTCLOUD_ADMIN_PASSWORD=arclink-ci-admin`, etc. `:93-95`). preflight uses a fake
  `PDF_VISION_API_KEY=fake-secret-key` and asserts the fixture forwards it as
  `Authorization: Bearer fake-secret-key` (`:362,:385`). restore-smoke asserts
  agent-home artifacts contain NO `secrets/` or `logs/` (`:221-222`).

### Locks / concurrency
- preflight tracks `PREFLIGHT_CHILD_PIDS` and kills the process group on cleanup
  (`:6-22`,`:513`,`:687`,`:888`). No file locks of its own; it exercises
  vault-watch's debounce (`VAULT_WATCH_DEBOUNCE_SECONDS=1`).
- live-agent-tool-smoke leans on `hermes`'s own session locking; it only diffs
  session files before/after (`:169`).

## CODE-PATH TRACE (CI install-smoke job, end-to-end)
1. GitHub fires `push`/`pull_request` -> `install-smoke` job step runs `./test.sh`
   (`install-smoke.yml:78`).
2. `test.sh:7-10` probes tailscale; on a fresh runner it is absent, so no
   tailscale env is exported. `test.sh:12` runs `bin/ci-preflight.sh`.
3. `ci-preflight.sh:954-964` `main`: `run_shell_lint` (`bash -n` over `test.sh` +
   every `bin/*.sh`, `:185-195`) -> `run_python_checks` (py_compile of 3 modules,
   `:197-203`) -> `run_systemd_verify` (skips if no `systemd-analyze`) ->
   `run_pdf_ingest_preflight` (`:225-312`) builds a fake `pdftotext`, writes a 1-page
   PDF, runs the REAL `bin/pdf-ingest.sh`, then asserts `status.json["backend"]==
   "pdftotext"`, `created==1`, `failed==0` (`:256-265`), then update (unchanged>=1)
   and delete (removed==1, total_pdfs==0) passes.
4. `run_pdf_ingest_vision_preflight` (`:314-424`) stands up the ephemeral fake vision
   server, runs pdf-ingest with `PDF_VISION_ENDPOINT` pointed at it, and asserts the
   request was `POST /v1/chat/completions` with `Authorization: Bearer
   fake-secret-key` and an `image_url` content part, and `status.json["vision_*"]`
   counts (`:369-388`).
5. `run_vault_watch_preflight`/`run_vault_notification_preflight`/
   `run_repo_sync_preflight` spawn real `vault-watch.sh` watchers (skipped if no
   `inotifywait`), create/delete files in a fixture vault, and assert
   markdown generation + `consume_agent_notifications` routing + git-mirror sync
   against the REAL control DB (`:446-952`). On all-pass: `:964` logs "preflight
   checks passed", exit 0.
6. Back in `test.sh:14`, `exec sudo env … bin/ci-install-smoke.sh`.
7. `ci-install-smoke.sh` root-check (`:39-42`) -> `write_answers` (`:2494`) ->
   `load_answers_into_env` (`:2495`) -> `preclean` (`:2496`, removes any prior
   smoke user via `deploy.sh --apply-remove`).
8. `:2498-2504` runs `deploy.sh --apply-install` with the answers file ->
   `INSTALLED=1`. deploy reads `ARCLINK_INSTALL_ANSWERS_FILE` (`deploy.sh:24`) and
   dispatches `--apply-install` (`deploy.sh:757`).
9. `:2506-2551` runs ~14 control-plane assertions (agent payload, vault bootstrap,
   token roundtrip, async bootstrap, remote auto-provision, upgrade-dedup,
   rate-limit 429, admin-auth, token-reinstate, SSOT rails, Notion webhook,
   notification backlog).
10. `:2554-2582` starts qmd + Nextcloud, waits for ports + `/status.php`, and runs the
    Nextcloud/vault-mount/text-watch/markdown-watch/pdf-ingest runtime assertions.
11. `:2584-2589` runs `bin/health.sh` as the service user.
12. `:2592-2593` `teardown` -> `deploy.sh --apply-remove`. `:2595-2603` assert user
    + home removed. `:2607` prints success. `trap on_exit` (`:2492`) guarantees
    teardown + answers-file removal on any earlier failure.

## CROSS-PIECE CONTRACTS (both ends verified)

1. **CANON-29 (Test Corpus) — the python-regressions gate.**
   Producer: `install-smoke.yml:33` globs `tests/test_*.py` and runs each via
   `python3 "$test_file"` (`:40`). Consumer/contract: each test file must be a
   directly-executable script that exits non-zero on failure (NOT a pytest-collected
   module). `pytest.ini` (testpaths/norecursedirs) is IGNORED by this lane — pytest
   is never run. SEAM CONTRACT: "every `tests/test_*.py` is an executable script with
   a `__main__` runner; first non-zero aborts the job." BOTH-ENDS-VERIFIED: PARTIAL —
   the producer side is fully verified here; whether all 99+ test files actually run
   standalone is CANON-29's to confirm (I verified the runner shape, not every file).

2. **CANON-03 (Web App) — the web-regressions gate.**
   Producer: `install-smoke.yml:64-67` runs `npm run lint && npm test && npm run
   build`. Consumer: `web/package.json` scripts `lint` = `eslint … --max-warnings=0`,
   `test` = `node --test tests/test_page_smoke.mjs tests/test_api_client.mjs`,
   `build` = `next build`. Both test files exist (`web/tests/test_page_smoke.mjs`,
   `web/tests/test_api_client.mjs`). SEAM CONTRACT: those three npm scripts exist and
   exit non-zero on failure; lint is zero-warning. BOTH-ENDS-VERIFIED: YES.

3. **CANON-24 (Deploy & Install Lane) — install-smoke -> deploy.sh.**
   Producer: `ci-install-smoke.sh:2503` `deploy.sh --apply-install` (and `--apply-remove`
   `:2443`, `agent-payload` `:1035`) passing `ARCLINK_INSTALL_ANSWERS_FILE`. Consumer:
   `deploy.sh:24` reads `ARCLINK_INSTALL_ANSWERS_FILE`, `deploy.sh:757` handles
   `--apply-install`, `:768` handles `--apply-remove`. SEAM CONTRACT: env-var answers
   file + these exact subcommand strings. BOTH-ENDS-VERIFIED: YES (arg names match
   exactly).

4. **CANON-29/test corpus — restore-smoke as a fixture-under-test.**
   Producer: `tests/test_backup_git_regressions.py:14` and
   `test_agent_backup_regressions.py:14` reference `bin/arclink-restore-smoke.sh` as
   the binary they invoke and assert on. Consumer: the script's `--kind/--source/
   --json` CLI and JSON shape (`{ok,kind,source,restore_dir,file_count,checks}`,
   `:258-265`). SEAM CONTRACT: stable flags + JSON keys. BOTH-ENDS-VERIFIED: PARTIAL
   — I verified the script's emitted JSON keys; the exact assertions live in CANON-29.

5. **CANON-24/25 — live-agent-tool-smoke invoked by deploy/docker (NOT CI).**
   Producer: `bin/deploy.sh:5609-5612,5748-5751` (`if [[ -x … ]]`) and
   `bin/arclink-docker.sh:2693` (`compose_supervisor_command ./bin/live-agent-tool-smoke.sh`).
   Consumer: this script's CLI + its read of `agents` and the telemetry file. SEAM
   CONTRACT: it is an optional best-effort live check guarded by `-x`. BOTH-ENDS-
   VERIFIED: YES for the existence/guard; the live behavior is unverifiable without a
   real Hermes runtime.

6. **CANON-30 (Hermes Plugins) — live-agent-tool-smoke <- context telemetry.**
   Producer: `plugins/hermes-agent/arclink-managed-context/__init__.py:1885-1895`
   `_emit_telemetry({"session_id": …, "event":"tool_token_injected",
   "tool_token_injected": True, …})` written to
   `_hermes_home()/state/arclink-context-telemetry.jsonl` (`:1078-1106`,
   `_TELEMETRY_FILENAME = "arclink-context-telemetry.jsonl"` `:575`). Consumer:
   `live-agent-tool-smoke.sh:163` reads `$TARGET_HERMES_HOME/state/
   arclink-context-telemetry.jsonl` and at `:312-315` matches
   `record.get("session_id")==session_id` AND `record.get("tool_token_injected") is
   True`. SEAM CONTRACT: JSONL rows keyed `session_id` + boolean `tool_token_injected`
   at path `HERMES_HOME/state/arclink-context-telemetry.jsonl`. BOTH-ENDS-VERIFIED:
   YES (key names, boolean type, and path all match).

7. **CANON-31 (operational scripts) — preflight <- pdf-ingest status.json.**
   Producer: `bin/pdf-ingest.py:604-621` builds the summary dict with keys `backend,
   total_pdfs, created, updated, unchanged, removed, failed, vision_enabled,
   vision_model, vision_pages_rendered, vision_pages_captioned, vision_pages_failed`
   and `write_status_file` (`:583,:835`). Consumer: `ci-preflight.sh` Python asserts
   on exactly those keys (`:261-265, :283-285, :307-311, :378-388, :415-419`). SEAM
   CONTRACT: that status.json key set + value types. BOTH-ENDS-VERIFIED: YES.

8. **CANON-23 (Diagnostics) — boundary, NOT a CI seam.** The prior doc
   `research/ground-truth/12-diagnostics-health-evidence.md` is CANON-23's subject;
   it only references CANON-28 obliquely via `local-validation.md`/`ci-preflight.sh`.
   Verified: `docs/arclink/local-validation.md:24` documents `./bin/ci-preflight.sh`
   and `:11-17,:37-40` document `requirements-dev.txt` + the `test.sh` sudo install
   smoke — accurate vs code. The diagnostics/live-runner CLIs live in CANON-23; CANON-28
   does NOT gate them (no CI step runs `arclink_diagnostics`/`arclink_live_runner`).

## CODE vs COMMENT/DOC/NAME DRIFT
1. **`pytest.ini` exists but pytest is never the gate.** The workflow runs each
   `tests/test_*.py` directly (`install-smoke.yml:40`), not `pytest`. `pytest.ini`'s
   `testpaths`/`norecursedirs` only matter if a human runs `pytest` manually.
   `local-validation.md:16-17` correctly states "`pytest` is not required" — so the
   DOC is honest, but the presence of `pytest.ini` in this piece is misleading at a
   glance.
2. **`requirements-dev.txt` pins `ruff` and `pyflakes`, but NO CANON-28 file invokes
   either.** `rg ruff|pyflakes` over `bin/`, `.github/`, `test.sh` finds zero
   invocations (only `install-arclink-plugins.sh` excludes `.ruff_cache/`). The lint
   GATE for Python is effectively just `bash -n` + `py_compile` in preflight; ruff/
   pyflakes are install-only conveniences for ad-hoc local use. `PROMPT_lint.md`
   ("quality gate agent") never names ruff/pyflakes either — it suggests py_compile /
   node --check / bash -n. So the "quality gate" name oversells: there is no
   style/lint enforcement on Python in CI.
3. **"CI install-smoke" naming vs the file `install-smoke.yml` actually being the
   whole CI.** The workflow `name: CI` contains THREE jobs, only one of which is the
   install smoke; the filename undersells. Not a bug, but a naming drift worth noting.
4. **restore-smoke + live-agent-tool-smoke are commonly grouped under "CI smoke"
   (this very piece's title) yet are NOT in the CI workflow at all.** They are live/
   deploy-time tools. The prior steering docs that lump them as "smoke gates" overstate
   CI coverage.
5. **PROMPT_test/lint/build.md are inert.** They are Ralphie agent-loop prompts; no
   code in the repo parses them as a gate. Their "agent" language could be mistaken
   for an executable test harness — it is not.

## ADVERSARIAL SELF-CHECK
1. **"CI runs each test file with python3, not pytest."** Falsifier: a hidden second
   workflow or a `pytest` call. I confirmed `git ls-files .github/` returns ONLY
   `install-smoke.yml`, and `:40` is `python3 "$test_file"`. Low residual risk.
2. **"ruff/pyflakes are never invoked."** Falsifier: an invocation inside a file I
   didn't grep (e.g. a Makefile, a git hook, or inside one of the 99 test files). I
   grepped `bin/ .github/ test.sh PROMPT_lint.md` and the docs; I did NOT exhaustively
   grep `tests/**` or `.git/hooks`. A test file COULD shell out to ruff. Medium
   residual uncertainty — flagged for Codex.
3. **"web `npm test` runs exactly those two .mjs files."** Falsifier: a `pretest`/
   `posttest` hook or a config that expands the set. I read the `scripts` block; there
   is no `pretest`. Low risk.
4. **"python-regressions has no fail-fast beyond the first failing file."** True only
   because the loop has no `|| true` and `set -euo pipefail` is at `:31`. If a future
   edit adds `|| true`, the gate silently passes on failures. Verified current state;
   fragility noted as a risk.
5. **"restore-smoke/live-agent-tool-smoke are not in CI."** Falsifier: an indirect
   call (e.g. a test file invoking them, which WOULD then run under python-regressions
   in CI). `tests/test_*backup*.py` DO invoke restore-smoke (seam 4), so restore-smoke
   IS exercised transitively in CI via the test corpus — just not by the install-smoke
   job. I corrected my own claim: restore-smoke runs in CI **through CANON-29 tests**,
   not directly. live-agent-tool-smoke's test references are deploy/docker test
   regressions that check the script is referenced, not that it runs live.

## OPEN FOR CODEX FEDERATION
1. Confirm NO `tests/**` file shells out to `ruff`/`pyflakes` (if one does, Python
   linting IS gated in CI via the python-regressions job — directly contradicting my
   drift #2). Grep `tests/` for `ruff`/`pyflakes`/`flake8`.
2. Confirm all `tests/test_*.py` are standalone-executable (have a `__main__` runner /
   non-zero exit on failure). If any rely on pytest fixtures with no `__main__`, that
   file is a silent no-op under `python3 file.py` — a hole in the gate (CANON-29
   territory but it directly weakens THIS gate's value).
3. Confirm `deploy.sh --apply-install` actually consumes every key the answers file
   writes (`ci-install-smoke.sh:44-121`) — unconsumed keys are dead config that could
   drift.
4. Verify the live-agent-tool-smoke retry/exec loop (`:467-473`) cannot infinite-loop
   (it gates on `ARCLINK_LIVE_AGENT_SMOKE_RETRY_ATTEMPT==0`, but an env leak could
   defeat that).
5. Whether the install-smoke job's 90-minute timeout is sufficient for a cold
   Nextcloud+qmd bring-up on a fresh ubuntu-22.04 runner (no cache) — a flaky timeout
   would make the gate non-deterministic.

## RISKS (severity-ranked, code-cited)
- **MEDIUM** — No Python style/lint gate in CI. `ruff`/`pyflakes` are pinned
  (`requirements-dev.txt:12-13`) but never invoked by any CANON-28 file; the only
  Python "lint" is `py_compile` on THREE modules (`ci-preflight.sh:197-203`). Syntax
  errors in the other 80+ python modules are caught only if a test imports them.
- **MEDIUM** — python-regressions gate quality is entirely delegated to CANON-29: a
  `tests/test_*.py` file that lacks a `__main__` runner runs to no-op exit 0 under
  `python3 file.py` (`install-smoke.yml:40`), silently passing. The workflow cannot
  detect "this file tested nothing."
- **MEDIUM** — install-smoke mutates the REAL host (creates users, installs the
  stack, brings up containers) and depends on passwordless sudo + `ubuntu-22.04`
  shape (`test.sh:14`, `ci-install-smoke.sh:39-42,2503`). It is heavy (90m timeout)
  and host-environment-sensitive; a partial failure mid-install relies on
  `trap on_exit` + `deploy.sh --apply-remove || true` (`:2443,:2492`) to not leave
  residue — the `|| true` means teardown failures are swallowed.
- **LOW** — Branch trigger drift: workflow runs on `arclink`, `master`, `main`
  (`install-smoke.yml:5-8`), but the repo's main branch is `main` and dev branch
  `arclink`; `master` is a dead trigger. Harmless but stale.
- **LOW** — preflight skips (not fails) when `systemd-analyze`/`inotifywait` are
  absent (`ci-preflight.sh:208-211,457-460,541-544,748-751`). On a minimal runner the
  watcher/notification/repo-sync fixtures silently DON'T run, reducing coverage with
  no signal beyond a `[preflight] … skipping` log line.
- **LOW** — `test.sh` only enables tailscale-serve when a logged-in tailscale exists
  (`test.sh:7-10`); on CI this branch is never exercised, so the tailscale ingress
  path is effectively untested by this gate.
- **INFO** — restore-smoke and live-agent-tool-smoke are titled as "smoke gates" but
  are NOT in the workflow; restore-smoke is exercised only transitively via CANON-29
  backup tests, live-agent-tool-smoke only in live deploy/docker flows
  (`bin/deploy.sh:5609`, `bin/arclink-docker.sh:2693`).
- **INFO** — PROMPT_test/lint/build.md are inert agent prompts, not gates; their
  inclusion in this piece is organizational, not load-bearing.

## VERDICT
CANON-28 provably gates exactly three things on every push/PR, and the seams to its
consumers are real and matched at both ends: (a) python-regressions runs each
`tests/test_*.py` directly under python3 3.11 (verified producer; corpus quality is
CANON-29's), (b) web-regressions runs `lint`/`test`/`build` whose scripts and test
files all exist (fully verified), and (c) install-smoke runs the full host
install/health/teardown via `deploy.sh --apply-install/--apply-remove`, with verified
arg-level seams to CANON-24, a clean trap-based teardown, and end-asserts that the
host is left clean. The preflight is a genuinely strong no-secret gate — it runs the
REAL pdf-ingest/vault-watch pipelines against the REAL control DB and asserts exact
status-json/notification shapes (status producer keys verified against
`pdf-ingest.py`). The live-agent-tool-smoke telemetry seam to the managed-context
plugin is exact (key + boolean + path all match).

Real weaknesses: (1) there is NO Python lint/style gate — ruff/pyflakes are pinned but
dead; (2) the python-regressions gate's value is only as good as CANON-29's
self-executing test convention, which the workflow cannot enforce; (3) the heaviest
gate (install-smoke) is host-mutating, sudo-dependent, and 90-minute, making it the
most fragile/flaky; (4) `master` is a dead branch trigger and the piece's own title
("smoke gates") overstates CI coverage by implying restore-smoke / live-agent-tool-smoke
run in CI when they do not (restore-smoke only transitively, live-agent-tool only in
live deploy). Net: the piece does its job for what it gates, but its name promises more
quality enforcement than the code delivers.
