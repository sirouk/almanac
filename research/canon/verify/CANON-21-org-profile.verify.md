# CANON-21 — Org Profile — ADVERSARIAL VERIFY

Auditor: independent Opus 4.8 skeptic. Method: re-opened every load-bearing file and
re-verified citations at path:line; executed validation/secret-scan code paths; traced
both ends of each cross-piece seam in code.

Verdict up front: **The record is substantially TRUSTWORTHY.** Its core claims
(fail-closed apply, write-only SQLite mirror, allowlist secret scanner, no concurrency
lock, both-ends-verified seams) re-confirmed in code. BUT it contains one materially
over-stated VERDICT claim (privacy "omits restricted fields by default" — the SHIPPED
example does the opposite) and misses three real gaps (dead `clear_materialized_agent_context`,
post-commit file-write divergence, and dict-key secret blindness). Details below.

---

## A. RE-CONFIRMED CLAIMS (refuted=false — independently re-verified in code)

1. **apply_profile is fail-closed.** `arclink_org_profile.py:2083-2091`: re-validates, returns
   `{"applied": False, ...}` before any DB/file write when `not valid`. Re-read; correct.

2. **Write-only SQLite mirror.** Ran `rg "FROM org_profile_"` across the WHOLE tree
   (`*.py *.sh *.ts *.tsx *.js`, not just `python/`) → 0 hits outside `research/`. The
   record's self-check #1 hedged "did not grep bin/web" at medium confidence; I closed that
   gap — there is genuinely no reader anywhere. Tables written at
   `arclink_org_profile.py:1965-2044`, never read. Claim holds; the record under-credited
   its own confidence.

3. **settings seam → CANON-01.** Producer `arclink_org_profile.py:2046-2052` INSERT
   `settings(key,value,updated_at)`; schema owner `arclink_control.py:597-601`
   (`key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL`). Columns match
   exactly. BOTH-ENDS-VERIFIED: yes.

4. **agent_identity.org_profile_person_id seam → CANON-04/08.** Consumer
   `_active_agent_rows` LEFT JOIN `COALESCE(i.org_profile_person_id,'')`
   (`arclink_org_profile.py:2065`); column defined `arclink_control.py:682`, added by
   `_ensure_column` (`:1765`), unique partial index (`:1777-1785`). Producer
   `upsert_agent_identity` (`arclink_control.py:5391,5479`). `_match_person_for_agent`
   matches person_id first (`:1347-1351`). Both ends agree on a string id. Verified.
   Also re-checked JOIN safety: `agent_identity.unix_user` is PRIMARY KEY and
   `agents.unix_user` is UNIQUE (`arclink_control.py:661,680`) — the LEFT JOIN cannot
   fan out duplicate rows. The record didn't claim a JOIN-duplication bug; correct to omit.

5. **Managed-context payload seam → CANON-19.** Producer
   `build_managed_sections_for_agent` returns keys `org-profile`, `user-responsibilities`,
   `team-map`, `org_profile_agent_context`, `org_profile_revision`
   (`arclink_org_profile.py:1587-1591`). Consumer reads each exactly at
   `arclink_control.py:17760-17764`, repacks at `:18543-18547`, and feeds
   `org_profile_agent_context` into `materialize_agent_context` at `:18598-18604`. Key names
   match at both ends. BOTH-ENDS-VERIFIED: yes.

6. **headless-setup seam → CANON-19.** `render_soul_for_identity` returns `(None,None)`
   when no profile/no match (`:1893,:1898`); consumer `arclink_headless_hermes_setup.py:381-383`
   treats falsy SOUL as "fall back to `_render_soul`", and `:510-514` calls
   `identity_values_from_context`. Verified both ends.

7. **academy overlay seam → CANON-17.** `merge_academy_overlay` consumed at
   `arclink_action_worker.py:2087,2094`. Marker-pair logic (`:1745-1752`) only touches the
   academy block. Verified the call; capsule body is adjacent-piece-owned (record's
   "partial" is honest).

8. **builder→ctl subprocess seam → CANON-14/31.** Producer argv
   `[ctl,"org-profile","apply","--file",path,"--yes"]` (`arclink_org_profile_builder.py:623`);
   consumer argparse accepts `org-profile apply --file --yes`
   (`arclink_ctl.py:238-250,249-250`). Verified.

9. **Both examples + builder starter validate cleanly.** Executed `validate_profile(cfg=None)`:
   `example.yaml` valid=True/0/0; `ultimate.example.yaml` valid=True/0/0; builder
   `profile_starter()` valid=True/0/0. Matches the record's VERDICT.

10. **Secret scanner catches gh-token in a non-secret-named field.** Executed
    `_secret_scan_errors({"x":"ghp_..."})` → flagged; `{"notes":["ghp_..."]}` → flagged.
    Record correct.

11. **Path-traversal guard.** Executed `_generated_vault_profile_path_error`: `../../etc`,
    `/abs`, and `ok/../../escape.md` all rejected (`:749-758`). Solid; even the
    no-leading-`..` traversal is caught because `..` appears in `path.parts`.

12. **No concurrency lock around apply.** Re-read `_replace_profile_rows` (`:1961-2053`) and
    `apply_profile` (`:2093-2145`): no `BEGIN IMMEDIATE`, no file lock, no advisory lock.
    Record correct.

13. **fail-closed cpk_ ordering.** `_is_placeholder_secret` runs at `:239` BEFORE the
    key-name check at `:242` — confirmed by reading the body. The record's LOW-severity
    `cpk_` note is real (see C2 for an amplification).

---

## B. CLAIMS CHALLENGED / RE-CALIBRATED (record over- or under-states)

### B1. VERDICT over-claim: "sanitizing renderer that omits restricted fields BY DEFAULT" — REFUTED for the shipped example.
The VERDICT (line 87) and OUTPUT CONTRACT credit the renderer as privacy-safe by default,
citing `_vault_render_allows_people_details` (`:807`). I executed the gate against the
SHIPPED `config/org-profile.example.yaml`:
- `default_people_visibility: org_visible` (`example.yaml:540`)
- vault generated_output `audience: all_agents`, `sensitivity: internal` (`example.yaml:467-470`)
- → `_vault_render_allows_people_details(profile)` returns **True**.

Result: the generated vault file (written world-readable at **mode 0o644**,
`arclink_org_profile.py:2110`) contains the FULL per-person block — display names, role,
GitHub username, repo list, responsibilities, decision authority, and agent
may_do/must_not_do — for ALL people (verified by rendering the `## People And Agents`
section). So the **default shipped example does NOT sanitize**; it publishes person
details to `all_agents`. The "operator_only by default" framing is true only of the
function's *fallback* (`output.get("audience") or "operator_only"`, `:809`) when the
profile is silent — but the example is not silent, it opts in. The record's adversarial
self-check did not test the gate against the shipped example.
(No raw emails leak — the render template simply doesn't emit `contact.email` — so the
"private emails omitted" Privacy footer claim at `:1028` is technically honest.)
Severity of the underlying behavior: MEDIUM (privacy posture of the default example, not a
code bug). The record's *characterization* is what I am refuting.

### B2. `cpk_` bypass under-calibrated (record: LOW). Amplification, not refutation.
Executed `_secret_scan_errors({"api_key":"cpk_ghp_ABCDEF...012345"})` → **BYPASS**. Because
`_is_placeholder_secret` (`:216`, returns True for any `cpk_` prefix) runs at `:239` before
both the secret-named-key check (`:242`) AND the value-pattern check (`:245`), ANY value
beginning `cpk_` — even in a field literally named `api_key`/`token`/`secret`, even if the
remainder is a real gh/sk/AWS token — is silently skipped. The record framed this as
"benign for public keys"; the precise behavior is broader: it is a universal
secret-scan escape hatch keyed on a 4-char prefix. Still operator-self-inflicted, so LOW is
defensible, but the record's description ("treats any cpk_ value as a placeholder and skips
scanning it") is accurate even if it undersells the field-name override.

### B3. CODE-PATH TRACE understates the ctl wrapper. Minor.
The trace (line 46) calls downstream materialization a "separate trigger." In fact
`arclink_ctl.py:963-989` runs `apply_profile` and THEN, inline in the same command, loops
every matched+unmatched agent calling `publish_central_managed_memory` +
`signal_agent_refresh_from_curator` (`:972-978`), which is what ultimately drives
`materialize_agent_context`. So `org-profile apply` is not purely "control-plane + files";
it also kicks managed-memory refresh per agent. Not wrong, but the trace's boundary is
drawn one call too early. INFO.

---

## C. NEW GAPS — neither the record nor prior docs mention these

### C1. HIGH-ish (MEDIUM) — `clear_materialized_agent_context` is DEAD CODE / unwired teardown.
`clear_materialized_agent_context` (`arclink_org_profile.py:1807`) is defined to remove the
SOUL overlay + strip `ORG_PROFILE_IDENTITY_KEYS` from identity JSON + delete the context
state file. `rg clear_materialized_agent_context python/` → **only the definition, no
caller**. Consequence chained with the consumer guard at `arclink_control.py:18600`
(`if isinstance(org_profile_context, dict) and org_profile_context:` — i.e. materialize is
SKIPPED when context is empty): once an agent has received a SOUL org-profile overlay and
identity keys, if that agent later stops matching any person (renamed, person removed,
profile cleared), `apply_profile` deletes only the JSON *slice*
(`arclink_org_profile.py:2122-2124`) — it never clears the agent's `SOUL.md` overlay or
identity JSON, and nothing else calls the teardown. The agent keeps a STALE org-profile
overlay (old role/responsibilities/authority) inside its `<!-- BEGIN/END ARCLINK ORG
PROFILE -->` markers indefinitely. This is a silent stale-authority footgun the record's
"unmatched-agent slice deletion is silent" LOW risk only half-covers (it noted the slice
delete; it missed that the SOUL/identity overlay is never reaped).

### C2. MEDIUM — post-commit file divergence (no atomicity across DB+files).
`_replace_profile_rows` calls `conn.commit()` at `:2053`. AFTER the commit,
`apply_profile` writes `applied.json` (`:2107`), the vault render (`:2110`), and per-agent
slices (`:2116-2145`). If ANY of those file writes raises (disk full, permission,
`_generated_vault_abs_path` ValueError on a hostile path that somehow passed validation,
ENOSPC during fsync), the exception propagates UNCAUGHT, but the SQLite
`settings.org_profile_revision` and all `org_profile_*` rows are ALREADY committed. Because
the authoritative read surface is `applied.json` (record's own thesis), the DB now reports a
revision that `applied.json` does not reflect — and `doctor_profile` compares
`settings_revision` vs `profile_checksum(applied)` (`:2176-2177`) and would surface the
drift, but nothing self-heals and no rollback occurs. The record's concurrency risk is about
*two* applies; this is a single apply that partially fails. Distinct gap.

### C3. LOW — secret scanner never inspects dict KEYS.
Executed `_secret_scan_errors({"ghp_ABCDEF...012345":"note"})` → **NOT FLAGGED**.
`_walk_values` (`:221-230`) yields each value at a path, and `_secret_scan_errors` (`:236`)
`continue`s unless `isinstance(value, str)`; the secret-named-key check only inspects the
LAST path segment of *containing* keys, and the value-pattern check only runs on string
*values*. A secret placed as a YAML mapping key (e.g. under `metadata`/`glossary` objects,
which schema permits via `additionalProperties: true` at `:95,:184`) is persisted to
`applied.json`/SQLite unscanned. Niche but real; extends the record's "allowlist scanner"
MEDIUM.

### C4. INFO — `passphrase` bypass re-confirmed (record self-check #2, promote to RISK).
The record raised this only in ADVERSARIAL SELF-CHECK #2 at "medium-high confidence" but did
NOT promote it into the RISKS list. Executed
`_secret_scan_errors({"passphrase":"Tq9xZ2mWv7Lp0Rb4Kn8Yc3Fd6Hj1Gs5"})` → BYPASS, and
confirmed no `SECRET_KEY_TERM` is a substring of `passphrase` (`password` != `passphrase`).
Real and should be a named RISK, not just a self-check. It is effectively the same root as
the existing MEDIUM "allowlist secret scanner," so no new severity, but the record's RISK
list omits the concrete `passphrase` exemplar.

---

## D. SEAM MISMATCHES
None found. All six both-ends-verified seams (settings, agent_identity.org_profile_person_id,
managed-context payload, headless SOUL/identity, academy overlay, builder→ctl) re-confirmed
with matching key/column names at producer and consumer. The record's seam table is accurate.

---

## E. RISK SEVERITY RE-CALIBRATION
- MEDIUM "Write-only SQLite mirror" — agree (and confirmed tree-wide, stronger than recorded).
- MEDIUM "No concurrency control" — agree; add C2 (post-commit single-apply divergence) under
  the same theme.
- MEDIUM "Allowlist secret scanner" — agree; add C3 (dict keys) and C4 (`passphrase`) as
  concrete instances.
- LOW "cpk_ bypass" — agree LOW, but note field-name override (B2).
- LOW "Unmatched-agent slice deletion silent" — UNDER-SCOPED: the real exposure is C1
  (SOUL/identity overlay never reaped because `clear_materialized_agent_context` is unwired).
  I would raise the combined item to MEDIUM.
- LOW "Scope role='user' active only" — agree.
- The VERDICT's privacy praise — DOWNGRADE (see B1): the shipped example publishes person
  details to all_agents at 0o644.

---

## OVERALL VERDICT
**TRUSTWORTHY WITH CORRECTIONS.** Every cross-piece contract the record marked
both-ends-verified is genuinely both-ends-verified in code; the fail-closed, write-only-mirror,
allowlist-scanner, and no-lock claims are all re-confirmed by reading the actual lines and
executing the relevant code. The record is honest about its own confidence levels. Required
corrections: (1) the VERDICT's "sanitizes by default" framing is refuted by the shipped
example (B1); (2) three unmentioned gaps — dead `clear_materialized_agent_context` leaving
stale SOUL/identity overlays (C1, MEDIUM), post-commit DB/file divergence on partial apply
failure (C2, MEDIUM), and dict-key secret blindness (C3, LOW); (3) the `passphrase` bypass
should be promoted from self-check to a named risk (C4). None of these break the happy path,
matching the record's own conclusion, but C1 and B1 are the two items most worth a Codex pass.
