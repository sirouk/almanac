# Ground Truth: Knowledge / Memory / Notion / SSOT / Org-Profile / MCP / Skills / Vault

Subsystem map as of 2026-05-30 (branch `arclink`). Source of truth is the code; docs
are judged against it below. No secrets, raw prompts, or operator identity are reproduced.

Owning code files (canonical):
- `python/arclink_memory_synthesizer.py` — memory synthesis (qmd-source-aware card builder).
- `python/arclink_org_profile.py` — org-profile validate/apply/doctor, managed sections, SOUL overlay, identity state.
- `python/arclink_org_profile_builder.py` — interactive builder CLI (`bin/org-profile-builder.sh`).
- `python/arclink_notion_ssot.py` — low-level Notion API client + SSOT handshake + no-secret proof harness.
- `python/arclink_notion_webhook.py` — Notion webhook receiver + verification-token arming/install policy.
- `python/arclink_mcp_server.py` — ArcLink control-plane MCP server (all agent-facing tools).
- `python/arclink_resource_map.py` — shared/managed resource-rail line composition.
- `python/arclink_control.py` — tables, managed-memory payload, recall stubs, notion index/SSOT broker, today-plate, batcher.
- `python/arclink_ssot_batcher.py` — thin worker calling `process_pending_notion_events` + `consume_notion_reindex_queue`.
- `bin/`: `arclink-ssot-batcher.sh`, `arclink-notion-webhook.sh`, `memory-synth.sh`, `qmd-daemon.sh`, `qmd-refresh.sh`, `org-profile-builder.sh`, `sync-hermes-docs-into-vault.sh`.
- `skills/arclink-*/SKILL.md`, `skills/notion-page-pdf-export/SKILL.md`.
- `templates/arclink-priv/vault/*/README.md`, `templates/SOUL.md.tmpl`, `config/org-profile.schema.json` (+ `.example.yaml`, `.ultimate.example.yaml`).

---

## A. What is actually implemented today (local-real)

### Memory synthesis (`arclink_memory_synthesizer.py`)
- `run_once(cfg, model_client=None)` is the entrypoint (`main()` -> `bin/memory-synth.sh`, job name `memory-synth`, kind `memory-synth`, recorded via `note_refresh_job`). Holds an exclusive `fcntl.flock` on `synth.lock`; writes a redacted `status.json` (api_key/token/secret/password stripped by `_write_status`).
- **Off the chat critical path**: it is a timer job that populates the `memory_synthesis_cards` table; the chat path only *reads* card_text (see recall stubs below). Cards are explicitly "awareness hints, not evidence."
- Sources (candidates) are built from TWO rails:
  - `build_vault_candidates` — walks `cfg.vault_dir`. Per top-level folder it builds a payload of repos/subfolders/text_files/pdfs/asset_counts/asset_examples/snippets and a fingerprint digest. Bounded walks (`_bounded_walk_files`, limit 800), skips symlinks + `SKIP_DIR_NAMES`. Detects "repo inventory" folders (`_is_repo_inventory`). Pulls PDF sidecar snippets from `PDF_INGEST_MARKDOWN_DIR` (`_pdf_sidecar_snippets`). Sorts `agents_kb/projects/research` first. Adds a synthetic `__root_files__` candidate for loose vault-root files.
  - `build_notion_candidates` — reads `notion_index_documents WHERE state='active'` (limit 600), groups by `_notion_landmark_area` (breadcrumb-derived), builds per-area pages/owners/snippets. Notion markdown snippet reads are path-confined to `ARCLINK_NOTION_INDEX_MARKDOWN_DIR` via `_safe_notion_markdown_path` (traversal guard).
- **Freshness**: each candidate has `source_signature = sha256(json_dumps(payload))` where the payload includes a content-hash-based fingerprint digest (`_file_fingerprint` uses `_file_content_hash` = full sha256, not just size+mtime — this is the GAP-005-equivalent fix). `run_once` SKIPS candidates whose stored card `status='ok'` AND `source_signature` AND `prompt_version` (`memory-synth-v3`) AND `model` all match. Failed cards retry only after `failure_retry_seconds` (default 3600). Stale cards (`_mark_stale_cards`) are blanked when their source disappears.
- **Model client**: `load_settings` resolves an OpenAI-compatible chat endpoint from `ARCLINK_MEMORY_SYNTH_*` (fallback to `PDF_VISION_*`). If all of endpoint+model+api_key present -> `call_openai_compatible_model` (temp 0.1, bounded max_tokens). Otherwise -> `local_non_llm_fallback_model` (deterministic, no network): derives topics/domains/content_types/source_hints from already-bounded metadata. `enabled` is `auto` by default (on only when LLM config exists OR explicitly enabled). Explicit-enabled-but-no-config sets model to `local-non-llm-fallback`.
- **Prompt-injection / output hardening**: untrusted source inventory is wrapped in `BEGIN_UNTRUSTED_ARCLINK_SOURCE_INVENTORY`/`END_...` markers with an instruction not to follow embedded commands. Output is normalized (`_normalize_card_payload`) and run through `UNSAFE_OUTPUT_PATTERNS` (urls, shell verbs, "ignore previous instructions", etc.); any hit blanks the summary and sets `inject=false`/`unsafe_output_rejected=true`. Secrets redacted via `redact_secret_material`/`redact_then_truncate`.
- On `changed` it queues a `curator`/`brief-fanout` notification "Memory synthesis cards refreshed for managed context."

### How cards reach the agent (recall stubs)
- `arclink_control._memory_synthesis_card_lines` reads `memory_synthesis_cards WHERE status='ok' AND card_text != ''`, prefers subscribed-vault cards, caps at `ARCLINK_MEMORY_SYNTH_CARDS_IN_CONTEXT` (default 8, max 30).
- `arclink_control._build_recall_stubs` emits the `Retrieval memory stubs:` block (default tool routing: `knowledge.search-and-fetch`, `vault.search-and-fetch`, `notion.search-and-fetch`/`notion.query`), subscribed awareness lanes, "Recent hot-reload signals" (vault-watch change rows), then appends synthesis card lines under `Semantic synthesis cards:`. This is the `[managed:recall-stubs]` section. Cards = hints, confirmed by the leading guidance line.

### Org profile (`arclink_org_profile.py`, builder, schema)
- Schema top-level properties (`config/org-profile.schema.json`): `$schema, version, organization, roles, people, teams, relationships, agent_lineage, work_surfaces, authority, identity_verification, distribution, workflows, automations, benchmarks, policies, references, metadata`.
- `validate_profile` = schema (jsonschema) + semantic (`_semantic_report`: duplicate ids, missing role/team refs, agent `serves` must match containing person for personal/operator delegates, escalate_to targets, knowledge_refs, seed_source sha256 checks, generated-vault-path traversal guard, duplicate identity labels) + **secret scan** (`_secret_scan_errors`: key-name terms + value regexes for private keys, sk- keys, gh tokens, AWS/Slack/Telegram tokens, JWTs) which **fails closed**.
- `apply_profile(conn, cfg, profile, source_path, actor)`:
  - Rejects on invalid; otherwise computes `checksum = profile_checksum` (sha256 of canonical JSON).
  - `_replace_profile_rows` DELETEs+repopulates `org_profile_revisions`, `org_profile_roles`, `org_profile_people`, `org_profile_teams`, `org_profile_relationships`, and upserts `settings.org_profile_revision`.
  - Writes `state/org-profile/applied.json` (0o600), renders sanitized vault doc to `work_surfaces.vault.generated_org_profile_path` (default `Agents_KB/Operating_Context/org-profile.generated.md`, 0o644) via `render_vault_profile`, writes per-agent context slices to `state/org-profile/agent-context/<agent_id>.json` for active `role='user'` agents, removes stale slices for unmatched agents, writes `state/org-profile/last-apply.json`.
- `doctor_profile` compares applied/settings revision, matched/unmatched active agents, generated doc existence.
- **Managed sections** (`build_managed_sections_for_agent`): produces `org-profile`, `user-responsibilities`, `team-map` strings + `org_profile_agent_context` + `org_profile_revision`. If a person can't be matched (`_match_person_for_agent` by `org_profile_person_id` -> `unix_user` -> unique display/preferred/agent-name/alias), falls back to `org_baseline_context_for_agent` (operating_mode `org_member_unmatched`) which explicitly tells the agent NOT to infer role/team/identity from the roster.
- **SOUL overlay**: `render_soul_overlay` produces a `<!-- BEGIN ARCLINK ORG PROFILE -->` … `<!-- END ARCLINK ORG PROFILE -->` block; `merge_soul_overlay`/`_remove_soul_overlay` splice it idempotently. `materialize_agent_context(hermes_home, context)` atomically writes `state/arclink-org-profile-context.json` (0o644), merges `state/arclink-identity-context.json` (0o600, keys in `ORG_PROFILE_IDENTITY_KEYS`), and merges the SOUL overlay into `SOUL.md` (0o600). `render_soul_for_identity` + `_render_base_soul` render a full SOUL from `templates/SOUL.md.tmpl` for onboarding.
- Builder (`arclink_org_profile_builder.py`) is interactive (menu sections 1-10 + preview/save), `slugify`s ids, writes 0o600 YAML with `.bak`, refuses to store secrets (explicit prompt), and can `--apply` via `bin/arclink-ctl org-profile apply`. `profile_starter()` ships a full non-secret default profile.

### Notion: indexed knowledge rail + SSOT broker + webhook
- **Notion API client** (`arclink_notion_ssot.py`): `DEFAULT_NOTION_API_VERSION = "2026-03-11"`, base `https://api.notion.com/v1`, retry/backoff on 429/5xx. Resolves page/database/data_source targets; markdown via `/pages/{id}/markdown`; data-source-aware query (`query_notion_collection[_all]` prefers `data_sources[0]` then legacy `databases/{id}/query`). `handshake_notion_space` validates integration via `/users/me`, resolves target + stable root page (shared databases must live under a page). `preflight_notion_root_children` does a brokered create-page + create-database then trashes both (`in_trash:true`).
- **No-secret proof harness** `run_notion_ssot_no_secret_proof(...)`: dependency-injected `urlopen_fn`; `proof_mode` ∈ {`fake`,`authorized_live`}; only returns public urls/ids, never the raw token; emits checks incl. `brokered_ssot_write_preflight` (`proof_gated` unless write preflight requested), `email_share_only_status=not_proof`, `user_owned_oauth_status=proof_gated`, `live_workspace_mutation_status=proof_gated` unless explicitly `authorized_live` + `allow_live_mutation`. **This is the PG-NOTION gate in code.**
- **Indexed Notion knowledge** stored in `notion_index_documents` (doc_key, root_id, source_page_id, page_title, section_heading, breadcrumb_json, owners_json, content_hash, file_path, state). qmd collection name `notion-shared` (`ARCLINK_NOTION_INDEX_COLLECTION_NAME`, default `notion-shared`). Index markdown root `ARCLINK_NOTION_INDEX_MARKDOWN_DIR` (default `state/notion-index/markdown`). `notion_search`/`notion_fetch`/`notion_query`/`read_ssot`/`enqueue_ssot_write`/`preflight_ssot_write` live in `arclink_control.py`.
- **Webhook** (`arclink_notion_webhook.py`): loopback-only `/notion/webhook` POST + `/health` GET. Verification-token install is operator-armed: `arm_verification_token_install` / `reset_verification_token` / `mark_verification_token_verified` with a window stored in `settings` (`notion_webhook_verification_token*`). First handshake stores token only if armed and not already set (else 409 CONFLICT / 412 PRECONDITION_FAILED). Signed events verified via `notion_verify_signature`, stored via `store_notion_event`, then a **debounced** `_kick_ssot_batcher()` spawns `arclink-ssot-batcher.service` (`start_new_session`, 1s debounce) in addition to the 1-min timer.
- **Pipeline** (the "within seconds" claim in today-plate): Notion webhook -> `store_notion_event` -> batcher (`process_pending_notion_events` + `consume_notion_reindex_queue`) -> re-fetch page markdown (`retrieve_notion_page_markdown`) -> `notion_index_documents` -> qmd reindex of `notion-shared`.

### MCP server (`arclink_mcp_server.py`)
- JSON-RPC `/mcp` over loopback-only HTTP (`backend_client_allowed`), `/health`. Restart-safe session recovery (`_ensure_mcp_session`): reaccepts stale `mcp-session-id` for `notifications/initialized`/`tools/list`/`tools/call` so chats survive an MCP restart. JSON-RPC errors are returned on HTTP 200 with `X-ArcLink-MCP-Error-Status` to avoid client session teardown.
- **Bootstrap tokens** are the auth model: `AGENT_TOKEN_PROP` is harness-injected by `arclink-managed-context` (agents omit `token`); operator tools use `operator_token` (`_require_operator` -> `validate_operator_token`). `bootstrap.*` tools gate on tailnet/loopback source and optional Tailscale-Serve identity headers (`ARCLINK_TRUST_TAILSCALE_PROXY_HEADERS`). `bootstrap.status` is gated by (request_id + source_ip) match.
- **Tool set** (`TOOLS`/`TOOL_SCHEMAS`): `status`, `bootstrap.request|handshake|status|approve|deny|revoke|reinstate`, `agents.register`, `catalog.vaults`, `vaults.refresh|subscribe|reload-defs`, `vault.search|fetch|search-and-fetch`, `agents.managed-memory`, `agents.consume-notifications`, `academy.propose-resource`, `shares.request`, `pod_comms.list|send|share-file`, `curator.fanout`, `notifications.list`, `ssot.read|pending|status|approve|deny|preflight|write`, `notion.search|fetch|query|search-and-fetch`, `knowledge.search|search-and-fetch`.
- **qmd vault bridge**: `vault.*` and `knowledge.*` vault rail call qmd MCP (`cfg.qmd_url`, `_mcp_tool_call` -> qmd `query`/`get`). Default collections `["vault", "vault-pdf-ingest"]` (`_qmd_default_collections`), so uploaded PDFs are included. Bridge is deliberately fast: `rerank: false` always on the vault side; `vault.search-and-fetch` falls back to lex-only if vector search throws. `_vault_source_metadata` enriches hits with vault root/.vault/.git/PDF-manifest info; PDF manifest read from `state/pdf-ingest/manifest.sqlite3` (`pdf_ingest_manifest`). A leading Markdown YAML metadata block is preserved inline AND duplicated into `metadata` (`_split_markdown_metadata_block`) — important for files like `SKILL.md`.
- **Notion fetch fallback**: `notion.search-and-fetch`/`knowledge.search-and-fetch` first try live `notion_fetch` by recovered target id; if no id, recover the `<page-id>-NNN.md` markdown file from the qmd index and fetch via qmd `get` (`_qmd_fetch_notion_index_file`, `fetch_source: "qmd-index-fallback"`).
- **SSOT writes** route through `enqueue_ssot_write`; out-of-scope writes queue for user approval (`ssot.pending|status|approve|deny`), applied page/database creates promote url/id (`_normalize_ssot_write_result`). Archive/delete/trash are rejected by the broker.

### Resource map (`arclink_resource_map.py`)
- Pure formatter. `shared_resource_lines` emits the QMD MCP retrieval rail, ArcLink MCP control rail, optional external knowledge rail, Shared Notion SSOT url, and "Notion webhook: shared operator-managed rail on this host". `managed_resource_lines`/`managed_resource_ref` build `[managed:resource-ref]` content; always appends "Credentials are intentionally omitted from plugin-managed context."

### Skills (the ArcLink skill set, `skills/*/SKILL.md`)
Installed skill set (user-agent default is 10; the Curator/operator home adds `arclink-upgrade-orchestrator` for 11): `arclink-first-contact`, `arclink-qmd-mcp`, `arclink-vaults`, `arclink-vault-reconciler`, `arclink-notion-knowledge`, `arclink-notion-mcp`, `arclink-ssot`, `arclink-ssot-connect`, `arclink-resources`, `arclink-academy` (+ `arclink-upgrade-orchestrator` for Curator). `notion-page-pdf-export` SHIPS in `skills/` with a working `bin/notion-page-pdf-export.py` companion but is NOT in any default install list — it is an optional, chromium-gated operator-enabled skill, not part of the 10/11 default set. The installed skills consistently teach: call `arclink-mcp` tools directly, leave `token` out (managed-context injects it), prefer brokered tools over raw filesystem/Notion. `arclink-vault-reconciler` enumerates the canonical managed prefixes: `[managed:arclink-skill-ref|vault-ref|resource-ref|qmd-ref|notion-ref|vault-topology|vault-landmarks|recall-stubs|notion-landmarks|notion-stub]`.

### Docs -> vault sync (feeds Agents_KB)
- `bin/sync-hermes-docs-into-vault.sh`: ArcLink docs -> `$VAULT_DIR/Agents_KB/arclink-docs` (`ARCLINK_DOCS_VAULT_DIR`, with legacy migration); Hermes runtime docs (ref `ARCLINK_HERMES_DOCS_REF`/`ARCLINK_HERMES_AGENT_REF`) -> `$VAULT_DIR/Agents_KB/hermes-agent-docs` (legacy `Repos/hermes-agent-docs`). These dirs are then qmd-indexed in the `vault` collection and become memory-synth source candidates.

---

## B. Proof-gated / fake-adapter / local-only

- **PG-NOTION**: any live external Notion mutation. Code default is `proof_mode="fake"` with injected `urlopen_fn`; `run_notion_ssot_no_secret_proof` marks `brokered_ssot_write_preflight`, `user_owned_oauth_status`, `live_workspace_mutation_status` as `proof_gated` unless an operator explicitly passes `authorized_live` + `allow_live_mutation`. Real `ssot.read`/`ssot.write` require a configured `ARCLINK_SSOT_NOTION_TOKEN` + verified Notion identity + in-scope target; unit tests never use a live token.
- **PG-HERMES**: live agent/workspace proof for the whole knowledge/memory contract (qmd indexing of a real vault, watcher-driven synthesis, managed-context injection in a live Hermes pod, self-healing on delete/move). Source + tests cover it locally; live workspace proof is gated.
- **Memory synthesis LLM** is optional: with no `ARCLINK_MEMORY_SYNTH_*`/`PDF_VISION_*` config it runs the deterministic `local-non-llm-fallback` (no network). The LLM path is configured-but-unproven on hosts without an endpoint.
- **Academy** (`academy.propose-resource`) records proposals to `academy_trainees`/Academy tables for Trainer review; live source acquisition + apply are `PG-PROVIDER`/`PG-HERMES` gated (per `docs/arclink/academy-trainer.md`).
- **Notion webhook funnel** (`bin/tailscale-notion-webhook-funnel.sh`) and live signature verification depend on operator-armed token install + a real Tailscale Funnel — local tests stub the transport.
- **PDF ingest / vault-pdf-ingest** collection presence depends on the PDF pipeline actually having run on the host; the MCP bridge tolerates its absence.

---

## C. Canonical vocabulary (exact names from code)

- Tables: `memory_synthesis_cards`, `notion_index_documents`, `notion_retrieval_audit`, `notion_parent_scope_cache`, `org_profile_revisions`, `org_profile_roles`, `org_profile_people`, `org_profile_teams`, `org_profile_relationships`, `arclink_webhook_events`, `pdf_ingest_manifest` (in `state/pdf-ingest/manifest.sqlite3`), `academy_trainees`. Setting key `org_profile_revision`.
- qmd collections: `vault`, `vault-pdf-ingest`, `notion-shared`.
- Managed-context section keys: `arclink-skill-ref`, `org-profile`, `user-responsibilities`, `team-map`, `vault-ref`, `resource-ref`, `qmd-ref`, `notion-ref`, `vault-topology`, `vault-landmarks`, `recall-stubs`, `notion-landmarks`, `notion-stub`, `today-plate`.
- MCP tools: see section A. Constants: `PROMPT_VERSION="memory-synth-v3"`, `LOCAL_FALLBACK_MODEL="local-non-llm-fallback"`, `DEFAULT_NOTION_API_VERSION="2026-03-11"`, `DEFAULT_GENERATED_PROFILE_PATH="Agents_KB/Operating_Context/org-profile.generated.md"`, SOUL markers `<!-- BEGIN/END ARCLINK ORG PROFILE -->`.
- Services/jobs: `arclink-ssot-batcher.service`, job `memory-synth`, job `notion-webhook-token`.
- Env vars: `ARCLINK_MEMORY_SYNTH_*` (ENABLED/ENDPOINT/MODEL/API_KEY/MAX_*/STATE_DIR/CARDS_IN_CONTEXT), `PDF_VISION_*` (fallback), `PDF_INGEST_MARKDOWN_DIR`, `ARCLINK_NOTION_INDEX_MARKDOWN_DIR`, `ARCLINK_NOTION_INDEX_COLLECTION_NAME`, `ARCLINK_SSOT_NOTION_TOKEN`, `ARCLINK_DOCS_VAULT_DIR`, `ARCLINK_HERMES_DOCS_REF`/`ARCLINK_HERMES_AGENT_REF`.
- Vault roots seeded: `Agents_KB` (+ `arclink-docs`, `hermes-agent-docs`, `Operating_Context`), `Agents_Skills`, `Agents_Plugins`, `Projects`, `Repos`, `Research`.

---

## D. Undocumented / newer-than-docs in code

1. **`knowledge.search` / `knowledge.search-and-fetch`** (source-agnostic vault+notion rails) — not described in `notion-human-guide.md`'s lane list as first-class; only appears in the managed example and SKILL recipes. The unified rail is the recommended first move in code (`skill_ref`).
2. **`vault.search-and-fetch` lex-only fallback** and **qmd-index-fallback for Notion fetch** (`fetch_source: "qmd-index-fallback"`, recovering `<page-id>-NNN.md`) — undocumented resilience behavior.
3. **Markdown YAML metadata duplication** (`_split_markdown_metadata_block`, `metadata_notice` about `SKILL.md`) and compatibility aliases `frontmatter`/`stripped_metadata` — undocumented.
4. **Operator-armed Notion webhook verification-token install** (arm/install/reset/verify state machine with 409/412 policy on a shared multi-user host) — not in `notion-human-guide.md`.
5. **Notion API version `2026-03-11` with data-source-aware queries** (`data_sources[0]`, legacy fallback, `create_database` via `initial_data_source`) — docs don't mention the data-source model.
6. **`org_member_unmatched` baseline context** + explicit "do not infer role/team from roster" managed text — newer than `docs/org-profile.md`, which doesn't describe the unmatched-agent fallback slice.
7. **`policies` top-level schema section** (privacy `default_people_visibility`, `agent_behavior`) and **`agent_lineage` baseline/modules/seed_sources with sha256 verification** — present in schema + render logic but only lightly referenced in `org-profile.md`.
8. **`today-plate` real-time awareness wording** ("webhook -> ssot batcher (sub-second nudge + 1 min timer) -> qmd reindex … within seconds") and `today_plate_item_ids` diffing — undocumented as a managed section in `org-profile.md` (it lists only org-profile/user-responsibilities/team-map).
9. **`pod_comms.*`, `shares.request`, `academy.propose-resource`** knowledge-adjacent MCP tools — not covered by the knowledge/Notion docs at all.
10. **Memory synth `disagreement_signals` / `contradiction_signals` / `trust_score`** card fields and `unsafe_output_rejected` flag — undocumented.
11. **Notion-page-pdf-export skill** auto-ingest into `vault-pdf-ingest` via headless chromium — only partially reflected in `notion-human-guide.md` PDF section.

---

## E. Per-doc staleness verdicts

### `docs/arclink/notion-human-guide.md` — staleness: light
- Correct on the three lanes (shared SSOT broker, indexed `notion-shared` knowledge, personal Notion MCP), destructive boundaries, and PDF/export fallback.
- Missing/needs adding: `knowledge.search-and-fetch` as the unified first-move rail; `ssot.preflight`, `ssot.pending`, `ssot.approve`, `ssot.deny` (only `ssot.read/write/status` are listed); the operator-armed webhook verification-token flow and the webhook->batcher->qmd "within seconds" pipeline; data-source-aware Notion API model. The "non-default OAuth/email-share-only" framing matches the proof harness exactly.

### `docs/org-profile.md` — staleness: light-to-moderate
- Accurate on commands (`validate/build/preview/apply/doctor`), file paths, fail-closed model, control-DB tables, SOUL overlay, identity state, `[managed:org-profile|user-responsibilities|team-map]`, vault render path, and that dynamic `[managed:*]` slices are NOT written to `MEMORY.md`.
- Corrections needed: add the **unmatched-agent baseline slice** (`org_member_unmatched`, "do not infer identity from roster"); add the **`policies` and `agent_lineage`** schema sections (privacy visibility gating of the vault render, baseline doctrine, seed-source sha256 verification); note `[managed:today-plate]` exists alongside the three slices it lists; the "Distribution Surfaces" preview example uses `org_profile_* tables` wording that matches `preview_payload` (good). The Preview/Apply receipt text is illustrative, not literal output.

### `docs/managed-memory-stubs-example.md` — staleness: fresh
- Matches code closely: recall-stub header lines (verbatim from `_build_recall_stubs`), subscribed-lane format, hot-reload signal format, `Semantic synthesis cards:` block (matches `_memory_synthesis_card_lines`), `[managed:vault-landmarks]` and `[managed:notion-stub]` examples (match `_build_*` functions). Correctly states dynamic context is hot-injected by `arclink-managed-context` and not written to `MEMORY.md`. Only gap: example state JSON omits some payload keys (`today_plate_item_ids`, `vault_landmark_items`) but explicitly flags itself as a fictionalized subset.

### `docs/hermes-qmd-config.yaml` — staleness: fresh
- Correct: qmd MCP at `http://127.0.0.1:8181/mcp`, tailnet URL form. Matches `arclink-qmd-mcp/SKILL.md` "local MCP endpoint: http://127.0.0.1:8181/mcp". (Note: the ArcLink control MCP is a separate port, e.g. 8282, not in this file — by design.)

### `skills/*/SKILL.md` — staleness: fresh (mostly)
- `arclink-ssot`, `arclink-notion-knowledge`, `arclink-vaults`, `arclink-qmd-mcp`, `arclink-resources`, `arclink-vault-reconciler`, `arclink-first-contact`, `arclink-academy`, `arclink-ssot-connect`, `arclink-notion-mcp`, `arclink-upgrade-orchestrator`, `notion-page-pdf-export` all align with current tools/contracts. The "Raven/operator" + `raw.githubusercontent.com/example/arclink` stale text in `arclink-resources` was already corrected (GAP Priority 5, now reads credentials-omitted + Curator/operator reset). Vault-reconciler's managed-prefix list matches `_MANAGED_MEMORY_KEYS`. Default collection `vault` + index name `arclink` match qmd config.

### `docs/arclink/sovereign-control-node-symphony.md` (dream-shape reference) — staleness: aligned-as-aspirational
- The "Hermes Skills And Tool Recipes" and "Agent Knowledge, Memory, And Docs" sections accurately describe the implemented contract and correctly scope live workspace proof to `PG-HERMES` and external Notion proof to `PG-NOTION`. It already states "Current source and tests cover much of this locally." No correction needed; it is honestly labeled as the intended shape with proof gates called out.

### `templates/arclink-priv/vault/*/README.md` — staleness: fresh
- Match seeded vault layout and the "convention not boundary" framing in `arclink-vault-reconciler`. `Agents_KB/README.md` references `hermes-agent-docs/` which matches the sync script target. `Repos/README.md` documents the hourly Curator hard-sync-to-upstream behavior (matches vault-repo-sync). No drift found.

---

## F. GAP-* / PG-* true status this subsystem touches

- **GAP Priority 5 (Knowledge Freshness And Generated Content Safety)** — checklist items all `[x]` in `research/RALPHIE_ARCLINK_ECOSYSTEM_GAP_REPAIR_STEERING.md` and confirmed in code:
  - PDF vision endpoint redaction from sidecar frontmatter — done (pipeline_signature hashed; no endpoint in `pdf_ingest_manifest` exposure).
  - **Full-source hashes for memory synthesis freshness** — done: `_file_content_hash` is a full sha256; `source_signature` over content-hash fingerprints (not size+mtime). Same-size/same-second rewrite refreshes cards.
  - PDF same-size/same-second rewrite detection — done (manifest uses `source_sha256`).
  - **DB claim/lock around SSOT batcher** — done: webhook stores events idempotently; batcher (`process_pending_notion_events`/`consume_notion_reindex_queue`) is the single claim path; `_kick_ssot_batcher` debounces and `arclink-ssot-batcher.service` serializes.
  - resources skill stale text + fallback URL — done.
- **GAP Priority 6** — "Add Notion human guide" `[x]` (`docs/arclink/notion-human-guide.md` exists, light staleness above). "Doc status map" and `org-profile.md` classification `[x]` (see `docs/document-phase-status.md`).
- **PG-NOTION** — OPEN. Live external Notion mutation proof remains gated; code default is fake/injected transport; per `research/BUILD_COMPLETION_NOTES.md` it "remains open until an operator-authorized proof window." The no-secret proof harness is the in-code representation.
- **PG-HERMES** — OPEN. Live agent/workspace proof (qmd-on-real-vault, watcher-driven synthesis, managed-context injection in a live pod, index self-healing) is gated; local source + tests cover it.

(Note: this subsystem's gaps are tracked under the descriptive Priority-5/6 checklist and the `PG-*` proof gates rather than numeric `GAP-0NN` ids; the numeric `GAP-032` upgrade gate and `GAP-033` bot gate are adjacent, not owned here.)
