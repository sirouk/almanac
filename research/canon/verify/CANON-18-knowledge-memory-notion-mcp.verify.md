# CANON-18 — Knowledge / Memory / Notion / MCP — ADVERSARIAL VERIFICATION

Verifier: independent Opus 4.8 skeptic. Method: re-opened every CANON-18 file and the
adjacent control-plane seams; verified each load-bearing citation at path:line. Code wins
over comments/docstrings/prior-doc.

Overall: the record is **mostly trustworthy and unusually well-cited** (its line numbers
are exact in nearly every spot I checked), BUT it contains **one materially false DRIFT/RISK
claim** (the "dead env var") and several seam-description imprecisions. I also resolved two of
its own OPEN-FOR-CODEX items in code (broker destructive-op rejection: CONFIRMED fail-closed).

---

## REFUTATIONS (record claim is WRONG)

### R1 — REFUTED: "ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES is exported but never read / dead"
Record DRIFT #1 (lines 137-140, 274-278), RISK "LOW — exported env ... is dead" (363-364),
and VERDICT "one exported env var is dead" (382).

The env var **IS read and live**. `arclink_memory_synthesizer.py:329-334`:
```
max_hash_bytes = _int_env(
    "ARCLINK_MEMORY_SYNTH_MAX_CONTENT_HASH_BYTES",
    DEFAULT_MAX_CONTENT_HASH_BYTES,
    minimum=0, maximum=256*1024*1024,
)
if max_hash_bytes and stat.st_size > max_hash_bytes:
    return ""
```
The auditor only grepped `load_settings` and missed `_file_content_hash`. Setting the env var
DOES change the cap (clamped 0..256 MiB). The constant `DEFAULT_MAX_CONTENT_HASH_BYTES` is only
the default. The drift claim, the OPEN/RISK item, and the verdict line are all refuted by
`arclink_memory_synthesizer.py:329`. This is the most serious error in the record.

### R2 — REFUTED (partial): contract #5 "both-ends" consumed-key shape is wrong
Record contract #5 / OPEN #1 (lines 249-250, 332-335): claims `_normalize_ssot_write_result`
consumes broker keys `final_state`,`target_id`,`url`,`id`.

Actual `_normalize_ssot_write_result` (`arclink_mcp_server.py:1605-1623`) reads:
`applied`/`queued`/`approval_required`/`status` (via `_ssot_final_state` `:1597`) and a NESTED
`notion_result` dict's `url`/`id`/`object` (`:1608-1622`). It does NOT read top-level
`target_id` or top-level `url`/`id`. `target_id` is read by the *caller* at
`arclink_mcp_server.py:2682` (`result.get("target_id")`), not by the normalizer. The record
conflated the normalizer's inputs with the caller's downstream reads. Seam description is
imprecise; refuted as stated.

---

## CONFIRMATIONS (independently re-verified in code)

- C1 — Webhook do_POST flow: loopback (`notion_webhook.py:312`), path `/notion/webhook`
  (`:314`), Content-Length parse + bounds 256 KiB (`:318-323`), JSON (`:327`),
  verification-token handshake branch (`:339-342`), stored-token 412 (`:345-346`), HMAC verify
  + 403 (`:348-350`), event_id 400 (`:354-356`), `store_notion_event` (`:357`), 200 THEN
  `_kick_ssot_batcher()` (`:360-361`). All exact.
- C2 — Token state machine: 409 on already-stored (`:210-219`), 412 if not armed
  (`:220-230`), TTL floor 60s (`:110`), `mark_verification_token_verified` raises if no token
  (`:254-255`). CONFIRMED fail-closed against secret overwrite on shared host.
- C3 — `notion_verify_signature` = `"sha256="+HMAC-SHA256` with `hmac.compare_digest`
  (`arclink_control.py:12135-12141`). Constant-time, correct arg order. CONFIRMED.
- C4 — `store_notion_event` = INSERT OR IGNORE into `notion_webhook_events`
  (`arclink_control.py:12151-12158`). CONFIRMED.
- C5 — Contract #1 (webhook->systemd): argv `["systemctl","--user","--no-block","start",
  "arclink-ssot-batcher.service"]` (`notion_webhook.py:42-49`) vs unit
  `ExecStart=%h/arclink/bin/arclink-ssot-batcher.sh` (systemd/user/arclink-ssot-batcher.service:6).
  Unit name matches. CONFIRMED both ends.
- C6 — Contract #2 (batcher->control): `process_pending_notion_events(conn)` (def at
  `arclink_control.py:19206`) then `consume_notion_reindex_queue(conn, cfg, actor="ssot-batcher")`
  (def at `:14821`). `ssot_batcher.py:13-14`. Arg shapes match. CONFIRMED.
- C7 — Contract #4/#8 (ctl seams): `arclink_ctl.py` imports the four token funcs (`:26-29`) +
  handshake/preflight (`:19-20`) and calls them (`:2697,2715,2729,2744,2753,2773`). CONFIRMED.
- C8 — Contract #7 (notion_ssot client -> control imports): names/keyword-only sigs match.
  `DEFAULT_NOTION_API_VERSION="2026-03-11"` (`notion_ssot.py:11`). CONFIRMED.
- C9 — `run_notion_ssot_no_secret_proof`: proof_mode validated to {fake,authorized_live}
  (`:1096-1097`); fake REQUIRES injected urlopen_fn (`:1098-1100`); token required
  (`:1102-1104`); never returns raw token; returns `{ok,model:"brokered_shared_root",proof_mode,
  token_ref_status,api_version,checks}` (`:1198-1205`). CONFIRMED.
- C10 — `authorized_live` defaults to `request.urlopen` and runs a live root-page READ
  (`notion_ssot.py:1101,1120`) even with `allow_live_mutation=False`. CONFIRMED (the write
  preflight is separately gated at `:1139-1147`). Record's MEDIUM risk is accurate.
- C11 — MCP: loopback-first do_POST (`:1745`), `/mcp` only (`:1747`), body bound
  `ARCLINK_MCP_MAX_REQUEST_BYTES` 1 MiB default capped 16 MiB (`:1650-1655`), per-tool
  `validate_token` (`:2667`) / `_require_operator` (`:1882`) / bootstrap source gate
  (`:1858`) + optional Tailscale identity (`:1863`, env-gated `:1873`). JSON-RPC errors on HTTP
  200 with `X-ArcLink-MCP-Error-Status` (`:1718-1721`). Health BEHIND loopback (`:1727-1742`).
  Success result shape `{content:[{type:text,text:json}],structuredContent:result}`
  (`:1835-1838`). CONFIRMED.
- C12 — memory-synth: `flock(LOCK_EX)` whole run (`:1695-1696`); `_write_status` strips
  api_key/authorization/token/secret/password (`:1673-1679`); dedupe on
  signature+prompt_version+model (`:1734-1742`); failure-backoff only when source unchanged
  (`:1743-1754`); unsafe-output filter blanks summary + inject=false (`:1429-1433`,
  patterns `:95-101`); changed>0 -> queue_notification brief-fanout + immediate consume unless
  `ARCLINK_MEMORY_SYNTH_CONSUME_FANOUT=0` (`:1826,1844`); Academy markers (`:1871`). Schema
  `memory_synthesis_cards` (`arclink_control.py:944-960`), UNIQUE index (`:1848`). CONFIRMED.
- C13 — RESOLVES record OPEN #1 / self-check #3: `enqueue_ssot_write`
  (`arclink_control.py:17093`) IS fail-closed: `if op in SSOT_FORBIDDEN_OPERATIONS: raise
  PermissionError` (`:17105-17108`) AND strict allowlist `if op not in SSOT_WRITE_OPERATIONS:
  raise ValueError` (`:17109-17112`). `operation="trash"` cannot reach the broker. The record's
  feared falsifier does not exist. CONFIRMED fail-closed.

---

## NEW GAPS (neither record nor prior docs flagged)

### G1 — MEDIUM: loopback "enforcement" on the webhook is NOT a defense under its intended Funnel deployment
The webhook is meant to be exposed via Tailscale Funnel. `bin/tailscale-notion-webhook-funnel.sh`
proxies to `http://127.0.0.1:${ARCLINK_NOTION_WEBHOOK_PORT:-8283}` (lines 175/231). When a
genuinely external Notion request arrives via the funnel proxy, `self.client_address[0]` is
`127.0.0.1`, so `backend_client_allowed` (`arclink_control.py:7628-7632`) returns True for ALL
funnel traffic. The record's verdict (line 378) credits "the webhook enforces loopback" as a
security property; under the deployed Funnel path that gate passes for the entire internet. The
real gate against forged events is the HMAC signature + token state machine (which the record
also credits). Severity: MEDIUM because the record over-states loopback as a defense; the actual
forgery defense (HMAC) does hold, so this is a framing/severity error, not an exploitable hole.
Cite: `bin/tailscale-notion-webhook-funnel.sh:175`, `arclink_control.py:7628`,
`arclink_notion_webhook.py:289-293`.

### G2 — LOW: setting MAX_CONTENT_HASH_BYTES=0 silently DISABLES the content-hash cap
Because `_int_env` has `minimum=0` and the guard is `if max_hash_bytes and st_size > ...`
(`arclink_memory_synthesizer.py:333,335`), a value of `0` makes `max_hash_bytes` falsy and the
size check is skipped entirely — the synth will sha256 files of ANY size (the only remaining
guard is the 2 MB cap in `_read_file_snippet:316`, which limits the *snippet* but NOT the hash
read at `:338-340`). This is the opposite of the record's "dead/hardcoded 8 MiB cap" claim: the
cap is not only live, it is operator-defeatable to "unbounded". Cite:
`arclink_memory_synthesizer.py:329-340`.

### G3 — LOW: stale comment couples MCP protocol to qmd 2.5.2, but the pin is 2.5.3
`arclink_mcp_server.py:71-75` comment: "qmd 2.5.2 speaks 2025-03-26 ... bump it together with any
qmd upgrade after verifying the pinned qmd's MCP handshake." But `config/pins.json:57` pins qmd
at `2.5.3`. The qmd upgrade (commit 5aca64d) bumped the pin WITHOUT updating this comment or
re-verifying the handshake per the comment's own instruction. The record cited this comment as
near-authoritative ("qmd 2.5.2 speaks") and did not catch the drift. The protocol-version
coupling (contract #6) remains UNVERIFIED against the actual pinned qmd. Cite:
`arclink_mcp_server.py:73` vs `config/pins.json:57`.

### G4 — LOW: source_ip spoofing surface in MCP bootstrap/status gating (env-gated)
`_request_source_ip` (`arclink_mcp_server.py:1847-1856`) lets a loopback caller override the
source IP via `arguments["source_ip"]` when `ARCLINK_ALLOW_LOOPBACK_SOURCE_IP_OVERRIDE=1`. That
declared IP then feeds `_ensure_bootstrap_source_allowed` (`:1858`) AND the `bootstrap.status`
capability match `_match_status_request` (`:1900-1902`), which is the only gate on retrieving a
bootstrap token "once". With the override on, a loopback caller can both (a) claim any tailnet
IP and (b) satisfy the source-IP capability by declaring the original request's IP. Gated behind
an env var defaulting to "0", so not a default-config hole, but the record's auth section does
not mention this TOCTOU/capability surface. Cite: `arclink_mcp_server.py:1847-1856,1889-1903`.

### G5 — INFO: `_qmd_query_arguments` payload also emits a clamped `limit` key (1..5)
Contract #6's documented producer shape omits `limit` (`arclink_mcp_server.py:753`,
clamp `:735`). Minor incompleteness of the seam contract description.

---

## SEAM MISMATCHES (summary)
- Contract #5 consumed-key shape: see R2. The normalizer reads applied/queued/approval_required/
  status + nested notion_result{url,id,object}, NOT top-level final_state/target_id/url/id.
- Contract #6 (qmd): producer-only; protocol-version coupling is an UNVERIFIED + now-STALE
  comment (G3). Record correctly flagged "both-ends: no" but cited the stale 2.5.2 figure.

## RISK RE-CALIBRATION
- Record "LOW — env var is dead": REMOVE — false (R1). Replace with G2 (cap is
  operator-defeatable to unbounded).
- Record "LOW — /health pre-auth": keep LOW for presence-leak, but elevate the underlying issue
  to MEDIUM per G1 (loopback is not a defense behind Funnel; HMAC is the real gate).
- Record MEDIUM (timer-only drain) and MEDIUM (authorized_live live egress): CONFIRMED accurate.

## VERDICT
The record is **largely trustworthy** on behavior and exceptionally precise on citations, and its
two biggest cautions (timer-only drain; authorized_live live egress) are real and correctly
rated. However it must NOT be accepted as-is: DRIFT #1 / the "dead env var" risk / the verdict's
"one exported env var is dead" are **factually wrong** (R1, refuted at `:329`), and contract #5's
both-ends key shape is mis-described (R2). It also missed that loopback is not a real defense for
the Funnel-deployed webhook (G1), that the hash cap is operator-defeatable to unbounded (G2), and
that the qmd protocol comment is stale vs the pin (G3). I independently CONFIRMED the broker is
fail-closed on destructive ops (C13), resolving the record's own largest open question in its
favor. Net: trustworthy for the strengths it claims, but the "dead env var" thread must be struck
and three new gaps folded in before this CANON section is treated as ground truth.
