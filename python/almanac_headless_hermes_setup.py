#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from string import Template
import tempfile
from typing import Any

from almanac_model_providers import provider_default_model

REPO_ROOT = Path(__file__).resolve().parents[1]
SOUL_TEMPLATE_PATH = REPO_ROOT / "templates" / "SOUL.md.tmpl"
IDENTITY_STATE_FILENAME = "almanac-identity-context.json"
UPSTREAM_SOUL_FALLBACK = (
    "You are Hermes Agent, an intelligent AI assistant created by Nous Research. "
    "You are helpful, knowledgeable, and direct. You assist users with a wide "
    "range of tasks including answering questions, writing and editing code, "
    "analyzing information, creative work, and executing actions via your tools. "
    "You communicate clearly, admit uncertainty when appropriate, and prioritize "
    "being genuinely useful over being verbose unless otherwise directed below. "
    "Be targeted and efficient in your exploration and investigations."
)


def _load_provider_spec(raw_json: str) -> dict[str, Any]:
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise SystemExit("provider spec must be a json object")
    return payload


def _read_secret(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _ensure_model_config(default_model: str) -> dict[str, Any]:
    from hermes_cli.config import load_config

    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        payload = dict(model_cfg)
    elif isinstance(model_cfg, str) and model_cfg.strip():
        payload = {"default": model_cfg.strip()}
    else:
        payload = {}
    if not payload.get("default"):
        payload["default"] = default_model
    config["model"] = payload
    return config


def _normalized_reasoning_effort(spec: dict[str, Any]) -> str:
    raw = str(spec.get("reasoning_effort") or "").strip().lower().replace(" ", "")
    aliases = {
        "default": "medium",
        "recommended": "medium",
        "normal": "medium",
        "standard": "medium",
        "med": "medium",
        "extra": "xhigh",
        "extrahigh": "xhigh",
        "veryhigh": "xhigh",
        "max": "xhigh",
        "maximum": "xhigh",
        "off": "none",
        "disabled": "none",
        "disable": "none",
    }
    raw = aliases.get(raw, raw)
    return raw if raw in {"minimal", "low", "medium", "high", "xhigh", "none"} else ""


def _write_reasoning_effort(spec: dict[str, Any]) -> None:
    from hermes_cli.config import load_config, save_config

    effort = _normalized_reasoning_effort(spec)
    if not effort:
        return
    config = load_config()
    agent_cfg = config.get("agent")
    if not isinstance(agent_cfg, dict):
        agent_cfg = {}
    agent_cfg["reasoning_effort"] = effort
    config["agent"] = agent_cfg
    save_config(config)


def _path_key(path_value: str) -> str:
    expanded = os.path.expanduser(os.path.expandvars(str(path_value or "").strip()))
    if not expanded:
        return ""
    path = Path(expanded)
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def _external_dirs_list(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        raw_values = [raw_value]
    elif isinstance(raw_value, list):
        raw_values = raw_value
    else:
        raw_values = []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value or "").strip()
        key = _path_key(text)
        if not text or not key or key in seen:
            continue
        result.append(text)
        seen.add(key)
    return result


def _org_skill_library_bases(hermes_home: Path) -> list[Path]:
    bases: list[Path] = []
    for env_key in ("ALMANAC_SHARED_SKILLS_DIR",):
        value = str(os.environ.get(env_key) or "").strip()
        if value:
            bases.append(Path(value).expanduser())
    for env_key in ("ALMANAC_AGENT_VAULT_DIR", "VAULT_DIR"):
        value = str(os.environ.get(env_key) or "").strip()
        if value:
            bases.append(Path(value).expanduser() / "Agents_Skills")
    home = Path(os.environ.get("HOME") or str(Path.home())).expanduser()
    bases.extend(
        [
            home / "Almanac" / "Agents_Skills",
            hermes_home / "Almanac" / "Agents_Skills",
            hermes_home / "Vault" / "Agents_Skills",
        ]
    )
    result: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        key = _path_key(str(base))
        if not key or key in seen:
            continue
        result.append(base)
        seen.add(key)
    return result


def _discover_org_skill_external_dirs(hermes_home: Path) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()
    for base in _org_skill_library_bases(hermes_home):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir(), key=lambda path: path.name.lower()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            skill_root = child / "skills"
            if not skill_root.is_dir() or not any(skill_root.rglob("SKILL.md")):
                continue
            key = _path_key(str(skill_root))
            if not key or key in seen:
                continue
            discovered.append(str(skill_root))
            seen.add(key)
    return discovered


def _ensure_org_skill_external_dirs(skills_cfg: dict[str, Any], hermes_home: Path) -> list[str]:
    discovered = _discover_org_skill_external_dirs(hermes_home)
    existing = _external_dirs_list(skills_cfg.get("external_dirs"))
    merged = list(existing)
    seen = {_path_key(value) for value in existing}
    added: list[str] = []
    for value in discovered:
        key = _path_key(value)
        if not key or key in seen:
            continue
        merged.append(value)
        added.append(value)
        seen.add(key)
    skills_cfg["external_dirs"] = merged
    return added


def _seed_openai_codex(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.auth import _save_codex_tokens, _update_config_for_provider

    payload = json.loads(_read_secret(secret_path))
    if not isinstance(payload, dict):
        raise SystemExit("codex secret payload is invalid")
    tokens = {
        "access_token": str(payload.get("access_token") or ""),
        "refresh_token": str(payload.get("refresh_token") or ""),
    }
    if not tokens["access_token"] or not tokens["refresh_token"]:
        raise SystemExit("codex secret payload is missing tokens")
    _save_codex_tokens(tokens, last_refresh=str(payload.get("last_refresh") or "") or None)
    _update_config_for_provider(
        "openai-codex",
        str(payload.get("base_url") or spec.get("base_url") or ""),
        default_model=str(spec.get("model_id") or provider_default_model("codex") or "gpt-5.5"),
    )


def _seed_anthropic(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.config import (
        load_config,
        save_anthropic_api_key,
        save_anthropic_oauth_token,
        save_config,
        use_anthropic_claude_code_credentials,
    )

    secret = _read_secret(secret_path)
    try:
        credential_payload = json.loads(secret)
    except json.JSONDecodeError:
        credential_payload = None
    if isinstance(credential_payload, dict) and credential_payload.get("kind") == "claude_code_oauth":
        from agent.anthropic_adapter import _write_claude_code_credentials

        access_token = str(credential_payload.get("accessToken") or "").strip()
        refresh_token = str(credential_payload.get("refreshToken") or "").strip()
        try:
            expires_at_ms = int(credential_payload.get("expiresAt") or 0)
        except (TypeError, ValueError):
            expires_at_ms = 0
        scopes_raw = credential_payload.get("scopes")
        scopes = [str(scope).strip() for scope in scopes_raw if str(scope).strip()] if isinstance(scopes_raw, list) else None
        if not access_token or not refresh_token or expires_at_ms <= 0:
            raise SystemExit("Claude Code OAuth credential payload is incomplete")
        _write_claude_code_credentials(
            access_token,
            refresh_token,
            expires_at_ms,
            scopes=scopes,
        )
        use_anthropic_claude_code_credentials()
    elif secret.startswith("sk-ant-api-"):
        save_anthropic_api_key(secret)
    else:
        save_anthropic_oauth_token(secret)

    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        payload = dict(model_cfg)
    elif isinstance(model_cfg, str) and model_cfg.strip():
        payload = {"default": model_cfg.strip()}
    else:
        payload = {}
    payload["provider"] = "anthropic"
    payload["default"] = str(spec.get("model_id") or provider_default_model("opus") or "claude-opus-4-7")
    payload.pop("base_url", None)
    config["model"] = payload
    save_config(config)


def _seed_custom_provider(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.config import load_config, save_config, save_env_value

    provider_id = str(spec.get("provider_id") or "").strip()
    key_env = str(spec.get("key_env") or "").strip()
    base_url = str(spec.get("base_url") or "").strip()
    model_id = str(spec.get("model_id") or "").strip()
    api_mode = str(spec.get("api_mode") or "").strip() or "chat_completions"
    display_name = str(spec.get("display_name") or provider_id).strip() or provider_id
    if not provider_id or not key_env or not base_url or not model_id:
        raise SystemExit("custom provider spec is incomplete")

    save_env_value(key_env, _read_secret(secret_path))
    config = _ensure_model_config(model_id)
    providers = config.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    providers[provider_id] = {
        "name": display_name,
        "base_url": base_url,
        "key_env": key_env,
        "default_model": model_id,
        "api_mode": api_mode,
    }
    config["providers"] = providers
    model_cfg = dict(config.get("model") or {})
    model_cfg["provider"] = provider_id
    model_cfg["default"] = model_id
    model_cfg["base_url"] = base_url
    model_cfg["api_mode"] = api_mode
    config["model"] = model_cfg
    save_config(config)


def _seed_api_key_provider(spec: dict[str, Any], secret_path: str) -> None:
    from hermes_cli.auth import _update_config_for_provider
    from hermes_cli.config import save_env_value

    provider_id = str(spec.get("provider_id") or "").strip()
    key_env = str(spec.get("key_env") or "").strip()
    model_id = str(spec.get("model_id") or "").strip()
    if not provider_id or not key_env or not model_id:
        raise SystemExit("api-key provider spec is incomplete")

    save_env_value(key_env, _read_secret(secret_path))
    _update_config_for_provider(
        provider_id,
        str(spec.get("base_url") or ""),
        default_model=model_id,
    )


def _config_value(name: str, default: str = "") -> str:
    try:
        from almanac_control import config_env_value
    except Exception:
        return str(os.environ.get(name, default) or default)
    return str(config_env_value(name, default) or default)


def _identity_value(value: str, default: str) -> str:
    normalized = value.strip()
    return normalized or default


def _upstream_soul_text() -> str:
    try:
        from hermes_cli.default_soul import DEFAULT_SOUL_MD
    except Exception:
        text = UPSTREAM_SOUL_FALLBACK
    else:
        text = str(DEFAULT_SOUL_MD or "").strip() or UPSTREAM_SOUL_FALLBACK
    return " ".join(text.split())


def _org_profile_soul_and_context(bot_name: str, unix_user: str, user_name: str = "") -> tuple[str | None, dict[str, Any] | None]:
    try:
        from almanac_control import Config
        from almanac_org_profile import render_soul_for_identity

        return render_soul_for_identity(
            cfg=Config.from_env(),
            bot_name=bot_name,
            unix_user=unix_user,
            user_name=user_name,
        )
    except Exception:
        return None, None


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".almanac-identity-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _render_soul(bot_name: str, unix_user: str, user_name: str = "") -> str:
    org_profile_soul, _ = _org_profile_soul_and_context(bot_name, unix_user, user_name)
    if org_profile_soul:
        return org_profile_soul
    try:
        template = SOUL_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"missing SOUL template at {SOUL_TEMPLATE_PATH}: {exc}") from exc
    try:
        return (
            Template(template).substitute(
                {
                    "upstream_soul": _upstream_soul_text(),
                    "agent_label": _identity_value(bot_name, "your Almanac agent"),
                    "unix_user": _identity_value(unix_user, "unknown"),
                    "user_name": _identity_value(user_name, "your enrolled user"),
                    "org_name": _identity_value(_config_value("ALMANAC_ORG_NAME"), "the organization you support"),
                    "org_mission": _identity_value(
                        _config_value("ALMANAC_ORG_MISSION"),
                        "Help the organization stay coherent, responsive, and moving.",
                    ),
                    "org_primary_project": _identity_value(
                        _config_value("ALMANAC_ORG_PRIMARY_PROJECT"),
                        "the work your user puts in front of you",
                    ),
                    "org_timezone": _identity_value(_config_value("ALMANAC_ORG_TIMEZONE", "Etc/UTC"), "Etc/UTC"),
                    "org_quiet_hours": _identity_value(
                        _config_value("ALMANAC_ORG_QUIET_HOURS"),
                        "No quiet hours are configured yet; confirm before sending time-sensitive nudges.",
                    ),
                }
            ).strip()
            + "\n"
        )
    except KeyError as exc:
        raise SystemExit(f"SOUL template placeholder '{exc.args[0]}' is missing from the render context") from exc


def _seed_almanac_identity(bot_name: str, unix_user: str, user_name: str = "") -> dict[str, str]:
    from hermes_cli.config import load_config, save_config

    almanac_skill_names = [
        "almanac-qmd-mcp",
        "almanac-vault-reconciler",
        "almanac-first-contact",
        "almanac-vaults",
        "almanac-ssot",
        "almanac-notion-knowledge",
        "almanac-ssot-connect",
        "almanac-notion-mcp",
        "almanac-resources",
    ]
    almanac_plugin_names = [
        "almanac-managed-context",
    ]
    label = bot_name.strip() or "your Almanac agent"
    unix_user = unix_user.strip()
    user_name = user_name.strip()
    hermes_home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    state_dir = hermes_home / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    soul_path = hermes_home / "SOUL.md"
    prefill_path = state_dir / "almanac-prefill-messages.json"
    identity_state_path = state_dir / IDENTITY_STATE_FILENAME
    org_name = _identity_value(_config_value("ALMANAC_ORG_NAME"), "the organization you support")
    org_mission = _identity_value(
        _config_value("ALMANAC_ORG_MISSION"),
        "Help the organization stay coherent, responsive, and moving.",
    )
    org_primary_project = _identity_value(
        _config_value("ALMANAC_ORG_PRIMARY_PROJECT"),
        "the work your user puts in front of you",
    )
    org_timezone = _identity_value(_config_value("ALMANAC_ORG_TIMEZONE", "Etc/UTC"), "Etc/UTC")
    org_quiet_hours = _identity_value(
        _config_value("ALMANAC_ORG_QUIET_HOURS"),
        "No quiet hours are configured yet; confirm before sending time-sensitive nudges.",
    )
    org_profile_soul, org_profile_context = _org_profile_soul_and_context(label, unix_user, user_name)
    # Hermes reads HERMES_HOME/SOUL.md directly at runtime as the durable identity prompt.
    _atomic_write_text(soul_path, org_profile_soul or _render_soul(label, unix_user, user_name))
    identity_payload: dict[str, Any] = {
        "agent_label": label,
        "unix_user": unix_user,
        "user_name": user_name,
        "org_name": org_name,
        "org_mission": org_mission,
        "org_primary_project": org_primary_project,
        "org_timezone": org_timezone,
        "org_quiet_hours": org_quiet_hours,
    }
    if org_profile_context:
        try:
            from almanac_org_profile import identity_values_from_context

            identity_payload.update(identity_values_from_context(org_profile_context))
        except Exception:
            pass
    _atomic_write_text(
        identity_state_path,
        json.dumps(identity_payload, indent=2, sort_keys=True) + "\n",
    )
    prefill_messages = [
        {
            "role": "system",
            "content": (
                f"Your public-facing bot name is {label}. Introduce yourself as {label}, "
                "not Hermes, unless you are explicitly explaining that Hermes is the runtime "
                "you run on. Your durable identity lives at HERMES_HOME/SOUL.md; read it first "
                "and let it lead."
                + (f" You are the dedicated Almanac user agent for unix user {unix_user}." if unix_user else " You are an Almanac user agent on a shared host.")
                + (f" Your user is {user_name}." if user_name else "")
                + " Treat the installed Almanac skills and Curator-managed [managed:*] memory "
                "entries as active defaults, not passive extras. Use qmd and the wired Almanac "
                "resources for depth instead of improvising a parallel system. Keep the layers "
                "straight: a skill tells you the right workflow and guardrails; the wired broker "
                "or MCP rail performs the actual read or write. Do not decide that a capability "
                "is missing just because raw env vars are absent in a chat turn; rely on the "
                "installed skills, managed stubs, and Almanac-provisioned rails first. Treat "
                "private/shared-vault questions as qmd-first work: start with [managed:qmd-ref] "
                "and the current user's local Almanac state, not repo-wide searches to rediscover "
                "the rail. Only inspect deployment docs or qmd daemon files if the qmd path "
                "itself fails or the user is explicitly debugging Almanac. Treat "
                "[managed:resource-ref], [managed:notion-ref], [managed:recall-stubs], [managed:notion-stub], and [managed:today-plate] as the authoritative shared-rail "
                "snapshot even when human-facing setup copy leaves machine-facing rails out for "
                "brevity. The almanac-managed-context plugin can inject refreshed local Almanac "
                "context into future turns without requiring /reset or a gateway restart once it "
                "has been loaded. If a "
                "brokered action is denied, explain the concrete scope, verification, or "
                "operation limit instead of acting like the skill disappeared. If you learn "
                "personal preferences such as preferred name, desk hours, or current focus, save "
                "them in your own local memory entries rather than rewriting managed stubs. The "
                "canonical user/dashboard/code and shared host addresses live under "
                "[managed:resource-ref] without storing the user's credentials there. Respect "
                "shared-host boundaries: stay within the current user's authorized Hermes home, "
                "channels, and Almanac resources; never browse other users' home directories or "
                "central deployment secrets unless the operator explicitly asks for host-level "
                "debugging."
            ),
        }
    ]
    _atomic_write_text(prefill_path, json.dumps(prefill_messages, indent=2) + "\n")

    config = load_config()
    skills_cfg = config.setdefault("skills", {})
    if not isinstance(skills_cfg, dict):
        skills_cfg = {}
        config["skills"] = skills_cfg
    disabled = [name for name in skills_cfg.get("disabled", []) if name not in almanac_skill_names]
    skills_cfg["disabled"] = disabled
    _ensure_org_skill_external_dirs(skills_cfg, hermes_home)
    platform_disabled = skills_cfg.get("platform_disabled")
    if isinstance(platform_disabled, dict):
        cleaned_platform_disabled: dict[str, list[str]] = {}
        for platform, names in platform_disabled.items():
            if isinstance(names, list):
                kept = [name for name in names if name not in almanac_skill_names]
                if kept:
                    cleaned_platform_disabled[str(platform)] = kept
        if cleaned_platform_disabled:
            skills_cfg["platform_disabled"] = cleaned_platform_disabled
        else:
            skills_cfg.pop("platform_disabled", None)

    plugins_cfg = config.setdefault("plugins", {})
    disabled_plugins = plugins_cfg.get("disabled", [])
    if isinstance(disabled_plugins, list):
        plugins_cfg["disabled"] = [name for name in disabled_plugins if name not in almanac_plugin_names]
    else:
        plugins_cfg["disabled"] = []

    config["prefill_messages_file"] = str(prefill_path)
    agent_cfg = config.get("agent")
    if not isinstance(agent_cfg, dict):
        agent_cfg = {}
    agent_cfg["prefill_messages_file"] = str(prefill_path)
    config["agent"] = agent_cfg
    save_config(config)
    return {
        "identity_state_file": str(identity_state_path),
        "prefill_messages_file": str(prefill_path),
        "soul_file": str(soul_path),
    }


def _validate_runtime(spec: dict[str, Any]) -> dict[str, Any]:
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider

    runtime = resolve_runtime_provider(requested=str(spec.get("provider_id") or ""))
    config = load_config()
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        model_id = str(model_cfg.get("default") or "")
        provider_id = str(model_cfg.get("provider") or "")
    else:
        model_id = str(model_cfg or "")
        provider_id = ""
    agent_cfg = config.get("agent")
    reasoning_effort = ""
    if isinstance(agent_cfg, dict):
        reasoning_effort = str(agent_cfg.get("reasoning_effort") or "").strip()
    return {
        "provider": runtime.get("provider"),
        "base_url": runtime.get("base_url"),
        "api_mode": runtime.get("api_mode"),
        "model": model_id,
        "configured_provider": provider_id,
        "reasoning_effort": reasoning_effort,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Hermes home for headless Almanac onboarding.")
    parser.add_argument("--provider-spec-json", help="Provider setup spec as json.")
    parser.add_argument("--secret-path", help="Path to the staged provider secret.")
    parser.add_argument("--bot-name", default="", help="Public-facing bot name for Almanac prefill priming.")
    parser.add_argument("--unix-user", default="", help="Unix username being provisioned.")
    parser.add_argument("--user-name", default="", help="Human display name for the user being provisioned.")
    parser.add_argument(
        "--identity-only",
        action="store_true",
        help="Only refresh the Almanac SOUL.md and prefill config.",
    )
    parser.add_argument("--prefill-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    identity_paths = _seed_almanac_identity(args.bot_name, args.unix_user, args.user_name)
    identity_only = bool(args.identity_only or args.prefill_only)
    if identity_only:
        print(
            json.dumps(
                {
                    **identity_paths,
                    "identity_only": True,
                    "prefill_only": True,
                },
                sort_keys=True,
            )
        )
        return

    if not args.provider_spec_json or not args.secret_path:
        raise SystemExit("--provider-spec-json and --secret-path are required unless --identity-only is set")

    spec = _load_provider_spec(args.provider_spec_json)
    provider_id = str(spec.get("provider_id") or "").strip()
    if provider_id == "openai-codex":
        _seed_openai_codex(spec, args.secret_path)
    elif provider_id == "anthropic":
        _seed_anthropic(spec, args.secret_path)
    elif bool(spec.get("is_custom")):
        _seed_custom_provider(spec, args.secret_path)
    else:
        _seed_api_key_provider(spec, args.secret_path)

    _write_reasoning_effort(spec)
    payload = _validate_runtime(spec)
    payload.update(identity_paths)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
