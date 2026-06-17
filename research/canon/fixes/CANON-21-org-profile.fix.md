<<<CODEX-FIX-START CANON-21>>>
## CANON-21 — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: python/arclink_org_profile.py, python/arclink_control.py, tests/test_arclink_org_profile.py
TESTS: 3 files pass + targeted plugin bridge pass + py_compile pass; full tests/test_arclink_plugins.py blocked by unrelated tmux permission failure before relevant cases

### Fixed (severity — what — path:line)
- MEDIUM — hardened org-profile secret scanning: `passphrase` is secret-bearing, `cpk_` is no longer a universal placeholder escape, dict keys are scanned for token patterns, and high-entropy benign-key values are blocked with path/checksum exemptions — python/arclink_org_profile.py:74, python/arclink_org_profile.py:218, python/arclink_org_profile.py:295
- MEDIUM — reference `audience` is now enforced in the shared vault render; only `all_agents` non-restricted references render — python/arclink_org_profile.py:355, python/arclink_org_profile.py:1148
- LOW — shared-render reference paths now fail closed for unsafe local paths and unsafe URI schemes, and rendered paths are sanitized to `<vault>`/`<repo>` or withheld — python/arclink_org_profile.py:366, python/arclink_org_profile.py:487, python/arclink_org_profile.py:899
- MEDIUM — apply now serializes through an advisory lock and no longer commits the SQLite mirror before file fan-out; fan-out exceptions roll back the DB revision — python/arclink_org_profile.py:134, python/arclink_org_profile.py:2229, python/arclink_org_profile.py:2305
- MEDIUM — empty org-profile managed payloads now call the existing teardown helper, clearing stale SOUL/identity/context overlays — python/arclink_control.py:18902

### Skipped (risk-accepted / standing / out-of-scope — why)
- Privacy posture of the shipped example: canon labels this a refuted posture/fictional example opt-in, not a code bug; no config example changed.
- Full removal of write-only `org_profile_*` tables: removing the mirror is a DB/public-contract decision, not a surgical bug fix.

### NEEDS-DECISION (ambiguous; left for human)
- Whether org-profile fan-out should include non-`role='user'` or inactive agents; current scope looks like an intentional contract boundary.
- Whether unmatched slice deletion needs a separate audit/event rail beyond the existing apply report; that crosses reporting/notification ownership.

### Cross-piece edits made (if any) + tests added
- Cross-piece edit: python/arclink_control.py only, to clear materialized org-profile state when context is empty.
- Added/updated tests in tests/test_arclink_org_profile.py for secret bypasses, reference audience/path safety, stale overlay clearing, and apply rollback on file fan-out failure.
<<<CODEX-FIX-END CANON-21>>>
