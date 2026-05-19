# ArcLink Theme

This is a no-tab Hermes plugin that carries the ArcLink dashboard theme.
It intentionally has no `dashboard/manifest.json`, so Hermes will not add a
left-hand dashboard menu item for it.

ArcLink's agent install and refresh scripts copy `dashboard-themes/arclink.yaml`
into `HERMES_HOME/dashboard-themes/` and set `dashboard.theme: arclink` in
`config.yaml` when this plugin is enabled. Those installers also render the
per-agent label/accent placeholders and generate the bundled ArcLink variants
for secondary Crew members, so upgrades can refresh the theme without patching
Hermes core.
