# ArcLink Vocabulary

This is the canonical reference for ArcLink terms. User-facing surfaces (the web app,
public bots, Captain dashboard, completion bundles, Raven copy, Wrapped reports, and
human-readable docs) use the **Captain-facing** vocabulary. Backend, admin, and operator
surfaces (admin dashboard, deploy scripts, audit/event tables, internal logs, code
identifiers, env vars, OpenAPI route names, and research files) use the **Operator-facing**
vocabulary. Where one page bridges the two (the admin dashboard's per-Captain panel),
both vocabularies coexist with their boundaries respected.

When in doubt, follow the example column. If a string is rendered to the buyer or to the
person who owns the running Pod, use the Captain term. If a string is rendered to the
operator running `./deploy.sh control install`, an audit row, or a code identifier, use
the Operator term.

## Captain-Facing Canon

| Term | Means | Use it for | Do not use it for |
| --- | --- | --- | --- |
| **Raven** | The guide to ArcLink and the Curator of the Console. The public bot persona, the onboarding voice, the dashboard guide voice. | Web hero, onboarding page, public bot replies, completion bundles, Wrapped emails, dashboard guide copy. | Admin/operator screens. |
| **ArcPod** | A single Captain's provisioned deployment. Renames the old "Sovereign Pod" / "deployment" on Captain-facing surfaces. | All Captain-facing copy. First occurrence on a page should be "ArcPod"; later occurrences may use "Pod". | Module names, table names, env-var names, route names. |
| **Pod** | Short form of ArcPod, used after the first occurrence. | Fluent Captain-facing copy. | Operator screens. |
| **Agent** | The Hermes-powered occupant of one ArcPod. One Agent per Pod. The Agent has a Name and a Title (e.g. "Bob, the know-it-all"). | Everywhere a Captain or Operator refers to the running assistant. | n/a — same word both surfaces. |
| **Captain** | A user who owns one or more ArcPods. All paying users are Captains. Founders / Sovereign / Scale plans all make a user a Captain. Captains see "Captain &lt;name&gt;" in formal greetings. | Public bot copy, web pages, dashboard greetings, completion bundles, Wrapped reports, share-grant copy. | Backend audit reasons (use `user_id`), admin operator screens (use "user"). |
| **Crew** | The inventory of Agents managed by one Captain. Sovereign / Founders is a Crew of one. Scale is a Crew of three. Agentic Expansion grows the Crew. | Captain-facing copy: "Show My Crew", "Train Your Crew", "your Crew member &lt;name&gt;". | n/a |
| **Comms** | Inter-Pod messages within a Captain's Crew, and (in the Operator view) across Captains. | Captain Comms tab, Operator Comms Console, agent tooling, audit reasons surfaced to Captains. | n/a |
| **Comms Console** | The Captain's unified view of all Crew comms, and the Operator's view across all Captains. | Captain dashboard "Comms" tab, admin dashboard "Comms" tab. | n/a |
| **Crew Training** | The character-creation-style flow that captures the Captain's role, mission, and treatment preference; picks a preset and capacity; produces a Crew Recipe; and applies it as an additive SOUL overlay to every Pod in the Crew. | Captain dashboard, public bot `/train-crew`, web `/train-crew`. | n/a |
| **Crew Recipe** | The combined `preset × capacity × role × mission` definition that drives the SOUL overlay. Internally `arclink_crew_recipes`. | Captain-facing copy. | n/a |
| **ArcLink Wrapped** | The periodic Captain-facing insights report. Default cadence is daily; weekly and monthly are operator-selectable per Captain. Includes at least five novel non-standard statistics per period. | Captain dashboard "Wrapped" tab, delivery messages. Internal module name is `arclink_wrapped`. | n/a |

## Operator-Facing Canon

| Term | Means | Use it for |
| --- | --- | --- |
| **Operator** | The owner of the ArcLink platform. Runs `./deploy.sh control install`, sees the admin dashboard, registers fleet machines, manages provider credentials. The platform identity. | Admin dashboard, deploy scripts, AGENTS.md, internal logs, research files, completion notes, audit actor identities (`actor_id="operator:..."`). |
| **deployment** | The internal name for an ArcPod row. Schema: `arclink_deployments`. | Schema/code references; admin audit log; OpenAPI route names like `/api/v1/admin/deployments`. |
| **user** | The internal name for a Captain row. Schema: `arclink_users`. | Schema/code references; admin queries; audit log `user_id`. |
| **fleet host** | An individual machine in the fleet that can host ArcPods. Schema: `arclink_fleet_hosts`. | Inventory submenu output, admin dashboard "Fleet" section, capacity reports. |
| **inventory machine** | A machine known to the Operator's inventory (manual, Hetzner, Linode). Schema: `arclink_inventory_machines`. Links to a fleet host once ready. | `./deploy.sh control inventory ...`, admin inventory tab. |
| **ASU** | ArcPod Standard Unit. The fair-share unit by which fleet hosts are sized. Computed as `min(vCPU/N, RAM/N, disk/N)`. | Inventory output, placement strategy, operator runbook. |

## Crossing the boundary

Some screens render both. The admin dashboard's Captain detail panel says
"Captain &lt;name&gt; · Pod `<deployment_id>`" — the friendly Captain term plus the technical
deployment id, side by side, with the boundary explicit. The Captain dashboard never shows
deployment ids unless a Captain explicitly requests the technical view.

Audit rows use the technical vocabulary (`user_id`, `deployment_id`, `actor_id`).
Operator notifications shaped *for* Captains (paid pings, vessel-online pings, Wrapped
reports, share-grant approval prompts) use the Captain vocabulary in their body even
though the underlying queue rows are keyed on technical identifiers.

## Migration rules for existing strings

1. Any user-facing string mentioning "Sovereign Pod" or "Sovereign deployment" becomes
   "ArcPod" (first mention) or "Pod" (subsequent mentions). Schema, route, and module
   names that contain "sovereign" stay unchanged (`arclink_sovereign_worker.py`, the
   Sovereign plan tier).
2. Captain-facing strings that say "user" or "buyer" become "Captain" where the
   reference is to the human paying for the service. Operator-facing strings stay as
   "user."
3. Bot copy "your bot" / "the agent" stays as "Agent" with a Name and Title where the
   identity is known. Use the Captain-supplied Name and Title in greetings, in
   completion bundles, and in Wrapped reports.
4. Multi-Pod Captains hear about their "Crew" and their "Crew members," not their
   "deployments" or "agents on different pods."
5. "Operator" is reserved for the platform owner and never used to address the paying
   Captain. The hosted API can keep its `actor_id="operator:..."` audit fields; that
   text is operator-facing.

## Examples

- Web onboarding hero: "Name your Agent. Raven runs the rest."
- Paid ping: "Captain Atlas, payment cleared. I'm provisioning your ArcPod now."
- Vessel-online ping: "Captain Atlas, your Pod is live. Open Helm."
- Share-grant: "Approve sharing this Drive folder with Captain Vega's Crew?"
- Wrapped greeting: "Captain Atlas — this week your Crew shipped 14 commits and Bob, the know-it-all, answered 47 inbound questions."
- Admin dashboard Captain detail: "Captain Atlas · Pod `dep_abc12` · Hetzner host `fsn1-arc-3`."
- Operator audit reason: "operator:opadm123 queued action `restart` on deployment `dep_abc12`."
- Inventory output: "Hetzner host `fsn1-arc-3` · ASU capacity 4 · 2 consumed · 2 free."

## Cross-references

This vocabulary is enforced by the surfaces named in
`research/RALPHIE_ARCPOD_CAPTAIN_CONSOLE_STEERING.md` and the wave-by-wave migration
plan in `IMPLEMENTATION_PLAN.md`. When a new surface is added, classify the audience
first, then pick the column.
