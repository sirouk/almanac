---
name: notion-page-pdf-export
description: Capture publicly-shared Notion pages (and their direct sub-pages) as full-fidelity PDFs via headless chromium when the Almanac integration cannot reach them. Sizes each output to the page's actual rendered width and height (capped) so wide tables, horizontally-scrolling collections, and long documents print without clipping. The resulting PDFs auto-ingest into the qmd vault-pdf-ingest collection.
---

# Notion → PDF export (headless-browser fallback)

Use this skill ONLY when:

- The shared Notion SSOT integration cannot reach the page (e.g. it lives in a
  third-party agency workspace like `example/`, or in a separate
  workspace nobody invited Almanac into), AND
- The page is configured for "Share to web" / "anyone with the link", so
  Notion's public web renderer will return content without a Notion login.

If either of those isn't true, prefer the proper rails:

- Page in our own workspace → ask the page owner to add the Almanac
  integration via Notion → Share → Add connections → Almanac. Then
  `notion.fetch` / `notion.search` / the qmd `notion-shared` index pick it
  up live within ~1 minute via the webhook → ssot batcher → qmd reindex
  pipeline.
- Page is private → cannot capture without auth; ask the page owner to
  share to web first or grant the integration access.

## Render mode: full-fidelity, content-sized PDF

Each PDF is written as a single tall page sized to the rendered content's
actual width and height (with a small breathing-room margin and configurable
caps). The script:

1. Loads the page in chromium at a wide viewport (1800×1800).
2. Injects print CSS that:
   - drops the floating help/share overlay,
   - uncaps `.notion-page-content` / `.notion-collection-view` /
     `.notion-column-block` etc. (those classes cap at ~900px and clip wide
     content),
   - flips `overflow-x: visible` on every horizontally-scrolling collection
     view so all columns reflow into the print, and
   - sets tables and collection bodies to `width: max-content` so they grow
     to their natural width instead of being constrained to the parent.
3. Scrolls top-to-bottom to materialize lazy images / blocks, then scrolls
   every horizontally-scrolling region to its right edge to force Notion's
   column virtualization to render every column.
4. Clicks every collapsed `[aria-expanded=false]` toggle so callouts and
   sub-blocks print fully open.
5. Resets all scroll positions to the origin.
6. Measures `document.documentElement.scrollWidth` × `scrollHeight` and uses
   those (px ÷ 96, plus a small margin, capped at `--max-width-in` /
   `--max-height-in`) as the PDF page dimensions.
7. Calls `page.pdf()` with the measured size (no scaling).

Effect: a wide dashboard prints as a wide page; a long document prints as
a tall page; nothing gets cut off at the right edge or scrolled out of view.

The defaults cap width at 24in and height at 200in to prevent absurdly
huge files from runaway content.

## What the skill does end-to-end

1. Drives headless chromium against each Notion URL the user supplies.
2. Discovers direct sub-pages of each root via Notion's `/api/v3/loadPageChunk`
   JSON endpoint (publicly readable for web-shared pages — no auth needed,
   no rate limits in normal use).
3. Renders each page (root + every direct child by default) as a content-
   sized PDF.
4. Writes the PDFs to a configurable output directory.

After the script returns, an operator copies the PDFs anywhere under the shared
vault. Use the folder shape that will make sense to the organization:
`Projects/<area>/<topic>/`, `Research/<org>/<topic>/`, `Clients/<client>/`, or
a flatter structure are all fine. The `almanac-pdf-ingest.timer` (every 5
minutes) then auto-converts each PDF to markdown and qmd's `vault-pdf-ingest`
collection picks them up. From that point any agent can answer questions about
the captured material via `knowledge.search-and-fetch`.

## Pre-requisites (one-time per host)

```bash
sudo apt-get install -y python3.10-venv
python3.10 -m venv /tmp/scrape-venv
/tmp/scrape-venv/bin/pip install --quiet --upgrade pip
/tmp/scrape-venv/bin/pip install --quiet playwright requests
sudo /tmp/scrape-venv/bin/playwright install --with-deps chromium
```

## Usage

```bash
# Single page + its direct children (default depth=1):
/tmp/scrape-venv/bin/python \
  /home/almanac/almanac/bin/notion-page-pdf-export.py \
  -o /tmp/some-area-pdfs \
  https://www.notion.so/<workspace>/<Page-Title>-<32-hex-id>

# Multiple roots, deeper recursion, wider/taller cap:
/tmp/scrape-venv/bin/python \
  /home/almanac/almanac/bin/notion-page-pdf-export.py \
  -o /tmp/multi-export -d 2 --max-width-in 30 --max-height-in 300 \
  https://www.notion.so/.../Root-A-... \
  https://www.notion.so/.../Root-B-...

# Then move the PDFs into the vault and trigger ingest:
for PDF in /tmp/some-area-pdfs/*.pdf; do
  sudo install -o almanac -g almanac -m 0644 "$PDF" \
    "/home/almanac/almanac/almanac-priv/vault/<Area>/<Topic>/$(basename "$PDF")"
done
sudo -u almanac \
  XDG_RUNTIME_DIR=/run/user/$(id -u almanac) \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u almanac)/bus \
  systemctl --user start almanac-pdf-ingest.service almanac-qmd-update.service
```

## Failure modes

- **Page redirects to `/login`** — the page is not web-shared. Ask the owner
  to enable Share → "Anyone with the link" (view), or share with the
  Almanac integration and use the proper SSOT rails.
- **Some collection columns still cut off** — Notion may have changed CSS
  classes; inspect the live page in chromium devtools and add the new
  selector to `PRINT_CSS` in `bin/notion-page-pdf-export.py` (the uncap
  block + the `overflow-x: visible` block).
- **Output is 8 KB and almost empty** — the print CSS hid a wrapper element
  it shouldn't have. The wrappers `.notion-frame`, `.notion-cursor-listener`,
  `.notion-app-inner` are scroll containers; never set them to
  `display: none` in the print CSS.
- **Sub-pages not discovered** — `loadPageChunk` returns up to 200 blocks
  per call. For pages with > 200 first-level children, extend the discover
  function to follow the `cursor.stack` for paging.
- **PDF too tall** — bump `--max-height-in` (default 200) or split the
  scrape across the explicit child URLs at depth 0.

## Where the captured content ends up

Example vault destinations:

| source area | vault destination |
|---|---|
| Strategy / GTM material | `Projects/<Org>/Strategy/<Page-Slug>.pdf` |
| Marketing playbooks / SoT | `Projects/<Org>/Marketing-SoT/<Page-Slug>.pdf` |
| Research / external papers | `Research/<Org>/<Topic>/<Page-Slug>.pdf` |

Each capture should also get a sibling `README.md` in its folder pointing
back to the live Notion URL and noting the capture date, so future agents
know whether the PDF is current or stale.

If captured PDFs are moved or deleted later, the PDF ingest rail reconciles the
generated markdown sidecars on the next watcher/timer pass. Old qmd paths may
change, but content search self-heals after refresh.

## Why this is a fallback, not the default

Headless-browser captures are static. Real-time edits in Notion don't show
up until the next manual re-run. The Almanac integration + webhook pipeline
gives sub-second propagation and is the right mechanism for material we
control. Use this skill for material we don't control (third-party
workspaces, public-facing pages from other orgs, archived snapshots) — and
re-run it on a schedule if the source still changes.
