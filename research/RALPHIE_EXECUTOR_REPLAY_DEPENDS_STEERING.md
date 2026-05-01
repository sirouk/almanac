# Ralphie Steering: Executor Replay And Dependency Consistency

Next BUILD only: fix the fresh LINT HOLD in `python/arclink_executor.py`.
Do not repeat the already-completed four-risk executor lint repair, and do not
start live provider, dashboard UI, or frontend work in this slice.

## Current Blockers

1. Fake DNS, Access, Chutes, and rollback adapters accept reused idempotency
   keys without validating that the replay input is identical to the stored run.
2. Chutes replay can return the current request `action` and `secret_ref` while
   reusing a previously stored key result. This can mask a key lifecycle drift.
3. `_compose_service_start_order` ignores `depends_on` services that are missing
   from the rendered compose intent. Fake execution must reject a graph that real
   Docker Compose would reject.

## Implementation Shape

- Add a small stable digest helper for operation inputs, similar in spirit to
  the existing intent digest helper. Use canonical JSON plus SHA-256.
- Store an operation digest with each fake DNS, Access, Chutes, and rollback run.
- For both explicit and derived idempotency keys, compare the incoming operation
  digest to the stored digest before returning any stored result.
- On mismatch, raise `ArcLinkExecutorError` with enough context to identify the
  operation and reused idempotency key. Do not include secrets or secret values.
- For Chutes, either reject mismatched inputs before result creation or return
  only stored `action` and stored `secret_ref` on identical replay. Prefer strict
  mismatch rejection. Never echo current request metadata from an old stored run.
- In `_compose_service_start_order`, raise `ArcLinkExecutorError` when a
  dependency listed in `depends_on` is absent from `services`. Include both the
  service name and missing dependency in the error message.

## Required Tests

Add focused regressions in `tests/test_arclink_executor.py`:

- Reusing a DNS idempotency key with changed records rejects.
- Reusing an Access idempotency key with changed app or SSH plan rejects.
- Reusing a Chutes idempotency key with changed action and/or `secret_ref`
  rejects; identical replay returns the stored action and stored secret ref.
- Reusing a rollback idempotency key with changed plan, actions, or health
  rejects.
- Compose `depends_on` that references an unknown service rejects with
  `ArcLinkExecutorError`.

## Validation

Run:

```bash
python3 tests/test_arclink_executor.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/arclink_executor.py python/arclink_provisioning.py
python3 -m ruff check python/arclink_executor.py tests/test_arclink_executor.py
git diff --check
```

Update `research/BUILD_COMPLETION_NOTES.md` only after the new regressions pass.
