#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO)
    return [REPO / item.decode("utf-8") for item in output.split(b"\0") if item]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def private_terms_pattern() -> re.Pattern[str]:
    raw_terms = private_terms()
    escaped = [re.escape(term) for term in raw_terms]
    if not escaped:
        return re.compile(r"a\A")
    return re.compile(r"(?i)(?<![a-z0-9_-])(" + "|".join(escaped) + r")(?![a-z0-9_-])")


def private_terms() -> list[str]:
    configured = os.environ.get("ALMANAC_PUBLIC_HYGIENE_TERMS", "")
    terms = [term.strip() for term in configured.splitlines() if term.strip()]
    terms_file_env = os.environ.get("ALMANAC_PUBLIC_HYGIENE_TERMS_FILE", "")
    terms_file = Path(terms_file_env) if terms_file_env else REPO / "almanac-priv" / "config" / "public-hygiene-terms.txt"
    if terms_file.exists():
        for line in terms_file.read_text(encoding="utf-8").splitlines():
            term = line.strip()
            if term and not term.startswith("#"):
                terms.append(term)
    return sorted(set(terms))


PROVIDER_TERM = "Chutes"
PROVIDER_TERM_RE = re.compile(PROVIDER_TERM, re.IGNORECASE)
PROVIDER_CONTEXT_RE = re.compile(
    r"(?i)("
    r"inference|provider|model|preset|api key|key|secret|thinking|openai-compatible|"
    r"llm\.chutes\.ai|moonshotai|model-router|auto-failover|chutes:|chutes_|"
    r"chute\b|chutesai|custom-provider"
    r")"
)
PROVIDER_CODE_PATHS = {
    Path("bin/bootstrap-curator.sh"),
    Path("bin/common.sh"),
    Path("bin/deploy.sh"),
    Path("bin/init.sh"),
    Path("config/model-providers.yaml"),
    Path("python/almanac_model_providers.py"),
    Path("python/almanac_onboarding_flow.py"),
    Path("python/almanac_onboarding_provider_auth.py"),
    Path("tests/test_almanac_onboarding_prompts.py"),
    Path("tests/test_deploy_regressions.py"),
    Path("tests/test_model_providers.py"),
}

DEPLOYMENT_IDENTIFIER_PATTERNS = (
    (
        "real-looking Tailscale hostname",
        re.compile(r"(?i)\b[a-z0-9][a-z0-9-]*\.tail[0-9a-f]{4,}\.ts\.net\b"),
    ),
)


def relative(path: Path) -> Path:
    return path.relative_to(REPO)


def test_no_private_operator_names_in_public_tracked_files() -> None:
    pattern = private_terms_pattern()
    violations: list[str] = []
    for path in tracked_files():
        rel = relative(path)
        if rel.parts and rel.parts[0] == "almanac-priv":
            continue
        text = read_text(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    expect(not violations, "private operator terms found in public tracked files:\n" + "\n".join(violations[:50]))


def test_provider_name_is_only_used_for_model_provider_context() -> None:
    violations: list[str] = []
    for path in tracked_files():
        rel = relative(path)
        if rel.parts and rel.parts[0] == "almanac-priv":
            continue
        text = read_text(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not PROVIDER_TERM_RE.search(line):
                continue
            if rel in PROVIDER_CODE_PATHS or PROVIDER_CONTEXT_RE.search(line):
                continue
            violations.append(f"{rel}:{lineno}: {line.strip()}")
    expect(
        not violations,
        "provider name appears outside inference/model provider context:\n" + "\n".join(violations[:50]),
    )


def test_no_live_deployment_identifiers_in_public_tracked_files() -> None:
    violations: list[str] = []
    for path in tracked_files():
        rel = relative(path)
        if rel.parts and rel.parts[0] == "almanac-priv":
            continue
        text = read_text(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, pattern in DEPLOYMENT_IDENTIFIER_PATTERNS:
                if pattern.search(line):
                    violations.append(f"{rel}:{lineno}: {label}: {line.strip()}")
    expect(
        not violations,
        "live deployment identifiers found in public tracked files:\n" + "\n".join(violations[:50]),
    )


def main() -> int:
    test_no_private_operator_names_in_public_tracked_files()
    test_provider_name_is_only_used_for_model_provider_context()
    test_no_live_deployment_identifiers_in_public_tracked_files()
    print("PASS public repo hygiene")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
