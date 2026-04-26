#!/usr/bin/env python3
"""notion-page-pdf-export.py — print publicly-shared Notion pages as PDFs.

Use case: a Notion page (or set of pages) is shared via "Share to web" / "anyone
with the link" but the Almanac Notion integration was never invited, so the
ssot.read / notion.fetch rails return 404. We can still capture the live state
by driving headless chromium against the public URL.

Discovers direct sub-pages via Notion's loadPageChunk JSON (publicly readable
for web-shared pages), so passing one root URL gets the root + all its first-
level children. Recursion depth defaults to 1 to keep API budget bounded; use
--depth N to go deeper.

The output is a printable PDF per page with Notion's chrome retained but the
content-width caps removed, so wide tables and images don't clip on the right
edge.

USAGE
    notion-page-pdf-export.py [-o OUT_DIR] [-d DEPTH] URL [URL ...]

EXAMPLE
    notion-page-pdf-export.py -o /tmp/chutes-strategy-pdfs \\
        https://www.notion.so/lunarstrategy/Chutes-Strategy-3332d1d5935b80ff90fce4712666778c

PRE-REQUISITES
    python3 -m venv /tmp/scrape-venv
    /tmp/scrape-venv/bin/pip install playwright requests
    sudo /tmp/scrape-venv/bin/playwright install --with-deps chromium

NOTES
    - This bypasses the Almanac integration deliberately. If the operator can
      get the page shared with the Almanac integration instead, prefer that
      path: it gives webhook-driven sub-second propagation and no PDF cycle.
    - Pages that aren't web-shared will redirect to /login and we skip them.
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
  .notion-overlay-container { display: none !important; }
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
  table { max-width: 100% !important; }
  img, video, .notion-image-block img { max-width: 100% !important; height: auto !important; }
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


def render_page_pdf(page, url: str, out_pdf: Path) -> tuple[bool, str]:
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
    page.evaluate(
        "() => new Promise(r => { let y=0; const id=setInterval(()=>{"
        "  window.scrollTo(0,y); y += 1000;"
        "  if (y > document.body.scrollHeight + 2400) { clearInterval(id); r(); }"
        "}, 250); })"
    )
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2.5)
    page.evaluate(
        "() => Array.from(document.querySelectorAll('[aria-expanded=\"false\"]'))"
        ".forEach(el => { try { el.click(); } catch (e) {} })"
    )
    time.sleep(1.5)
    page.emulate_media(media="print")
    page.pdf(
        path=str(out_pdf),
        format="A4",
        landscape=True,
        print_background=True,
        scale=0.85,
        margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"},
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
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    queue: list[tuple[str, str, int]] = []
    for url in args.urls:
        try:
            slug = slugify(url.rsplit("/", 1)[-1].split("-")[0]) or page_id_from_url(url).split("-")[0]
        except ValueError:
            slug = "page"
        queue.append((slug, url, 0))

    seen: set[str] = set()
    rendered: list[Path] = []
    failed: list[tuple[str, str]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 1800})
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
            ok, err = render_page_pdf(page, url, out_pdf)
            if not ok:
                failed.append((url, err))
                print(f"   FAIL: {err}", flush=True)
                continue
            rendered.append(out_pdf)
            print(f"   OK  -> {out_pdf}  ({out_pdf.stat().st_size} bytes)", flush=True)
            if depth >= args.depth:
                continue
            for ctitle, curl in discover_children(pid):
                cslug = slugify(ctitle) or page_id_from_url(curl).split("-")[0]
                queue.append((cslug, curl, depth + 1))

        browser.close()

    print()
    print(f"rendered {len(rendered)} pdfs to {out_dir}; {len(failed)} failed")
    for url, err in failed:
        print(f"  FAILED: {url}  -- {err}", file=sys.stderr)
    return 0 if rendered else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
