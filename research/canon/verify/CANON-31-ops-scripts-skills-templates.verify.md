# CANON-31 — Adversarial Verification

Verifier: independent adversarial skeptic. Method: re-opened every load-bearing
citation in the real code; did not trust the section's path:line numbers.

Overall: the record is **substantially trustworthy** on its core claims (exec
seams, MCP tool existence, qmd lock-serialization, pdf-ingest robustness,
systemd ExecStart mapping all re-confirmed in code). It carries one materially
**under-stated risk** (the misnamed teardown is still driven by a live
`ENABLE_TAILSCALE_SERVE=1` deploy gate — a config-vs-behavior contradiction, not
just a naming smell), several **methodology overstatements** (markdown-prose
tool refs counted as "both-ends-verified" code seams; validation guarantee that
only holds on one of two branches), and it **missed 3 fresh gaps** (non-atomic
CONFIG_FILE rewrite, silent forwarder death in qmd-daemon, unvalidated
managed-memory fallback payload).

---

## RE-CONFIRMED CLAIMS (re-opened in code, record was right)

- **Artifact counts.** 12 `SKILL.md` cards + 5 helper scripts under
  `skills/**/scripts/` (git ls-files). Record line 8 accurate.
- **tailscale-nextcloud-serve.sh teardown.** Main body calls
  `tailscale-nextcloud-unserve.sh` + prints "no longer publishes…"
  (tailscale-nextcloud-serve.sh:238-239). DRIFT #1 / MEDIUM risk are real.
- **14 systemd ExecStart lines** all match owned scripts byte-for-byte
  (systemd/user/*.service, re-grepped all 14). Record line 13 / line 67 accurate.
- **qmd-refresh.sh**: `flock 9` (:122-123), endpoint-provider local fallback +
  stderr WARNING (:71-79), 124/137 timeout swallowed as success (:105-108),
  `clear_qmd_embed_force_flag` under `umask 077` (:30-64). Record lines 24,74,93
  accurate.
- **pdf-ingest.py**: required env via `os.environ[...]` KeyError (:21-24);
  `pdf_ingest_manifest` schema (:474-486); `path_within_root` commonpath guard
  (:132-138) + `require_generated_artifact_path` (:147-151); `SAFE_TOOL_ENV_KEYS`
  minimal subprocess env (:41,154-160); `list_pdf_sources` symlink+commonpath
  guard (:506-527). Record lines 15,42,52 accurate.
- **pdf_ingest_manifest single writer CONFIRMED** (record's own SELF-CHECK only
  partially grepped). Repo-wide: only `bin/pdf-ingest.py` has
  CREATE/INSERT/UPDATE (:474,670,733,777). `arclink_mcp_server.py:922` and
  `vault-watch.sh:68` are read-only SELECTs. Record's ownership claim HOLDS;
  OPEN-FOR-CODEX item #2 is now RESOLVED (one writer).
- **vault notify-paths / reload-defs handlers EXIST** (record marked "partial",
  consumer "assumed-present"). Subparsers at arclink_ctl.py:185-188
  (`paths nargs="+"`, `--source default vault-watch`); dispatch at :2240,:2243.
  OPEN-FOR-CODEX item #4 RESOLVED — record under-claimed; seam is fully verifiable.
- **vault-repo-sync / curator-refresh internal subparsers** exist
  (arclink_ctl.py:266-268, dispatch :2655,:2689). Record line 61 accurate.
- **write_managed_memory_stubs** defined at arclink_control.py:18450; defensive
  (`dict(payload)` + `setdefault`, :18473-18519) so missing keys won't KeyError.
- **Notion webhook → ssot-batcher kick**: `_kick_ssot_batcher()`
  (arclink_notion_webhook.py:62) → `systemctl --user start
  arclink-ssot-batcher.service` (:44-48), called :361. ExecStart owned by piece.
  Record line 64 accurate.
- **ssot-batcher exec seam bodies exist**: `process_pending_notion_events`
  (arclink_control.py:19206) + `consume_notion_reindex_queue` (:14821) — but see
  Refutation R1 (adjacent piece mislabel).
- **sync_dashboard_user_passwords output keys** `{scanned,users,updated,skipped,
  missing}` confirmed (bin/sync-dashboard-user-passwords.py:88); password set only
  on hash mismatch (:83-86). Record line 31 accurate.
- **install-arclink-skills.sh** usage (:4-11), 10-skill default list (:14-24),
  hard-fail on missing source/installed SKILL.md (:36-39,:50-53). Record lines
  18,28 accurate.
- **render-quarto.sh** triple no-op gate (:8-20) + `quarto render` (:24);
  **tailscale-notion-webhook-funnel.sh** root (:265), gate (:270), funnel to
  `127.0.0.1:${ARCLINK_NOTION_WEBHOOK_PORT:-8283}` (:290). Records 33,35 accurate.
- **notion-transfer DEFAULT_API_VERSION = `2026-03-11`** (notion-transfer.py:25).
- **All 14 MCP tool names exist** in arclink_mcp_server.py (3 hits each =
  description+schema+dispatch). arclink_rpc_client CLI `--url/--tool/--json-args`
  (:93-95), `mcp_call(url,tool_name,arguments)` (:11). Record line 62 accurate
  on existence (but see R2 on the "used" framing).

---

## REFUTATIONS / OVERSTATEMENTS

### R1 — ssot-batcher exec seam adjacent-piece MISLABELED (and "exist" framing)
Record line 60: "execs `arclink_ssot_batcher.py`, whose
`process_pending_notion_events`/`consume_notion_reindex_queue` exist
(arclink_ssot_batcher.py:7,13-14) … adjacent = CANON-18". CODE: those two names
are **imported** from `arclink_control` at arclink_ssot_batcher.py:7 and merely
**called** at :13-14 — they are NOT defined in the ssot_batcher module. Their
bodies live in `python/arclink_control.py` (:19206,:14821), i.e. the real
consumer of the exec'd module's work is **arclink_control (CANON-01 territory)**,
not CANON-18. The seam is still both-ends-real, but the cited lines are
import/call sites (not definitions) and the adjacent-piece label is wrong.
Refuted: the "exist (…:7,13-14)" phrasing implies the definition was verified at
those lines; it was not. Severity: low (functionally sound, label imprecise).

### R2 — "Every tool used … BOTH-ENDS-VERIFIED: yes" conflates script calls with markdown prose
Record line 62 lists 14 tools as "used" by the skill scripts and claims the
skill→MCP seam is both-ends-verified. CODE: the executable skill scripts only
invoke **5** tools (`rg --tool` over skills/: catalog.vaults, vaults.refresh,
agents.managed-memory, status, notion.search — plus a literal qmd `query` in
run-first-contact.sh). The other 9 (vaults.subscribe, notion.fetch, notion.query,
vault.search-and-fetch, knowledge.search-and-fetch, ssot.read/write,
academy.search-graduates/propose-resource) appear ONLY in `SKILL.md` prose
(instructions to the agent), which the binding method classifies as a CLAIM, not
an executed code path. They all exist in mcp_server, but a markdown sentence
"call X" is not a producer→consumer code seam. Over-stated as both-ends code
verification.

### R3 — "Payload required keys … validated before reuse" only holds on ONE of two branches
Record lines 30,63: run-first-contact.sh validates required keys
(`agent_id,vault-ref,qmd-ref,catalog,subscriptions,vault_path_contract`) at
:90-91 before `write_managed_memory_stubs`. CODE: that validation guards only the
**local-file branch** (:76-94). When `agent_id` is empty or the local managed
payload is missing/invalid, the `else` branch (:98-103) fetches `$managed_file`
from the MCP `agents.managed-memory` tool and passes it **unvalidated** straight
to `write_managed_memory_stubs` (:309-311). So the "validated before reuse"
guarantee is not unconditional. Mitigated only because the consumer uses
`setdefault` (R-confirmed), so it's degraded-data, not a crash. The record's
blanket claim is an overstatement.

### R4 — MEDIUM teardown risk is UNDER-stated: live `ENABLE_TAILSCALE_SERVE=1` deploy gate still drives it
Record RISK (line 92) frames the misnamed serve script as a confusion/dead-code
hazard. CODE: deploy.sh **still calls it** at deploy.sh:5571 and :5713, gated by
`nextcloud_effectively_enabled && [[ "$ENABLE_TAILSCALE_SERVE" == "1" ]]`. So an
operator who sets `ENABLE_TAILSCALE_SERVE=1` (a config flag literally named to
publish Nextcloud over Tailscale Serve) gets the script that **tears Serve down**
and prints "no longer publishes." This is a config-flag-vs-behavior contradiction
(the enable flag now drives a disable), not merely a stale name. health.sh:671-672
even asserts on the "no longer publishes" string, confirming the deprecation is
intentional — but the live `ENABLE_TAILSCALE_SERVE` gate was not retired, so the
operator-facing contract is actively misleading. This RESOLVES OPEN-FOR-CODEX #1
(callers exist) and argues the risk deserves a sharper, env-var-specific framing.

---

## NEW GAPS (neither record nor prior docs mention)

### G1 — qmd-refresh.sh `clear_qmd_embed_force_flag` rewrites CONFIG_FILE non-atomically
qmd-refresh.sh:57 does `cat "$temp" >"$config"` — a truncate-then-write into the
shared CONFIG_FILE, NOT an atomic `mv`/rename. A crash/SIGKILL/disk-full mid-write
leaves CONFIG_FILE truncated or partially written. The `flock 9` (:122-123)
serializes *qmd-refresh* instances, but CONFIG_FILE is read/written by many other
scripts (every `source common.sh`) that do NOT hold fd 9. The record praised the
piece as "correctly lock-serialized" and missed that this particular rewrite is
both non-atomic and only partially lock-protected. Severity: LOW (force-flag
clear is infrequent; corruption window is small but real).

### G2 — qmd-daemon.sh silently keeps running with a dead TCP forwarder
qmd-daemon.sh:83 `wait "$qmd_pid"` waits only on the qmd process, never on the
backgrounded Python forwarder (`proxy_pid`, :75). If the forwarder dies (e.g.
`bind_host:container_port` already in use → `Server((bind_host, listen_port))`
raises at :71 and the python child exits), the trap fires only on qmd exit, so the
parent keeps qmd alive while the container port is silently unreachable. No
liveness check on the forwarder; failure is a silent no-op. The record described
the forwarder + trap but missed this one-sided `wait`. Severity: MEDIUM in
container mode (container clients lose qmd MCP with the unit still "active").

### G3 — qmd-daemon.sh loopback-bump condition omits `QMD_MCP_INTERNAL_PORT` guard
Record line 23 says "When loopback==container it bumps the loopback to
container+20000 (:15-17)". The real guard is
`if [[ "$loopback_port" == "$container_port" && -z "${QMD_MCP_INTERNAL_PORT:-}" ]]`
(:15) — the bump is suppressed when `QMD_MCP_INTERNAL_PORT` is set. An operator
setting that var changes the forwarder topology in a way the record's description
doesn't capture. Severity: INFO (citation/description incompleteness).

### G4 — pdf-ingest.py hard-depends on `arclink_http` import before any env read
pdf-ingest.py:18 `from arclink_http import http_request, parse_json_object`. If
the adjacent-piece `python/` dir is not on PYTHONPATH, the script ImportErrors at
import time — before the env-KeyError the record flags (:21-24). The record's
"requires env or hard-crashes" risk omits the prior import dependency. Severity:
INFO (wrapped path always sets PYTHONPATH).

### G5 — arclink-upgrade-orchestrator SKILL.md is a 12th card not in any default install
12 SKILL.md cards exist; the default install list is 10
(install-arclink-skills.sh:14-24). The record explicitly noted
notion-page-pdf-export is excluded (line 98) but did not note
`arclink-upgrade-orchestrator` is the *other* non-default card. Severity: INFO.

---

## SEAM RE-CHECK SUMMARY
- exec wrapper → python module: re-verified target paths; bodies for ssot-batcher
  live in arclink_control not the exec'd module (R1).
- skill → MCP tools: 5 script-invoked tools are true code seams; 9 are
  prose-only (R2).
- run-first-contact → write_managed_memory_stubs: both ends real; validation
  conditional (R3).
- vault-watch → arclink-ctl vault notify-paths/reload-defs: BOTH ENDS NOW
  VERIFIED (arclink_ctl.py:185-188,2240,2243) — record under-claimed.
- notion-webhook → ssot-batcher unit: both ends real.
- upsert-hermes-mcps → hermes_cli.config: external dep, consumer unverifiable —
  record honest, unchanged.

## VERDICT
TRUSTWORTHY WITH CORRECTIONS. No core functional claim collapsed under
re-verification; the qmd/pdf/skills machinery does what the record says. But: the
tailscale-serve risk is under-stated (live enable-flag drives teardown, R4); two
"both-ends-verified" claims are overstated (R1 mislabel, R2 prose-vs-code); the
validation guarantee is branch-conditional (R3); and three real defects were
missed (non-atomic CONFIG_FILE rewrite G1, silent forwarder death G2,
loopback-bump guard G3). Recommend the record (a) re-scope R2's seam claim to the
5 script-invoked tools, (b) re-label the ssot-batcher adjacent piece, (c) add the
ENABLE_TAILSCALE_SERVE contradiction and G1/G2 to RISKS.
