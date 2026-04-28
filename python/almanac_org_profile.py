#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from string import Template
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "config" / "org-profile.schema.json"
SOUL_TEMPLATE_PATH = REPO_ROOT / "templates" / "SOUL.md.tmpl"
IDENTITY_STATE_FILENAME = "almanac-identity-context.json"
BEGIN_SOUL_MARKER = "<!-- BEGIN ALMANAC ORG PROFILE -->"
END_SOUL_MARKER = "<!-- END ALMANAC ORG PROFILE -->"
DEFAULT_GENERATED_PROFILE_PATH = "Agents_KB/Operating_Context/org-profile.generated.md"
STATE_SUBDIR = "org-profile"

UPSTREAM_SOUL_FALLBACK = (
    "You are Hermes Agent, an intelligent AI assistant created by Nous Research. "
    "You are helpful, knowledgeable, and direct. You assist users with a wide "
    "range of tasks including answering questions, writing and editing code, "
    "analyzing information, creative work, and executing actions via your tools. "
    "You communicate clearly, admit uncertainty when appropriate, and prioritize "
    "being genuinely useful over being verbose unless otherwise directed below. "
    "Be targeted and efficient in your exploration and investigations."
)

SECRET_KEY_TERMS = (
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "fingerprint",
    "jwt",
    "oauth",
    "password",
    "private_key",
    "secret",
    "token",
)
SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("OpenAI-style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Telegram bot token", re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{25,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_profile_path(cfg: Any) -> Path:
    return Path(cfg.private_dir) / "config" / "org-profile.yaml"


def state_dir(cfg: Any) -> Path:
    return Path(cfg.state_dir) / STATE_SUBDIR


def applied_profile_path(cfg: Any) -> Path:
    return state_dir(cfg) / "applied.json"


def last_apply_path(cfg: Any) -> Path:
    return state_dir(cfg) / "last-apply.json"


def agent_context_dir(cfg: Any) -> Path:
    return state_dir(cfg) / "agent-context"


def _atomic_write_text(path: Path, content: str, *, mode: int | None = None) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = ""
    try:
        previous = path.read_text(encoding="utf-8")
    except OSError:
        previous = ""
    if previous == content:
        if mode is not None:
            try:
                path.chmod(mode)
            except OSError:
                pass
        return False
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".almanac-org-profile-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return True


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_yaml_file(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised on hosts missing PyYAML
        raise RuntimeError("PyYAML is required for org-profile ingestion") from exc
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise FileNotFoundError(f"cannot read operating profile: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("operating profile must be a YAML object")
    return payload


def load_profile(path: Path) -> dict[str, Any]:
    return _read_yaml_file(path)


def _json_canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def profile_checksum(profile: dict[str, Any]) -> str:
    return hashlib.sha256(_json_canonical(profile).encode("utf-8")).hexdigest()


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_errors(profile: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised on hosts missing jsonschema
        return [f"jsonschema is required for schema validation: {exc}"]
    schema = _schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = []
    for error in sorted(validator.iter_errors(profile), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip()
    lowered = normalized.lower()
    if not normalized:
        return True
    if "..." in normalized or "example" in lowered or "placeholder" in lowered:
        return True
    if lowered in {"todo", "tbd", "changeme", "change-me", "redacted", "none", "null"}:
        return True
    if normalized.startswith("<") and normalized.endswith(">"):
        return True
    if normalized.startswith("cpk_"):
        return True
    return False


def _walk_values(value: object, path: str = "") -> Iterable[tuple[str, object]]:
    yield path or "<root>", value
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_values(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield from _walk_values(child, child_path)


def _secret_scan_errors(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, value in _walk_values(profile):
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or _is_placeholder_secret(normalized):
            continue
        leaf = path.rsplit(".", 1)[-1].lower()
        if any(term in leaf for term in SECRET_KEY_TERMS):
            errors.append(f"{path}: looks like a secret-bearing field; store secrets outside org-profile.yaml")
            continue
        for label, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(normalized):
                errors.append(f"{path}: looks like a {label}; remove it before ingestion")
                break
    return errors


def _list_ids(values: Sequence[dict[str, Any]], key: str = "id") -> list[str]:
    return [str(item.get(key) or "").strip() for item in values if isinstance(item, dict)]


def _semantic_report(profile: dict[str, Any], cfg: Any | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    roles = profile.get("roles") if isinstance(profile.get("roles"), dict) else {}
    people = profile.get("people") if isinstance(profile.get("people"), list) else []
    teams = profile.get("teams") if isinstance(profile.get("teams"), list) else []
    references = profile.get("references") if isinstance(profile.get("references"), list) else []

    person_ids = _list_ids(people)
    duplicate_people = sorted({person_id for person_id in person_ids if person_ids.count(person_id) > 1})
    if duplicate_people:
        errors.append(f"duplicate people ids: {', '.join(duplicate_people)}")
    people_by_id = {str(person.get("id") or ""): person for person in people if isinstance(person, dict)}

    team_ids = _list_ids(teams)
    duplicate_teams = sorted({team_id for team_id in team_ids if team_ids.count(team_id) > 1})
    if duplicate_teams:
        errors.append(f"duplicate team ids: {', '.join(duplicate_teams)}")
    teams_by_id = {str(team.get("id") or ""): team for team in teams if isinstance(team, dict)}

    ref_ids = _list_ids(references)
    duplicate_refs = sorted({ref_id for ref_id in ref_ids if ref_ids.count(ref_id) > 1})
    if duplicate_refs:
        errors.append(f"duplicate reference ids: {', '.join(duplicate_refs)}")

    for person in people:
        if not isinstance(person, dict):
            continue
        person_id = str(person.get("id") or "").strip()
        role = str(person.get("role") or "").strip()
        if role and role not in roles:
            errors.append(f"people.{person_id}.role references missing role: {role}")
        for team_id in person.get("teams") or []:
            if str(team_id) not in teams_by_id:
                errors.append(f"people.{person_id}.teams references missing team: {team_id}")
        primary_team = str(person.get("primary_team") or "").strip()
        if primary_team and primary_team not in teams_by_id:
            errors.append(f"people.{person_id}.primary_team references missing team: {primary_team}")
        agent = person.get("agent") if isinstance(person.get("agent"), dict) else {}
        serves = str(agent.get("serves") or "").strip()
        operating_mode = str(agent.get("operating_mode") or "personal_delegate").strip()
        if serves and serves != person_id and operating_mode in {"personal_delegate", "operator_delegate"}:
            errors.append(
                f"people.{person_id}.agent.serves is {serves}; personal/operator delegates must serve the containing person"
            )
        if not serves:
            warnings.append(f"people.{person_id}.agent.serves is empty; Almanac will treat it as serving {person_id}")
        accountability = person.get("human_accountability") if isinstance(person.get("human_accountability"), dict) else {}
        for target in accountability.get("escalate_to") or []:
            if str(target) not in people_by_id:
                errors.append(f"people.{person_id}.human_accountability.escalate_to references missing person: {target}")

    for team in teams:
        if not isinstance(team, dict):
            continue
        team_id = str(team.get("id") or "").strip()
        lead = str(team.get("lead") or "").strip()
        if lead and lead not in people_by_id:
            errors.append(f"teams.{team_id}.lead references missing person: {lead}")
        if not lead:
            warnings.append(f"teams.{team_id}.lead is empty")
        for member in team.get("members") or []:
            if str(member) not in people_by_id:
                errors.append(f"teams.{team_id}.members references missing person: {member}")
        for ref_id in team.get("knowledge_refs") or []:
            if str(ref_id) not in ref_ids:
                warnings.append(f"teams.{team_id}.knowledge_refs references unknown reference: {ref_id}")

    for reference in references:
        if not isinstance(reference, dict):
            continue
        ref_id = str(reference.get("id") or "").strip()
        ref_type = str(reference.get("type") or "markdown").strip()
        raw_path = str(reference.get("path") or "").strip()
        if ref_type in {"markdown", "repo"} and raw_path and cfg is not None:
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = Path(cfg.vault_dir) / raw_path
            if not candidate.exists():
                warnings.append(f"references.{ref_id}.path is not currently accessible: {raw_path}")

    return errors, warnings


def validate_profile(profile: dict[str, Any], cfg: Any | None = None) -> dict[str, Any]:
    schema_errors = _schema_errors(profile)
    semantic_errors, warnings = _semantic_report(profile, cfg)
    secret_errors = _secret_scan_errors(profile)
    errors = [*schema_errors, *semantic_errors, *secret_errors]
    return {
        "valid": not errors,
        "checksum": profile_checksum(profile),
        "errors": errors,
        "warnings": warnings,
    }


def load_and_validate(path: Path, cfg: Any | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = load_profile(path)
    report = validate_profile(profile, cfg)
    return profile, report


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text_list(lines: Sequence[str], *, prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{line}" for line in lines if line)


def _first_line(value: object, *, limit: int = 160) -> str:
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if line:
            return line[:limit]
    return ""


def _organization(profile: dict[str, Any]) -> dict[str, Any]:
    org = profile.get("organization")
    return org if isinstance(org, dict) else {}


def _policies(profile: dict[str, Any]) -> dict[str, Any]:
    policies = profile.get("policies")
    return policies if isinstance(policies, dict) else {}


def _lineage(profile: dict[str, Any]) -> dict[str, Any]:
    lineage = profile.get("agent_lineage")
    return lineage if isinstance(lineage, dict) else {}


def _work_surfaces(profile: dict[str, Any]) -> dict[str, Any]:
    surfaces = profile.get("work_surfaces")
    return surfaces if isinstance(surfaces, dict) else {}


def preview_payload(profile: dict[str, Any], *, cfg: Any | None = None, source_path: Path | None = None) -> dict[str, Any]:
    validation = validate_profile(profile, cfg)
    org = _organization(profile)
    people = _as_list(profile.get("people"))
    teams = _as_list(profile.get("teams"))
    references = _as_list(profile.get("references"))
    lineage = _lineage(profile)
    baseline = lineage.get("baseline") if isinstance(lineage.get("baseline"), dict) else {}
    return {
        "source": str(source_path or ""),
        "valid": validation["valid"],
        "checksum": validation["checksum"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "organization": {
            "id": org.get("id", ""),
            "name": org.get("name", ""),
            "profile_kind": org.get("profile_kind", ""),
            "scope": org.get("scope", ""),
            "mission": org.get("mission", ""),
            "primary_project": org.get("primary_project", ""),
        },
        "counts": {
            "roles": len(profile.get("roles") or {}),
            "people": len(people),
            "teams": len(teams),
            "relationships": len(_as_list(profile.get("relationships"))),
            "references": len(references),
        },
        "lineage": {
            "purpose": lineage.get("purpose", ""),
            "prototype_agent": lineage.get("prototype_agent", ""),
            "baseline_sections": sorted(baseline.keys()),
            "department_modules": [item.get("id", "") for item in _as_list(lineage.get("department_modules")) if isinstance(item, dict)],
            "function_modules": [item.get("id", "") for item in _as_list(lineage.get("function_modules")) if isinstance(item, dict)],
            "agent_modules": [item.get("id", "") for item in _as_list(lineage.get("agent_modules")) if isinstance(item, dict)],
        },
        "people": [
            {
                "id": person.get("id", ""),
                "display_name": person.get("display_name", ""),
                "role": person.get("role", ""),
                "teams": person.get("teams", []),
                "unix_user": person.get("unix_user", ""),
                "agent": (person.get("agent") or {}).get("name", "") if isinstance(person.get("agent"), dict) else "",
            }
            for person in people
            if isinstance(person, dict)
        ],
        "teams": [
            {
                "id": team.get("id", ""),
                "name": team.get("name", ""),
                "lead": team.get("lead", ""),
                "members": team.get("members", []),
            }
            for team in teams
            if isinstance(team, dict)
        ],
        "references": [
            {
                "id": reference.get("id", ""),
                "title": reference.get("title", ""),
                "type": reference.get("type", ""),
                "path": reference.get("path", ""),
                "audience": reference.get("audience", "all_agents"),
                "sensitivity": reference.get("sensitivity", "internal"),
            }
            for reference in references
            if isinstance(reference, dict)
        ],
        "distribution": {
            "control_database": "org_profile_* tables and settings.org_profile_revision",
            "state": "state/org-profile/applied.json plus per-agent context slices",
            "vault_render": generated_vault_profile_path(profile),
            "managed_memory": "[managed:org-profile], [managed:user-responsibilities], [managed:team-map]",
            "agent_identity": f"state/{IDENTITY_STATE_FILENAME} and SOUL managed overlay for matched agents",
        },
    }


def format_preview(payload: dict[str, Any]) -> str:
    lines = [
        "Operating profile preview",
        f"  Source:   {payload.get('source') or '(default)'}",
        f"  Valid:    {'yes' if payload.get('valid') else 'no'}",
        f"  Revision: sha256:{payload.get('checksum')}",
        "",
        "Operating Context",
        f"  {payload.get('organization', {}).get('name') or '(unnamed)'}",
    ]
    profile_kind = payload.get("organization", {}).get("profile_kind")
    if profile_kind:
        lines.append(f"  Kind: {profile_kind}")
    scope = payload.get("organization", {}).get("scope")
    if scope:
        lines.append(f"  Scope: {scope}")
    mission = payload.get("organization", {}).get("mission")
    if mission:
        lines.append(f"  Mission: {mission}")
    primary = payload.get("organization", {}).get("primary_project")
    if primary:
        lines.append(f"  Primary project: {primary}")
    lines.extend(["", "People"])
    for person in payload.get("people") or []:
        lines.append(
            "  "
            f"{person.get('id')} -> {person.get('display_name')}, "
            f"{person.get('role')}, teams={','.join(person.get('teams') or []) or '-'}, "
            f"unix={person.get('unix_user') or '-'}, agent={person.get('agent') or '-'}"
        )
    lines.extend(["", "Teams"])
    for team in payload.get("teams") or []:
        lines.append(
            "  "
            f"{team.get('id')} lead={team.get('lead') or '-'} "
            f"members={','.join(team.get('members') or []) or '-'}"
        )
    lineage = payload.get("lineage") or {}
    if lineage.get("purpose") or lineage.get("baseline_sections"):
        lines.extend(["", "Agent Lineage"])
        if lineage.get("purpose"):
            lines.append(f"  Purpose: {lineage.get('purpose')}")
        if lineage.get("prototype_agent"):
            lines.append(f"  Prototype: {lineage.get('prototype_agent')}")
        if lineage.get("baseline_sections"):
            lines.append(f"  Baseline sections: {', '.join(lineage.get('baseline_sections') or [])}")
        if lineage.get("department_modules"):
            lines.append(f"  Department modules: {', '.join(lineage.get('department_modules') or [])}")
        if lineage.get("function_modules"):
            lines.append(f"  Function modules: {', '.join(lineage.get('function_modules') or [])}")
        if lineage.get("agent_modules"):
            lines.append(f"  Agent modules: {', '.join(lineage.get('agent_modules') or [])}")
    lines.extend(["", "References"])
    for reference in payload.get("references") or []:
        lines.append(
            "  "
            f"{reference.get('id')} ({reference.get('type') or 'other'}, "
            f"{reference.get('sensitivity') or 'internal'}): {reference.get('path')}"
        )
    lines.extend(["", "Distribution"])
    for key, value in (payload.get("distribution") or {}).items():
        lines.append(f"  {key}: {value}")
    if payload.get("errors"):
        lines.extend(["", "Errors"])
        lines.extend(f"  - {item}" for item in payload.get("errors") or [])
    if payload.get("warnings"):
        lines.extend(["", "Warnings"])
        lines.extend(f"  - {item}" for item in payload.get("warnings") or [])
    return "\n".join(lines).rstrip()


def generated_vault_profile_path(profile: dict[str, Any]) -> str:
    surfaces = _work_surfaces(profile)
    vault = surfaces.get("vault") if isinstance(surfaces.get("vault"), dict) else {}
    return str(vault.get("generated_org_profile_path") or DEFAULT_GENERATED_PROFILE_PATH).strip()


def _generated_vault_abs_path(cfg: Any, profile: dict[str, Any]) -> Path:
    relative = generated_vault_profile_path(profile)
    path = Path(relative)
    if path.is_absolute():
        return path
    return Path(cfg.vault_dir) / path


def _safe_join(values: object) -> str:
    parts = _strings(values)
    return ", ".join(parts) if parts else "-"


def _role(profile: dict[str, Any], role_id: str) -> dict[str, Any]:
    roles = profile.get("roles") if isinstance(profile.get("roles"), dict) else {}
    role = roles.get(role_id)
    return role if isinstance(role, dict) else {}


def _people_by_id(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(person.get("id") or ""): person
        for person in _as_list(profile.get("people"))
        if isinstance(person, dict) and str(person.get("id") or "").strip()
    }


def _teams_by_id(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(team.get("id") or ""): team
        for team in _as_list(profile.get("teams"))
        if isinstance(team, dict) and str(team.get("id") or "").strip()
    }


def render_vault_profile(profile: dict[str, Any], *, source_path: Path | None = None) -> str:
    org = _organization(profile)
    checksum = profile_checksum(profile)
    lines: list[str] = [
        "# Almanac Operating Profile",
        "",
        "Generated from the private structured operating profile. The YAML profile is authoritative for roles, accountability, and agent boundaries.",
        "",
        f"- Context: {org.get('name') or '(unnamed)'}",
        f"- Kind: {org.get('profile_kind') or 'organization'}",
        f"- Scope: {org.get('scope') or '(unset)'}",
        f"- Mission: {org.get('mission') or '(unset)'}",
        f"- Primary project: {org.get('primary_project') or '(unset)'}",
        f"- Revision: sha256:{checksum}",
    ]
    if source_path is not None:
        lines.append(f"- Source file: {source_path}")
    lineage = _lineage(profile)
    if lineage:
        lines.extend(["", "## Agent Lineage", ""])
        if lineage.get("purpose"):
            lines.append(str(lineage["purpose"]))
            lines.append("")
        if lineage.get("prototype_agent"):
            lines.append(f"- Prototype agent: {lineage.get('prototype_agent')}")
        baseline = lineage.get("baseline") if isinstance(lineage.get("baseline"), dict) else {}
        for key in (
            "doctrine",
            "product_facts",
            "fact_caveats",
            "source_of_truth_discipline",
            "security_rules",
            "communication_style",
            "tool_use_expectations",
        ):
            values = _strings(baseline.get(key))
            if not values:
                continue
            title = key.replace("_", " ").title()
            lines.extend(["", f"### {title}", "", _text_list(values)])
        modules = (
            _as_list(lineage.get("department_modules"))
            + _as_list(lineage.get("function_modules"))
            + _as_list(lineage.get("agent_modules"))
        )
        if modules:
            lines.extend(["", "### Modules", ""])
            for module in modules:
                if not isinstance(module, dict):
                    continue
                lines.append(f"- {module.get('id')}: {module.get('name') or module.get('purpose') or ''}".rstrip())
    lines.extend(["", "## People And Agents", ""])
    for person in _as_list(profile.get("people")):
        if not isinstance(person, dict):
            continue
        role = _role(profile, str(person.get("role") or ""))
        agent = person.get("agent") if isinstance(person.get("agent"), dict) else {}
        lines.extend(
            [
                f"### {person.get('display_name') or person.get('id')}",
                "",
                f"- Person id: {person.get('id')}",
                f"- Role: {person.get('role')} - {_first_line(role.get('description'))}",
                f"- Teams: {_safe_join(person.get('teams'))}",
                f"- Agent: {agent.get('name') or '(unnamed)'}",
                f"- Agent purpose: {agent.get('purpose') or '(unset)'}",
            ]
        )
        public_context = _dict(person.get("public_context"))
        github = _dict(person.get("github"))
        if public_context.get("external_title"):
            lines.append(f"- External title: {public_context.get('external_title')}")
        if github.get("username"):
            lines.append(f"- GitHub: {github.get('username')}")
        visible_repos = [
            repo
            for repo in _as_list(github.get("primary_repos")) + _as_list(github.get("accessible_repos"))
            if isinstance(repo, dict) and str(repo.get("sensitivity") or "internal") != "restricted"
        ]
        if visible_repos:
            lines.extend(["", "GitHub / Repo Context:"])
            for repo in visible_repos[:8]:
                repo_name = repo.get("owner_repo") or repo.get("url") or repo.get("id")
                lines.append(f"- {repo_name}: {repo.get('purpose') or '(no purpose set)'}")
        responsibilities = _strings(person.get("responsibilities")) or _strings(role.get("responsibilities"))
        authority = _strings(person.get("decision_authority")) or _strings(role.get("decision_authority"))
        may_do = _strings(agent.get("may_do"))
        must_ask = _strings(agent.get("must_ask_before"))
        must_not = _strings(agent.get("must_not_do"))
        for heading, values in (
            ("Responsibilities", responsibilities),
            ("Decision Authority", authority),
            ("Agent May Do", may_do),
            ("Agent Must Ask Before", must_ask),
            ("Agent Must Not Do", must_not),
        ):
            if values:
                lines.extend(["", f"{heading}:", _text_list(values)])
        lines.append("")
    lines.extend(["## Teams", ""])
    for team in _as_list(profile.get("teams")):
        if not isinstance(team, dict):
            continue
        lines.extend(
            [
                f"### {team.get('name') or team.get('id')}",
                "",
                f"- Team id: {team.get('id')}",
                f"- Lead: {team.get('lead') or '(unset)'}",
                f"- Members: {_safe_join(team.get('members'))}",
            ]
        )
        responsibilities = _strings(team.get("responsibilities"))
        if responsibilities:
            lines.extend(["", "Responsibilities:", _text_list(responsibilities)])
        lines.append("")
    references = [
        reference
        for reference in _as_list(profile.get("references"))
        if isinstance(reference, dict) and str(reference.get("sensitivity") or "internal") != "restricted"
    ]
    if references:
        lines.extend(["## Supporting References", ""])
        for reference in references:
            lines.append(
                f"- {reference.get('id')}: {reference.get('title')} ({reference.get('type') or 'other'}) - {reference.get('path')}"
            )
    lines.extend(
        [
            "",
            "## Privacy",
            "",
            "Direct identifiers such as private emails, chat ids, tokens, OAuth credentials, cookies, and private keys are intentionally omitted from this generated render.",
            "",
        ]
    )
    return "\n".join(lines)


def _module_matches_person(module: dict[str, Any], person: dict[str, Any]) -> bool:
    person_id = str(person.get("id") or "").strip()
    role = str(person.get("role") or "").strip()
    teams = {str(value) for value in _as_list(person.get("teams"))}
    primary_team = str(person.get("primary_team") or "").strip()
    module_id = str(module.get("id") or "").strip()
    matches = {str(value) for value in _as_list(module.get("applies_to"))}
    for key in ("serves", "human_liaison", "owner"):
        if str(module.get(key) or "").strip() == person_id:
            return True
    if module_id and (module_id == role or module_id == primary_team or module_id in teams):
        return True
    if matches and (person_id in matches or role in matches or primary_team in matches or bool(matches & teams)):
        return True
    return False


def _agent_modules_for_person(profile: dict[str, Any], person: dict[str, Any]) -> list[dict[str, Any]]:
    lineage = _lineage(profile)
    modules = _as_list(lineage.get("department_modules")) + _as_list(lineage.get("function_modules")) + _as_list(lineage.get("agent_modules"))
    return [module for module in modules if isinstance(module, dict) and _module_matches_person(module, person)]


def _team_summaries(profile: dict[str, Any], person: dict[str, Any]) -> list[dict[str, Any]]:
    people = _people_by_id(profile)
    summaries: list[dict[str, Any]] = []
    for team_id in _as_list(person.get("teams")):
        team = _teams_by_id(profile).get(str(team_id))
        if not team:
            continue
        members = []
        for member_id in _as_list(team.get("members")):
            if str(member_id) == str(person.get("id")):
                continue
            member = people.get(str(member_id))
            if not member:
                continue
            members.append(
                {
                    "id": member.get("id", ""),
                    "display_name": member.get("display_name", ""),
                    "role": member.get("role", ""),
                    "title": member.get("title", ""),
                    "responsibilities": _strings(member.get("responsibilities"))[:5],
                }
            )
        summaries.append(
            {
                "id": team.get("id", ""),
                "name": team.get("name", ""),
                "lead": team.get("lead", ""),
                "responsibilities": _strings(team.get("responsibilities"))[:8],
                "members": members,
            }
        )
    return summaries


def agent_context_for_person(profile: dict[str, Any], person: dict[str, Any], *, agent_id: str = "") -> dict[str, Any]:
    org = _organization(profile)
    role = _role(profile, str(person.get("role") or ""))
    agent = person.get("agent") if isinstance(person.get("agent"), dict) else {}
    policies = _policies(profile)
    lineage = _lineage(profile)
    baseline = lineage.get("baseline") if isinstance(lineage.get("baseline"), dict) else {}
    return {
        "revision": profile_checksum(profile),
        "agent_id": agent_id,
        "person_id": person.get("id", ""),
        "human_display_name": person.get("display_name", ""),
        "preferred_name": person.get("preferred_name", ""),
        "role_id": person.get("role", ""),
        "role": role,
        "title": person.get("title", ""),
        "teams": person.get("teams", []),
        "primary_team": person.get("primary_team", ""),
        "contact": {
            "preferred_channels": _strings(_dict(person.get("contact")).get("preferred_channels")),
            "discord_handle": _dict(person.get("contact")).get("discord_handle", ""),
        },
        "public_context": _dict(person.get("public_context")),
        "github": _dict(person.get("github")),
        "organization": {
            "id": org.get("id", ""),
            "name": org.get("name", ""),
            "profile_kind": org.get("profile_kind", ""),
            "scope": org.get("scope", ""),
            "mission": org.get("mission", ""),
            "primary_project": org.get("primary_project", ""),
            "timezone": org.get("timezone", ""),
            "quiet_hours": org.get("quiet_hours", ""),
            "operating_principles": _strings(org.get("operating_principles")),
            "glossary": org.get("glossary", []),
        },
        "agent": {
            "name": agent.get("name", ""),
            "purpose": agent.get("purpose", ""),
            "serves": agent.get("serves") or person.get("id", ""),
            "operating_mode": agent.get("operating_mode", "personal_delegate"),
            "may_do": _strings(agent.get("may_do")),
            "should_proactively_watch": _strings(agent.get("should_proactively_watch")),
            "must_ask_before": _strings(agent.get("must_ask_before")),
            "must_not_do": _strings(agent.get("must_not_do")),
            "handoff_rules": _strings(agent.get("handoff_rules")),
            "success_criteria": _strings(agent.get("success_criteria")),
            "default_surfaces": _strings(agent.get("default_surfaces")),
        },
        "responsibilities": _strings(person.get("responsibilities")) or _strings(role.get("responsibilities")),
        "decision_authority": _strings(person.get("decision_authority")) or _strings(role.get("decision_authority")),
        "human_accountability": person.get("human_accountability") if isinstance(person.get("human_accountability"), dict) else {},
        "baseline": {
            "doctrine": _strings(baseline.get("doctrine")),
            "product_facts": _strings(baseline.get("product_facts")),
            "fact_caveats": _strings(baseline.get("fact_caveats")),
            "source_of_truth_discipline": _strings(baseline.get("source_of_truth_discipline")),
            "security_rules": _strings(baseline.get("security_rules")),
            "communication_style": _strings(baseline.get("communication_style")),
            "tool_use_expectations": _strings(baseline.get("tool_use_expectations")),
        },
        "modules": _agent_modules_for_person(profile, person),
        "teams_summary": _team_summaries(profile, person),
        "global_agent_policy": policies.get("agent_behavior", {}) if isinstance(policies.get("agent_behavior"), dict) else {},
        "work_surfaces": _work_surfaces(profile),
    }


def _match_person_for_agent(profile: dict[str, Any], *, agent_id: str = "", unix_user: str = "", display_name: str = "") -> dict[str, Any] | None:
    people = _as_list(profile.get("people"))
    normalized_unix = unix_user.strip().lower()
    normalized_display = display_name.strip().lower()
    for person in people:
        if not isinstance(person, dict):
            continue
        if normalized_unix and str(person.get("unix_user") or "").strip().lower() == normalized_unix:
            return person
    for person in people:
        if not isinstance(person, dict):
            continue
        agent = person.get("agent") if isinstance(person.get("agent"), dict) else {}
        candidates = {
            str(person.get("display_name") or "").strip().lower(),
            str(person.get("preferred_name") or "").strip().lower(),
            str(agent.get("name") or "").strip().lower(),
        }
        aliases = person.get("identity_hints", {}).get("aliases") if isinstance(person.get("identity_hints"), dict) else []
        candidates.update(str(alias).strip().lower() for alias in _as_list(aliases))
        if normalized_display and normalized_display in candidates:
            return person
    return None


def load_applied_profile(cfg: Any) -> dict[str, Any]:
    payload = _read_json_dict(applied_profile_path(cfg))
    profile = payload.get("profile")
    return profile if isinstance(profile, dict) else {}


def build_agent_context_for_row(profile: dict[str, Any], row: dict[str, Any] | sqlite3.Row) -> dict[str, Any] | None:
    agent_id = str(row["agent_id"] if "agent_id" in row.keys() else row.get("agent_id", "")).strip() if hasattr(row, "keys") else str(row.get("agent_id", "")).strip()
    unix_user = str(row["unix_user"] if "unix_user" in row.keys() else row.get("unix_user", "")).strip() if hasattr(row, "keys") else str(row.get("unix_user", "")).strip()
    display_name = str(row["display_name"] if "display_name" in row.keys() else row.get("display_name", "")).strip() if hasattr(row, "keys") else str(row.get("display_name", "")).strip()
    person = _match_person_for_agent(profile, agent_id=agent_id, unix_user=unix_user, display_name=display_name)
    if person is None:
        return None
    return agent_context_for_person(profile, person, agent_id=agent_id)


def _managed_org_profile_section(context: dict[str, Any]) -> str:
    org = context.get("organization") if isinstance(context.get("organization"), dict) else {}
    baseline = context.get("baseline") if isinstance(context.get("baseline"), dict) else {}
    lines = [
        "Operating profile:",
        f"- Context: {org.get('name') or '(unset)'}",
        f"- Kind: {org.get('profile_kind') or 'organization'}",
        f"- Mission: {org.get('mission') or '(unset)'}",
    ]
    if org.get("primary_project"):
        lines.append(f"- Primary project: {org.get('primary_project')}")
    if context.get("revision"):
        lines.append(f"- Applied profile revision: sha256:{context.get('revision')}")
    for heading, key in (
        ("Operating principles", "doctrine"),
        ("Product facts", "product_facts"),
        ("Fact caveats", "fact_caveats"),
        ("Source-of-truth discipline", "source_of_truth_discipline"),
        ("Security rules", "security_rules"),
        ("Communication style", "communication_style"),
        ("Tool-use expectations", "tool_use_expectations"),
    ):
        values = _strings(baseline.get(key))[:8]
        if values:
            lines.append(f"{heading}:")
            lines.extend(f"- {value}" for value in values)
    modules = context.get("modules") if isinstance(context.get("modules"), list) else []
    if modules:
        lines.append("Relevant modules:")
        for module in modules[:8]:
            if isinstance(module, dict):
                lines.append(f"- {module.get('id')}: {module.get('name') or module.get('purpose') or ''}".rstrip())
    return "\n".join(lines)


def _managed_user_responsibilities_section(context: dict[str, Any]) -> str:
    agent = context.get("agent") if isinstance(context.get("agent"), dict) else {}
    role = context.get("role") if isinstance(context.get("role"), dict) else {}
    lines = [
        "User responsibility and authority:",
        f"- Human served: {context.get('human_display_name') or context.get('person_id')}",
        f"- Role: {context.get('role_id') or '(unset)'} - {_first_line(role.get('description'))}",
    ]
    if context.get("title"):
        lines.append(f"- Title: {context.get('title')}")
    if context.get("teams"):
        lines.append(f"- Teams: {_safe_join(context.get('teams'))}")
    public_context = _dict(context.get("public_context"))
    github = _dict(context.get("github"))
    contact = _dict(context.get("contact"))
    if public_context.get("external_title") or github.get("username") or contact.get("discord_handle"):
        lines.append("Public/contact orientation:")
        if public_context.get("external_title"):
            lines.append(f"- External title: {public_context.get('external_title')}")
        if public_context.get("social_posture"):
            lines.append(f"- Social posture: {_first_line(public_context.get('social_posture'), limit=220)}")
        if contact.get("discord_handle"):
            lines.append(f"- Discord handle: {contact.get('discord_handle')}")
        if github.get("username"):
            lines.append(f"- GitHub username: {github.get('username')}")
        repos = [
            repo
            for repo in _as_list(github.get("primary_repos")) + _as_list(github.get("accessible_repos"))
            if isinstance(repo, dict)
        ]
        for repo in repos[:6]:
            repo_name = repo.get("owner_repo") or repo.get("url") or repo.get("id")
            lines.append(f"- Repo: {repo_name} ({repo.get('role') or 'unknown'}, {repo.get('permission') or 'unknown'})")
    for heading, key in (
        ("Responsibilities", "responsibilities"),
        ("Decision authority", "decision_authority"),
    ):
        values = _strings(context.get(key))[:10]
        if values:
            lines.append(f"{heading}:")
            lines.extend(f"- {value}" for value in values)
    lines.extend(
        [
            "Agent delegation:",
            f"- Agent name: {agent.get('name') or '(unset)'}",
            f"- Purpose: {agent.get('purpose') or '(unset)'}",
            f"- Operating mode: {agent.get('operating_mode') or 'personal_delegate'}",
        ]
    )
    for heading, key in (
        ("May do", "may_do"),
        ("Should proactively watch", "should_proactively_watch"),
        ("Must ask before", "must_ask_before"),
        ("Must not do", "must_not_do"),
        ("Handoff rules", "handoff_rules"),
    ):
        values = _strings(agent.get(key))[:10]
        if values:
            lines.append(f"{heading}:")
            lines.extend(f"- {value}" for value in values)
    return "\n".join(lines)


def _managed_team_map_section(context: dict[str, Any]) -> str:
    lines = ["Team map:"]
    summaries = context.get("teams_summary") if isinstance(context.get("teams_summary"), list) else []
    if not summaries:
        lines.append("- No team context is configured for this profile slice.")
        return "\n".join(lines)
    for team in summaries[:8]:
        if not isinstance(team, dict):
            continue
        lines.append(f"- {team.get('name') or team.get('id')}: lead={team.get('lead') or '(unset)'}")
        for responsibility in _strings(team.get("responsibilities"))[:5]:
            lines.append(f"  - responsibility: {responsibility}")
        members = team.get("members") if isinstance(team.get("members"), list) else []
        for member in members[:8]:
            if isinstance(member, dict):
                suffix = f", {member.get('title')}" if member.get("title") else ""
                lines.append(f"  - teammate: {member.get('display_name') or member.get('id')} ({member.get('role')}{suffix})")
    return "\n".join(lines)


def build_managed_sections_for_agent(cfg: Any, *, agent_id: str, unix_user: str, display_name: str) -> dict[str, Any]:
    profile = load_applied_profile(cfg)
    if not profile:
        return {}
    row = {"agent_id": agent_id, "unix_user": unix_user, "display_name": display_name}
    context = build_agent_context_for_row(profile, row)
    if not context:
        return {}
    return {
        "org-profile": _managed_org_profile_section(context),
        "user-responsibilities": _managed_user_responsibilities_section(context),
        "team-map": _managed_team_map_section(context),
        "org_profile_agent_context": context,
        "org_profile_revision": str(context.get("revision") or ""),
    }


def _identity_overlay(context: dict[str, Any]) -> dict[str, Any]:
    org = context.get("organization") if isinstance(context.get("organization"), dict) else {}
    agent = context.get("agent") if isinstance(context.get("agent"), dict) else {}
    return {
        "org_profile_revision": context.get("revision", ""),
        "person_id": context.get("person_id", ""),
        "human_display_name": context.get("human_display_name", ""),
        "preferred_name": context.get("preferred_name", ""),
        "role_id": context.get("role_id", ""),
        "title": context.get("title", ""),
        "teams": context.get("teams", []),
        "primary_team": context.get("primary_team", ""),
        "responsibilities": context.get("responsibilities", []),
        "decision_authority": context.get("decision_authority", []),
        "human_accountability": context.get("human_accountability", {}),
        "contact": context.get("contact", {}),
        "public_context": context.get("public_context", {}),
        "github": context.get("github", {}),
        "agent_delegation": agent,
        "org_name": org.get("name", ""),
        "org_profile_kind": org.get("profile_kind", ""),
        "org_scope": org.get("scope", ""),
        "org_mission": org.get("mission", ""),
        "org_primary_project": org.get("primary_project", ""),
        "org_timezone": org.get("timezone", ""),
        "org_quiet_hours": org.get("quiet_hours", ""),
    }


def render_soul_overlay(context: dict[str, Any]) -> str:
    org = context.get("organization") if isinstance(context.get("organization"), dict) else {}
    agent = context.get("agent") if isinstance(context.get("agent"), dict) else {}
    lines = [
        BEGIN_SOUL_MARKER,
        "Almanac operating-profile overlay:",
        f"- Revision: sha256:{context.get('revision') or ''}",
        f"- Context: {org.get('name') or '(unset)'}",
        f"- Kind: {org.get('profile_kind') or 'organization'}",
        f"- Mission: {org.get('mission') or '(unset)'}",
        f"- Human served: {context.get('human_display_name') or context.get('person_id')}",
        f"- Role: {context.get('role_id') or '(unset)'}",
        f"- Teams: {_safe_join(context.get('teams'))}",
        f"- Agent name: {agent.get('name') or '(unset)'}",
        f"- Agent purpose: {agent.get('purpose') or '(unset)'}",
        "",
        "Responsibilities:",
    ]
    responsibilities = _strings(context.get("responsibilities"))
    lines.extend(f"- {item}" for item in (responsibilities or ["Confirm responsibilities during onboarding."]))
    authority = _strings(context.get("decision_authority"))
    if authority:
        lines.extend(["", "Decision authority:"])
        lines.extend(f"- {item}" for item in authority)
    for heading, key in (
        ("Agent may do", "may_do"),
        ("Agent should proactively watch", "should_proactively_watch"),
        ("Agent must ask before", "must_ask_before"),
        ("Agent must not do", "must_not_do"),
        ("Handoff rules", "handoff_rules"),
    ):
        values = _strings(agent.get(key))
        if values:
            lines.extend(["", f"{heading}:"])
            lines.extend(f"- {item}" for item in values)
    baseline = context.get("baseline") if isinstance(context.get("baseline"), dict) else {}
    doctrine = _strings(baseline.get("doctrine"))[:8]
    if doctrine:
        lines.extend(["", "Shared baseline doctrine:"])
        lines.extend(f"- {item}" for item in doctrine)
    lines.extend([END_SOUL_MARKER, ""])
    return "\n".join(lines)


def merge_soul_overlay(existing: str, overlay: str) -> str:
    existing = existing.rstrip() + "\n" if existing.strip() else ""
    start = existing.find(BEGIN_SOUL_MARKER)
    end = existing.find(END_SOUL_MARKER)
    if start >= 0 and end >= start:
        end += len(END_SOUL_MARKER)
        merged = existing[:start].rstrip() + "\n\n" + overlay.strip() + "\n" + existing[end:].lstrip()
    else:
        merged = existing.rstrip() + "\n\n" + overlay.strip() + "\n"
    return merged


def materialize_agent_context(hermes_home: Path, context: dict[str, Any]) -> dict[str, Any]:
    state_path = hermes_home / "state" / "almanac-org-profile-context.json"
    identity_path = hermes_home / "state" / IDENTITY_STATE_FILENAME
    soul_path = hermes_home / "SOUL.md"
    changed: dict[str, Any] = {}

    context_body = json.dumps(context, indent=2, sort_keys=True) + "\n"
    changed["org_profile_context_changed"] = _atomic_write_text(state_path, context_body, mode=0o644)

    existing_identity = _read_json_dict(identity_path)
    identity = {**existing_identity, **_identity_overlay(context)}
    changed["identity_changed"] = _atomic_write_text(
        identity_path,
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        mode=0o600,
    )

    try:
        existing_soul = soul_path.read_text(encoding="utf-8")
    except OSError:
        existing_soul = ""
    soul = merge_soul_overlay(existing_soul, render_soul_overlay(context))
    changed["soul_changed"] = _atomic_write_text(soul_path, soul, mode=0o600)
    changed.update(
        {
            "org_profile_context_path": str(state_path),
            "identity_path": str(identity_path),
            "soul_path": str(soul_path),
            "changed": any(bool(changed.get(key)) for key in ("org_profile_context_changed", "identity_changed", "soul_changed")),
        }
    )
    return changed


def _upstream_soul_text() -> str:
    try:
        from hermes_cli.default_soul import DEFAULT_SOUL_MD  # type: ignore
    except Exception:
        text = UPSTREAM_SOUL_FALLBACK
    else:
        text = str(DEFAULT_SOUL_MD or "").strip() or UPSTREAM_SOUL_FALLBACK
    return " ".join(text.split())


def _render_base_soul(context: dict[str, Any], *, unix_user: str = "") -> str:
    org = context.get("organization") if isinstance(context.get("organization"), dict) else {}
    agent = context.get("agent") if isinstance(context.get("agent"), dict) else {}
    try:
        template = SOUL_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"missing SOUL template at {SOUL_TEMPLATE_PATH}: {exc}") from exc
    rendered = Template(template).substitute(
        {
            "upstream_soul": _upstream_soul_text(),
            "agent_label": agent.get("name") or "your Almanac agent",
            "unix_user": unix_user or "unknown",
            "user_name": context.get("human_display_name") or "your enrolled user",
            "org_name": org.get("name") or "the operating context you support",
            "org_mission": org.get("mission") or "Help the operating context stay coherent, responsive, and moving.",
            "org_primary_project": org.get("primary_project") or "the work your user puts in front of you",
            "org_timezone": org.get("timezone") or "Etc/UTC",
            "org_quiet_hours": org.get("quiet_hours") or "No quiet hours are configured yet; confirm before sending time-sensitive nudges.",
        }
    ).strip()
    return merge_soul_overlay(rendered, render_soul_overlay(context))


def render_soul_for_identity(
    *,
    cfg: Any,
    bot_name: str,
    unix_user: str,
    user_name: str = "",
    fallback_renderer: Any | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    profile = load_applied_profile(cfg)
    if not profile:
        return None, None
    row = {"agent_id": "", "unix_user": unix_user, "display_name": user_name or bot_name}
    context = build_agent_context_for_row(profile, row)
    if not context:
        return None, None
    agent = context.get("agent") if isinstance(context.get("agent"), dict) else {}
    if bot_name.strip() and not agent.get("name"):
        agent["name"] = bot_name.strip()
    rendered = _render_base_soul(context, unix_user=unix_user)
    return rendered, context


def identity_values_from_context(context: dict[str, Any]) -> dict[str, Any]:
    return _identity_overlay(context)


def ensure_org_profile_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS org_profile_revisions (
          revision TEXT PRIMARY KEY,
          source_path TEXT NOT NULL,
          organization_id TEXT NOT NULL DEFAULT '',
          organization_name TEXT NOT NULL DEFAULT '',
          checksum TEXT NOT NULL,
          profile_json TEXT NOT NULL,
          applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS org_profile_roles (
          role_id TEXT PRIMARY KEY,
          revision TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          payload_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS org_profile_people (
          person_id TEXT PRIMARY KEY,
          revision TEXT NOT NULL,
          unix_user TEXT NOT NULL DEFAULT '',
          display_name TEXT NOT NULL DEFAULT '',
          role_id TEXT NOT NULL DEFAULT '',
          primary_team TEXT NOT NULL DEFAULT '',
          agent_name TEXT NOT NULL DEFAULT '',
          payload_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS org_profile_teams (
          team_id TEXT PRIMARY KEY,
          revision TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          lead_person_id TEXT NOT NULL DEFAULT '',
          payload_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS org_profile_relationships (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          revision TEXT NOT NULL,
          subject TEXT NOT NULL,
          relation TEXT NOT NULL,
          object TEXT NOT NULL,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        """
    )


def _replace_profile_rows(conn: sqlite3.Connection, profile: dict[str, Any], *, source_path: Path, checksum: str) -> None:
    ensure_org_profile_schema(conn)
    org = _organization(profile)
    now = utc_now_iso()
    for table in (
        "org_profile_relationships",
        "org_profile_teams",
        "org_profile_people",
        "org_profile_roles",
        "org_profile_revisions",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.execute(
        """
        INSERT INTO org_profile_revisions (
          revision, source_path, organization_id, organization_name, checksum, profile_json, applied_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            checksum,
            str(source_path),
            str(org.get("id") or ""),
            str(org.get("name") or ""),
            checksum,
            json.dumps(profile, indent=2, sort_keys=True),
            now,
        ),
    )
    for role_id, role in (profile.get("roles") or {}).items():
        if isinstance(role, dict):
            conn.execute(
                "INSERT INTO org_profile_roles (role_id, revision, description, payload_json) VALUES (?, ?, ?, ?)",
                (str(role_id), checksum, str(role.get("description") or ""), json.dumps(role, indent=2, sort_keys=True)),
            )
    for person in _as_list(profile.get("people")):
        if not isinstance(person, dict):
            continue
        agent = person.get("agent") if isinstance(person.get("agent"), dict) else {}
        conn.execute(
            """
            INSERT INTO org_profile_people (
              person_id, revision, unix_user, display_name, role_id, primary_team, agent_name, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(person.get("id") or ""),
                checksum,
                str(person.get("unix_user") or ""),
                str(person.get("display_name") or ""),
                str(person.get("role") or ""),
                str(person.get("primary_team") or ""),
                str(agent.get("name") or ""),
                json.dumps(person, indent=2, sort_keys=True),
            ),
        )
    for team in _as_list(profile.get("teams")):
        if not isinstance(team, dict):
            continue
        conn.execute(
            "INSERT INTO org_profile_teams (team_id, revision, name, lead_person_id, payload_json) VALUES (?, ?, ?, ?, ?)",
            (
                str(team.get("id") or ""),
                checksum,
                str(team.get("name") or ""),
                str(team.get("lead") or ""),
                json.dumps(team, indent=2, sort_keys=True),
            ),
        )
    for relationship in _as_list(profile.get("relationships")):
        if not isinstance(relationship, dict):
            continue
        conn.execute(
            """
            INSERT INTO org_profile_relationships (revision, subject, relation, object, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                checksum,
                str(relationship.get("subject") or ""),
                str(relationship.get("relation") or ""),
                str(relationship.get("object") or ""),
                json.dumps(relationship, indent=2, sort_keys=True),
            ),
        )
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ('org_profile_revision', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (checksum, now),
    )
    conn.commit()


def _active_agent_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT agent_id, role, unix_user, display_name, hermes_home
        FROM agents
        WHERE role = 'user' AND status = 'active'
        ORDER BY agent_id
        """
    ).fetchall()


def apply_profile(
    conn: sqlite3.Connection,
    cfg: Any,
    *,
    profile: dict[str, Any],
    source_path: Path,
    actor: str = "operator",
) -> dict[str, Any]:
    validation = validate_profile(profile, cfg)
    if not validation["valid"]:
        return {
            "applied": False,
            "source": str(source_path),
            "checksum": validation["checksum"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        }
    checksum = str(validation["checksum"])
    _replace_profile_rows(conn, profile, source_path=source_path, checksum=checksum)

    state_dir(cfg).mkdir(parents=True, exist_ok=True)
    applied_body = json.dumps(
        {
            "revision": checksum,
            "source_path": str(source_path),
            "applied_at": utc_now_iso(),
            "applied_by": actor,
            "profile": profile,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    applied_changed = _atomic_write_text(applied_profile_path(cfg), applied_body, mode=0o600)

    vault_path = _generated_vault_abs_path(cfg, profile)
    vault_changed = _atomic_write_text(vault_path, render_vault_profile(profile, source_path=source_path), mode=0o644)

    matched_agents: list[dict[str, Any]] = []
    unmatched_agents: list[str] = []
    context_root = agent_context_dir(cfg)
    context_root.mkdir(parents=True, exist_ok=True)
    for row in _active_agent_rows(conn):
        context = build_agent_context_for_row(profile, row)
        agent_id = str(row["agent_id"] or "").strip()
        if not context:
            unmatched_agents.append(agent_id)
            continue
        context_body = json.dumps(context, indent=2, sort_keys=True) + "\n"
        path = context_root / f"{agent_id}.json"
        context_changed = _atomic_write_text(path, context_body, mode=0o644)
        matched_agents.append(
            {
                "agent_id": agent_id,
                "unix_user": str(row["unix_user"] or ""),
                "person_id": str(context.get("person_id") or ""),
                "context_path": str(path),
                "context_changed": context_changed,
            }
        )

    report = {
        "applied": True,
        "source": str(source_path),
        "revision": checksum,
        "checksum": checksum,
        "warnings": validation["warnings"],
        "state_file": str(applied_profile_path(cfg)),
        "state_changed": applied_changed,
        "generated_vault_doc": str(vault_path),
        "generated_vault_doc_changed": vault_changed,
        "matched_agents": matched_agents,
        "unmatched_active_agents": unmatched_agents,
        "counts": {
            "roles": len(profile.get("roles") or {}),
            "people": len(_as_list(profile.get("people"))),
            "teams": len(_as_list(profile.get("teams"))),
            "relationships": len(_as_list(profile.get("relationships"))),
        },
    }
    _atomic_write_text(last_apply_path(cfg), json.dumps(report, indent=2, sort_keys=True) + "\n", mode=0o600)
    return report


def doctor_profile(conn: sqlite3.Connection, cfg: Any, *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_org_profile_schema(conn)
    applied = load_applied_profile(cfg)
    source_profile = profile or applied
    validation = validate_profile(source_profile, cfg) if source_profile else {"valid": False, "errors": ["no applied profile found"], "warnings": []}
    revision_row = conn.execute("SELECT value FROM settings WHERE key = 'org_profile_revision'").fetchone()
    settings_revision = str(revision_row["value"] or "") if revision_row else ""
    applied_revision = profile_checksum(applied) if applied else ""
    active_rows = _active_agent_rows(conn)
    matched = []
    unmatched = []
    for row in active_rows:
        context = build_agent_context_for_row(source_profile, row) if source_profile else None
        agent_id = str(row["agent_id"] or "")
        if context:
            context_path = agent_context_dir(cfg) / f"{agent_id}.json"
            matched.append(
                {
                    "agent_id": agent_id,
                    "unix_user": str(row["unix_user"] or ""),
                    "person_id": str(context.get("person_id") or ""),
                    "context_exists": context_path.is_file(),
                }
            )
        else:
            unmatched.append(agent_id)
    generated = _generated_vault_abs_path(cfg, source_profile) if source_profile else Path("")
    return {
        "valid": validation.get("valid", False),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "settings_revision": settings_revision,
        "applied_revision": applied_revision,
        "state_file_exists": applied_profile_path(cfg).is_file(),
        "generated_vault_doc": str(generated) if source_profile else "",
        "generated_vault_doc_exists": generated.is_file() if source_profile else False,
        "matched_agents": matched,
        "unmatched_active_agents": unmatched,
    }
