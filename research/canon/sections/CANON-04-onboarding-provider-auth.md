# CANON-04 — Onboarding & Provider Auth

## PIECE

This piece owns ArcLink's onboarding code, which is **two structurally distinct
state machines** that share a file-name prefix but almost no runtime:

1. **NEW public-bot onboarding** — `python/arclink_onboarding.py` (902 lines). A
   button-led, Stripe-checkout-first session/state machine over two tables
   (`arclink_onboarding_sessions`, `arclink_onboarding_events`). It is the SQL
   engine behind the Captain/Raven public-bot path and the hosted web checkout.
   It does **not** import the other three files, does **not** do provider OAuth,
   does **not** provision Unix users, and does **not** touch Hermes. Its job is:
   create/resume a session keyed on `(channel, channel_identity)`, capture
   identity hints, reserve `arclink_deployments` rows at `entitlement_required`,
   open a Stripe checkout, and (after Stripe clears, driven by an adjacent piece)
   advance the deployment past the entitlement gate to `provisioning_ready`.

2. **OLD curator/"Almanac" onboarding** — `python/arclink_onboarding_flow.py`
   (2548 lines), `python/arclink_onboarding_completion.py` (575 lines),
   `python/arclink_onboarding_provider_auth.py` (520 lines). A free-text intake
   state machine (name → org-profile match → unix-user → purpose → bot platform →
   bot name → model preset → model id → thinking level → operator approval →
   bot token → **provider credential / OAuth** → provisioning) over the legacy
   `agents`/`agent_identity`/legacy-onboarding-session tables
   (`save_onboarding_session`/`start_onboarding_session` in `arclink_control.py`).
   `_provider_auth.py` is the ONLY place real provider auth lives in this piece:
   OpenAI **Codex device-code** flow, Anthropic **Claude Code PKCE OAuth**, and
   Chutes/generic **API-key** setup. `_completion.py` builds the scrub-on-ack
   credential-handoff completion bundle (password reveal + followup links + remote
   Hermes wrapper).

CANON-04's brief says "Chutes OAuth handoff" — **code disagrees**: Chutes is an
**API-key** flow (`auth_flow="api-key"`, `key_env="CHUTES_API_KEY"`,
`arclink_onboarding_provider_auth.py:153-165`), not OAuth. The only OAuth flows in
this piece are Codex (device-code) and Anthropic (PKCE). See DRIFT.

## INPUT CONTRACT (code-verified)

### NEW module (`arclink_onboarding.py`) — all functions take a live `sqlite3.Connection`

- `create_or_resume_arclink_onboarding_session(conn, *, channel, channel_identity, session_id="", email_hint="", display_name_hint="", agent_name="", agent_title="", selected_plan_id="", selected_model_id="", current_step="started", metadata=None, force_new=False)` (`:421`). `channel` validated to `{web,telegram,discord}` via `_clean_channel` (`:192`); blank/unknown → `ArcLinkOnboardingError`. `channel_identity` required (`_clean_identity`, `:199`). Every free-text hint passed through `_reject_secret_material` (`:440-448`). `agent_name`≤40, `agent_title`≤80 chars (`:62-63,:163-171`). Resume key = active session by `(channel, channel_identity)`; for `web` also by `email_hint` (`:451-453`).
- `answer_arclink_onboarding_question(conn, *, session_id, question_key, answer_summary="", email_hint="", ...)` (`:513`). Requires a non-terminal session (`_active_session_or_error`, `:336`). Sets `status='collecting'`, `current_step=question_key`. Each provided hint re-validated by `_reject_secret_material` (`:543`).
- `prepare_arclink_onboarding_deployment(conn, *, session_id, base_domain="", prefix="")` (`:557`). Reserves 1 deployment (or 3 if `selected_plan_id=='scale'`, `_plan_agent_count`, `:219`).
- `open_arclink_onboarding_checkout(conn, *, session_id, stripe_client, price_id, success_url, cancel_url, base_domain="", line_items=None)` (`:645`). `stripe_client` is a duck-typed object that MUST implement `create_checkout_session(**kwargs)` returning a dict with `id`/`url` (seam to CANON-07).
- `sync_arclink_onboarding_after_entitlement(conn, *, session_id, checkout_session_id="", stripe_customer_id="", commit=True)` (`:799`). Returns `bool`. Caller is CANON-07.
- `mark_arclink_onboarding_checkout_{cancelled,expired,failed}`, `cancel_arclink_onboarding_session`, `handoff_arclink_onboarding_channel`, `record_arclink_onboarding_first_agent_contact`, `expire_stale_arclink_onboarding_sessions`, `record_arclink_onboarding_event`.
- Any caller with a `conn` may call these; **there is no auth/identity check inside this module** — authorization is the caller's responsibility (hosted API / public-bot turn engine). Validation is structural only (channel allowlist, char limits, secret rejection, status enum).

### OLD module entrypoint (`arclink_onboarding_flow.py`)

- `process_onboarding_message(cfg, incoming: IncomingMessage, *, validate_bot_token: BotTokenValidator) -> list[OutboundMessage]` (`:1761`). `incoming` carries `platform/chat_id/sender_id/sender_username/sender_display_name/text/reply_to_message_id` (`:138`). Dispatch is a giant `if state == ...` ladder keyed on `session["state"]` (`:1804-2310+`). State transitions persisted via `save_onboarding_session` (CANON-01). Only callers: `arclink_curator_onboarding.py` and `arclink_curator_discord_onboarding.py` (CANON-06) — verified at `python/arclink_curator_onboarding.py:685,770,1098` and `python/arclink_curator_discord_onboarding.py:372`.

### `_provider_auth.py` inputs

- `resolve_provider_setup(cfg, preset, *, model_id="", reasoning_effort="") -> ProviderSetupSpec` (`:106`). Reads `cfg.model_presets[preset]` of shape `"<provider>:<model>"`; raises `ValueError` if missing/malformed.
- `start_codex_device_authorization()` (`:300`), `poll_codex_device_authorization(auth_state)` (`:326`), `start_anthropic_pkce_authorization()` (`:385`), `complete_anthropic_pkce_authorization(auth_state, code_input)` (`:408`), `normalize_api_key_credential(spec, raw_value)` (`:473`), `normalize_anthropic_credential(raw_value)` — **always raises** (`:466`, OAuth-only enforcement).

## OUTPUT CONTRACT (code-verified)

### NEW module — DB writes (all to `arclink_onboarding_sessions` / `arclink_onboarding_events`)

- `create_or_resume...`: INSERT session row at `status='started'`, `checkout_state=''`, `expires_at` = now+24h (`:477-501`); INSERT `started` event (`:502-508`). Resume path returns existing row, back-filling only blank hints (`:454-472`).
- `answer...`: UPDATE `status='collecting'`, `current_step`, hints (`:545`); INSERT `question_answered` event w/ `{question_key, answer_summary}` (`:546-552`).
- `prepare...`: calls `upsert_arclink_user` (CANON-01) and `reserve_arclink_deployment_prefix` / `reserve_generated_arclink_deployment_prefix` (CANON-01) with `status="entitlement_required"` and a `deployment_metadata` dict carrying `onboarding_session_id`, `bundle_*`, theme fields (`:599-635`); UPDATE session `user_id`,`deployment_id` (`:636-641`). **Side effect: writes `arclink_deployments` rows** (owned by CANON-01/08).
- `open...`: calls `stripe_client.create_checkout_session(...)` with `idempotency_key=f"arclink:onboarding:checkout:{session_id}"` and `metadata` keys `arclink_user_id`, `arclink_onboarding_session_id`, `arclink_deployment_id`, `arclink_purchase_kind`, `arclink_plan_id`, `arclink_agent_name`, `arclink_agent_title` (`:664-682`); UPDATE session `status='checkout_open'`,`checkout_session_id`,`checkout_url`,`checkout_state='open'` (`:683-692`); INSERT `checkout_opened` event.
- `sync_arclink_onboarding_after_entitlement`: gated by `arclink_deployment_can_provision` (CANON-01); calls `advance_arclink_entitlement_gate` (deployment → `provisioning_ready`); UPDATE session `status='provisioning_ready'`,`current_step='provisioning_requested'`,`checkout_state='paid'`,`stripe_customer_id` (`:812-821`); INSERTs `payment_success` + `provisioning_requested` events. Returns `False` (no write) if deployment missing or not yet entitled (`:808-810`).
- checkout terminal markers set `status ∈ {payment_cancelled, payment_expired, payment_failed}` and a matching `checkout_state` + event (`:704-796`).
- `record_arclink_onboarding_first_agent_contact`: UPDATE `status='first_contacted'`, `current_step='first_agent_contact'` + `first_agent_contact` event (`:880-902`). **This is the furthest-forward status the NEW machine ever assigns.**

### OLD module outputs

- `process_onboarding_message` returns `list[OutboundMessage]` (chat text + reply markup); persists state via `save_onboarding_session` and, at the credential step, writes provider secrets to disk via `write_onboarding_secret` / `write_onboarding_platform_token_secret` (CANON-01, returns a path string), then calls `request_bootstrap` + `approve_request` (CANON-01/08) inside `begin_onboarding_provisioning` (`:1149-1184`).
- `_provider_auth.py` outputs: `ProviderSetupSpec` dataclass (`.as_dict()` persisted into `answers.provider_setup`); Codex token payload `{access_token, refresh_token, last_refresh, base_url}` (`:374-382`); Anthropic credential JSON `{"kind":"claude_code_oauth","accessToken","refreshToken","expiresAt","scopes"}` (`:456-463`). **Real outbound HTTP** to `auth.openai.com` / `console.anthropic.com` via `http_request` (`:507`).
- `_completion.py` `completion_message_bundle(...)` returns a dict with `full_text` (contains the plaintext shared password), `scrubbed_text`, `followup_text`, telegram/discord reply markup + parse modes (`:440-456`).

## TOUCH POINTS

- **Tables (schema cites in `arclink_control.py`):**
  - `arclink_onboarding_sessions` (`:1309-1332`), CHECK constraint pins the status enum (`:1313`). Unique index on `LOWER(channel),LOWER(channel_identity)` (`:2235`), index on `checkout_session_id` (`:2251`). Columns `agent_name/agent_title/completed_at/expires_at` added via `_ensure_column` (`:2170-2173`).
  - `arclink_onboarding_events` (`:1334-1342`), indices `:2257`,`:2263`.
  - NEW module also writes `arclink_deployments` (via CANON-01 reserve fns) and `arclink_users` (via `upsert_arclink_user`).
  - OLD module writes legacy `agents`/`agent_identity`/onboarding-session tables and `request`/action tables via CANON-01 helpers.
- **Env vars (read indirectly via `cfg`/helpers):** OLD `_completion.py` reads `ENABLE_TAILSCALE_SERVE`, `TAILSCALE_DNS_NAME`, `NEXTCLOUD_TRUSTED_DOMAIN`, `TAILSCALE_SERVE_PORT`, `ENABLE_NEXTCLOUD`, `TAILSCALE_QMD_PATH`, `TAILSCALE_ARCLINK_MCP_PATH`, `ARCLINK_SSOT_NOTION_ROOT_PAGE_URL`/`_SPACE_URL`, `ARCLINK_ORG_NAME` (`arclink_onboarding_completion.py:204-228,:379`). NEW module reads no env directly.
- **Subprocess:** `_completion.py:_repo_ref_contains_path` shells `git -C <repo> cat-file -e` (`:36-51`). NEW module: none.
- **External services:** NEW — Stripe (injected client only; never imports `stripe`). OLD `_provider_auth.py` — direct HTTPS to OpenAI auth + Anthropic OAuth token endpoints (live network).
- **Secrets handling:** NEW module is **secret-hostile by design** — `_reject_secret_material` (`:145-160`) recursively scans both keys (`_SECRET_KEY_RE`) and values (`_PLAINTEXT_SECRET_RE`, matches `sk_live`, `whsec_`, `gh[pousr]_`, `xox[baprs]-`, `ntn_`, telegram `\d{6,}:[a-z0-9_-]{20,}`) and raises before any write. OLD module is secret-bearing: it persists provider keys/OAuth tokens to disk (`write_onboarding_secret`) and reveals a shared password in `_completion.py:411`.
- **Locks/concurrency:** none in this piece; relies on SQLite connection-level transactions. `expire_stale_...` does bulk UPDATEs (`:271-326`).

## CODE-PATH TRACE (NEW path: first contact → provisioning-ready)

1. Public-bot/web caller invokes `create_or_resume_arclink_onboarding_session(conn, channel=..., channel_identity=...)` → `_clean_channel`/`_clean_identity` validate (`arclink_onboarding.py:437-438`) → `expire_stale_...` runs first (`:439`) → INSERT `started` row + `started` event (`:477-509`).
2. Identity capture: `answer_arclink_onboarding_question(..., question_key, agent_name, ...)` → `status='collecting'` + `question_answered` event (`:526-554`).
3. `open_arclink_onboarding_checkout(..., stripe_client, price_id, success_url, cancel_url)` → internally calls `prepare_arclink_onboarding_deployment` (`:656`) which `upsert_arclink_user` + reserves `arclink_deployments` at `entitlement_required` (`:583-635`) → calls `stripe_client.create_checkout_session(...metadata[arclink_onboarding_session_id]...)` (`:664`) → UPDATE `status='checkout_open'`, store `checkout_url` (`:683-692`) → `checkout_opened` event.
4. **(Boundary: leaves this piece.)** User pays; Stripe webhook lands in CANON-07 `arclink_entitlements.py`. It reads `_stripe_onboarding_session_id(obj)` (`arclink_entitlements.py:286`), and on `checkout.session.completed` calls back into this piece: `sync_arclink_onboarding_after_entitlement(conn, session_id=..., checkout_session_id=..., stripe_customer_id=...)` (`arclink_entitlements.py:744`).
5. `sync_arclink_onboarding_after_entitlement` (`arclink_onboarding.py:799`) checks `arclink_deployment_can_provision` (CANON-01, requires entitlement_state ∈ {paid,comp}, `arclink_control.py:3927`) → `advance_arclink_entitlement_gate` flips the deployment `entitlement_required → provisioning_ready` (`arclink_control.py:3931-3962`) → UPDATE session `status='provisioning_ready'` + 2 events → returns `True`.
6. **(Boundary: leaves this piece.)** CANON-08 `arclink_sovereign_worker.py` provisions the pod; on first agent online it calls `record_arclink_onboarding_first_agent_contact(conn, session_id, channel, channel_identity)` (`arclink_sovereign_worker.py:2476`) → session `status='first_contacted'` (`arclink_onboarding.py:880`). End state.

## CODE-PATH TRACE (OLD path: provider auth handoff)

1. `process_onboarding_message` reaches `state=='awaiting-bot-token'` → `validate_bot_token(text)` + `write_onboarding_platform_token_secret` + `resolve_provider_setup(cfg, preset, ...)` → persists `answers.provider_setup = spec.as_dict()`, `state='awaiting-provider-credential'` (`arclink_onboarding_flow.py:2009-2045`).
2. Branch on `spec.auth_flow`: `codex-device` → `start_codex_device_authorization()` (live POST to OpenAI, `_provider_auth.py:300`) → `state='awaiting-provider-browser-auth'`, store device-auth state (`:2051-2069`). `anthropic-credential` → `start_anthropic_pkce_authorization()` builds the `claude.ai/oauth/authorize` URL (`:2070-2079`). API-key (Chutes/generic) handled at `awaiting-provider-credential` (`:2084-2163`): `normalize_api_key_credential` → `write_onboarding_secret` → `begin_onboarding_provisioning`.
3. **(Boundary: leaves this piece.)** For Codex, CANON-08 `arclink_enrollment_provisioner.py:_run_pending_onboarding_provider_authorizations` (`:1635`) reads `answers.provider_setup` via `provider_setup_from_dict` (`:1639`) and `answers.provider_browser_auth`, then calls `poll_codex_device_authorization(browser_auth)` (`_provider_auth.py:326`, live POST). On token, writes `write_onboarding_secret(json.dumps(token_payload))` (`:1671`) and `begin_onboarding_provisioning` (`:1686`).
4. Anthropic completion happens inline in the flow at `awaiting-provider-browser-auth` (`arclink_onboarding_flow.py:2205` → `complete_anthropic_pkce_authorization`).
5. `begin_onboarding_provisioning` (`:1137`) → `request_bootstrap(...auto_provision=True...)` (CANON-01/08) → `approve_request(surface='curator-channel')` → `state='provision-pending'` + `linked_request_id`/`linked_agent_id`.

## CROSS-PIECE CONTRACTS (both ends verified)

1. **NEW→CANON-07 (Stripe checkout):** `open_arclink_onboarding_checkout` calls `stripe_client.create_checkout_session(...)` and reads `checkout["id"]`/`checkout["url"]` (`arclink_onboarding.py:664,688-689`). Both adapters in `arclink_adapters.py` return exactly `{"id":..., "url":...}` (Fake `:42,54`; Live `:128`). Kwargs accepted match (`arclink_adapters.py:22-34,83-95`). **BOTH-ENDS-VERIFIED: yes.**

2. **CANON-07→NEW (entitlement sync):** producer = `arclink_entitlements.py:742-750` passes `session_id` (from Stripe metadata `arclink_onboarding_session_id`, written by NEW at `arclink_onboarding.py:674`), `checkout_session_id`, `stripe_customer_id`, `commit=False`. Consumer = `sync_arclink_onboarding_after_entitlement(conn, *, session_id, checkout_session_id, stripe_customer_id, commit)` (`arclink_onboarding.py:799`). Metadata key string matches on both ends (`arclink_onboarding.py:674` writes `arclink_onboarding_session_id`; `arclink_entitlements.py:289` reads same). **BOTH-ENDS-VERIFIED: yes.**

3. **NEW→CANON-01 (deployment reservation + gate):** `prepare_...` calls `reserve_arclink_deployment_prefix`/`reserve_generated_arclink_deployment_prefix(..., status="entitlement_required", metadata=...)` (`arclink_onboarding.py:614-635`); `sync_...` calls `advance_arclink_entitlement_gate` (`:811`). Consumer signatures `arclink_control.py:3569,3526,3931`; gate transitions `entitlement_required→provisioning_ready` (`:3947-3951`). **BOTH-ENDS-VERIFIED: yes.**

4. **CANON-08→NEW (first contact):** producer = `arclink_sovereign_worker.py:2476` calls `record_arclink_onboarding_first_agent_contact(conn, session_id=str(session["session_id"]), channel=..., channel_identity=...)` for telegram/discord sessions matched by deployment/user (`:2429-2445`). Consumer = `arclink_onboarding.py:880`. **BOTH-ENDS-VERIFIED: yes.**

5. **OLD→CANON-08 (provider_setup + codex device-auth state via session answers):** producer = `arclink_onboarding_flow.py:2033` persists `answers.provider_setup = provider_setup.as_dict()` and `answers.provider_browser_auth = start_codex_device_authorization()` (`:2067`). Consumer = `arclink_enrollment_provisioner.py:1639` `provider_setup_from_dict(answers["provider_setup"])` + `poll_codex_device_authorization(answers["provider_browser_auth"])` (`:1647`). Dict shape round-trips through `ProviderSetupSpec.as_dict()`/`provider_setup_from_dict` (`_provider_auth.py:46,50-69`). **BOTH-ENDS-VERIFIED: yes.**

6. **OLD→CANON-06 (entrypoint):** producer/caller = `arclink_curator_onboarding.py:685` etc. pass `(cfg, incoming, validate_bot_token=...)`; consumer = `process_onboarding_message` (`arclink_onboarding_flow.py:1761`). **BOTH-ENDS-VERIFIED: yes** (signature match confirmed).

7. **OLD→CANON-01/08 (bootstrap request):** `begin_onboarding_provisioning` calls `request_bootstrap` + `approve_request` (`arclink_onboarding_flow.py:1149,1163`; defs `arclink_control.py:10854,11125`). **BOTH-ENDS-VERIFIED: partial** — call args read; I did not exhaustively trace `request_bootstrap`'s full body (owned by CANON-01).

## CODE vs COMMENT/DOC/NAME DRIFT

1. **Brief says "Chutes OAuth handoff" — FALSE.** Chutes is `auth_flow="api-key"` (`arclink_onboarding_provider_auth.py:153-165`). The only OAuth flows are Codex (device-code) and Anthropic (PKCE). There is no Chutes OAuth anywhere in this piece.
2. **Status enum declares `payment_pending`, `paid`, `completed` but the NEW machine never assigns them.** The active set lists `payment_pending`/`paid` (`arclink_onboarding.py:23-33`), terminal set lists `completed` (`:34-43`), and the schema CHECK pins all three (`arclink_control.py:1313`). Grep proves no `_update_session(status="payment_pending"|"paid"|"completed")` exists. `checkout_state='paid'` is a *column value*, not the `status`. The `status="completed"` writes at `arclink_enrollment_provisioner.py:2372`+ are on the **OLD** `save_onboarding_session` (legacy table), not `arclink_onboarding_sessions`. So `completed`/`payment_pending`/`paid` are **dead-but-declared** session statuses for the NEW path; the real terminal-forward status is `first_contacted`.
3. **Prior doc `04-captain-bots-onboarding.md` is accurate on the two-system split** (lines 15-17): confirmed — `_flow.py`/`_completion.py`/`_provider_auth.py` are the OLD curator path, consumed by CANON-06 + CANON-08, undocumented in Captain docs. No refutation; one nuance: the prior doc's section A13 lists `payment_pending`/`paid` as live active statuses without flagging they are never set — I record that here.
4. **`normalize_anthropic_credential` name implies it normalizes; it only raises** (`arclink_onboarding_provider_auth.py:466-470`) — intentional OAuth-only guard, but the name lies about behavior.
5. **`_completion.py` user-agent string `"arclink-curator-onboarding/1.0"`** appears in `_provider_auth.py:431` (Anthropic token POST) — confirms provider-auth belongs to the curator path, reinforcing the system split.

## ADVERSARIAL SELF-CHECK

1. *"`completed` is never set for NEW sessions."* — Falsifiable by any `UPDATE arclink_onboarding_sessions SET status='completed'`. I grepped python and found none; but a raw SQL string assembled dynamically, or a call site outside `python/`, could exist. Confidence: high, not absolute.
2. *"Both Stripe adapters return `{id,url}` and nothing else load-bearing is read."* — NEW reads only `.get("id")`/`.get("url")` (`:688-689`); Fake returns more keys but they're ignored. Falsified only if a Live-mode key were needed downstream — not in this module.
3. *"The NEW module has no internal authz."* — I read every public function; none checks caller identity. Falsifiable if a decorator/wrapper I missed enforces it, but the functions are plain module-level defs.
4. *"`_reject_secret_material` is the only secret gate, and `_update_session` does NOT re-validate."* — `_update_session` (`:344-383`) writes arbitrary allowed fields without calling `_reject_secret_material`; secret rejection only fires at `create/answer/handoff` entry and at `_json()` for metadata. A caller that routes secret-shaped data straight through `_update_session(metadata_json=...)` bypasses scanning unless it went through `_json()`. Worth CODEX confirmation (see RISKS).
5. *"OLD `process_onboarding_message` is reachable in production only via curator channels (CANON-06)."* — Only callers found are the two curator modules. Falsifiable if a bin/ script or test harness invokes it as a live path; I checked `python` + `bin`.

## OPEN FOR CODEX FEDERATION

1. Confirm `payment_pending`/`paid`/`completed` are truly never assigned to `arclink_onboarding_sessions.status` anywhere in the repo (including dynamically-built SQL and tests). If a transition to `completed` is intended on full provisioning success, it is **missing** — sessions appear to remain `first_contacted` forever.
2. Verify the `_update_session` secret-rejection bypass: can any reachable caller pass attacker-controlled secret-shaped data into `email_hint`/`display_name_hint`/`metadata_json` via `_update_session` (e.g. the API metadata UPDATE at `arclink_api_auth.py:1093`) without passing through `_reject_secret_material`/`_json`?
3. Confirm `request_bootstrap`/`approve_request` (CANON-01) actually honor `auto_provision=True` + `surface='curator-channel'` as `begin_onboarding_provisioning` assumes, and that `approve_request` is safe to call with a synthetic operator actor string (`arclink_onboarding_flow.py:1167`).
4. Cross-check the live OAuth endpoints/client-ids in `_provider_auth.py:17-27` against the actual provider APIs (Codex `app_EMoamEEZ73f0CkXaXp7hrann`, Anthropic `9d1c250a-...`) — are these the correct, current public client IDs?

## RISKS (severity-ranked, code-cited)

- **MEDIUM — NEW onboarding has no terminal "completed" transition.** Sessions reach `first_contacted` and stop; `completed` is declared but never set (`arclink_onboarding.py:880` is the furthest state; grep shows no `completed` assignment). Downstream consumers treating `completed` as the success terminal will never see it. `arclink_onboarding.py:34-43`, schema `arclink_control.py:1313`.
- **MEDIUM — secret-rejection is entry-point-only, not centralized at the write.** `_update_session` (`arclink_onboarding.py:344-383`) writes allowed fields with no secret scan; only `create/answer/handoff` and `_json()` enforce `_reject_secret_material`. A future/edge caller routing data straight through `_update_session` (e.g. metadata UPDATEs) could persist secret-shaped material. `arclink_onboarding.py:344`, `arclink_api_auth.py:1093`.
- **MEDIUM — OLD path makes live unauthenticated-by-default outbound HTTP to OpenAI/Anthropic during onboarding.** `start_codex_device_authorization`/`poll_codex_device_authorization`/`complete_anthropic_pkce_authorization` POST to external hosts (`arclink_onboarding_provider_auth.py:300,326,408`). Failure modes are caught and surfaced as chat text, but this is real network egress driven by user input; rate-limiting/abuse controls live in CANON-06, not here.
- **MEDIUM — OLD `_completion.py` emits a plaintext shared password into chat text.** `completion_message_bundle` puts the password into `full_text` (`arclink_onboarding_completion.py:411,423,427,432`); the scrub-on-ack flow is best-effort (depends on the user clicking the ack button and the bot editing the message). If ack never fires, the password remains in chat history. `arclink_onboarding_completion.py:307-456`.
- **LOW — `expire_stale_...` runs on the read path inside `_active_session_or_error`** (`arclink_onboarding.py:337`) and issues bulk UPDATEs on every active-session lookup; on a hot path this is repeated write traffic. Functionally correct (TTL-driven), but a perf/lock consideration under concurrency.
- **LOW — `_active_session_row` builds `IN (?,...)` placeholders from frozenset iteration order but binds `sorted(...)` values** (`arclink_onboarding.py:237-249`). Verified harmless: counts match and `IN` is set-membership, so order is irrelevant. Flagged only because it reads like a bug.
- **INFO — Brief/name drift "Chutes OAuth".** Chutes is API-key, not OAuth (`arclink_onboarding_provider_auth.py:153-165`). Any doc/consumer expecting a Chutes OAuth handoff is wrong.

## VERDICT

This piece **provably does its job for the NEW path**: it is a clean, well-bounded
SQL state machine that creates/resumes sessions, reserves deployments at the
entitlement gate, opens Stripe checkout with a correct idempotency key and metadata
contract, and re-enters from the entitlement webhook to lift the gate — every seam
to CANON-01/07/08 is byte-for-byte verified on both ends (checkout id/url, the
`arclink_onboarding_session_id` metadata key, the entitlement-gate transition, and
the first-contact callback). Its secret-hostile design (`_reject_secret_material`)
is a real load-bearing strength: the public onboarding store cannot hold provider
keys or bot tokens. Real weaknesses: (1) the status enum over-declares
(`payment_pending`/`paid`/`completed` are dead for this path — no session ever
reaches `completed`), so "a completed account" in the brief's framing maps to
`first_contacted`, not `completed`; (2) secret scanning is enforced at entry
points but not centralized at the DB write, leaving `_update_session` as an
unscanned channel. The OLD curator path (`_flow`/`_completion`/`_provider_auth`)
is the only place real provider auth lives — Codex device-code and Anthropic PKCE
OAuth are genuinely implemented with live HTTP — but it is a **separate system**
consumed by CANON-06/08, and the brief's "Chutes OAuth handoff" description is
factually wrong (Chutes is API-key). Both machines are honest about live-proof
gating: validation is deferred to provisioning, and no fake-mode path silently
claims a real provider was reached.
