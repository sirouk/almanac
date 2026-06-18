<<<CODEX-D-START>>>
SIGN-OFF: OBJECT(1)
### 1 Owner-scoping
CONFIRM: I found no global name-resolution path for `/agents` or `/agent <name>`. Telegram and Discord derive the public-bot identity from platform user id (`python/arclink_telegram.py:1645`, `python/arclink_discord.py:512`), `_deployment_context` resolves that contact’s session/deployment (`python/arclink_public_bots.py:2596`), and `_deployment_for_session` rejects `active_deployment_id` unless the deployment `user_id` equals the session `user_id` (`python/arclink_public_bots.py:2036`, `python/arclink_public_bots.py:2039`, `python/arclink_public_bots.py:2040`).

CONFIRM: `/agents` gets `user_id` from that deployment/session and calls `_deployments_for_user` (`python/arclink_public_bots.py:4522`, `python/arclink_public_bots.py:4523`), whose SQL is strictly `WHERE user_id = ?` (`python/arclink_public_bots.py:2165`, `python/arclink_public_bots.py:2173`). `/agent` uses the same scoped list (`python/arclink_public_bots.py:4574`) and `_find_agent_deployment` only scans the passed list (`python/arclink_public_bots.py:2279`, `python/arclink_public_bots.py:2288`).

### 2 Switch correctness
CONFIRM: A successful switch persists to the same store the router reads: `_switch_agent_reply` writes `active_deployment_id` into session metadata (`python/arclink_public_bots.py:4589`, `python/arclink_public_bots.py:4592`), `_update_session_metadata` updates `arclink_onboarding_sessions.metadata_json` (`python/arclink_public_bots.py:2557`, `python/arclink_public_bots.py:2564`), and `_deployment_for_session` reads `metadata_json.active_deployment_id` (`python/arclink_public_bots.py:2037`).

CONFIRM: Case-insensitivity works through `command = message.lower()` (`python/arclink_public_bots.py:7184`) plus `_agent_switch_request` (`python/arclink_public_bots.py:1138`, `python/arclink_public_bots.py:1143`). Non-ready owned deployments are not silently routed; matched non-ready rows return `switch_agent_not_ready` (`python/arclink_public_bots.py:4578`, `python/arclink_public_bots.py:4584`).

BUG: Duplicate/ambiguous owned agent names are not handled sanely. `_find_agent_deployment` returns the first alias match with no ambiguity check (`python/arclink_public_bots.py:2288`, `python/arclink_public_bots.py:2291`), and roster buttons encode only `/agent {label}` (`python/arclink_public_bots.py:2688`, `python/arclink_public_bots.py:2690`). I confirmed in memory that two ready owned agents named `Forge` produce one indistinguishable `Take Helm: Forge` command, and pressing it resolves to the first Forge, so the second same-named agent cannot be selected via its button and `/agent Forge` can silently route to the wrong owned agent. This is the ship-blocking objection.

### 3 Roster
CONFIRM: `/agents` is owner-scoped and marks the at-helm agent from the router-selected deployment id (`python/arclink_public_bots.py:4522`, `python/arclink_public_bots.py:4524`). The marker only says `at helm` when the id matches and the status is ready (`python/arclink_public_bots.py:2606`, `python/arclink_public_bots.py:2608`), so a cancelled/stale deployment should not be marked at helm. No-session/no-deployment returns the no-crew path (`python/arclink_public_bots.py:4508`, `python/arclink_public_bots.py:4513`).

BUG: Same duplicate-label issue affects roster correctness: the roster can show two identical names, but the generated helm button cannot uniquely target the non-active one (`python/arclink_public_bots.py:2678`, `python/arclink_public_bots.py:2690`).

### 4 The diff
CONFIRM: The new not-found list does not leak cross-tenant names because it is built from the already owner-scoped `deployments` list (`python/arclink_public_bots.py:4574`) and further filtered to ready statuses (`python/arclink_public_bots.py:4606`, `python/arclink_public_bots.py:4610`). It preserves the existing asserted substring: `That name is not on your ArcLink roster.` (`python/arclink_public_bots.py:4621`).

RISK: Agent names are interpolated into Markdown code spans without escaping (`python/arclink_public_bots.py:4611`, `python/arclink_public_bots.py:4613`). The cleaner only trims, length-checks, and rejects secrets (`python/arclink_onboarding.py:172`, `python/arclink_onboarding.py:180`), so backticks remain possible. Telegram’s converter pairs raw backticks into entities (`python/arclink_public_bots.py:1237`, `python/arclink_public_bots.py:1260`), and Discord interaction replies send `content` without `allowed_mentions` (`python/arclink_discord.py:544`, `python/arclink_discord.py:562`). Escape or plain-render names before wrapping.

### 5 Test
CONFIRM: The new test is not tautological. It reads the real persisted `arclink_onboarding_sessions.metadata_json['active_deployment_id']` (`tests/test_arclink_public_bots.py:2387`, `tests/test_arclink_public_bots.py:2401`), seeds an owned Forge and unowned Rival (`tests/test_arclink_public_bots.py:2428`, `tests/test_arclink_public_bots.py:2454`), proves lowercase and uppercase switches move the stored active id (`tests/test_arclink_public_bots.py:2475`, `tests/test_arclink_public_bots.py:2497`), and proves `/agent Rival` is refused without moving the helm (`tests/test_arclink_public_bots.py:2514`, `tests/test_arclink_public_bots.py:2525`).

CONFIRM: `main()` calls the new test (`tests/test_arclink_public_bots.py:2539`, `tests/test_arclink_public_bots.py:2580`). Full `python3 tests/test_arclink_public_bots.py` could not complete in this read-only sandbox because an older test needs `tempfile.TemporaryDirectory()` and no usable temp dir exists (`tests/test_arclink_public_bots.py:633`). Direct invocation of the new test passed.

RISK: The test does not cover duplicate/ambiguous same-owner names or markup escaping in the not-found valid-name list.

### 6 Other
BLOCK SHIP on duplicate selector handling. Fix by detecting multiple alias matches before persisting, and make roster buttons target a unique stable selector such as deployment id or prefix while displaying the friendly label. No cross-tenant switch/list leak found.
<<<CODEX-D-END>>>
