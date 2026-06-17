<<<CODEX-VERDICT-START CANON-21>>>
## CANON-21 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(3)
ONE-LINE VERDICT: Core record ratifies, but stale-overlay severity needs narrowing, privacy-default praise is refuted, and reference `audience` is ignored in the vault render.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM — `apply_profile` is fail-closed before DB/file writes on invalid profile: `python/arclink_org_profile.py:2083`, `python/arclink_org_profile.py:2084`.
- CONFIRM — CANON §B38 write-only mirror: org tables are created/written at `python/arclink_org_profile.py:1910`, deleted/inserted at `python/arclink_org_profile.py:1965`, and tracked grep found no `(FROM|JOIN) org_profile_*` readers.
- CONFIRM — apply fan-out scope skips operator/curator/non-active agents: `_active_agent_rows` hard-filters `a.role = 'user' AND a.status = 'active'` at `python/arclink_org_profile.py:2069`; refresh signaling repeats that gate at `python/arclink_control.py:18848`.
- CONFIRM — no apply-level concurrency control: DB DELETE/INSERT/commit occurs at `python/arclink_org_profile.py:1965`, `python/arclink_org_profile.py:2053`, then multi-file fan-out at `python/arclink_org_profile.py:2107`; no lock/BEGIN path exists in this module.
- CONFIRM — post-commit DB/file divergence: SQLite is committed at `python/arclink_org_profile.py:2053`; `applied.json`, vault doc, slices, and last-apply are written afterward at `python/arclink_org_profile.py:2107`, `python/arclink_org_profile.py:2110`, `python/arclink_org_profile.py:2136`, `python/arclink_org_profile.py:2166`.
- CONFIRM — allowlist/best-effort secret scanner: it scans string values only at `python/arclink_org_profile.py:235`, checks secret-looking leaf names at `python/arclink_org_profile.py:241`, then known regex families at `python/arclink_org_profile.py:245`; benign-named high-entropy strings can pass.
- CONFIRM — `cpk_` is a universal scan escape before key-name/value checks: `python/arclink_org_profile.py:205`, `python/arclink_org_profile.py:216`, `python/arclink_org_profile.py:239`.
- CONFIRM — dict-key secret blindness: dict keys only become path labels in `_walk_values`; regex checks run on values, not keys: `python/arclink_org_profile.py:221`, `python/arclink_org_profile.py:235`.
- REFINE — stale-overlay risk: `clear_materialized_agent_context` is uncalled except its definition at `python/arclink_org_profile.py:1807`, and empty payloads skip clearing at `python/arclink_control.py:18600`; however normal unmatched apply is not “stale forever” because ctl refreshes unmatched rows at `python/arclink_ctl.py:966` and `build_managed_sections_for_agent` emits a baseline context when no person matches at `python/arclink_org_profile.py:1577`.
- CONFIRM — shipped example refutes “sanitized by default”: example sets vault `audience: all_agents`/`sensitivity: internal` at `config/org-profile.example.yaml:467` and `default_people_visibility: org_visible` at `config/org-profile.example.yaml:540`; the gate then allows full people details at `python/arclink_org_profile.py:807`, rendered at `python/arclink_org_profile.py:940`, into a 0644 vault doc at `python/arclink_org_profile.py:2110`.

### New findings both Claude passes missed (severity + path:line)
- MEDIUM — reference `audience` is ignored in the shared vault render. Schema/builder model `audience` at `config/org-profile.schema.json:750` and preview preserves it at `python/arclink_org_profile.py:594`, but render filters only `sensitivity != restricted` at `python/arclink_org_profile.py:1012` and emits title/path verbatim at `python/arclink_org_profile.py:1021`. Shipped ultimate has `source-packet` as `team_only` + `internal` at `config/org-profile.ultimate.example.yaml:1478`; it still renders to the generated vault doc.
- LOW — non-restricted reference paths are not containment-checked for render disclosure. Absolute paths are accepted by the resolver at `python/arclink_org_profile.py:371`; existing markdown/repo paths merely avoid a warning at `python/arclink_org_profile.py:382`; render emits the raw path at `python/arclink_org_profile.py:1021`.

### Claude citations re-confirmed or corrected
- Reconfirmed seams: settings `python/arclink_org_profile.py:2046` ↔ `python/arclink_control.py:598`; agent identity `python/arclink_enrollment_provisioner.py:1819`/`python/arclink_control.py:5472` ↔ `python/arclink_org_profile.py:2065`; managed payload `python/arclink_org_profile.py:1586` ↔ `python/arclink_control.py:17760`; headless SOUL `python/arclink_org_profile.py:1884` ↔ `python/arclink_headless_hermes_setup.py:353`; Academy overlay `python/arclink_org_profile.py:1745` ↔ `python/arclink_action_worker.py:2087`; builder→ctl `python/arclink_org_profile_builder.py:623` ↔ `python/arclink_ctl.py:238`.
- Corrected: stale-overlay row should say “dead clear causes stale preservation when org-profile context becomes empty or build fails,” not “any agent that stops matching keeps old person authority forever.”
- Corrected: privacy posture is profile-dependent; the shipped example opts into all-agent people detail.

### Residual disagreement with the Claude half (for final reconciliation)
- Add the reference-audience leak to CANON-21 risk register, likely MEDIUM.
- Keep dead `clear_materialized_agent_context`, but narrow the mechanism/severity as above.
- No remaining disagreement on the core happy path: validation, apply, mirror write, vault render, slices, SOUL/identity materialization, and six cross-piece seams are code-confirmed.
<<<CODEX-VERDICT-END CANON-21>>>
