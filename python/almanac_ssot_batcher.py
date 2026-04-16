#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

from almanac_control import Config, connect_db, process_pending_notion_events


def main() -> None:
    cfg = Config.from_env()
    with connect_db(cfg) as conn:
        result = process_pending_notion_events(conn)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
