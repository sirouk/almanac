"""ArcLink Crew switcher API.

One read-only route: the Captain's other Agents and their dashboard URLs,
straight from the web-access state the ArcLink control plane already
maintains at ``$HERMES_HOME/state/arclink-web-access.json``
(``crew_dashboards``, refreshed by the sovereign worker on apply, handoff
recovery, and teardown). No secrets live in that file and none are returned.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover - test/headless import without fastapi
    class APIRouter:  # type: ignore
        def get(self, *_args, **_kwargs):
            return lambda fn: fn


router = APIRouter()


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")).expanduser()


def _web_access_path() -> Path:
    return _hermes_home() / "state" / "arclink-web-access.json"


def _clean_link(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    label = str(entry.get("label") or "").strip()
    url = str(entry.get("hermes_url") or entry.get("url") or entry.get("dashboard_url") or "").strip()
    if not label or not url.startswith("https://"):
        return None
    return {
        "label": label[:80],
        "title": str(entry.get("title") or "").strip()[:120],
        "status": str(entry.get("status") or "").strip()[:40],
        "url": url,
        "current": bool(entry.get("current")),
        "theme_label": str(entry.get("theme_label") or "").strip()[:64],
    }


@router.get("/crew")
def crew() -> dict[str, Any]:
    path = _web_access_path()
    crew_links: list[dict[str, Any]] = []
    refreshed_at = ""
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            refreshed_at = str(payload.get("crew_dashboards_refreshed_at") or "")
            for entry in payload.get("crew_dashboards") or []:
                cleaned = _clean_link(entry)
                if cleaned is not None:
                    crew_links.append(cleaned)
    return {
        "crew": crew_links[:24],
        "refreshed_at": refreshed_at,
        "count": len(crew_links[:24]),
    }


@router.get("/status")
def status() -> dict[str, Any]:
    path = _web_access_path()
    return {
        "plugin": "arclink-crew",
        "state_file_present": path.is_file(),
        "summary": (
            "Crew switcher ready: the header dropdown lists this Captain's Agents."
            if path.is_file()
            else "Crew switcher is waiting for the ArcLink control plane to publish crew links. "
            "Next: finish Agent provisioning or open the Raven `/agents` roster."
        ),
    }
