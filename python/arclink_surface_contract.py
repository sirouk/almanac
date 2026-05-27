#!/usr/bin/env python3
"""Shared local copy contract for ArcLink product surfaces."""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Literal, Sequence


SurfaceAudience = Literal["captain", "operator", "agent", "mixed"]
SurfaceChannel = Literal["chat", "dashboard", "plugin", "cli", "tui", "api", "web", "docs"]
SurfaceState = Literal["normal", "blocked", "proof_gated"]


_SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_/-]{8,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9_/-]{8,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bntn_[A-Za-z0-9_/-]{8,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"secret://", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_TRACEBACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r'File "[^"]+", line \d+'),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception):\s+\S"),
)

_CAPTAIN_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Captain-facing copy should say ArcPod or Pod, not deployment.", re.compile(r"\bdeployments?\b", re.IGNORECASE)),
    ("Captain-facing copy should say Captain, not user or buyer.", re.compile(r"\b(?:users?|buyers?)\b", re.IGNORECASE)),
    ("Operator is reserved for admin/deploy surfaces.", re.compile(r"\boperators?\b", re.IGNORECASE)),
    ("Product terms should be capitalized as Agent, Agents, Pod, Pods, and Crew.", re.compile(r"\b(?:agent|agents|pod|pods|crew)\b")),
)

_NEXT_ACTION_RE = re.compile(
    r"\b(?:Next|Use|Open|Run|Register|Complete|Send|Tap|Choose|Check|Retry|Operator|dashboard|checkout|proof|PG-[A-Z-]+)\b"
)


@dataclass(frozen=True)
class SurfaceSample:
    name: str
    text: str
    audience: SurfaceAudience
    channel: SurfaceChannel
    state: SurfaceState = "normal"
    required_terms: tuple[str, ...] = ()
    proof_gates: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allow_captain_technical_terms: bool = False
    max_chars: int = 2400
    max_line_chars: int = 360
    metadata: dict[str, str] = field(default_factory=dict)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        clean = " ".join(str(data or "").split())
        if clean:
            self._chunks.append(clean)

    def text(self) -> str:
        return "\n".join(self._chunks)


def visible_text_from_html(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(str(html or ""))
    return parser.text()


def surface_contract_issues(sample: SurfaceSample) -> list[str]:
    text = str(sample.text or "")
    issues: list[str] = []
    if not text.strip():
        return [f"{sample.name}: surface text is empty"]

    if len(text) > sample.max_chars:
        issues.append(f"{sample.name}: surface text is {len(text)} chars, above {sample.max_chars}")
    for index, line in enumerate(text.splitlines(), start=1):
        if len(line) > sample.max_line_chars:
            issues.append(f"{sample.name}: line {index} is {len(line)} chars, above {sample.max_line_chars}")

    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            issues.append(f"{sample.name}: secret-looking value leaked into rendered text")
            break
    for pattern in _TRACEBACK_PATTERNS:
        if pattern.search(text):
            issues.append(f"{sample.name}: raw traceback or exception leaked into rendered text")
            break

    if sample.channel == "chat":
        if text.count("`") % 2:
            issues.append(f"{sample.name}: chat markdown has unbalanced backticks")
        if "<br" in text.lower() or "</" in text:
            issues.append(f"{sample.name}: chat copy contains HTML tags")

    if sample.audience == "captain" and not sample.allow_captain_technical_terms:
        for message, pattern in _CAPTAIN_FORBIDDEN_PATTERNS:
            if pattern.search(text):
                issues.append(f"{sample.name}: {message}")

    for term in sample.required_terms:
        if term not in text:
            issues.append(f"{sample.name}: required term {term!r} is missing")
    for gate in sample.proof_gates:
        if gate not in text:
            issues.append(f"{sample.name}: proof gate {gate!r} is missing")
    lowered = text.lower()
    for term in sample.forbidden_terms:
        if term.lower() in lowered:
            issues.append(f"{sample.name}: forbidden term {term!r} is present")

    blocked_or_gated = sample.state in {"blocked", "proof_gated"} or bool(
        re.search(r"\b(?:blocked|proof[- ]gated|proof still required|not active yet|disabled until)\b", text, re.IGNORECASE)
    )
    if blocked_or_gated and not _NEXT_ACTION_RE.search(text):
        issues.append(f"{sample.name}: blocked/proof-gated copy lacks a concrete next action or proof gate")

    return issues


def assert_surface_contract(samples: Sequence[SurfaceSample]) -> None:
    issues: list[str] = []
    for sample in samples:
        issues.extend(surface_contract_issues(sample))
    if issues:
        rendered = "\n".join(f"- {issue}" for issue in issues)
        raise AssertionError(f"ArcLink surface contract violations:\n{rendered}")
