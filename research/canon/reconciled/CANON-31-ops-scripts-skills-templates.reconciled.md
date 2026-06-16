# CANON-31 — Operational & Knowledge-Pipeline Scripts, Skills & Templates — RECONCILED

**Adjudicator:** Claude Opus 4.8 (1M) — final federation reconciliation.
**Method:** Every disputed point re-opened in the real code (Read/rg/sed). Code wins over any name, comment, or prior claim. Codex CONFIRM items where both halves already agree are ratified one-line; REFUTE/REFINE/new-findings re-proved independently.

- **Codex (GPT-5.5 xhigh) SIGN-OFF:** OBJECT(6)
- **Claude verifier verdict:** TRUSTWORTHY WITH CORRECTIONS
- **FEDERATION SIGN-OFF:** BOTH-MODEL-AGREED

Net: no core functional claim collapsed. The qmd/PDF/skills/ops machinery does what the Claude record says. Reconciliation adjusts four record claims (skill→MCP tool count, Tailscale enable-flag framing, ssot-batcher cite/label, token-argv window), promotes two missed defects to federation risks (non-atomic CONFIG_FILE rewrite, silent qmd-daemon forwarder death), and rejects two over-reaches (verifier G4 PYTHONPATH, Codex's vault-watch "neutered late-PDF" finding).

---

## RESOLUTION TABLE (point | winner | deciding cite)

| Point | Winner | Deciding cite (my re-open) |
|---|---|---|
| skill→MCP tools that are *executed* code seams: 14 (record) vs 5 (verifier) vs 8 (codex) | **codex** | Union of `--tool` literals (`run-first-contact.sh:41,48,98,106,266`) + `call_tool` wrapper (`curate-vaults.sh:62,89,93,97,165`; `curate-notion.sh:80,101,140,185`) = 8 ArcLink-MCP tools {catalog.vaults, vaults.refresh, agents.managed-memory, status, vaults.subscribe, notion.search, notion.fetch, notion.query}; +1 qmd `query` probe (`run-first-contact.sh:214`). The other 9 named tools appear only in SKILL.md prose. Verifier's "5" missed the `call_tool` wrapper. |
| managed-memory validation "validated before reuse" (record) — branch-conditional? | **both** (verifier R3 = codex REFINE) | `run-first-contact.sh:76-94` validates required keys only on the local-file branch; `else` (`:98-103`) fetches MCP fallback and passes it **unvalidated** to `write_managed_memory_stubs` (`:299-311`). Consumer `dict(payload)`+`setdefault` (`arclink_control.py:18472,18476…`) → degraded-data, not crash. |
| ssot-batcher seam: "functions exist (ssot_batcher.py:7,13-14), adjacent=CANON-18" | **both** (verifier R1 = codex REFINE) | `arclink_ssot_batcher.py:7` **imports** `consume_notion_reindex_queue, process_pending_notion_events` from `arclink_control`; calls at `:13-14`. Definitions live in `arclink_control.py:14821,:19206` (CANON-01 territory). Cite is import/call, not definition; adjacent label imprecise. Seam still both-ends-real. |
| vault reload-defs / notify-paths seam status: record "partial / assumed-present" | **claude-verifier** (codex CONFIRM agrees) | Subparsers + dispatch exist: `arclink_ctl.py:182-188` (`paths nargs="+"`, `--source` default `vault-watch`), dispatch `:2240-2252`. Producer `vault-watch.sh:222-242`. Record under-claimed; seam fully both-ends-verified. |
| `pdf_ingest_manifest` single writer | **claude+codex agree** | Only `bin/pdf-ingest.py` does CREATE/INSERT/UPDATE/DELETE (`:474,670,733,777,830`). `vault-watch.sh:68-77` and `arclink_mcp_server.py:918-924` are read-only SELECTs. OPEN-FOR-CODEX #2 RESOLVED — one writer. |
| Tailscale-serve risk: naming/dead-code (record) vs live enable-flag drives teardown | **both** (verifier R4 = codex CONFIRM) | `deploy.sh:5570-5571` and `:5712-5713` call `tailscale-nextcloud-serve.sh` gated by `nextcloud_effectively_enabled && ENABLE_TAILSCALE_SERVE==1`; script body `:219-220` exits unless flag==1, then `:234-240` un-serves and prints "no longer publishes." Enable-flag drives a disable. OPEN-FOR-CODEX #1 RESOLVED (callers exist). |
| Endpoint qmd embeddings fall back to local + stderr WARNING | **claude+codex agree** | `qmd-refresh.sh:71-79`. Ratified. |
| 124/137 qmd embed timeout swallowed as success | **claude+codex agree** | `qmd-refresh.sh:105-108` → `return 0`. Ratified. |
| vault-watch fail-open on unreadable PDF manifest | **claude+codex agree** | `vault-watch.sh:78-81` `raise SystemExit(0)` on `sqlite3.Error`. Ratified (MEDIUM as record ranked). |
| qmd-daemon waits only on `qmd_pid`; forwarder death silent | **both** (verifier G2 = codex CONFIRM) → **net-new risk** | `qmd-daemon.sh:75` `proxy_pid="$!"`, `:83` `wait "$qmd_pid"` (proxy never waited); `with Server((bind_host,listen_port))` (:71) raises on port-in-use, child exits, trap fires only on qmd exit. Unit stays active, container port dead. |
| CONFIG_FILE rewrite non-atomic + only partly flock-protected | **verifier G1 = codex re-confirm** → **net-new risk** | `qmd-refresh.sh:57` `cat "$temp" >"$config"` (truncate-then-write, no `mv`). The `flock 9` (`:122`) is taken AFTER `clear_qmd_embed_force_flag` runs; other `source common.sh` readers don't hold fd 9. |
| qmd-daemon loopback-bump guard omits `QMD_MCP_INTERNAL_PORT` | **claude-verifier** (G3) | `qmd-daemon.sh:15` real guard is `[[ "$loopback_port"=="$container_port" && -z "${QMD_MCP_INTERNAL_PORT:-}" ]]`. Record line 23 description incomplete. INFO. |
| verifier G4: pdf-ingest "hard-depends on arclink_http import before env, ImportErrors if python/ not on PYTHONPATH" | **codex** (REJECTS the gap framing) | `pdf-ingest.py:16` `sys.path.insert(0, .../python)` runs BEFORE `from arclink_http import …` (`:18`). Script self-bootstraps the path; no external PYTHONPATH dependency. Only depends on the in-repo module existing. Overstated → INFO at most. |
| token-on-argv exposure window: "sub-second heredoc" (record) | **codex** (sharpens record LOW) | Heredoc `auth_payload` (`curate-vaults.sh:64-72`) is sub-second, BUT its JSON output is passed as `--json-args` to `arclink_rpc_client.py` (`:62`), whose argv carries the token for the HTTP-call lifetime (timeout=20s, `arclink_rpc_client.py:26`). `--json-args-file` exists "for secret-bearing payloads" (`:91-95`) and is unused. Window longer than record stated. |
| S6 fleet-probe-wrapper seam (producer-subset + consumer-fallback) | **codex CONFIRM** (accurate) | Wrapper emits `hardware_summary.vcpu_cores` (`arclink-fleet-probe-wrapper:60-67`), never top-level `capacity_slots`/`observed_load`; consumer falls back `payload.get("capacity_slots") or hardware.get("vcpu_cores") …` and `payload.get("observed_load") or _active_placement_count(…)` (`arclink_fleet_inventory_worker.py:351,354`). Seam tolerant by design. INFO (and arguably outside CANON-31 core scope). |
| qmd version comment drift (mcp_server says 2.5.2, pin is 2.5.3) | **codex** (accurate) | `arclink_mcp_server.py:73` comment "qmd 2.5.2"; `config/pins.json:56` `"version":"2.5.3"`. Protocol constant `MCP_PROTOCOL_VERSION="2025-03-26"` (:75) unchanged. Stale comment text only. INFO. |
| 12 SKILL.md cards; 10-card default install | **claude+codex+verifier agree** | `ls skills/*/SKILL.md` = 12; default list `install-arclink-skills.sh:14-25` = 10. Non-default: `notion-page-pdf-export` (record line 98) + `arclink-upgrade-orchestrator` (verifier G5). INFO. |
| upsert-hermes-mcps → `hermes_cli.config.save_config` atomicity | **claude+codex agree** | External pinned dep, absent from repo. BEV=no. Unresolvable from this checkout (see Standing Disagreements §). |

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (re-verified true in code → net-new federation risk)
- **LOW — token-argv exposure longer than record stated; `--json-args-file` available and unused.** Token-bearing JSON reaches `arclink_rpc_client.py` argv (`--json-args`) and persists for the HTTP-call lifetime (timeout 20s), not just the sub-second heredoc. Safer `--json-args-file` exists. `curate-vaults.sh:62-72`; `run-first-contact.sh:41-46`; `arclink_rpc_client.py:26,91-95`. (Sharpens record's existing LOW; severity unchanged.)
- **LOW — `notion-page-pdf-export.py` silent overwrite on slug collision.** De-dupe by page id (`seen` set, `:286-288`); output path is only `out_dir/f"{slug}.pdf"` (`:289`). Two distinct pages sharing a slug → second silently overwrites first. `:263-289,:303-305`. Net-new (record/verifier never noted it). Bounded: notion-page-pdf-export is operator-enabled, non-default, chromium-gated.

### REJECTED (does not hold in code)
- **Codex finding #2 — vault-watch post-refresh late-PDF check "effectively neutered."** REJECTED. `preserve_pdf_status_change_summary` (`vault-watch.sh:147`) forces `qmd_refresh_needed=False` (`:165`) ONLY when `delta_count(current)==0 AND delta_count(previous)!=0` — i.e. the post-refresh pass found NO new changes (the prior pass's changes were already indexed by the intervening refresh; forcing False is correct). A genuine late change (`delta_count(current)!=0`) makes the function `raise SystemExit(1)` (`:147`, no-op), leaving `qmd_refresh_needed` = pdf-ingest's computed value (True if created/updated/removed, `pdf-ingest.py:834`), so `run_qmd_refresh` runs (`vault-watch.sh:455-458`). Late changes are NOT lost. Codex's "can wait for the next event/timer" does not hold.

---

## SEVERITY CHANGES (only where code supports it)
| Risk | From | To | Cite |
|---|---|---|---|
| Misnamed Tailscale teardown | MEDIUM (naming/dead-code) | MEDIUM (re-framed: live `ENABLE_TAILSCALE_SERVE=1` enable-flag actively drives teardown) | `deploy.sh:5570-5571,5712-5713`; `tailscale-nextcloud-serve.sh:219-240` |
| qmd-daemon dead forwarder | (absent from record) | MEDIUM in container mode | `qmd-daemon.sh:75,83,71` |
| Non-atomic CONFIG_FILE rewrite | (absent from record) | LOW | `qmd-refresh.sh:57,122` |
| token-argv exposure | LOW (sub-second) | LOW (window = rpc client HTTP lifetime ≤20s) | `curate-vaults.sh:62`; `arclink_rpc_client.py:26` |
| notion-page-pdf-export slug overwrite | (absent) | LOW | `notion-page-pdf-export.py:286-289` |
| verifier G4 pdf-ingest import dependency | (proposed gap) | INFO (downgraded; self-inserts path) | `pdf-ingest.py:16-18` |

No upward change to any core-machinery severity; the qmd lock-serialization, pdf-ingest robustness, exec-seam and skill→MCP-existence claims all held.

---

## STANDING DISAGREEMENTS (cannot be settled from this checkout)
- **`hermes_cli.config.save_config` atomicity.** Both models agree: the consumer is an external pinned Hermes package not vendored in this repo/env. Producer call shape verified (`upsert-hermes-mcps.sh:43-57`); the upstream write semantics (atomic rename vs truncate) cannot be read here. Seam BEV=no until the pinned Hermes source is opened. This is a genuine evidence-availability gap, not a model disagreement — both halves and this adjudicator concur it is unresolvable from the checkout. (Recorded for completeness; it does NOT block BOTH-MODEL-AGREED because neither model asserts a contradicting claim about it.)

---

## FINAL BOTH-MODEL VERDICT
**BOTH-MODEL-AGREED.** Every material disputed point reconciled to one code-grounded truth:
- skill→MCP executed seam = **8 ArcLink-MCP tools** (codex), remaining 9 are SKILL.md prose/claims; qmd `query` is a 9th (separate qmd MCP).
- managed-memory validation is **branch-conditional** (degraded-data not crash, via consumer `setdefault`).
- ssot-batcher cite is **import/call**, adjacent piece is **arclink_control (CANON-01)**, not CANON-18; seam still both-ends-real.
- Tailscale serve is an **active enable-flag-vs-behavior contradiction** (MEDIUM), not mere naming drift.
- Two **net-new federation risks** promoted: silent qmd-daemon forwarder death (MEDIUM/container), non-atomic CONFIG_FILE rewrite (LOW). One **net-new LOW**: notion-page-pdf-export slug overwrite.
- verifier G4 (PYTHONPATH) and Codex's vault-watch "neutered late-PDF" finding both **REJECTED** on code.
- The only residual is the external `hermes_cli.config` atomicity (evidence-unavailable, non-contradictory) — does not amount to a standing model disagreement.

The piece provably does its job; the consolidated record stands with the corrections above folded in.
