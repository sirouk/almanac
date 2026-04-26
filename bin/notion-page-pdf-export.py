#!/usr/bin/env python3
"""notion-page-pdf-export.py — print publicly-shared Notion pages as PDFs.

Use case: a Notion page (or set of pages) is shared via "Share to web" / "anyone
with the link" but the Almanac integration was never invited, so the
ssot.read / notion.fetch rails return 404. We can still capture the live state
by driving headless chromium against the public URL.

Discovers direct sub-pages via Notion's loadPageChunk JSON (publicly readable
for web-shared pages), so passing one root URL gets the root + its first-level
children. Recursion depth defaults to 1; use --depth N to go deeper.

Render mode: full content, no clipping. We measure the actually-rendered page
width and height after warm-up (vertical scroll for lazy images, horizontal
scroll on every collection/table view to materialize all columns, expand every
collapsed toggle), then size the PDF page to the measured dimensions (capped
at 24in wide x 200in tall) and emit a single tall page that captures the
whole document the way Notion shows it.

USAGE
    notion-page-pdf-export.py [-o OUT_DIR] [-d DEPTH] [--max-width-in IN]
                              [--max-height-in IN] URL [URL ...]

EXAMPLE
    notion-page-pdf-export.py -o /tmp/chutes-strategy-pdfs \\
        https://www.notion.so/lunarstrategy/Chutes-Strategy-3332d1d5935b80ff90fce4712666778c

PRE-REQUISITES
    sudo apt-get install -y python3.10-venv
    python3.10 -m venv /tmp/scrape-venv
    /tmp/scrape-venv/bin/pip install playwright requests
    sudo /tmp/scrape-venv/bin/playwright install --with-deps chromium

NOTES
    - This is a fallback for pages we can't reach via the Almanac integration.
      Pages in our own workspace should be shared with the integration so the
      webhook + qmd pipeline gives sub-second propagation.
    - Pages that aren't web-shared redirect to /login and we skip them.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import requests  # noqa: E402  (pip dep)
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError


PRINT_CSS = """
@media print {
  /* Drop floating help/share UI that paints over text */
  .notion-overlay-container { display: none !important; }

  /* Uncap content-width caps that clip wide tables/images on the right edge.
     We DO NOT touch wrappers like .notion-frame, .notion-cursor-listener, or
     .notion-app-inner — those are scroll containers and hiding them blanks
     the print. Only target the inner content layers. */
  .notion-page-content,
  .notion-page-content-inner,
  .notion-collection-view,
  .notion-collection_view-block,
  .notion-column-block,
  .notion-column_list-block,
  .notion-table-block {
    max-width: none !important;
    width: 100% !important;
  }

  /* Force horizontally-scrolling regions (Notion databases, wide tables, code
     blocks) to render their full content instead of clipping at the visible
     scroll-port edge. */
  .notion-collection-view,
  .notion-collection_view-block,
  .notion-board-view,
  .notion-table-view,
  .notion-gallery-view,
  .notion-timeline-view,
  .notion-calendar-view,
  table,
  pre,
  code {
    overflow-x: visible !important;
    overflow-y: visible !important;
    max-width: none !important;
  }
  .notion-collection-view-body,
  .notion-table-view-body,
  .notion-board-view-body,
  table > tbody,
  table > thead,
  table {
    width: max-content !important;
    max-width: none !important;
  }
  img, video, .notion-image-block img {
    max-width: 100% !important;
    height: auto !important;
  }
}
/* Outside print: also de-virtualize horizontally-scrolling regions so the
   in-page measurement step counts the full content width. */
.notion-collection-view,
.notion-collection_view-block,
.notion-table-view,
.notion-board-view,
table {
  overflow-x: visible !important;
}
"""


def page_id_from_url(url: str) -> str:
    m = re.search(r"([0-9a-f]{32})", url)
    if not m:
        raise ValueError(f"no page id in {url}")
    raw = m.group(1)
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip()).strip("-")
    return s or "untitled"


def slug_from_url(url: str) -> str:
    """Pull the human-readable slug out of a Notion URL like
    https://www.notion.so/<workspace>/<Page-Title>-<32hex>.
    Strips the trailing 32-hex id (and the leading hyphen if present).
    """
    last = url.rstrip("/").rsplit("/", 1)[-1]
    last = re.sub(r"-?[0-9a-f]{32}$", "", last)
    return slugify(last) or page_id_from_url(url).split("-")[0]


def discover_children(page_id: str) -> list[tuple[str, str]]:
    body = {"pageId": page_id, "limit": 200, "cursor": {"stack": []},
            "chunkNumber": 0, "verticalColumns": False}
    try:
        r = requests.post(
            "https://www.notion.so/api/v3/loadPageChunk",
            json=body,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  loadPageChunk failed for {page_id}: {exc}", file=sys.stderr, flush=True)
        return []
    blocks = data.get("recordMap", {}).get("block", {}) or {}
    children: list[tuple[str, str]] = []
    for _bid, wrap in blocks.items():
        v = (wrap or {}).get("value", {})
        if isinstance(v.get("value"), dict):
            v = v["value"]
        if not isinstance(v, dict) or v.get("type") != "page" or v.get("id") == page_id:
            continue
        title_parts = (v.get("properties") or {}).get("title") or [[""]]
        title = "".join(part[0] for part in title_parts if part) or v.get("id", "")
        url = f"https://www.notion.so/{v['id'].replace('-', '')}"
        children.append((title, url))
    return children


def render_page_pdf(page, url: str, out_pdf: Path, *, max_width_in: float, max_height_in: float) -> tuple[bool, str]:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except PWTimeoutError as exc:
        return False, f"goto timeout: {exc}"
    if "/login" in page.url:
        return False, f"redirected to login (page is not web-shared): {page.url}"
    try:
        page.wait_for_selector(
            ".notion-page-content, .notion-page-block, [data-block-id], div.notion-frame",
            timeout=45000,
            state="attached",
        )
    except PWTimeoutError as exc:
        return False, f"content selector never appeared: {exc}"

    page.add_style_tag(content=PRINT_CSS)

    # Vertical scroll to load lazy images / toggles.
    page.evaluate(
        "() => new Promise(r => { let y=0; const id=setInterval(()=>{"
        "  window.scrollTo(0,y); y += 1000;"
        "  if (y > document.body.scrollHeight + 2400) { clearInterval(id); r(); }"
        "}, 220); })"
    )
    # Horizontal scroll on every horizontally-scrollable region so column
    # virtualization renders all columns before we measure + print.
    page.evaluate(
        "() => { document.querySelectorAll("
        "    \".notion-collection-view, .notion-table-view, .notion-board-view,"
        "    .notion-collection_view-block, [style*='overflow-x']\""
        "  ).forEach(el => { try { el.scrollLeft = el.scrollWidth; } catch (e) {} });"
        "}"
    )
    time.sleep(2.5)

    page.evaluate(
        "() => Array.from(document.querySelectorAll('[aria-expanded=\"false\"]'))"
        ".forEach(el => { try { el.click(); } catch (e) {} })"
    )
    time.sleep(1.5)

    # Reset scroll positions so the rendered output starts at top-left.
    page.evaluate(
        "() => { window.scrollTo(0, 0);"
        "  document.querySelectorAll("
        "    \".notion-collection-view, .notion-table-view, .notion-board-view,"
        "    .notion-collection_view-block, [style*='overflow-x']\""
        "  ).forEach(el => { try { el.scrollLeft = 0; } catch (e) {} });"
        "}"
    )

    page.emulate_media(media="print")
    metrics = page.evaluate(
        "() => ({"
        "  width: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),"
        "  height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)"
        "})"
    )
    px_per_in = 96.0
    width_in = max(11.0, min(metrics["width"] / px_per_in + 0.6, max_width_in))
    height_in = max(8.5, min(metrics["height"] / px_per_in + 0.6, max_height_in))
    print(f"   page {metrics['width']}x{metrics['height']}px -> pdf {width_in:.1f}x{height_in:.1f}in", flush=True)

    page.pdf(
        path=str(out_pdf),
        width=f"{width_in:.2f}in",
        height=f"{height_in:.2f}in",
        print_background=True,
        margin={"top": "0.3in", "bottom": "0.3in", "left": "0.3in", "right": "0.3in"},
        display_header_footer=False,
        prefer_css_page_size=False,
    )
    return True, ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("urls", nargs="+", help="One or more Notion page URLs.")
    parser.add_argument("-o", "--out", default="/tmp/notion-pdf-export",
                        help="Output dir (default: /tmp/notion-pdf-export).")
    parser.add_argument("-d", "--depth", type=int, default=1,
                        help="Sub-page recursion depth (0 = roots only; default: 1).")
    parser.add_argument("--max-pages", type=int, default=80,
                        help="Hard cap on total pages rendered (default: 80).")
    parser.add_argument("--max-width-in", type=float, default=24.0,
                        help="Max PDF page width in inches (default: 24).")
    parser.add_argument("--max-height-in", type=float, default=200.0,
                        help="Max PDF page height in inches (default: 200; tall single-page output).")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    queue: list[tuple[str, str, int]] = []
    for url in args.urls:
        queue.append((slug_from_url(url), url, 0))

    seen: set[str] = set()
    rendered: list[Path] = []
    failed: list[tuple[str, str]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1800, "height": 1800})
        page = ctx.new_page()
        page.set_default_timeout(60000)

        i = 0
        while queue and i < args.max_pages:
            slug, url, depth = queue.pop(0)
            i += 1
            try:
                pid = page_id_from_url(url)
            except ValueError:
                continue
            if pid in seen:
                continue
            seen.add(pid)
            out_pdf = out_dir / f"{slug}.pdf"
            print(f"[{i}] depth={depth}  {slug}", flush=True)
            ok, err = render_page_pdf(
                page, url, out_pdf,
                max_width_in=args.max_width_in,
                max_height_in=args.max_height_in,
            )
            if not ok:
                failed.append((url, err))
                print(f"   FAIL: {err}", flush=True)
                continue
            rendered.append(out_pdf)
            print(f"   OK  -> {out_pdf}  ({out_pdf.stat().st_size} bytes)", flush=True)
            if depth >= args.depth:
                continue
            for ctitle, curl in discover_children(pid):
                cslug = slugify(ctitle) or slug_from_url(curl)
                queue.append((cslug, curl, depth + 1))

        browser.close()

    print()
    print(f"rendered {len(rendered)} pdfs to {out_dir}; {len(failed)} failed")
    for url, err in failed:
        print(f"  FAILED: {url}  -- {err}", file=sys.stderr)
    return 0 if rendered else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
