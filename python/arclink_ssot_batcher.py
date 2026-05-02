#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from arclink_control import Config, connect_db, consume_notion_reindex_queue, process_pending_notion_events


def main() -> None:
    cfg = Config.from_env()
    with connect_db(cfg) as conn:
        events = process_pending_notion_events(conn)
        reindex = consume_notion_reindex_queue(conn, cfg, actor="ssot-batcher")
    result = {
        "events": events,
        "reindex": reindex,
    }
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
