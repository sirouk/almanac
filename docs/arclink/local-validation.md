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
install smoke for legacy host primitives. Treat that path, or a narrower
authorized `sudo bin/ci-install-smoke.sh` run, as a host-mutation proof only;
do not run it in unattended local passes because it mutates the host.

### Host Readiness And Provider Diagnostics

Two no-secret, no-mutation preflight CLIs print JSON and are safe to run in
unattended local passes. Neither prints secret values; both report missing
variable names only.

```bash
python3 -m arclink_host_readiness
python3 -m arclink_diagnostics
```

`arclink_host_readiness` checks Docker, `docker compose version`, the writable
state root (`ARCLINK_STATE_ROOT` or `/arcdata`), the required env vars
(`ARCLINK_PRODUCT_NAME`, `ARCLINK_BASE_DOMAIN`, `ARCLINK_PRIMARY_PROVIDER`),
presence-only secret env vars, the ingress strategy, and the local ingress
ports. Missing optional secrets do not flip `ready` to false; the `secret_*`
checks are excluded from the `ready` computation. Flags: `--state-root`,
`--docker-binary`, `--skip-ports`, `--ports` (default `80,443,8080`). Exit code
is `0` when `ready`, `1` otherwise.

`arclink_diagnostics` runs credential-presence checks for stripe, ingress
(cloudflare, or tailscale when `ARCLINK_INGRESS_MODE=tailscale`), the model
provider, telegram, discord, and docker. `--live` is reserved for future credentialed
connectivity probing and is a no-op today (presence-only). Flags:
`--docker-binary`, `--live`. Exit code is `0` when all checks pass, `1`
otherwise. These checks are presence-only; passing diagnostics is not live
provider proof.

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
