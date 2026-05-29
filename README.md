# ArcLink

ArcLink is a Sovereign Control Node for operating Raven, Captain onboarding,
fleet inventory, Docker ArcPod deployments, Academy workflows, provider routing,
and the Telegram/Discord bridges around Hermes agents.

The public install surface is now one lane:

```bash
./deploy.sh control install
./deploy.sh control upgrade
./deploy.sh control health
```

The bare shortcuts are intentionally mapped to the same Control Node lane:

```bash
./deploy.sh install     # control install
./deploy.sh upgrade     # control upgrade
./deploy.sh health      # control health
```

The old Shared Host/systemd installer and the public Shared Host Docker menu
are retired. Fleet growth now happens by registering worker machines with the
Control Node and placing ArcPods as Docker deployments on those workers.
ArcPods as Docker deployments on registered fleet workers are the supported
fleet shape.

## Current Architecture

| Layer | Purpose | Primary commands |
| --- | --- | --- |
| Sovereign Control Node | Hosted API, web control plane, Raven, Stripe/billing rails, public bots, fleet inventory, provisioning, admin actions, Academy, inference routing. | `./deploy.sh control install`, `upgrade`, `health`, `logs`, `ps`, `ports` |
| Fleet Inventory | Expandable worker inventory for local, Hetzner, Akamai/Linode, and SSH-managed machines. | `./deploy.sh control register-worker`, `./deploy.sh control inventory ...` |
| ArcPods | Captain deployments placed by the Control Node onto registered Docker-capable workers. | Control provisioner/action worker, dashboard, Raven, fleet commands |
| Operator | Platform owner/admin surface. Operator Raven owns powerful control commands; Operator Hermes workbench must remain outside Captain ArcPods and operate against the Control Node. | Operator Telegram/Discord, `./deploy.sh control ...`, `/upgrade`, `/action_status` |
| Hermes Agent Runtime | Captain and Operator agent homes, plugins, skills, MCP, qmd, vault, memory synthesis, dashboard access, and command menus maintained by ArcLink installers. | `bin/install-deployment-hermes-home.sh`, rollout/upgrade rails |

The Control Node still uses Docker Compose internally. That does not mean
`./deploy.sh docker ...` is a supported public mode. Use `./deploy.sh control ...`
so the Operator has one control center and ArcPods stay under fleet management.

## Control Node Quick Start

```bash
git clone <arclink-repo-url> arclink
cd arclink
./deploy.sh control install
```

Install collects:

- product/site URLs and ingress mode (`domain` or `tailscale`)
- Stripe and hosted API settings
- Telegram/Discord Raven/public bot settings
- Operator Raven channel and allowlist
- fleet deployment style (`single-machine`, `hetzner`, `akamai-linode`, or
  control-plane only)
- LLM router defaults, allowed models, fallback models, and replacement policy

After install, verify:

```bash
./deploy.sh control health
./deploy.sh control ps
./deploy.sh control ports
```

Register and inspect workers:

```bash
./deploy.sh control fleet-key
./deploy.sh control register-worker
./deploy.sh control inventory list
./deploy.sh control inventory health --json
./deploy.sh control inventory probe-all --json
```

## Upgrades

Use Control Node upgrade for normal code deployments:

```bash
./deploy.sh upgrade
```

Pinned component upgrades still use `config/pins.json` as the source of truth:

```bash
./deploy.sh pins-check
./deploy.sh hermes-upgrade-check
./deploy.sh hermes-upgrade [--ref REF]
./deploy.sh qmd-upgrade-check
./deploy.sh qmd-upgrade [--version V]
```

Component apply commands commit/push the pin change when configured and then
re-enter `./deploy.sh upgrade`, which now means Control Node upgrade.

## Retired Modes

These public modes are intentionally retired:

- `./deploy.sh install` as a Shared Host/systemd/per-Unix-user installer
- `./deploy.sh upgrade` as a Shared Host host-mutating upgrade
- `./deploy.sh docker ...` as a Shared Host Docker control center
- old operator-led enrollment commands that provisioned per-user Unix accounts

Lower-level scripts for migration, tests, and host-side Operator workbench work
may still exist in the tree. They are not the public product install path.

## Operator And Captain Boundaries

Captain-facing language uses Raven, Captain, Crew, ArcPod/Pod, and Agent.
Operator is reserved for platform/admin/deploy surfaces.

Isolation goals:

- Captains receive isolated ArcPods and Hermes homes.
- Fleet workers are registered inventory controlled by the Control Node.
- Operator Raven can queue audited system actions such as upgrades and repairs.
- Operator Hermes should be a single host-side workbench owned by the deployment
  user, not a Captain-style multi-agent bundle and not a Captain ArcPod.
- Shared vault, qmd, Notion, dashboard, plugin, terminal, code, and drive access
  must stay scoped through ArcLink’s generated credentials and MCP rails.

## Organization Profile

`arclink-ctl org-profile` is the shipped operator CLI for the build, validate,
preview, apply, and doctor workflow:

```bash
./bin/arclink-ctl org-profile build
./bin/arclink-ctl org-profile validate
./bin/arclink-ctl org-profile preview
./bin/arclink-ctl org-profile apply --yes
./bin/arclink-ctl org-profile doctor
```

Private organization profiles belong under `arclink-priv/config/`; public
examples must stay fictional.

## Validation

Focused checks:

```bash
python3 tests/test_deploy_regressions.py
python3 tests/test_documentation_truths.py
python3 tests/test_arclink_operator_raven.py
python3 tests/test_arclink_operator_agent.py
```

Broad checks:

```bash
./bin/ci-preflight.sh
./test.sh
```

Live proof remains credential-gated. Local tests and dry runs must not be
reported as live customer provisioning proof.
