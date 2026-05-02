# Chutes Integration Notes For ArcLink

Sources reviewed:

- `https://github.com/Veightor/chutes-agent-toolkit`
- live `https://llm.chutes.ai/v1/models` on 2026-05-01
- ArcLink `config/model-providers.yaml` and provider auth code

## Current Live Model Facts

The live Chutes model endpoint returned 39 models during prep. Required ArcLink default model was present:

- `moonshotai/Kimi-K2.6-TEE`
- `confidential_compute: true`
- provider backend: `vllm`
- context length: `262144`
- max output length: `65535`
- supported features: `json_mode`, `structured_outputs`, `tools`, `reasoning`
- pricing shown by endpoint: prompt `0.95`, completion `4.0`, cache read `0.475` USD per 1M tokens

Other confirmed TEE candidates:

- `moonshotai/Kimi-K2.5-TEE`
- `zai-org/GLM-5.1-TEE`
- `Qwen/Qwen3.5-397B-A17B-TEE`
- `deepseek-ai/DeepSeek-V3.2-TEE`
- `openai/gpt-oss-120b-TEE`

ArcLink should not hard-code stale model claims. It should periodically refresh Chutes inventory and update a safe central config/catalog.

## Auth Caveat

The Chutes Agent Toolkit notes a live-auth caveat: direct inference succeeded with `X-API-Key: cpk_...`; `Authorization: Bearer cpk_...` returned 401 in toolkit live tests dated 2026-04-15. Hermes custom providers generally expect bearer-style auth. ArcLink currently treats Chutes as an OpenAI-compatible provider through Hermes custom-provider configuration.

ArcLink must build and test one of these before claiming Chutes works end-to-end:

1. A Hermes-compatible Chutes provider path that can send `X-API-Key`.
2. A local ArcLink proxy that accepts Hermes/OpenAI-style bearer calls and forwards to Chutes with `X-API-Key`.
3. Confirmation that current Chutes inference accepts bearer auth for ArcLink keys.

Do not silently assume generic OpenAI SDK drop-in compatibility.

## Product Decision

Chutes is the default ArcLink inference provider. ArcLink owner account will create/manage separate Chutes API keys per deployment for control, revocation, spend isolation, and incident response. Per-deployment Chutes keys should be stored only in secret storage and injected into user runtime environments as needed.

BYOK remains available:

- OpenAI Codex OAuth/device flow.
- Anthropic/Claude OAuth/PKCE where supported by current ArcLink flow.
- Optional user-owned Chutes key later, but default is ArcLink-managed.

## Implementation Shape

Add an ArcLink provider service around existing provider setup:

- `ARCLINK_PRIMARY_PROVIDER=chutes`
- `ARCLINK_CHUTES_BASE_URL=https://llm.chutes.ai/v1`
- `ARCLINK_CHUTES_DEFAULT_MODEL=moonshotai/Kimi-K2.6-TEE`
- `ARCLINK_MODEL_CATALOG_REFRESH_INTERVAL_SECONDS=21600`
- `ARCLINK_MODEL_REASONING_DEFAULT=medium`
- `ARCLINK_MODEL_REASONING_POWER=xhigh`

Model catalog job:

- Fetch `https://llm.chutes.ai/v1/models`.
- Validate default model exists and has expected feature flags.
- Prefer `confidential_compute: true` for default/premium privacy lanes.
- Record current pricing/capabilities in DB.
- Alert admin dashboard when configured default disappears, loses tools/reasoning, or changes pricing materially.
- Support manual pin and canary changes before fleet rollout.

Per-deployment key lifecycle:

- On successful Stripe entitlement and before provisioning, create or allocate a Chutes key for the deployment.
- Store key as secret, not in chat logs or DB plaintext.
- Inject into Hermes home/provider config at provisioning time.
- Admin dashboard can rotate/revoke with reason and audit log.
- Usage dashboard should reconcile Chutes cost with Stripe plan/limits.

## Toolkit Assets Worth Reusing

From `chutes-agent-toolkit`:

- `plugins/chutes-ai/skills/chutes-ai/scripts/manage_credentials.py` patterns for secure credential handling.
- `other-agents/hermes/config-examples/chutes-basic.yaml` for Hermes custom provider shape.
- `other-agents/system-prompt/chutes-agent-prompt.md` for API endpoint/auth caveats and model routing concepts.
- `plugins/chutes-ai/skills/chutes-mcp-portability/mcp-server/server.py` as reference for future Chutes MCP operator tools.
- `plugins/chutes-ai/skills/chutes-routing/*` for future model alias/pool ideas.

ArcLink should not vendor the whole toolkit blindly. Import concepts/scripts selectively or add it as a clearly licensed/reference submodule later if needed.
