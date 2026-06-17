<<<CODEX-VERDICT-START CANON-15>>>
## CANON-15 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(6)
ONE-LINE VERDICT: Core broker/runner/detector proof holds, but the record needs corrections on policy consumers, M1 wording, M3/M5 severity, timeout semantics, and detector overlap.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM H1 HIGH: one bad `pending/*.json` wedges the drain; `item.stat()` can raise before per-file handling, and `_process_request_file` pre-`try` rejects poison files without moving them. `python/arclink_operator_upgrade_host_runner.py:367-376,380-396,412,417-423`
- REFINE M1: same explicit queue env is read on both sides, but broker confines it under private state while runner only requires absolute; fallback priv env families differ. `python/arclink_operator_upgrade_broker.py:276-288`; `python/arclink_operator_upgrade_host_runner.py:79-92`; `compose.yaml:862`; `bin/deploy.sh:8395-8397`
- CONFIRM M2: nonce replay window exists because `_nonce_seen` and `_record_nonce` are separate locked regions, and the store is process-memory under `ThreadingHTTPServer`. `python/arclink_operator_upgrade_broker.py:665-716,765`
- REFINE M3: mechanism confirmed, severity LOW not MEDIUM; dismiss sets `silenced=1`, active filtering ignores `silenced`, but execution still requires an operator confirm. `python/arclink_control.py:9596-9608,9675-9706`; `python/arclink_operator_raven.py:1281-1290`
- CONFIRM M4: control payload normalization lacks a component allowlist, and non-Docker provisioner validates kind/target but not component; broker/runner are the enforcing boundary. `python/arclink_control.py:9502-9534`; `python/arclink_enrollment_provisioner.py:421-448`; `python/arclink_operator_upgrade_broker.py:265-273`; `python/arclink_operator_upgrade_host_runner.py:262-271`
- REFINE M5: stale authority-inventory prose is real, but actual compose boundary has no docker.sock and internal-only network; this is doc/audit drift more than runtime authority. `config/docker-authority-inventory.json:205,316,2229-2245,2419`; `compose.yaml:842-872,1173-1174`
- CONFIRM M6: successful response decode can raise `UnicodeDecodeError`, outside the provisioner catch tuple. `python/arclink_enrollment_provisioner.py:334-343`
- CONFIRM stale/ghost execution: broker can time out after writing pending JSON, while runner never enforces `created_at` or `timeout_seconds` staleness. `python/arclink_operator_upgrade_broker.py:338-365`; `python/arclink_operator_upgrade_host_runner.py:279-330,381`
- CONFIRM verifier LOW queue growth: broker only reads `results/<id>.json`; runner writes results and moves processed files with no retention. `python/arclink_operator_upgrade_broker.py:314-315,345-360`; `python/arclink_operator_upgrade_host_runner.py:377,391-396`
- REFINE §B32 hermes-docs: docs-only payload is reachable if pins diverge; collapse only drops child when parent is also included, and broker rejects `hermes-docs`. `python/arclink_pin_upgrade_check.py:58-67,640-659`; `config/pins.json:23-30`; `python/arclink_operator_upgrade_broker.py:48,265-273`
- CONFIRM §B32 detector overlap risk: no detector lock/transaction surrounds SELECT→INSERT/UPDATE→notify, so overlap can IntegrityError on first insert or double-notify same target. `python/arclink_pin_upgrade_check.py:405-443,503-532,699-731`; `python/arclink_ctl.py:2685-2687`
- REFINE §B32 policy drift: policy is not display-only; `PIN_UPGRADE_COMPONENTS` gates mutating `/pin_upgrade`, but Raven queues opaque tokens, not literal `hermes`, and control maps `hermes` to agent/docs payloads. `python/arclink_operator_raven.py:35,1594-1600,1307-1313`; `python/arclink_control.py:9579-9593`
- REFINE §C51: M3 should settle at LOW unless final product semantics define Dismiss as a hard removal contract. `python/arclink_control.py:9683-9706`; `python/arclink_control.py:9654-9668`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: provisioner HTTP timeout is 30s shorter than broker’s own wait window, so a host result in the broker grace period can be reported as failed to the action worker, inviting retry/double execution. `python/arclink_enrollment_provisioner.py:297-335,352-356`; `python/arclink_operator_upgrade_broker.py:340-365`
- LOW: malformed `ARCLINK_OPERATOR_UPGRADE_HOST_RUNNER_POLL_SECONDS` is parsed after `_atomic_write_json`, so the broker can return rejection while the already-queued host mutation still executes. `python/arclink_operator_upgrade_broker.py:338-342,651-653`; `python/arclink_operator_upgrade_host_runner.py:412-413`

### Claude citations re-confirmed or corrected
- HMAC seam reconfirmed byte-for-byte: producer signs `ts\nnonce\nsha256(body_bytes)`, consumer hashes raw body bytes. `python/arclink_enrollment_provisioner.py:312-330`; `python/arclink_operator_upgrade_broker.py:707-715`
- Control spans corrected: `register_pin_upgrade_action` is `9518-9547`; `_normalize_pin_upgrade_item` is `9502-9515`; dismiss is `9675-9711`. `python/arclink_control.py:9502-9547,9675-9711`
- Runner→component marker seam reconfirmed: host runner uses tail status markers; `--skip-upgrade` emits one terminal marker per apply path. `python/arclink_operator_upgrade_host_runner.py:248-259,274-276`; `bin/component-upgrade.sh:611-668`
- M5 citation corrected from impossible `broker.py:866` to compose/inventory lines. `compose.yaml:842-872,1173-1174`; `config/docker-authority-inventory.json:2229-2245`

### Residual disagreement with the Claude half (for final reconciliation)
- The record/verifier overstate `arclink_upgrade_policy` as display-only; it is also a mutating command component gate, though not a broker payload source.
- I downgrade M3 to LOW and M5 to LOW/doc-drift; H1, M1, M2, M4, M6, stale/ghost, and queue-growth mechanisms stand.
- Add the provisioner/broker timeout mismatch as a real CANON-15 seam defect.
<<<CODEX-VERDICT-END CANON-15>>>
