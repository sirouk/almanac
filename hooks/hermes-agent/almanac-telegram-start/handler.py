from __future__ import annotations

import os


def handle(event_type: str, context: dict | None = None) -> dict | None:
    if event_type != "command:start":
        return None
    context = context or {}
    platform = str(context.get("platform") or "").strip().lower()
    if platform and platform != "telegram":
        return None

    raw_args = str(context.get("raw_args") or context.get("args") or "").strip()
    text = raw_args or os.getenv("ALMANAC_TELEGRAM_START_TEXT", "hi")
    if not text:
        text = "hi"
    return {
        "decision": "rewrite",
        "command_name": "steer",
        "raw_args": text,
    }
