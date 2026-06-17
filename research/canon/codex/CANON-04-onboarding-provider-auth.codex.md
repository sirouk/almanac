<<<CODEX-VERDICT-START CANON-04>>>
## CANON-04 — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: OBJECT(4)
ONE-LINE VERDICT: Mostly ratified, but the webhook HIGH is mechanistically wrong as written: code commits mid-webhook, then fails/replays; it does not roll the paid entitlement back.

### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- CONFIRM: Chutes is API-key, not OAuth: `auth_flow="api-key"`, `key_env="CHUTES_API_KEY"`; OAuth paths are Codex device and Anthropic PKCE. `python/arclink_onboarding_provider_auth.py:153-165`, `python/arclink_onboarding_provider_auth.py:300`, `python/arclink_onboarding_provider_auth.py:385`
- CONFIRM: “public onboarding store cannot hold provider keys” is false; local regex misses modern OpenAI/Anthropic/Chutes/AWS key shapes, and hints are stored. `python/arclink_onboarding.py:116-126`, `python/arclink_onboarding.py:440-449`, `python/arclink_onboarding.py:490-496`
- CONFIRM: `arclink_api_auth.py:1093` is not the cited bypass; it serializes through local `_json()` → `json_dumps_safe()` → `reject_secret_material()`. `python/arclink_api_auth.py:221-222`, `python/arclink_api_auth.py:1092-1095`, `python/arclink_boundary.py:65-73`
- CONFIRM: `payment_pending` / `paid` / `completed` are declared but not assigned by the NEW machine; live forward writes are `provisioning_ready` and `first_contacted`. `python/arclink_onboarding.py:23-43`, `python/arclink_control.py:1313`, `python/arclink_onboarding.py:812-820`, `python/arclink_onboarding.py:887-892`
- REFINE: CANON HIGH webhook wedge is real, but not “entitlement rolled back.” `sync_arclink_onboarding_after_entitlement()` calls `_active_session_or_error()`, which calls `expire_stale_arclink_onboarding_sessions(commit=True)` and commits inside the webhook transaction before terminal-session raise; the event is then marked failed/replayable. `python/arclink_entitlements.py:526`, `python/arclink_entitlements.py:724-750`, `python/arclink_onboarding.py:271`, `python/arclink_onboarding.py:324-340`, `python/arclink_entitlements.py:799-809`
- REFINE: `_update_session()` has no centralized secret scan, but it is private and repo-visible calls are intra-module; downgrade the “DB-write bypass” risk unless a reachable caller is found. The real secret risk is regex coverage. `python/arclink_onboarding.py:344-383`, `python/arclink_onboarding.py:471`, `python/arclink_onboarding.py:545`, `python/arclink_onboarding.py:887`
- CONFIRM: OLD path performs live outbound HTTP to OpenAI/Anthropic during onboarding. `python/arclink_onboarding_provider_auth.py:300-305`, `python/arclink_onboarding_provider_auth.py:335-364`, `python/arclink_onboarding_provider_auth.py:419-432`, `python/arclink_onboarding_provider_auth.py:507-515`
- CONFIRM: OLD completion emits plaintext shared password into chat text before scrub-ack. `python/arclink_onboarding_completion.py:411-432`, `python/arclink_onboarding_completion.py:440-456`
- CONFIRM: `sync_arclink_onboarding_after_entitlement()` can silently no-op; caller ignores its boolean. `python/arclink_onboarding.py:807-810`, `python/arclink_entitlements.py:742-750`
- CONFIRM: first-agent contact has no terminal guard and can resurrect expired sessions into active `first_contacted`. `python/arclink_onboarding.py:880-902`, `python/arclink_control.py:2237-2245`, `python/arclink_sovereign_worker.py:2429-2481`
- CONFIRM: Stripe seam shape holds: onboarding writes `arclink_onboarding_session_id`, webhook reads it, adapters return `{id,url}`. `python/arclink_onboarding.py:664-689`, `python/arclink_entitlements.py:286-295`, `python/arclink_adapters.py:42-54`, `python/arclink_adapters.py:127-128`
- CONFIRM: OLD provider setup round-trip holds from curator state to provisioner Codex polling. `python/arclink_onboarding_flow.py:2032-2068`, `python/arclink_enrollment_provisioner.py:1635-1648`, `python/arclink_onboarding_provider_auth.py:46-69`

### New findings both Claude passes missed (severity + path:line)
- MEDIUM: late cancel can regress a paid/provisioning session to `abandoned`/`cancelled`; cancel API only treats terminal statuses as immutable, excluding `provisioning_ready` and `first_contacted`, then `cancel_arclink_onboarding_session()` rewrites active paid state. `python/arclink_api_auth.py:5039-5050`, `python/arclink_onboarding.py:748-760`
- LOW: public answer `question_key` is user-controlled, stored directly as `current_step`, and reflected by `_public_onboarding_session()`; no length or secret scan is applied to `current_step`. `python/arclink_hosted_api.py:737-754`, `python/arclink_api_auth.py:313-323`, `python/arclink_api_auth.py:1127-1141`, `python/arclink_onboarding.py:526-527`

### Claude citations re-confirmed or corrected
- Re-confirmed: two-system split, Chutes API-key drift, dead NEW statuses, plaintext completion password, live provider HTTP, first-contact callback shape, and provider-auth handoff. `python/arclink_onboarding.py:421`, `python/arclink_onboarding_flow.py:1761`, `python/arclink_onboarding_completion.py:411-456`, `python/arclink_onboarding_provider_auth.py:153-165`
- Corrected: verifier/CANON rollback wording should be “premature commit + failed replay loop,” not “entitlement write undone.” `python/arclink_onboarding.py:324-340`, `python/arclink_entitlements.py:789-809`
- Corrected: `arclink_api_auth.py:1093` is scanned; do not use it as the `_update_session` bypass proof. `python/arclink_api_auth.py:221-222`, `python/arclink_api_auth.py:1092-1095`, `python/arclink_boundary.py:65-73`

### Residual disagreement with the Claude half (for final reconciliation)
- Keep CANON-04 HIGH, but rewrite mechanism: paid entitlement/gate can be committed while webhook event is failed/replayable; “entitlement rollback” is code-false. `python/arclink_entitlements.py:526`, `python/arclink_entitlements.py:741-750`, `python/arclink_onboarding.py:324-340`
- Downgrade generic `_update_session` bypass unless an external reachable caller is found; elevate/keep the concrete weak-regex free-text secret leak instead. `python/arclink_onboarding.py:116-126`, `python/arclink_onboarding.py:344-383`
<<<CODEX-VERDICT-END CANON-04>>>
