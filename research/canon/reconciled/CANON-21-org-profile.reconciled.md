# CANON-21 — Org Profile — FEDERATION RECONCILIATION

- **Codex (GPT-5.5 xhigh) SIGN-OFF:** OBJECT(3)
- **Claude Opus 4.8 FINAL ADJUDICATOR FEDERATION SIGN-OFF:** BOTH-MODEL-AGREED
- Method: every disputed/REFUTE/REFINE/new-finding point was re-opened in code by the adjudicator (Read + rg + executed scanner). Code wins over name/comment/prior claim. Codex CONFIRM items where both passes already agreed get a one-line ratification.

All three of Codex's OBJECT points (stale-overlay severity narrowing, privacy-default refutation, reference-`audience` leak) are resolved against the code below and fold cleanly into the Claude record + verify pass. No point remained unsettleable from code. Hence BOTH-MODEL-AGREED.

---

## Resolution table (point | winner | deciding cite)

| Point | Winner | Deciding cite |
|---|---|---|
| `apply_profile` fail-closed before any DB/file write on invalid profile | both | `python/arclink_org_profile.py:2083-2091` (returns `applied:False` before `_replace_profile_rows`) |
| Write-only SQLite mirror — 5 tables written, never read | both | written `:1965-2044`; `rg "(FROM|JOIN) org_profile_(people|roles|teams|relationships|revisions)"` tree-wide → 0 (excl. research/) |
| No apply-level concurrency control | both | commit `:2053`, then file fan-out `:2107-2166`; no lock/`BEGIN IMMEDIATE` in module |
| Allowlist/best-effort secret scanner | both | string-values-only `:235-236`; key-term `:242`; value regex `:245`; `SECRET_KEY_TERMS :71`, `SECRET_VALUE_PATTERNS :84` |
| `cpk_` is a universal scan escape (field-name override) | both (Claude verify B2 amplification holds) | `_is_placeholder_secret` returns True for `cpk_` `:216`, runs at `:239` BEFORE key check `:242` and value check `:245`. Executed: `{"api_key":"cpk_ghp_…"}` → `[]` not flagged |
| Apply fan-out scope = `role='user' AND status='active'` only | both | `_active_agent_rows` `:2069`; refresh signal repeats gate `python/arclink_control.py:18848` |
| Post-commit DB/file divergence on partial single-apply failure (Claude verify C2) | both | DB committed `:2053`; uncaught file writes `:2107`,`:2110`,`:2136`,`:2166`; `doctor_profile` surfaces drift `:2175-2177` but no rollback/self-heal |
| Privacy "sanitizes by default" VERDICT over-claim — REFUTED for shipped example | both (Claude verify B1 + Codex CONFIRM) | gate `_vault_render_allows_people_details` `:807-816` returns True when `audience=all_agents`+`sensitivity∈{public,internal}`+`visibility∈{org_visible,household_visible}`; shipped `config/org-profile.example.yaml:469-470,540` opts into all three → full people block to 0o644 vault doc `:2110` |
| Dict-key secret blindness (Claude verify C3) | both | `_walk_values` keys become path labels only `:221-230`; value regex runs on string values `:236,245`. Executed: `{"ghp_…":"note"}` → `[]` |
| `passphrase` bypass (Claude verify C4) | both | "password" ∈ `SECRET_KEY_TERMS :79` but not substring of "passphrase". Executed `{"passphrase":"<32-char entropy>"}` → `[]` |
| Stale SOUL/identity overlay — REFINE: NOT "stale forever on any unmatch"; only on full-profile teardown / build failure | codex (narrows Claude verify C1) | `clear_materialized_agent_context` defined `:1807`, **0 callers** (rg). BUT unmatched-with-profile → `build_managed_sections_for_agent` `:1577-1585` falls to non-empty `org_baseline_context_for_agent` `:1248-1324` → guard `python/arclink_control.py:18600` passes → `materialize_agent_context` `:1785` `merge_soul_overlay` **replaces** the block `:1705-1707`. Only `load_applied_profile` empty `:1378-1381` → `{}` `:1570` → guard skips → overlay un-reaped |
| Six cross-piece seams both-ends-verified | both | settings `:2046`↔`arclink_control.py:598`; identity `arclink_enrollment_provisioner.py:1819`/`arclink_control.py:5472`↔`:2065`; managed payload `:1586`↔`arclink_control.py:17760`; headless SOUL `:1884`↔`arclink_headless_hermes_setup.py:353`; academy `:1745`↔`arclink_action_worker.py:2087`; builder→ctl `arclink_org_profile_builder.py:623`↔`arclink_ctl.py:238` |

---

## Codex NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (re-verified in code → net-new federation risks)

1. **MEDIUM — reference `audience` is ignored in the shared vault render.** Schema models `audience` enum `all_agents|team_only|operator_only` (default `all_agents`) at `config/org-profile.schema.json:750`; builder preview preserves it at `python/arclink_org_profile.py:594`. But `render_vault_profile`'s reference filter at `:1012-1016` keys ONLY on `sensitivity != "restricted"` — `audience` is never consulted — and emits id/title/type/path verbatim at `:1021` into the 0o644 vault doc. Shipped `config/org-profile.ultimate.example.yaml:1478-1481` has `source-packet` with `audience: team_only`, `sensitivity: internal` → it renders to the all-agents vault doc. Title+path scope-leak (not body), but real. CONFIRMED.

2. **LOW — non-restricted reference paths are not containment-checked for render disclosure.** `resolve_profile_path` `:371` returns absolute paths as-is (no vault/private/repo containment); the only check is an existence test that emits a non-blocking warning `:382-385` (warnings never block: `valid = not errors`, `:445`). The raw path is then rendered verbatim into the all-agents vault doc `:1021`. An operator-authored absolute host path is disclosed. CONFIRMED (narrow: discloses a path string, operator-authored).

### REJECTED
- None. Both Codex new findings hold in code.

---

## Severity changes (from → to, code-supported)

| Risk | From | To | Cite |
|---|---|---|---|
| Unmatched-agent slice deletion / stale overlay (Claude record LOW "slice deletion silent"; Claude verify C1 proposed MEDIUM "stale forever") | record LOW / verify-proposed MEDIUM | **MEDIUM (narrowed mechanism)** — stale SOUL/identity overlay only on FULL profile teardown or `build_managed_sections_for_agent` failure, NOT on ordinary unmatch (baseline overlay overwrites) | dead clear `:1807`; baseline fallback `:1577-1585`,`:1248`; replace `:1705-1707`; empty-skip guard `arclink_control.py:18600`; empty-profile `:1570` |
| `passphrase` bypass (Claude verify C4) | self-check only (record) | **named risk, no new severity** — concrete instance of existing MEDIUM "allowlist secret scanner" | `:79` vs executed `{"passphrase":…}`→`[]` |
| Dict-key secret blindness (Claude verify C3) | unmentioned (record) | **LOW, net-new** instance under allowlist-scanner theme | `:221-230,236`; executed `{"ghp_…":"note"}`→`[]` |
| Post-commit DB/file divergence (Claude verify C2) | unmentioned (record) | **MEDIUM, net-new** under no-atomicity theme (distinct from two-apply concurrency) | commit `:2053` then uncaught writes `:2107+`; doctor surfaces but no rollback `:2175-2177` |
| Reference `audience` ignored (Codex #1) | unmentioned (both) | **MEDIUM, net-new** | `:1012-1016`,`:1021`; schema `:750`; ultimate `:1478-1481` |
| Reference path not containment-checked (Codex #2) | unmentioned (both) | **LOW, net-new** | `:371`,`:382-385`,`:1021` |
| Privacy VERDICT "sanitizes by default" praise | record strength | **DOWNGRADED to refuted-for-shipped-example** (MEDIUM posture, not a code bug) | gate `:807-816`; example `:469-470,540`; 0o644 `:2110` |

No severity change was applied beyond what the code supports.

---

## Standing disagreements
None. Every material point reconciled to a single code-grounded truth. Codex's OBJECT(3) was a request to (a) narrow the stale-overlay mechanism, (b) register the reference-`audience` leak, (c) keep the privacy refutation — all three are satisfied above and agreed by both models.

---

## Final both-model verdict
**The piece provably does its core job, and the federation agrees on its weaknesses.** Re-confirmed in code: fail-closed apply (`:2083-2091`); write-only SQLite mirror (0 readers tree-wide); allowlist/best-effort secret scanner with three concrete escapes (`cpk_` field-name override, dict-key blindness, `passphrase`/unnamed-entropy) all reproduced by executing the scanner; no apply-level lock and no DB↔file atomicity (post-commit single-apply divergence is real, distinct from two-apply concurrency); all six cross-piece seams both-ends key-verified. Two corrections to the original record stand: the "sanitizes restricted fields by default" praise is REFUTED for the shipped example (it opts people detail into the all-agents 0o644 vault doc), and the stale-overlay risk is REAL but NARROWER than first stated — the dead `clear_materialized_agent_context` only leaves a stale overlay on full-profile teardown or a build failure, because ordinary unmatch overwrites the SOUL block with a baseline overlay. Net-new federation risks: reference `audience` ignored in render (MEDIUM), reference path not containment-checked (LOW), post-commit DB/file divergence (MEDIUM), dict-key secret blindness (LOW). FEDERATION SIGN-OFF: BOTH-MODEL-AGREED.
