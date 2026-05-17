# Coverage Matrix

## Mission Coverage

| Goal / criterion | Current PLAN/source coverage | BUILD proof required |
| --- | --- | --- |
| Dedicated router app | `python/arclink_llm_router.py` exists as FastAPI app. | Compose service, healthcheck, no Docker socket, import/health tests. |
| OpenAI-compatible `/v1/models` | Authenticated route exists and returns OpenAI-style list. | Re-run router tests and document auth failures. |
| OpenAI-compatible `/v1/chat/completions` | Route exists for streaming and non-streaming. | Re-run tests for success, failures, and usage settlement. |
| Separate key per ArcPod | Router key lifecycle helpers exist in `arclink_control.py`. | Worker/provisioning tests prove one generated key/ref per deployment. |
| Store only key hashes | Key registration stores `key_hash` and safe metadata. | DB assertions continue to prove raw router keys are absent from rows, metadata, logs, and API payloads. |
| Central Chutes key stays in Control Node | Router uses server-side Chutes credential; provisioning still needs default switch. | Provisioning and Docker tests prove ArcPods receive router key refs, not `CHUTES_API_KEY`, unless compatibility flag is set. |
| Billing and budget enforcement | Router calls `evaluate_chutes_deployment_boundary` and reserves budget. | Tests cover missing budget, exhausted budget, past-due billing, missing central credential, and settlement. |
| Rate and concurrency limits | Router uses existing rate scopes and open reservations. | Tests cover per-key/per-deployment/per-Captain rate limits and deployment concurrency cap. |
| Model allowlist | Router uses key or config allowed models. | Tests cover allowed, disallowed, and default models. |
| Request limits | Router checks body size, prompt estimate, and max token cap. | Tests cover oversized body, prompt cap, max token cap, and malformed JSON. |
| Non-streaming usage ledger | Router writes `arclink_llm_usage_events` and Chutes metadata. | Tests assert tokens, cents, status, deployment/user, and no prompt/completion persistence. |
| Streaming usage ledger | Router streams bytes and settles on completion/failure. | Tests assert chunk passthrough and no leaked reservations on partial failure. |
| Sanitized error handling | Router uses shared redaction before response/storage. | Tests cover upstream secret-looking errors. |
| Provider-state/dashboard consumption | Existing provider-state surfaces identified. | Add API/web tests if usage summaries are exposed. |
| Runtime dependencies | FastAPI/uvicorn/httpx present in runtime and dev lanes. | Dependency/Docker tests keep them pinned. |
| Docs/OpenAPI | Docs targets identified; router runbook exists in dirty tree. | API reference/OpenAPI document routes, auth, errors, live gate, and no-prompt storage policy. |
| Live Chutes safety | Live proof gate specified. | Tests prove no live calls by default; proof requires explicit env gate. |
| Audit Wave 1 regression gate | Historical audit treated as regression gate. | Existing focused tests pass or fresh regressions are fixed; fiction items remain ignored. |

## Required Artifact Coverage

| Artifact | PLAN status |
| --- | --- |
| `research/RESEARCH_SUMMARY.md` | Updated with `<confidence>`, current findings, path comparison, assumptions, risks, and verdict. |
| `research/CODEBASE_MAP.md` | Updated with directories, entrypoints, architecture rails, and remaining router BUILD surfaces. |
| `research/DEPENDENCY_RESEARCH.md` | Updated with stack components, current dependency state, alternatives, integration posture, risks, and validation dependencies. |
| `research/COVERAGE_MATRIX.md` | Updated with requirement-to-proof coverage and current source signals. |
| `research/STACK_SNAPSHOT.md` | Updated with ranked stack hypotheses, deterministic confidence score, and alternatives. |
| `IMPLEMENTATION_PLAN.md` | Rewritten as a router-specific checkbox backlog; no fallback marker remains. |
| `consensus/build_gate.md` | Present and updated to allow no-secret local router BUILD while blocking live/private actions. |

## Focused Test Targets

| Test file | Required proof |
| --- | --- |
| `tests/test_arclink_llm_router.py` | Router auth, models route, chat route, streaming, budget/rate/concurrency failures, usage ledger, redaction, no prompt persistence. |
| `tests/test_arclink_chutes_and_adapters.py` | Chutes boundary and sanitized usage ingestion remain compatible with router settlement. |
| `tests/test_arclink_provisioning.py` | ArcPods default to router URL/key refs; direct Chutes is compatibility-gated. |
| `tests/test_arclink_sovereign_worker.py` | Router key secret generation/registration and central Chutes key isolation. |
| `tests/test_arclink_hosted_api.py` | Provider-state usage/quota payloads and Wave 1 hosted API boundaries. |
| `tests/test_arclink_docker.py` | `control-llm-router` service, healthcheck, env, dependencies, and no Docker socket. |
| `tests/test_deploy_regressions.py` | Deploy/control shell syntax and any router helper wiring. |
| `tests/test_arclink_secrets_regex.py` | Router keys, Chutes keys, upstream errors, and prompt-looking text are redacted/rejected where appropriate. |

## Completion Rules

BUILD can claim complete only when:

- The router service exists and is wired into Compose.
- ArcPods get per-deployment router keys by default.
- Router auth maps each request to exactly one deployment and user/Captain.
- Billing, budget, model, request, rate, and concurrency checks fail closed.
- Streaming and non-streaming completions are fake-tested.
- Usage rows and Chutes metadata record token/cost consumption without raw
  prompt/completion storage.
- Provider-state/dashboard surfaces, if changed, expose only sanitized usage.
- Focused validation passes without live credentials.
- Live Chutes proof is either not run and explicitly gated, or run only with
  operator-provided proof env and redacted evidence.
- Audit fiction/outdated items are not reintroduced as backlog.
