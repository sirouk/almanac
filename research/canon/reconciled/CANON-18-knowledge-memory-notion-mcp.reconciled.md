# CANON-18 — Knowledge / Memory / Notion / MCP — RECONCILED (both-model truth)

- Piece: CANON-18 (Knowledge / Memory / Notion / MCP)
- Codex sign-off: **OBJECT(4)** — ratify verifier-corrected record + 2 new concurrency/auth refinements + qmd left unratified
- Final adjudicator: Claude Opus 4.8 (1M), code re-opened for every disputed point
- Federation sign-off: **AGREED-WITH-STANDING-DISAGREEMENTS** (see §Standing Disagreements; all are external/cross-piece non-code-settleable, not in-code disputes)

Method: every REFUTE/REFINE/NEW-FINDING below was re-decided by re-opening the cited
code in this repo. Code wins over any comment, name, or prior claim. Codex CONFIRM
items where both models already agreed are ratified one-line.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| Point | Winner | Deciding cite (re-opened) |
|---|---|---|
| "ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES is dead/unread" (original record DRIFT#1 + RISK + VERDICT) | **claude-verify + codex** (original record REFUTED) | `arclink_memory_synthesizer.py:329-335` — `_int_env(...)` reads the env var live; guard `if max_hash_bytes and st_size>...` |
| Setting that env to `0` disables the cap (unbounded sha256) | **claude-verify (G2) + codex** | `arclink_memory_synthesizer.py:335` falsy-guard; read loop `:337-341` has no size bound |
| ssot.write seam: `_normalize_ssot_write_result` consumes `final_state/target_id/url/id` (original contract#5/OPEN#1) | **claude-verify + codex** (original record REFINED) | `arclink_mcp_server.py:1597-1623` reads `applied/queued/approval_required/status` + nested `notion_result.{url,id,object}`; top-level `target_id` is read by the **caller** at `:2682`, not the normalizer |
| Broker fail-closed on destructive ops (record OPEN#1 / self-check#3) | **both** (record's own fear refuted; fail-closed confirmed) | `arclink_control.py:17105-17112` raise `PermissionError` on `SSOT_FORBIDDEN_OPERATIONS`, `ValueError` if not in allowlist; constants `:12162,:12164` |
| MEDIUM: webhook kick best-effort; timer is only guaranteed drain | **both** | `arclink_notion_webhook.py:42-59` (swallowed), `:361`; `systemd/user/arclink-ssot-batcher.timer` OnUnitActiveSec=1m |
| MEDIUM: `authorized_live` defaults to real `request.urlopen`, reads root page w/o mutation allowed | **both** | `arclink_notion_ssot.py:1101` default, `:1120` live read, `:1139-1147` write preflight separately gated |
| Loopback "enforcement" is not a public-webhook defense under Funnel (record over-credits loopback) | **claude-verify (G1) + codex** | funnel proxies to `127.0.0.1` (`bin/tailscale-notion-webhook-funnel.sh:290`); `backend_client_allowed` returns True for loopback (`arclink_control.py:7628-7632`); gate at `arclink_notion_webhook.py:289-293,312`. HMAC + token state machine is the real gate |
| qmd protocol coupling comment "qmd 2.5.2 speaks 2025-03-26" is stale vs pin 2.5.3 (G3) | **claude-verify + codex** | comment `arclink_mcp_server.py:73`; pin `config/pins.json:57` = `2.5.3`; protocol const `:75` |
| `/health` pre-auth applies to **webhook only**; MCP health is behind loopback | **both** (original record correct; codex re-affirms) | `arclink_notion_webhook.py:303-306` (pre-auth) vs `arclink_mcp_server.py:1727-1742` (behind loopback) |
| qmd producer payload also emits clamped `limit` (1..5), not just searches/collections/intent/rerank | **codex + claude-verify (G5)** | `arclink_mcp_server.py:735` clamp, `:753` emit |
| Webhook HMAC signature path (raw body + header + stored token -> compare_digest) | **both** | `arclink_notion_webhook.py:344-350`; `arclink_control.py:12135-12141` |
| Webhook event storage/dedupe INSERT OR IGNORE by unique event_id | **both** | `arclink_notion_webhook.py:352-360`; `arclink_control.py:12151-12158`; schema `:774-787` |
| Token state machine 409/412 + TTL floor 60s + mark-verified raises w/o token | **both** | `arclink_notion_webhook.py:210-230,110,254-255` |
| memory-synth bounds/redaction/flock/dedupe/unsafe-filter | **both** | `arclink_memory_synthesizer.py:184-225,1673-1679,1695-1697,1734-1754,1429-1433` |
| MCP loopback/body-bound/per-tool-auth/HTTP-200 JSON-RPC error/structuredContent | **both** | `arclink_mcp_server.py:1650-1655,1718-1721,1744-1758,1835-1839,2667,1882,1858` |

---

## CONFIRMED Codex NEW FINDINGS (re-verified true -> net-new federation risks)

### NF1 — MEDIUM (CONFIRMED): armed-window verification-token hijack + non-atomic check/set race
During an operator-armed install window, `handle_verification_token_post` does a
read-then-write that is not atomic: `get_setting` (`arclink_notion_webhook.py:209`),
empty-stored branch (`:210`), armed branch (`:220`), then `upsert_setting`
(`:231`) which is `INSERT ... ON CONFLICT(key) DO UPDATE`
(`arclink_control.py:2971-2980`). Two concurrent armed POSTs both observe empty
`stored` and both write; the later `ON CONFLICT` write wins. Under the intended
Funnel deployment (`bin/tailscale-notion-webhook-funnel.sh:290` -> `127.0.0.1`),
`backend_client_allowed` (`arclink_control.py:7628-7632`) passes for the entire
internet, so any external caller can attempt the POST while the window is open.
Bounded: requires (a) the operator-armed window to be open and (b) Funnel exposure;
the 409-on-already-stored guard still blocks overwrite outside the window. Code-verified.

### NF2 — MEDIUM (CONFIRMED): unclaimed reindex-consumer race (double full sync)
`consume_notion_reindex_queue` selects undelivered `notification_outbox` rows with a
plain SELECT (`arclink_control.py:14828-14839`) and runs `sync_shared_notion_index`
(`:14874`) BEFORE any row is marked delivered (`mark_notification_delivered` at
`:14964`). There is no claim/lease — unlike the event-table path which uses
`_claim_pending_notion_webhook_events`. Two concurrent batchers (timer + webhook
kick firing together) can both select the same due rows and both run the live sync.
Idempotent at the index level (it re-fetches+re-indexes), so the harm is duplicated
work / wasted Notion+qmd calls, not corruption. Code-verified.

---

## REJECTED Codex NEW FINDINGS

None. Both Codex new findings hold in code.

(Note: G4 from the Claude verifier — source_ip override TOCTOU on MCP bootstrap —
is not a Codex new finding; it is a Claude-verify gap, env-gated behind
`ARCLINK_ALLOW_LOOPBACK_SOURCE_IP_OVERRIDE` defaulting to 0. It is real but
INFO/conditional and not contested by either model; folded as INFO, not a net-new
MEDIUM.)

---

## SEVERITY CHANGES (only where code supports)

| Risk | From | To | Cite |
|---|---|---|---|
| "exported env ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES is dead" | LOW (false risk) | **REMOVED** | `arclink_memory_synthesizer.py:329-335` (env is live) |
| hash-cap is operator-defeatable to unbounded when set to 0 (replaces the above) | (n/a) | **LOW (new)** | `arclink_memory_synthesizer.py:335-341` |
| webhook loopback as a security property | implied defense in original VERDICT (line 378) | **reframed: NOT a public defense under Funnel; HMAC is the real gate** | `bin/tailscale-notion-webhook-funnel.sh:290`, `arclink_control.py:7628-7632` |
| armed-window token hijack/race | (unflagged) | **MEDIUM (net-new, NF1)** | `arclink_notion_webhook.py:209-231`, `arclink_control.py:2971-2980` |
| reindex-consumer race | (unflagged) | **MEDIUM (net-new, NF2)** | `arclink_control.py:14828-14964` |

Unchanged-and-correct: MEDIUM (timer-only drain), MEDIUM (authorized_live live egress),
LOW (/health webhook pre-auth presence-leak), LOW (MCP HTTP-200 JSON-RPC errors),
INFO (memory cards are awareness hints, bounded/redacted).

---

## STANDING DISAGREEMENTS (cannot be settled from in-repo code alone)

1. **qmd MCP protocol compatibility (contract #6).** ArcLink emits MCP `2025-03-26`
   (`arclink_mcp_server.py:75`) but the qmd binary is external (`@tobilu/qmd` pin
   `config/pins.json:57`) and not in-tree. Both models agree this is producer-only
   and the comment is now stale (qmd 2.5.2 -> pinned 2.5.3, G3). It **cannot** be
   ratified from this repo; requires running the pinned qmd's handshake. Standing.

2. **§3 cross-piece HIGH scoping (S2) and script-tool count (S12).** Codex's REFINE
   items about S2 (`pod_comms.*` vs `agents.register`) and S12 (">=8 script-invoked
   MCP tools, not 5") concern the broader catalog (§3 / cross-piece rows), not any
   in-piece CANON-18 claim. They were spot-checked as plausible but live outside this
   piece's resolution scope; they are flagged for the catalog-level reconciliation,
   not settled here.

3. **WWAL double-process proof for the event-table path (record self-check #2 / OPEN#4).**
   `_claim_pending_notion_webhook_events` (`arclink_control.py:19154`) DOES lease the
   event rows (so the event path is guarded), but the formal proof that no two batchers
   double-process under WAL was not executed by either model (it is CANON-01 internal
   concurrency). Note: the **reindex** path is now affirmatively shown UNGUARDED (NF2);
   the **event** path is guarded. The residual is only the un-run formal WAL stress test.

---

## NET BOTH-MODEL VERDICT

CANON-18 **provably does its job within its real (narrow) scope**, after corrections.
The record's load-bearing strengths are code-verified by both models: bounded,
content-hash-fresh, prompt-injection-wrapped, unsafe-filtered, secret-redacted,
single-flighted memory-synth off the chat path; a clean dependency-injectable Notion
REST client with a fail-closed no-secret proof harness; HMAC + operator-armed
verification-token state machine on the webhook; loopback + per-tool-token MCP server;
and a fail-closed SSOT broker (destructive ops raise before apply,
`arclink_control.py:17105-17112`).

Three corrections are binding: (1) the "dead env var" thread (DRIFT#1 + its RISK +
the VERDICT line) is **struck** — the env var is live (`memory_synthesizer.py:329`);
(2) the ssot.write seam key-shape is **restated** to match the normalizer's real inputs
(`mcp_server.py:1597-1623`); (3) loopback is **reframed** as not a public-webhook
defense under Funnel — HMAC is the gate.

Two net-new MEDIUM federation risks are added and code-confirmed: the armed-window
token hijack/race (NF1) and the unclaimed reindex-consumer race (NF2). One residual
external item (qmd protocol ratification) and two cross-piece catalog scoping notes
remain genuinely unsettleable from this repo.

Federation sign-off: **AGREED-WITH-STANDING-DISAGREEMENTS** — every in-code material
point is reconciled to one truth; the standing items are external/cross-piece and
cannot be decided from CANON-18 code alone.
