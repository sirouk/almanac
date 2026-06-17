<<<CODEX-VERDICT-START CANON-23>>>
## CANON-23 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(6)
ONE-LINE VERDICT: Core record is trustworthy, but the broker seam can now be closed and several delivery/proof edge failures need to be added to CANON.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM MEDIUM no retry backoff: `mark_notification_error` only writes `delivery_error`, while due checks depend on `next_attempt_at`; the 5s delivery timer makes non-leased failures hot-loop. `python/arclink_control.py:9403`, `python/arclink_notification_delivery.py:313`, `systemd/user/arclink-notification-delivery.timer:5`
- CONFIRM MEDIUM evidence DB unwired: `store_evidence_run` exists, but `run_live_proof` writes only local JSON; repo grep found production references only to schema/health, not DAL callers. `python/arclink_evidence.py:278`, `python/arclink_live_runner.py:743`, `python/arclink_control.py:2523`
- CONFIRM MEDIUM divergent redaction engines: evidence uses narrow `_SECRET_PATTERNS`; shared regex catches OpenAI/Anthropic/JWT/PEM/Telegram/Discord/Chutes/GitHub families. Error path can preserve weakly-redacted exception text. `python/arclink_evidence.py:26`, `python/arclink_evidence.py:68`, `python/arclink_live_journey.py:385`, `python/arclink_secrets_regex.py:25`
- CONFIRM MEDIUM global env mutation: `run_live_proof` patches `os.environ` because journey credential checks read process globals. `python/arclink_live_runner.py:704`, `python/arclink_live_journey.py:58`
- REFINE §5B-40 gateway-exec broker: end-to-end JSON/header contract is confirmed, not open. Consumer sends `/v1/public-agent-bridge` with `deployment_id,prefix,project_name,payload,timeout_seconds` and `X-ArcLink-Gateway-Exec-Token`; broker reads/auths those fields and rejects raw commands. `python/arclink_notification_delivery.py:342`, `python/arclink_notification_delivery.py:379`, `python/arclink_gateway_exec_broker.py:51`, `python/arclink_gateway_exec_broker.py:227`
- REFINE §5B-40 album race: I do not see a double-leader race after `_claim_notification_for_delivery`; the real failure mode is non-leader deferral leaving its lease intact until expiry if the leader dies. `python/arclink_notification_delivery.py:1629`, `python/arclink_notification_delivery.py:1527`, `python/arclink_notification_delivery.py:1718`, `python/arclink_notification_delivery.py:1927`
- CONFIRM S8 bot token persistence: detached bridge jobs serialize `payload`/`gateway_exec_request`, and payload includes `bot_token`; job file is 0600 and unlinked on worker read, but still disk persistence. `python/arclink_notification_delivery.py:674`, `python/arclink_notification_delivery.py:973`, `python/arclink_notification_delivery.py:997`, `python/arclink_notification_delivery.py:1005`
- CONFIRM dashboard/runner env divergence: runner honors `CLOUDFLARE_API_TOKEN_REF`, dashboard blocker check does plain key lookup only. `python/arclink_live_runner.py:85`, `python/arclink_live_journey.py:53`, `python/arclink_dashboard.py:548`
- CONFIRM pod-message nonatomic seam: pod message commits before `queue_notification`, whose helper commits separately. `python/arclink_pod_comms.py:306`, `python/arclink_pod_comms.py:308`, `python/arclink_control.py:8071`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM — Due filtering happens after `LIMIT`, causing head-of-line blocking: a not-due leased public-agent-turn can hide newer due turns, and hosted API calls the fast path with `limit=1`. `python/arclink_notification_delivery.py:1686`, `python/arclink_notification_delivery.py:1699`, `python/arclink_hosted_api.py:2828`; same pattern exists in periodic fetch. `python/arclink_control.py:9423`, `python/arclink_notification_delivery.py:1898`
- MEDIUM — `run_live_proof` can return `dry_run_ready`/exit 0 even when readiness/diagnostics failed; status/exit ladder ignores `readiness.ready` and `diagnostics.all_ok`. `python/arclink_live_runner.py:670`, `python/arclink_live_runner.py:678`, `python/arclink_live_runner.py:692`, `python/arclink_live_runner.py:751`
- LOW — Default evidence artifact write is unguarded; an unwritable `evidence/` crashes the CLI before it can print JSON/result. `python/arclink_live_runner.py:743`, `python/arclink_live_runner.py:747`, `python/arclink_live_runner.py:804`
- LOW — Health-watch forwards raw `[fail]`/`[warn]`/stderr lines to operator notifications without shared redaction, so a secret printed by health output can leave the host. `python/arclink_health_watch.py:88`, `python/arclink_health_watch.py:220`, `python/arclink_health_watch.py:141`, `python/arclink_health_watch.py:248`
- LOW — If detached bridge worker spawn/log-open fails after job write, the token-bearing job file is not unlinked by that path. `python/arclink_notification_delivery.py:1185`, `python/arclink_notification_delivery.py:1198`, `python/arclink_notification_delivery.py:1213`

### Claude citations re-confirmed or corrected
- CONFIRM adapter shapes: Telegram unwraps `result.message_id`; Discord returns raw `id` objects consumed by delivery. `python/arclink_telegram.py:205`, `python/arclink_notification_delivery.py:1335`, `python/arclink_discord.py:68`, `python/arclink_notification_delivery.py:1380`
- CORRECT `_REDACT_ENV_KEYS`: it is 15 keys, not 18. `python/arclink_evidence.py:44`
- CORRECT evidence serialization wording: `EvidenceRecord.to_dict` redacts provider/url/health/detail/error only, not every field. `python/arclink_evidence.py:118`
- CORRECT timer wording: notification delivery is 5s boot/active; health-watch has `OnActiveSec=5m` plus `OnUnitActiveSec=15m`. `systemd/user/arclink-notification-delivery.timer:5`, `systemd/user/arclink-health-watch.timer:16`
- CORRECT bridge argv: allowlist uses absolute Hermes venv Python and script path, not bare `python3`. `python/arclink_notification_delivery.py:297`

### Residual disagreement with the Claude half (for final reconciliation)
- None material against the CANON-23 verdict. Fold in the six refinements above, especially closing §5B-40 broker verification and adding the notification head-of-line/dry-run readiness gaps.
<<<CODEX-VERDICT-END CANON-23>>>
