# ArcLink Operating Profile

The operating profile is the intended operator-owned source of truth for
people, roles, responsibilities, relationships, and agent delegation
boundaries.

The command and file names still use `org-profile` for compatibility, but the
profile is not company-specific. It can describe a solo operator, a
family/household, a project collective, a formal organization, or a hybrid of
those shapes.

It exists as a schema and design contract so agents do not learn authority from
vibes, chat history, or fuzzy prose. Humans remain responsible. Agents should
receive enough orientation to help those humans without mistaking awareness for
permission.

## Implementation Status

Shipped today:

- `config/org-profile.schema.json` defines the profile shape.
- `config/org-profile.example.yaml` gives a fictional, non-secret example.
- `config/org-profile.ultimate.example.yaml` gives a full fictional layered
  ingestion example covering solo, household/family, project collective, and
  organization/team modes with baseline, function modules, a prototype-agent
  module, starter stubs, source references, revalidation rules, privacy policy,
  automation boundaries, and distribution expectations.
- `./bin/arclink-ctl org-profile validate`
- `./bin/arclink-ctl org-profile build`
- `./bin/arclink-ctl org-profile preview`
- `./bin/arclink-ctl org-profile apply`
- `./bin/arclink-ctl org-profile doctor`
- `./bin/org-profile-builder.sh` provides the same interactive builder path
  directly for install flows and operator shells.
- ArcLink already seeds per-agent `SOUL.md` and
  `state/arclink-identity-context.json` from onboarding/session data.
- The `arclink-managed-context` plugin can read the local identity state when
  it exists and inject a compact `[local:identity]` section.
- Applied profiles also feed `[managed:org-profile]`,
  `[managed:user-responsibilities]`, and `[managed:team-map]` through plugin
  state, plus a durable `SOUL.md` overlay for matched agents after their
  refresh runs.
- During chat onboarding, Curator can offer safe, non-secret profile-person
  choices for unapplied roster entries when the applied profile privacy policy
  allows it. The user-selected link is stored separately from bot and Unix
  names, shown to the operator as unverified, and used only to orient the
  agent after normal approval/provisioning.

The commands and receipts below are the shipped operator contract. The current
pipeline is intentionally conservative: schema and semantic errors block
apply; missing source references warn; real-looking secrets fail closed.

## Files

Intended private profile file:

```text
arclink-priv/config/org-profile.yaml
```

Private resource manifest generated or maintained from the same operator-owned
profile:

```text
arclink-priv/config/team-resources.tsv
```

Public template and schema:

```text
config/org-profile.example.yaml
config/org-profile.ultimate.example.yaml
config/org-profile.schema.json
config/team-resources.example.tsv
```

The populated private file should not be committed. It may contain direct
identifiers such as emails, Notion emails, Discord handles, Discord user ids,
GitHub usernames, repo maps, and relationship maps. The public example uses
fictional people and `example.com` addresses.

## Identity And Repos

The profile should capture human-readable identifiers that operators can
actually collect during onboarding:

- `contact.discord_handle`: the Discord username/handle the human can provide
  in chat. This is easier than a numeric Discord user id and is useful as an
  onboarding hint, but it is not proof of identity by itself.
- `contact.discord_user_id`: optional stronger Discord id when ArcLink can
  resolve it through the gateway or an operator provides it.
- `identity_hints.discord_handle`: matching hint for profile-to-enrollment
  alignment.
- `identity_hints.github_username` and `github.username`: GitHub identity for
  source pointers, code review, public credibility, and repo operations.
- `github.primary_repos` and `github.accessible_repos`: person-specific repo
  context, including `owner_repo`, URL, role, expected permission, purpose,
  default branch, and sensitivity.
- `work_surfaces.code.repositories`: shared repo map for the whole operating
  context.

Credentials do not go here. Repo URLs, owner/repo names, local paths, branch
names, and expected permission levels are fine; deploy keys, tokens, SSH keys,
cookies, and OAuth credentials stay in private state.

## Design Position

The authoritative profile is structured YAML only.

Markdown is allowed as supporting context, but not as the authority for who owns
work, who approves decisions, or what an agent may do. A profile can reference
Markdown in `references`, and ArcLink can render a sanitized generated Markdown
summary for retrieval, but the structured YAML is the contract.

That design gives operators three useful properties:

- Schema validation catches typos and malformed input before agents consume it.
- Preview can show exactly what ArcLink believes the operator meant.
- Distribution can give each surface only the slice it needs.

## Minimum Useful Profile

A tiny valid file can start with one operating context, one role, and one
person. This solo example is intentionally not an organization:

```yaml
$schema: https://arclink.local/schema/org-profile.schema.json
version: 1

organization:
  id: personal-arclink
  name: Personal ArcLink
  profile_kind: solo_operator
  scope: One person running ArcLink for personal projects and operating rhythm.
  mission: Help the operator do focused, well-documented work.

roles:
  operator:
    description: Owns the ArcLink deployment, privacy boundaries, and agent policy.

people:
  - id: example-operator
    display_name: Example Operator
    role: operator
    agent:
      name: Guide
      purpose: Help the operator maintain ArcLink and keep important work visible.
```

Operators can deepen the file over time with groups/teams, household circles,
relationships, responsibilities, identity hints, work surfaces, and policies.

## Ingestion Commands

The operator flow is:

```bash
./bin/arclink-ctl org-profile build
./bin/arclink-ctl org-profile validate
./bin/arclink-ctl org-profile preview
./bin/arclink-ctl org-profile apply --yes
./bin/arclink-ctl org-profile doctor
```

`build` launches the interactive shell builder for the private profile. It can
start from a starter profile, edit an existing file section by section, accept
multi-line answers in the terminal, validate the result, and save only under
the private `arclink-priv/config/org-profile.yaml` path unless `--file` points
elsewhere. During `./deploy.sh install`, ArcLink asks whether to launch this
builder once the private path is known.

`validate` reads `arclink-priv/config/org-profile.yaml`, validates it
against `config/org-profile.schema.json`, and fails closed on invalid input.

`preview` prints a human-readable uptake report without writing live
agent state.

`apply` writes atomically, records the applied checksum/revision, refreshes
agent materialized context, and reports the exact surfaces updated.

`doctor` compares the current profile against enrolled agents and reports
drift, missing users, missing identity matches, stale generated files, and
agents that have not consumed the latest revision.

Automation may call `apply --yes`, but interactive operator flows should show
the preview first.

## Validation

Schema validation should catch:

- Missing required top-level sections.
- Unknown fields caused by typos.
- Invalid ids or usernames.
- Malformed email fields.
- Invalid enum values.
- Incorrect list/object shapes.

Semantic validation should catch:

- Duplicate person or team ids.
- People referencing roles that do not exist.
- People referencing teams that do not exist.
- Teams referencing members or leads that do not exist.
- Relationships whose subject/object look like missing known ids.
- Agent `serves` values that do not match the containing person.
- Work-surface paths that point outside expected shared locations.
- Sensitive identity hints being routed to public render targets.

Invalid schema blocks apply. Semantic warnings can be split into hard failures
and warnings. Identity mismatch, unknown roles, unknown teams, and impossible
agent ownership should be hard failures.

## Preview Report

Preview should show the operator what ArcLink will ingest in plain language:

```text
Operating profile preview
  Source:   arclink-priv/config/org-profile.yaml
  Schema:   v1 valid
  Revision: sha256:...

Operating Context
  Example ArcLink
  Kind: hybrid
  Scope: Solo, household, project, and team lanes.
  Mission: Keep useful work and life logistics visible without blurring privacy or approval.

People
  alex-rivera  -> Alex Rivera, operator, groups solo-practice/platform, agent Atlas
  morgan-lee   -> Morgan Lee, household_coordinator, group household, agent North
  priya-shah   -> Priya Shah, engineering_lead, group project-collective, agent Forge

Groups / Teams
  solo-practice       lead: alex-rivera  members: alex-rivera
  household           lead: morgan-lee   members: morgan-lee, alex-rivera
  project-collective  lead: priya-shah   members: morgan-lee, priya-shah

Relationships
  alex-rivera approves client_portal_launch_scope
  morgan-lee owns support_queue
  priya-shah owns release_readiness

Distribution
  control database:
    org_profile_revision, roles, people, teams, relationships
  per-agent SOUL.md:
    agent-alex, agent-morgan, agent-priya
  per-agent identity state:
    state/arclink-identity-context.json
  plugin-managed context:
    org-profile, user-responsibilities, team-map
  vault render:
    Agents_KB/Operating_Context/org-profile.generated.md
```

The preview is not decorative. It is the operator's chance to catch a bad
mapping before agents start using it.

## Distribution Surfaces

Each destination should receive the least powerful useful slice.

### Control Database

Store normalized profile rows and the source revision:

- profile checksum and applied timestamp
- operating-context summary
- roles
- people
- teams
- relationships
- identity hints
- work-surface defaults
- authority, identity-verification, distribution, workflow, automation, and
  benchmark contracts

The control database is the exact lookup layer for policy checks. It does not
depend on re-parsing generated Markdown.

### Per-Agent SOUL.md

`SOUL.md` receives a managed overlay with durable identity and responsibility
boundaries:

- operating-context name, mission, primary project, timezone, and quiet hours
- the human served by this agent
- that human's role, teams, responsibilities, and decision authority
- what the agent may do for that human
- what the agent must ask before doing
- what the agent must never do
- escalation rules

SOUL.md should not include unnecessary private details about other people.

### Per-Agent Identity State

`state/arclink-identity-context.json` receives machine-readable local
identity for the installed `arclink-managed-context` plugin:

- agent label
- unix user
- human display name
- operating-context summary
- user responsibilities
- user decision authority
- teammates needed for coordination
- applied org-profile revision

### Plugin-Managed Context

Plugin-managed context receives compact, refreshable operational slices:

- `[managed:org-profile]`: context mission, operating principles, work surfaces
  and relevant operational rails
- `[managed:user-responsibilities]`: the current user's responsibilities,
  authority, and agent boundaries
- `[managed:team-map]`: teams and teammate coordination context

These should be small enough to inject without drowning the agent, but precise
enough to prevent authority confusion. Dynamic `[managed:*]` slices, including
vault/Notion landmark maps and today-plate recall, are not written into Hermes
`MEMORY.md`; `SOUL.md` remains the durable identity and orientation artifact.

### Vault Render

Apply renders a sanitized Markdown summary into a shared knowledge path such
as:

```text
vault/Agents_KB/Operating_Context/org-profile.generated.md
```

This gives agents retrievable narrative context. It should omit direct chat ids,
private emails, and restricted notes unless the operator explicitly chooses a
less private render. The generated file should state that the YAML profile is
authoritative.

### Enrollment Defaults

During onboarding, ArcLink can ask a newly enrolled human to select one of the
applied profile people that is not already linked to an active agent. Curator
shows only short labels such as name, role/title, and group/team when the
profile privacy policy permits roster visibility. The selected
`org_profile_person_id` orients plugin-managed context and the `SOUL.md` overlay even
when the user chooses an unrelated bot name or Unix account name. Existing
agents can also match by exact `unix_user`, then simple display/alias/agent
name matches. A match can prefill or orient:

- display name
- preferred agent name
- purpose
- group/team
- provider defaults
- Notion identity claim email

Hints and user-selected profile links are not verification by themselves.
Operator approval still controls provisioning, and Notion identity still goes
through the existing claim/verification path.

## Authority Rules

Agents must learn these distinctions from the profile:

- A human is accountable for outcomes.
- An agent may prepare work, maintain context, and execute scoped tasks.
- A teammate is a person, not that person's agent.
- Another agent's statement is not approval from that human.
- Shared work belongs under shared rails such as SSOT writes, not private
  pages.
- Destructive operations remain blocked by broker policy regardless of profile
  wording.

If a profile says an agent may do something that the broker refuses, the broker
wins. The agent should explain the scope or verification limit and offer the
next best path.

## Privacy

The private profile may include sensitive direct identifiers. Distribution must
not blindly copy the full file everywhere.

Recommended defaults:

- Full person slice: only the agent serving that person and operator tools.
- Teammate summary: role, team, responsibilities, escalation lane.
- Public vault render: no chat ids, no private notes, no direct identifiers.
- Control DB: full structured data, readable only by ArcLink services.
- Managed memory: compact and role-oriented.

## Apply Receipt

After apply, ArcLink records and prints:

```text
Applied operating profile
  revision: sha256:...
  schema:   v1
  source:   arclink-priv/config/org-profile.yaml
  people:   3
  teams:    3
  roles:    3

Updated
  control database: ok
  generated vault doc: ok
  agent-alex context slice: ok
  agent-morgan context slice: ok
  agent-priya context slice: ok
  plugin-managed context refresh queued: ok
```

Apply is idempotent. Reapplying the same file should produce the same
revision and no unnecessary file churn.

`./deploy.sh install` and `./deploy.sh upgrade` also attempt to apply the
private profile when it exists, after the control plane is available. This
keeps production installs aligned with the structured profile without requiring
operators to remember a separate apply step.

## Failure Model

Fail closed when:

- YAML cannot be parsed.
- Schema validation fails.
- A person references a missing role.
- A person references a missing team.
- A team lead/member is missing.
- A profile tries to assign one agent to multiple humans without an explicit
  team-delegate/curator mode.
- A generated output would expose restricted fields to a public/shared render.

Warn, but allow apply when:

- A person does not yet correspond to an enrolled ArcLink user.
- A Notion identity hint has not yet been verified.
- A referenced supporting document does not exist yet.
- A team has no lead.

## Explicit File Review

The CLI accepts an explicit path for staging and review:

```bash
./bin/arclink-ctl org-profile validate --file ./draft-org-profile.yaml
./bin/arclink-ctl org-profile preview --file ./draft-org-profile.yaml
./bin/arclink-ctl org-profile apply --file ./draft-org-profile.yaml --yes
```

Without `--file`, commands use:

```text
arclink-priv/config/org-profile.yaml
```

The command names are intentionally boring. Operators need confidence that
this is infrastructure, not an agent improvisation.
