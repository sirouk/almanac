# Contributing

Thanks for helping improve Almanac.

## Before you start

- Please keep pull requests focused. Small, reviewable changes land faster than broad cleanup.
- For larger features, behavior changes, or rollout-sensitive work, open an issue or start a discussion before investing heavily in implementation.
- By submitting a contribution, you agree that your work will be released under the repository's Apache 2.0 license.

## Development checks

This repository currently uses two main validation paths:

- Python regression suite:

```bash
for test_file in tests/test_*.py; do
  python3 "$test_file"
done
```

- Install / health / teardown smoke:

```bash
./test.sh
```

If your change only affects documentation or GitHub workflow files, running the relevant lightweight checks is usually enough. If you touch install, runtime, systemd, or provisioning behavior, please run both paths when practical.

## Pull request expectations

- Explain the problem being solved and the user or operator impact.
- Mention the validation you ran locally.
- Avoid mixing unrelated refactors with functional changes.
- Preserve existing behavior unless the PR clearly documents an intentional change.
- Do not revert work you did not author unless the maintainers ask for it.

## Code and review notes

- Follow the existing style of the surrounding files instead of introducing a new pattern.
- Add tests when behavior changes or regressions are being fixed.
- Keep shell changes portable and defensive (`set -euo pipefail` is the current norm).
- Keep documentation and workflow changes in sync with the actual commands contributors should run.

## Reporting issues

Bug reports are most helpful when they include:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Relevant logs, screenshots, or command output
- Host OS / runtime details when the issue is environment-specific

For sensitive security issues, please follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
