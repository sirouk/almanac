# Ralphie Steering: Entitlement Preservation Repair

## Status

The entitlement preservation repair is complete and covered by no-secret
regressions. This note is retained as historical steering for the defect and
the validation contract that closed it.

## Original Bug

`upsert_arclink_user()` previously defaulted `entitlement_state` to `"none"`
and wrote it during profile-only updates. This could regress an existing
`paid` or `comp` ArcLink user to `none`.

Observed probe:

```text
upsert_arclink_user(... entitlement_state="paid")
upsert_arclink_user(... display_name="Name Only")
=> entitlement_state becomes "none"
```

`python/arclink_onboarding.py` could trigger the same bug while preparing or
resuming onboarding for a returning paid customer.

## Completed Build Repair

1. Make entitlement mutation explicit in `python/almanac_control.py`.
2. Prefer `entitlement_state: str | None = None` for `upsert_arclink_user()`.
3. Preserve existing entitlement state and `entitlement_updated_at` on conflict
   when no explicit entitlement state is supplied.
4. Keep `set_arclink_user_entitlement()` and entitlement webhook/admin comp
   helpers as the normal entitlement writers.
5. Added regressions proving:
   - Profile-only user updates preserve `paid` and `comp`.
   - Public onboarding prepare/resume preserves an already paid or comped user.
   - Explicit entitlement writes still work for new users where needed.

## Required Verification

Run focused no-secret tests after the fix:

```bash
python3 tests/test_arclink_schema.py
python3 tests/test_arclink_onboarding.py
python3 tests/test_arclink_entitlements.py
python3 tests/test_arclink_provisioning.py
python3 tests/test_public_repo_hygiene.py
python3 -m py_compile python/almanac_control.py python/arclink_onboarding.py python/arclink_entitlements.py
git diff --check
```

The next no-secret product slice can proceed to dashboard/admin contracts. Live
provisioning execution, DNS execution, public bot delivery, and hosted UI work
remain later phases with separate E2E prerequisites.
