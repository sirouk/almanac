# ArcLink Local Validation

Local validation is split into no-secret checks, web checks, and credentialed
proof-gated checks.

## Python And Shell

Install the focused no-secret Python dependencies:

```bash
python3 -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` intentionally contains direct script dependencies such
as `jsonschema`, `PyYAML`, `pyflakes`, and `ruff`. The repository's Python
tests are executable scripts; `pytest` is not required for the documented
focused test path.

Common checks:

```bash
git diff --check
bash -n deploy.sh bin/*.sh test.sh
./bin/ci-preflight.sh
python3 -m py_compile python/arclink_control.py python/arclink_*.py
```

Focused tests should be selected by touched surface, for example:

```bash
python3 tests/test_arclink_hosted_api.py
python3 tests/test_arclink_plugins.py
python3 tests/test_arclink_docker.py
python3 tests/test_public_repo_hygiene.py
```

`./test.sh` is heavier than focused validation because it includes a sudo
install smoke.

## Web And Playwright

The web app has its own Node dependency set:

```bash
cd web
npm ci
npm run lint
npm test
npm run build
```

Browser checks use Playwright:

```bash
cd web
npx playwright install --with-deps chromium
npm run test:browser
```

Use the browser suite when changing `web/`, hosted API client behavior, route
copy that reflects backend state, checkout success/cancel journeys, login,
dashboard rendering, or admin dashboard shape.

## Live Proof

Live proof is credential-gated and must be explicitly enabled. The live Python
test path needs the relevant environment variables, and Stripe checks require
the `stripe` Python package when `STRIPE_SECRET_KEY` is set:

```bash
python3 -m pip install stripe
ARCLINK_E2E_LIVE=1 ARCLINK_E2E_DOCKER=1 python3 tests/test_arclink_e2e_live.py
```

Workspace browser proof is orchestrated from the repo root but uses the web
Playwright dependencies:

```bash
cd web && npm ci && npx playwright install --with-deps chromium
cd ..
bin/arclink-live-proof --journey workspace --live --json
```

Credential-gated skips are expected when required live values are absent. Do
not turn a skipped live proof into a production claim.
