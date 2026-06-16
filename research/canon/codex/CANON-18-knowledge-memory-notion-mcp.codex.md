<<<CODEX-VERDICT-START CANON-18>>>
## CANON-18 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: Ratify the verifier-corrected CANON-18, but add two confirmed concurrency/auth refinements and keep qmd protocol unratified.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- REFUTE original dead-env claim: `ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES` is live in `_file_content_hash`; `0` disables the cap via falsy guard. `python/arclink_memory_synthesizer.py:329-335`
- CONFIRM ssot broker fail-closed on destructive ops: `archive/delete/trash/destroy` raise before apply; allowlist follows. `python/arclink_control.py:17103-17112`
- REFINE ssot.write seam: MCP calls `enqueue_ssot_write` correctly, but normalizer derives `final_state` from `applied/queued/approval_required/status` and promotes nested `notion_result`, not top-level `final_state/url/id`. `python/arclink_mcp_server.py:1597-1623`, `python/arclink_mcp_server.py:2670-2679`, `python/arclink_control.py:16513-16525`, `python/arclink_control.py:16856-16867`
- CONFIRM MEDIUM risk: webhook kick is best-effort and swallowed; timer is the only guaranteed drain. `python/arclink_notion_webhook.py:42-59`, `systemd/user/arclink-ssot-batcher.timer:5-7`
- CONFIRM MEDIUM risk: `authorized_live` defaults to real `request.urlopen` and reads the root page even when mutation is not allowed. `python/arclink_notion_ssot.py:1098-1101`, `python/arclink_notion_ssot.py:1120-1125`, `python/arclink_notion_ssot.py:1139-1147`
- CONFIRM/REFINE loopback risk: loopback gate is real in direct transport, but Funnel proxies to `127.0.0.1`, so HMAC is the real public-webhook gate. `python/arclink_notion_webhook.py:289-293`, `python/arclink_control.py:7628-7632`, `bin/tailscale-notion-webhook-funnel.sh:175`
- CONFIRM webhook signature path: raw body + `X-Notion-Signature` + stored token reach HMAC-SHA256 `compare_digest`. `python/arclink_notion_webhook.py:344-350`, `python/arclink_control.py:12135-12141`
- CONFIRM webhook event storage/dedupe: accepted events are `INSERT OR IGNORE` by unique `event_id`. `python/arclink_notion_webhook.py:352-360`, `python/arclink_control.py:774-787`, `python/arclink_control.py:12144-12158`
- REFINE open B35: producer of `notion-reindex` rows is found; event rows are claim-guarded, but reindex notifications are not claimed before live sync. `python/arclink_control.py:19333-19339`, `python/arclink_control.py:14703-14764`, `python/arclink_control.py:19154-19203`, `python/arclink_control.py:14828-14840`
- REFINE qmd seam: ArcLink sends MCP `2025-03-26`, but qmd is external and not locally ratified; comment says qmd 2.5.2 while pin is 2.5.3. `python/arclink_mcp_server.py:71-75`, `python/arclink_mcp_server.py:703-724`, `config/pins.json:54-58`
- REFINE S2 HIGH seam: confirmed live break for `pod_comms.*` token injection, but `agents.register` intentionally uses an explicit registration token path. `plugins/hermes-agent/arclink-managed-context/__init__.py:276-302`, `plugins/hermes-agent/arclink-managed-context/__init__.py:667-668`, `python/arclink_mcp_server.py:397-426`, `python/arclink_mcp_server.py:1093-1097`, `bin/activate-agent.sh:80-111`
- REFINE S12 seam: "only 5 script-invoked tools" undercounts current scripts; at least 8 distinct ArcLink MCP tools are script-called, while many others remain SKILL.md prose only. `skills/arclink-first-contact/scripts/run-first-contact.sh:41-48`, `skills/arclink-first-contact/scripts/run-first-contact.sh:98-106`, `skills/arclink-first-contact/scripts/run-first-contact.sh:266`, `skills/arclink-vaults/scripts/curate-vaults.sh:88-97`, `skills/arclink-vaults/scripts/curate-vaults.sh:156-165`, `skills/arclink-notion-knowledge/scripts/curate-notion.sh:101-140`, `skills/arclink-notion-knowledge/scripts/curate-notion.sh:170-185`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: during an operator-armed install window, any Funnel-reachable caller can POST `verification_token` before HMAC exists; the check/set is also non-atomic, so two concurrent armed POSTs can both pass `get_setting` and the later `ON CONFLICT` update wins. `python/arclink_notion_webhook.py:220-235`, `python/arclink_notion_webhook.py:332-341`, `python/arclink_control.py:2971-2985`, `bin/tailscale-notion-webhook-funnel.sh:175`
- MEDIUM: `consume_notion_reindex_queue` has no claim/lease; concurrent batchers can select the same due `notification_outbox` row and both run `sync_shared_notion_index` before either marks delivered. `python/arclink_control.py:14828-14840`, `python/arclink_control.py:14873-14881`, `python/arclink_control.py:14960-14964`, `python/arclink_control.py:9395-9400`

### Claude citations re-confirmed or corrected
- Re-confirmed memory-synth bounds/redaction/single-flight/status writes. `python/arclink_memory_synthesizer.py:184-225`, `python/arclink_memory_synthesizer.py:229-232`, `python/arclink_memory_synthesizer.py:1673-1679`, `python/arclink_memory_synthesizer.py:1695-1697`
- Re-confirmed MCP loopback, session, structuredContent, and HTTP-200 JSON-RPC error behavior. `python/arclink_mcp_server.py:1650-1655`, `python/arclink_mcp_server.py:1718-1721`, `python/arclink_mcp_server.py:1744-1758`, `python/arclink_mcp_server.py:1764-1809`, `python/arclink_mcp_server.py:1835-1839`
- Corrected original record: `/health` pre-auth applies to webhook only; MCP health is behind loopback. `python/arclink_notion_webhook.py:303-307`, `python/arclink_mcp_server.py:1727-1742`
- Corrected original record: qmd producer payload includes `limit` as well as searches/collections/intent/rerank. `python/arclink_mcp_server.py:731-753`

### Residual disagreement with the Claude half (for final reconciliation)
- No CANON-18 HIGH row exists in §3; the only HIGH touching CANON-18 is S2, and it should be scoped to `pod_comms.*`, not `agents.register`.
- qmd MCP compatibility remains unratified from in-repo evidence; the only executable ArcLink side is producer-side.
- The verifier-corrected CANON still needs the armed-window webhook token hijack/race and unclaimed reindex-consumer race folded into CANON-18.
<<<CODEX-VERDICT-END CANON-18>>>
