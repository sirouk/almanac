<<<CODEX-D2-START>>>
SIGN-OFF: OBJECT(1)
### A ambiguity
CONFIRM-FIXED for exact duplicate friendly names: `_switch_agent_reply` now uses plural matches and returns `switch_agent_ambiguous` before switching when `len(matches) > 1` at python/arclink_public_bots.py:4687 and python/arclink_public_bots.py:4693. Single-match and not-found paths remain direct/graceful at python/arclink_public_bots.py:4700 and python/arclink_public_bots.py:4741. Legacy `_find_agent_deployment` callers keep first-match semantics at python/arclink_public_bots.py:2354.

STILL-BROKEN: `/agent <prefix>` is not reliably exact. Prefix is just one alias in the same undifferentiated alias set as labels at python/arclink_public_bots.py:2289 and python/arclink_public_bots.py:2300, and matching is any alias intersection at python/arclink_public_bots.py:2341. If Agent A has prefix `arc-forge` and Agent B is named `Arc Forge`, `/agent arc-forge` returns `switch_agent_ambiguous` instead of selecting Agent A. That violates the claimed unique-selector path.

### B buttons
STILL-BROKEN by the same resolver flaw. Roster buttons encode the prefix selector at python/arclink_public_bots.py:2757, and disambiguation buttons do the same at python/arclink_public_bots.py:4659, but the command can still be ambiguous if another owned agent’s label slug collides with that prefix. I reproduced a roster button `Take Helm: Atlas -> /agent arc-forge` that re-entered `switch_agent_ambiguous`.

No button still intentionally encodes the friendly label for helm switching in the reviewed paths.

### C escaping
CONFIRM-FIXED for the stated metacharacters in /agents and /agent display paths. `_safe_agent_name` substitutes backtick/star/underscore/tilde/pipe at python/arclink_public_bots.py:2239. Roster lines/buttons use safe display at python/arclink_public_bots.py:2747 and python/arclink_public_bots.py:2758. Disambiguation, not-ready, success, and not-found list render safe names at python/arclink_public_bots.py:4653, python/arclink_public_bots.py:4709, python/arclink_public_bots.py:4723, and python/arclink_public_bots.py:4737.

Stored routing state remains raw: `active_agent_label` is set from raw `label` at python/arclink_public_bots.py:4717. Selector matching also still uses raw labels before display escaping, so no selector corruption from over-escaping.

### D owner-scope/regression
CONFIRM-FIXED on owner scope. Switch uses `_deployments_for_user` from the current deployment user at python/arclink_public_bots.py:4686, and `_deployments_for_user` filters `WHERE user_id = ?` at python/arclink_public_bots.py:2171. Active deployment restoration also checks same user at python/arclink_public_bots.py:2039.

NEW-ISSUE is intra-owner prefix/label collision, not cross-owner escape.

### E tests
Targeted new tests passed when run directly. Full `python3 tests/test_arclink_public_bots.py` could not complete in this read-only environment because `tempfile.TemporaryDirectory()` at tests/test_arclink_public_bots.py:633 failed with no usable temp dir before reaching the new tests.

The new tests are wired into `main()` at tests/test_arclink_public_bots.py:2793. They prove duplicate-name disambiguation and simple prefix selection at tests/test_arclink_public_bots.py:2586 and tests/test_arclink_public_bots.py:2607, plus basic escaping at tests/test_arclink_public_bots.py:2719. They do not cover prefix-vs-label slug collision, so the “unique selector” proof is incomplete.

### F other
Ship-block: make selector resolution typed/precedent, e.g. exact `prefix`/`deployment_id` match wins before friendly label aliases, or encode a namespaced selector that cannot collide with user-controlled labels.
<<<CODEX-D2-END>>>
