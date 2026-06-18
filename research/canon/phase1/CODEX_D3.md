<<<CODEX-D3-START>>>
SIGN-OFF: RATIFY
### A precedence
CONFIRM-FIXED. `_exact_unique_selector_matches` compares the raw stripped token case-insensitively only against `prefix`/`deployment_id`, then `_find_agent_deployments` short-circuits before alias matching: `python/arclink_public_bots.py:2324`, `python/arclink_public_bots.py:2341`, `python/arclink_public_bots.py:2346`, `python/arclink_public_bots.py:2370`. Label-slug collisions only run after no exact match: `python/arclink_public_bots.py:2373`.

A DB-bypass cross-field collision can return >1 because `deployment_id` and `LOWER(prefix)` are separately unique, not cross-field unique: `python/arclink_control.py:1073`, `python/arclink_control.py:2035`. `/agent` handles that by disambiguating any `len(matches) > 1`: `python/arclink_public_bots.py:4723`. Normal public deployment IDs are `arcdep_...` while prefixes reject underscores, so prefix==deployment_id is not reachable through canonical onboarding: `python/arclink_onboarding.py:604`, `python/arclink_control.py:3076`.

### B buttons
CONFIRM-FIXED under canonical ID/prefix invariants. Roster buttons encode `_agent_unique_selector` rather than the friendly label: `python/arclink_public_bots.py:2262`, `python/arclink_public_bots.py:2790`. Disambiguation buttons do the same: `python/arclink_public_bots.py:4687`, `python/arclink_public_bots.py:4695`. Replay enters the exact selector path first, so duplicate labels and label-slug collisions no longer make helm buttons ambiguous.

### C friendly-name path
CONFIRM-FIXED. Friendly matching is preserved when no raw exact prefix/id exists: `python/arclink_public_bots.py:2373`. `/agent` now uses plural matches and disambiguates duplicate friendly names instead of first-picking: `python/arclink_public_bots.py:4723`, `python/arclink_public_bots.py:4724`, `python/arclink_public_bots.py:4729`. Single friendly match and not-found remain direct/graceful: `python/arclink_public_bots.py:4736`, `python/arclink_public_bots.py:4755`, `python/arclink_public_bots.py:4777`.

### D regression/owner-scope
No ship-blocking regression found. The changed helper is fed owner-scoped deployment lists: `_deployments_for_user` filters `WHERE user_id = ?`: `python/arclink_public_bots.py:2165`, `python/arclink_public_bots.py:2173`. Switch, retire, and academy callers all build from that owner list: `python/arclink_public_bots.py:3094`, `python/arclink_public_bots.py:4722`, `python/arclink_public_bots.py:5973`, `python/arclink_public_bots.py:6130`, `python/arclink_public_bots.py:6265`, `python/arclink_public_bots.py:6332`, `python/arclink_public_bots.py:6616`. Credential selector paths use separate owner-scoped SQL, not this helper: `python/arclink_public_bots.py:2097`.

Non-blocking hardening note: singular `_find_agent_deployment` still first-picks if its internal match list has >1: `python/arclink_public_bots.py:2384`. That is not reachable for canonical public IDs, but a cross-field DB-bypass collision would be cleaner if rejected there too.

### E tests
Adequate. The new test proves the old failure shape, then drives the public bot handler and persisted helm store, so it is not just helper tautology: `tests/test_arclink_public_bots.py:2667`, `tests/test_arclink_public_bots.py:2735`, `tests/test_arclink_public_bots.py:2745`, `tests/test_arclink_public_bots.py:2751`, `tests/test_arclink_public_bots.py:2760`, `tests/test_arclink_public_bots.py:2775`, `tests/test_arclink_public_bots.py:2793`, `tests/test_arclink_public_bots.py:2804`. It is wired into `main()`: `tests/test_arclink_public_bots.py:2941`.

Ran the three relevant selector tests directly; they pass. Full `tests/test_arclink_public_bots.py` could not complete in this read-only sandbox because Python had no writable temp directory.

### F other
No blocker. The selector-precedence flaw is closed for `/agents` and `/agent`.
<<<CODEX-D3-END>>>
