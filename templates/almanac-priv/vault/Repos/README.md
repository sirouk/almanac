<!-- managed: almanac-default-vault -->
# Repos

Keep one note per repository the organization depends on, or clone the
repository itself into this vault when agents should be able to retrieve its
markdown docs through qmd.

If a repository is present on disk as a real Git checkout, Almanac's hourly
Curator refresh hard-syncs it to `origin/<current-branch>` in place. Local
commits, uncommitted edits, untracked files, and gitignored build artifacts are
cleaned so the checkout mirrors upstream. Markdown and text files in the
checkout are indexed by qmd through the normal vault watcher.

Useful contents:
- repo purpose and ownership
- architecture entry points
- deployment / CI quirks
- onboarding notes for contributors and agents
