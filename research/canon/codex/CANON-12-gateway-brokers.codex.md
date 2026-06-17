<<<CODEX-VERDICT-START CANON-12>>>
## CANON-12 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(6)
ONE-LINE VERDICT: The broker-boundary thesis is code-proven, but the consolidated record still needs corrections for detached secret storage, cap/setpriv certainty, broker-net exposure, pod-message delivery semantics, and one false FD-leak risk.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM core boundary: GAP-019 is code-enforced at shared guard and at broker/helper startup/request paths: `python/arclink_boundary.py:85-97`; `python/arclink_gateway_exec_broker.py:287-293,378-380`; `python/arclink_agent_process_helper.py:871-887,945-947`.
- CONFIRM token auth/raw-command rejection: constant-time token checks and raw command rejection are present across the HTTP boundary family, e.g. `python/arclink_gateway_exec_broker.py:51-54,196-198`; `python/arclink_deployment_exec_broker.py:96-99,117-119`; `python/arclink_agent_process_helper.py:92-100,873-884`.
- CONFIRM gateway-exec contract: producer sends `{deployment_id,prefix,project_name,payload,timeout_seconds}` and broker validates route/auth/body/payload before local command reconstruction: `python/arclink_notification_delivery.py:334-348,674-685,729-735`; `python/arclink_gateway_exec_broker.py:173-193,227-284,335-361`.
- CONFIRM deployment/supervisor/migration/user/process helper contracts: local operation reconstruction and path/IP/env validation match the claimed shape: `python/arclink_deployment_exec_broker.py:117-156`; `python/arclink_agent_supervisor_broker.py:96-110,265-281`; `python/arclink_migration_capture_helper.py:115-158`; `python/arclink_agent_user_helper.py:408-422`; `python/arclink_agent_process_helper.py:334-370,385-457`.
- CONFIRM HIGH S8/A8 secret correction: “stdin-only, never on disk” is false. The detached path stores `gateway_exec_request.payload.bot_token` in a 0600 JSON job file: `python/arclink_notification_delivery.py:674-680,960-1001`.
- REFINE HIGH cap/setpriv risk: compose definitely drops all caps and adds none for `agent-process-helper`, while code runs `setpriv --reuid/--regid`; the likely EPERM impact still needs live container proof. `compose.yaml:908-918`; `python/arclink_agent_process_helper.py:444-457`.
- REFINE MEDIUM broker bind risk: production compose binds brokers/helpers to `0.0.0.0` on internal networks, and gateway-exec is currently co-attached to operator gateway/dashboard plus notification-delivery. Only notification-delivery is shown with the gateway token. `compose.yaml:388-431,1006-1020,1025-1032,1050-1052,1163-1176`.
- REFINE MEDIUM env pass-through: helper accepts arbitrary safe uppercase non-secret keys, but the in-repo supervisor producer pre-filters and constructs the env, so the risk requires a compromised tokened producer or alternate client. `python/arclink_agent_process_helper.py:334-370`; `python/arclink_docker_agent_supervisor.py:291-300,649-673`.
- REFUTE MEDIUM log-FD leak as stated: the helper stores only `Popen` and signatures in globals; the log handle is a local passed to `Popen`, not retained in `PROCESSES`. `python/arclink_agent_process_helper.py:71-73,837-857`.
- CONFIRM/REFINE pod_comms grants: same-Captain sends bypass grants, and cross-Captain grants are user-pair scoped unless metadata pins deployments. `python/arclink_pod_comms.py:68-81,125-144`.
- REFINE S9: `send_pod_message` commits message/audit/event first, then `queue_notification` commits separately; notification-delivery does not consume `target_kind='user-agent'` rows. User agents consume via MCP refresh. `python/arclink_pod_comms.py:306-321`; `python/arclink_control.py:8055-8071,9411-9423,9858-9890`; `python/arclink_mcp_server.py:2127-2134`.
- REFINE B29 command-shape audit: validator allows only docker-exec or compose-exec bridge shapes, and broker-built deployment mode derives project/container from safe IDs and Docker labels; validator alone is weaker for tampered detached job files. `python/arclink_notification_delivery.py:479-527,530-552`; `python/arclink_gateway_exec_broker.py:227-284`.

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: Pod Comms notification metadata is queued but stripped at agent consumption: `extra` has `message_id`, sender, and attachments, but `consume_agent_notifications` SELECTs no `extra_json`, so refresh writes only the flattened notification row. `python/arclink_pod_comms.py:308-320`; `python/arclink_control.py:9871-9890`; `bin/user-agent-refresh.sh:184-240`.
- LOW/MEDIUM: Pod message status appears unwired in production: `mark_pod_message_delivered` updates `arclink_pod_messages`, but the agent notification consume path only marks `notification_outbox.delivered_at`; no production caller of `mark_pod_message_delivered` was found by `rg`. `python/arclink_pod_comms.py:398-437`; `python/arclink_control.py:9883-9890`; `python/arclink_mcp_server.py:2127-2134`.

### Claude citations re-confirmed or corrected
- Re-confirmed: three services mount Docker socket and the root supervisor does not: `compose.yaml:666,832,1017,949-992`.
- Re-confirmed: public bridge receives JSON on stdin and then moves bot tokens into process env for Hermes adapters. `python/arclink_gateway_exec_broker.py:295-302`; `python/arclink_public_agent_bridge.py:32-39,375-383,793-800`.
- Corrected: `queue_notification(channel_kind='pod-message')` is not one transaction with the pod message write and is not delivered by notification-delivery’s normal loop. `python/arclink_pod_comms.py:306-321`; `python/arclink_notification_delivery.py:1783-1787,1890-1895`.
- Corrected: gateway-exec-broker-net “future co-attachment” is current topology, but current operator co-tenants have URL without token in compose. `compose.yaml:165-174,388-431,1025-1032,1050-1052`.
- Corrected/softened: chown TOCTOU remains a validate-then-act concern, but the code invokes plain `chown -R` without `-H/-L`; the symlink-traversal wording is overstated. `python/arclink_agent_user_helper.py:129-148,425-447`.

### Residual disagreement with the Claude half (for final reconciliation)
- Keep OBJECT, not REJECT: the privilege-boundary design is real, but the detached token-on-disk and pod-message notification/status mismatches are material contract corrections.
- Do not carry the agent-process-helper FD leak as a confirmed MEDIUM without runtime evidence; code does not retain log handles in globals. `python/arclink_agent_process_helper.py:71-73,843-857`.
- Cap-drop vs `setpriv` should remain HIGH or “HIGH pending live proof”; this read-only audit proved the compose/code mismatch, not an executed live-container EPERM. `compose.yaml:911-918`; `python/arclink_agent_process_helper.py:444-457`.
- No CANON-12 item appears in §5C residual severity disputes.
<<<CODEX-VERDICT-END CANON-12>>>
