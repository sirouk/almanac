<!-- managed: arclink-default-vault -->
# Repos

Use this area as a default library for repository notes and cloned docs. It is
not a hard boundary: agents can retrieve repository notes or cloned checkouts
from any folder under the shared vault.

If a repository is present anywhere under the vault as a real Git checkout,
ArcLink's hourly Curator refresh hard-syncs it to `origin/<current-branch>` in
place. Local commits, uncommitted edits, untracked files, and gitignored build
artifacts are cleaned so the checkout mirrors upstream. Markdown and text files
in the checkout are indexed by qmd through the normal vault watcher.

Useful contents:
- repo purpose and ownership
- architecture entry points
- deployment / CI quirks
- onboarding notes for contributors and agents
