# CANON-15 — Operator Upgrade Pipeline

> **Reconciliation note.** This section was produced by re-verifying the prior federated
> dissection (`DISSECT.md`, the 8-piece P1–P8 record signed by Claude Opus 4.8 + GPT-5.5) against
> the **current working tree** (branch `arclink`). DISSECT.md remains the authoritative deep proof
> for the broker (P4/P5) and host runner (P6/P7) and the infra seam (P8); this CANON section
> **owns** the two detector/policy files not carried as a standalone DISSECT piece
> (`arclink_pin_upgrade_check.py`, `arclink_upgrade_policy.py`), re-confirms DISSECT's load-bearing
> broker/runner claims line-by-line, records drift since DISSECT was written, and carries forward
> the DISSECT-confirmed risks **H1** and **M1–M6**. Where this CANON section and DISSECT.md cite
> the same line, the code was re-read here and the citation re-confirmed against the working tree
> (the two in-scope files carry uncommitted edits — see DRIFT §1).

## PIECE

CANON-15 is the **operator/pin upgrade pipeline**: the path that turns "an upstream advanced past a
pinned component" or "operator asked to upgrade" into an actually-executed `deploy.sh upgrade` /
`bin/component-upgrade.sh ... apply` on the host. It owns four tracked files:

- `python/arclink_pin_upgrade_check.py` — the **detector** (origination half). Runs hourly (or via
  `./deploy.sh pin-upgrade-notify`), scans `config/pins.json`, calls `bin/component-upgrade.sh <c>
  check` per managed component, runs a SQLite throttle state machine over
  `pin_upgrade_notifications`, builds one rolled-up operator digest, and registers a content-hashed
  pin-upgrade action via `arclink_control.register_pin_upgrade_action` (`:710-715`).
- `python/arclink_upgrade_policy.py` — a **source-owned, read-only policy catalog** (rollout order,
  preflight/proof-gate/rollback contracts per component). It is **NOT** in the broker→runner
  execution path; its only consumer is `arclink_operator_raven.py` (CANON-14) — see CROSS-PIECE §6
  and DRIFT §2.
- `python/arclink_operator_upgrade_broker.py` — the Docker-mode **broker** (P3/P4/P5 in DISSECT):
  authenticates HMAC requests, validates them, transforms them into a typed schema-v1 host-runner
  payload, writes it atomically to a private-state queue, and polls for the result.
- `python/arclink_operator_upgrade_host_runner.py` — the host **systemd-oneshot runner** (P6/P7 in
  DISSECT): drains the queue under a `flock`, re-validates each request fail-closed, and runs the
  canonical host upgrade flow.

No clearly-belonging file is missing from the list. The test `tests/test_arclink_pin_upgrade_detector.py`
exercises the detector (10 tests, re-run green here). The broker/runner are additionally exercised by
`tests/test_arclink_docker.py` (CANON-28/CANON-29).

## INPUT CONTRACT (code-verified)

### Detector (`arclink_pin_upgrade_check.py`)
- `run_detector(conn: sqlite3.Connection, cfg: Any) -> dict` (`:664`). `conn` is the control DB;
  `cfg` is read for `operator_notify_channel_id` / `operator_notify_platform` only (`:703-708`).
  Caller: `main()` (`:745-753`, `Config.from_env` + `connect_db`) and `arclink_ctl`/deploy
  `pin-upgrade-notify`.
- Inputs sourced from disk/subprocess, NOT the caller: `config/pins.json` via `_read_pins()`
  (`:99-100`, `json.loads(PINS_PATH.read_text())` — **no try/except**: a missing/corrupt pins.json
  raises out of `run_detector`); per-component `bin/component-upgrade.sh <c> check` via `_run_check`
  (`:197-221`, `subprocess.run([..], capture_output=True, text=True, timeout=60)`; any exception is
  swallowed into a synthetic `status: upstream-resolution-failed` string, `:217-221`).
- `MANAGED_COMPONENTS` = `(hermes-agent, hermes-docs, nvm, node, qmd, nextcloud, postgres, redis)`
  (`:58-67`). A component is scanned only if `config/pins.json` declares a non-empty `kind`
  (`:676-678`). **Note `hermes-docs` is scanned here but is NOT in the broker/runner execution
  allowlist** — see CROSS-PIECE §4.
- `_notify_limit(pins)` (`:343-352`): `int(pins["upgrade_notifications"]["notify_limit_per_release"])`,
  non-int / absent → `DEFAULT_NOTIFY_LIMIT = 1` (`:69`), clamped `max(1, min(value, 10))`.
- Network input (best-effort, for git-commit release labels): `_github_raw_text` GETs
  `raw.githubusercontent.com/<owner/repo>/<ref>/<path>` with a 10 s timeout (`:124-136`); every
  failure (`HTTPError/URLError/TimeoutError/OSError/UnicodeError`) degrades to `""`. This is the
  ONLY outbound network call in CANON-15 (the broker/runner make none).

### Broker (`arclink_operator_upgrade_broker.py`) — re-confirms DISSECT P4 INPUT CONTRACT
- HTTP entry `do_POST` (`:734`): path `==/v1/operator-upgrade` else 404 (`:735-737`);
  `Content-Length` int (ValueError→0), must be `0 < n <= MAX_REQUEST_BYTES(16384)` else 413
  (`:36,:739-744`); `_is_authorized(headers, raw_body)` before JSON parse else 401 (`:745-748`);
  body must UTF-8 decode + be a dict else 400 (`:749-756`).
- `_is_authorized` (`:686-716`): token env `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` vs header
  `X-ArcLink-Operator-Upgrade-Broker-Token`, both non-empty, `hmac.compare_digest` (`:687-690`);
  `int(timestamp)` (malformed → return False, `:696-699`); `abs(now-ts) <= 300` (`:700-701`); nonce
  `[A-Za-z0-9_.~+/=-]{16,160}` (`:703`); `_nonce_seen` replay check (`:705`); signature =
  `HMAC-SHA256(token, f"{timestamp}\n{nonce}\n{sha256hex(raw_body)}")` constant-time compared
  (`:707-714`); nonce recorded only on full success (`:715`).
- `run_operator_upgrade_request(request_body: dict) -> tuple[bool, dict|str]` (`:636`): trusted-host
  gate first (`require_docker_trusted_host_risk_accepted`, `:638`); `operation` ∈
  `{run_operator_upgrade, run_pin_upgrade}` (`:642,:646,:650`); else `ValueError`. Raw-command keys
  `args/cmd/command` rejected (`_reject_raw_commands`, `:139-141`, called at `:303,:496,:526` — the
  operation gate runs first, so rejection applies only to the two allowlisted operations).
- Request fields: `log_path` → `_require_operator_log_path` (`:307,:376-397`); `timeout_seconds` →
  `_operator_timeout` (`int(str(...).strip())`, default **7200**, clamp `[30,21600]`, `:368-373`);
  `upstream` used only if `isinstance dict` (`:255-257`); `install_items` (pin only) non-empty list
  of dicts each through `_normalized_pin_upgrade_item` (`:265-273`).
- Pin allowlists (the **enforcing boundary**): `ALLOWED_PIN_COMPONENTS =
  {hermes-agent, qmd, nextcloud, postgres, redis, nvm, node}` (`:48`); `SAFE_COMPONENT_RE`
  `^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$` (`:47`); `PIN_UPGRADE_FLAGS` 6-kind map (`:49-56`). Component
  must match regex AND be in the set (`:267`); kind must key the flag map (`:271`); `target`
  single-line ≤240 (`:270`).
- Host-derived env: `ARCLINK_DOCKER_HOST_REPO_DIR` (required, resolved, `:119-126`),
  `ARCLINK_DOCKER_HOST_PRIV_DIR` (required, absolute, `:110-116`),
  `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` (default `/home/arclink/arclink/arclink-priv`, must be
  absolute + contain `arclink-priv`, `:129-136`).

### Host runner (`arclink_operator_upgrade_host_runner.py`) — re-confirms DISSECT P6 INPUT CONTRACT
- Queue files: immediate `*.json` under `<queue_root>/pending` (`:403,:412`); each `json.loads`'d and
  must be a dict (`:371-373`). `_validate_request` (`:279-330`) re-checks from scratch (does NOT
  trust the broker): raw-command reject (`:280-281`); `int(schema_version or 0) == 1` (`:282-283`,
  **lax** — accepts `True`/`1.9`/`"1"`, see RISKS M-class INFO); `request_id` regex
  `^[a-z0-9][a-z0-9_.-]{7,80}$` (`:25,:284-286`); `operation` allowlist (`:287-289`);
  `repo_dir`/`priv_dir` if present must `resolve()`-equal this host's (`:290-295`); `log_path` forced
  under `<priv>/state/operator-actions` via `_require_child_path(mkdir_parent=True)` (`:296-302`);
  pin `install_items` each `_validated_pin_upgrade`'d **before any command runs** (`:321-329`).
- Path-derivation env: `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR` (`:69`, else `parents[1]`),
  `_PRIV_DIR` (`:80`, must resolve to a `arclink-priv`-named dir, `:82`), `_QUEUE_DIR` (`:88`, must be
  absolute — **no containment check**, the M1 asymmetry).

## OUTPUT CONTRACT (code-verified)

### Detector
- Return dict (`:733-742`): `{ok:True, scanned:[...], included:[...], silenced:[...], cleared:[...],
  digest:str, notified:bool, notify_limit:int}`.
- Side effects, only if `included` is non-empty (`:699-731`):
  1. `register_pin_upgrade_action(conn, items=_pin_upgrade_action_items(included),
     install_items=_pin_upgrade_install_items(pins, included), notify_limit=...)` (`:710-715`) →
     content-hashed token persisted in `settings` (CANON-01 owns that write).
  2. `queue_notification(conn, target_kind="operator", ...)` with the digest + button extras
     (`:723-730`) (CANON-01/05 own the notification table).
  3. `_mark_notified(conn, [components], notify_limit)` (`:731`) — `UPDATE
     pin_upgrade_notifications SET notify_count=notify_count+1, last_notified_at=?, silenced=CASE
     WHEN notify_count+1 >= ? THEN 1 ELSE silenced END` (`:516-532`) + commit.
- Per-component throttle writes (`_upsert_state`, `:386-513`), each committed inline:
  - transient upstream failure → no write, preserve row (`:411-414`);
  - `not upgrade_available or not target` with an existing row → `DELETE` (`:416-425`);
  - new row → `INSERT ... notify_count=0, silenced=0` (`:430-449`);
  - legacy raw-SHA→release-version migration → `UPDATE target_value/current_pin/extra_json`,
    preserving strikes (`:461-479`);
  - changed target → `UPDATE ... notify_count=0, silenced=0, last_notified_at=NULL, applied_at=NULL`
    (`:481-499`);
  - same target → `UPDATE current_pin/extra_json` only (`:503-509`).
- `_pin_upgrade_action_items` (`:615-627`): every included result with a non-empty `target`, shape
  `{component, kind, field, current, target, throttle_target}`.
- `_pin_upgrade_install_items` (`:630-659`): same shape, but **collapses** a component out if its
  `pins.components[c].inherits_from` parent is also included (`:643-646`) — this is what keeps
  `hermes-docs` out of the executable set when `hermes-agent` is present.

### Upgrade policy
- `upgrade_policy_for(component)` (`:274-280`) → one policy dict, or `ValueError` on unknown.
- `upgrade_policy_catalog()` (`:270-271`) → all policies sorted by `rollout_order`.
- `upgrade_policy_summary(component="")` (`:283-302`) → `{mode, ...}` with `mutation_performed:
  False` ALWAYS (read-only, proven — no DB/file/subprocess in this module).
- `normalize_upgrade_component` (`:265-267`) lower-cases, `_`→`-`, applies `_ALIASES` (`:248-262`).

### Broker — re-confirms DISSECT P4/P5 OUTPUT CONTRACT
- Host-runner payload (`:316-337`): `{schema_version:1, request_id:"op-<epoch>-<uuid4hex>",
  created_at:int, operation, repo_dir, priv_dir(resolved), container_priv_dir, log_path(str),
  timeout_seconds(int), upstream:dict}` + `install_items:[{component,kind,target}]` for pin.
  Written atomically (`_atomic_write_json`, `:295-299`, tmp `.{name}.{pid}.tmp` + `os.replace`) to
  `<queue_root>/pending/<id>.json` (`:338-339`). `json.dumps(payload, sort_keys=True)+"\n"`.
- Poll loop (`:340-365`): deadline `time.monotonic() + max(30, min(21630, timeout+30))`; poll interval
  `float(env or "1")` clamped `[0.05,5.0]` (**no try/except** — malformed env raises, M-class LOW).
  On result: dict + `ok is True` + `int(returncode)` → `{returncode:int, host_runner:True,
  request_id}` (`:360`); else distinct `RuntimeError`. Timeout → `RuntimeError(...check
  arclink-operator-upgrade-host-runner.timer...)` (`:362-365`).
- `run_operator_upgrade_request` → `(True, dict)` (`:644,:648`) or, on caught
  `OSError/RuntimeError/ValueError/SubprocessError`, **records a rejection incident** to
  `<host_priv>/state/docker/operator-upgrade-broker/rejections.jsonl` and returns `(False, str(exc))`
  (`:651-653`). HTTP: 200 `{ok:True, result}` / 400 `{ok:False, error}` (`:757-761`); GET `/health`
  → 200/503/404 (`:725-732`).

### Host runner — re-confirms DISSECT P6/P7 OUTPUT CONTRACT
- Exactly one result JSON per request via `_atomic_write_json` to `<queue_root>/results/<id>.json`
  (`:377,:391`): success `{ok:True, request_id, returncode:int, completed_at:int}` (`:382`); any
  `_run_request` exception (`except BaseException`, `:383`) → `{ok:False, request_id, error,
  error_class, completed_at}` (`:384-390`). **A non-zero child returncode is `ok:True`** — not an
  error.
- Request file moved to `<queue_root>/processed/<name>` (`os.replace`, else `unlink`, `:392-396`).
- Subprocess argv (the ONLY two shapes): `[<repo>/deploy.sh, "upgrade"]` (`:345,:363`) and per pin
  item `[<repo>/bin/component-upgrade.sh, component, "apply", flag, target, "--skip-upgrade"]`
  (`:276,:354`). Deploy-after-pin runs iff `_pin_upgrade_log_requires_deploy` is True (`:359-363`),
  i.e. unless every one of the last `len(install_items)` `ARCLINK_COMPONENT_UPGRADE_STATUS` markers
  is exactly `noop` (`:248-259`).
- `process_once`/`main` always return 0 on the happy path (`:414,:423`); the real returncode travels
  only in the result file. **No try/except around the drain loop** — H1.

## TOUCH POINTS

- **Env vars (detector):** none read directly; `cfg` carries `operator_notify_*` (read at
  `:703-708`). Indirectly: `config/pins.json` path is fixed (`:52`).
- **Env vars (broker):** `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` (`:98`),
  `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` (via `:638`→`boundary.py`),
  `ARCLINK_DOCKER_HOST_REPO_DIR`/`_PRIV_DIR`/`ARCLINK_DOCKER_CONTAINER_PRIV_DIR` (`:120,:111,:131`),
  `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED` (default on, `:250`),
  `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` (must be absolute + under `<priv>/state`, `:277-287`),
  `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` (`:341`),
  `ARCLINK_OPERATOR_UPGRADE_BROKER_HOST`/`_PORT` (`:771-776`), plus BASE/OPTIONAL child env keys on
  the (dead in shipped topology) in-process fallback (`:69-89,:204-246`).
- **Env vars (host runner):** `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR`/`_PRIV_DIR`/`_QUEUE_DIR`
  (`:69,:80,:88`); child env keys (`:43-63,:170-195`). Note the env-NAME family differs from the
  broker (M1).
- **DB tables (detector r/w):** `pin_upgrade_notifications` — schema cite
  `arclink_pin_upgrade_check.py:309-320` (defensive `CREATE IF NOT EXISTS`; authoritative schema in
  `arclink_control.ensure_schema`, CANON-01). Reads/writes: `SELECT *` (`:405-408`), `INSERT`
  (`:431-442`), `UPDATE`/`DELETE` (`:420-423,:465-506,:522-531`). Writes to `settings` and
  `notifications` are delegated to `arclink_control` (CANON-01).
- **Files/paths:** `config/pins.json` (detector read); `<queue_root>/{pending,results,processed}/`
  + `runner.lock` (broker writes pending + reads results; runner drains/writes results/processed);
  `<priv>/state/operator-actions/<...>.log` (operator execution log);
  `<host_priv>/state/docker/operator-upgrade-broker/rejections.jsonl` (broker rejection incidents).
- **Sockets/ports:** broker `ThreadingHTTPServer((host,port))` (`:765`), code default
  `127.0.0.1:8917` (`:39-40`), **compose overrides to `0.0.0.0:8917`** on `internal:true`
  `operator-upgrade-broker-net` (DISSECT P8). Runner opens no socket. Detector opens an outbound
  HTTPS GET to GitHub raw (`:133`).
- **Subprocess argv:** detector → `["bash", COMPONENT_UPGRADE_SH, component, "check"]` (`:204`);
  broker (fallback only) / runner → `deploy.sh upgrade` and `component-upgrade.sh ... --skip-upgrade`.
- **Locks:** broker in-process `_SEEN_SIGNATURE_NONCES_LOCK` (`:46`); runner file lock
  `fcntl.flock(LOCK_EX|LOCK_NB)` on `runner.lock` (`:404,:407-409`). Detector: none.
- **Secrets handling:** broker queue payload `upstream` carries only deploy-key/known-hosts **PATHS**
  (validated under private state, `:157-192`), never key content — so the plain `json.dumps` queue
  write leaks no secret (DISSECT P4 GAP-2, INFO).

## CODE-PATH TRACE

End-to-end, detector → executed upgrade (each hop a real line):

1. **Detect.** `run_detector` iterates `MANAGED_COMPONENTS`; per component
   `_run_check` (`pin_upgrade_check.py:680`) → `bin/component-upgrade.sh <c> check`; `_parse_check_output`
   (`:681`) extracts `pinned:`/`latest:`/`status:` and sets `upgrade_available` only for
   non-transient, non-`container-image`, non-`nvm-version` kinds where `"upgrade available" in
   status_line` (`:266-280`).
2. **Throttle.** `_upsert_state` (`:682`) decides `include` per the state machine; `_throttle_target`
   (`:355-360`) keys git-commit pins on the **release version** (`v0.11.0`), not the raw SHA, so
   commit churn inside one release does not restart alerts.
3. **Digest + register.** If any `include`, build the digest (`:709`), then
   `register_pin_upgrade_action(items=_pin_upgrade_action_items(included),
   install_items=_pin_upgrade_install_items(pins, included), ...)` (`:710-715`) — token is
   `sha256(json_dumps({items,install_items,notify_limit}))[:16]` (CANON-01 `arclink_control:9540`).
4. **Notify.** `queue_notification(... extra={pin_upgrade_action_token, telegram/discord button})`
   (`:723-730`); `_mark_notified` increments + silences at limit (`:731`).
5. **Operator queues.** Operator Raven lists active payloads via
   `list_pin_upgrade_action_payloads(active_only=True)` (`arclink_operator_raven.py:1281-1290`) and
   queues `operator_actions(action_kind="pin-upgrade", requested_target=token,
   request_source="operator-raven")` (`:1293-1318`).
6. **Dispatch + sign.** The enrollment provisioner re-hydrates the token, builds
   `_brokered_operator_payload(cfg, log_path)` + raw `install_items`, and HMAC-signs
   `f"{timestamp}\n{nonce}\n{sha256hex(body_bytes)}"` over `json.dumps(body, sort_keys=True)`
   (`arclink_enrollment_provisioner.py:310-330`), POSTing to `http://operator-upgrade-broker:8917`.
7. **Broker ingress + validate.** `do_POST` (`broker.py:734`) → size/auth/JSON gates →
   `run_operator_upgrade_request` (`:757`) → trusted-host gate (`:638`) → operation dispatch →
   `_run_host_runner_request` (`:644,:648`).
8. **Broker transform + enqueue.** `_run_host_runner_request` (`:302`) rejects raw commands, resolves
   host repo/priv, confines log path, clamps timeout, mints `request_id`, resolves queue root, builds
   schema-v1 payload (`:316-337`), `_atomic_write_json(pending/<id>.json)` (`:339`), then polls
   `results/<id>.json` (`:344-365`).
9. **Runner drain.** systemd timer (~5 s) → shim → `process_once` (`:399`): `flock(LOCK_EX|LOCK_NB)`
   (contention → `return 0`, `:407-411`); mtime-sorted glob `pending/*.json` (`:412`);
   `_process_request_file` per file (`:413`).
10. **Runner validate + execute.** `_process_request_file` (`:367`) pre-validates (lstat/JSON/id,
    **outside the try at :380 — H1**); inside the try, `_run_request` (`:381`) →
    `_validate_request` (`:334`) → `_require_repo_script` for both scripts (`:335-336`) →
    `_operator_env` (`:337`) → run `deploy.sh upgrade` and/or per-item `component-upgrade.sh ...
    --skip-upgrade` (`:344-364`); deploy-after-pin gated on the status markers (`:359`).
11. **Result round-trip.** Runner writes `results/<id>.json` atomically (`:391`), moves the request to
    `processed/` (`:394`). Broker reads it once, requires `ok:True` + int `returncode`, returns
    `{returncode, host_runner:True, request_id}` (`:352-360`); the provisioner consumes only
    `result["returncode"]` (`enrollment_provisioner.py:384`).

## CROSS-PIECE CONTRACTS (both ends verified)

1. **Detector → control plane (CANON-01).** Producer:
   `register_pin_upgrade_action(items, install_items, notify_limit)`
   (`pin_upgrade_check.py:710-715`) emitting items `{component, kind, field, current, target,
   throttle_target}` (`:615-627,:649-658`). Consumer: `arclink_control.register_pin_upgrade_action`
   normalizes each item (six keys), raises on blank `component`/`target`
   (`arclink_control.py:9502-9534`). **BOTH ENDS VERIFIED** — the detector always emits non-empty
   `component` (from `MANAGED_COMPONENTS`) and filters `if r.target` (`:626,:647`), so the control
   plane's blank-target raise is unreachable from this producer.
2. **Detector → operator dispatch token (CANON-14 → enrollment provisioner).** The token is queued as
   `requested_target` and re-hydrated by `get_pin_upgrade_action_payload`; the provisioner reads
   `install_items` only. The detector's `install_items` may legitimately differ from `items` (the
   parent-collapse at `:643-646`). **BOTH ENDS VERIFIED** via the control-plane read-back
   (`enrollment_provisioner.py` consumes `install_items`, dropping `field/current/throttle_target`).
3. **Provisioner → broker HMAC (CANON-08 → CANON-15).** Producer signs `HMAC-SHA256(token,
   f"{timestamp}\n{nonce}\n{sha256hex(body_bytes)}")` over `json.dumps(body, sort_keys=True)` and
   sends header `X-ArcLink-Operator-Upgrade-Broker-Token` (`enrollment_provisioner.py:310-330`).
   Consumer recomputes the identical pre-image over the **raw received bytes**
   (`broker.py:707-713`), with byte-identical header constants (`broker.py:41`==`provisioner:99`).
   Nonce `secrets.token_urlsafe(18)` (24 chars) ∈ `{16,160}`. **BOTH ENDS VERIFIED** (re-read here;
   matches DISSECT P2/P3 winner=both).
4. **Pin allowlist parity / `hermes-docs` collapse (CANON-15 internal + CANON-08).** Broker `:48-56`
   and runner `:26-34` carry **byte-identical** `ALLOWED_PIN_COMPONENTS` (7) and `PIN_UPGRADE_FLAGS`
   (6). The provisioner's `_pin_upgrade_apply_flag` (`:410-418`) replicates only the 6-kind flag map
   and does **NOT** enforce the component allowlist (M4). The detector's `MANAGED_COMPONENTS`
   includes `hermes-docs`, which is **NOT** in the broker/runner allowlist; the pipeline stays sound
   only because `_pin_upgrade_install_items` collapses `hermes-docs` out whenever its
   `inherits_from` parent `hermes-agent` is co-included (`pin_upgrade_check.py:643-646`;
   `config/pins.json:23-30` declares `inherits_from: hermes-agent`). **BOTH ENDS VERIFIED** — and the
   residual is recorded as a risk: a `hermes-docs`-only digest (parent already at target, docs
   behind) would produce an `install_items` entry the broker rejects with "component is not
   allowlisted" (LOW; see RISKS).
5. **Broker → runner request/result schema.** Producer payload keys (`broker.py:316-337`); consumer
   re-validates `schema_version==1`, identical `request_id` regex, operation allowlist,
   repo/priv equality, log confinement, pin items (`host_runner.py:279-330`). Result: runner writes
   `{ok, returncode|error, ...}` atomically (`host_runner.py:382-391`); broker requires `ok is True`
   + int `returncode` (`broker.py:352-360`). **BOTH ENDS VERIFIED** (re-read here; matches DISSECT
   P5/P6). The runner ignores the broker's `created_at` extra key (benign).
6. **Upgrade policy → Operator Raven (CANON-15 → CANON-14).** `arclink_operator_raven.py` imports
   `PIN_UPGRADE_COMPONENTS, STATEFUL_PIN_UPGRADE_COMPONENTS` (`:35`) and
   `policy_components_by_scope, upgrade_policy_summary` (`:1207`) for the read-only `/upgrade_policy`
   router. **BOTH ENDS VERIFIED**: the policy module is consumed ONLY here; it does NOT touch the
   broker/runner path. Its `PIN_UPGRADE_COMPONENTS` uses `"hermes"` while the executable allowlist
   uses `"hermes-agent"` — a naming drift that is benign because the two sets never meet in code
   (DRIFT §2).
7. **Runner → `component-upgrade.sh` status markers (CANON-15 → CANON-31/CANON-24).** Producer
   `status_marker(){ printf 'ARCLINK_COMPONENT_UPGRADE_STATUS=%s\n' ...}` (`bin/component-upgrade.sh:46`);
   under `--skip-upgrade` exactly one terminal marker per apply — `noop` (`:637`), `pushed` (only
   when an uncommitted pins.json diff / HEAD-not-on-upstream forces a push, `:618-637`), or `changed`
   (`:668`); the `:665` marker and every `reexec_upgrade` are guarded by `skip_upgrade != 1`
   (`:624,:632,:664`). Consumer `_pin_upgrade_log_requires_deploy` reads the last
   `len(install_items)` markers and runs deploy unless all are `noop` (`host_runner.py:248-259`).
   **BOTH ENDS VERIFIED** — single-marker-per-item holds, so the tail-N slice is sound.

## CODE vs COMMENT/DOC/NAME DRIFT

1. **Uncommitted working-tree edits in BOTH in-scope execution files (since DISSECT).**
   `git diff HEAD` confirms two edits that match DISSECT's working-tree provenance notes:
   - `broker.py` — the `_host_runner_result_error` helper is **deleted** and the `ok!=True` error
     message is **inlined** from the already-loaded dict (`broker.py:352-355`). Committed HEAD
     `63a42c8` still re-reads the result file via the helper. DISSECT P5 flagged this exactly; it
     remains uncommitted. Reviewers diffing HEAD will see the helper.
   - `host_runner.py` — `_pin_upgrade_command` is refactored into `_validated_pin_upgrade`
     (`:262-276`) and `_validate_request` now **validates-then-forwards the raw `install_items`**
     (`:328-329`) instead of reconstructing normalized dicts. Behavior preserved (every item still
     validated before any command); DISSECT P6 cites the post-edit line numbers, which match the
     working tree.
2. **`arclink_upgrade_policy.PIN_UPGRADE_COMPONENTS` says `"hermes"`; the executable allowlist says
   `"hermes-agent"`.** `upgrade_policy.py:10` lists `"hermes"`; broker/runner
   `ALLOWED_PIN_COMPONENTS` list `"hermes-agent"` (`broker.py:48`, `host_runner.py:26`). The
   module-level `_POLICIES` also keys on `component="hermes"` / `"hermes-docs"` (`:68,:90`). This is a
   **name drift across pieces** but **non-load-bearing**: the policy catalog is display-only and never
   crosses into the broker path (CROSS-PIECE §6). Code wins — there is no `"hermes"` in the
   allowlist, and nothing reconciles the two names.
3. **Docstring vs code, detector "delete stale row".** The module docstring step 3 says "If pin
   advanced past the tracked target ... delete the stale row" (`:20-22`). The code deletes whenever
   `not upgrade_available or not target` for an existing row (`:416-425`) — i.e. also when upstream
   merely stops reporting an upgrade (rollback, transient-but-non-flagged). Slightly broader than the
   docstring's "applied or bumped" framing; behavior is the code's.
4. **`config/docker-authority-inventory.json` prose still says "writeable Docker socket" / egress
   network** for the broker (`:205,:316,:2269,:2306,:2419`) while the structured fields are correct
   (`docker_socket:"none"` `:2229`, `egress_networks:[]` `:2245`) and match compose. Carried forward
   as **M5** (DISSECT P8). The drift test asserts only structured fields, so the stale prose passes
   CI.
5. **DISSECT cosmetic citation drift (P6/P7).** DISSECT's per-file header for P6 writes
   "`/root/arclink/deploy.sh`, `/root/arclink/bin/component-upgrade.sh`" as the execed consumers; the
   runner resolves `deploy.sh` (repo-root wrapper) and `bin/component-upgrade.sh` (`host_runner.py:335-336`).
   No functional drift — `deploy.sh` is the repo-root script that execs `bin/deploy.sh "$@"`.

## ADVERSARIAL SELF-CHECK

The claims I am least sure of (what would falsify each):

1. **"`hermes-docs` can never reach the broker allowlist rejection in practice."** I proved the
   `inherits_from` collapse (`:643-646`) and that `hermes-docs` is excluded only when `hermes-agent`
   is co-included. I did NOT exhaustively prove that the detector can never emit a `hermes-docs`-only
   digest (e.g. parent at target but docs ref behind). FALSIFIER: a detector run where
   `hermes-agent` is `noop` (not included) but `hermes-docs` has an available upgrade → `install_items`
   contains `hermes-docs` → broker rejects. I rate this LOW (the docs ref is normally bumped with the
   runtime), but it is not impossible. **Open for Codex.**
2. **"The detector's only outbound network is GitHub raw, fully fail-soft."** I read `_github_raw_text`
   (`:124-136`) and the `except` tuple. FALSIFIER: a code path where a label-lookup exception is NOT
   in that tuple and escapes `_git_commit_release_label`. The `_pyproject_metadata` fallback uses a
   broad `except Exception` (`:149`), so I believe it holds, but `_github_owner_repo` regex on a
   malformed repo URL returning `""` (`:120`) was only spot-checked.
3. **"Status-marker single-emission under `--skip-upgrade` is guaranteed."** I read `do_apply`
   (`component-upgrade.sh:611-669`) and confirmed the `skip_upgrade != 1` guards. FALSIFIER: a kind
   whose apply path (`:543-609`, the non-noop branch) emits an intermediate marker before line 668 —
   I did not read every per-kind apply branch above line 605. The DISSECT P7 ratifier asserted single
   emission with cites `:611,:637,:664,:668`; I re-read 605-669 only.
4. **"`_upsert_state` commits leave no half-written throttle state under concurrency."** Each branch
   commits inline, but the detector assumes a single hourly runner. FALSIFIER: two concurrent
   `run_detector` passes (timer + manual `pin-upgrade-notify`) interleaving SELECT/UPDATE on the same
   `component` PRIMARY KEY row — there is no row lock or `BEGIN IMMEDIATE`. SQLite's default isolation
   would serialize writes but could double-notify. Not proven safe; rated INFO.
5. **"The working-tree edits change no behavior."** I diffed both edits and reasoned they are
   refactors. FALSIFIER for `host_runner`: forwarding the **raw** `install_items` (rather than the
   normalized `{component,kind,target}`) means extra keys now survive into the request used by
   `_run_request`; `_pin_upgrade_command` re-validates, so argv is identical — but if any future code
   read other item keys off `request["install_items"]`, behavior would differ. Currently none does.

## OPEN FOR CODEX FEDERATION

The claims most worth an independent GPT-5.5 cross-check:

1. **`hermes-docs`-only `install_items` reachability.** Can the detector emit an `install_items` list
   containing `hermes-docs` without `hermes-agent` (parent `noop`/excluded, docs upgrade available)?
   If yes, the broker rejects with "component is not allowlisted" — confirm severity and whether the
   detector should map `hermes-docs`→`hermes-agent` before queueing.
2. **`upgrade_policy` "hermes" vs "hermes-agent" name drift.** Confirm there is no consumer that
   bridges `PIN_UPGRADE_COMPONENTS` (policy names) into the broker allowlist (component-upgrade.sh,
   operator_raven action queueing). I found only the read-only `/upgrade_policy` router; verify no
   `/pin_upgrade hermes` path passes the literal `"hermes"` into `install_items`.
3. **Detector concurrency.** Independent confirmation that overlapping detector runs (hourly timer +
   on-demand `deploy.sh pin-upgrade-notify`) cannot corrupt `pin_upgrade_notifications` or
   double-register a token — the throttle state machine has no explicit lock.
4. **H1 reproduction on the current working tree.** DISSECT empirically reproduced the dangling-symlink
   drain crash at `host_runner.py:412`. Re-confirm the sort-key `item.stat()` still precedes the
   `_process_request_file` lstat guard after the working-tree refactor (it does in my read).
5. **M3 still live.** Confirm `dismiss_pin_upgrade_action` (CANON-01) still sets `silenced=1` without
   `applied_at`, and that `list_pin_upgrade_action_payloads(active_only=True)`
   (`operator_raven.py:1281-1290` consumer) still returns dismissed-but-unapplied items.

## RISKS (severity-ranked, code-cited)

- **[HIGH] H1 — Poison/dangling-symlink file permanently wedges the host-runner drain.**
  `_process_request_file` raises for non-regular/symlink (`host_runner.py:367-370`), non-JSON/non-dict
  (`:371-373`), or bad request-id (`:374-376`) — all **before** the `try:` at `:380`. A *dangling*
  symlink `*.json` fails even earlier in the glob **sort key** `item.stat().st_mtime` (`:412`).
  Neither `process_once` (`:399-414`) nor `main` (`:417-423`) wraps the loop, so the exception aborts
  the whole pass; the file is never moved to `processed/` and is re-globbed every ~5 s — permanently
  blocking all queued upgrades. The broker side then just times out (`broker.py:362`). Trusted-host
  boundary (not remotely exploitable), but a real availability dead-lock. Cite:
  `python/arclink_operator_upgrade_host_runner.py:412,367-376,380,417-423`.
- **[MEDIUM] M1 — Queue-root agreement is deploy-enforced, not code-enforced.** Broker
  containment-checks its queue dir `relative_to(<host_priv>/state)` and defaults from
  `ARCLINK_DOCKER_HOST_PRIV_DIR` (`broker.py:278,283-287`); the runner's `_queue_root` does **only**
  an `is_absolute()` check (no containment) and defaults from a **different** env var
  `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR` (`host_runner.py:87-92`). Compose/deploy.sh wire both to
  the same path, so they agree as shipped; config drift desyncs them and every request silently times
  out. Cite: `python/arclink_operator_upgrade_host_runner.py:87-92`.
- **[MEDIUM] M2 — Nonce replay: TOCTOU window + non-persistent store.** The broker releases the lock
  between `_nonce_seen` (`broker.py:665-671`) and `_record_nonce` (`:674-683`), doing HMAC work
  in between on a per-request thread (`:765`), so two concurrent identical signed requests can both
  pass. The store is an in-memory global (`:45`) wiped on restart, so a captured request inside the
  ±300 s window replays once after a broker restart. Cite:
  `python/arclink_operator_upgrade_broker.py:665-683`.
- **[MEDIUM] M3 — Dismissed pin upgrade remains listable as "active".** (Lives in CANON-01, but is
  the visible failure of THIS pipeline.) `dismiss_pin_upgrade_action` sets `silenced=1` but never
  `applied_at` (`arclink_control.py:9683-9703`), while `_active_pin_upgrade_targets` filters only on
  `applied_at IS NULL` (`:9601`). The detector never assigns a non-null `applied_at` (only resets to
  NULL, `pin_upgrade_check.py:487`), so a dismissed item keeps satisfying the "active" filter that
  Operator Raven queues from. Cite: `python/arclink_pin_upgrade_check.py:487`.
- **[MEDIUM] M4 — Component allowlist is enforced only on the Docker broker/runner path.** The
  control-plane `register_pin_upgrade_action` accepts any non-empty `component`
  (`arclink_control.py:9512`); the non-Docker provisioner `_pin_upgrade_command_args` validates only
  `kind` (`enrollment_provisioner.py:429-448`). Only the broker (`broker.py:267`) and runner
  (`host_runner.py:264`) enforce the 7-name allowlist — the "byte-identical across three modules"
  framing is false (the provisioner has no component allowlist). Cite:
  `python/arclink_operator_upgrade_broker.py:267`.
- **[MEDIUM] M5 — Authority-inventory prose contradicts the real boundary.**
  `config/docker-authority-inventory.json` still carries prose saying "writeable Docker socket"
  (`:205,:2269,:2306,:2419`) and an egress network (`:316`) while structured fields are correct
  (`docker_socket:"none"` `:2229`, `egress_networks:[]` `:2245`) and match compose. The drift test
  asserts only structured fields, so the stale prose passes CI. Cite (this piece's anchor — the
  broker has no socket mount): `python/arclink_operator_upgrade_broker.py:866` (no socket in
  `_operator_env`; broker never opens docker.sock).
- **[MEDIUM] M6 — Provisioner decode/HTTP error paths can escape the handler.** On success,
  `response.read().decode("utf-8")` (`enrollment_provisioner.py:335`) can raise `UnicodeDecodeError`
  (a `ValueError`, not in the caught `OSError/URLError/TimeoutError/JSONDecodeError` tuple, `:342`);
  a non-dict JSON `HTTPError` body also escapes normalization (`:336-341`). Bounded: a stale
  `running` row is reaped on the next provisioner cycle. (Producer-side, CANON-08.) Cite:
  `python/arclink_enrollment_provisioner.py:335,342`.
- **[LOW] `hermes-docs` allowlist rejection.** A `hermes-docs`-only `install_items` (parent not
  co-included) would be rejected by the broker as "component is not allowlisted"; the pipeline relies
  on the `inherits_from` collapse to avoid it. Cite: `python/arclink_pin_upgrade_check.py:643-646`.
- **[LOW] Malformed `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` aborts the request.** `float()`
  has no try/except (`broker.py:341`); a non-numeric value raises, is caught by the outer handler, and
  the whole request fails instead of defaulting to 1 s. Cite:
  `python/arclink_operator_upgrade_broker.py:341`.
- **[LOW] Detector `pins.json` read is unguarded.** `_read_pins` does `json.loads(read_text())`
  (`pin_upgrade_check.py:99-100`) with no try/except; a missing/corrupt pins.json raises out of
  `run_detector`. Acceptable for a source-controlled file, noted. Cite:
  `python/arclink_pin_upgrade_check.py:99-100`.
- **[LOW] Constants triplicated across the trust boundary.** `ALLOWED_PIN_COMPONENTS`,
  `PIN_UPGRADE_FLAGS`, `REQUEST_ID_RE`, `HOST_RUNNER_SCHEMA_VERSION`, `UPSTREAM_ENV_KEYS` are
  independently re-declared in broker, runner, and (partial) provisioner with no shared import;
  byte-identical today, drift-prone. Cite: `python/arclink_operator_upgrade_host_runner.py:23-42`.
- **[INFO] `schema_version` / `returncode` / `container_priv_dir` laxity.** Runner `int(x or 0)==1`
  accepts `True`/`1.9`/`"1"` (`host_runner.py:282`); broker `int(result.get("returncode"))` accepts
  `"3"`/`3.9`/`True` (`broker.py:357`); runner single-line-checks `container_priv_dir` without the
  broker's absoluteness/arclink-priv re-check (`host_runner.py:308-310`). All reachable only by direct
  queue tampering inside the trusted host boundary; broker always writes clean values. Cite:
  `python/arclink_operator_upgrade_host_runner.py:282`.
- **[INFO] `upgrade_policy` "hermes" name drift.** `PIN_UPGRADE_COMPONENTS` uses `"hermes"` vs the
  allowlist's `"hermes-agent"`; benign (display-only module, never crosses into the broker path).
  Cite: `python/arclink_upgrade_policy.py:10`.

## VERDICT

**Provably YES for the proven scope, with two named soft spots.** The detector
(`arclink_pin_upgrade_check.py`) is a deterministic, fail-soft state machine: it scans
`config/pins.json`, runs `component-upgrade.sh <c> check` per managed component, throttles per
**release-version** (not raw SHA) so commit churn does not re-alert, builds exactly one operator
digest per run, and emits a content-addressed action whose executable `install_items` correctly
collapse inheritors (`hermes-docs`→`hermes-agent`). Its only network call is fully fail-soft, and its
test suite passes (10/10, re-run here). The upgrade-policy module is provably read-only
(`mutation_performed: False` always) and provably out of the execution path (sole consumer is
Operator Raven's display router). The broker and host runner — the deep proof of which lives in
DISSECT.md P4–P8 and was re-confirmed line-by-line here against the working tree — authenticate every
request (HMAC over `ts\nnonce\nsha256(body)`, TTL- and nonce-protected), fence behind the
trusted-host gate, allowlist exactly two operations and seven pin components, perform a deterministic
typed transform into a schema-v1 queue payload, and execute only two hard-coded, symlink-checked
scripts with reconstructed argv. All seven cross-piece seams verify at both ends.

**Real weaknesses (carried forward, not closed):** liveness — not authority — is the underbelly.
**H1** (a single poison/dangling-symlink pending file permanently wedges the drain, with no
try/except around the loop) is the single most material defect and is contained only by the
trusted-host boundary. **M1** (queue-root agreement deploy-enforced via mismatched env-var names and
asymmetric containment checks) and **M3** (a dismissed pin upgrade stays queue-able because
`applied_at` is never set) are the two most likely real-world surprises. The two in-scope execution
files carry **uncommitted working-tree edits** (the broker's single-read inlining and the runner's
validate-then-forward refactor) — the audited behavior is what runs now but is not yet in committed
HEAD `63a42c8`. The `upgrade_policy` "hermes"/"hermes-agent" naming drift and the inventory prose
drift (M5) are documentation-class and non-load-bearing. Net: the pipeline is well-guarded against an
adversary and under-guarded against entropy.
