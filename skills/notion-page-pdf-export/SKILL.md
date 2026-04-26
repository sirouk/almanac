---
name: notion-page-pdf-export
description: Capture publicly-shared Notion pages (and their direct sub-pages) as printable PDFs via headless chromium when the Almanac integration doesn't have access to them. Treats the page tree as opaque; the resulting PDFs auto-ingest into the qmd vault-pdf-ingest collection.
---

# Notion → PDF export (headless-browser fallback)

Use this skill ONLY when:

- The shared Notion SSOT integration cannot reach the page (e.g. it lives in a
  third-party agency workspace like `lunarstrategy/`, or in a separate
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

## What the skill does

1. Drives headless chromium against each Notion URL the user supplies.
2. Discovers direct sub-pages of each root via Notion's `/api/v3/loadPageChunk`
   JSON endpoint (publicly readable for web-shared pages — no auth needed,
   no rate limits in normal use).
3. Renders each page (root + every direct child by default) as a printable
   PDF, with Notion's content-width caps removed so wide tables and images
   don't clip on the right edge.
4. Writes the PDFs to a configurable output directory.

The PDFs land in the vault under `Projects/<area>/<topic>/` and get
auto-converted to markdown by `almanac-pdf-ingest.timer` (every 5 minutes),
indexed by qmd's `vault-pdf-ingest` collection. From that point any agent
can answer questions about the captured material via
`knowledge.search-and-fetch`.

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

# Multiple roots, deeper recursion:
/tmp/scrape-venv/bin/python \
  /home/almanac/almanac/bin/notion-page-pdf-export.py \
  -o /tmp/multi-export -d 2 \
  https://www.notion.so/.../Root-A-... \
  https://www.notion.so/.../Root-B-...

# Then move the PDFs into the vault and trigger ingest:
for PDF in /tmp/some-area-pdfs/*.pdf; do
  sudo install -o almanac -g almanac -m 0644 "$PDF" \
    "/home/almanac/almanac/almanac-priv/vault/Projects/<Area>/<Topic>/$(basename "$PDF")"
done
sudo -u almanac \
  XDG_RUNTIME_DIR=/run/user/$(id -u almanac) \
  DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u almanac)/bus \
  systemctl --user start almanac-pdf-ingest.service almanac-qmd-update.service
```

## Render parameters (why these choices)

- **A4 landscape, scale 0.85, 0.4in margins** — fits Notion's typical content
  width without clipping; landscape is essential because portrait crops the
  right edge of multi-column dashboards and wide tables.
- **`viewport={width: 1600}`** — wider viewport so Notion's responsive
  layer renders the broader desktop layout instead of mobile reflows.
- **Print CSS injection** — uncaps `.notion-page-content`,
  `.notion-collection-view`, `.notion-column-block`, etc., which by default
  cap at ~900px and clip wide content. We do NOT hide wrappers like
  `.notion-frame` / `.notion-cursor-listener` / `.notion-app-inner` — those
  are scroll containers and hiding them blanks the print.
- **Scroll + toggle-expand pre-print** — Notion lazy-loads images and keeps
  toggle blocks collapsed by default; we scroll the page top to bottom to
  trigger lazy loading, then click every `[aria-expanded=false]` so callouts
  and toggles render fully open in the PDF.
- **`wait_until="domcontentloaded"` (NOT `networkidle`)** — Notion's app
  keeps polling/keep-alive forever, so `networkidle` always times out. We
  wait for the content selector instead.

## Failure modes

- **Page redirects to `/login`** — the page is not web-shared. Ask the owner
  to enable Share → "Anyone with the link" (view), or share with the
  Almanac integration and use the proper SSOT rails.
- **Content-width caps still clip** — Notion may have changed CSS classes;
  inspect the live page in chromium devtools and add the new selector to
  `PRINT_CSS` in `bin/notion-page-pdf-export.py`.
- **Sub-pages not discovered** — `loadPageChunk` only returns first-level
  blocks per call; the script handles pagination implicitly via `limit=200`.
  For pages with > 200 child blocks, extend with cursor-based paging.

## Where the captured content ends up

Following the existing vault convention:

| source area | vault destination |
|---|---|
| Strategy / GTM material | `Projects/<Org>/Strategy/<Page-Slug>.pdf` |
| Marketing playbooks / SoT | `Projects/<Org>/Marketing-SoT/<Page-Slug>.pdf` |
| Research / external papers | `Research/<Org>/<Topic>/<Page-Slug>.pdf` |

Each capture should also get a sibling `README.md` in its folder pointing
back to the live Notion URL and noting the capture date, so future agents
know whether the PDF is current or stale.

## Why this is a fallback, not the default

Headless-browser captures are static. Real-time edits in Notion don't show
up until the next manual re-run. The Almanac integration + webhook pipeline
gives sub-second propagation and is the right mechanism for material we
control. Use this skill for material we don't control (third-party
workspaces, public-facing pages from other orgs, archived snapshots) — and
re-run it on a schedule if the source still changes.
