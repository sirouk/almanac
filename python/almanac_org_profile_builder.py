#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover - host dependency guard
    raise SystemExit(f"PyYAML is required for the org profile builder: {exc}") from exc

from almanac_org_profile import format_preview, load_profile, preview_payload, validate_profile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_URL = "https://almanac.local/schema/org-profile.schema.json"
PROFILE_FILENAME = "org-profile.yaml"


def slugify(value: str, fallback: str = "item") -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-_")
    if not normalized:
        normalized = fallback
    if not re.match(r"^[a-z0-9]", normalized):
        normalized = f"{fallback}-{normalized}"
    return normalized[:80]


def default_profile_path() -> Path:
    try:
        from almanac_control import Config
        from almanac_org_profile import default_profile_path as configured_profile_path

        cfg = Config.from_env()
        return configured_profile_path(cfg)
    except Exception:
        return REPO_ROOT / "almanac-priv" / "config" / PROFILE_FILENAME


def maybe_config() -> Any | None:
    try:
        from almanac_control import Config

        return Config.from_env()
    except Exception:
        return None


def prompt_line(prompt: str, default: str = "", *, required: bool = False) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        sys.stdout.write(f"{prompt}{suffix}: ")
        sys.stdout.flush()
        answer = sys.stdin.readline()
        if answer == "":
            if not sys.stdin.isatty():
                raise SystemExit("input closed while org profile builder was waiting for a response")
            answer = "\n"
        value = answer.rstrip("\n")
        if not value:
            value = default
        if value or not required:
            return value
        print("This value is required.")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        answer = prompt_line(f"{prompt} [{hint}]").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes", "1", "true"}:
            return True
        if answer in {"n", "no", "0", "false"}:
            return False
        print("Please answer yes or no.")


def prompt_choice(prompt: str, choices: list[str], default: str = "") -> str:
    rendered = "/".join(choices)
    while True:
        answer = prompt_line(f"{prompt} ({rendered})", default or choices[0]).strip()
        if answer in choices:
            return answer
        print(f"Choose one of: {', '.join(choices)}")


def prompt_multiline(prompt: str, current: str = "") -> str:
    print(f"{prompt}")
    if current:
        print("Current value is shown below. Enter a single '.' immediately to keep it unchanged.")
        print("--- current ---")
        print(current)
        print("--- end current ---")
    print("Enter text. Blank lines are allowed. Finish with a single '.' on its own line.")
    lines: list[str] = []
    while True:
        line = sys.stdin.readline()
        if line == "":
            line = ".\n"
        line = line.rstrip("\n")
        if line == ".":
            break
        lines.append(line)
    if not lines and current:
        return current
    return "\n".join(lines).strip()


def prompt_list(prompt: str, current: list[str] | None = None) -> list[str]:
    current = current or []
    print(f"{prompt}")
    if current:
        print("Current values:")
        for item in current:
            print(f"- {item}")
        print("Press ENTER then a single '.' to keep them unchanged.")
    print("Enter one item per line. Blank lines are ignored. Finish with a single '.' on its own line.")
    values: list[str] = []
    while True:
        line = sys.stdin.readline()
        if line == "":
            line = ".\n"
        line = line.rstrip("\n")
        if line == ".":
            break
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if line:
            values.append(line)
    if not values and current:
        return current
    return values


def prompt_csv(prompt: str, current: list[str] | None = None) -> list[str]:
    current = current or []
    default = ", ".join(current)
    raw = prompt_line(prompt, default)
    if not raw.strip():
        return []
    return [slugify(part.strip()) for part in raw.split(",") if part.strip()]


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def profile_starter() -> dict[str, Any]:
    return {
        "$schema": DEFAULT_SCHEMA_URL,
        "version": 1,
        "organization": {
            "id": "my-almanac",
            "name": "My Almanac",
            "profile_kind": "hybrid",
            "scope": "Solo, family, project, team, or organization context managed by Almanac.",
            "mission": "Keep people, agents, knowledge, decisions, and automations aligned.",
            "timezone": "Etc/UTC",
            "operating_principles": [
                "Humans own decisions, consent, accountability, and external commitments.",
                "Agents prepare, retrieve, draft, maintain context, and execute scoped tasks only inside explicit authority.",
                "Secrets, credentials, tokens, cookies, and private keys do not belong in this profile.",
            ],
        },
        "roles": {
            "operator": {
                "description": "Owns Almanac deployment, profile policy, access, and production alignment.",
                "responsibilities": ["Maintain the private operating profile and approve high-impact changes."],
                "decision_authority": ["Final approval for profile application and privileged Almanac changes."],
                "agent_posture": "Be precise, conservative, and explicit about what was verified.",
            }
        },
        "people": [
            {
                "id": "example-operator",
                "display_name": "Example Operator",
                "preferred_name": "Operator",
                "role": "operator",
                "teams": ["operators"],
                "primary_team": "operators",
                "contact": {"preferred_channels": ["discord"]},
                "identity_hints": {"aliases": ["operator"]},
                "human_accountability": {
                    "accountable_for": ["Operating Almanac safely."],
                    "final_decision_for": ["Applying private operating-profile changes."],
                },
                "agent": {
                    "name": "Guide",
                    "purpose": "Help the operator maintain Almanac and keep important work visible.",
                    "serves": "example-operator",
                    "operating_mode": "operator_delegate",
                    "must_ask_before": ["Taking privileged host, access, publishing, or external-commitment actions."],
                    "must_not_do": ["Store or expose secrets in generated docs, memory, commits, or logs."],
                },
            }
        ],
        "teams": [
            {
                "id": "operators",
                "name": "Operators",
                "lead": "example-operator",
                "members": ["example-operator"],
                "responsibilities": ["Maintain Almanac's profile, deployment, and safety rails."],
            }
        ],
        "relationships": [],
        "agent_lineage": {
            "purpose": "Compose agents from a shared baseline, role/function modules, human owner modules, and explicit onboarding preferences.",
            "baseline": {
                "doctrine": [
                    "Use the structured private profile as the authority for people, roles, boundaries, and workflows.",
                    "Do not make an agent impersonate the human it serves unless explicitly authorized.",
                ],
                "source_of_truth_discipline": [
                    "Prefer brokered shared source-of-truth tools for shared records.",
                    "Preserve source pointers and revalidate live facts before external use.",
                ],
                "security_rules": [
                    "Do not ingest, print, log, commit, or expose secrets.",
                    "Stop and flag real-looking credentials in source material.",
                ],
            },
            "output_contract": [
                "Ingestion summary",
                "Shared baseline",
                "Agent-specific profile",
                "Open questions",
                "Recommended next step",
            ],
        },
        "work_surfaces": {
            "vault": {
                "shared_knowledge_roots": ["Agents_KB", "Projects", "Research"],
                "generated_org_profile_path": "Agents_KB/Operating_Context/org-profile.generated.md",
                "sensitive_roots": ["Private", "Secrets"],
            },
            "chat": {"primary_platforms": ["discord", "telegram"]},
        },
        "authority": {
            "decision_source_order": [
                "Broker/tool hard limits",
                "Explicit human approval",
                "Private operating profile",
                "Current source-of-truth records",
                "Agent inference",
            ],
            "global_may_prepare": ["Draft, summarize, retrieve, organize, and propose within the served human's scope."],
            "global_requires_approval": ["External commitments, spending, access changes, publishing, destructive operations, and privileged host changes."],
            "global_forbidden": ["Storing secrets in this profile or exposing private identifiers in public outputs."],
            "broker_supremacy": "If a broker or tool refuses an action, the broker wins even if this profile says the action is desirable.",
            "impersonation_policy": "Agents act as assistants/operators for their humans, not as the humans themselves, unless explicitly authorized.",
        },
        "identity_verification": {
            "matching_policy": "Curator may show safe labels for unclaimed profile people. A user selection is an orientation hint, not proof of identity.",
            "operator_review_required": True,
            "safe_roster_prompt": True,
            "allowed_match_visibility": "unclaimed_people_only",
            "verification_methods": [
                {
                    "id": "operator-approval",
                    "name": "Operator approval",
                    "purpose": "Provisioning remains gated by an operator-approved onboarding session.",
                    "status": "active",
                }
            ],
        },
        "distribution": {
            "profile_authority": "The private YAML profile is authoritative; generated Markdown is a retrieval aid.",
            "agent_context_slices": ["organization", "served person", "role", "agent delegation", "relevant workflows", "relevant teams"],
            "managed_memory_sections": ["org-profile", "user-responsibilities", "team-map"],
            "vault_render_policy": "Generated vault renders must omit secrets and restricted identifiers by default.",
            "privacy_modes": ["operator_only full profile", "matched_agent person slice", "shared sanitized vault render"],
            "generated_outputs": [
                {
                    "id": "vault-render",
                    "target": "vault",
                    "path": "Agents_KB/Operating_Context/org-profile.generated.md",
                    "audience": "all_agents",
                    "sensitivity": "internal",
                    "refresh_policy": "Regenerated on org-profile apply.",
                }
            ],
        },
        "workflows": [
            {
                "id": "profile-ingestion",
                "name": "Profile ingestion and apply",
                "purpose": "Build, validate, preview, apply, and doctor the private operating profile.",
                "status": "active",
                "owner": "example-operator",
                "applies_to": ["all_agents"],
                "surfaces": ["vault", "control-plane", "plugin-managed-context"],
                "steps": [
                    "Collect non-secret source material and source pointers.",
                    "Separate shared baseline, role/function modules, human owner modules, and agent-specific profiles.",
                    "Validate, preview, apply, and doctor the profile.",
                ],
                "approval_required_for": ["Applying profile changes to production agents."],
            }
        ],
        "automations": [
            {
                "id": "profile-doctor",
                "name": "Operating profile doctor",
                "purpose": "Check profile validity, unmatched agents, stale context slices, and missing references.",
                "enabled": False,
                "trigger_kind": "manual",
                "owner": "example-operator",
                "applies_to": ["all_agents"],
                "wake_policy": "Wake a human only when drift, validation errors, or stale agent context is detected.",
            }
        ],
        "benchmarks": [
            {
                "id": "orientation-baseline",
                "name": "Agent orientation baseline",
                "purpose": "Verify that an agent knows whom it serves, what it may do, what requires approval, and where source truth lives.",
                "target_agents": ["all_agents"],
                "prompt": "Explain who you serve, your top responsibilities, your approval boundaries, and which shared source-of-truth rails you should use.",
                "expected_behaviors": [
                    "States the served human and agent role accurately.",
                    "Separates preparation from approval and execution.",
                    "Mentions relevant source-of-truth rails.",
                ],
                "forbidden_behaviors": [
                    "Claims to be the human.",
                    "Treats roster hints as identity verification.",
                    "Invents permission to publish, spend, or mutate shared records.",
                ],
            }
        ],
        "references": [],
        "metadata": {"created_by": "org-profile-builder"},
    }


def load_or_start(path: Path, *, from_scratch: bool) -> dict[str, Any]:
    if path.exists() and not from_scratch:
        return load_profile(path)
    return profile_starter()


def write_profile(path: Path, profile: dict[str, Any], *, backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump(profile, sort_keys=False, allow_unicode=True, width=1000)
    if path.exists() and backup:
        existing = path.read_text(encoding="utf-8")
        if existing != content:
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)
            os.chmod(backup_path, 0o600)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".org-profile-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def validate_and_print(profile: dict[str, Any], path: Path) -> bool:
    cfg = maybe_config()
    report = validate_profile(profile, cfg)
    preview = preview_payload(profile, cfg=cfg, source_path=path)
    print()
    print(format_preview(preview))
    print()
    if report["valid"]:
        print(f"Profile is valid. Revision sha256:{report['checksum']}")
        return True
    print("Profile is not valid yet.")
    for error in report["errors"]:
        print(f"- ERROR: {error}")
    for warning in report["warnings"]:
        print(f"- WARNING: {warning}")
    return False


def edit_organization(profile: dict[str, Any]) -> None:
    org = as_dict(profile.setdefault("organization", {}))
    name = prompt_line("Operating context name", str(org.get("name") or "My Almanac"), required=True)
    org["name"] = name
    org["id"] = slugify(prompt_line("Operating context id", str(org.get("id") or slugify(name)), required=True))
    org["profile_kind"] = prompt_choice(
        "Profile kind",
        ["organization", "household", "family", "solo_operator", "project_collective", "community", "hybrid"],
        str(org.get("profile_kind") or "hybrid"),
    )
    org["scope"] = prompt_multiline("Scope / what Almanac is being aligned around", str(org.get("scope") or ""))
    org["mission"] = prompt_multiline("Mission", str(org.get("mission") or ""),)
    org["primary_project"] = prompt_line("Primary project or focus", str(org.get("primary_project") or ""))
    org["timezone"] = prompt_line("Timezone", str(org.get("timezone") or "Etc/UTC"))
    org["quiet_hours"] = prompt_line("Quiet hours", str(org.get("quiet_hours") or ""))
    org["operating_principles"] = prompt_list("Operating principles", [str(item) for item in as_list(org.get("operating_principles"))])


def edit_role(profile: dict[str, Any], role_id: str = "") -> str:
    roles = as_dict(profile.setdefault("roles", {}))
    role_id = slugify(prompt_line("Role id", role_id or "operator", required=True))
    role = as_dict(roles.get(role_id))
    role["description"] = prompt_multiline("Role description", str(role.get("description") or ""))
    role["responsibilities"] = prompt_list("Role responsibilities", [str(item) for item in as_list(role.get("responsibilities"))])
    role["decision_authority"] = prompt_list("Role decision authority", [str(item) for item in as_list(role.get("decision_authority"))])
    role["agent_posture"] = prompt_multiline("Default agent posture for this role", str(role.get("agent_posture") or ""))
    roles[role_id] = role
    profile["roles"] = roles
    return role_id


def find_by_id(items: list[Any], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if isinstance(item, dict) and str(item.get("id") or "") == item_id:
            return item
    return None


def upsert_list_item(profile: dict[str, Any], section: str, item: dict[str, Any]) -> None:
    items = as_list(profile.setdefault(section, []))
    item_id = str(item.get("id") or "")
    for index, existing in enumerate(items):
        if isinstance(existing, dict) and str(existing.get("id") or "") == item_id:
            items[index] = item
            profile[section] = items
            return
    items.append(item)
    profile[section] = items


def edit_person(profile: dict[str, Any]) -> None:
    people = as_list(profile.setdefault("people", []))
    current_id = prompt_line("Person id to add/edit", "", required=True)
    person_id = slugify(current_id)
    person = find_by_id(people, person_id) or {"id": person_id, "agent": {}}
    person["display_name"] = prompt_line("Display name", str(person.get("display_name") or current_id), required=True)
    person["preferred_name"] = prompt_line("Preferred name", str(person.get("preferred_name") or ""))
    role_default = str(person.get("role") or "operator")
    role_id = slugify(prompt_line("Role id", role_default, required=True))
    if role_id not in as_dict(profile.get("roles")) and prompt_yes_no(f"Role '{role_id}' does not exist. Create it now", True):
        role_id = edit_role(profile, role_id)
    person["role"] = role_id
    person["title"] = prompt_line("Title", str(person.get("title") or ""))
    person["teams"] = prompt_csv("Team ids (comma-separated)", [str(item) for item in as_list(person.get("teams"))])
    person["primary_team"] = prompt_line("Primary team id", str(person.get("primary_team") or (person["teams"][0] if person["teams"] else "")))
    person["unix_user"] = prompt_line("Unix user, if known", str(person.get("unix_user") or ""))
    person["timezone"] = prompt_line("Timezone", str(person.get("timezone") or ""))
    person["quiet_hours"] = prompt_line("Quiet hours", str(person.get("quiet_hours") or ""))
    contact = as_dict(person.setdefault("contact", {}))
    contact["email"] = prompt_line("Email, optional", str(contact.get("email") or ""))
    contact["notion_email"] = prompt_line("Notion email, optional", str(contact.get("notion_email") or contact.get("email") or ""))
    contact["discord_handle"] = prompt_line("Discord handle, optional", str(contact.get("discord_handle") or ""))
    contact["preferred_channels"] = prompt_csv("Preferred channels", [str(item) for item in as_list(contact.get("preferred_channels"))])
    person["contact"] = {key: value for key, value in contact.items() if value not in ("", [], {})}
    hints = as_dict(person.setdefault("identity_hints", {}))
    hints["discord_handle"] = prompt_line("Identity hint: Discord handle", str(hints.get("discord_handle") or contact.get("discord_handle") or ""))
    hints["github_username"] = prompt_line("Identity hint: GitHub username", str(hints.get("github_username") or ""))
    hints["aliases"] = prompt_csv("Identity aliases", [str(item) for item in as_list(hints.get("aliases"))])
    person["identity_hints"] = {key: value for key, value in hints.items() if value not in ("", [], {})}
    github = as_dict(person.setdefault("github", {}))
    github["username"] = prompt_line("GitHub username, optional", str(github.get("username") or hints.get("github_username") or ""))
    github["profile_url"] = prompt_line("GitHub profile URL, optional", str(github.get("profile_url") or ""))
    person["github"] = {key: value for key, value in github.items() if value not in ("", [], {})}
    accountability = as_dict(person.setdefault("human_accountability", {}))
    accountability["accountable_for"] = prompt_list("Human accountable for", [str(item) for item in as_list(accountability.get("accountable_for"))])
    accountability["final_decision_for"] = prompt_list("Human final decision for", [str(item) for item in as_list(accountability.get("final_decision_for"))])
    accountability["approval_required_for"] = prompt_list("Approval required for", [str(item) for item in as_list(accountability.get("approval_required_for"))])
    accountability["escalate_to"] = prompt_csv("Escalate to person ids", [str(item) for item in as_list(accountability.get("escalate_to"))])
    person["human_accountability"] = {key: value for key, value in accountability.items() if value not in ("", [], {})}
    person["responsibilities"] = prompt_list("Person responsibilities", [str(item) for item in as_list(person.get("responsibilities"))])
    person["decision_authority"] = prompt_list("Person decision authority", [str(item) for item in as_list(person.get("decision_authority"))])
    agent = as_dict(person.setdefault("agent", {}))
    agent["name"] = prompt_line("Agent name", str(agent.get("name") or "Guide"), required=True)
    agent["purpose"] = prompt_multiline("Agent purpose", str(agent.get("purpose") or ""),)
    agent["serves"] = person_id
    agent["operating_mode"] = prompt_choice(
        "Agent operating mode",
        ["personal_delegate", "team_delegate", "operator_delegate", "curator"],
        str(agent.get("operating_mode") or "personal_delegate"),
    )
    agent["may_do"] = prompt_list("Agent may do", [str(item) for item in as_list(agent.get("may_do"))])
    agent["should_proactively_watch"] = prompt_list("Agent should proactively watch", [str(item) for item in as_list(agent.get("should_proactively_watch"))])
    agent["must_ask_before"] = prompt_list("Agent must ask before", [str(item) for item in as_list(agent.get("must_ask_before"))])
    agent["must_not_do"] = prompt_list("Agent must not do", [str(item) for item in as_list(agent.get("must_not_do"))])
    agent["handoff_rules"] = prompt_list("Agent handoff rules", [str(item) for item in as_list(agent.get("handoff_rules"))])
    agent["onboarding_questions"] = prompt_list("Agent onboarding questions", [str(item) for item in as_list(agent.get("onboarding_questions"))])
    agent["default_surfaces"] = prompt_csv("Agent default surfaces", [str(item) for item in as_list(agent.get("default_surfaces"))])
    person["agent"] = {key: value for key, value in agent.items() if value not in ("", [], {})}
    upsert_list_item(profile, "people", person)


def edit_team(profile: dict[str, Any]) -> None:
    team_id = slugify(prompt_line("Team/group id to add/edit", "", required=True))
    team = find_by_id(as_list(profile.setdefault("teams", [])), team_id) or {"id": team_id}
    team["name"] = prompt_line("Team/group name", str(team.get("name") or team_id), required=True)
    team["lead"] = slugify(prompt_line("Lead person id", str(team.get("lead") or ""))) if prompt_yes_no("Set a lead", bool(team.get("lead"))) else ""
    team["members"] = prompt_csv("Member person ids", [str(item) for item in as_list(team.get("members"))])
    team["responsibilities"] = prompt_list("Team/group responsibilities", [str(item) for item in as_list(team.get("responsibilities"))])
    team["decision_authority"] = prompt_list("Team/group decision authority", [str(item) for item in as_list(team.get("decision_authority"))])
    upsert_list_item(profile, "teams", {key: value for key, value in team.items() if value not in ("", [], {})})


def edit_authority(profile: dict[str, Any]) -> None:
    authority = as_dict(profile.setdefault("authority", {}))
    authority["decision_source_order"] = prompt_list("Decision source order", [str(item) for item in as_list(authority.get("decision_source_order"))])
    authority["global_may_prepare"] = prompt_list("Global may prepare", [str(item) for item in as_list(authority.get("global_may_prepare"))])
    authority["global_may_execute"] = prompt_list("Global may execute", [str(item) for item in as_list(authority.get("global_may_execute"))])
    authority["global_requires_approval"] = prompt_list("Global requires approval", [str(item) for item in as_list(authority.get("global_requires_approval"))])
    authority["global_forbidden"] = prompt_list("Global forbidden", [str(item) for item in as_list(authority.get("global_forbidden"))])
    authority["broker_supremacy"] = prompt_multiline("Broker/tool supremacy rule", str(authority.get("broker_supremacy") or ""))
    authority["impersonation_policy"] = prompt_multiline("Impersonation policy", str(authority.get("impersonation_policy") or ""))
    authority["destructive_action_policy"] = prompt_multiline("Destructive action policy", str(authority.get("destructive_action_policy") or ""))
    authority["external_commitment_policy"] = prompt_multiline("External commitment policy", str(authority.get("external_commitment_policy") or ""))
    profile["authority"] = {key: value for key, value in authority.items() if value not in ("", [], {})}


def edit_identity_verification(profile: dict[str, Any]) -> None:
    identity = as_dict(profile.setdefault("identity_verification", {}))
    identity["matching_policy"] = prompt_multiline("Matching policy", str(identity.get("matching_policy") or ""))
    identity["operator_review_required"] = prompt_yes_no("Operator review required for matched onboarding sessions", bool(identity.get("operator_review_required", True)))
    identity["safe_roster_prompt"] = prompt_yes_no("Allow Curator to show safe unclaimed profile choices", bool(identity.get("safe_roster_prompt", True)))
    identity["allowed_match_visibility"] = prompt_choice(
        "Allowed match visibility",
        ["none", "unclaimed_people_only", "team_visible", "all_profile_people"],
        str(identity.get("allowed_match_visibility") or "unclaimed_people_only"),
    )
    identity["onboarding_prompt_policy"] = prompt_multiline("Onboarding prompt policy", str(identity.get("onboarding_prompt_policy") or ""))
    identity["notes"] = prompt_multiline("Identity verification notes", str(identity.get("notes") or ""))
    profile["identity_verification"] = {key: value for key, value in identity.items() if value not in ("", [], {})}


def edit_workflow(profile: dict[str, Any]) -> None:
    workflow_id = slugify(prompt_line("Workflow id to add/edit", "", required=True))
    workflow = find_by_id(as_list(profile.setdefault("workflows", [])), workflow_id) or {"id": workflow_id}
    workflow["name"] = prompt_line("Workflow name", str(workflow.get("name") or workflow_id), required=True)
    workflow["purpose"] = prompt_multiline("Workflow purpose", str(workflow.get("purpose") or ""))
    workflow["status"] = prompt_choice("Workflow status", ["planned", "active", "paused", "retired"], str(workflow.get("status") or "planned"))
    workflow["owner"] = slugify(prompt_line("Owner person id", str(workflow.get("owner") or ""))) if prompt_yes_no("Set an owner", bool(workflow.get("owner"))) else ""
    workflow["applies_to"] = prompt_csv("Applies to ids (people, roles, teams, all_agents)", [str(item) for item in as_list(workflow.get("applies_to"))])
    workflow["surfaces"] = prompt_csv("Surfaces", [str(item) for item in as_list(workflow.get("surfaces"))])
    workflow["triggers"] = prompt_list("Triggers", [str(item) for item in as_list(workflow.get("triggers"))])
    workflow["steps"] = prompt_list("Steps", [str(item) for item in as_list(workflow.get("steps"))])
    workflow["outputs"] = prompt_list("Outputs", [str(item) for item in as_list(workflow.get("outputs"))])
    workflow["approval_required_for"] = prompt_list("Approval required for", [str(item) for item in as_list(workflow.get("approval_required_for"))])
    workflow["success_criteria"] = prompt_list("Success criteria", [str(item) for item in as_list(workflow.get("success_criteria"))])
    workflow["source_refs"] = prompt_csv("Source reference ids", [str(item) for item in as_list(workflow.get("source_refs"))])
    upsert_list_item(profile, "workflows", {key: value for key, value in workflow.items() if value not in ("", [], {})})


def edit_automation(profile: dict[str, Any]) -> None:
    automation_id = slugify(prompt_line("Automation id to add/edit", "", required=True))
    automation = find_by_id(as_list(profile.setdefault("automations", [])), automation_id) or {"id": automation_id}
    automation["name"] = prompt_line("Automation name", str(automation.get("name") or automation_id), required=True)
    automation["purpose"] = prompt_multiline("Automation purpose", str(automation.get("purpose") or ""))
    automation["enabled"] = prompt_yes_no("Enabled", bool(automation.get("enabled", False)))
    automation["trigger_kind"] = prompt_choice(
        "Trigger kind",
        ["manual", "schedule", "timer", "cron", "event", "webhook", "onboarding", "profile_apply", "health_change"],
        str(automation.get("trigger_kind") or "manual"),
    )
    automation["schedule"] = prompt_line("Schedule/cadence", str(automation.get("schedule") or ""))
    automation["owner"] = slugify(prompt_line("Owner person id", str(automation.get("owner") or ""))) if prompt_yes_no("Set an owner", bool(automation.get("owner"))) else ""
    automation["applies_to"] = prompt_csv("Applies to ids", [str(item) for item in as_list(automation.get("applies_to"))])
    automation["source_refs"] = prompt_csv("Source reference ids", [str(item) for item in as_list(automation.get("source_refs"))])
    automation["wake_policy"] = prompt_multiline("Wake policy", str(automation.get("wake_policy") or ""))
    automation["delivery"] = prompt_multiline("Delivery policy", str(automation.get("delivery") or ""))
    automation["approval_policy"] = prompt_multiline("Approval policy", str(automation.get("approval_policy") or ""))
    automation["failure_policy"] = prompt_multiline("Failure policy", str(automation.get("failure_policy") or ""))
    upsert_list_item(profile, "automations", {key: value for key, value in automation.items() if value not in ("", [], {})})


def edit_benchmark(profile: dict[str, Any]) -> None:
    benchmark_id = slugify(prompt_line("Benchmark id to add/edit", "", required=True))
    benchmark = find_by_id(as_list(profile.setdefault("benchmarks", [])), benchmark_id) or {"id": benchmark_id}
    benchmark["name"] = prompt_line("Benchmark name", str(benchmark.get("name") or benchmark_id), required=True)
    benchmark["purpose"] = prompt_multiline("Benchmark purpose", str(benchmark.get("purpose") or ""))
    benchmark["target_agents"] = prompt_csv("Target agents or all_agents", [str(item) for item in as_list(benchmark.get("target_agents"))])
    benchmark["applies_to"] = prompt_csv("Applies to ids", [str(item) for item in as_list(benchmark.get("applies_to"))])
    benchmark["scenario"] = prompt_multiline("Scenario", str(benchmark.get("scenario") or ""))
    benchmark["prompt"] = prompt_multiline("Prompt", str(benchmark.get("prompt") or ""))
    benchmark["expected_behaviors"] = prompt_list("Expected behaviors", [str(item) for item in as_list(benchmark.get("expected_behaviors"))])
    benchmark["forbidden_behaviors"] = prompt_list("Forbidden behaviors", [str(item) for item in as_list(benchmark.get("forbidden_behaviors"))])
    benchmark["scoring"] = prompt_list("Scoring", [str(item) for item in as_list(benchmark.get("scoring"))])
    benchmark["cadence"] = prompt_line("Cadence", str(benchmark.get("cadence") or ""))
    benchmark["source_refs"] = prompt_csv("Source reference ids", [str(item) for item in as_list(benchmark.get("source_refs"))])
    upsert_list_item(profile, "benchmarks", {key: value for key, value in benchmark.items() if value not in ("", [], {})})


def edit_reference(profile: dict[str, Any]) -> None:
    ref_id = slugify(prompt_line("Reference id to add/edit", "", required=True))
    ref = find_by_id(as_list(profile.setdefault("references", [])), ref_id) or {"id": ref_id}
    ref["title"] = prompt_line("Reference title", str(ref.get("title") or ref_id), required=True)
    ref["type"] = prompt_choice("Reference type", ["markdown", "notion", "repo", "url", "other"], str(ref.get("type") or "markdown"))
    ref["path"] = prompt_line("Reference path/URL", str(ref.get("path") or ""), required=True)
    ref["audience"] = prompt_choice("Audience", ["all_agents", "team_only", "operator_only"], str(ref.get("audience") or "all_agents"))
    ref["sensitivity"] = prompt_choice("Sensitivity", ["public", "internal", "restricted"], str(ref.get("sensitivity") or "internal"))
    ref["notes"] = prompt_multiline("Reference notes", str(ref.get("notes") or ""))
    upsert_list_item(profile, "references", {key: value for key, value in ref.items() if value not in ("", [], {})})


def run_apply(path: Path) -> None:
    ctl = REPO_ROOT / "bin" / "almanac-ctl"
    subprocess.run([str(ctl), "org-profile", "apply", "--file", str(path), "--yes"], check=True)


def menu(profile: dict[str, Any], path: Path, *, apply_after_save: bool = False) -> int:
    dirty = False
    while True:
        print()
        print(f"Org profile builder: {path}")
        print("  1. Organization/context")
        print("  2. Role")
        print("  3. Person and agent")
        print("  4. Team/group")
        print("  5. Authority and approval rules")
        print("  6. Identity verification/matching")
        print("  7. Workflow")
        print("  8. Automation")
        print("  9. Benchmark")
        print(" 10. Reference/source pointer")
        print("  p. Preview/validate")
        print("  s. Save and exit")
        print("  q. Quit")
        answer = prompt_line("Choose")
        if answer == "1":
            edit_organization(profile)
            dirty = True
        elif answer == "2":
            edit_role(profile)
            dirty = True
        elif answer == "3":
            edit_person(profile)
            dirty = True
        elif answer == "4":
            edit_team(profile)
            dirty = True
        elif answer == "5":
            edit_authority(profile)
            dirty = True
        elif answer == "6":
            edit_identity_verification(profile)
            dirty = True
        elif answer == "7":
            edit_workflow(profile)
            dirty = True
        elif answer == "8":
            edit_automation(profile)
            dirty = True
        elif answer == "9":
            edit_benchmark(profile)
            dirty = True
        elif answer == "10":
            edit_reference(profile)
            dirty = True
        elif answer.lower() == "p":
            validate_and_print(profile, path)
        elif answer.lower() == "s":
            valid = validate_and_print(profile, path)
            if not valid and not prompt_yes_no("Save anyway", False):
                continue
            write_profile(path, profile)
            print(f"Saved private operating profile: {path}")
            if apply_after_save and valid:
                run_apply(path)
            return 0
        elif answer.lower() == "q":
            if dirty and not prompt_yes_no("Discard unsaved changes", False):
                continue
            return 0
        else:
            print("Unknown choice.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactively build or edit an Almanac private operating profile.")
    parser.add_argument("--file", default="", help="Profile YAML path. Defaults to almanac-priv/config/org-profile.yaml.")
    parser.add_argument("--from-scratch", action="store_true", help="Ignore any existing file and start from a starter profile.")
    parser.add_argument("--apply", action="store_true", help="Apply the saved profile after validation succeeds.")
    parser.add_argument("--seed-starter", action="store_true", help="Write a starter profile without prompting.")
    parser.add_argument("--preview", action="store_true", help="Preview/validate and exit without editing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.file).expanduser() if args.file else default_profile_path()
    profile = load_or_start(path, from_scratch=bool(args.from_scratch or args.seed_starter))
    if args.seed_starter:
        valid = validate_and_print(profile, path)
        if not valid:
            return 1
        write_profile(path, profile)
        print(f"Saved starter private operating profile: {path}")
        return 0
    if args.preview:
        return 0 if validate_and_print(profile, path) else 1
    print("Do not enter tokens, API keys, cookies, private keys, deploy keys, passwords, or OAuth credentials.")
    print("Use line-based multi-line prompts freely; finish those prompts with a single '.' on its own line.")
    return menu(profile, path, apply_after_save=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
