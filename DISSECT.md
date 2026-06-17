# DISSECT.md — ArcLink Operator-Upgrade Pipeline, Federated Code-Path Dissection

> **What this is.** A two-model "Federation" dissection of the operator-upgrade pipeline as it
> stands in canon right now (branch `arclink`, working tree). Every one of the 8 pipeline pieces
> was audited **independently and in full** by both a **Claude Opus 4.8 (xhigh)** auditor and a
> **GPT-5.5 (xhigh, via Codex CLI)** auditor — 100% overlap. The two audits per piece were then
> **reconciled by a Claude adjudicator that re-verified every disputed claim against the real code**,
> and finally **ratified by an independent GPT-5.5 pass** that re-checked the merged record line by
> line. Both model families have signed every piece.
>
> **Binding method (enforced in every prompt):** prove, do not guess. Comments and docstrings are
> *not evidence* — only executed code paths are. Every load-bearing claim cites `path:line`. Where
> code and comment disagree, the code wins and it is called out.

## Federation provenance (audit trail)

| Stage | Engine | Output |
|---|---|---|
| Independent audit (round 1) | 8× Claude Opus 4.8 xhigh **and** 8× GPT-5.5 xhigh | 16 full audits |
| Convergence + adjudication | 8× Claude reconciler (xhigh), re-verifying both audits vs code | 8 merged records, **38 cross-model disagreements adjudicated** |
| Ratification (round 2) | 8× GPT-5.5 xhigh skeptic | 8 sign-offs, **74 independent code re-confirmations**, 35 refinements |

**Adjudication tally over the 38 disagreements:** GPT-5.5 auditor correct **22**, both correct **12**,
Claude auditor correct **2**, both over-stated (severity rejected) **2**. Read literally: the GPT-5.5
auditors were the more aggressive edge-hunters (they surfaced most of the unhappy-path defects), and
the Claude convergence layer independently confirmed those edges in code rather than averaging them
away. The GPT-5.5 ratifier returned `OBJECT`-with-refinements on all 8 pieces — not rejections, but
precise corrections (off-by-one citations, severity calibration, and several *additional* edges),
each of which is folded into the records below.

---

## The pipeline, proven end-to-end

This is the actual dataflow, each hop proven from executable code (not comments):

1. **P1 — Origination.** A detector/Raven intent enters `register_pin_upgrade_action()`
   (`python/arclink_control.py:9518`). Each item is normalized to exactly
   `{component, kind, field, current, target, throttle_target}` (`:9502-9515`; blank component or
   target raises). The payload core `{items, install_items, notify_limit}` is content-hashed
   `sha256(json.dumps(sort_keys=True))[:16]` into a token (`:9540`) and upserted into the `settings`
   table under key `pin_upgrade_action:<token>` (`:9546`). Operator-**upgrade** (vs pin) intent is
   surfaced as notification-button extras embedding the stripped upstream commit in callback data
   (`:9762`), but its execution path runs a **generic configured host upgrade**, not a commit-targeted
   dispatch (ratifier P1-obj1).
2. **P2 — Dispatch + signing.** The enrollment provisioner reads the payload and POSTs to
   `http://operator-upgrade-broker:8917` (`python/arclink_enrollment_provisioner.py:289-335`). It
   HMAC-signs (`:316-320`) the exact bytes `f"{timestamp}\n{nonce}\n{body_hash}"` where
   `body_hash = sha256(body).hexdigest()`, keyed by the shared broker token, and sends the token,
   timestamp, nonce, and signature headers alongside the JSON body.
3. **P3 — Broker ingress.** `do_POST` (`python/arclink_operator_upgrade_broker.py:734`) verifies, in
   order: bearer token via `hmac.compare_digest` (`:689`), ±300 s timestamp window (`:701`), nonce
   format regex + replay rejection (`:703-705`), and an HMAC recomputed over the **raw wire bytes**
   `f"{timestamp}\n{nonce}\n{body_hash}"` (`:707-713`). **The signed string and the verified string
   were independently re-confirmed byte-identical at both ends** (P3 disagreement, winner: both).
4. **P4 — Validation -> payload.** `run_operator_upgrade_request` (`:648`) rejects raw command keys,
   gates on `_host_runner_enabled` (default on, `:250`), and builds a typed payload dict with
   `schema_version=1` (`:317`), a fresh `request_id`, resolved `repo_dir`/`priv_dir`, a confined
   `log_path`, a clamped `timeout_seconds` (default **7200**, clamp `[30,21600]`), normalized
   `upstream`, and (for pin upgrades) `install_items` each validated against the 7-component / 6-kind
   allowlist.
5. **P5 — Queue handoff + poll.** `_run_host_runner_request` (`:312`) atomically writes the payload to
   `pending/<id>.json` under `<host_priv>/state/operator-upgrade-host-runner` (`:283-286`, `:348-349`)
   and polls `results/<id>.json` (`:354-369`) until `wait_seconds = clamp(timeout+30, 30, 21630)`,
   then reads the result exactly once, requiring `ok is True` and an integer `returncode`.
6. **P6 — Runner ingress.** A systemd timer (every ~5 s) runs the shim -> `process_once` (`:401`),
   which takes a non-blocking `flock` (`:411`; a second concurrent run simply returns), mtime-sorts
   `pending/*.json` (`:414`), and re-validates each request from scratch in `_validate_request`
   (`:274-332`): `schema_version==1`, request-id regex, operation allowlist, supplied
   `repo_dir`/`priv_dir` **must equal this host's**, `log_path` forced under
   `state/operator-actions`, and every `install_item` validated up-front before any command runs.
7. **P7 — Execution.** `_run_request` (`:335`) resolves the allowlisted scripts via
   `_require_repo_script` (rejects symlink/non-regular/non-exec/escape, `:123-150`) and runs, with a
   pruned child env (`_operator_env`, `:168-202`), either `deploy.sh upgrade`, or per pin item
   `component-upgrade.sh <component> apply <flag> <target> --skip-upgrade` followed by a **conditional**
   `deploy.sh upgrade` decided by parsing `ARCLINK_COMPONENT_UPGRADE_STATUS=` markers (`:236-259`).
8. **P8 — Wiring.** `compose.yaml` runs the broker as `user 0:0` on an `internal: true` network with
   **no `ports:` mapping and no `docker.sock` mount** (`:842-872`); `bin/deploy.sh` installs the host
   systemd timer/service that execs the **bare-`python3`** shim (`:8366-8417`); the runner is
   deliberately stdlib-only. The container broker's queue dir and the host runner's queue dir are
   wired to the same host path **by deployment env, not by code**.

---

## Findings, severity-ranked (both-model confirmed)

### [HIGH] H1 — A single poison/dangling-symlink file permanently wedges the entire host-runner drain
**Converged independently by P6, P7, and P8; empirically reproduced; ratified by both models.**
In `python/arclink_operator_upgrade_host_runner.py`, `_process_request_file` raises for a non-regular
or symlink file (`:367-370`), a non-JSON / non-dict body (`:371-373`), or a bad request-id
(`:374-376`) — and all of these are **before** the `try:` at `:380` that converts errors into an
`ok:false` result. Worse, a *dangling* symlink named `*.json` fails even earlier, at the glob **sort
key** `item.stat().st_mtime` (`:414`), before `_process_request_file` is ever called. Neither
`process_once` (`:401-416`) nor `main` (`:419-425`) wraps the loop in `try/except`, so the exception
propagates out and aborts the whole pass. Consequence: **no result file is written, the offending
file is never moved to `processed/`, and it is re-globbed on every ~5 s timer tick — permanently
blocking every other queued operator upgrade** with no self-recovery. The matching broker side
(`_run_host_runner_request`) then simply times out (P5). This is inside the trusted-host boundary (so
not remotely exploitable), but any corrupt, partial, or leftover file silently dead-locks all
upgrades. *Fix shape: wrap the per-file body (including the `item.stat()` sort key) so a bad entry is
quarantined to a failed-result + moved aside, never aborting the drain.*

### [MEDIUM] M1 — Queue-root agreement is deploy-enforced, not code-enforced (producer/consumer can silently split)
The broker containment-checks its configured queue dir `relative_to(<host_priv>/state)`
(`broker.py:283-286`) and defaults it from `ARCLINK_DOCKER_HOST_PRIV_DIR` (`:278`). The host runner's
`_queue_root` performs **only** an `is_absolute()` check — **no containment** (`host_runner.py:87-92`)
— and derives its default from a **different** env var (`ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR`).
`compose.yaml` + `bin/deploy.sh` (`:8395-8397`, `:8493-8494`) wire both to the same host path, so they
agree *as shipped*; nothing in code guarantees it. A config drift (or a different `docker.env`
consumed by `bin/arclink-docker.sh`, ratifier P8-obj2) puts the broker's writes and the runner's
reads on different queues — the broker enqueues, the runner never drains, every request times out.

### [MEDIUM] M2 — Nonce replay: TOCTOU window + non-persistent store
`broker.py` releases the lock between `_nonce_seen` (check, `:667-671`) and `_record_nonce` (record,
`:676-683`), doing HMAC work in between, and `ThreadingHTTPServer` services each request on its own
thread (`:764-766`) — so two concurrent identical signed requests can **both** pass the replay check
(P3, winner: codex). Separately, the nonce store is an in-memory module global (`:45`) wiped on
restart, so a captured request still inside the ±300 s window replays **exactly once** after any
broker restart (P3, winner: both, MEDIUM). Ratifier adds: a malformed numeric timestamp can make
`int(timestamp_raw)` (`:697`) raise and **abort the handler** rather than return the documented 401
(P3-obj2).

### [MEDIUM] M3 — Dismissed pin upgrade remains listable as "active"
`dismiss_pin_upgrade_action` sets `silenced=1` but never sets `applied_at`
(`control.py:9683-9703`), while `_active_pin_upgrade_targets` filters **only** on `applied_at IS NULL`
and ignores `silenced` (`:9601`). A repo-wide grep confirms `pin_upgrade_notifications.applied_at` is
**never assigned a non-null value anywhere in production** (only reset to NULL). So a dismissed item
keeps satisfying the "active" filter (P1, winner: codex).

### [MEDIUM] M4 — Component allowlist is enforced only on the Docker path
`register_pin_upgrade_action` accepts any non-empty `component` (`control.py:9512`). The Docker broker
and host runner enforce the 7-name `ALLOWED_PIN_COMPONENTS` + 6-kind `PIN_UPGRADE_FLAGS`
(`broker.py:265-272`, `host_runner.py:262-271`), but the **non-Docker** `_pin_upgrade_command_args`
validates only `kind` and accepts any non-empty component (`enrollment_provisioner.py:429-448`). The
"byte-identical across all three" framing is therefore false — the provisioner has **no** component
allowlist and relies entirely on downstream (P4, ratifier P4-obj1).

### [MEDIUM] M5 — Authority-inventory prose contradicts the real (and structured) boundary
`config/docker-authority-inventory.json` still carries **4 prose lines saying "writeable Docker
socket"** (`:205,2269,2306,2419`) and one claiming an **egress network** for the broker (`:316`),
while the structured fields are correct (`docker_socket: "none"` `:2229`; `egress_networks: []`
`:2245`) and match the real compose (no socket mount, only the `internal:true`
`operator-upgrade-broker-net`). The drift test asserts equality **only** on the structured fields
(`tests/test_arclink_docker.py:1755-1788`), so the stale, now-false prose passes CI (P8, winner:
codex). *This directly post-dates the very commit that removed the socket — the prose was not updated.*

### [MEDIUM] M6 — Provisioner decode/HTTP error paths can escape the handler
On the **success** path, `response.read().decode("utf-8")` (`enrollment_provisioner.py:335`) can raise
`UnicodeDecodeError`, which (MRO-verified) is a subclass of `ValueError` but **not** of the caught
`OSError/URLError/TimeoutError/JSONDecodeError` tuple (`:342`), so it propagates (P2, winner: codex).
Ratifier adds: a valid **non-dict** JSON `HTTPError` body also escapes the error-normalization at
`:336-341` (P2-obj1). Both are **bounded**, not unbounded: `_fail_stale_running_operator_actions`
(stale_seconds = 30 min) reaps the stranded `running` row on the next provisioner cycle
(`:613-641,2322,2440`) (ratifier P2-obj4).

### [LOW / INFO] (proven, low impact)
- **Working-tree caveat (P5):** the result-file *single-read + inlined error message* described here
  is an **uncommitted working-tree edit**. Committed `HEAD` (`63a42c8`) still re-reads the result file
  via the `_host_runner_result_error` helper. The converged P5 record reflects the **working tree**,
  not `HEAD` — reviewers diffing against `HEAD` will see the helper still present (P5, MEDIUM-as-process
  note, winner: codex via `git show`).
- **Blank `log_path` -> cwd (P4):** `Path("").resolve()` is cwd, which `_require_operator_log_path`
  would accept as a directory — but as shipped `WORKDIR=/home/arclink/arclink` is **not** under
  `arclink-priv/state/operator-actions`, so a blank value is rejected anyway (`Dockerfile:71`,
  `compose.yaml:859`).
- **`returncode` coercion (P5):** `int(result.get("returncode"))` (`:357`) would accept `"3"`/`3.9`/
  `True`; the **sole** producer writes a genuine JSON int (`host_runner.py:382`) over an atomic write,
  so it is not reachable in practice.
- **`schema_version` laxity (P6):** `int(x or 0)==1` accepts `True`/`1.9`/`"1"`; only reachable by
  direct queue tampering inside the trusted host boundary (broker always writes integer `1`).
- **Runner forwards single-line-only upstream paths (P6/P7):** for **broker-produced** requests this
  is safe (the broker path-confines deploy-key/known-hosts paths, `broker.py:157-192`); only
  hand-crafted pending files (trusted-boundary write) bypass that.
- **No socket/read timeout on the listener (P3):** bounded by `MAX_REQUEST_BYTES=16384` and internal-net
  containment.

---

## Cross-cutting observations

1. **The trust model is "the queue directory is sacred."** Almost every LOW/INFO defect (schema_version
   laxity, returncode coercion, single-line-only path forwarding, raw-file validation gaps) is gated
   behind "only something with write access to `<host_priv>/state/.../pending` can reach it." That is a
   sound boundary — **but H1 shows the same directory is also the pipeline's single point of failure**:
   one bad file there is both *harmless to security* and *fatal to liveness*. The drain needs to treat
   its own queue as potentially hostile to *availability*, even while trusting it for *authority*.
2. **Constants are triplicated across a trust boundary and already drifting in prose.** The pin
   allowlist/flag maps live in the provisioner (partial), broker, and host runner; the schema version
   lives in broker and runner. They agree today only by hand. M4 (provisioner lacks the component
   allowlist) and M5 (inventory prose drift) are two faces of the same altitude problem: **the contract
   is copied, not shared.** A single read-only contract module (constants + the validators), imported
   by all three, plus a test asserting `broker.SCHEMA == runner.SCHEMA`, would convert a class of silent
   drifts into import-time/test-time failures. (Note: the host runner is deliberately stdlib-only and
   self-contained, so the shared module must be a leaf with zero heavy imports — see P8.)
3. **Two ends compute the same contract independently and agree only by deployment.** The signed-string
   (P2/P3) is the *good* version of this pattern — both ends were proven byte-identical. The queue root
   (M1) is the *fragile* version — both ends compute it from different env vars with asymmetric
   validation, reconciled only by compose/deploy.sh. The HMAC seam shows the team can do
   code-level contract agreement; the queue seam shows where they didn't.
4. **Liveness, not authority, is the soft underbelly.** Every signature/auth/allowlist path held up
   under both models (the broker correctly rejects, confines, and constant-time-compares). The defects
   that survived adjudication are overwhelmingly about *what happens when something is malformed,
   concurrent, restarted, or left behind* — drain aborts, replay-after-restart, stranded `running`
   rows, dismissed-but-active. The pipeline is well-guarded against the adversary and under-guarded
   against entropy.

---

## Per-piece converged records

Each section below is the converged, code-adjudicated record for one piece, followed by the GPT-5.5
ratifier's material refinements. Line citations are to the working tree.



---

# P1 — Origination & persistence (control plane)


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 4 refinement(s) and 10 independent code re-confirmations.


## PIECE
P1 — Origination & persistence (control plane). File: `python/arclink_control.py`. Covers how a pin-upgrade / operator-upgrade intent is normalized, content-hashed into a 16-hex token, persisted in the `settings` table, re-hydrated on read, listed for the operator, dismissed, and rendered as notification-button extras; plus `upstream_*` config sourcing. Both independent audits (Claude, GPT-5.5) were re-verified line-by-line against the real code; the record below is the converged truth.

## AGREED INPUT CONTRACT (re-confirmed in code)
- `register_pin_upgrade_action(conn, *, items, install_items=None, notify_limit=PIN_UPGRADE_NOTIFY_LIMIT)` — signature at `arclink_control.py:9518-9524`; `PIN_UPGRADE_NOTIFY_LIMIT = 1` at `:9489`. (Codex inlined the default as `1`, Claude cited the constant; identical value, no conflict.)
- Each `items`/`install_items` entry is passed through `_normalize_pin_upgrade_item(dict(item))` (`:9526-9530`). The normalizer reads EXACTLY six keys — `component, kind, field, current, target, throttle_target` — each `str(item.get(k) or "").strip()`; `throttle_target` falls back to the raw `target` value before stripping (`:9503-9510`). Unknown keys are dropped. Blank `component` raises `ValueError` (`:9512`); blank `target` raises `ValueError` (`:9514`). `kind/field/current/throttle_target` may be empty. No regex / allowlist / newline / path-traversal check exists in this normalizer.
- `install_items is None` ⇒ defaults to `normalized_items`; if supplied it is normalized independently and may differ (`:9527-9530`). Empty `normalized_items` or empty `normalized_install_items` ⇒ `ValueError` (`:9531-9534`).
- `notify_limit` runs through `_normalize_pin_upgrade_notify_limit`: `int(value or 1)`, non-int ⇒ `1`, then clamped `max(1, min(limit, 10))` (`:9494-9499`).
- `get_pin_upgrade_action_payload(conn, token)`: `token` lowercased/stripped (`:9551`) and must match `_PIN_UPGRADE_TOKEN_RE = ^[0-9a-f]{16}$` (`:9491,:9552`).
- Sole production producer is the detector: `register_pin_upgrade_action(conn, items=_pin_upgrade_action_items(included), install_items=_pin_upgrade_install_items(pins, included), notify_limit=...)` (`arclink_pin_upgrade_check.py:710-715`). `items` = every included result with a target (`:615-627`); `install_items` = same shape but skips a component when its `pins.components[c].inherits_from` parent is also included (`:630-659`). This is the proven `items` vs `install_items` difference: `items` = full digest/display set, `install_items` = collapsed executable set.
- `upstream_*` config: `Config` fields at `:389-393`, populated in `Config.from_env` at `:530-538`. Env is sourced through `_load_config_env()` which does `merged = dict(os.environ)` (`:305`) then applies config-file values via `merged.setdefault(key, value)` (`:334`) — process env WINS over the config file. Defaults: repo `https://github.com/example/arclink.git` (`:530`), branch `arclink` (`:531`), deploy-key-enabled `False` via `bool_env` truthy set `{1,true,yes,on}` (`:532-536`, `:147-155`), deploy-key-path `""` (`:537`), known-hosts `""` (`:538`).

## AGREED OUTPUT CONTRACT (re-confirmed in code)
- `register_pin_upgrade_action` returns `token: str` = `sha256(json_dumps(payload_core))[:16]`, lowercase hex (`:9540`). `payload_core` = `{items, install_items, notify_limit}` only (`:9535-9539`). `json_dumps = json.dumps(value, sort_keys=True)` (`:158-159`) ⇒ token is content-addressed and key-order-independent.
- Side-effect: `upsert_setting("pin_upgrade_action:{token}", json_dumps(payload))` (`:9546`, prefix `:9490`) → `INSERT … ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at` + commit (`:2971-2980`). `settings(key,value,updated_at)` table `:598-602`. Re-registering identical core ⇒ same key ⇒ idempotent upsert with refreshed `updated_at`.
- Stored JSON = `{token, created_at(utc_now_iso), items[...], install_items[...], notify_limit}` (`:9541-9545`). `token`/`created_at` are added AFTER hashing, so they do not affect the token. Each item = `{component, kind, field, current, target, throttle_target}` all `str` (`:9503-9510`).
- `get_pin_upgrade_action_payload` returns `{token(normalized), created_at(str), items, install_items, notify_limit}` (`:9570-9576`); every item re-normalized, `notify_limit` re-clamped; missing/falsey stored `install_items` falls back to `items` (`:9564`). Returns `None` on: bad token regex (`:9552`), missing/blank value (`json_loads("",{})→{}`), non-dict payload, stored `token` field ≠ requested (`:9558`), any item re-normalize `ValueError/TypeError` (`:9560-9567`), or empty `items`/`install_items` (`:9568`).
- `list_pin_upgrade_action_payloads(conn, *, component="", active_only=True)` (`:9628-9672`): `list[dict]` newest-first by `settings.updated_at DESC, key DESC` (`:9647`); each entry is a `get_pin_upgrade_action_payload` dict plus injected `updated_at` (`:9669`); skips payloads that fail re-hydration (`:9663`); optional component filter (`:9665`); with `active_only`, keeps only payloads whose `items` have `(component,target)` or `(component,throttle_target)` in the active set (`:9667`).
- `dismiss_pin_upgrade_action` returns `{token, components[...], silenced[...]}`; side-effect `UPDATE pin_upgrade_notifications SET silenced=1, notify_count=max(notify_count,limit), last_notified_at=COALESCE(...)` WHERE `component=? AND target_value IN (target, throttle_target)` + commit (`:9683-9706`). A component is added to `silenced` only if `cursor.rowcount>0` (`:9704`).
- `operator_pin_upgrade_action_extra(cfg, *, token)` (`:9714-9759`): `None` unless 16-hex token; else Telegram `telegram_reply_markup` or Discord `discord_components` with `callback_data`/`custom_id` = `arclink:pin-upgrade:{preview|dismiss}:{token}`. Discord requires numeric `operator_notify_channel_id` (`:9736`).
- `operator_upgrade_action_extra(cfg, *, upstream_commit)` (`:9762-9807`): strips commit, returns `None` if blank (`:9767-9769`); else Telegram/Discord button dict with callbacks `arclink:upgrade:{preview|dismiss}:{target}` keyed by the RAW commit. Discord requires numeric channel id (`:9784`).

## TOUCH POINTS (agreed)
- Env (read in `Config.from_env`, `:530-538`): `ARCLINK_UPSTREAM_REPO_URL`, `ARCLINK_UPSTREAM_BRANCH`, `ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED`, `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH`, `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE`. Config discovery layer (`_load_config_env`, `:302-337`) additionally consults `ARCLINK_CONFIG_FILE` and config-file candidates via `Path.read_text` (`:315`). No env reads inside the pin-upgrade functions themselves. NOTE: `ARCLINK_UPSTREAM_DEPLOY_KEY_USER` is NOT a `Config` field — it is read straight from `os.environ` in the dispatch layer (`arclink_enrollment_provisioner.py:283`).
- DB tables: `settings` (write `:9546/:2972`, read `:9554/:2984`, list `:9642-9650`); `pin_upgrade_notifications` (schema `:732-743`, `component` is PRIMARY KEY at `:733`; read `_active_pin_upgrade_targets` `:9596-9608`; written by `dismiss_pin_upgrade_action` `:9683-9703`).
- Hashing `hashlib.sha256` (`:9540`); serialization `json_dumps`/`json_loads` (`:158-168`); time `utc_now_iso`; token regex `_PIN_UPGRADE_TOKEN_RE` (`:9491`); settings prefix `pin_upgrade_action:` (`:9490`).
- Subprocess argv / sockets / ports / locks: NONE in P1. argv is built downstream (`arclink_enrollment_provisioner._pin_upgrade_command_args:439-448`; broker). Durability relies on `conn.commit()` (`:2980`, `:9706`).

## CODE-PATH TRACE (agreed)
**Pin-upgrade origination (P1's persistence half):**
1. Detector calls `register_pin_upgrade_action(conn, items=_pin_upgrade_action_items(included), install_items=_pin_upgrade_install_items(pins, included), notify_limit=...)` (`arclink_pin_upgrade_check.py:710-715`).
2. Normalize each `items` entry (`arclink_control.py:9526` → `:9502-9515`), raising on blank component/target.
3. Normalize `install_items` (or fall back to `normalized_items`) (`:9527-9530`); guard empties (`:9531-9534`).
4. Build `payload_core` (`:9535-9539`); token = `sha256(json_dumps(payload_core))[:16]` (`:9540`).
5. Build full `payload` adding `token`+`created_at` (`:9541-9545`); `upsert_setting` + commit (`:9546→:2971-2980`); return token (`:9547`).
6. Detector stores token in notification `extra` (`pin_upgrade_action_token`) and merges `operator_pin_upgrade_action_extra` button markup (`arclink_pin_upgrade_check.py:716-730`).
7. Operator Raven lists active payloads (`list_pin_upgrade_action_payloads(component, active_only=True)`, `arclink_operator_raven.py:1281-1284`) and queues `operator_actions(action_kind="pin-upgrade", requested_target=token, request_source="operator-raven")` (`:1307-1314`).
8. Dispatch read-back: provisioner reads `requested_target` as token (`arclink_enrollment_provisioner.py:2456`), `get_pin_upgrade_action_payload` re-hydrates (`:2457`), fails closed "unknown action token" on `None` (`:2458-2470`), else `_run_pin_upgrade_action(cfg, payload, …)` consuming `install_items` (`:2498`).

**Operator-upgrade origination (P1's slice = button extra only):** `arclink_ctl._run_upstream_check` computes `upstream_commit` and calls `operator_upgrade_action_extra(cfg, upstream_commit=...)`; the dispatch path uses `requested_target` directly AS the commit (no token table). Structural asymmetry vs pin-upgrade (which is content-addressed). Confirmed both audits.

## CROSS-PIECE CONTRACTS (both ends verified in code)
1. **Item shape → dispatch.** P1 persists `{component,kind,field,current,target,throttle_target}` (`:9503-9510`). Every dispatch consumer reads ONLY `component,kind,target`: non-Docker `_pin_upgrade_command_args` (`arclink_enrollment_provisioner.py:429-431`) and broker `_normalized_pin_upgrade_item` (`arclink_operator_upgrade_broker.py:265-273`) DROP `field`,`current`,`throttle_target`. CONTRACT: P1 must emit non-empty `component`,`target` and a `kind` in the flag set.
2. **kind → flag.** `{git-commit:--ref, git-tag:--tag, container-image:--tag, npm:--version, nvm-version:--version, release-asset:--version}` — broker `PIN_UPGRADE_FLAGS` (`broker:49-56`) and provisioner `_pin_upgrade_apply_flag` (`:410-418`) are identical. Unsupported kind ⇒ `ValueError` at dispatch (`provisioner:437-438`, `broker:271-272`). P1 does NOT validate kind.
3. **Component allowlist.** P1 enforces only non-empty component (`:9512`). Docker broker enforces `SAFE_COMPONENT_RE` + `ALLOWED_PIN_COMPONENTS={hermes-agent,qmd,nextcloud,postgres,redis,nvm,node}` (`broker:47-48,267-268`). Non-Docker `_pin_upgrade_command_args` does NOT check the allowlist — it accepts any non-empty component (`provisioner:429-448`). Detector-managed `hermes-docs` (outside the broker allowlist) is collapsed out of `install_items` only when its `inherits_from` parent `hermes-agent` is co-included (`arclink_pin_upgrade_check.py:640-646`); P1 itself provides no such guarantee.
4. **Token formula.** `sha256(json_dumps(payload_core))[:16]` (`:9540`); read regex `^[0-9a-f]{16}$` (`:9491`) — width and charset agree. Token is what Operator Raven queues as `requested_target` and what the provisioner re-hydrates (`provisioner:2456-2457`). Button callbacks `arclink:pin-upgrade:{preview|dismiss}:{token}` (`:9722-9723`).
5. **Upstream config → dispatch env.** P1's `Config.upstream_*` (`:530-538`) projected by `_operator_upstream_env` (`provisioner:275-286`) to the same key names the broker expects in `UPSTREAM_ENV_KEYS` (`broker:57-64`). Default repo is the placeholder `example/arclink.git`. `ARCLINK_UPSTREAM_DEPLOY_KEY_USER` is appended only from live `os.environ` (`provisioner:283-285`) — it cannot come from the parsed config file because there is no `Config.upstream_deploy_key_user` field.

## DISAGREEMENTS & ADJUDICATION
1. **Dismissed-but-still-active listing (Codex flagged MEDIUM; Claude did NOT flag).** WINNER: codex. ADJUDICATION CONFIRMED AND STRENGTHENED. `_active_pin_upgrade_targets` filters rows by `applied_at IS NULL` only and never inspects `silenced` (`:9596-9608`). `dismiss_pin_upgrade_action` sets `silenced=1` but never touches `applied_at` (`:9683-9703`). A grep of all of `python/` shows `pin_upgrade_notifications.applied_at` is NEVER assigned a non-null value anywhere — it is only declared (`:732-743`) and reset to NULL on a new target (`arclink_pin_upgrade_check.py:487`). Therefore a dismissed payload's notification row keeps `applied_at IS NULL` and `list_pin_upgrade_action_payloads(active_only=True)` STILL returns it; Operator Raven (`arclink_operator_raven.py:1281-1290`) relies solely on that filter, so a dismissed pin upgrade remains queue-able. This is a real medium-severity drift Claude missed.
2. **`ARCLINK_UPSTREAM_DEPLOY_KEY_USER` not a Config field (Codex MEDIUM; Claude omitted).** WINNER: codex. Confirmed: read only from `os.environ` at `provisioner:283`; broker/host-runner accept it (`broker:61`, `host_runner:39`); no `Config` field exists (`:389-393`). Real cross-piece detail; severity lowered to LOW here because it only affects the optional deploy-key-user path and process env is the documented source.
3. **`list_pin_upgrade_action_payloads` error handling (Codex LOW; Claude omitted).** WINNER: codex. The `try/except sqlite3.Error` wraps ONLY the settings SELECT (`:9641-9652`); `_active_pin_upgrade_targets(conn)` runs OUTSIDE it (`:9654`) and would propagate a `sqlite3.Error`. Confirmed.
4. **Component allowlist not enforced at origination (Claude MEDIUM; Codex MEDIUM, framed as non-Docker accepting any component).** WINNER: both. Both correct; converged: P1 enforces only non-empty component, the Docker broker enforces the allowlist (`broker:267-268`), and the NON-Docker path does not (`provisioner:429-448`) — only `kind` is rejected there.
5. **`arclink_upgrade_last_dismissed_sha` written but never read (Codex LOW; Claude omitted).** WINNER: codex (with scope caveat). Confirmed: written at `arclink_curator_onboarding.py:975` and `arclink_curator_discord_onboarding.py:272`; no reader exists; suppression uses only `arclink_upgrade_last_notified_sha` (`arclink_ctl.py:1822`). These files are adjacent to P1, not `arclink_control.py` itself, so it is a neighbor-side observation.
6. **`throttle_target` fallback wording (minor).** Claude: "falls back to target when blank"; Codex: "falls back before stripping". WINNER: both. Code (`:9509`) does `str(item.get("throttle_target") or item.get("target") or "").strip()` — fallback on the raw (falsey) value, then strip. Both descriptions are functionally accurate for string inputs.
7. **`notify_limit` default citation.** Claude cited the constant `PIN_UPGRADE_NOTIFY_LIMIT`; Codex inlined `1`. WINNER: both — `PIN_UPGRADE_NOTIFY_LIMIT = 1` (`:9489`).

## GAPS BOTH MISSED
- **`applied_at` is effectively write-only-NULL (dead field) for `pin_upgrade_notifications`.** Neither audit stated that NO production code ever marks a pin notification "applied"; both spoke of `applied_at` filtering as if it naturally clears. It only ever moves toward NULL (reset on new target, `arclink_pin_upgrade_check.py:487`). The active filter is therefore effectively "a notification row exists for this (component,target)", and dismiss does NOT remove a payload from the active list. This is the root cause behind disagreement #1 and is the single most material edge in P1.
- **`dismiss_pin_upgrade_action` silently no-ops on target drift.** Because the WHERE clause is `component=? AND target_value IN (target, throttle_target)` (`:9692-9693`) and `pin_upgrade_notifications.component` is PRIMARY KEY (one row/component), if the live notification's `target_value` has moved on since the token was minted, `rowcount=0`, the component is excluded from `silenced` (`:9704`), and no error surfaces — the dismiss appears to succeed but silences nothing.
- **Read-path `install_items` fallback can diverge from write-time semantics.** On read, missing/falsey stored `install_items` falls back to `items` (`:9564`), but the producer always supplies a (possibly collapsed) `install_items`, so the fallback only triggers for hand-written/legacy settings rows. Benign but a real read/write asymmetry.

## RISKS (severity-ranked, all code-cited)
- MEDIUM — Dismissed pin upgrade stays listable (`:9601` vs `:9683-9703`); `applied_at` never set non-null anywhere (root cause).
- MEDIUM — Component allowlist enforced only at the Docker broker (`broker:267-268`); the non-Docker dispatch path accepts any non-empty component (`provisioner:429-448`); `kind` is unvalidated at origination (`:9502-9515`).
- LOW — `ARCLINK_UPSTREAM_DEPLOY_KEY_USER` sourced only from live `os.environ` (`provisioner:283`), not from the parsed config file (no Config field, `:389-393`).
- LOW — `_active_pin_upgrade_targets` SQLite errors are uncaught in `list_pin_upgrade_action_payloads` (`:9654` outside the `try` at `:9641-9652`).
- LOW — Placeholder default `upstream_repo_url=https://github.com/example/arclink.git` (`:530`); unset env silently points the whole upgrade pipeline at a non-existent repo; P1 does not flag it.
- LOW — `dismiss_pin_upgrade_action` silently silences nothing on target drift (`rowcount=0`, `:9704`).
- INFO — P1 persists `field`/`current` per item but every dispatch consumer drops them (`broker:273`, `provisioner:429-431`); persisted shape over-specifies.
- INFO — Read-time fail-closed: any stored item failing re-normalize ⇒ whole token returns `None` (`:9566-9567`) ⇒ dispatcher fails "unknown action token" (`provisioner:2458-2470`). Acceptable.
- INFO — Neighbor-side: `arclink_upgrade_last_dismissed_sha` written, never read (onboarding `:975`/`:272`; only `_last_notified_sha` read at `arclink_ctl.py:1822`).

## AGREED VERDICT
P1 PROVABLY does its origination/persistence job. It deterministically normalizes each upgrade item to a strict six-key string shape (rejecting blank component/target), content-addresses `{items,install_items,notify_limit}` into a stable lowercase-16-hex token (sort-keyed sha256[:16], idempotent upsert into `settings` under `pin_upgrade_action:{token}`), and re-hydrates with full re-validation, fail-closing to `None` on any corruption. The `items` (full digest/display) vs `install_items` (inheritor-collapsed executable) distinction is real and load-bearing, and the token→`requested_target`→re-hydrate cross-piece contract is verified at both ends. The deliberate weaknesses are that component/kind allowlisting and most field validation live downstream (the Docker broker, not P1, and the non-Docker path is even more permissive), and the one genuine correctness bug is that a DISMISSED pin upgrade remains "active" for listing because `applied_at` is never set non-null and the active filter ignores `silenced`. None of these breaks P1's own write/read contract, but the dismiss/active interaction is a real medium-severity drift the Federation should fix at the source (`_active_pin_upgrade_targets` or `dismiss_pin_upgrade_action`).


### Adjudicated cross-model disagreements


- **Dismissed pin upgrade still listed as active** — winner: **CODEX**  
  Claude: Did not flag; treated active_only filtering as adequate and only noted active_only returns [] when zero applied_at IS NULL rows exist (info).  
  GPT-5.5: MEDIUM: dismiss sets silenced=1 but active filtering ignores silenced, so a dismissed payload remains 'active' for listing (arclink_control.py:9683 vs :9601).  
  Adjudication: Codex correct and understated. _active_pin_upgrade_targets filters only applied_at IS NULL (:9601); dismiss_pin_upgrade_action sets silenced=1 and never touches applied_at (:9683-9703). A repo-wide grep confirms pin_upgrade_notifications.applied_at is NEVER assigned a non-null value anywhere (only reset to NULL at arclink_pin_upgrade_check.py:487), so dismissed payloads stay active_only and remain queue-able by Operator Raven (arclink_operator_raven.py:1281-1290). Real medium bug Claude missed. `[python/arclink_control.py:9601, python/arclink_control.py:9683-9703, python/arclink_pin_upgrade_check.py:487]`

- **ARCLINK_UPSTREAM_DEPLOY_KEY_USER not a Config field** — winner: **CODEX**  
  Claude: Omitted.  
  GPT-5.5: MEDIUM: not a Config field; broker upstream payload includes it only from os.environ, not from parsed config-file state.  
  Adjudication: Codex correct. Read only from os.environ at provisioner:283; no Config.upstream_deploy_key_user field (:389-393); broker/host-runner accept the key (broker:61, host_runner:39). Severity reduced to LOW in the converged record (optional deploy-key-user path, process env is the source). `[python/arclink_enrollment_provisioner.py:283, python/arclink_control.py:389-393, python/arclink_operator_upgrade_broker.py:61]`

- **list_pin_upgrade_action_payloads error handling scope** — winner: **CODEX**  
  Claude: Omitted.  
  GPT-5.5: LOW: try/except sqlite3.Error covers only the settings query; _active_pin_upgrade_targets errors are not caught.  
  Adjudication: Codex correct. The try/except wraps only the settings SELECT (:9641-9652); _active_pin_upgrade_targets(conn) is called at :9654 outside the guard and would propagate sqlite3.Error. `[python/arclink_control.py:9641-9654]`

- **Component allowlist not enforced at origination** — winner: **BOTH**  
  Claude: MEDIUM: register only requires non-empty component; broker restricts to {hermes-agent,qmd,nextcloud,postgres,redis,nvm,node}; hermes-docs survives in items and is only excluded from install_items by detector collapse.  
  GPT-5.5: MEDIUM: normalizer does not validate component/kind/target beyond non-empty component/target; Docker broker rejects unsafe components later but non-Docker dispatch accepts any component and only rejects unsupported kind.  
  Adjudication: Both correct and complementary. Confirmed: P1 enforces only non-empty component (:9512); Docker broker enforces ALLOWED_PIN_COMPONENTS (broker:267-268); non-Docker _pin_upgrade_command_args accepts any non-empty component and only validates kind (provisioner:429-448, :437-438). `[python/arclink_control.py:9512, python/arclink_operator_upgrade_broker.py:267-268, python/arclink_enrollment_provisioner.py:429-448]`

- **arclink_upgrade_last_dismissed_sha written but never read** — winner: **CODEX**  
  Claude: Omitted.  
  GPT-5.5: LOW: written by callback handlers but rg found no reader; suppression uses only arclink_upgrade_last_notified_sha.  
  Adjudication: Codex correct with scope caveat. Written at arclink_curator_onboarding.py:975 and arclink_curator_discord_onboarding.py:272; no get_setting reader exists; only arclink_upgrade_last_notified_sha is read (arclink_ctl.py:1822). These are adjacent files, not arclink_control.py (P1's primary file). `[python/arclink_curator_onboarding.py:975, python/arclink_curator_discord_onboarding.py:272, python/arclink_ctl.py:1822]`

- **Env-precedence / config sourcing depth** — winner: **CODEX**  
  Claude: Cited upstream_* env reads inside Config.from_env (:530-538) only.  
  GPT-5.5: Traced full discovery: merged=dict(os.environ) then config-file setdefault, so process env wins (:305,:334).  
  Adjudication: Codex more complete; not a conflict. Confirmed merged=dict(os.environ) at :305 and merged.setdefault(key,value) at :334 — process env overrides config file. Claude's narrower citation is accurate but does not surface precedence. `[python/arclink_control.py:305, python/arclink_control.py:334]`


### Risks (converged, severity-ranked)

- **[MEDIUM]** Dismissed pin upgrade stays listable as 'active'. dismiss_pin_upgrade_action sets silenced=1 but never sets applied_at; _active_pin_upgrade_targets filters only applied_at IS NULL and ignores silenced. applied_at is NEVER assigned a non-null value anywhere in production code (only reset to NULL on new target), so list_pin_upgrade_action_payloads(active_only=True) keeps returning dismissed payloads and Operator Raven can re-queue them. `[python/arclink_control.py:9601, python/arclink_control.py:9683-9703, python/arclink_pin_upgrade_check.py:487]`
- **[MEDIUM]** Component/kind allowlisting is enforced only downstream. register_pin_upgrade_action accepts any non-empty component and any kind; the Docker broker enforces ALLOWED_PIN_COMPONENTS + PIN_UPGRADE_FLAGS, but the non-Docker dispatch path validates only kind and accepts any non-empty component string. `[python/arclink_control.py:9502-9515, python/arclink_operator_upgrade_broker.py:267-272, python/arclink_enrollment_provisioner.py:429-448]`
- **[LOW]** ARCLINK_UPSTREAM_DEPLOY_KEY_USER is sourced only from live os.environ in the dispatch layer, not from the parsed config file, because there is no Config.upstream_deploy_key_user field. A deploy-key-user set only in the config file will not reach the broker payload. `[python/arclink_enrollment_provisioner.py:283, python/arclink_control.py:389-393]`
- **[LOW]** list_pin_upgrade_action_payloads guards only the settings SELECT with try/except sqlite3.Error; _active_pin_upgrade_targets(conn) runs outside the guard and would propagate a sqlite3.Error to the caller. `[python/arclink_control.py:9641-9654]`
- **[LOW]** Default upstream_repo_url is the placeholder https://github.com/example/arclink.git; if ARCLINK_UPSTREAM_REPO_URL is unset the entire upgrade pipeline targets a non-existent repo and P1 does not flag it. `[python/arclink_control.py:530]`
- **[LOW]** dismiss_pin_upgrade_action silently silences nothing on target drift: WHERE component=? AND target_value IN (target, throttle_target); with component as PRIMARY KEY (one row/component), a moved target_value yields rowcount=0, the component is omitted from 'silenced', and no error is raised. `[python/arclink_control.py:9692-9704, python/arclink_control.py:733]`
- **[INFO]** P1 persists field/current per item but every dispatch consumer drops them (broker reads only component/kind/target; non-Docker arg builder reads only component/kind/target). Persisted shape over-specifies relative to what dispatch consumes. `[python/arclink_control.py:9503-9510, python/arclink_operator_upgrade_broker.py:273, python/arclink_enrollment_provisioner.py:429-431]`
- **[INFO]** Read is fail-closed: any stored item failing _normalize_pin_upgrade_item makes get_pin_upgrade_action_payload return None for the whole token, and the dispatcher fails the action with 'unknown action token'. Acceptable. `[python/arclink_control.py:9560-9569, python/arclink_enrollment_provisioner.py:2457-2470]`


### GPT-5.5 ratifier refinements

- **[HIGH]** Operator-upgrade dispatch uses `requested_target` directly as the upstream commit, with no token table.  
  → correction: Operator-upgrade button extras embed the stripped upstream commit directly in callback data, but the normal execution path runs a generic configured host upgrade, not a commit-targeted dispatch. `[python/arclink_control.py:9770; python/arclink_curator_onboarding.py:981; python/arclink_operator_raven.py:1558; python/arclink_operator_raven.py:1563; python/arclink_enrollment_provisioner.py:2340; python/arclink_enrollment_provisioner.py:2366; python/arclink_enrollment_provisioner.py:390]`
- **[MEDIUM]** Config sourcing touch points are sufficiently covered by `ARCLINK_CONFIG_FILE` plus generic config-file candidates.  
  → correction: Upstream config precedence is process env first, then selected config-file values via `setdefault`, but the selected config file can be chosen through `ARCLINK_CONFIG_FILE`, `ARCLINK_REPO_DIR`, `ARCLINK_OPERATOR_ARTIFACT_FILE`, and operator-artifact hint keys. `[python/arclink_control.py:210; python/arclink_control.py:221; python/arclink_control.py:245; python/arclink_control.py:251; python/arclink_control.py:253; python/arclink_control.py:255; python/arclink_control.py:305; python/arclink_control.py:334]`
- **[MEDIUM]** `list_pin_upgrade_action_payloads` has an optional component filter, with no further contract needed.  
  → correction: `component=""` is unfiltered; `component="hermes"` matches `hermes-agent` and `hermes-docs`; other nonblank values match normalized component names across `install_items` and `items`. `[python/arclink_control.py:9579; python/arclink_control.py:9583; python/arclink_control.py:9588; python/arclink_control.py:9592; python/arclink_control.py:9665; python/arclink_operator_raven.py:1590; python/arclink_operator_raven.py:1604]`
- **[LOW]** The default upstream repo is a non-existent repo.  
  → correction: If `ARCLINK_UPSTREAM_REPO_URL` is absent, `Config.from_env` sets `upstream_repo_url` to `https://github.com/example/arclink.git`; whether git operations fail is not proven by P1 code. `[python/arclink_control.py:530; python/arclink_ctl.py:1716]`


---

# P2 — Client dispatch & HMAC signing (enrollment provisioner)


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 5 refinement(s) and 10 independent code re-confirmations.


## PIECE
P2 — Client dispatch & HMAC signing (enrollment provisioner). All in-scope code is in `python/arclink_enrollment_provisioner.py`. In Docker mode this piece signs and POSTs operator-upgrade and pin-upgrade requests to the operator-upgrade-broker (P3 = `python/arclink_operator_upgrade_broker.py`). Anchor note: the prompt's `_run_operator_upgrade_action (~375)` does NOT exist; the real brokered dispatcher is `_run_brokered_host_upgrade` (`arclink_enrollment_provisioner.py:374`), reached via `_run_host_upgrade` (`:390`). The pin entrypoint is `_run_pin_upgrade_action` (`:451`). Both audits independently identified this anchor drift; no behavioral gap.

## AGREED INPUT CONTRACT
- Signing function `_operator_upgrade_broker_request(operation, payload, *, timeout_seconds=7200)` — `arclink_enrollment_provisioner.py:297-302`. Confirmed.
- `operation: str` is literally `"run_operator_upgrade"` (`:377-378`) or `"run_pin_upgrade"` (`:465`), injected at `:311` (`body["operation"] = operation`). Confirmed.
- `payload: dict` = `{"log_path": str(log_path), "upstream": _operator_upstream_env(cfg)}` from `_brokered_operator_payload` (`:352-356`). For pin, caller also sets `request_payload["install_items"] = install_items` at `:463`. Confirmed.
- `upstream` map built by `_operator_upstream_env` (`:275-286`): keys `ARCLINK_UPSTREAM_REPO_URL`, `ARCLINK_UPSTREAM_BRANCH`, `ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED` ("1"/""), `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH`, `ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE` (all from `cfg`), plus optional `ARCLINK_UPSTREAM_DEPLOY_KEY_USER` from env if non-blank (`:283-285`). Confirmed.
- Env at dispatch: `ARCLINK_OPERATOR_UPGRADE_BROKER_URL` default `http://operator-upgrade-broker:8917`, `.strip().rstrip("/")` (`:289-290`); `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` `.strip()`, default `""` (`:293-294`); `ARCLINK_DOCKER_MODE` gate via `_docker_mode()` accepts `{1,true,yes}` (`:763-764`, checked at `:391`, `:457`). Confirmed.
- Pin `install_items` sourced via `get_pin_upgrade_action_payload(conn, token)` where `token = action.requested_target` (`:2456-2457`); `None` payload fails the action before any dispatch (`:2458-2470`). Codex traced this chain; confirmed.

## AGREED OUTPUT CONTRACT
On the wire (HTTP POST to `broker_url + "/v1/operator-upgrade"`, `:322`):
- Method `POST` (`:331`); header `Content-Type: application/json` (`:325`).
- Body = `body_bytes = json.dumps(body, sort_keys=True).encode("utf-8")` where `body = dict(payload); body["operation"] = operation` (`:310-312`). The EXACT bytes signed (hash at `:315`) and sent (`data=body_bytes` at `:323`) are byte-identical.
- Four auth headers (`:324-330`): `X-ArcLink-Operator-Upgrade-Broker-Token: <token>`, `X-ArcLink-Operator-Upgrade-Timestamp: <str(int(time.time()))>`, `X-ArcLink-Operator-Upgrade-Nonce: <secrets.token_urlsafe(18)>`, `X-ArcLink-Operator-Upgrade-Signature: <hex hmac-sha256>`.
- There is NO body-hash header; `body_hash` exists only inside the signed string (proven by the complete header dict at `:324-330`). Both audits agree; confirmed.
- Read timeout = `max(30, int(timeout_seconds))`, default 7200 (`:301`, `:334`). Confirmed.
- Return value: `result = data["result"]` (`:346-349`), a dict, from a success response requiring `isinstance(data, dict) and data["ok"] is True` (`:344-345`). Callers coerce `int(result.get("returncode"))`, defaulting to `2` on `TypeError/ValueError` (`:383-386`, `:468-471`).
- Side effect on broker `RuntimeError`: `_brokered_operator_failure` (`:359-371`) does `log_path.parent.mkdir(parents=True, exist_ok=True)` (`:365`), appends a refusal line via `_append_operator_log` (`:366`), and returns `CompletedProcess(returncode=2, stderr=message)` (`:371`). The happy brokered path writes NO local log (host-runner owns the real log).

## TOUCH POINTS
- ENV `ARCLINK_OPERATOR_UPGRADE_BROKER_URL` — `:289-290`.
- ENV `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` — `:293-294` (read again at `:304`).
- ENV `ARCLINK_DOCKER_MODE` — `:763-764` (gate at `:391`, `:457`).
- ENV `ARCLINK_UPSTREAM_DEPLOY_KEY_USER` — `:283` (into `upstream` map only).
- ENV (via cfg into upstream): `ARCLINK_UPSTREAM_REPO_URL`/`BRANCH`/`DEPLOY_KEY_ENABLED`/`DEPLOY_KEY_PATH`/`KNOWN_HOSTS_FILE` — `:277-281`.
- Constant `OPERATOR_UPGRADE_BROKER_TOKEN_HEADER = "X-ArcLink-Operator-Upgrade-Broker-Token"` — `:99`.
- Network: `urllib.request.urlopen(request, timeout=max(30, int(timeout_seconds)))` — `:334`; URL `broker_url + "/v1/operator-upgrade"` (`:322`); plaintext `http://`, default host:port `operator-upgrade-broker:8917`.
- Crypto: `secrets.token_urlsafe(18)` nonce (`:314`), `time.time()` timestamp (`:313`), `hashlib.sha256` body_hash (`:315`), the SOLE `hmac.new(...).hexdigest()` HMAC site (`:316-320`; verified the only `hmac.new` in the file via grep — `import hmac` at `:8`).
- File path: `log_path` (e.g. `state/operator-actions/upgrade-{action_id}.log` at `:2341`, `pin-upgrade-{action_id}.log` at `:2473`) written ONLY on the failure path (`:365-366`).
- DB: `mark_operator_action_running` writes `started_at`/`note`/`log_path` BEFORE the broker call (`:2342`, `:2474`); `finish_operator_action` on completion/failure (`:2369`, `:2396`).
- Subprocess: NONE on the Docker brokered path; a synthesized `CompletedProcess(args=["operator-upgrade-broker", "run_operator_upgrade"|"run_pin_upgrade"])` is returned (`:375`, `:387`, `:461`, `:472`). Bare-metal branches (`deploy.sh`, `bin/component-upgrade.sh`) are bypassed in Docker mode (`:393-407`, `:474+`).
- Imports `operator_upgrade_action_extra` (`:62`) / `operator_pin_upgrade_action_extra` (`:61`) are notification-button metadata only, NOT part of signing/dispatch.

## CODE-PATH TRACE (agreed)
run_operator_upgrade:
1. `main()` → `_run_pending_operator_actions(conn, cfg)` with no try/except wrapper (`:3330`, `:3348`).
2. Pop confirmed `upgrade` action; `_operator_action_has_confirmed_source` gate; mark running at `:2342`; `_run_host_upgrade(cfg, log_path=...)` at `:2366`.
3. `_run_host_upgrade`: `_docker_mode()` true → `_run_brokered_host_upgrade` (`:391-392`).
4. `_run_brokered_host_upgrade`: `args=["operator-upgrade-broker","run_operator_upgrade"]` (`:375`); calls `_operator_upgrade_broker_request("run_operator_upgrade", _brokered_operator_payload(...))` (`:377-380`).
5. `_operator_upgrade_broker_request`: read url+token (`:303-304`); falsy either → `RuntimeError` before any network I/O (`:305-309`).
6. `body=dict(payload); body["operation"]=operation; body_bytes=json.dumps(body,sort_keys=True).encode()` (`:310-312`).
7. `timestamp=str(int(time.time()))` (`:313`); `nonce=secrets.token_urlsafe(18)` (`:314`); `body_hash=sha256(body_bytes).hexdigest()` (`:315`).
8. `signature=hmac.new(token.encode("utf-8"), f"{timestamp}\n{nonce}\n{body_hash}".encode("utf-8"), sha256).hexdigest()` (`:316-320`).
9. Build `Request(url+"/v1/operator-upgrade", data=body_bytes, headers={4+1}, method="POST")` (`:321-332`); `urlopen(..., timeout=max(30,int(timeout_seconds)))` (`:334`); `data=json.loads(response.read().decode("utf-8"))` (`:335`).
10. `HTTPError` → parse error JSON / `{"error": str(exc)}` → `RuntimeError(str(data.get("error") or data))` (`:336-341`). `(OSError, TimeoutError, URLError, JSONDecodeError)` → `RuntimeError("operator upgrade broker request failed: "+str(exc)[:220])` (`:342-343`).
11. Require `isinstance(data,dict) and data["ok"] is True` (`:344-345`) and `isinstance(result,dict)` (`:346-348`); return `result` (`:349`).
12. Back in dispatcher: `RuntimeError`→`_brokered_operator_failure` (returncode 2, logged) (`:381-382`); else `int(result.get("returncode"))` default 2 → `CompletedProcess` (`:383-387`). Outer dispatcher (`:2368`+) marks completed on rc 0, else failed + notification with log tail.

run_pin_upgrade:
1. `_run_pending_pin_upgrade_actions` (`:2440`): pop `pin-upgrade` action (`reclaim_stale_running_seconds=0`), confirm source, `token=requested_target`, `payload=get_pin_upgrade_action_payload` (`:2456-2457`); `None`→fail (`:2458-2470`); mark running (`:2474`); `_run_pin_upgrade_action(cfg, payload, log_path=...)` (`:2498`).
2. `_run_pin_upgrade_action` Docker branch (`:457`): `install_items=list(payload.get("install_items") or [])` (`:458`); empty → `CompletedProcess(returncode=2, stderr="no install items")` (`:459-460`); `request_payload=_brokered_operator_payload(...); request_payload["install_items"]=install_items` (`:462-463`); `_operator_upgrade_broker_request("run_pin_upgrade", request_payload)` (`:465`) — identical signing path. `RuntimeError`→failure (`:466-467`); else rc coercion → `CompletedProcess` (`:468-472`).
3. After rc 0, dispatcher verifies canonical pins from `config/pins.json`; mismatch → log + rc 2 (`:2500-2511`).

## CROSS-PIECE CONTRACTS (verifier P3 = arclink_operator_upgrade_broker.py — both ends opened and verified)
- Signed-string format: client `f"{timestamp}\n{nonce}\n{body_hash}"` UTF-8 (`enrollment:318`) vs broker `f"{timestamp}\n{nonce}\n{body_hash}".encode("utf-8")` (`broker:710`). EXACT MATCH (three fields, LF-joined, no trailing newline).
- HMAC key: client `broker_token.encode("utf-8")` (`enrollment:317`) vs broker `expected.encode("utf-8")` where `expected=_broker_token()` (`broker:687,709`). Both read the SAME env var `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` with `.strip()` (client `:294`, broker `:98`). MATCH.
- body_hash: client `sha256(body_bytes).hexdigest()` over the exact POST body (`enrollment:315`); broker `sha256(raw_body).hexdigest()` over raw socket bytes `raw_body=self.rfile.read(length)` (`broker:707,745`). Because client signs and sends the SAME bytes and broker hashes the raw wire bytes (not a re-serialization), `sort_keys=True` canonicalization is irrelevant to verification — only byte-identity matters. MATCH/safe.
- Header names — all four match byte-for-byte: Token (`enrollment:99,326` / `broker:41,688`), Timestamp (`enrollment:327` / `broker:42,691`), Nonce (`enrollment:328` / `broker:43,692`), Signature (`enrollment:329` / `broker:44,693`).
- Constant-time compares: broker uses `hmac.compare_digest` on token (`broker:689`) and signature (`broker:713`). MATCH-required.
- Nonce: client `secrets.token_urlsafe(18)` → 24-char `[A-Za-z0-9_-]`; broker requires `re.fullmatch(r"[A-Za-z0-9_.~+/=-]{16,160}", nonce)` (`broker:703`). Empirically verified a generated nonce matches the regex; alphabet ⊂ allowed and 24 ∈ [16,160] → never trips format check. Broker enforces single-use via `_nonce_seen`/`_record_nonce` (`broker:705,715`) bounded by `MAX_SEEN_SIGNATURE_NONCES=4096` (`broker:38,680-683`).
- Timestamp freshness: broker rejects if `abs(now - timestamp) > REQUEST_SIGNATURE_TTL_SECONDS (=300)` (`broker:37,701`). Client sends `int(time.time())` immediately before POST. Client's 7200s value is the urlopen READ timeout for the broker's long-running response, independent of the 300s signature window (signature validated on arrival, before the host-runner wait). Not in conflict.
- Operation allowlist: client emits `{"run_operator_upgrade","run_pin_upgrade"}` (`enrollment:378,465`); broker dispatches exactly those (`broker:642,646`) and `raise ValueError("...not allowlisted")` otherwise (`broker:650`). MATCH.
- Endpoint/port: client `http://operator-upgrade-broker:8917` + `/v1/operator-upgrade`; broker `DEFAULT_PORT=8917` (`broker:40`), `do_POST` only accepts `/v1/operator-upgrade` (`broker:735`). MATCH.
- Response shape: broker success → HTTP 200 `{"ok": True, "result": <dict>}` (`broker:757-759`); failure → 400 `{"ok": False, "error": str}` (`broker:761`), plus 401 unauthorized (`broker:747`), 413 size (`broker:743`), 404 path (`broker:736`). Client requires `ok is True` + dict `result` (`enrollment:344-348`) and extracts `error` from HTTPError bodies (`enrollment:336-341`). MATCH.
- Request-size ceiling: broker `MAX_REQUEST_BYTES=16384` (`broker:36`), rejects `length<=0 or length>16384` with HTTP 413 (`broker:742-743`). Client has no client-side size cap; an oversized pin `install_items` body would be rejected 413 → client HTTPError branch → RuntimeError → returncode-2 failure (graceful). Verified both ends.

## DISAGREEMENTS & ADJUDICATION
1. UnicodeDecodeError on the SUCCESS decode path (`enrollment:335`). Codex flagged this "Low: success bodies are not in the non-HTTP exception tuple." Claude asserted the opposite globally — "HTTP/network/JSON errors and non-ok/malformed responses ALL become a logged returncode-2 refusal rather than a silent success" (claude_P2.md VERDICT). ADJUDICATION: Codex is correct and Claude's blanket claim is FALSE for this branch. `response.read().decode("utf-8")` at `:335` can raise `UnicodeDecodeError`, which (verified via MRO) is a subclass of `ValueError` but NOT of `OSError`, `TimeoutError`, `URLError`, or `json.JSONDecodeError` — so it escapes the `except` tuple at `:342`. It then propagates past `_run_brokered_host_upgrade`/`_run_pin_upgrade_action` (which catch only `RuntimeError` at `:381`/`:466`), past `_run_host_upgrade`, and out of `main()` (no try/except at `:3330,:3348`). Because the row was marked `running` at `:2342`/`:2474` BEFORE the call, the action is left stuck in `running` and the provisioner run crashes — NOT a clean returncode-2. WINNER: codex (Claude missed the consequence chain). Real-world reachability is low (the in-repo P3 always emits valid UTF-8 via `_json_response`), so severity stays Low, but the failure-mode claim differs materially. CITATION: `enrollment:335,342,381,466,2342,2474,3348`.
2. "No HTTP status inspection on success" — Codex rated MEDIUM; Claude did not flag it. ADJUDICATION: overstated. `urllib.request.urlopen` raises `HTTPError` for 4xx/5xx (handled at `:336`) and auto-follows 3xx; the broker only ever returns 200 with `{ok:true}` on success, and the `data["ok"] is True` gate at `:344` is the real correctness check. Non-200-but-2xx is not a path the broker produces. WINNER: neither fully — the behavior is correctly handled in practice; correct severity is Low/Info, not Medium. CITATION: `enrollment:333,336,344`; `broker:757-761`.
3. "No scheme/host allowlist on broker URL" — Codex rated MEDIUM; Claude did not flag (Claude instead flagged plaintext-http). ADJUDICATION: the env var is operator-controlled inside the GAP-019 Docker-internal trust boundary; there is no untrusted source that sets it, so SSRF-via-env is not a meaningful threat here. WINNER: neither (real observation, wrong severity) — downgrade to Low. The more substantive transport caveat both touch on differently is that the bearer token + body travel over plaintext `http://` (`:322`); HMAC gives integrity/replay protection but not confidentiality. CITATION: `enrollment:289-290,322`.
4. Direct-call malformed-input edges (bad `timeout_seconds` → `int()` raises; non-mapping `payload` → `dict(payload)` raises) — Codex flagged Low; Claude omitted. ADJUDICATION: Codex is correct that these escape the function's RuntimeError contract, but the only two in-file callers (`:377-380`, `:465`) always pass a dict payload and never override `timeout_seconds`, so the edges are unreachable in the real pipeline. WINNER: codex on completeness; severity Info. CITATION: `enrollment:301,310,334,379,462`.
No disagreement on the core signing contract — both audits agree byte-for-byte and I re-confirmed every claim in code.

## GAPS BOTH MISSED
- Consequence of the uncaught success-path `UnicodeDecodeError`: neither audit traced that it crashes the entire provisioner run AND leaves the `operator_actions` row stuck in `running` (marked at `:2342`/`:2474`), because no caller above `_operator_upgrade_broker_request` catches anything broader than `RuntimeError` and `main()` (`:3348`) has no guard. Proven: `enrollment:335,381,466,2342,2474,3330,3348`; MRO checked empirically.
- Both correctly note the broker's `MAX_REQUEST_BYTES=16384` 413 path, but neither states the client-side consequence explicitly: a large pin `install_items` list has NO client-side size guard, so the broker's 413 is the only ceiling; it is handled gracefully as an HTTPError→RuntimeError→returncode-2. Proven: `broker:36,742-743`; `enrollment:336-341`.
- The `_record_nonce` eviction (`broker:680-683`) caps the seen-nonce set at 4096; under a flood this could theoretically evict a still-valid nonce within the 300s window, but the client never reuses a nonce (`secrets.token_urlsafe(18)` fresh per request at `:314`), so this is a broker-side robustness note only, not a client contract issue.

## RISKS
- LOW: Uncaught `UnicodeDecodeError` on success decode (`enrollment:335`) escapes the RuntimeError contract, crashes the run, and strands the action row in `running`. Reachable only if the responder returns non-UTF-8 (not the in-repo broker).
- LOW: Plaintext `http://` transport (`enrollment:322`); broker bearer token and body (log paths, upstream repo URL, deploy-key path) are unencrypted. HMAC = integrity/replay only, not confidentiality. Accepted GAP-019 Docker-internal model.
- LOW: Broker URL is env-controlled with only strip/rstrip, no scheme/host allowlist (`enrollment:289-290`); benign inside the trust boundary.
- INFO: Client trusts local clock for the signed timestamp (`enrollment:313`); broker rejects skew >300s (`broker:701`). Same Docker host ⇒ skew ~0, but a >5min drift fails every request closed.
- INFO: Error-message surfacing — HTTPError branch returns broker-supplied `error` (`enrollment:341`) and generic errors truncated to 220 chars (`enrollment:343`) into operator-facing notifications; cosmetic info-leak, not exploitable.
- INFO: Direct callers passing malformed `timeout_seconds`/non-mapping `payload` raise outside the RuntimeError handler (`enrollment:301,310`); unreachable from the two real call sites.

## AGREED VERDICT
PROVABLY YES — this piece does its job. It deterministically builds a canonical JSON body (`sort_keys=True`, `enrollment:312`), HMAC-SHA256-signs the exact string `timestamp\nnonce\nbody_hash` with the shared broker token (`:316-320`), and POSTs the identical bytes plus the four agreed headers to `/v1/operator-upgrade` (`:321-332`). Every field the verifier P3 checks — header names, key, message format, body-hash-over-raw-bytes, operation allowlist, nonce alphabet/length, timestamp TTL, and the `{ok,result,returncode}` response shape — is byte-for-byte compatible with the broker's `_is_authorized`/`do_POST` (verified at both ends). Fail-closed behavior is correct for the dominant failure modes: missing url/token fails before network I/O (`:305-309`), and HTTPError/network/JSON errors plus non-`ok`/malformed responses become a logged returncode-2 refusal (`:336-348,381-382,466-467`). The one real residual defect both reconciled-on is the uncaught success-path `UnicodeDecodeError` (`:335`), which is Low-severity (only reachable from a non-UTF-8 responder) but does break the "everything becomes returncode-2" claim and can strand a `running` row. The plaintext-http transport is an accepted Docker-internal trust assumption, not a code defect. The signing contract is sound and client-side correct.


### Adjudicated cross-model disagreements


- **Failure handling of UnicodeDecodeError on the success-decode path (enrollment:335)** — winner: **CODEX**  
  Claude: All HTTP/network/JSON errors and non-ok/malformed responses become a logged returncode-2 refusal rather than a silent success (blanket claim in VERDICT and PROVEN FACTS).  
  GPT-5.5: Low: successful HTTP response decode can raise UnicodeDecodeError, which is not in the non-HTTP exception tuple; success bodies are not broadly caught.  
  Adjudication: Codex is correct; Claude's blanket claim is false for this branch. response.read().decode('utf-8') at :335 can raise UnicodeDecodeError, which (MRO-verified) is a subclass of ValueError but NOT of OSError/TimeoutError/URLError/json.JSONDecodeError, so it escapes the except tuple at :342. It propagates past _run_brokered_host_upgrade/_run_pin_upgrade_action (catch only RuntimeError at :381/:466), past _run_host_upgrade, and out of main() (no guard at :3348). Because the row was marked running at :2342/:2474 before the call, the action is stranded in 'running' and the provisioner run crashes — not a clean returncode-2. Reachability is low (in-repo broker always emits UTF-8 via _json_response), so severity stays Low. `[python/arclink_enrollment_provisioner.py:335,342,381,466,2342,2474,3348]`

- **Severity of 'no explicit HTTP status inspection on successful urlopen'** — winner: **NEITHER**  
  Claude: Not flagged; relies on the ok-is-True gate as the correctness check.  
  GPT-5.5: Medium: P2 does not explicitly inspect HTTP status on successful urlopen.  
  Adjudication: Overstated by Codex. urllib.request.urlopen raises HTTPError for 4xx/5xx (handled at :336) and auto-follows 3xx; the broker only emits 200 with {ok:true} on success, and the data['ok'] is True gate at :344 is the real check. Correct severity is Low/Info, not Medium. `[python/arclink_enrollment_provisioner.py:333,336,344; python/arclink_operator_upgrade_broker.py:757-761]`

- **Severity of env-controlled broker URL with no scheme/host allowlist** — winner: **NEITHER**  
  Claude: Flagged the related plaintext-http transport as Low (bearer token in clear), not the URL allowlist.  
  GPT-5.5: Medium: ARCLINK_OPERATOR_UPGRADE_BROKER_URL accepted from env with only strip/trailing-slash removal, no scheme/host allowlist.  
  Adjudication: The env var is operator-controlled inside the GAP-019 Docker-internal trust boundary; no untrusted source sets it, so SSRF-via-env is not a meaningful threat. Real observation but wrong severity — downgrade to Low. The substantive transport caveat is the plaintext http:// carrying the bearer token (Claude's framing), not the missing allowlist. `[python/arclink_enrollment_provisioner.py:289-290,322]`

- **Anchor _run_operator_upgrade_action does not exist** — winner: **BOTH**  
  Claude: INFO: prompt's _run_operator_upgrade_action (~375) does not exist; real dispatcher is _run_brokered_host_upgrade (line 374) via _run_host_upgrade (line 390); no behavioral gap.  
  GPT-5.5: Low/discrepancy: requested anchor _run_operator_upgrade_action is not the actual function name; the executable brokered path is _run_brokered_host_upgrade and _run_host_upgrade.  
  Adjudication: Both correct and in agreement. The function does not exist; the real path is _run_host_upgrade -> _run_brokered_host_upgrade. No behavioral impact. Severity Info. `[python/arclink_enrollment_provisioner.py:374,390-392]`


### Risks (converged, severity-ranked)

- **[LOW]** Uncaught UnicodeDecodeError on the success-decode path: response.read().decode('utf-8') at :335 is not in the function's except tuple (:342) and is not RuntimeError, so a non-UTF-8 success body propagates out of every caller and out of main() (:3348), crashing the run and leaving the operator_actions row stuck 'running' (marked at :2342/:2474). Reachable only from a non-UTF-8 responder; the in-repo broker always returns UTF-8 JSON. `[python/arclink_enrollment_provisioner.py:335,342,381,466,2342,2474,3348]`
- **[LOW]** Plaintext http:// transport (no TLS). The broker bearer token is sent as a cleartext header and the body (log paths, upstream repo URL, deploy-key path) is unencrypted. HMAC provides integrity/replay protection but not confidentiality; security relies on the Docker-internal network (GAP-019 risk-accepted). `[python/arclink_enrollment_provisioner.py:322,326]`
- **[LOW]** Broker URL is env-controlled with only strip/rstrip and no scheme/host allowlist; benign inside the Docker trust boundary but provides no defense if the env is tampered. `[python/arclink_enrollment_provisioner.py:289-290]`
- **[INFO]** Client trusts local clock for the signed timestamp (no self skew check). Broker rejects if abs(now-timestamp) > 300s (broker:701). Same Docker host means skew ~0, but a >5min drift would fail every request closed. `[python/arclink_enrollment_provisioner.py:313; python/arclink_operator_upgrade_broker.py:701]`
- **[INFO]** Error surfacing: HTTPError branch returns broker-supplied error JSON (:341) and generic errors are truncated to 220 chars (:343), flowing into operator-facing notifications. Cosmetic info-leak, not exploitable from this piece. `[python/arclink_enrollment_provisioner.py:341,343]`
- **[INFO]** Direct callers passing malformed timeout_seconds (int() raises) or a non-mapping payload (dict(payload) raises) bypass the RuntimeError handling; unreachable from the only two in-file call sites which pass dicts and use the default timeout. `[python/arclink_enrollment_provisioner.py:301,310,379,462]`
- **[INFO]** No client-side body-size guard: a large pin install_items body is bounded only by the broker's MAX_REQUEST_BYTES=16384 (413), which is handled gracefully via the HTTPError->RuntimeError->returncode-2 path. `[python/arclink_operator_upgrade_broker.py:36,742-743; python/arclink_enrollment_provisioner.py:336-341]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** HTTPError/network/JSON errors plus non-ok/malformed responses become a logged returncode-2 refusal.  
  → correction: Only HTTPError bodies that fail parsing, or parse to a dict, are converted to RuntimeError. A valid non-dict JSON HTTPError body escapes and can leave an already-marked action running until stale cleanup. `[/root/arclink/python/arclink_enrollment_provisioner.py:336; /root/arclink/python/arclink_enrollment_provisioner.py:338; /root/arclink/python/arclink_enrollment_provisioner.py:341; /root/arclink/python/arclink_enrollment_provisioner.py:381; /root/arclink/python/arclink_enrollment_provisioner.py:466]`
- **[MEDIUM]** Malformed broker input/error behavior is fully covered by missing token/url, non-200, network error, and the noted direct bad timeout/non-mapping payload edges.  
  → correction: The executable contract is stricter: payload must be JSON-serializable and broker_url must be acceptable to urllib.request.Request before urlopen. Failures at body serialization or Request construction escape the clean returncode-2 path. `[/root/arclink/python/arclink_enrollment_provisioner.py:310; /root/arclink/python/arclink_enrollment_provisioner.py:312; /root/arclink/python/arclink_enrollment_provisioner.py:321; /root/arclink/python/arclink_enrollment_provisioner.py:333]`
- **[MEDIUM]** DB touch points are covered by mark_operator_action_running at upgrade/pin start and finish_operator_action on completion/failure at lines 2369 and 2396.  
  → correction: Pin-upgrade actions are marked completed at 2518-2524 or failed at 2546-2552, then the failure path queues an operator notification with operator_pin_upgrade_action_extra at 2575-2581. `[/root/arclink/python/arclink_enrollment_provisioner.py:2518; /root/arclink/python/arclink_enrollment_provisioner.py:2546; /root/arclink/python/arclink_enrollment_provisioner.py:2575; /root/arclink/python/arclink_enrollment_provisioner.py:2581]`
- **[LOW]** The uncaught UnicodeDecodeError consequence is fully described as stranding the operator_actions row in running.  
  → correction: Both upgrade and pin-upgrade paths call _fail_stale_running_operator_actions with stale_seconds=30*60 before taking new work, and that helper finishes stale running rows as failed and queues an operator message. `[/root/arclink/python/arclink_enrollment_provisioner.py:613; /root/arclink/python/arclink_enrollment_provisioner.py:621; /root/arclink/python/arclink_enrollment_provisioner.py:641; /root/arclink/python/arclink_enrollment_provisioner.py:2322; /root/arclink/python/arclink_enrollment_provisioner.py:2440]`
- **[LOW]** Header names match byte-for-byte as a cross-piece contract.  
  → correction: The contract that is proven in repo code is presence of token, timestamp, nonce, and signature header values under the named HTTP headers, plus the signed body bytes. Header-name byte casing should not be stated as load-bearing. `[/root/arclink/python/arclink_enrollment_provisioner.py:321; /root/arclink/python/arclink_enrollment_provisioner.py:324; /root/arclink/python/arclink_operator_upgrade_broker.py:688; /root/arclink/python/arclink_operator_upgrade_broker.py:691]`


---

# P3 — Broker ingress: token + signature + replay protection


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 6 refinement(s) and 8 independent code re-confirmations.


## PIECE
P3 — Broker ingress: token + signature + replay protection.
File in scope: `/root/arclink/python/arclink_operator_upgrade_broker.py` (HTTP listener `OperatorUpgradeBrokerHandler`, auth `_is_authorized`, nonce store `_nonce_seen`/`_record_nonce`, `serve`/`main` bind). Signer neighbor (P2): `/root/arclink/python/arclink_enrollment_provisioner.py` `_operator_upgrade_broker_request` (297-349). Deployment shape: `compose.yaml` `operator-upgrade-broker` service (842-875) + network (1173-1174). Consumer neighbor (P4 host runner): `/root/arclink/python/arclink_operator_upgrade_host_runner.py`.

## AGREED INPUT CONTRACT (re-verified)
Inbound HTTP request:
- Method/path routing: `do_GET` serves only exact `/health`, else 404 (`arclink_operator_upgrade_broker.py:725-728`); `do_POST` serves only exact `/v1/operator-upgrade`, else 404 (`:734-737`).
- `Content-Length`: `int(self.headers.get("Content-Length") or "0")`, `ValueError`→0 (`:738-741`); must be `1..MAX_REQUEST_BYTES(16384)` or 413 returned BEFORE body read (`:36`, `:742-744`). A negative value parses (e.g. `int("-5")==-5`) and trips `length <= 0` → 413 (verified by probe).
- Body: `raw_body = self.rfile.read(length)` (`:745`) — exactly `Content-Length` bytes; this is the byte string the HMAC is computed over (no re-serialization).
- Four auth headers, each `str(headers.get(...) or "").strip()`, missing→"" : Token `X-ArcLink-Operator-Upgrade-Broker-Token` (`:41`, read `:688`), Timestamp `-Timestamp` (`:42`, `:691`), Nonce `-Nonce` (`:43`, `:692`), Signature `-Signature` (`:44`, `:693`).
- Server secret/HMAC key: `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` via `_broker_token()` (`:97-98`); used as expected token (`:687`,`:689`) AND HMAC key (`:709`).
- After auth: `json.loads(raw_body.decode("utf-8"))` (`:750`) → 400 on `UnicodeDecodeError`/`JSONDecodeError` (`:751-753`); must be `dict` else 400 (`:754-756`); validated dict flows to `run_operator_upgrade_request(body)` (`:757`).
- Signer side (P2) produces: `body_bytes = json.dumps(body, sort_keys=True).encode("utf-8")` (`enrollment_provisioner.py:312`), `timestamp = str(int(time.time()))` (`:313`), `nonce = secrets.token_urlsafe(18)` (`:314`).

## AGREED OUTPUT CONTRACT (re-verified)
All responses via `_json_response`: `json.dumps(payload, sort_keys=True)+"\n"` UTF-8, `Content-Type: application/json`, correct `Content-Length` (`:656-662`).
- GET non-`/health` → `404 {"ok": false, "error": "not found"}` (`:726-728`).
- GET `/health`, token unset → `503 {"ok": false, "error": "operator upgrade broker token is not configured"}` (`:729-731`).
- GET `/health`, token set → `200 {"ok": true}`; NO auth headers required — `do_GET` never calls `_is_authorized` (`:725-732`).
- POST wrong path → `404` (`:735-736`).
- POST bad size (`<=0` or `>16384`) → `413 {"ok": false, "error": "invalid operator upgrade request size"}` (`:742-744`).
- POST any auth failure (token / missing header / non-numeric ts / window / nonce-format / replay / HMAC) → single generic `401 {"ok": false, "error": "unauthorized"}` (`:746-748`). No oracle distinguishing failure modes.
- POST non-UTF8/non-JSON (post-auth) → `400 {"ok": false, "error": "invalid JSON"}` (`:749-753`).
- POST non-object JSON (post-auth) → `400 {"ok": false, "error": "operator upgrade request must be a JSON object"}` (`:754-756`).
- POST dispatch success → `200 {"ok": true, "result": <dict>}` (`:757-759`); failure → `400 {"ok": false, "error": str(payload)}` (`:760-761`). Note: a nonzero subprocess returncode is still a `200` success with `result.returncode` set (`:495-510`, `:356-360`, `:757-759`) — HTTP 400 is reserved for raised exceptions.
- In-process side effect: on FULL auth success only, `_record_nonce(nonce, now)` inserts into `_SEEN_SIGNATURE_NONCES` (`:715`).

## TOUCH POINTS (re-verified)
- Env `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` — `_broker_token()` `:97-98`; gates health (`:729`), is expected token + HMAC key (`:687`,`:709`), required at startup (`:779-780`).
- Env `ARCLINK_OPERATOR_UPGRADE_BROKER_HOST` — bind host, code default `127.0.0.1` (`:39`,`:771`). DEPLOYMENT override `0.0.0.0` (`compose.yaml:865`).
- Env `ARCLINK_OPERATOR_UPGRADE_BROKER_PORT` — bind port, default `8917` (`:40`,`:772-776`; `compose.yaml:866`).
- Env `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` — startup gate (`:778`) and per-request gate (`:638`); env name in `arclink_boundary.py:19`, checker `:85`.
- Const `REQUEST_SIGNATURE_TTL_SECONDS=300` (`:37`) — used as BOTH timestamp window (`:701`) AND nonce eviction cutoff (`:666`,`:675`).
- Const `MAX_SEEN_SIGNATURE_NONCES=4096` (`:38`) — eviction cap (`:680`).
- Const `MAX_REQUEST_BYTES=16384` (`:36`) — size clamp (`:742`).
- Bind: `ThreadingHTTPServer((host, port), OperatorUpgradeBrokerHandler)` + `serve_forever()` (`:764-766`). `ThreadingHTTPServer` uses `ThreadingMixIn` (verified via MRO) → one thread per request, real concurrency.
- Lock `_SEEN_SIGNATURE_NONCES_LOCK = threading.Lock()` (`:46`), held inside `_nonce_seen` (`:667`) and `_record_nonce` (`:676`) — two SEPARATE acquisitions across the check/record gap.
- Store `_SEEN_SIGNATURE_NONCES: dict[str,float]` (`:45`) — process-local, in-memory, not persisted, not shared.
- Nonce regex `[A-Za-z0-9_.~+/=-]{16,160}` (`:703`).
- HMAC `hashlib.sha256`, key `expected.encode("utf-8")` (`:708-712`); constant-time compares `hmac.compare_digest` for token (`:689`) and signature (`:713`).
- No socket/read timeout configured anywhere (grep confirmed); `do_POST` blocks on `self.rfile.read(length)` (`:745`) with no deadline.
- No file paths / subprocess in the ingress/auth layer; those occur only after auth in `run_operator_upgrade_request` → host-runner queue or direct `deploy.sh`/`component-upgrade.sh` (P4/P5).

## CODE-PATH TRACE (agreed)
POST `/v1/operator-upgrade`:
1. Path check; non-match → 404 (`:735-736`).
2. `Content-Length` parse, `ValueError`→0 (`:738-741`).
3. Size clamp `<=0 or >16384` → 413, body NOT yet read (`:742-744`).
4. `raw_body = self.rfile.read(length)` (`:745`).
5. `_is_authorized(self.headers, raw_body)` (`:746`):
   a. `expected=_broker_token()` (`:687`); token gate `expected and supplied and hmac.compare_digest(expected, supplied)` — constant-time; unset token short-circuits False (`:687-690`).
   b. Read ts/nonce/sig headers stripped; any empty → False (`:691-695`).
   c. `timestamp=int(timestamp_raw)`; non-int → False (`:696-699`).
   d. `now=time.time()`; `abs(now-timestamp) > 300` → False (symmetric ±300, 300 inclusive) (`:700-702`).
   e. Nonce regex fail → False (`:703-704`).
   f. `_nonce_seen(nonce, now)` True → False — acquires lock, evicts stale, checks membership, RELEASES lock (`:705-706`, `:665-671`).
   g. `body_hash=sha256(raw_body).hexdigest()` (`:707`).
   h. `expected_signature=HMAC-SHA256(key=expected.encode, msg=f"{timestamp}\n{nonce}\n{body_hash}".encode)` — NOTE msg uses the PARSED int `timestamp`, re-canonicalized (`:708-712`).
   i. `hmac.compare_digest(expected_signature, supplied_signature)` fail → False (`:713-714`).
   j. `_record_nonce(nonce, now)` — RE-acquires lock, evicts stale, LRU-evicts at cap, inserts; return True (`:715-716`, `:674-683`).
6. Not authorized → 401 (`:747-748`).
7. `json.loads(raw_body.decode("utf-8"))`, errors → 400 (`:749-753`).
8. Non-dict → 400 (`:754-756`).
9. `run_operator_upgrade_request(body)` (`:757`): trusted-host gate FIRST (`:638`), then operation allowlist routes `run_operator_upgrade`/`run_pin_upgrade` (host-runner or direct), else raises (`:641-650`); exceptions → `_record_rejection_incident` + `(False, str(exc))` (`:651-653`).
10. 200 with `result` or 400 with error (`:758-761`).

GET `/health`: `do_GET` (`:725`) → path check (`:726`) → token-set check (`:729`) → 200/503. No `_is_authorized` ever called on the GET path.

`run_operator_upgrade` vs `run_pin_upgrade`: P3 does NOT differentiate at ingress/auth — both `operation` values pass the identical token+ts+nonce+regex+replay+HMAC funnel in `_is_authorized`. Differentiation happens only post-auth in `run_operator_upgrade_request` (`:642-649`).

## CROSS-PIECE CONTRACTS (re-verified, both ends)
1. P2→P3 signed-string / HMAC (byte-identical, VERIFIED BOTH ENDS):
   - Body bytes: P2 `json.dumps(body, sort_keys=True).encode("utf-8")` (`enrollment_provisioner.py:312`) sent as wire body (`data=body_bytes`, `:323`); P3 hashes the exact wire bytes `raw_body` (`broker.py:707`,`:745`). No canonicalization seam — broker hashes received bytes, not a re-serialization.
   - body_hash: both `hashlib.sha256(<bytes>).hexdigest()` (P2 `:315`, P3 `:707`).
   - Signed string: both `f"{timestamp}\n{nonce}\n{body_hash}"` UTF-8, LF separators, no trailing newline, order ts/nonce/body_hash (P2 `:318`, P3 `:710`). IDENTICAL.
   - HMAC: both `hmac.new(token.encode("utf-8"), msg, hashlib.sha256).hexdigest()` keyed by the broker token (P2 `:316-320`, P3 `:708-712`). IDENTICAL.
   - Headers: P2 sets the four `X-ArcLink-Operator-Upgrade-*` headers via shared constant `OPERATOR_UPGRADE_BROKER_TOKEN_HEADER` (`enrollment_provisioner.py:99`,`:326-329`); P3 reads the same names (`broker.py:41-44`,`:688-693`). Match.
   - Timestamp: P2 `str(int(time.time()))` canonical base-10; P3 parses `int()` and re-formats canonically into the signed msg (`:697`,`:710`) — agree for P2-generated values AND robust to non-canonical smuggling (broker signs the canonical form).
   - Nonce: P2 `secrets.token_urlsafe(18)` (24 chars, alphabet `[A-Za-z0-9_-]`); P3 regex `[A-Za-z0-9_.~+/=-]{16,160}` accepts it (length 24 in range, chars in class). Compatible (broker is strictly more permissive — slack, no break).
   - URL/port/token: P2 default `http://operator-upgrade-broker:8917` (`:290`), token env `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` (`:294`); P3 port `8917` (`:40`), same env (`:98`). Match. Compose wires both to the same `:8917` and same secret (`compose.yaml:863-866`, `963-964`).
   - Response: P2 expects `{"ok": true, "result": dict}`, raises otherwise (`:344-349`); P3 emits exactly that (`broker.py:757-761`). Match.
2. P3→P4 host-runner queue (producer side, VERIFIED BOTH ENDS): broker writes `pending/<request_id>.json` with `schema_version=1`, `request_id`, `operation`, `repo_dir`, `priv_dir`, `container_priv_dir`, `log_path`, `timeout_seconds`, `upstream`, optional `install_items` (`broker.py:316-339`); host runner requires `schema_version==1` (`host_runner.py:282`). Host runner writes result `{"ok": True, "request_id", "returncode": int, "completed_at"}` (`host_runner.py:382`); broker requires `ok is True` + integer `returncode` (`broker.py:345-360`). Both ends agree.

## DISAGREEMENTS & ADJUDICATION
1. **Concurrency atomicity of replay check.** Codex: HIGH — `_nonce_seen` (705) and `_record_nonce` (715) use SEPARATE lock acquisitions with non-locked HMAC work between, so two simultaneous identical requests can both pass `_nonce_seen` before either records. Claude: stated "Replay protection is sound" and rated only the cross-restart issue, MISSING the TOCTOU entirely. ADJUDICATION: Codex correct on mechanism — the lock is released between check (`:667-671`) and record (`:676-683`), and `ThreadingHTTPServer` is genuinely multithreaded (MRO confirms `ThreadingMixIn`), so the TOCTOU window is real. WINNER: codex. BUT severity HIGH is overstated: the broker token is the entire trust boundary (token-holder can already post arbitrary signed upgrades), the operations are coarse upgrade actions, and the listener is reachable only on an `internal:true` Docker network with no published host port. Adjudicated severity: MEDIUM. Citation: `broker.py:705`, `:715`, `:667`, `:676`, `:764-766`.
2. **Bind exposure.** Claude: "binds loopback 127.0.0.1:8917 by default" (code default, accurate) and flagged `0.0.0.0` override only as a hypothetical INFO that is "not set in this file." Codex: states the ACTUAL deployment sets `0.0.0.0:8917` (`compose.yaml:865`) and the net is internal. ADJUDICATION: Both partly right. Code default IS `127.0.0.1` (`broker.py:39`,`:771`) — Claude correct on the code. But the real shipped config overrides to `0.0.0.0` (`compose.yaml:865`) — Codex correct on deployment. WINNER: both. The decisive nuance NEITHER stated cleanly: `0.0.0.0` is contained because the broker service publishes NO host `ports:` (verified absent in 842-876) and its only network `operator-upgrade-broker-net` is `internal: true` (`compose.yaml:1173-1174`), so the listener is reachable only from peer containers on that internal net, not the host or internet. Citation: `broker.py:39`, `compose.yaml:865`, `compose.yaml:1173-1174`.
3. **Poll-seconds parsed after queueing.** Codex: MEDIUM — broker writes `pending/<id>.json` (`:339`) before parsing `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` via `float()` (`:341`); a non-numeric value raises after the file is queued, so the host runner can still drain it while the broker returns 400. Claude: did not cover (treated host-runner internals as out of P3 scope). ADJUDICATION: mechanically correct — line 339 precedes line 341, and a non-numeric env raises `ValueError` caught at `:651` → 400, but the pending file persists. WINNER: codex. Severity reduced to LOW: requires operator misconfiguration of a numeric env var, and it is a P4-boundary detail rather than pure ingress. Citation: `broker.py:338-342`, `:651-653`.
4. **No socket/read timeout.** Codex: LOW — plain `ThreadingHTTPServer`, `do_POST` blocks on `rfile.read(length)` with no timeout. Claude: did not cover. ADJUDICATION: confirmed — grep shows no `settimeout`/handler `timeout` set; `:745` read has no deadline. WINNER: codex. Bounded by `MAX_REQUEST_BYTES=16384` (`:36`,`:742`) and internal-net containment. Severity LOW. Citation: `broker.py:745`, `:764-766`.
5. **Auth-failure not incident-logged.** Both agree (Claude LOW, Codex LOW). Confirmed: `_record_rejection_incident` runs only inside `run_operator_upgrade_request` post-auth (`:652`); 401/413/400-JSON return directly; `log_message` is silenced (`:722-723`). WINNER: both.
6. **In-memory / cross-restart replay window.** Both agree (Claude LOW, Codex MEDIUM). Confirmed: `_SEEN_SIGNATURE_NONCES` is a module global, no persistence (`:45`); on restart a still-fresh (±300s) signed request replays once. Adjudicated severity: MEDIUM (a captured request inside the window replays exactly once after any restart, no code mitigation). WINNER: both; Codex's MEDIUM rating preferred.

## GAPS BOTH MISSED (newly proven)
- **`internal: true` network containment of the `0.0.0.0` bind.** Neither audit stated that the `0.0.0.0` deployment bind is confined to a non-published, `internal: true` Docker network (`compose.yaml:1173-1174`; no `ports:` in 842-876). This materially downgrades the exposure concern: the broker is not reachable from the host or internet, only from peer containers on `operator-upgrade-broker-net` (joined by enrollment-provisioner/api-class services, lines 390/430/872/992).
- **Timestamp re-canonicalization in the signed message.** The HMAC msg uses the PARSED int `timestamp` (`:697`,`:710`), not the raw header string. This is a safening property neither flagged precisely: a malicious proxy cannot smuggle a differently-formatted timestamp (`"+123"`, `"0123"`, `" 123 "`) into the signed bytes because the broker always signs the canonical decimal form; the client signature must match that canonical form. No bypass.
- **Negative `Content-Length` handling.** `int("-5")` parses (no `ValueError`), so it is NOT coerced to 0 at `:740`, but the subsequent `length <= 0` test (`:742`) catches it → 413. Safe, but the safety comes from the `<= 0` clamp, not the `ValueError` handler — verified by probe.
- **Health POST behavior.** `POST /health` returns 404, not health, because `do_POST` only matches `/v1/operator-upgrade` (`:735`). (Codex noted this; recording as agreed for completeness.)

## RISKS (severity-ranked)
- MEDIUM: TOCTOU race in nonce replay check — lock released between `_nonce_seen` (`broker.py:705`,`:667-671`) and `_record_nonce` (`:715`,`:676-683`) with HMAC work between; `ThreadingHTTPServer` is multithreaded (`:764-766`). Two concurrent identical signed requests can both pass and both dispatch.
- MEDIUM: In-memory, per-process nonce store (`broker.py:45`) — no persistence; broker restart wipes it, allowing a captured still-fresh (±300s, `:701`) request to replay exactly once. Unmitigated in code.
- LOW: Auth-failure paths (401/413/400-JSON) are not incident-logged and `log_message` is silenced (`broker.py:722-723`, `:742-756`); `_record_rejection_incident` runs only post-auth (`:652`). No broker-side audit trail for brute-force/replay/bad-token attempts.
- LOW: Poll-seconds env parsed AFTER the pending request file is written — a non-numeric `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` raises `float()` (`broker.py:341`) after `_atomic_write_json` (`:339`), so the host runner may drain a request the broker reported as failed (400).
- LOW: No socket/read timeout (`broker.py:745`,`:764-766`); slow-body client can hold a thread, bounded by `MAX_REQUEST_BYTES=16384` (`:36`,`:742`) and internal-net containment.
- LOW: Coupled constant `REQUEST_SIGNATURE_TTL_SECONDS=300` (`broker.py:37`) is both the timestamp window (`:701`) and the nonce retention/eviction cutoff (`:666`,`:675`); sound within a live process but two semantics tied to one value.
- INFO: Deployment binds `0.0.0.0:8917` (`compose.yaml:865`) vs code default `127.0.0.1` (`broker.py:39`), but contained by `internal: true` network and no published `ports:` (`compose.yaml:1173-1174`).
- INFO: Signature binds only timestamp+nonce+body-hash, not HTTP method/path/content-type (`broker.py:707-713`); benign while only one mutating POST path exists.
- NONE on signature correctness: signed bytes, hash, key, separator, field order, and header names are byte-identical between P2 (`enrollment_provisioner.py:312-329`) and P3 (`broker.py:707-713`,`:41-44`). No drift.

## AGREED VERDICT
PROVABLY does its job for authentication/signature verification; replay protection is sound for sequential traffic but PROVABLY incomplete for two edges. Every POST to `/v1/operator-upgrade` must pass, in order: a cheap size clamp (413 before body read, `:742-744`), constant-time token equality (`hmac.compare_digest`, `:689`), a well-formed timestamp inside a symmetric ±300s window (`:697-702`), a regex-validated nonce (`:703`), a single-use replay check (`:705`), and a constant-time HMAC-SHA256 signature over the byte-identical signed string `timestamp\n nonce\n sha256(raw_body)` keyed by the broker token (`:707-713`). The signed-string and HMAC are byte-for-byte identical to the sole signer (P2, `enrollment_provisioner.py:312-320`), and because the broker hashes the exact wire bytes there is no canonicalization seam. `/health` is intentionally unauthenticated and leaks only token-configured-or-not (`:725-732`). All auth failures collapse to one generic 401 with no oracle (`:747`). The residual gaps: (1) a real TOCTOU race between the nonce check and record under the threaded server (MEDIUM), and (2) a non-persistent nonce store that yields a ≤300s cross-restart replay window (MEDIUM) — both meaning exactly-once nonce semantics are NOT guaranteed under concurrency or restart. The cryptographic ingress contract itself is correct and matches both neighbors; the replay layer is sound only for sequential, same-process traffic.


### Adjudicated cross-model disagreements


- **Concurrency atomicity of replay nonce check (TOCTOU)** — winner: **CODEX**  
  Claude: Stated replay protection is sound; missed the TOCTOU entirely, flagging only cross-restart in-memory wipe.  
  GPT-5.5: HIGH severity: _nonce_seen (705) and _record_nonce (715) use separate lock acquisitions with HMAC work between, so two simultaneous identical requests can both pass before either records.  
  Adjudication: Codex is mechanically correct: the lock is released between the check (667-671) and record (676-683); ThreadingHTTPServer is genuinely multithreaded (MRO confirms ThreadingMixIn), so the window is real and exploitable for a same-instant duplicate. Claude's 'sound' claim is wrong for the concurrent case. However HIGH overstates impact given the token is full trust, operations are coarse, and the listener is on an internal-only Docker net with no published host port; adjudicated to MEDIUM. `[python/arclink_operator_upgrade_broker.py:705,715,667,676,764-766]`

- **Bind host exposure (loopback vs 0.0.0.0)** — winner: **BOTH**  
  Claude: Binds loopback 127.0.0.1:8917 by default; 0.0.0.0 override is only a hypothetical INFO 'not set in this file'.  
  GPT-5.5: Actual deployment sets ARCLINK_OPERATOR_UPGRADE_BROKER_HOST=0.0.0.0 in compose; network is internal.  
  Adjudication: Both partly right. Code default IS 127.0.0.1 (broker.py:39,771) so Claude is correct on the code; the shipped config overrides to 0.0.0.0 (compose.yaml:865) so Codex is correct on deployment. The decisive nuance neither stated: the 0.0.0.0 bind is contained because the broker service publishes NO host ports (none in 842-876) and its only network is internal:true (compose.yaml:1173-1174) — reachable only from peer containers, not host/internet. `[python/arclink_operator_upgrade_broker.py:39,771; compose.yaml:865,1173-1174]`

- **Host-runner poll-seconds parsed after queueing the pending request** — winner: **CODEX**  
  Claude: Did not cover (treated host-runner internals as out of P3 scope).  
  GPT-5.5: MEDIUM: broker writes pending/<id>.json (339) before parsing ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS via float (341); a non-numeric value raises after queueing, so host runner can drain a request the broker reported as 400.  
  Adjudication: Mechanically correct: line 339 precedes line 341; non-numeric env raises ValueError caught at 651 -> 400 while the pending file persists. Codex wins existence. Severity reduced to LOW: requires operator misconfiguration of a numeric env var and is a P4-boundary detail. `[python/arclink_operator_upgrade_broker.py:338-342,651-653]`

- **No socket/read timeout on the listener** — winner: **CODEX**  
  Claude: Did not cover.  
  GPT-5.5: LOW: plain ThreadingHTTPServer, do_POST blocks on rfile.read(length) with no timeout.  
  Adjudication: Confirmed: grep shows no settimeout/handler timeout set; the read at 745 has no deadline. Codex wins. Bounded by MAX_REQUEST_BYTES=16384 and internal-net containment, so LOW. `[python/arclink_operator_upgrade_broker.py:745,764-766,36,742]`

- **In-memory / cross-restart replay window** — winner: **BOTH**  
  Claude: LOW: nonce store is per-process; restart wipes it leaving a <=300s replay window; unmitigated.  
  GPT-5.5: MEDIUM: same finding, rated MEDIUM.  
  Adjudication: Both correct on the fact (module global, no persistence at :45). A captured request inside the +/-300s window replays exactly once after any restart with no code mitigation; Codex's MEDIUM rating is the more appropriate severity. `[python/arclink_operator_upgrade_broker.py:45,701]`

- **Auth-failure not incident-logged** — winner: **BOTH**  
  Claude: LOW: 401/413/400-JSON return directly; _record_rejection_incident only runs post-auth; log_message silenced.  
  GPT-5.5: LOW: same finding.  
  Adjudication: Confirmed: _record_rejection_incident runs only inside run_operator_upgrade_request (652); auth-failure paths return directly; log_message is a no-op (722-723). Both correct. `[python/arclink_operator_upgrade_broker.py:652,722-723,742-756]`

- **P2/P3 signed-string byte identity** — winner: **BOTH**  
  Claude: Byte-identical: f-string ts/nonce/body_hash, sha256(raw_body), HMAC key=token, header names match.  
  GPT-5.5: Byte-identical, verified both ends; timestamp canonical so f-string reformat matches.  
  Adjudication: Independently re-confirmed both ends: P2 signs f-string at enrollment_provisioner.py:318 keyed at :316-320 over json.dumps(sort_keys=True) bytes; P3 recomputes over raw wire bytes at broker.py:707-712. Identical. Both correct; no drift. `[python/arclink_enrollment_provisioner.py:312-329; python/arclink_operator_upgrade_broker.py:41-44,707-713]`


### Risks (converged, severity-ranked)

- **[MEDIUM]** TOCTOU race in nonce replay check: the lock is released between _nonce_seen (check) and _record_nonce (record) with HMAC work in between, and ThreadingHTTPServer handles each request in its own thread. Two concurrent identical signed requests can both pass the replay check and both dispatch. `[python/arclink_operator_upgrade_broker.py:705,715,667,676,764-766]`
- **[MEDIUM]** Nonce replay store is an in-memory, per-process module global with no persistence. A broker restart wipes it, allowing a captured request still inside the +/-300s timestamp window to replay exactly once. No mitigation in code. `[python/arclink_operator_upgrade_broker.py:45,701]`
- **[LOW]** Authentication-failure responses (401 unauthorized, 413 bad size, 400 invalid JSON) return directly and are not recorded as rejection incidents; log_message is silenced. No broker-side audit trail for bad-token/replay/brute-force attempts. _record_rejection_incident runs only post-auth. `[python/arclink_operator_upgrade_broker.py:652,722-723,742-756]`
- **[LOW]** Host-runner poll-interval env var is parsed via float() AFTER the pending request file is atomically written. A non-numeric ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS raises ValueError (caught -> HTTP 400) while the host runner can still drain the already-queued pending file. `[python/arclink_operator_upgrade_broker.py:338-342,651-653]`
- **[LOW]** No socket/read timeout is configured; do_POST blocks on self.rfile.read(length) with no deadline, allowing a slow-body client to tie up a handler thread. Bounded by MAX_REQUEST_BYTES=16384 and internal-network containment. `[python/arclink_operator_upgrade_broker.py:745,764-766,36,742]`
- **[LOW]** Single constant REQUEST_SIGNATURE_TTL_SECONDS=300 serves as both the timestamp acceptance window and the nonce retention/eviction cutoff. Sound within a live process, but the two semantics are coupled to one value. `[python/arclink_operator_upgrade_broker.py:37,701,666,675]`
- **[INFO]** Deployment binds 0.0.0.0:8917 (compose override) versus code default 127.0.0.1, but exposure is contained: the broker service publishes no host ports and its only network operator-upgrade-broker-net is internal:true, so the listener is reachable only from peer containers. `[compose.yaml:865,1173-1174; python/arclink_operator_upgrade_broker.py:39]`
- **[INFO]** The HMAC signed message binds only timestamp, nonce, and body hash, not HTTP method/path/content-type. Benign while only one mutating POST path exists, but adding routes would not be covered by the signature. `[python/arclink_operator_upgrade_broker.py:707-713,734-737]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** Record says every POST auth failure collapses to `401 {"ok": false, "error": "unauthorized"}` with no distinguishing failure mode.  
  → correction: Most ordinary auth failures return 401, but malformed header values can escape the 401 branch and abort the handler instead of returning the documented JSON response. `[python/arclink_operator_upgrade_broker.py:689; python/arclink_operator_upgrade_broker.py:713; python/arclink_operator_upgrade_broker.py:746]`
- **[MEDIUM]** Record says timestamp failures are handled by `int()` parse or the ±300 second window and therefore return the generic 401.  
  → correction: The timestamp algorithm is `timestamp = int(timestamp_raw)` followed by `abs(now - timestamp) > 300`; not all malformed numeric timestamps are converted into False/401. `[python/arclink_operator_upgrade_broker.py:697; python/arclink_operator_upgrade_broker.py:701; python/arclink_operator_upgrade_broker.py:746]`
- **[MEDIUM]** Record states `raw_body = self.rfile.read(length)` reads exactly `Content-Length` bytes.  
  → correction: The broker authenticates and parses whatever bytes `rfile.read(length)` returns; a short read is not explicitly rejected by code. `[python/arclink_operator_upgrade_broker.py:745; python/arclink_operator_upgrade_broker.py:746]`
- **[LOW]** Record says post-auth non-UTF8/non-JSON bodies return `400 {"ok": false, "error": "invalid JSON"}`.  
  → correction: The 400 invalid-JSON branch is narrower than claimed; some syntactically malformed or rejected JSON inputs can escape the documented response path after valid auth. `[python/arclink_operator_upgrade_broker.py:750; python/arclink_operator_upgrade_broker.py:751]`
- **[LOW]** Record cites the deployment host override as `compose.yaml:865` and the port as `compose.yaml:866`.  
  → correction: The deployment override is real, but the load-bearing citations should be corrected to `compose.yaml:864` for host and `compose.yaml:865` for port. `[compose.yaml:864; compose.yaml:865]`
- **[LOW]** Record treats `internal: true` plus no Compose `ports:` as proving the broker is reachable only from peer containers and not from the host.  
  → correction: Publishable wording should say the Compose service has no `ports:` mapping and is on `operator-upgrade-broker-net` with `internal: true`; the stronger `not reachable from the host` claim should be labeled as an inference. `[compose.yaml:842; compose.yaml:864; compose.yaml:871; compose.yaml:1173]`


---

# P4 — Broker validation & normalization -> host-runner payload


**Both-model sign-off:** convergence `both_models_agree=True`; GPT-5.5 ratification `OBJECT` with 6 refinement(s) and 10 independent code re-confirmations.


## PIECE
P4 — Broker validation & normalization -> host-runner payload. File in scope: `python/arclink_operator_upgrade_broker.py`. Neighbors verified in code: producer `python/arclink_enrollment_provisioner.py`, consumer `python/arclink_operator_upgrade_host_runner.py`, gate `python/arclink_boundary.py`, deploy/compose wiring `compose.yaml` + `bin/deploy.sh` + `Dockerfile`.

## AGREED INPUT CONTRACT (re-confirmed in code)
Authenticated `request_body: dict[str, Any]`, parsed from a JSON object. HTTP entry is `do_POST`:
- Path must be `/v1/operator-upgrade`; else 404 — `arclink_operator_upgrade_broker.py:735-737`.
- `Content-Length` parsed as int (`ValueError`→0); must be `>0` and `<=MAX_REQUEST_BYTES(16384)`; else **413** — `:36`,`:739-744`.
- Raw body read, then `_is_authorized(headers, raw_body)` must pass before JSON parse; else **401** — `:745-748`.
- Body must decode UTF-8 + be a JSON object; else **400** — `:749-756`. Public `run_operator_upgrade_request` re-checks dict — `:639-640`.

Auth (`_is_authorized`, `:686-716`): token env `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` vs header `X-ArcLink-Operator-Upgrade-Broker-Token` via `hmac.compare_digest`, both non-empty — `:97-98`,`:688-690`; timestamp int within `REQUEST_SIGNATURE_TTL_SECONDS=300` (`abs(now-ts)`) — `:37`,`:697-702`; nonce matches `[A-Za-z0-9_.~+/=-]{16,160}` and unseen in TTL cache — `:703-706`; signature `= HMAC-SHA256(token, f"{timestamp}\n{nonce}\n{sha256hex(raw_body)}")` compared constant-time — `:707-715`; nonce recorded only on full success — `:715`.

Request fields read off `request_body`:
- `operation` — `str(request_body.get("operation") or "").strip()` (`:641`); allowlist exactly `run_operator_upgrade` (`:642`) / `run_pin_upgrade` (`:646`); else `ValueError("...operation is not allowlisted")` (`:650`).
- Forbidden keys `args`/`cmd`/`command` — presence of ANY → `ValueError("...does not accept raw commands")` via `_reject_raw_commands` (`:139-141`), called first in `_run_host_runner_request` (`:303`) and in-process fallbacks (`:496`,`:526`).
- `log_path` — `str(request_body.get("log_path") or "")` → `_require_operator_log_path` (`:307`,`:376-397`).
- `timeout_seconds` — `int(str(...get("timeout_seconds") or "").strip())`; on `TypeError/ValueError`→`7200`; clamped `[30,21600]` (`_operator_timeout`, `:368-373`).
- `upstream` — used only if `isinstance(dict)` (`:255-257`); per-key over `UPSTREAM_ENV_KEYS` (`:57-64`); non-dict silently dropped → `{}`.
- `install_items` — pin only; must be non-empty `list` (`:330`) else `ValueError`; each elem must be `dict` (`:334`) else `ValueError`; each normalized by `_normalized_pin_upgrade_item` (`:265-273`).

Host-derived inputs: `ARCLINK_DOCKER_HOST_REPO_DIR` required+resolved+absolute (`:119-126`); `ARCLINK_DOCKER_HOST_PRIV_DIR` required+absolute (`:110-116`); `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` default `/home/arclink/arclink/arclink-priv`, must be absolute AND contain `arclink-priv` part (`:129-136`).

Pin allowlists: `SAFE_COMPONENT_RE=^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$` (`:47`); `ALLOWED_PIN_COMPONENTS={hermes-agent,qmd,nextcloud,postgres,redis,nvm,node}` (`:48`); `PIN_UPGRADE_FLAGS={git-commit:--ref, git-tag:--tag, container-image:--tag, npm:--version, nvm-version:--version, release-asset:--version}` (`:49-56`). Component must match regex AND be in set (`:267`); kind must be in `PIN_UPGRADE_FLAGS` (`:271`); `target` only single-line ≤240 (`:270`).

Pre-everything gate: `require_docker_trusted_host_risk_accepted(service, ValueError)` runs first in the public entry (`:638`); requires `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED == "accepted"` (`arclink_boundary.py:19-20,80-97`).

## AGREED OUTPUT CONTRACT (re-confirmed in code)
Two modes gated by `_host_runner_enabled()` (`:249-251`, default ON; disabled only if stripped/lowered value ∈ `{0,false,no,off}`).

**(A) Host-runner payload dict (load-bearing transform), `:316-327`:**
- `schema_version` = int `HOST_RUNNER_SCHEMA_VERSION = 1` — `:93`,`:317`.
- `request_id` = `f"op-{int(time.time())}-{uuid.uuid4().hex}"` (`_host_runner_request_id`, `:291-292`,`:309`), re-validated against `HOST_RUNNER_REQUEST_ID_RE=^[a-z0-9][a-z0-9_.-]{7,80}$` (`:94`,`:310-311`).
- `created_at` = `int(time.time())` — `:319`.
- `operation` = validated string — `:320`.
- `repo_dir` = `str(_host_repo_dir())` (resolved, absolute) — `:304`,`:321`.
- `priv_dir` = `str(Path(_host_priv_dir()).resolve(strict=False))` — `:305-306`,`:322`.
- `container_priv_dir` = `_container_priv_dir()` raw validated string — `:323`.
- `log_path` = `str(log_path)` host-mapped from `_require_operator_log_path` — `:307`,`:324`.
- `timeout_seconds` = clamped int — `:308`,`:325`.
- `upstream` = `_normalized_upstream(...)` dict[str,str] of nonblank allowed keys, with private-path validation for `ARCLINK_UPSTREAM_DEPLOY_KEY_PATH`/`_KNOWN_HOSTS_FILE` — `:326`,`:254-262`,`:195-201`,`:157-192`.
- `install_items` (pin only) = list of `{component,kind,target}` — `:328-337`.

Side effects: `_atomic_write_json(queue_root/pending/{request_id}.json, payload)` writes `json.dumps(payload, sort_keys=True)+"\n"` via `.{name}.{pid}.tmp`+`os.replace` (`:295-299`,`:338-339`). Then polls `queue_root/results/{request_id}.json` (`:315`,`:344-361`) until `deadline = time.monotonic() + max(30, min(21630, timeout_seconds+30))` (`:340`,`:343`); poll interval = `float(POLL_SECONDS or "1")` clamped `[0.05,5.0]` (`:341-342`). On success returns `{"returncode": int, "host_runner": True, "request_id": str}` (`:360`). Non-dict / `ok is not True` / non-int `returncode` → `RuntimeError` (`:350-359`); no result before deadline → `RuntimeError("...did not complete...")` (`:362-365`).

`run_operator_upgrade_request` returns `(True, result_dict)` (`:644`,`:648`) or, on caught `OSError/RuntimeError/ValueError/SubprocessError`, records a rejection incident and returns `(False, str(exc))` (`:651-653`). HTTP: `200 {"ok":True,"result":dict}` (`:759`) or `400 {"ok":False,"error":str}` (`:761`); `_json_response` writes `json.dumps(...,sort_keys=True)+"\n"` (`:656-662`).

**(B) Host-runner disabled fallback:** `_run_operator_upgrade` runs `[deploy.sh,"upgrade"]` (`:495-510`); `_run_pin_upgrade` runs `[component-upgrade.sh, component, "apply", flag, target, "--skip-upgrade"]` per item then conditionally `deploy.sh upgrade` (`:513-565`). Returns `{"returncode": int}` only. No host-runner payload produced.

## TOUCH POINTS (re-confirmed)
Env: `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN` (`:97-98`); `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED` (`:638`→`boundary.py:82`); `ARCLINK_DOCKER_HOST_REPO_DIR` (`:120`); `ARCLINK_DOCKER_HOST_PRIV_DIR` (`:111`, also rejection-incident env_name `:626`); `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` (`:131`); `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED` (`:250`); `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` (`:277`, must be absolute + under `<priv>/state` `:280-287`); `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` (`:341`); `ARCLINK_OPERATOR_UPGRADE_BROKER_HOST`/`_PORT` (`:771-776`, code defaults `127.0.0.1:8917` `:39-40`); `ARCLINK_DOCKER_BINARY` + BASE/OPTIONAL child env keys only on the in-process path (`:69-89`,`:204-246`). On the host-runner path the broker builds NO child env.
Files: queue root `<priv>/state/operator-upgrade-host-runner` (default) `:288`; `pending/{id}.json` written `:338-339`; `results/{id}.json` read `:315,345-347`; log parent `mkdir(parents=True)` `:395`; rejection incident `private_state_rejection_path(SERVICE_NAME, env_name="ARCLINK_DOCKER_HOST_PRIV_DIR")` `:626`.
Subprocess argv: NONE on host-runner path; in-process only `[deploy,"upgrade"]` (`:505`) and pin argv (`:522`).
Socket: `ThreadingHTTPServer((host,port))` `:765`; **compose overrides host to `0.0.0.0:8917`** (`compose.yaml:864-865`) on dedicated net `operator-upgrade-broker-net` (`:872`).
Locks: in-proc `_SEEN_SIGNATURE_NONCES_LOCK` (`:46`,`:667`,`:676`); broker has NO file lock (the `runner.lock` flock is consumer-side, `host_runner.py:404,407-409`).

## CODE-PATH TRACE (agreed)
1. `do_POST` → path/size/auth/JSON/dict gates → `run_operator_upgrade_request(body)` — `:734-757`.
2. `require_docker_trusted_host_risk_accepted(...)` (`:638`); dict check (`:639`); `operation=str(...).strip()` (`:641`).
3. `run_operator_upgrade` + `_host_runner_enabled()` → `_run_host_runner_request("run_operator_upgrade", body)` (`:642-644`); else `_run_operator_upgrade` (`:645`).
4. `run_pin_upgrade` + enabled → `_run_host_runner_request("run_pin_upgrade", body)` (`:646-648`); else `_run_pin_upgrade` (`:649`); anything else → `ValueError` (`:650`).
5. `_run_host_runner_request`: `_reject_raw_commands` (`:303`) → `_host_repo_dir` (`:304`) → `_host_priv_dir`+resolve (`:305-306`) → `_require_operator_log_path` (`:307`) → `_operator_timeout` (`:308`) → `_host_runner_request_id`+regex (`:309-311`) → `_host_runner_queue_root` (`:312`) → build payload (`:316-327`).
6. Pin branch: non-empty list (`:330`); each dict (`:334`); `_normalized_pin_upgrade_item` (`:336`); assign `payload["install_items"]` (`:337`).
7. `_atomic_write_json(pending/{id}.json, payload)` (`:339`); poll results (`:344-361`); return `{returncode,host_runner,request_id}` (`:360`) or `RuntimeError` on timeout (`:362-365`).
8. Errors bubble to `:651-653` → rejection incident + `(False, str(exc))`.

## CROSS-PIECE CONTRACTS (both ends verified in code)
1. **Producer→broker signature.** Producer signs `HMAC-SHA256(token, f"{ts}\n{nonce}\n{sha256hex(body_bytes)}")` where `body_bytes=json.dumps(body, sort_keys=True).encode()` and POSTs `data=body_bytes` — `enrollment_provisioner.py:310-323`. Broker hashes the raw received bytes and recomputes the same pre-image — `:707-713`. Match holds because urllib transmits exactly `body_bytes`. Header constants byte-identical (`OPERATOR_UPGRADE_BROKER_TOKEN_HEADER` provisioner:99 == broker:41; timestamp/nonce/signature header strings provisioner:327-329 == broker:42-44). Nonce `secrets.token_urlsafe(18)` = 24 chars ∈ `{16,160}`. VERIFIED.
2. **Producer payload shape.** `_brokered_operator_payload` sends `{log_path, upstream}` (provisioner:352-356); pin adds `install_items` (provisioner:463) each carrying `component/kind/target` (provisioner:429-431,2433-2436) — matches broker reads (broker:266,269,270). Producer never sends `timeout_seconds` → broker default 7200 applies. VERIFIED.
3. **Allowlist parity (3 modules).** `ALLOWED_PIN_COMPONENTS`/`PIN_UPGRADE_FLAGS` byte-identical: broker `:48-56` == host_runner `:26-34` == provisioner `_pin_upgrade_apply_flag:411-418`. VERIFIED identical now (7 components, 6 kinds). Producer does NOT enforce the component allowlist; broker `:267` and host_runner `:264` are the enforcing boundaries.
4. **Broker→host-runner payload validation.** host_runner `_validate_request` re-checks: raw-cmd reject (`:280`); `schema_version==1` (`:282`, == broker constant `:93`/`:317`); `request_id` via identical regex (`host_runner:25,285` vs broker `:94`); operation allowlist (`:288`); `repo_dir`/`priv_dir` if present must equal host's resolved dirs (`:292-295`); `log_path` confined to `<priv>/state/operator-actions` via `_require_child_path` (`:296-302,108-120`); pin items re-validated (`:321-329`). VERIFIED.
5. **Result file.** Broker expects `ok is True` + int `returncode` (`:352-359`); host_runner writes `{ok,request_id,returncode|error+error_class,completed_at}` atomically (`host_runner:382-391`). VERIFIED.
6. **Log-path round trip.** Broker maps container-rooted path → host root and confines under `<host_priv>/state/operator-actions` (`:385-396`); host_runner requires under `<priv>/state/operator-actions` (`:296-302`). Broker emits the host-mapped path so the runner check passes. VERIFIED.
7. **Env-name family + queue dir wiring.** Broker reads `ARCLINK_DOCKER_HOST_REPO_DIR`/`_PRIV_DIR` (compose:857-858); host runner reads `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR`/`_PRIV_DIR` (`host_runner:69,80`) and rejects on mismatch (`:292-295`). Install wires both from `$BOOTSTRAP_DIR` (deploy.sh:8395-8397) and queue dir from `${ARCLINK_DOCKER_HOST_PRIV_DIR}/state/operator-upgrade-host-runner` (compose:862) vs `$BOOTSTRAP_DIR/arclink-priv/state/...` (deploy.sh:8397) — match iff `ARCLINK_DOCKER_HOST_PRIV_DIR==$BOOTSTRAP_DIR/arclink-priv`. Fail-closed on misconfig. VERIFIED templates (not live env).

## DISAGREEMENTS & ADJUDICATION
1. **Blank `log_path` severity (Codex MEDIUM vs Claude: confined).** Codex: blank `log_path`→`Path("").resolve()`=cwd, rejected only if cwd outside allowed roots; if broker cwd were inside operator-actions a blank could pass as a directory — `:307,381-397`. Claude: `_require_operator_log_path` confines the path. ADJUDICATION: Codex's mechanism is accurate (`Path("").resolve()` returns cwd `/home/arclink/arclink`; `_require_operator_log_path` accepts a directory path, not only files). BUT in the shipped deployment `WORKDIR=/home/arclink/arclink` (Dockerfile:71) and container priv = `/home/arclink/arclink/arclink-priv` (compose:859), so cwd is NOT under `…/arclink-priv/state/operator-actions` → blank is REJECTED at `:397`. Producer always sends a real `log_path` (provisioner:354). Real but non-exploitable as shipped → downgrade to LOW. Winner: **both** (Codex right on mechanism, Claude right on confinement outcome).
2. **HTTP status-code coverage.** Codex enumerated 404/413/401/400/200 (`:736,743,747,752,759-761`); Claude's OUTPUT contract only stated 200/400 for the result and omitted 413/401/404. Code: 413 (`:743`), 401 (`:747`), 404 (`:736`). No factual error in Claude, but a completeness gap. Winner: **codex** (more complete transport contract).
3. **`POLL_SECONDS` malformed handling.** Codex LOW: malformed value raises in `float(...)` with no local default-to-1 fallback, caught by outer handler → request fails (`:341-342`,`:651-653`). Claude omitted. Confirmed: `float("not-a-number")` raises `ValueError`, which is in the outer `except` tuple → `(False, str(exc))`. Winner: **codex** (real edge Claude missed).
4. **`runner.lock` flock attribution.** Claude noted the broker has no file lock and the flock is consumer-side (`host_runner:404,407-409`); Codex omitted. Confirmed correct; it is a host-runner concern, not P4-side. Winner: **claude** (extra correct cross-piece detail).
5. **`container_priv_dir` consumer trust.** Claude LOW: broker emits it (`:323`); host_runner copies into `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` child env with only single-line validation, no absoluteness/arclink-priv re-check (`host_runner:186,308-310`). Codex omitted. Confirmed: `_operator_env` receives the normalized single-line value (host_runner:334→337→186); broker DID check at `:134`, consumer does not. Winner: **claude** (real residual, LOW).
No material *conflicting* (mutually exclusive) claims exist; all deltas are completeness gaps or severity calibration, now reconciled.

## GAPS BOTH MISSED
1. **Compose binds the broker to `0.0.0.0:8917`, not the code default `127.0.0.1`** — `compose.yaml:864`. Both audits cited only the code default. Mitigated: dedicated `operator-upgrade-broker-net` (`compose.yaml:872`) and HMAC+nonce+TTL auth fence every request. Severity LOW/INFO.
2. **Broker writes the payload with plain `json.dumps` (`:298`), NOT `arclink_boundary.json_dumps_safe`/`reject_secret_material`.** So no plaintext-secret scrub on the queued payload. By design the `upstream` private keys are PATHS only (deploy-key path / known-hosts file), validated to stay under private state (`:157-192`), and key CONTENT never transits — so no secret leaks into the queue file. Worth recording. INFO.
3. **`container_priv_dir` and `priv_dir` may diverge but it is benign:** payload `priv_dir` is the HOST priv (`:322`) while `container_priv_dir` is the in-container path (`:323`); host_runner uses HOST `priv_dir` for log-root/env and only injects `container_priv_dir` as an env string (`host_runner:186,296`). No path-mismatch bug. INFO.
4. **`_operator_timeout` is called on the RAW `request_body`** (`:308`,`:368-370`), so any client-supplied `timeout_seconds` is honored within clamp `[30,21600]`; producer omits it so 7200 is used. Both implied it; explicitly: a client CAN shrink/extend within the clamp. INFO.

## RISKS (severity-ranked)
- LOW — env-name family divergence: broker repo/priv come from `ARCLINK_DOCKER_HOST_*` (compose:857-858), host runner from `ARCLINK_OPERATOR_UPGRADE_HOST_*` (`host_runner:69,80`), rejected on mismatch (`host_runner:292-295`); fails closed, broker cannot detect at enqueue time.
- LOW — blank `log_path` resolves to cwd and is only rejected by root-confinement (`:307,381-397`); safe as shipped because `WORKDIR=/home/arclink/arclink` (Dockerfile:71) ≠ operator-actions root.
- LOW — `container_priv_dir` trusted into child env with single-line-only validation, no absoluteness/arclink-priv re-check on consumer side (`host_runner:186,308-310`), unlike broker's own check (`:134`).
- LOW — malformed `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` raises in `float()` (`:341`), caught by outer handler → whole request fails; no local default fallback.
- LOW/INFO — compose binds `0.0.0.0:8917` (compose:864) vs code default 127.0.0.1; mitigated by dedicated net + HMAC auth.
- INFO — duplicated/triplicated constants (`ALLOWED_PIN_COMPONENTS`/`PIN_UPGRADE_FLAGS`, request-id regex, schema version) across broker/host-runner/provisioner; byte-identical now, drift-prone.
- INFO — pin `target` only single-line ≤240 (`:270`); semantic ref/tag/version safety delegated downstream to `component-upgrade.sh`.
- INFO — fallback (disabled) path uses `HOME=/home/arclink` (`:214`) while host runner uses `HOME=/root` (`host_runner:174`); only matters when host runner disabled.

## AGREED VERDICT
PROVABLY YES. With the host runner enabled (the code default, `:249-251`), the broker authenticates every request (HMAC-SHA256 over `timestamp\nnonce\nsha256(raw_body)`, TTL- and nonce-replay-protected, `:686-716`), fences entry behind the trusted-host risk gate (`:638`→`boundary.py:80-97`), rejects raw-command keys (`:303`), allowlists exactly two operations (`:642,646,650`), and performs a deterministic, explicitly-constructed transformation of the authenticated `request_body` into a typed schema-v1 host-runner payload (`:316-337`): stamping `schema_version=1`, minting a regex-conformant `request_id`, copying the validated `operation`, resolving required-absolute `repo_dir`/`priv_dir`/`container_priv_dir`, host-mapping and confining `log_path` under `<priv>/state/operator-actions`, clamping `timeout_seconds` to `[30,21600]`, path-validating the two upstream private-path keys, and (for pin) emitting a strictly allowlisted `{component,kind,target}` list. The payload is written atomically to `pending/`, and only an `ok:True` integer-`returncode` result is surfaced as success. Every payload key, every accept/reject branch, and both ends of all six cross-piece contracts (signature bytes, header names, allowlists, schema/regex, result file, log-path round trip, env/queue wiring) were re-traced to executable lines and agree. Residual issues are operational and fail-closed (env-name family divergence, blank-log_path-as-cwd which is non-exploitable as shipped, consumer-side `container_priv_dir` trust, malformed poll-seconds, `0.0.0.0` bind) — none break the proven transformation.


### Adjudicated cross-model disagreements


- **Blank log_path severity** — winner: **BOTH**  
  Claude: _require_operator_log_path confines the path under <priv>/state/operator-actions; treated as handled  
  GPT-5.5: MEDIUM: blank log_path -> Path('').resolve() = cwd, rejected only if cwd outside allowed roots; could pass if broker cwd were inside operator-actions  
  Adjudication: Codex's mechanism is accurate: Path('').resolve()=cwd and _require_operator_log_path accepts a directory path. But as shipped WORKDIR=/home/arclink/arclink (Dockerfile:71) and container priv=/home/arclink/arclink/arclink-priv (compose.yaml:859), so cwd is NOT under arclink-priv/state/operator-actions and a blank value is rejected at broker.py:397. Producer always sends a real log_path (provisioner:354). Real edge but non-exploitable as deployed -> LOW. `[python/arclink_operator_upgrade_broker.py:307,381-397; Dockerfile:71; compose.yaml:859; python/arclink_enrollment_provisioner.py:354]`

- **HTTP transport status-code coverage** — winner: **CODEX**  
  Claude: OUTPUT contract states 200 on success / 400 on error; omits 413/401/404  
  GPT-5.5: Enumerates 404 (wrong path), 413 (bad size), 401 (unauthorized), 400 (invalid JSON/non-dict), 200/400 (result)  
  Adjudication: Code returns 413 at :743, 401 at :747, 404 at :736, 400 at :752/:755, 200/400 at :759/:761. Claude made no factual error but under-enumerated the transport status codes; Codex is more complete. `[python/arclink_operator_upgrade_broker.py:736,743,747,752,755,759,761]`

- **Malformed POLL_SECONDS handling** — winner: **CODEX**  
  Claude: Not mentioned  
  GPT-5.5: LOW: malformed ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS raises in float(...) with no local default; caught by outer handler so the request fails  
  Adjudication: Confirmed: float('not-a-number') raises ValueError at :341, which is in the outer except tuple at :651 -> (False, str(exc)). No fallback to default 1. Real edge Claude missed. `[python/arclink_operator_upgrade_broker.py:341-342,651-653]`

- **runner.lock flock attribution** — winner: **CLAUDE**  
  Claude: Broker has no file lock; the runner.lock flock is consumer-side at host_runner.py:404,407-409  
  GPT-5.5: Not mentioned  
  Adjudication: Confirmed correct. The broker holds only the in-process nonce lock; serialization of queue draining is the host runner's flock. Correct extra cross-piece detail. `[python/arclink_operator_upgrade_broker.py:46,667; python/arclink_operator_upgrade_host_runner.py:404,407-409]`

- **container_priv_dir consumer-side trust** — winner: **CLAUDE**  
  Claude: LOW: broker emits container_priv_dir; host runner copies it into ARCLINK_DOCKER_CONTAINER_PRIV_DIR child env with only single-line validation, no absoluteness/arclink-priv re-check unlike broker's :134  
  GPT-5.5: Not mentioned  
  Adjudication: Confirmed: _operator_env receives the normalized single-line value (host_runner:334->337->186); the broker validated at :134 but the consumer only single-line-checks at :308-310. Real residual, LOW. `[python/arclink_operator_upgrade_broker.py:134,323; python/arclink_operator_upgrade_host_runner.py:186,308-310]`


### Risks (converged, severity-ranked)

- **[LOW]** Env-name family divergence: broker derives payload repo_dir/priv_dir from ARCLINK_DOCKER_HOST_REPO_DIR/_PRIV_DIR (compose.yaml:857-858) but the host runner reads ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR/_PRIV_DIR (host_runner.py:69,80) and rejects on mismatch (host_runner.py:292-295). Install wires both from $BOOTSTRAP_DIR; misconfiguration fails every brokered request closed and the broker cannot detect it at enqueue time. `[python/arclink_operator_upgrade_broker.py:304-306,321-322; python/arclink_operator_upgrade_host_runner.py:69,80,292-295; bin/deploy.sh:8395-8397]`
- **[LOW]** Blank/missing log_path resolves to cwd via Path('').resolve() and is rejected only by the operator-actions root-confinement check, not by a non-blank requirement. Safe as shipped because container WORKDIR=/home/arclink/arclink (Dockerfile:71) is outside arclink-priv/state/operator-actions (compose.yaml:859), so blank is rejected; non-exploitable but a confinement-only guard. `[python/arclink_operator_upgrade_broker.py:307,381-397; Dockerfile:71; compose.yaml:859]`
- **[LOW]** container_priv_dir is trusted into the runner child env with only single-line validation on the consumer side; no absoluteness/arclink-priv re-check (host_runner.py:186,308-310), unlike the broker's own check at broker.py:134. `[python/arclink_operator_upgrade_broker.py:134,323; python/arclink_operator_upgrade_host_runner.py:186,308-310]`
- **[LOW]** Malformed ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS raises ValueError inside float(...) with no local fallback to the default 1; the outer handler catches it and the whole request fails as a rejection. `[python/arclink_operator_upgrade_broker.py:341-342,651-653]`
- **[LOW]** Compose binds the broker to 0.0.0.0:8917 rather than the code default 127.0.0.1; mitigated by the dedicated operator-upgrade-broker-net and per-request HMAC+nonce+TTL auth, but the listen surface is broader than the code default suggests. `[compose.yaml:864-865,872; python/arclink_operator_upgrade_broker.py:39-40,765]`
- **[INFO]** Critical constants (ALLOWED_PIN_COMPONENTS, PIN_UPGRADE_FLAGS, request-id regex, schema version) are duplicated across broker, host runner, and provisioner instead of a shared import; byte-identical today but drift-prone. `[python/arclink_operator_upgrade_broker.py:47-56,94; python/arclink_operator_upgrade_host_runner.py:23-34; python/arclink_enrollment_provisioner.py:411-418]`
- **[INFO]** Pin target is only validated as a single line of <=240 chars (broker.py:270); semantic safety of refs/tags/versions is delegated downstream to component-upgrade.sh. `[python/arclink_operator_upgrade_broker.py:270; python/arclink_operator_upgrade_host_runner.py:267]`
- **[INFO]** Broker writes the queue payload with plain json.dumps (broker.py:298), not arclink_boundary.json_dumps_safe/reject_secret_material; no plaintext-secret scrub. By design upstream private keys are PATHS only and validated under private state (broker.py:157-192), so key content never transits the queue file. `[python/arclink_operator_upgrade_broker.py:298,157-192]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** The record says `ALLOWED_PIN_COMPONENTS`/`PIN_UPGRADE_FLAGS` are byte-identical across broker, host runner, and provisioner, with 7 components and 6 kinds.  
  → correction: Broker and host runner enforce the 7-component allowlist and 6-kind flag map; the provisioner only maps/validates kind flags and relies on downstream broker/runner component validation. `[python/arclink_operator_upgrade_broker.py:48; python/arclink_operator_upgrade_broker.py:265; python/arclink_operator_upgrade_host_runner.py:26; python/arclink_operator_upgrade_host_runner.py:262; python/arclink_enrollment_provisioner.py:410; python/arclink_enrollment_provisioner.py:429]`
- **[LOW]** The record says forbidden raw-command keys `args`/`cmd`/`command` have presence-of-any semantics for the request body.  
  → correction: Raw-command keys are rejected for allowlisted `run_operator_upgrade`/`run_pin_upgrade` requests on both host-runner and fallback paths; the operation gate runs first. `[python/arclink_operator_upgrade_broker.py:641; python/arclink_operator_upgrade_broker.py:650; python/arclink_operator_upgrade_broker.py:303; python/arclink_operator_upgrade_broker.py:496; python/arclink_operator_upgrade_broker.py:526]`
- **[LOW]** The record says `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` must be absolute and under `<priv>/state`.  
  → correction: The effective resolved queue root must be absolute and relative to `<host_priv>/state`; the raw configured string is not directly checked for absoluteness. `[python/arclink_operator_upgrade_broker.py:276; python/arclink_operator_upgrade_broker.py:280; python/arclink_operator_upgrade_broker.py:284]`
- **[LOW]** The record says any client-supplied `timeout_seconds` is honored within the `[30,21600]` clamp.  
  → correction: Only parseable, truthy integer-like values are clamped; missing, falsey, or malformed values default to `7200`. `[python/arclink_operator_upgrade_broker.py:368]`
- **[LOW]** The record cites `bin/deploy.sh:8395-8397` as wiring both the broker `ARCLINK_DOCKER_HOST_*` env family and the host-runner `ARCLINK_OPERATOR_UPGRADE_HOST_*` env family from `$BOOTSTRAP_DIR`.  
  → correction: Host-runner env is set at `8395-8397`; Docker `ARCLINK_DOCKER_HOST_REPO_DIR` and `ARCLINK_DOCKER_HOST_PRIV_DIR` are written at `8493-8494` and consumed by compose at `857-858`. `[bin/deploy.sh:8395; bin/deploy.sh:8493; compose.yaml:857]`
- **[LOW]** The record's accept/reject branch coverage for host-runner result files is complete.  
  → correction: A result file's internal `request_id` is ignored by the broker; success depends on result file path, `ok`, and `returncode`. `[python/arclink_operator_upgrade_broker.py:344; python/arclink_operator_upgrade_broker.py:352; python/arclink_operator_upgrade_broker.py:356; python/arclink_operator_upgrade_broker.py:360]`


---

# P5 — Broker queue handoff + result polling


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 3 refinement(s) and 11 independent code re-confirmations.


## PIECE
P5 — Broker queue handoff + result polling. Scope: `python/arclink_operator_upgrade_broker.py`, the `_run_host_runner_request` path (the half of the broker that, when the host runner is enabled, serializes a validated upgrade request to a queue file under private state, polls for the runner's result file, validates it, and returns a returncode). Entry from `run_operator_upgrade_request` (`python/arclink_operator_upgrade_broker.py:636-649`).

IMPORTANT PROVENANCE NOTE (governs the whole record): the in-scope file currently has an **UNCOMMITTED working-tree edit** (`git status --short` → ` M python/arclink_operator_upgrade_broker.py`). All line numbers below refer to the WORKING TREE (what runs now), which is what both audits cited. Committed HEAD `63a42c8` differs in the result-error path (see DISAGREEMENTS §1).

## AGREED INPUT CONTRACT (re-verified)
- Entry `_run_host_runner_request(operation: str, request_body: dict)` (`broker.py:302`); reached only for `operation in {"run_operator_upgrade","run_pin_upgrade"}` AND `_host_runner_enabled()` true (`broker.py:641-648`).
- `operation` — verbatim into payload (`broker.py:320`).
- `args`/`cmd`/`command` — ANY present → `ValueError` before any queue write (`broker.py:303` → `:139-141`).
- `log_path` — `str(request_body.get("log_path") or "")` → `_require_operator_log_path` (`broker.py:307`); must resolve under host or container `…/state/operator-actions`, container paths remapped to host root, `mapped_path.parent` `mkdir`-ed (`broker.py:376-397`). Host abs string stored (`broker.py:324`).
- `timeout_seconds` — `_operator_timeout` (`broker.py:308` → `:368-373`): `int(str(get("timeout_seconds") or "").strip())`, default 7200 on TypeError/ValueError, clamp `max(30, min(21600, value))`. Stored int (`broker.py:325`).
- `upstream` (if dict) — `_normalized_upstream` over 6 `UPSTREAM_ENV_KEYS` (`broker.py:57-64`, `:254-262`); the two path keys (`ARCLINK_UPSTREAM_DEPLOY_KEY_PATH`, `…_KNOWN_HOSTS_FILE`) containment+symlink checked vs the raw priv dir (`broker.py:65-68`, `:157-201`). Non-dict → `{}` (`broker.py:257`).
- `install_items` — ONLY for `run_pin_upgrade` (`broker.py:328-337`): non-empty `list`, each a dict, each normalized to exactly `{component,kind,target}` with `component ∈ ALLOWED_PIN_COMPONENTS` & `SAFE_COMPONENT_RE`, `kind ∈ PIN_UPGRADE_FLAGS`, `target` single-line ≤240 (`broker.py:48-56,:265-273`). Normalized list stored, not raw.
- Env inputs: `ARCLINK_DOCKER_HOST_REPO_DIR` (req, abs, resolved; `broker.py:119-126`), `ARCLINK_DOCKER_HOST_PRIV_DIR` (req, abs; `:110-116`), `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` (default `/home/arclink/arclink/arclink-priv`, abs, must contain `arclink-priv` part; `:129-136`), `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` (`:277`), `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` (`:341`), `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED` (default on; `:249-251`).
- Upstream producer of `request_body`: `arclink_enrollment_provisioner.py` builds `{"log_path","upstream"}` (`:352-356`) + `"operation"` injected (`:311`); pins add `install_items`.

## AGREED OUTPUT CONTRACT (re-verified)
- Success return dict (`broker.py:360`): `{"returncode": int(result.get("returncode")), "host_runner": True, "request_id": <id>}`. `host_runner`/`request_id` are inert downstream — the provisioner reads only `result.get("returncode")` (`enrollment_provisioner.py:384`).
- Wrapped by HTTP handler as `{"ok": True, "result": payload if isinstance(payload, dict) else {}}` HTTP 200 (`broker.py:757-759`). Failure → `(False, str(exc))` → HTTP 400 `{"ok": False, "error": …}` (`broker.py:760-761`).
- Queued JSON payload (broker → runner), keys (`broker.py:316-337`): `schema_version=1`, `request_id`, `created_at`(int epoch), `operation`, `repo_dir`, `priv_dir`(resolved), `container_priv_dir`, `log_path`(str), `timeout_seconds`(int), `upstream`(dict), and conditionally `install_items`. Serialized `json.dumps(payload, sort_keys=True)+"\n"` (`broker.py:298`).
- Side effects: exactly one request file `<queue_root>/pending/<request_id>.json` written atomically (`broker.py:313,338-339` → `:295-299`); `pending_dir` created implicitly via `_atomic_write_json` parent mkdir (`:296`); log-path parent mkdir (`:395`). Reads (never creates) `<queue_root>/results/<request_id>.json` (`:315,345-347`). On any failure path a rejection incident is appended to `<host_priv>/state/docker/operator-upgrade-broker/rejections.jsonl` when the priv base safely exists (`broker.py:623-633`; `arclink_rejection_incidents.py:80-101`).

## TOUCH POINTS (merged, re-verified)
- ENV `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED` default `"1"`, off for `{0,false,no,off}` (`broker.py:250-251`).
- ENV `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR`: if set must be absolute (`:281-282`) AND `relative_to(<host_priv>.resolve()/"state")` else `ValueError` (`:283-286`); else default `<host_priv resolved>/state/operator-upgrade-host-runner` (`:288`).
- ENV `ARCLINK_DOCKER_HOST_PRIV_DIR` (`:110-116`), `ARCLINK_DOCKER_HOST_REPO_DIR` (`:119-126`), `ARCLINK_DOCKER_CONTAINER_PRIV_DIR` (`:129-136`).
- ENV `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS`: `float(str(env or "1"))` then clamp `[0.05, 5.0]` (`:341-342`). NB: non-numeric → uncaught `ValueError` from `float()` (see RISKS).
- FILE WRITE (atomic) `<queue_root>/pending/<request_id>.json` via tmp `.<name>.<pid>.tmp` + `os.replace` (`:295-299,338-339`).
- FILE READ `<queue_root>/results/<request_id>.json` — read at most once per poll iteration, and on the terminal path exactly once total (`:347`).
- TIME — `time.monotonic()` deadline (`:343-344`), `time.sleep(poll_interval)` (`:361`), `time.time()` for `created_at`(`:319`) and request id (`:292`).
- `request_id = op-<int(time.time())>-<uuid4.hex>` (`:291-292`), re-validated vs `HOST_RUNNER_REQUEST_ID_RE = ^[a-z0-9][a-z0-9_.-]{7,80}$` (`:94,310-311`).
- No sockets/ports/locks in this piece. Locking lives on the runner (`runner.lock`, non-blocking `fcntl.flock`, `host_runner.py:404-409`).
- API ingress (P-other but adjacent): POST `/v1/operator-upgrade`, size `1..16384` (`:742`), HMAC auth (`:686-716`), JSON-object body (`:754`).

## CODE-PATH TRACE (agreed)
1. `run_operator_upgrade_request(body)`: trusted-host gate (`:638`), dict check (`:639`), `operation = str(get("operation") or "").strip()` (`:641`).
2. `run_operator_upgrade`+enabled → `_run_host_runner_request("run_operator_upgrade", body)` (`:643-644`); `run_pin_upgrade`+enabled → same call (`:647-648`). Both operations share one path; only the `install_items` block differs.
3. `_reject_raw_commands` (`:303`).
4. `repo_dir=_host_repo_dir()` (`:304`); `private_dir_raw=Path(_host_priv_dir())` (`:305`); `private_dir=…resolve(strict=False)` (`:306`).
5. `log_path=_require_operator_log_path(...)` (`:307`).
6. `timeout_seconds=_operator_timeout(...)` (`:308`).
7. `request_id=_host_runner_request_id()` (`:309`); regex re-check → `ValueError` if fail (`:310-311`).
8. `queue_root=_host_runner_queue_root()` (`:312`); `pending_dir`(`:313`), `results_dir`(`:314`), `result_path`(`:315`).
9. Build `payload` (`:316-327`).
10. (pin only) require non-empty list, each dict, normalize, store (`:328-337`).
11. `request_path=pending_dir/f"{request_id}.json"` (`:338`); `_atomic_write_json(request_path, payload)` (`:339`) — parent mkdir (`:296`), write tmp (`:297-298`), `os.replace` (`:299`).
12. `wait_seconds = max(30, min(21630, timeout_seconds+30))` (`:340`).
13. `poll_interval` from env, clamp `[0.05,5.0]` (`:341-342`).
14. `deadline=time.monotonic()+wait_seconds` (`:343`).
15. Loop `while time.monotonic() < deadline` (`:344`): if `result_path.exists()` (`:345`): read **once** `json.loads(result_path.read_text("utf-8"))`; on `OSError|JSONDecodeError` → `RuntimeError("…unreadable result")` (`:346-349`); non-dict → `RuntimeError("…invalid result")` (`:350-351`); `result.get("ok") is not True` → `RuntimeError(str(result.get("error") or result.get("message") or "…failed"))` **from the already-loaded dict, no second read** (`:352-355`); `returncode=int(result.get("returncode"))`, on `TypeError|ValueError` → `RuntimeError("…did not include an integer returncode")` (`:356-359`); else `return {returncode, host_runner:True, request_id}` (`:360`). Else `time.sleep(poll_interval)` (`:361`).
16. Deadline exceeded → `RuntimeError("…did not complete the queued request before timeout; check arclink-operator-upgrade-host-runner.timer…")` (`:362-365`).
17. Any of `(OSError,RuntimeError,ValueError,subprocess.SubprocessError)` → `_record_rejection_incident` (`:651-652`) → `(False, str(exc))`.

## CROSS-PIECE CONTRACTS (verified both ends)
1. **Queue-root path (broker → runner).** Broker: `…HOST_QUEUE_DIR` if set+abs+under `<HOST_PRIV>/state`, else `<HOST_PRIV resolved>/state/operator-upgrade-host-runner` (`broker.py:276-288`). Runner: `…HOST_QUEUE_DIR` if set+abs (NO containment check), else `<ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR>/state/operator-upgrade-host-runner` (`host_runner.py:87-92`). Default-equal ONLY because `bin/deploy.sh:8396-8397` sets `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR` and `…HOST_QUEUE_DIR` on the runner unit and `:8494` sets `ARCLINK_DOCKER_HOST_PRIV_DIR` for the broker, all to `…/arclink-priv[…]`. NOTE the env-var NAMES differ between ends and the runner does not mirror the broker's containment check — agreement is deploy-enforced, not code-enforced.
2. **Result schema (runner → broker).** Runner success `{"ok":True,"request_id","returncode":int,"completed_at":int}` (`host_runner.py:382`); failure `{"ok":False,"request_id","error":str,"error_class":str,"completed_at":int}` (`:384-390`), written atomically (`:391`). Broker requires dict, `ok is True`, int-coercible `returncode` (`broker.py:350-360`) and reads `error`/`message` on failure (`:354`). MATCHES. Runner atomic write is what makes the broker's single read safe.
3. **Request schema (broker → runner).** Broker `schema_version=1`; runner rejects `int(get("schema_version") or 0)!=1` (`host_runner.py:282-283`). `REQUEST_ID_RE` identical (`broker.py:94` == `host_runner.py:25`). `ALLOWED_PIN_COMPONENTS`/`PIN_UPGRADE_FLAGS`/`UPSTREAM_ENV_KEYS` byte-identical (`broker.py:48-64` == `host_runner.py:26-42`). Runner also re-validates repo_dir/priv_dir match, log containment, pin items (`host_runner.py:279-330`).
4. **Runner drain safety.** Runner globs `pending/*.json` (`host_runner.py:412`). VERIFIED empirically: pathlib `glob('*.json')` does NOT match the broker's hidden tmp sibling `.<name>.<pid>.tmp` (dotfile + `.tmp` suffix), so a half-written request can never be drained. End-to-end atomicity holds.
5. **HMAC signature (provisioner → broker).** Provisioner signs `HMAC_SHA256(token, f"{timestamp}\n{nonce}\n{sha256_hex(body_bytes)}")` (`enrollment_provisioner.py:312-320`); broker recomputes the identical bytes (`broker.py:707-713`). MATCHES.
6. **HTTP/caller.** Broker wraps `{"ok":True,"result":{returncode,host_runner,request_id}}` (`broker.py:757-759`); provisioner consumes only `result["returncode"]` defaulting to 2 on failure (`enrollment_provisioner.py:344-349,384-387`). Extra keys ignored. MATCHES.

## DISAGREEMENTS & ADJUDICATION
See structured `disagreements`. Summary of the load-bearing one: both audits correctly conclude the CURRENT code reads the result file once and inlines the error, but Claude attached a false git-provenance claim ("helper removed in 63a42c8") — 63a42c8 actually ADDED that helper, and the removal/inlining is an UNCOMMITTED working-tree edit (`git diff HEAD` proves it). Committed HEAD still re-reads via `_host_runner_result_error`. Codex described the current code accurately and made no false history claim. Both MISSED that the proven single-read behavior is uncommitted.

## GAPS BOTH MISSED
- **Uncommitted edit / committed HEAD differs.** `git diff HEAD -- python/arclink_operator_upgrade_broker.py` shows the `_host_runner_result_error` helper and its re-reading call (`raise RuntimeError(_host_runner_result_error(result_path))`) are present in committed HEAD 63a42c8 and removed only in the working tree. The single-read guarantee the prompt asked to verify is real but NOT yet committed. (Both audits implied it was settled in git.)
- **HTTP wrapper `else {}` fallback** at `broker.py:759`: if the success payload were ever not a dict it is replaced with `{}`. Inert for this piece (it always returns a dict) but neither audit cited it.
- **Rejection-incident write is a real failure-path side effect** (`broker.py:623-633` → `arclink_rejection_incidents.py:80-101`, path `<host_priv>/state/docker/operator-upgrade-broker/rejections.jsonl`). Codex cited it; Claude's audit omitted it from the side-effect list. Confirmed here.
- **glob/tmp non-collision** (verified empirically above) — a positive safety fact neither audit proved.

## RISKS
See structured `risks`.

## AGREED VERDICT
PROVABLY YES — the working-tree code does P5's job. It writes the validated request exactly once, atomically (tmp + `os.replace`) to `<queue_root>/pending/<request_id>.json` under a queue_root containment-checked to stay within `<host_priv>/state` (`broker.py:283-288,295-299,338-339`); polls the matching `results/<request_id>.json` on a monotonic deadline `clamp(timeout+30, 30, 21630)` with a `[0.05,5.0]s` interval (`:340-344`); enforces a strict success contract (dict, `ok is True`, int-coercible returncode) and maps every other outcome (unreadable, non-dict, `ok!=True`, non-int returncode, overall timeout) to a distinct RuntimeError surfaced as a 400 (`:345-365,651-653`). The result file is read exactly once on the terminal/error path with the error string taken from the already-parsed dict (`:347,352-355`) — the prompt's single-read requirement is satisfied in the working tree. Cross-piece queue-path, result-schema, request-schema, and HMAC contracts all match the host runner / provisioner ends. The one material caveat for the record: this single-read behavior is an UNCOMMITTED edit; committed HEAD 63a42c8 still re-reads the result file via `_host_runner_result_error`. The only true cross-piece fragility is that queue-root agreement is deploy-enforced (differing env-var names + the runner omitting the broker's containment check), not code-enforced.

## DISSECT cross-refs
- In scope: `/root/arclink/python/arclink_operator_upgrade_broker.py`
- Neighbors verified: `/root/arclink/python/arclink_operator_upgrade_host_runner.py`, `/root/arclink/python/arclink_enrollment_provisioner.py`, `/root/arclink/python/arclink_rejection_incidents.py`, `/root/arclink/bin/deploy.sh`


### Adjudicated cross-model disagreements


- **Provenance of the result-file single-read / removal of _host_runner_result_error helper** — winner: **CODEX**  
  Claude: The old re-reading _host_runner_result_error helper was confirmed REMOVED in commit 63a42c8; current code reads once and inlines the error.  
  GPT-5.5: Current code reads the result file once (json.loads at :347) and the ok!=True message uses the already-loaded result object inline; makes no claim about which commit removed a helper.  
  Adjudication: Verified via git. `git show 63a42c8 -- python/arclink_operator_upgrade_broker.py` shows commit 63a42c8 ADDED the `_host_runner_result_error` helper plus the re-reading call `raise RuntimeError(_host_runner_result_error(result_path))`. `git show HEAD:` confirms committed HEAD (which IS 63a42c8) still re-reads. The removal/inlining exists ONLY as an UNCOMMITTED working-tree edit (`git diff HEAD` shows the helper deleted and the message inlined at :352-355). So Claude's history attribution is backwards (63a42c8 added, not removed, the helper) and it failed to note the change is uncommitted. Codex's description of the *current* (working-tree) code is accurate and it made no false git claim. Both reach the correct conclusion that the running code now reads once. `[git diff HEAD -- python/arclink_operator_upgrade_broker.py (helper deleted, :352-355 inlined); git show HEAD:python/arclink_operator_upgrade_broker.py still has _host_runner_result_error; broker.py:347,352-355]`

- **returncode validation looseness severity** — winner: **BOTH**  
  Claude: Success requires int-coercible returncode (TypeError/ValueError caught); treats it as correct, no risk flagged.  
  GPT-5.5: MEDIUM: broker does not require returncode to be a JSON integer type; int() accepts numeric strings and truncatable floats, looser than 'integer type required'.  
  Adjudication: Codex is factually right that `int(result.get('returncode'))` (broker.py:357) accepts '3' (str→3), 3.9 (float→3), True (→1) — empirically confirmed. But the SOLE producer is the host runner writing a genuine JSON int via `int(returncode)` (host_runner.py:382), and the result file is written atomically, so a non-int returncode is unreachable in the real pipeline. The looseness is real but non-exploitable; severity should be low/info, not medium. Both ends correct on behavior; Codex's flag is valid but over-weighted. `[broker.py:356-359; host_runner.py:382]`

- **Queue-root cross-piece divergence** — winner: **BOTH**  
  Claude: LOW: env-var NAME asymmetry — broker defaults from ARCLINK_DOCKER_HOST_PRIV_DIR, runner from ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR; agreement only via deploy.sh.  
  GPT-5.5: MEDIUM: broker containment-checks the configured queue root under private state, runner's _queue_root only checks absolute and does NOT mirror that containment; env drift can desync the two ends.  
  Adjudication: Both are correct and describe two DISTINCT facets of the same fragility. Verified: broker.py:283-286 does `root.relative_to(host_state_root)`; host_runner.py:87-92 only does `is_absolute()` with no containment. AND the default-derivation env var names differ (broker.py:278 ARCLINK_DOCKER_HOST_PRIV_DIR vs host_runner.py:80 ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR). Neither audit is wrong; the merged risk combines both. Deploy.sh:8396-8397/8494 makes them agree as shipped. Net real-world impact (silent timeout on misconfig) is the same; treat as a single low/medium fragility. `[broker.py:278,283-286; host_runner.py:80-92; bin/deploy.sh:8396-8397,8494]`


### Risks (converged, severity-ranked)

- **[MEDIUM]** The proven single-read / inlined-error behavior on the ok!=True path is an UNCOMMITTED working-tree edit. Committed HEAD 63a42c8 still re-reads the result file via the _host_runner_result_error helper (raise RuntimeError(_host_runner_result_error(result_path))). Anyone reviewing or deploying the committed tree gets the double-read version; the audited single-read code is not yet in git. This is the single most important caveat for the record. `[git diff HEAD -- python/arclink_operator_upgrade_broker.py; git show HEAD:python/arclink_operator_upgrade_broker.py (helper present); working-tree broker.py:352-355]`
- **[MEDIUM]** Cross-piece queue-root agreement is deploy-enforced, not code-enforced. Broker containment-checks the configured queue dir under <host_priv>/state (broker.py:283-286) AND defaults it from ARCLINK_DOCKER_HOST_PRIV_DIR (broker.py:278); the host runner's _queue_root only checks is_absolute() with no containment (host_runner.py:90-92) and defaults from a DIFFERENT env var ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR (host_runner.py:80). If an operator sets one side's priv/queue env but not the other, broker and runner target different roots and every request silently times out at broker.py:362. `[broker.py:278,283-286; host_runner.py:80,87-92; bin/deploy.sh:8396-8397,8494]`
- **[LOW]** broker.py:341 poll_interval = float(str(env or '1')) has no try/except. A non-numeric ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS (e.g. 'abc') raises ValueError that propagates out of _run_host_runner_request, is caught at :651, recorded as a rejection, and returned as a 400 — the request fails instead of falling back to the 1s default. `[broker.py:341,651-653]`
- **[LOW]** broker.py:357 int(result.get('returncode')) coerces loosely: numeric strings ('3'->3), floats truncate (3.9->3), booleans (True->1) all pass the 'integer returncode' gate. Non-exploitable in practice because the only producer (host_runner.py:382) writes a genuine JSON int atomically, but the broker's validation is looser than its error message implies. `[broker.py:356-359; host_runner.py:382]`
- **[LOW]** If a results/<request_id>.json exists but is corrupt/non-dict, the broker fails immediately (RuntimeError) on the first poll rather than retrying until deadline. Only reachable via a corrupt or external writer since the runner writes atomically (host_runner.py:391); no stale/replay guard exists, but request_id uniqueness (op-<epoch>-<uuid4>, broker.py:292) makes pre-existing-result collision implausible. `[broker.py:345-351; host_runner.py:153-157,391]`
- **[INFO]** Atomic write is rename-atomic (os.replace) but not fsync-durable: a crash between tmp write and replace, or after replace before flush, can lose the request/result file. No durability fsync is performed on either side. Acceptable for a queue drained by a timer, noted for completeness. `[broker.py:295-299; host_runner.py:153-157]`
- **[INFO]** Caller-side timeout skew: broker internal poll waits timeout_seconds+30 (broker.py:340) but the upstream HTTP client urlopen timeout is only max(30,int(timeout_seconds)) with no +30 slack (enrollment_provisioner.py:334). A runner consuming nearly the full timeout can trip the caller socket ~30s before the broker's own deadline, so the broker's success return may never be observed. Caller-side (P-other) but affects whether this piece's success output is consumed. `[broker.py:340; enrollment_provisioner.py:334]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR`, when set, must be absolute on the broker, and the runner accepts it only if set+absolute.  
  → correction: Broker behavior is: `Path(configured).resolve(strict=False)`, then containment under `<host_priv>.resolve()/state`. Runner behavior is: `Path(configured).resolve(strict=False)` and no containment check. `[/root/arclink/python/arclink_operator_upgrade_broker.py:277; /root/arclink/python/arclink_operator_upgrade_broker.py:280; /root/arclink/python/arclink_operator_upgrade_broker.py:283; /root/arclink/python/arclink_operator_upgrade_host_runner.py:87; /root/arclink/python/arclink_operator_upgrade_host_runner.py:89]`
- **[LOW]** `ARCLINK_DOCKER_HOST_REPO_DIR` is required to be an absolute path.  
  → correction: The broker requires `ARCLINK_DOCKER_HOST_REPO_DIR` to be non-empty, then stores/uses the resolved path; it does not enforce raw-env absolute-ness. `[/root/arclink/python/arclink_operator_upgrade_broker.py:120; /root/arclink/python/arclink_operator_upgrade_broker.py:123; /root/arclink/python/arclink_operator_upgrade_broker.py:124]`
- **[LOW]** The downstream proof that `host_runner` and `request_id` are inert cites only the operator-upgrade consumer at `enrollment_provisioner.py:384`.  
  → correction: For pin upgrades, the provisioner sends `install_items`, receives the broker result, converts only `result.get("returncode")`, and ignores `host_runner` and `request_id`. `[/root/arclink/python/arclink_enrollment_provisioner.py:463; /root/arclink/python/arclink_enrollment_provisioner.py:465; /root/arclink/python/arclink_enrollment_provisioner.py:469]`


---

# P6 — Host-runner ingress: drain, lock, validate, lifecycle


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 3 refinement(s) and 8 independent code re-confirmations.


# P6 — Host-runner ingress: drain, lock, validate, lifecycle (CONVERGED)

File in scope: `/root/arclink/python/arclink_operator_upgrade_host_runner.py`. Producer neighbor: `/root/arclink/python/arclink_operator_upgrade_broker.py`. Consumers it execs: `/root/arclink/deploy.sh`, `/root/arclink/bin/component-upgrade.sh`. Lifecycle owner: systemd unit generated in `bin/deploy.sh:8383-8418`; wrapper `bin/arclink-operator-upgrade-host-runner.sh:1-7` execs the Python file.

## PIECE
The host-side systemd oneshot that drains broker-queued operator/pin upgrade requests from `<queue_root>/pending/*.json`, validates each under a strict fail-closed contract, executes only allowlisted host scripts with reconstructed argv, and writes exactly one result file per request to `<queue_root>/results/<request_id>.json`. Entry `main` (`:417`), `process_once` (`:399`), `_process_request_file` (`:367`), `_run_request` (`:333`), `_validate_request` (`:279`).

## AGREED INPUT CONTRACT (re-confirmed in code)
Request files are immediate `*.json` entries under `<queue_root>/pending` (`:403`,`:412`). Each is `json.loads(path.read_text(...))` and must be a dict (`:371-373`). Enforced by `_validate_request` (`:279-330`):
- Raw-command keys `args`/`cmd`/`command` rejected up-front (`:280-281`).
- `schema_version`: `int(... or 0) == HOST_RUNNER_SCHEMA_VERSION(==1)` (`:23`,`:282-283`). NOTE laxness below.
- `request_id`: `_single_line(allow_blank=False, max_chars=96)` (`:284`) AND `REQUEST_ID_RE.fullmatch` `^[a-z0-9][a-z0-9_.-]{7,80}$` (`:25`,`:285-286`). Re-validated earlier and independently in `_process_request_file` (`:374-376`).
- `operation`: single-line `max_chars=64` in `{run_operator_upgrade, run_pin_upgrade}` (`:287-289`).
- `repo_dir`/`priv_dir`: optional (`allow_blank=True`); if non-blank, `Path(...).resolve(strict=False)` must equal the host's resolved dir (`:290-295`).
- `log_path`: required single-line `max_chars=4096`, forced under `priv_dir/state/operator-actions` via `_require_child_path(..., mkdir_parent=True)` (`:296-302`,`:108-120`).
- `timeout_seconds`: `_operator_timeout` -> `int(str(... or "").strip())`, default 7200 on TypeError/ValueError, clamped `max(30, min(21600, value))` (`:160-165`,`:307`).
- `container_priv_dir`: optional single-line `max_chars=4096` only (`:308-310`).
- `upstream`: dict; only the six `UPSTREAM_ENV_KEYS` picked, each single-line `max_chars=4096`; non-dict -> `{}` (`:35-42`,`:313-320`).
- `run_pin_upgrade` only: `install_items` must be a non-empty list (`:322-324`); every element must be a dict (`:325-327`) and pass `_validated_pin_upgrade` BEFORE any command runs (`:328`); raw (un-normalized) list stored on `normalized["install_items"]` (`:329`).
- Each item (`_validated_pin_upgrade:262-271`): `component` non-blank `max_chars=96`, `SAFE_COMPONENT_RE` `^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$` AND in `ALLOWED_PIN_COMPONENTS={hermes-agent,qmd,nextcloud,postgres,redis,nvm,node}` (`:24`,`:26`,`:264-265`); `kind` non-blank `max_chars=64`, key of `PIN_UPGRADE_FLAGS` (`:27-34`,`:266`,`:268-270`); `target` non-blank `max_chars=240` (`:267`).
- Env input: `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR` (`:69`), `_PRIV_DIR` (`:80`), `_QUEUE_DIR` (`:88`); child-env keys (`:43-63`,`:170-195`).

## AGREED OUTPUT CONTRACT (re-confirmed)
Exactly one result JSON per request via `_atomic_write_json` to `<queue_root>/results/<request_id>.json` (`:377`,`:391`), shape:
- Success: `{"ok": true, "request_id": str, "returncode": int, "completed_at": int}` (`:382`).
- Failure (BaseException from `_run_request`): `{"ok": false, "request_id": str, "error": str(exc), "error_class": exc.__class__.__name__, "completed_at": int}` (`:383-390`).
- Bytes: `json.dumps(payload, sort_keys=True) + "\n"`, written to `.<name>.<pid>.tmp` then `os.replace` (atomic) (`:153-157`).
Side-effects: request file moved to `<queue_root>/processed/<orig name>` via `os.replace`, falling back to `unlink(missing_ok=True)` on OSError (`:392-396`) — always leaves `pending/`. Execution log truncated+written at `log_path` (`"w"` mode, `:341`): banner (`:342`), `$ <shlex-quoted argv>` per command (`:213`), combined stdout+stderr (`:219-223`), `[exit N]` / timeout text (`:228`,`:231`). `process_once`/`main` always return 0 on the happy path (`:414`,`:423`); the real returncode travels only in the result file, read by the broker (`broker:356-360`).

## TOUCH POINTS (agreed)
- ENV read (host paths): `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR`/`_PRIV_DIR`/`_QUEUE_DIR` (`:69`,`:80`,`:88`).
- ENV read for child env: `HOME,PATH,LANG,LC_ALL,LC_CTYPE,TZ,TERM,SSL_CERT_FILE,REQUESTS_CA_BUNDLE` (`:43-53`,`:170`); `ARCLINK_DOCKER_BINARY/IMAGE/NETWORK/UID/GID/SOCKET_GID, ARCLINK_STATE_ROOT_BASE, RUNTIME_DIR` (`:54-63`,`:191`).
- ENV set for children (passed via `subprocess.run(env=...)`, not host env): `ARCLINK_DOCKER_MODE=1, ARCLINK_CONTAINER_RUNTIME=docker, ARCLINK_COMPONENT_UPGRADE_MODE=docker, ARCLINK_REPO_DIR, ARCLINK_PRIV_DIR, ARCLINK_PRIV_CONFIG_DIR, ARCLINK_DOCKER_HOST_REPO_DIR, ARCLINK_DOCKER_HOST_PRIV_DIR, ARCLINK_DOCKER_CONTAINER_PRIV_DIR, STATE_DIR, ARCLINK_CONFIG_FILE` (`:176-189`); defaults HOME=/root (`:174`), PATH=os.defpath (`:175`), RUNTIME_DIR=/opt/arclink/runtime (`:195`); upstream keys merged (`:196-201`).
- FILE read: each `pending/*.json` (`:371`); the execution log re-read by `_pin_upgrade_log_requires_deploy` (`:250`).
- FILE write: `results/<id>.json` (`:391`); `<log_path>` truncated (`:341`); request -> `processed/` (`:394`); tmp `.<name>.<pid>.tmp` (`:155`).
- DIR mkdir: `pending`,`results` (`:405-406`), `processed` (`:392`), log parent (`:118-119`), result parent (`:154`).
- SUBPROCESS (operator): `[<repo>/deploy.sh, "upgrade"]` cwd=repo, `stdin=DEVNULL, stdout=handle, stderr=STDOUT, check=False, timeout=timeout_seconds` (`:216-226`,`:345`).
- SUBPROCESS (pin, per item): `[<repo>/bin/component-upgrade.sh, component, "apply", flag, target, "--skip-upgrade"]` (`:274-276`,`:354-355`); then `[<repo>/deploy.sh,"upgrade"]` only if `_pin_upgrade_log_requires_deploy` True (`:359-363`).
- LOCK: `fcntl.flock(lock_handle.fileno(), LOCK_EX | LOCK_NB)` on `<queue_root>/runner.lock` (`:404`,`:407-409`).
- UMASK: `os.umask(0o077)` in `main` before `process_once` (`:422`).
- No sockets/ports opened by this file (`:216-226` is the only external boundary).
- Script allowlist `_require_repo_script` lstat-walks each component, rejects absolute/`..`/symlink/non-regular/non-readable/non-executable, then `resolve(strict=True).relative_to(repo)` (`:123-150`), used for deploy.sh and component-upgrade.sh (`:335-336`).

## CODE-PATH TRACE (agreed)
1. `main(argv)` (`:417`): argparse `--once` parsed then discarded (`:419-421`); `os.umask(0o077)` (`:422`); `process_once()` (`:423`). NO try/except — a `process_once` exception propagates to `raise SystemExit(main())` and exits nonzero (confirmed: only try/except in main path are the BlockingIOError guard `:408-410` and the in-file `:380-396`).
2. `process_once` (`:399-414`): `_repo_dir` (`:400`,`:68-76` env-or-`parents[1]`, must be absolute); `_priv_dir` (`:401`,`:79-84` env-or-`repo/arclink-priv`, must be absolute and `name=="arclink-priv"`); `_queue_root` (`:402`,`:87-92` env-or-`priv/state/operator-upgrade-host-runner`, must be absolute); mkdir `pending`+`results` (`:405-406`); open `runner.lock`, `flock(LOCK_EX|LOCK_NB)` -> on `BlockingIOError` `return 0` (single-instance guard, `:407-411`); drain `sorted(pending.glob("*.json"), key=lambda i:(i.stat().st_mtime, i.name))` (`:412`), call `_process_request_file` per file (`:413`); `return 0`, lock released on `with` exit.
3. `_process_request_file` (`:367-396`): `path.lstat()`, reject `S_ISLNK` or not `S_ISREG` (`:368-370`); `json.loads` -> must be dict (`:371-373`); `request_id` single-line + regex (`:374-376`) — ALL THREE raise BEFORE the try at `:380`; compute `result_path`/`done_dir` (`:377-378`); try `returncode=_run_request(...)` -> success dict (`:380-382`); except `BaseException` -> failure dict (`:383-390`); `_atomic_write_json` (`:391`); mkdir `processed`; `os.replace` else `unlink(missing_ok=True)` (`:392-396`).
4. `_run_request` (`:333-364`): `_validate_request` (`:334`); `_require_repo_script` for deploy.sh + component-upgrade.sh (`:335-336`); `_operator_env` (`:337`); open log `"w"`, banner (`:341-342`). run_operator_upgrade: one `[deploy,"upgrade"]`, return rc (`:344-346`). run_pin_upgrade: re-check list/dict (`:349-353`), per-item argv via `_pin_upgrade_command` (re-calls `_validated_pin_upgrade`, `:274-276`,`:354`), run each (`:355`), return on first nonzero (`:356-357`); then `_pin_upgrade_log_requires_deploy(log_path, expected_statuses=len(install_items))` (`:359`) reading `ARCLINK_COMPONENT_UPGRADE_STATUS=` markers (`:236-259`): deploy if fewer than N markers, any marker not in `{noop,changed,pushed}`, or any in `{changed,pushed}`; if no deploy -> note + last rc (`:360-362`); else final `[deploy,"upgrade"]` (`:363-364`).

## CROSS-PIECE CONTRACTS (both ends verified in code)
1. **Queue path.** Runner default `priv/state/operator-upgrade-host-runner` (`:89`) == broker default `Path(_host_priv_dir()).resolve()/state/operator-upgrade-host-runner` (`broker:278,288`); both honor `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR`; systemd pins all three to `$BOOTSTRAP_DIR/...` (`deploy.sh:8395-8397`). Subpaths identical: broker writes `pending/<id>.json` (`broker:313,338-339`), runner reads `pending/*.json` (`:403,412`); runner writes `results/<id>.json` (`:377,391`), broker polls it (`broker:314-315,345`). MATCH.
2. **Schema version.** Runner `==1` (`:282-283`); broker writes integer `1` (`broker:93,317`). MATCH.
3. **request_id.** Runner `^[a-z0-9][a-z0-9_.-]{7,80}$` (`:25`); broker generates `f"op-{int(time.time())}-{uuid4().hex}"` and self-checks the identical regex (`broker:94,291-292,310-311`). MATCH.
4. **operation allowlist.** Both `{run_operator_upgrade, run_pin_upgrade}` (`:288`; `broker:642-649`). MATCH.
5. **repo_dir/priv_dir equality.** Broker writes `str(_host_repo_dir())`/`str(resolved host priv)` (`broker:321-322,304-306`); runner resolve-compares to env-derived dirs (`:292-295`), blank-tolerant. MATCH (mismatch only if non-empty and divergent).
6. **log_path.** Broker maps container/host `state/operator-actions` -> host `state/operator-actions` with symlink/`..`-safe relative_to (`broker:376-397`); runner independently forces under `priv/state/operator-actions` (`:296-302`). Same root. MATCH.
7. **install_items shape.** Broker normalizes to `{component,kind,target}` with identical allowlists/regex (`broker:265-273`); runner re-validates each up-front (`:328`) and again per command (`:275`). DRIFT-SURFACE: `ALLOWED_PIN_COMPONENTS`, `PIN_UPGRADE_FLAGS`, `SAFE_COMPONENT_RE`, `HOST_RUNNER_SCHEMA_VERSION`, request-id regex, `UPSTREAM_ENV_KEYS`, env-key tuples and `_atomic_write_json`/`_operator_timeout` are DUPLICATED in both files (runner `:24-34,93-94 equiv`; broker `:47-56,93-94,265-273,295-299,368-373`) with NO shared import — verified textually identical at this commit. Fails closed today (runner is the gate).
8. **component-upgrade.sh argv.** Runner `[script, component, "apply", flag, target, "--skip-upgrade"]` (`:276`); consumer usage `<component> apply [--ref|--tag|--version V] ... [--skip-upgrade]` (`component-upgrade.sh:52-53`, parse `:680-687`). MATCH.
9. **Status markers.** Runner allowlists `{noop,changed,pushed}` (`:257`); producer `status_marker` emits exactly `noop`/`pushed`/`changed` (`component-upgrade.sh:46,614,623,631,665,668`). MATCH.
10. **Broker vs runner timeout.** Broker poll deadline `max(30, min(21630, timeout+30))` (`broker:340`); runner subprocess clamp `min(21600, value)` (`:165`). Broker always waits ≥30s longer than runner's max. MATCH.

## DISAGREEMENTS & ADJUDICATION
- **Severity of malformed-file ingress (Claude MEDIUM vs Codex HIGH).** WINNER: codex. Both correctly find that lstat/json/request_id raises (`:368-376`) occur BEFORE the try at `:380`, so they are NOT captured into a result file, the poison file is never moved out of `pending/`, and `process_once` propagates the exception to `main` (no try/except) -> process exits nonzero. Claude framed it as a "head-of-line block, no crash" MEDIUM; Codex framed it HIGH and additionally identified that a **broken symlink ending in `.json` raises inside the SORT KEY at `:412` (`item.stat().st_mtime`, which follows the symlink) before `_process_request_file`'s lstat guard at `:368` can run** — empirically reproduced: `item.stat()` on a dangling-symlink `*.json` raises `FileNotFoundError`, so the ENTIRE drain pass dies before processing any file. Codex's extra finding is real and load-bearing; severity HIGH is correct. (Impact bounded to a denial-of-drain; not a confinement/security break, but it is the most material defect in the piece.)
- **install_items up-front validation (NOTE in prompt).** WINNER: both. Re-confirmed: the loop at `:325-328` calls `_validated_pin_upgrade` on every item and raises on the first bad one, and `normalized["install_items"]` is only set AFTER the loop (`:329`); execution re-validates each item inside `_pin_upgrade_command` (`:354->275->262-271`). A disallowed component/kind cannot reach a subprocess. Both audits agree; confirmed.
- **schema_version type-strictness (Codex MEDIUM; Claude silent).** WINNER: codex. Re-confirmed by execution: `int(x or 0) == 1` accepts `True`, `1.9`, `"1"` as valid; `"abc"`/`[1]` raise (caught by `:383`). Claude omitted this. Low real impact (broker always writes integer 1, `broker:317`); reachable only by direct queue tampering inside the trusted boundary.
- **container_priv_dir / upstream deploy-key path confinement (Codex MEDIUM; Claude INFO-folded).** WINNER: codex (on the asymmetry being real), with Claude's trust-boundary framing also correct. Re-confirmed: the broker applies strong symlink/`..`/under-private-state confinement to upstream key paths (`broker:157-192`) and confines the configured queue root under private state (`broker:283-286`); the runner applies ONLY `_single_line` to `container_priv_dir` (`:308-310`) and upstream keys (`:317`) with no path confinement, then passes them to the child env (`:186,196-201`). This is a defense-in-depth gap exploitable only by writing directly into the root-owned host queue, i.e. already inside the trusted host boundary. Adjudicated LOW-MEDIUM.

## GAPS BOTH MISSED
- **Broken-symlink-in-sort vs valid-symlink-in-lstat is a TWO-tier failure, only Codex caught tier 1.** Claude's lstat-guard reasoning (`:368-370`) is correct ONLY for a symlink whose target EXISTS (the sort `item.stat()` succeeds, then lstat rejects). For a DANGLING symlink, the failure happens one layer earlier in the sort key (`:412`) and Claude's "lstat rejects it" claim does not apply. Confirmed empirically.
- **`run_operator_upgrade` still requires `bin/component-upgrade.sh` to pass `_require_repo_script` (`:336`) even though it only execs `deploy.sh upgrade`** (Codex LOW; Claude missed). A missing/non-exec/symlinked component-upgrade.sh would fail an operator-only upgrade with a confusing error, but this is captured into the error result file (`:383`) and is fail-closed. Confirmed (`:335-336` run unconditionally before the operation branch at `:344`).
- **`_pin_upgrade_log_requires_deploy` reads the SAME log the runner just wrote in `"w"` mode and parses the LAST N status markers (`:254`).** Neither audit flagged the edge that if `component-upgrade.sh` emits MORE than one `ARCLINK_COMPONENT_UPGRADE_STATUS=` line per item (it can emit multiple, `:614-668`), `statuses[-N:]` could mis-attribute markers across items. In practice each successful item ends with one terminal marker and the `< N` / not-in-allowlist branches fail safe to "deploy needed" (`:255-258`), so the worst case is an unnecessary `deploy.sh upgrade` — fail-safe, not unsafe. Noted as INFO.

## RISKS
See structured `risks`. Highest: broken-symlink drain crash + general malformed-file denial-of-drain (HIGH); allowlist/constant duplication drift (LOW, fails closed); schema_version type-laxness (LOW); runner-side missing path confinement for container_priv_dir/upstream keys vs broker (LOW-MEDIUM, trust-boundary-bounded); log `"w"` truncation on replay (LOW).

## AGREED VERDICT
P6 PROVABLY does its core job for well-formed broker-produced requests: single-instance via `flock(LOCK_EX|LOCK_NB)` with a clean `return 0` on contention (`:404,407-411`), deterministic `(mtime, name)` drain (`:412`), `0o077` umask before any write (`:422`), a strict fail-closed input contract (schema==1, request_id regex, operation allowlist, host repo/priv equality, log_path confinement under operator-actions, fully-validated install_items before any subprocess), raw-command rejection (`:280-281`), symlink/mode-checked script allowlisting (`:123-150`), reconstructed argv only, exactly one atomic result file per request, and unconditional eviction from `pending/`; in-request BaseException is captured as `{"ok": false, ...}` without crashing (`:383-396`); and all ten cross-piece contracts with the broker and the two shell consumers verify-match at this commit. The piece does NOT fully satisfy a robust ingress requirement: malformed pending entries (dangling-symlink `.json`, invalid/non-object JSON, bad request_id) raise BEFORE the result-capture block — and a dangling symlink raises inside the sort key itself (`:412`) before any lstat guard — with no try/except in `process_once`/`main`, so a single poison file in `pending/` is never evicted and head-of-line-blocks (and, for the broken symlink, crashes) every subsequent drain pass indefinitely. This is a real availability defect (HIGH) but not a confinement/security break (the runner remains the gate and fails closed). The only fix needed is to wrap the per-file pre-validation (and the sort/glob) in the same per-file guard that already protects `_run_request`.


### Adjudicated cross-model disagreements


- **Severity of malformed/symlink request file handling** — winner: **CODEX**  
  Claude: MEDIUM — _process_request_file raises (not captures) for symlink/non-regular (:368-370), non-JSON/non-dict (:371-373), bad request_id (:374-376) before the try at :380; one poison file head-of-line-blocks the drain indefinitely but framed as operational, not a crash.  
  GPT-5.5: HIGH (two findings): (1) those same pre-try raises are not captured into result files; (2) additionally a broken symlink ending in .json fails during the SORT itself because item.stat().st_mtime at :412 runs before _process_request_file's lstat rejection at :367-370.  
  Adjudication: Empirically reproduced: a dangling-symlink *.json in pending/ makes item.stat() in the sort key at :412 raise FileNotFoundError, killing process_once before ANY file is processed and before the lstat guard at :368 is reachable. process_once/main have no try/except (verified :408-423), so the exception propagates to raise SystemExit(main()) -> nonzero exit. The file is never moved out of pending/, so every subsequent timer tick re-crashes: permanent denial of drain. Codex's extra sort-key finding is correct and load-bearing; Claude's lstat-rejects reasoning holds only for symlinks whose target exists. HIGH is the right severity (bounded to availability, not a confinement break). `[python/arclink_operator_upgrade_host_runner.py:412 (sort key item.stat()), :367-370 (lstat guard, unreachable for dangling symlink), :380-383 (BaseException capture wraps only _run_request), :417-423 (main has no try/except)]`

- **schema_version type-strictness** — winner: **CODEX**  
  Claude: Stated schema_version coerced int(... or 0) must equal 1; did not flag type-laxness.  
  GPT-5.5: MEDIUM — not type-strict: JSON true, numeric 1.9, or string "1" satisfy int(value)==1.  
  Adjudication: Confirmed by execution: int(x or 0)==1 returns True for True, 1.9, and "1"; "abc"/[1] raise (caught by :383). Codex is correct that the check is lax. Real impact is LOW: the broker always writes integer 1 (broker:317), so non-integer schema_version is only reachable by direct queue tampering inside the trusted host boundary. Claude omitted it. `[python/arclink_operator_upgrade_host_runner.py:282-283; python/arclink_operator_upgrade_broker.py:317]`

- **Runner-side path confinement for container_priv_dir and upstream deploy-key paths** — winner: **CODEX**  
  Claude: Folded into an INFO note: only reachable by manual queue tampering inside the trusted host boundary.  
  GPT-5.5: MEDIUM — runner only single-line-checks container_priv_dir and upstream deploy-key/known-hosts paths; the broker applies stronger private-path confinement (symlink/..-rejecting, must stay under private state) that the runner does not replicate for direct queue files.  
  Adjudication: Both are right on different axes. Confirmed broker enforces under-private-state, symlink-rejecting, ..-rejecting checks for upstream key paths (broker:157-192) and confines the configured queue root under private state (broker:283-286); the runner applies only _single_line (:308-310, :317) then forwards to child env (:186,196-201). The asymmetry is real defense-in-depth drift (Codex), but exploitation requires writing into the root-owned host queue, i.e. already inside the trusted boundary (Claude). Adjudicated LOW-MEDIUM. `[python/arclink_operator_upgrade_host_runner.py:308-310,317,186,196-201; python/arclink_operator_upgrade_broker.py:157-192,283-286]`

- **install_items validated up-front before any command runs** — winner: **BOTH**  
  Claude: Every item validated in the :325-328 loop before normalized['install_items'] is set (:329); re-validated at execution via _pin_upgrade_command (:354->275). A disallowed item cannot reach a subprocess.  
  GPT-5.5: All install_items validated up front before any command can run (:321-329, :333-355).  
  Adjudication: Re-confirmed in code: the loop at :325-328 calls _validated_pin_upgrade on each item and raises on the first bad one; normalized['install_items'] assigned only after the loop (:329); execution re-validates inside _pin_upgrade_command (:274-276 -> :262-271). Both audits agree and are correct. `[python/arclink_operator_upgrade_host_runner.py:325-329,354,274-276,262-271]`


### Risks (converged, severity-ranked)

- **[HIGH]** Malformed/poison pending file denies drain (and a dangling-symlink *.json crashes the whole pass). _process_request_file raises for non-regular/symlink (:368-370), non-JSON/non-dict body (:371-373), and bad request_id (:374-376) BEFORE the try at :380, so no result file is written and the file is never moved out of pending/. Worse, a broken symlink raises inside the sort key item.stat() at :412 before the lstat guard at :368 even runs (empirically reproduced: FileNotFoundError). process_once and main have no try/except (:408-423), so the exception propagates to raise SystemExit(main()) and exits nonzero; the next timer tick re-encounters the same file and re-crashes/re-blocks indefinitely. Availability defect, not a confinement break (runner remains the gate). Fix: wrap the per-file pre-validation and the sort/glob in the same per-file guard that already protects _run_request at :380-390. `[python/arclink_operator_upgrade_host_runner.py:412, :367-376, :380-396, :417-423]`
- **[LOW]** Allowlist/constant duplication with no shared import: HOST_RUNNER_SCHEMA_VERSION, REQUEST_ID_RE, SAFE_COMPONENT_RE, ALLOWED_PIN_COMPONENTS, PIN_UPGRADE_FLAGS, UPSTREAM_ENV_KEYS, env-key tuples, _atomic_write_json and _operator_timeout are independently re-declared in the broker. Verified textually identical at this commit, but there is no compile-time link. Fails closed today (runner is the gate); a future one-sided edit broadening the runner allowlist would be the dangerous direction. `[python/arclink_operator_upgrade_host_runner.py:23-34,95-105,153-165,279-281; python/arclink_operator_upgrade_broker.py:47-56,93-94,144-154,265-273,295-299,368-373]`
- **[LOW]** schema_version check int(request_body.get('schema_version') or 0)==1 is not type-strict: JSON true, 1.9, and "1" all pass; 'abc'/[1] raise (caught by :383). Reachable only by direct queue tampering since the broker always writes integer 1. `[python/arclink_operator_upgrade_host_runner.py:282-283; python/arclink_operator_upgrade_broker.py:317]`
- **[LOW]** Runner does not replicate the broker's strong private-path confinement for container_priv_dir (:308-310) or upstream deploy-key/known-hosts paths (:317); it only _single_line-checks them, then forwards them into the child env (:186,196-201). The broker enforces symlink/..-rejecting, under-private-state checks (broker:157-192). Defense-in-depth drift exploitable only by writing directly into the root-owned host queue inside the trusted boundary. `[python/arclink_operator_upgrade_host_runner.py:308-310,317,186,196-201; python/arclink_operator_upgrade_broker.py:157-192]`
- **[LOW]** log_path is opened in 'w' truncation mode (:341); a replayed/re-queued request reusing the same broker-chosen log_path silently overwrites the prior execution log. Confinement under operator-actions is preserved; the loss is observability only. No replay/idempotency key beyond the filename (request_id includes uuid4 so natural collisions are nil; results/<id>.json would be overwritten on replay). `[python/arclink_operator_upgrade_host_runner.py:341, :377, :391-396]`
- **[INFO]** run_operator_upgrade unconditionally requires bin/component-upgrade.sh to pass _require_repo_script (:336) even though it only execs deploy.sh upgrade (:344-346). A missing/non-exec/symlinked component-upgrade.sh would fail an operator-only upgrade, but the error is captured into the error result file (:383) and is fail-closed. `[python/arclink_operator_upgrade_host_runner.py:335-336,344-346]`
- **[INFO]** _pin_upgrade_log_requires_deploy parses the trailing N ARCLINK_COMPONENT_UPGRADE_STATUS markers from the just-written log (:254); component-upgrade.sh can emit multiple markers per item (:614-668), so statuses[-N:] could mis-attribute markers across items. All ambiguous cases (fewer than N markers, any non-allowlisted, any changed/pushed) fail SAFE to running deploy.sh upgrade (:255-258), so the worst case is an unnecessary deploy, never a skipped-but-needed deploy. `[python/arclink_operator_upgrade_host_runner.py:236-259; bin/component-upgrade.sh:614-668]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** The merged input contract presents the request schema as strict/closed except for the listed fields and raw-command rejection.  
  → correction: Extra request keys other than args/cmd/command are accepted if the required validated fields pass; they do not reach subprocess argv and only selected upstream keys are forwarded. `[/root/arclink/python/arclink_operator_upgrade_host_runner.py:279]`
- **[LOW]** The record says component-upgrade.sh can emit more than one ARCLINK_COMPONENT_UPGRADE_STATUS marker per item, creating a last-N marker misattribution edge.  
  → correction: For runner-invoked successful pin items, component-upgrade.sh emits one terminal marker: noop, pushed, or changed. A failed item returns before deploy parsing. `[/root/arclink/python/arclink_operator_upgrade_host_runner.py:276; /root/arclink/bin/component-upgrade.sh:611; /root/arclink/bin/component-upgrade.sh:637; /root/arclink/bin/component-upgrade.sh:664; /root/arclink/bin/component-upgrade.sh:668]`
- **[LOW]** The code-path trace says configured _repo_dir/_priv_dir/_queue_root env paths must be absolute.  
  → correction: The returned paths are absolute; the configured env strings themselves are not required to be absolute. _priv_dir additionally requires the resolved path name to be arclink-priv. `[/root/arclink/python/arclink_operator_upgrade_host_runner.py:69; /root/arclink/python/arclink_operator_upgrade_host_runner.py:80; /root/arclink/python/arclink_operator_upgrade_host_runner.py:88]`


---

# P7 — Host-runner execution: canonical upgrade


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 4 refinement(s) and 9 independent code re-confirmations.


## PIECE
**P7 — Host-runner execution: canonical upgrade.** File: `python/arclink_operator_upgrade_host_runner.py`. The host-side systemd-oneshot/timer drain (`bin/arclink-operator-upgrade-host-runner.sh:7` execs the module) that reads typed JSON requests the Docker broker (`arclink_operator_upgrade_broker.py`, P6) wrote into private state, and runs the canonical host upgrade flow (`deploy.sh upgrade` and/or `bin/component-upgrade.sh <comp> apply <flag> <target> --skip-upgrade` + conditional deploy). Entry: `main` → `process_once` → `_process_request_file` → `_run_request`.

## AGREED INPUT CONTRACT (re-confirmed in code)
Request = JSON object from `<queue_root>/pending/*.json` (read `:371`). Validated in `_validate_request` (`:279-330`):
- **Hard reject** any of `args`/`cmd`/`command` → "does not accept raw commands" (`:280-281`). No raw-command channel.
- `schema_version`: `int(request_body.get("schema_version") or 0) != 1` rejects (`:282-283`; constant `HOST_RUNNER_SCHEMA_VERSION=1` `:23`).
- `request_id`: single-line, non-blank, ≤96 (`:284`), MUST fullmatch `REQUEST_ID_RE=^[a-z0-9][a-z0-9_.-]{7,80}$` (`:25`, `:285`). Re-validated independently in `_process_request_file:374-376` before `_run_request`.
- `operation`: single-line ≤64 (`:287`), MUST be `run_operator_upgrade`|`run_pin_upgrade` (`:288`).
- `repo_dir`/`priv_dir` (optional): if present, `Path(...).resolve(strict=False)` MUST equal host-derived values (`:292`,`:294`).
- `log_path`: required single-line ≤4096, passed to `_require_child_path` rooted at `priv_dir/state/operator-actions`, `mkdir_parent=True` (`:296-302`).
- `timeout_seconds`: `_operator_timeout` `int(str(...).strip())`; on `TypeError/ValueError`→`7200`; clamp `max(30,min(21600,v))` (`:160-165`).
- `container_priv_dir` (optional): single-line ≤4096 only (`:308-310`) — NOT path-validated here.
- `upstream` (optional dict): only the six `UPSTREAM_ENV_KEYS` (`:35-42`) extracted, each single-line ≤4096, blanks dropped (`:313-320`).
- `install_items` (REQUIRED iff `run_pin_upgrade`): non-empty list (`:323`), each a dict (`:326-327`), each pre-validated by `_validated_pin_upgrade` BEFORE any command runs (`:328`). Item: `component` ≤96 matching `SAFE_COMPONENT_RE=^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$` (`:24`) AND in `ALLOWED_PIN_COMPONENTS={hermes-agent,qmd,nextcloud,postgres,redis,nvm,node}` (`:26`, check `:264`); `kind` ≤64 mapping through `PIN_UPGRADE_FLAGS` (`:266-270`); `target` ≤240 non-blank (`:267`).
- Request file MUST be regular non-symlink (`:368-370`) and parse to a dict (`:372-373`).

## AGREED OUTPUT CONTRACT (re-confirmed)
1. Log opened mode `"w"` (truncate) at validated `log_path` (`:341`), fixed banner written (`:342`). Each command echoes `$ <shlex-quoted argv>` (`:213`), child stdout+stderr streamed live (`stdout=handle, stderr=STDOUT` `:222-223`), then `[exit N]` (`:231`) or `command timed out after Ns` (`:228`).
2. `_run_request` returns `int` returncode (precedence below).
3. `_process_request_file`: success → `{"ok":True,"request_id":str,"returncode":int,"completed_at":int}` (`:382`); ANY exception (`except BaseException` `:383`) → `{"ok":False,"request_id":str,"error":str(exc),"error_class":cls,"completed_at":int}` (`:384-390`). **Non-zero child returncode is NOT an error** — reported `ok:True` with that code.
4. Result atomically written to `<queue_root>/results/<request_id>.json` via `_atomic_write_json` (`:391`; tmp `.{name}.{pid}.tmp`+`os.replace`, `sort_keys`, trailing `\n`, `:153-157`).
5. Processed request moved to `<queue_root>/processed/<name>` via `os.replace`; on `OSError` unlinked (`:392-396`).
6. `process_once` and `main` always return `0` (`:414`,`:423`) — process exit does NOT reflect per-request returncodes.

## TOUCH POINTS (re-confirmed)
- **ENV READ for path derivation (host process env, NOT forwarded):** `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR` (`:69`; else `Path(__file__).resolve().parents[1]` `:73`; must be absolute `:74`); `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR` (`:80`; else `repo/arclink-priv`; must be absolute AND `.name=="arclink-priv"` `:82`); `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` (`:88`; else `priv/state/operator-upgrade-host-runner`; must be absolute `:90`).
- **ENV forwarded to children** (`_operator_env` `:168-202`): `BASE_CHILD_ENV_KEYS`=HOME,PATH,LANG,LC_ALL,LC_CTYPE,TZ,TERM,SSL_CERT_FILE,REQUESTS_CA_BUNDLE (copied if set, `:170-173`); `OPTIONAL_CHILD_ENV_KEYS`=ARCLINK_DOCKER_BINARY,_IMAGE,_NETWORK,_UID,_GID,_SOCKET_GID,ARCLINK_STATE_ROOT_BASE,RUNTIME_DIR (copied if set, `:191-194`). Child env is a FRESH dict — parent env NOT inherited (`env={}` `:169`).
- **ENV written unconditionally** (`:176-189`): ARCLINK_DOCKER_MODE=1, ARCLINK_CONTAINER_RUNTIME=docker, ARCLINK_COMPONENT_UPGRADE_MODE=docker, ARCLINK_REPO_DIR, ARCLINK_PRIV_DIR, ARCLINK_PRIV_CONFIG_DIR=`<priv>/config`, ARCLINK_DOCKER_HOST_REPO_DIR, ARCLINK_DOCKER_HOST_PRIV_DIR, ARCLINK_DOCKER_CONTAINER_PRIV_DIR=`<request.container_priv_dir or priv>`, STATE_DIR=`<priv>/state`, ARCLINK_CONFIG_FILE=`<priv>/config/docker.env`. Defaults: HOME→`/root` (`:174`), PATH→`os.defpath` (`:175`), RUNTIME_DIR→`/opt/arclink/runtime` (`:195`).
- **FILES read:** pending `<queue_root>/pending/*.json` (`:412`); pin log re-read (`:250`). **FILES written:** result JSON (`:391`), processed move (`:394`), operator log (`:341`), lock `<queue_root>/runner.lock` (`:404`,`:407`); dirs pending/results (`:405-406`), processed (`:392`), log parent (`:119`).
- **SUBPROCESS** (`_run_logged_command`→`subprocess.run` `:216-226`): cwd=`repo_dir`, env=constructed dict, `stdin=DEVNULL`, `stdout=handle`, `stderr=STDOUT`, `check=False`, `timeout=timeout_seconds`. No `shell` (→False). Only two argv shapes (TRACE).
- **SCRIPT ALLOWLIST** (`_require_repo_script` `:123-150`): only `deploy.sh` and `bin/component-upgrade.sh` ever resolved (`:335-336`); relative path hard-coded, no request-supplied script.
- **LOCK:** `fcntl.flock(LOCK_EX|LOCK_NB)` on `runner.lock` (`:409`); `BlockingIOError`→return 0 without draining (`:410-411`).
- `os.umask(0o077)` in `main` (`:422`). **NETWORK:** none in this module.

## CODE-PATH TRACE (agreed, re-confirmed)
`main(:417)`→parse `--once` (ignored, `del args` `:421`)→`os.umask(0o077)` (`:422`)→`process_once` (`:423`).
`process_once(:399-414)`: derive repo/priv/queue (`:400-402`); mkdir pending+results (`:405-406`); open `runner.lock`, non-blocking `LOCK_EX`, bail 0 if contended (`:407-411`); for each `pending/*.json` sorted by `(stat().st_mtime, name)` (`:412`) call `_process_request_file` (`:413`); return 0.
`_process_request_file(:367-396)`: lstat, reject symlink/non-regular (`:368-370`); read+parse JSON, require dict (`:371-373`); re-extract+regex `request_id` (`:374-376`); compute result_path/processed (`:377-378`); try `_run_request` → `ok:True` result (`:381-382`); except BaseException → `ok:False` (`:383-390`); atomic-write result (`:391`); move to processed else unlink (`:392-396`).
`_run_request(:333-364)`: `_validate_request` (`:334`); `_require_repo_script(repo,"deploy.sh")` (`:335`) + `(repo,"bin/component-upgrade.sh")` (`:336`); `_operator_env` (`:337`); `timeout=int(request["timeout_seconds"])` (`:338`); open log `"w"`+banner (`:341-342`).
- **run_operator_upgrade** (`:344-346`): `_run_logged_command(handle,[str(deploy),"upgrade"],...)`; return `int(result.returncode)`. ARGV = `["<repo>/deploy.sh","upgrade"]`. (deploy.sh execs `bin/deploy.sh "$@"` — `deploy.sh:5`.)
- **run_pin_upgrade** (`:347-364`): require list (`:348-350`); per item (re-check dict `:352-353`) build via `_pin_upgrade_command` (`:354`) → `[str(component_upgrade),component,"apply",flag,target,"--skip-upgrade"]` (`:276`); run (`:355`); if `returncode!=0` return immediately (`:356-357`) — first failing pin short-circuits, no deploy. After all items flush (`:358`); decision `_pin_upgrade_log_requires_deploy(log_path,expected_statuses=len(install_items))` (`:359`). If NOT requires deploy: write skip line, return last pin returncode or 0 (`:360-362`). Else run `[str(deploy),"upgrade"]` (`:363`); return deploy returncode or 0 (`:364`) — **deploy code wins**.
`_pin_upgrade_log_requires_deploy(:248-259)`: read log (OSError→return True `:251-252`); `statuses=_component_upgrade_statuses_from_text` (`:253`); `recent=statuses[-expected:]` (`:254`); fewer than expected→True (`:255-256`); any not in `{noop,changed,pushed}`→True (`:257-258`); else deploy iff any in `{changed,pushed}` (`:259`). **Deploy SKIPPED only when every one of the last len(install_items) markers is exactly `noop`.**
`_component_upgrade_statuses_from_text(:236-245)`: collects lines whose stripped form starts with `ARCLINK_COMPONENT_UPGRADE_STATUS=`, value stripped+lowercased, non-empty. Emitter: `bin/component-upgrade.sh:46` `status_marker(){ printf 'ARCLINK_COMPONENT_UPGRADE_STATUS=%s\n' "$1"; }`.
**Timeout edge** (`:227-230`): `subprocess.TimeoutExpired`→write timeout line→synthetic `CompletedProcess(returncode=124)`. 124 propagates as any returncode: operator-upgrade returns it (`:346`); per-item 124 short-circuits (`:356-357`); deploy 124 returned (`:364`).

## CROSS-PIECE CONTRACTS (both ends verified)
- **Producer = broker P6** (`arclink_operator_upgrade_broker.py`). Envelope written at `broker:316-339`: `schema_version=1` (`broker:93,317`=runner `:23`) ✓; `request_id=f"op-{int(time.time())}-{uuid4().hex}"` (`broker:292`) — **empirically confirmed** matches `REQUEST_ID_RE` (len 46, lowercase) ✓; `operation,repo_dir,priv_dir,container_priv_dir,log_path,timeout_seconds,upstream,install_items` ✓ (`created_at` is written by broker but ignored by runner — harmless extra key).
- **Path identity:** broker queue root `<host_priv>/state/operator-upgrade-host-runner` (`broker:288`) == runner default (`runner:89`). Broker writes `pending/<id>.json` (`broker:338-339`), polls `results/<id>.json` (`broker:315,345`); runner reads `pending/*.json` (`:412`), writes `results/<id>.json` (`:377,391`). ✓
- **log_path:** broker validates+maps under operator-actions then writes absolute host path (`broker:307,324`); runner re-validates under `priv/state/operator-actions` (`:296-302`). Same root ✓.
- **Constants drift:** `ALLOWED_PIN_COMPONENTS`, `SAFE_COMPONENT_RE`, `PIN_UPGRADE_FLAGS` byte-identical broker (`:47-56`) vs runner (`:24-34`). Both build identical pin argv (`broker:_normalized_pin_upgrade_item` vs runner `:276`). ✓
- **Result contract:** broker requires `result["ok"] is True` else raises `error` (`broker:352-355`), reads `int(result["returncode"])` (`broker:357`), returns `{"returncode","host_runner":True,"request_id"}` (`broker:360`). Runner emits exactly that ok-shape (`:382`) / failure-shape (`:384-390`). ✓
- **Child scripts:** `deploy.sh` execs `bin/deploy.sh "$@"` (`deploy.sh:4-5`); `bin/component-upgrade.sh` parses `--ref/--tag/--version/--skip-upgrade` (`:681-687`), `apply` dispatch (`:703`), emits markers (`:46`). With `--skip-upgrade=1` every `reexec_upgrade` is suppressed (guarded by `skip_upgrade!=1` at `:624,632,664`) and **exactly one** status marker emitted per apply (`:614` noop, `:637` noop/pushed, `:668` changed) — so the runner's tail-N decision sees one marker per item. ✓
- **Systemd install:** `bin/deploy.sh:8395-8397` sets the three host-runner env vars; `:8399` ExecStart=`bin/arclink-operator-upgrade-host-runner.sh --once`; wrapper execs `python3 .../arclink_operator_upgrade_host_runner.py "$@"` (`:7`). ✓
- **Executable proof:** `tests/test_arclink_docker.py:2773-2845` — **I ran it; it PASSES.** Proves: operator-upgrade runs `deploy upgrade` with `ARCLINK_CONFIG_FILE=<priv>/config/docker.env` (`:2838`); single `noop` pin → deploy skipped, "skipping deploy upgrade" logged, no second deploy marker line (`:2838,2844`); both results `ok:True returncode:0`.

## DISAGREEMENTS & ADJUDICATION
1. **Pre-execution abort writes no result and stalls the drain (codex Medium vs Claude omission).** Codex: malformed JSON / non-object / invalid request_id / symlink / non-regular request file occur BEFORE the try block (`:367-376`), so no result JSON is written, the pending file is not moved, and `process_once` does not catch it (`:412-413`). **VERIFIED CORRECT** — those checks are at `:368-376`, all outside the try at `:380`; the `process_once` loop has no try/except, so the exception propagates to `main`/`SystemExit`. Claude omitted this. **I found it is broader than codex stated:** the abort can occur even earlier — at the glob sort `item.stat().st_mtime` (`:412`) — for a *dangling symlink* in `pending/`, before `_process_request_file` runs at all. Empirically reproduced: `OSError [Errno 2]` during the sort-key lambda aborts the entire drain, so ONE poisoned pending entry blocks ALL queued requests, not just itself. **Winner: codex** (Claude missed it); I extend the finding.
2. **log_path symlink-escape "not caught" (Claude INFO — INCORRECT).** Claude asserted `_require_child_path` (`:108-117`) does not catch a pre-existing symlink inside operator-actions pointing outside, calling the log guard "strictly weaker than the script guard." **ADJUDICATED FALSE by direct test:** `Path(value).resolve(strict=False)` (`:110`) follows the final-component symlink to its real target, then `relative_to(root)` (`:115`) raises `ValueError` → "must stay under" rejection (`:116-117`). I reproduced: a symlink `operator-actions/evil.log → /etc/passwd` resolves to `/etc/passwd` and is **REJECTED**. The escape IS caught. The genuine (and lesser) residual: `_require_child_path` permits a symlink whose target stays *under* root, and the open at `:341` follows it — but that cannot escape the operator-controlled priv tree. **Winner: codex (by not making the wrong claim).** Claude's specific INFO claim is corrected to false; the weaker-guard framing is downgraded to "does not lstat-reject in-tree symlinks" only.
3. **container_priv_dir / ARCLINK_DOCKER_BINARY / queue-dir validation asymmetry (codex Low, Claude omission).** Codex flagged three broker-vs-runner asymmetries. **All VERIFIED:** (a) broker `_container_priv_dir` requires absolute + `arclink-priv` in parts (`broker:134`); runner only single-lines it (`:308-310`) and uses `request.container_priv_dir or priv` for the env (`:186`) — but the value comes from the broker-written request, already broker-validated. (b) broker re-validates `ARCLINK_DOCKER_BINARY` via `_docker_binary()` (`broker:233`); runner copies it raw from host env (`:191-194`) — but it is host-systemd-controlled, not attacker-controlled. (c) broker confines `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` under host state (`broker:284`); runner only checks `is_absolute` (`:90`) — but the env is host-operator-controlled. All three are real but source from trusted host env or already-validated request fields. **Winner: codex** (correct, low/within-trust-boundary). Claude omitted them.
4. **Deploy-after-pin treats `pushed`==`changed` (Claude INFO, codex equivalent).** Both correctly state deploy runs unless every recent marker is `noop`. Claude added the non-obvious nuance that an at-target pin can still emit `pushed` (`bin/component-upgrade.sh:623,631,637`) when pins.json has an uncommitted diff or HEAD isn't on upstream, triggering deploy. **VERIFIED** (`:618-637`). **Winner: both** — no conflict, Claude's nuance is a correct enrichment.

## GAPS BOTH MISSED
- **`schema_version` accepts non-int JSON via `int(x or 0)` (`:282`).** Tested: JSON `true`→`int(True)`=1→**accepted**; JSON `1.9`→`int(1.9)`=1→**accepted**; `[1]`/`{}` → `TypeError` (uncaught here, caught by `except BaseException` at `:383`→`ok:False`). Not exploitable (broker always sends int `1`; downstream validation is strict regardless), but the coercion is looser than an `== 1` int check. INFO.
- **Dangling symlink in `pending/` aborts the whole drain at `:412`** (see Disagreement #1 extension) — neither audit cited line 412 as the abort site for a stat-failing symlink.
- **`created_at` (broker `:319`) is an unmodeled extra key** the runner silently ignores — no schema-extra-key rejection. Benign (the only hard-rejected extras are args/cmd/command at `:280`), worth noting the runner is not a strict-schema validator.

## RISKS
- **[medium]** A single un-stattable/dangling symlink, malformed-JSON, non-object, or invalid-`request_id` pending entry aborts `process_once` before/without writing a result, leaving the bad file in place and **blocking every other queued request** — the failure is uncaught at `:412-413` and at the pre-try checks `:367-376`. Plantable only by something with write access to the host priv tree (GAP-019 trusted-host, Docker-mode), so not externally exploitable, but it is a real availability/robustness gap and a poison-pill that stalls the drain.
- **[low]** Deploy-after-pin parses `ARCLINK_COMPONENT_UPGRADE_STATUS` markers from the per-request log opened `"w"` (`:341`); the `statuses[-expected_statuses:]` slice (`:254`) is sound ONLY because `component-upgrade.sh` emits exactly one marker per apply under `--skip-upgrade` (`bin/component-upgrade.sh:614,637,668`, re-exec suppressed at `:624,632,664`). Fragile cross-language coupling — not a present defect.
- **[low]** Broker-vs-runner validation asymmetry: `container_priv_dir` (runner single-line only `:308-310` vs broker absolute+`arclink-priv` `broker:134`), `ARCLINK_DOCKER_BINARY` (runner raw `:191-194` vs broker `_docker_binary()` `broker:233`), queue dir (runner `is_absolute` only `:90` vs broker confined under state `broker:284`). All source from trusted host env or already-broker-validated request fields → within the accepted boundary.
- **[info]** `_require_child_path` (`:108-120`) does fully prevent escapes (resolve+relative_to, proven), but it does NOT lstat-reject in-tree symlinks, so the log open at `:341` will follow a pre-planted in-tree symlink and truncate its in-tree target. Strictly weaker than the lstat-walking `_require_repo_script`, but cannot leave the priv tree.
- **[info]** `schema_version` accepts JSON `true`/floats via `int(x or 0)` (`:282`); `_operator_timeout` defaults `7200` and clamps `[30,21600]` on malformed input (`:160-165`). Reachable only via hand-crafted pending files (broker always sends int `1`/int timeout). No injection (no raw-command channel `:280-281`).
- **[info]** Per-request child returncode (incl. non-zero / `124` timeout) is reported with `ok:True` in `results/<id>.json` (`:382`); `process_once`/`main` always return 0 (`:414,423`). A failed upgrade does not fail the host-runner process — by design; the broker surfaces the code (`broker:357-360`).
- **[info]** `run_operator_upgrade` is blocked if `bin/component-upgrade.sh` fails preflight (`:336`) even though that branch only runs `deploy.sh` — both scripts are preflighted unconditionally. Conservative, harmless on a healthy repo.
- **[info]** Script read/exec checks are by mode bits (`:142-145`), not an actual open/exec; ACLs/noexec/TOCTOU could still fail later at `subprocess.run` (`:216`). `check=False` means such a failure surfaces as the child's own nonzero exit, reported normally.

## AGREED VERDICT
**P7 provably does its job.** It is an allowlist-only executor: it accepts only the validated broker envelope (no raw-command channel `:280-281`), resolves only the two hard-coded repo scripts through a strict symlink/regular/read/exec/escape guard (`:123-150`), builds exactly two deterministic argv shapes — `["<repo>/deploy.sh","upgrade"]` (`:345`) and `["<repo>/bin/component-upgrade.sh",<comp>,"apply",<flag>,<target>,"--skip-upgrade"]` (`:276`) — runs them in a fresh, explicitly-constructed child env with the ARCLINK_DOCKER_* overrides and HOME/PATH/RUNTIME_DIR defaults (`:168-202`), streams output to a path-confined operator log, and makes the deploy-after-pin decision purely from the last `len(install_items)` `ARCLINK_COMPONENT_UPGRADE_STATUS` markers, skipping deploy iff all are `noop` (`:248-259`). Return-code precedence is correct and conservative (first pin failure short-circuits `:356-357`; otherwise deploy code wins `:364`; timeout→124 `:230`). The broker↔runner contract — schema version, request_id regex, queue/result/log paths, pin constants, and result shape — agrees at both ends, corroborated by a passing exec test (`tests/test_arclink_docker.py:2773-2845`, run green). The one substantive robustness gap is the uncaught pre-execution / glob-sort abort (medium) that can stall the drain on a poison-pill pending entry; the remaining items are accepted-trust-boundary asymmetries and one corrected false claim (the log-path guard DOES catch symlink escapes). The piece is correct for broker-produced input and the abort gap is contained within the GAP-019 trusted-host boundary.


### Adjudicated cross-model disagreements


- **Pre-execution / glob-sort abort writes no result and stalls the entire drain** — winner: **CODEX**  
  Claude: Omitted the abort consequence; noted line 412 follows symlinks but concluded 'no traversal' and that a symlinked pending entry is rejected by _process_request_file with an ok:False result.  
  GPT-5.5: Medium: malformed JSON, non-object, invalid/missing request_id, symlink or non-regular request file occur before the result-writing try block (:367-380), so no result JSON is written, the pending file is not moved, and process_once does not catch the per-file exception (:412-413).  
  Adjudication: Codex is correct: the checks at :368-376 are outside the try at :380, and the process_once loop has no try/except, so the exception propagates to main/SystemExit. I extend it: the abort can occur even earlier, at the glob sort `item.stat().st_mtime` (:412), for a dangling symlink in pending/ (empirically reproduced OSError), before _process_request_file runs — so ONE poison-pill entry blocks ALL queued requests, not just itself. Claude's 'ok:False result still written' is wrong for the pre-request_id/symlink cases. `[python/arclink_operator_upgrade_host_runner.py:367-376,380,412-413]`

- **log_path symlink-escape allegedly not caught by _require_child_path** — winner: **CODEX**  
  Claude: INFO: a symlink already present inside operator-actions pointing outside is NOT caught here (unlike _require_repo_script); the log_path guard is strictly weaker than the script guard.  
  GPT-5.5: Did not make this claim (no equivalent assertion).  
  Adjudication: Claude's specific claim is FALSE. Empirically verified: Path(value).resolve(strict=False) (:110) follows the final-component symlink to its real target, then relative_to(root) (:115) raises ValueError -> rejection (:116-117). A symlink operator-actions/evil.log -> /etc/passwd resolves to /etc/passwd and is REJECTED. The escape IS caught. The only genuine residual is that an in-tree symlink (target still under root) is followed by the open at :341 — which cannot leave the priv tree. `[python/arclink_operator_upgrade_host_runner.py:108-120,341]`

- **Broker-vs-runner validation asymmetries (container_priv_dir, ARCLINK_DOCKER_BINARY, queue dir)** — winner: **CODEX**  
  Claude: Omitted these three asymmetries.  
  GPT-5.5: Low: runner only single-lines container_priv_dir vs broker absolute+arclink-priv; runner copies ARCLINK_DOCKER_BINARY raw vs broker _docker_binary(); runner only checks queue dir is absolute vs broker confines under state.  
  Adjudication: All three verified real: broker:134 (container_priv_dir absolute+arclink-priv), broker:233 (_docker_binary), broker:284 (queue relative_to host_state_root) vs runner :308-310, :191-194, :90. But each sources from trusted host systemd env or an already-broker-validated request field, so none is attacker-reachable. Codex correct; severity low/within-trust-boundary is right. `[python/arclink_operator_upgrade_broker.py:134,233,284; python/arclink_operator_upgrade_host_runner.py:90,191-194,308-310]`

- **Deploy-after-pin treats pushed and changed identically; at-target pin can emit pushed** — winner: **BOTH**  
  Claude: INFO: deploy runs unless every recent marker is exactly noop; an at-target ('noop') pin can still emit a 'pushed' marker when pins.json has an uncommitted diff or HEAD isn't on upstream, which triggers deploy.  
  GPT-5.5: Skips deploy only when last len(install_items) statuses are present, all in {noop,changed,pushed}, and none are changed/pushed (i.e. all noop). Did not add the at-target-emits-pushed nuance.  
  Adjudication: Both correct on the rule (:248-259). Claude's nuance is verified against bin/component-upgrade.sh:618-637 (upgrade_status flips to 'pushed' on uncommitted diff or HEAD-not-on-upstream) and is a correct enrichment, not a conflict. `[python/arclink_operator_upgrade_host_runner.py:248-259; bin/component-upgrade.sh:618-637]`


### Risks (converged, severity-ranked)

- **[MEDIUM]** A single un-stattable/dangling symlink, malformed-JSON, non-object, or invalid-request_id pending entry aborts process_once before/without writing a result and leaves the bad file in place, BLOCKING every other queued request. The failure is uncaught at the glob sort (:412) and at the pre-try validation (:367-376); the loop has no try/except so it propagates to main/SystemExit. Empirically reproduced for a dangling symlink (OSError during the sort-key lambda). Plantable only with write access to the host priv tree (GAP-019 trusted-host, Docker-mode), so not externally exploitable, but a real poison-pill availability gap. `[python/arclink_operator_upgrade_host_runner.py:412,367-376,380]`
- **[LOW]** Deploy-after-pin parses ARCLINK_COMPONENT_UPGRADE_STATUS markers from the per-request log opened in 'w' mode (:341); the tail-N slice statuses[-expected_statuses:] (:254) is sound ONLY because component-upgrade.sh emits exactly one marker per apply under --skip-upgrade (bin/component-upgrade.sh:614,637,668 with reexec suppressed at :624,632,664). Fragile cross-language coupling; not a present defect. `[python/arclink_operator_upgrade_host_runner.py:254,341; bin/component-upgrade.sh:614,637,668]`
- **[LOW]** Broker-vs-runner validation asymmetry: container_priv_dir is only single-lined in the runner (:308-310) vs broker absolute+arclink-priv (broker:134); ARCLINK_DOCKER_BINARY is copied raw (:191-194) vs broker _docker_binary() (broker:233); queue dir is only checked is_absolute (:90) vs broker confined under host state (broker:284). All source from trusted host systemd env or already-broker-validated request fields, so within the accepted boundary. `[python/arclink_operator_upgrade_host_runner.py:90,191-194,308-310]`
- **[INFO]** _require_child_path (:108-120) DOES prevent log_path escapes (resolve(strict=False)+relative_to, empirically proven to reject a symlink to /etc/passwd), but it does not lstat-reject an in-tree symlink, so the log open at :341 follows a pre-planted in-tree symlink and truncates its in-tree target. Cannot leave the priv tree. Corrects Claude's claim that outside-pointing symlinks are not caught. `[python/arclink_operator_upgrade_host_runner.py:108-120,341]`
- **[INFO]** schema_version is accepted via int(x or 0) (:282), so JSON true and floats (e.g. 1.9) coerce to 1 and pass; lists/dicts raise TypeError caught by except BaseException (:383) -> ok:False. _operator_timeout defaults 7200 and clamps [30,21600] on malformed input (:160-165). Reachable only via hand-crafted pending files; broker always sends int 1 and an int timeout. No injection (no raw-command channel :280-281). `[python/arclink_operator_upgrade_host_runner.py:282,160-165]`
- **[INFO]** Per-request child returncode (including non-zero and 124 timeout) is reported with ok:True in results/<id>.json (:382); process_once and main always return 0 (:414,:423). A failed upgrade does not fail the host-runner process; the returncode is surfaced only via the result JSON, which the broker consumes (broker:357-360). By design. `[python/arclink_operator_upgrade_host_runner.py:382,414,423]`
- **[INFO]** run_operator_upgrade is blocked if bin/component-upgrade.sh fails the script preflight (:336) even though that branch only runs deploy.sh upgrade; both scripts are preflighted unconditionally. Conservative, harmless on a healthy repo. Also: script read/exec checks are by mode bits (:142-145), not an actual open/exec, so ACLs/noexec/TOCTOU can still fail later at subprocess.run (:216) and surface as the child's nonzero exit. `[python/arclink_operator_upgrade_host_runner.py:336,142-145,216]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** The record's output contract says `_process_request_file` turns ANY exception into an `ok:false` result, and that `process_once`/`main` always return 0.  
  → correction: Only exceptions raised inside `_run_request` at line 381 are converted into an `ok:false` result. Pre-try request-file failures, and `item.stat()` failures during pending-file sorting, escape the drain. `process_once` returns 0 only on normal completion or lock contention. `[python/arclink_operator_upgrade_host_runner.py:367, python/arclink_operator_upgrade_host_runner.py:380, python/arclink_operator_upgrade_host_runner.py:391, python/arclink_operator_upgrade_host_runner.py:412, python/arclink_operator_upgrade_host_runner.py:423]`
- **[LOW]** The record says ACL/noexec/TOCTOU failures after script mode-bit preflight would surface as the child's own nonzero exit because `check=False`.  
  → correction: A child returncode is propagated only when `subprocess.run` returns a `CompletedProcess`, or when timeout handling synthesizes returncode 124. Exec launch errors propagate out of `_run_logged_command` and become `ok:false` if they occur inside `_run_request`. `[python/arclink_operator_upgrade_host_runner.py:216, python/arclink_operator_upgrade_host_runner.py:227, python/arclink_operator_upgrade_host_runner.py:230, python/arclink_operator_upgrade_host_runner.py:383]`
- **[LOW]** The broker-vs-runner validation-asymmetry discussion is complete with `container_priv_dir`, `ARCLINK_DOCKER_BINARY`, and queue dir.  
  → correction: For broker-produced requests this is safe because the broker normalizes upstream private paths first. For hand-crafted pending files, the runner will pass arbitrary single-line upstream deploy-key/known-hosts paths to `deploy.sh`/`component-upgrade.sh`. `[python/arclink_operator_upgrade_broker.py:65, python/arclink_operator_upgrade_broker.py:195, python/arclink_operator_upgrade_broker.py:254, python/arclink_operator_upgrade_host_runner.py:196, python/arclink_operator_upgrade_host_runner.py:313]`
- **[LOW]** The log-path symlink assessment is complete when it says the guard catches symlink escapes and in-tree symlinks cannot leave the priv tree.  
  → correction: Pre-existing outside-pointing log symlinks are rejected, but there is no atomic no-follow open. This is within the trusted host/private-state write boundary, but it is still an unreported edge in the record's log-path claim. `[python/arclink_operator_upgrade_host_runner.py:108, python/arclink_operator_upgrade_host_runner.py:119, python/arclink_operator_upgrade_host_runner.py:341]`


---

# P8 — Infra/config wiring (the integration seam)


**Both-model sign-off:** convergence `both_models_agree=False`; GPT-5.5 ratification `OBJECT` with 4 refinement(s) and 11 independent code re-confirmations.


## PIECE
**P8 — Infra/config wiring (the integration seam).** Scope: `compose.yaml` operator-upgrade-broker service, `bin/deploy.sh` host-runner systemd-timer installer + docker.env writers, `bin/arclink-operator-upgrade-host-runner.sh` shim, `config/docker-authority-inventory.json` operator-upgrade-broker entry. Adjacent Python ends in reach and verified: `python/arclink_operator_upgrade_broker.py`, `python/arclink_operator_upgrade_host_runner.py`, `python/arclink_enrollment_provisioner.py` (producer), `python/arclink_boundary.py` (trusted-host gate). The seam's job: the container broker and the host systemd runner must resolve to the SAME host queue dir, the timer must drive the shim/runner, and the broker must hold NO docker-socket authority.

## AGREED INPUT CONTRACT (both models, re-verified)
- `BOOTSTRAP_DIR` = `$ARCLINK_DEPLOY_BOOTSTRAP_DIR` (canonicalized) else `dirname "$0"/..` canonicalized — `bin/deploy.sh:4-8`.
- docker.env path = `$BOOTSTRAP_DIR/arclink-priv/config/docker.env` — `bin/deploy.sh:8420-8422`; written mode 600 — `:8496`.
- `write_docker_runtime_config` writes `ARCLINK_DOCKER_HOST_REPO_DIR=$BOOTSTRAP_DIR` (`bin/deploy.sh:8493`) and `ARCLINK_DOCKER_HOST_PRIV_DIR=$BOOTSTRAP_DIR/arclink-priv` (`:8494`) via `write_kv` which emits `%s=%q` — `:1980-1984`.
- `bin/arclink-docker.sh` computes its own `REPO_DIR` (`:4-5`), defaults `DOCKER_ENV_FILE=$REPO_DIR/arclink-priv/config/docker.env` (`:7`), and feeds it to compose as `--env-file` only when the file exists — `:117-123`.
- Compose broker explicit env (`compose.yaml:852-865`): `ARCLINK_DOCKER_MODE=1`, `ARCLINK_CONTAINER_RUNTIME=docker`, `ARCLINK_COMPONENT_UPGRADE_MODE=docker`, `ARCLINK_REPO_DIR=/home/arclink/arclink`, `ARCLINK_DOCKER_HOST_REPO_DIR=${...:-}`, `ARCLINK_DOCKER_HOST_PRIV_DIR=${...:-}`, `ARCLINK_DOCKER_CONTAINER_PRIV_DIR=/home/arclink/arclink/arclink-priv`, `ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED=${...:-}`, `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED="1"`, `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR=${ARCLINK_DOCKER_HOST_PRIV_DIR:?...}/state/operator-upgrade-host-runner`, `ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN=${...:?...}`, `..._BROKER_HOST=0.0.0.0`, `..._BROKER_PORT=8917`. The `:?` guards on PRIV_DIR (`:862`) and TOKEN (`:863`) make compose REFUSE to start if unset — fail-closed.
- Systemd runner env (`bin/deploy.sh:8395-8398`): `ARCLINK_OPERATOR_UPGRADE_HOST_REPO_DIR=$BOOTSTRAP_DIR`, `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR=$BOOTSTRAP_DIR/arclink-priv`, `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR=$BOOTSTRAP_DIR/arclink-priv/state/operator-upgrade-host-runner`, `ARCLINK_CONFIG_FILE=$docker_env`.
- Timer cadence env: `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_INTERVAL_SECONDS` accepted only as positive integer, else `5s` — `bin/deploy.sh:8366-8373`.
- Broker HTTP input: `POST /v1/operator-upgrade`, `Content-Length` ∈ (0, 16384] (`arclink_operator_upgrade_broker.py:36,739-744`), HMAC headers (`:746`), JSON object body (`:750-756`). `operation` ∈ {`run_operator_upgrade`,`run_pin_upgrade`} (`:642,646`). Raw-command keys `args/cmd/command` rejected (`:139-141`). `timeout_seconds` clamped to `[30,21600]`, default 7200 (`:368-373`).
- Producer body: `json.dumps({**payload,"operation":op}, sort_keys=True).encode("utf-8")` — `arclink_enrollment_provisioner.py:310-312`.

## AGREED OUTPUT CONTRACT (both models, re-verified)
- docker.env file (mode 600) consumed by compose via `--env-file` — `bin/deploy.sh:8483-8496`, `bin/arclink-docker.sh:119-123`.
- Two systemd units `/etc/systemd/system/arclink-operator-upgrade-host-runner.{service,timer}` — `bin/deploy.sh:8383-8384`; service `Type=oneshot` (`:8393`), no `User=` → runs as root, `ExecStart=$BOOTSTRAP_DIR/bin/arclink-operator-upgrade-host-runner.sh --once` (`:8399`); timer `OnBootSec=20s`, `OnUnitActiveSec=$interval`(default `5s`), `AccuracySec=1s`, `Persistent=false` (`:8402-8414`); `daemon-reload`+`enable --now ...timer` (`:8416-8417`).
- Broker → queue file: atomic JSON to `<queue_root>/pending/<request_id>.json`, payload keys `schema_version:1, request_id, created_at, operation, repo_dir, priv_dir, container_priv_dir, log_path, timeout_seconds, upstream{}`, plus `install_items[]` for pin upgrades — `arclink_operator_upgrade_broker.py:316-339`. Then polls `<queue_root>/results/<request_id>.json` until deadline (`:343-361`).
- Runner → result file: atomic JSON `{ok, request_id, returncode, completed_at}` on success or `{ok:false, request_id, error, error_class, completed_at}` on failure inside try block — `arclink_operator_upgrade_host_runner.py:382-390`; request moved to `processed/` (`:392-396`); operator-action log written under `priv_dir/state/operator-actions/...` (`:296-302,341`).
- Broker HTTP: 200 `{ok:true, result:{...}}` / 400 `{ok:false, error}` / 401 / 404 / 413 / 503 — `arclink_operator_upgrade_broker.py:725-761`; success body `{returncode, host_runner:true, request_id}` (`:360`).

## TOUCH POINTS (re-verified)
- Env (compose broker): `compose.yaml:852-865`; this block sets its OWN `environment:` which overrides the `environment: &arclink-env` merged via `<<: *arclink-app` (`:13-18,843`) — so it does NOT inherit broad app env (YAML merge-key: a local mapping key wins over the merged one). It DOES inherit `image`/`restart`/`security_opt: no-new-privileges:true` from the anchor (`:14-17`).
- Env (systemd runner): `bin/deploy.sh:8395-8398`.
- File paths: docker.env `$BOOTSTRAP_DIR/arclink-priv/config/docker.env` (`bin/deploy.sh:8420`); unit files (`:8383-8384`); shared queue `$BOOTSTRAP_DIR/arclink-priv/state/operator-upgrade-host-runner/{pending,results,processed}` + `runner.lock` (`arclink_operator_upgrade_host_runner.py:403-406`); op-action logs `arclink-priv/state/operator-actions/` (`:296`).
- Volumes (compose broker): ONLY `${ARCLINK_DOCKER_HOST_REPO_DIR:-.}:${ARCLINK_DOCKER_HOST_REPO_DIR:-/home/arclink/arclink}` (host-path→host-path repo bind) — `compose.yaml:866-869`. NO `/var/run/docker.sock`.
- Networks: ONLY `operator-upgrade-broker-net` (`compose.yaml:872`), declared `internal: true` (`:1173`). No egress net; not on `default`. Test enforces exact membership — `tests/test_arclink_docker.py:883,888-889`.
- Caps/user: `user:"0:0"`, `cap_drop:[ALL]`, `cap_add:[DAC_OVERRIDE]` — `compose.yaml:847-851`. NO `group_add` (contrast socket brokers at `:658,827,1009`).
- Subprocess (runner): `[deploy.sh,"upgrade"]` (`arclink_operator_upgrade_host_runner.py:345`); `[bin/component-upgrade.sh, component,"apply",flag,target,"--skip-upgrade"]` (`:276,354`); both scripts re-derived via `_require_repo_script` which rejects symlinks/traversal and requires regular+readable+executable (`:123-150`).
- Subprocess (shim): `exec python3 "$REPO_DIR/python/arclink_operator_upgrade_host_runner.py" "$@"` — `bin/arclink-operator-upgrade-host-runner.sh:7` (bare host python3, no venv, no PYTHONPATH).
- Socket/port: `ThreadingHTTPServer((host,port))` (`arclink_operator_upgrade_broker.py:765`); `DEFAULT_HOST=127.0.0.1`,`DEFAULT_PORT=8917` (`:39-40`); compose forces `0.0.0.0:8917` (`:864-865`); health on `127.0.0.1:8917/health` (`:875`).
- Lock: `fcntl.flock(LOCK_EX|LOCK_NB)` on `runner.lock`; contention returns 0 without draining — `arclink_operator_upgrade_host_runner.py:407-411`.
- umask: `os.umask(0o077)` before drain — `:422`.
- Network call (producer): `urllib.request.urlopen(<broker_url>/v1/operator-upgrade, timeout=max(30,timeout_seconds))` — `arclink_enrollment_provisioner.py:321-334`.

## CODE-PATH TRACE (agreed)
1. `run_control_install_flow`: `write_docker_runtime_config "$docker_env"` (`bin/deploy.sh:11631`) → `run_arclink_docker up` (`:11637`) → `install_control_operator_upgrade_host_runner_timer` (`:11642`). Runtime-reset re-installs the timer (`:12751`).
2. `install_control_operator_upgrade_host_runner_timer` (`:8375`): no-op without systemd (`:8378-8380`); `interval=operator_upgrade_host_runner_interval` default `5s` (`:8382,8366-8373`); writes `.service` (`Type=oneshot`, repo/priv/queue env, `ExecStart=...shim --once`) (`:8386-8400`) and `.timer` (`OnBootSec=20s`, `OnUnitActiveSec=$interval`) (`:8402-8414`); `daemon-reload`+`enable --now` (`:8416-8417`).
3. Timer fires → `.service` → shim `exec python3 ...host_runner.py --once` (`bin/arclink-operator-upgrade-host-runner.sh:7`).
4. Broker POST: size guard (`broker.py:739-744`) → `_is_authorized` HMAC token+sig+nonce+ts (`:746,686-716`) → JSON parse (`:749-756`) → `run_operator_upgrade_request` (`:757`).
5. `run_operator_upgrade_request` (`:636`): trusted-host gate (`:638`); dispatch by `operation` (`:642,646`); `_host_runner_enabled()` default true (`:643,249-251`) → `_run_host_runner_request` (`:644,648`); all errors caught → `(False, str(exc))` (`:651-653`).
6. `_run_host_runner_request` (`:302`): reject raw cmds (`:303`); `_host_repo_dir`/`_host_priv_dir` (`:304-306`); `_require_operator_log_path` (`:307`); `_operator_timeout` clamp (`:308`); `queue_root=_host_runner_queue_root()` (`:312`); build payload `schema_version=1` (`:316-337`); atomic write `pending/<id>.json` (`:338-339`); poll `results/<id>.json` until `max(30,min(21630,timeout+30))` (`:340-361`); on ok return `{returncode, host_runner:true, request_id}` (`:360`); else RuntimeError timeout (`:362-365`).
7. Runner `main` (`:417`): parse `--once` then `del args` (`:419-421`); `os.umask(0o077)` (`:422`); `process_once()` (`:423`).
8. `process_once` (`:399`): `_repo_dir`(`:400`), `_priv_dir`(`:401`), `_queue_root`(`:402`); mkdir pending/results (`:405-406`); `flock` non-blocking, contention→0 (`:407-411`); glob `pending/*.json` sorted by `(mtime,name)` (`:412`); `_process_request_file` per file (`:413`).
9. `_process_request_file` (`:367`): `lstat`+symlink/non-regular reject (`:368-370`); `json.loads` (`:371`); request_id parse+regex (`:374-376`) — ALL BEFORE the `try:` at `:380`; inside try `_run_request` (`:381`) → write result (`:391`) → move to `processed/` (`:392-396`).
10. `_run_request` (`:333`): `_validate_request` (schema==1, id regex, op allowlist, repo/priv equality, log under `operator-actions`, pin items) (`:334,279-330`); `_require_repo_script(deploy.sh)` (`:335`); `_require_repo_script(bin/component-upgrade.sh)` (`:336`); `_operator_env` (`:337`); `run_operator_upgrade` → `[deploy,"upgrade"]` (`:345`); `run_pin_upgrade` → per-item `[component-upgrade.sh ... --skip-upgrade]` (`:351-357`), then `[deploy,"upgrade"]` unless every recent status is `noop`/clean (`:359-363`, `_pin_upgrade_log_requires_deploy:248-259`).

## CROSS-PIECE CONTRACTS (verified both ends)
1. **Shared queue host path — PROVEN byte-for-byte.** Broker `_host_runner_queue_root` reads `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR`, validates absolute + under `Path(ARCLINK_DOCKER_HOST_PRIV_DIR).resolve()/state`, returns it (`broker.py:276-288`). Compose sets it to `${ARCLINK_DOCKER_HOST_PRIV_DIR}/state/operator-upgrade-host-runner` (`compose.yaml:862`) where deploy writes `ARCLINK_DOCKER_HOST_PRIV_DIR=$BOOTSTRAP_DIR/arclink-priv` (`deploy.sh:8494`). Runner `_queue_root` reads the SAME var (`host_runner.py:88`), set by systemd to `$BOOTSTRAP_DIR/arclink-priv/state/operator-upgrade-host-runner` (`deploy.sh:8397`). Container path == host path because the bind maps host-path→host-path (`compose.yaml:869`), so `Path.resolve` yields identical strings. Both ends = `$BOOTSTRAP_DIR/arclink-priv/state/operator-upgrade-host-runner`.
2. **Request/result JSON schema — PROVEN both ends.** Broker writes `schema_version:1` (`broker.py:317`); runner asserts `==1` (`host_runner.py:282`). Result keys `ok/returncode/request_id` match broker reader (`broker.py:352-360`) ↔ runner writer (`host_runner.py:382`).
3. **Pin allowlists identical — PROVEN.** `ALLOWED_PIN_COMPONENTS` and `PIN_UPGRADE_FLAGS` byte-identical in broker (`:48-56`) and runner (`:26-34`).
4. **HMAC signature contract — PROVEN both ends.** Producer signs `hmac(token,"{ts}\n{nonce}\n{sha256(body)}",sha256)` over `json.dumps(...,sort_keys=True)` body (`arclink_enrollment_provisioner.py:312-320`); verifier recomputes identically over `raw_body` (`broker.py:707-713`). Nonce `secrets.token_urlsafe(18)` matches verifier regex `[A-Za-z0-9_.~+/=-]{16,160}` (`broker.py:703`). TTL 300s, replay-protected (`:701,705`).
5. **Inventory ↔ compose structured boundary — PROVEN + drift-tested.** `compose_boundary` block (`config/docker-authority-inventory.json:2228-2247`): `docker_socket:"none"`, `explicit_root:true`, `container_user:"root"`, `linux_capabilities:"drop_all_add_DAC_OVERRIDE"`, `compose_networks:["operator-upgrade-broker-net"]`, `default_network:false`, `egress_networks:[]`. Matches `compose.yaml:847-851,872`. Test `test_docker_authority_inventory_matches_compose_boundary` (`tests/test_arclink_docker.py:1720-1788`) parses real compose and asserts equality of `docker_socket/explicit_root/linux_capabilities/compose_networks/default_network/container_user`. NOTE: the test guards ONLY these structured fields; it does NOT validate prose fields (see Disagreement #2).
6. **Trusted-host gate value — PROVEN.** Gate requires literal `accepted` (`arclink_boundary.py:82`), enforced in broker `main` (`broker.py:778`) and per-request (`:638`). Compose passes `${...:-}` (`compose.yaml:860`), default empty → fails closed. Host runner does NOT require the gate (stdlib-only root systemd oneshot) — correct, the host operator owns systemd.

## DISAGREEMENTS & ADJUDICATION
**D1 — Inventory stale "Docker socket" prose. WINNER: codex.** Codex flagged that `residual_policy_state`/`remaining_gate`/`gap_019_*` prose still calls the broker's authority "writeable Docker socket" at `config/docker-authority-inventory.json:205,2269,2306,2419`, contradicting the structured `docker_socket:"none"` (`:2229`) and runtime compose (no socket mount, `compose.yaml:866-869`). I re-confirmed all four prose lines and that the drift test (`tests/test_arclink_docker.py:1755-1788`) never inspects them for the `docker_socket=="none"` case. Claude asserted "inventory matches compose and is drift-guarded by a test" without qualification — TRUE for the structured block, but it OMITS this prose drift. Codex is correct that the artifact has stale prose. I DOWNGRADE codex's "medium" to **low**: the authoritative machine-readable field and runtime are both correct (no socket); only human-readable narrative is stale, with no runtime effect.

**D2 — Inventory egress-network prose. WINNER: codex.** Codex flagged `config/docker-authority-inventory.json:316` claiming operator-upgrade-broker "receive[s] single-service outbound egress networks." I re-confirmed this is FALSE: the broker's only network is `operator-upgrade-broker-net` which is `internal:true` (`compose.yaml:872,1173`), the structured `egress_networks:[]` is correct (`:2245`), and a passing test asserts exact membership `["operator-upgrade-broker-net"]` and not-on-default (`tests/test_arclink_docker.py:883,888-889`). Claude did not surface this. Codex correct; **low** severity (doc prose only).

**D3 — Poison/malformed queue-file edge. WINNER: codex (and I strengthen it).** Codex flagged that `_process_request_file` does `lstat`/`json.loads`/request-id checks BEFORE its `try:` (`host_runner.py:368-376` vs `try:` at `:380`), so a symlink, non-regular file, invalid JSON, or bad request_id raises with NO result written, causing broker timeout (`broker.py:362`). Claude's trace step 9 listed these checks but did NOT note they sit outside the try and emit no result. I re-confirmed and found codex UNDERSTATED it: `process_once` (`:412-413`) and `main` (`:423`) do NOT catch the exception, and the offending file is NEVER moved to `processed/` (the move at `:394` is unreachable). Because the loop processes files sorted by `(mtime,name)` (`:412`), a poison file early in sort order BLOCKS every later legitimate pending request, and persists across timer ticks (re-globbed every 5s). This is a real availability edge both audits under-covered. Net: codex correct on existence; I add the persistent queue-blocking finding (see GAPS).

**D4 — Producer/HMAC cross-piece coverage. WINNER: codex.** Codex fully traced the producer (`arclink_enrollment_provisioner.py:310-320`) and verified the HMAC byte formula matches the broker verifier both ends. Claude omitted the producer/signature contract entirely. Not a conflict of fact (both correct where they spoke), but a coverage gap on Claude's side; codex's audit is more complete on this cross-piece seam. No factual disagreement — codex's account is verified correct.

**No conflict on the core claims.** Shared queue path, bare-python3 shim, stdlib-only runner, no socket/no group_add/internal-only network, timer cadence/oneshot/ExecStart, dual command-rejection, and the `:?` fail-closed guards: both audits agree and I independently re-confirmed every cited line. WINNER on all core claims: both.

## GAPS BOTH MISSED
- **G1 [medium] Persistent poison-file queue block.** Beyond codex's "broker times out": a malformed/symlink/bad-JSON/bad-id pending file raises before the try (`host_runner.py:368-376`), is never moved to `processed/`, and is re-globbed every timer tick, blocking all later-sorted legitimate requests indefinitely. Neither audit stated the persistence/queue-blocking consequence. Proof: raise paths `:368-376` precede `try:` `:380`; move/unlink at `:394-396` unreachable; `process_once`/`main` have no try (`:412-413,423`); sort by `(mtime,name)` (`:412`).
- **G2 [info] Broker poll cap constant `21630` vs timeout clamp `21600`.** `_run_host_runner_request` waits `max(30, min(21630, timeout_seconds+30))` (`broker.py:340`) while `_operator_timeout` clamps timeout to `[30,21600]` (`broker.py:368-373`). The `21630` is exactly `21600+30` headroom so the broker always outlasts the runner's own subprocess timeout (rc 124 at `host_runner.py:230`). Immaterial but neither audit noted the two constants.
- **G3 [info] `_priv_dir` name guard.** Runner requires the resolved priv dir basename == `arclink-priv` (`host_runner.py:82`) and broker requires `"arclink-priv" in path.parts` for the container priv dir (`broker.py:134`). Extra structural guards neither audit enumerated; they harden the seam.
- **G4 [info] Broker direct-fallback env home divergence.** When `HOST_RUNNER_ENABLED=0` (dead in shipped topology), broker `_operator_env` sets `HOME=/home/arclink` (`broker.py:214`) whereas the runner `_operator_env` sets `HOME=/root` (`host_runner.py:174`). Only the runner path is live; noted for completeness.

## RISKS (severity-ranked)
- [medium] Persistent poison-file queue block — `python/arclink_operator_upgrade_host_runner.py:368-376,380,394-396,412-413,423`.
- [low] Inventory stale "writeable Docker socket" prose contradicts structured `docker_socket:"none"` and runtime; not caught by drift test — `config/docker-authority-inventory.json:205,2269,2306,2419` vs `:2229`; `tests/test_arclink_docker.py:1755-1788`.
- [low] Inventory egress-network prose falsely claims operator-upgrade-broker gets an outbound egress net — `config/docker-authority-inventory.json:316` vs `compose.yaml:872,1173` and `tests/test_arclink_docker.py:883,888-889`.
- [low] Dead direct-execution fallback: if `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED=0`, broker takes `_run_operator_upgrade`/`_run_pin_upgrade` which need a docker socket the broker does NOT mount — fail-safe (errors) but unsupported in shipped compose (`compose.yaml:861`; `broker.py:645,649`).
- [info] Two env aliases for the same host priv dir across the boundary (container `ARCLINK_DOCKER_HOST_PRIV_DIR` vs host `ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR`); agreement holds because both sides explicitly pin `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR` identically — `compose.yaml:862` vs `deploy.sh:8397`. Maintenance fragility, not a defect.
- [info] `--once` parsed then discarded; `process_once()` runs unconditionally — `host_runner.py:419-423`. No behavioral impact (systemd always passes `--once`).

## CROSS-PIECE CONTRACTS (summary, all verified both ends)
Queue path formula `$BOOTSTRAP_DIR/arclink-priv/state/operator-upgrade-host-runner` (compose `:862`+deploy `:8494` == deploy systemd `:8397`); schema_version=1 + result keys; pin allowlists byte-identical; HMAC `hmac(token,"{ts}\n{nonce}\n{sha256(body)}",sha256)` producer==verifier; trusted-host gate literal `accepted`; inventory structured boundary == compose (drift-tested). All re-confirmed in code.

## AGREED VERDICT
**P8 provably does its job.** The container operator-upgrade-broker and the host systemd runner resolve to the identical host queue dir `$BOOTSTRAP_DIR/arclink-priv/state/operator-upgrade-host-runner` (both read `ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR`, pinned identically on the host unit `deploy.sh:8397` and via compose `${ARCLINK_DOCKER_HOST_PRIV_DIR}/state/...` where `ARCLINK_DOCKER_HOST_PRIV_DIR=$BOOTSTRAP_DIR/arclink-priv` `deploy.sh:8494`, collapsed to one path by the host-path→host-path repo bind `compose.yaml:869`). The `Type=oneshot` timer (default `5s`, `deploy.sh:8393,8402-8414`) runs `ExecStart=...host-runner.sh --once` (`:8399`); the shim execs bare host `python3` against a stdlib-only runner (`bin/arclink-operator-upgrade-host-runner.sh:7`, imports `host_runner.py:10-20`) so it never needs the managed venv during the very upgrade it triggers. The broker mounts NO `/var/run/docker.sock`, has NO `group_add`, and sits on a single `internal:true` network (`compose.yaml:866-872,1173`), so it cannot exec docker or fetch upstream directly — it queues typed work and the host runner (full host network/root) executes `deploy.sh upgrade`. The inventory's STRUCTURED boundary matches compose and is drift-guarded by a runtime test. Open items are non-blocking: a real but recoverable poison-file queue-block edge (medium; operator can clear `pending/`), and stale documentary prose in the inventory artifact (low; the machine-readable field and runtime are both correct). The seam is sound; the federation agrees.


### Adjudicated cross-model disagreements


- **Inventory stale 'writeable Docker socket' prose vs structured docker_socket:none** — winner: **CODEX**  
  Claude: Inventory entry matches the actual compose privileges/mounts and is guarded against drift by a runtime test (tests/test_arclink_docker.py:1720-1779) — stated without qualification.  
  GPT-5.5: Medium: inventory has stale socket prose; residual_policy_state/remaining_gate/gap_019 fields still say the broker has 'writeable Docker socket' authority (config/docker-authority-inventory.json:205,2269,2306,2419) while structured docker_socket is 'none' (:2229).  
  Adjudication: Re-confirmed all four prose lines say 'writeable Docker socket' and that the structured compose_boundary.docker_socket is 'none' (:2229), matching the real compose (no socket mount, compose.yaml:866-869). The drift test (tests/test_arclink_docker.py:1755-1788) asserts equality ONLY for docker_socket/explicit_root/linux_capabilities/compose_networks/default_network/container_user and never inspects the prose strings for the no-socket case. So Claude's structured-match claim is true and test-backed, but Claude omitted the prose drift codex correctly caught. Severity downgraded from codex's medium to low: machine-readable field and runtime are both correct, prose-only. `[config/docker-authority-inventory.json:205,2229,2269,2306,2419; tests/test_arclink_docker.py:1755-1788]`

- **Inventory egress-network prose for operator-upgrade-broker** — winner: **CODEX**  
  Claude: Broker is on a single internal:true network with no egress and not on default (compose.yaml:871-872,1173-1174); egress_networks:[] in inventory (:2245). Did not flag the contradicting prose.  
  GPT-5.5: Medium: inventory summary at :316 says operator-upgrade-broker receives a single-service outbound egress network; actual compose has only operator-upgrade-broker-net which is internal.  
  Adjudication: Re-confirmed inventory:316 falsely claims the broker gets an egress network; compose gives it only operator-upgrade-broker-net (internal:true, compose.yaml:872,1173); structured egress_networks:[] (:2245) is correct; a passing test asserts exact membership ['operator-upgrade-broker-net'] and not-on-default (tests/test_arclink_docker.py:883,888-889). Codex is correct, Claude omitted it. Severity low (prose only, runtime and structured field correct). `[config/docker-authority-inventory.json:316,2245; compose.yaml:872,1173; tests/test_arclink_docker.py:883,888-889]`

- **Malformed/poison queue-file handling in _process_request_file** — winner: **CODEX**  
  Claude: Trace listed 'reject symlink/non-regular :368-370; parse JSON :371' but did not note these execute before the try block and emit no result.  
  GPT-5.5: Medium edge: lstat and json.loads run before the try block, so symlink/non-regular/invalid-JSON escapes result emission and the broker then times out (broker.py:362).  
  Adjudication: Re-confirmed lstat/symlink-reject/json.loads/request-id checks are at host_runner.py:368-376, all BEFORE try: at :380; result write (:391) and move-to-processed (:394-396) are unreachable on that path; process_once (:412-413) and main (:423) have no try, so the exception aborts the whole drain. I found codex UNDERSTATED it: the poison file is never moved, is re-globbed every timer tick, and because the loop is sorted by (mtime,name) it persistently blocks all later legitimate pending requests. Codex correct on existence; I elevate to a persistent queue-block finding both audits under-covered. `[python/arclink_operator_upgrade_host_runner.py:368-376,380,391,394-396,412-413,423; python/arclink_operator_upgrade_broker.py:362]`

- **Producer/HMAC signature cross-piece coverage** — winner: **CODEX**  
  Claude: Did not cover the producer (enrollment_provisioner) or the HMAC signature byte formula at all.  
  GPT-5.5: Fully traced producer body json.dumps(...,sort_keys=True) (enrollment_provisioner.py:312) and HMAC over '{ts}\n{nonce}\n{sha256(body)}' (:316-320), verified it matches the broker verifier (broker.py:708-713).  
  Adjudication: No factual conflict — both correct where they spoke. I independently re-confirmed the producer formula (enrollment_provisioner.py:312-320) is byte-identical to the broker verifier (broker.py:707-713), nonce secrets.token_urlsafe(18) satisfies the verifier regex (:703). Codex's audit is materially more complete on this cross-piece seam; Claude's omitted it. Coverage win for codex, no truth dispute. `[python/arclink_enrollment_provisioner.py:312-320; python/arclink_operator_upgrade_broker.py:703,707-713]`

- **Core seam claims (shared queue path, bare-python3 shim, stdlib runner, no socket/group_add/egress, timer cadence/oneshot/ExecStart)** — winner: **BOTH**  
  Claude: All proven with path:line: queue path identical, shim bare python3, runner stdlib-only, no socket/no group_add/internal-only net, Type=oneshot every 5s, ExecStart runs shim --once.  
  GPT-5.5: Same set of core claims proven with equivalent path:line citations.  
  Adjudication: Independently re-verified every cited anchor: compose.yaml:847-851,862,866-872,1173; deploy.sh:8366-8417,8493-8496; arclink-operator-upgrade-host-runner.sh:7; host_runner.py:10-20,88,345,407-411; broker.py:276-288,316-339,765. No discrepancy between the two audits or against code. Both fully correct. `[compose.yaml:847-872; bin/deploy.sh:8366-8417,8493-8496; bin/arclink-operator-upgrade-host-runner.sh:7; python/arclink_operator_upgrade_host_runner.py:88,345; python/arclink_operator_upgrade_broker.py:276-288]`


### Risks (converged, severity-ranked)

- **[MEDIUM]** Persistent poison-file queue block: a malformed/symlink/non-regular/invalid-JSON/bad-request-id pending file raises in _process_request_file BEFORE the try block, so no result is written, the file is never moved to processed/, and it is re-globbed every timer tick. Because the drain loop is sorted by (mtime,name), such a file blocks all later legitimate pending requests indefinitely and the broker times out waiting for each. Recoverable by operator clearing pending/ but unguarded in code. `[python/arclink_operator_upgrade_host_runner.py:368-376,380,391,394-396,412-413,423; python/arclink_operator_upgrade_broker.py:362]`
- **[LOW]** Docker-authority inventory prose drift: residual_policy_state / remaining_gate / gap_019_* fields still describe the broker as owning a 'writeable Docker socket', contradicting the authoritative structured docker_socket:'none' and the real compose (no socket mount). The drift test only validates the structured boundary fields and does not catch the stale prose. `[config/docker-authority-inventory.json:205,2269,2306,2419 vs :2229; compose.yaml:866-869; tests/test_arclink_docker.py:1755-1788]`
- **[LOW]** Inventory egress-network prose falsely claims operator-upgrade-broker receives a single-service outbound egress network; the broker is attached only to operator-upgrade-broker-net which is internal:true, structured egress_networks is [], and a test asserts the exact membership. `[config/docker-authority-inventory.json:316 vs :2245; compose.yaml:872,1173; tests/test_arclink_docker.py:883,888-889]`
- **[LOW]** Dead direct-execution fallback: if ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_ENABLED=0 the broker would call _run_operator_upgrade/_run_pin_upgrade which need a Docker socket the broker does not mount. Fail-safe (errors rather than mis-executes) but unsupported in the shipped compose topology where the var is hardcoded 1. `[compose.yaml:861; python/arclink_operator_upgrade_broker.py:643-649]`
- **[INFO]** Two distinct env-var aliases for the same host private dir across the boundary (container ARCLINK_DOCKER_HOST_PRIV_DIR vs host ARCLINK_OPERATOR_UPGRADE_HOST_PRIV_DIR). Agreement holds only because both sides explicitly pin ARCLINK_OPERATOR_UPGRADE_HOST_QUEUE_DIR identically; maintenance fragility if a future change drops that explicit pin. `[compose.yaml:858,862; bin/deploy.sh:8396-8397,8494]`
- **[INFO]** Broker poll cap uses constant 21630 while the timeout clamp uses 21600; the +30 is intentional headroom so the broker always outlasts the runner subprocess timeout (rc 124). Immaterial but the two constants differ. `[python/arclink_operator_upgrade_broker.py:340,368-373; python/arclink_operator_upgrade_host_runner.py:230]`
- **[INFO]** --once flag is parsed then discarded (del args); process_once() runs unconditionally. No behavioral impact since the systemd unit always passes --once. `[python/arclink_operator_upgrade_host_runner.py:419-423; bin/deploy.sh:8399]`


### GPT-5.5 ratifier refinements

- **[MEDIUM]** The record’s touch-point/input coverage is complete for the broker/runner seam.  
  → correction: _atomic_write_json(request_path, payload) runs before poll_interval = float(... ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS ...); run_operator_upgrade_request catches ValueError and returns failure, while process_once later drains pending/*.json. `[python/arclink_operator_upgrade_broker.py:339; python/arclink_operator_upgrade_broker.py:341; python/arclink_operator_upgrade_broker.py:651; python/arclink_operator_upgrade_host_runner.py:412]`
- **[MEDIUM]** The record fully flags path/env variables that can make the container and host queue roots diverge.  
  → correction: The canonical path lines agree only when the Compose env file consumed by bin/arclink-docker.sh is the default BOOTSTRAP_DIR/arclink-priv/config/docker.env or otherwise contains the same ARCLINK_DOCKER_HOST_PRIV_DIR. `[bin/arclink-docker.sh:7; bin/arclink-docker.sh:119; bin/deploy.sh:8420; bin/deploy.sh:8397; compose.yaml:862]`
- **[LOW]** The record’s queue-path validation summary is complete on both Python ends.  
  → correction: Broker configured queue paths must be absolute and relative_to(host_priv/state); runner configured queue paths only pass an absolute-path check before use. `[python/arclink_operator_upgrade_broker.py:276; python/arclink_operator_upgrade_broker.py:283; python/arclink_operator_upgrade_host_runner.py:87; python/arclink_operator_upgrade_host_runner.py:90; bin/deploy.sh:8397]`
- **[LOW]** The record cites compose.yaml:1173 as proof that operator-upgrade-broker-net is internal:true.  
  → correction: operator-upgrade-broker-net is declared at compose.yaml:1173 and marked internal:true at compose.yaml:1174. `[compose.yaml:1173; compose.yaml:1174]`
