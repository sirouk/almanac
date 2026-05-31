# ArcLink Brand System

Source asset: `docs/arclink/brand/ArcLink Brandkit.pdf`

Version: 1.0, May 2026

## Positioning

- Category: private AI infrastructure.
- Audience: SMB owners, agencies, and operators drowning in manual work.
- Value: replace repetitive work, reduce operational overhead, and scale without hiring.
- Product promise: private AI agents that run your business.
- Short promise: built once. Runs forever.

## Personality

- Authoritative: speaks with certainty and expertise.
- Minimal: no excess and no fluff. Every element has purpose.
- Operational: focused on workflows, outcomes, and results.
- Quietly powerful: understated confidence that delivers impact.

## Palette

Primary colors:

- Jet Black: `#080808`
- Carbon: `#0F0F0E`
- Soft White: `#E7E6E6`
- Signal Orange: `#FB5005`

Secondary accents:

- Electric Blue: `#2075FE`
- Neon Green: `#1AC153`

These six values are mechanically verified: the local product-surface prototype
(`python/arclink_product_surface.py`, `_layout()`) sets `--jet:#080808`,
`--carbon:#0F0F0E`, `--soft:#E7E6E6`, `--signal:#FB5005`, `--blue:#2075FE`, and
`--green:#1AC153`, matching this palette exactly.

Usage rules:

- Black and carbon are the default surfaces.
- Signal orange drives primary action, energy, orbit lines, logo accents, and key conversion moments.
- Blue and green support system states and feedback. Do not let them dominate the interface.
- Keep the UI dark, precise, and high-contrast. Avoid broad gradients, generic AI purple, or decorative noise.

## Typography

- Display and headlines: Space Grotesk, bold or semibold.
- Body and UI: Satoshi, or Inter when Satoshi is not available.
- Use clean type, generous spacing, and direct hierarchy.
- Avoid oversized hero typography inside dashboards, control panels, or dense operational surfaces.

The product-surface prototype sets headings to `"Space Grotesk", Inter` and body
to `Inter, Satoshi, system-ui` (Satoshi declared as a webfont fallback), matching
this intent.

## Logo System

- Primary logo: orange arc mark plus spaced `ARCLINK` wordmark and `PRIVATE AI INFRASTRUCTURE` descriptor.
- Icon mark: the orange arc, optionally on signal-orange or carbon tiles.
- Keep the mark simple and recognizable. Do not overdecorate it or bury it in effects.

## UI Elements

- Buttons: signal-orange primary buttons with a simple right-arrow affordance; carbon/outlined secondary buttons.
- Tags: compact dark labels for neutral categories; green only for active/success states.
- Inputs: carbon/black fields with fine borders and soft-white text.
- Icons: line icons with consistent weight, rounded corners, and system-first subjects such as leads, calendar, payments, automations, reports, settings, integrations, and security.

## Imagery

- Visualize invisible workflows.
- Use abstract, minimal, purpose-driven infrastructure imagery.
- Avoid stock photos, generic AI imagery, cliches, and overused gradients.
- Preferred imagery: dark operational nodes, orange connection paths, private infrastructure, dashboards, hardware/system abstractions, and deployment topology.

## Voice

How ArcLink speaks:

- Clear. Direct. Confident.
- Operator language, not marketer language.
- Short sentences.
- Outcome-focused.
- Human, not robotic.

Prefer:

- "Your AI workforce. Deployed."
- "Private AI agents that run your business."
- "Built once. Runs forever."
- "Clean. Modern. Built to scale."

Shipped-copy note: the live local product-surface prototype
(`python/arclink_product_surface.py`, the no-secret WSGI prototype — not the
production Next.js `web/` app) leads with the hero line **"Your AI workforce.
Deployed."** under the **"Private AI infrastructure"** tag. It does **not** use
the short promise "Built once. Runs forever." anywhere in shipped copy. Treat
"Your AI workforce. Deployed." as the proven, in-product lead; "Built once.
Runs forever." remains brand canon but is currently unshipped.

Avoid:

- Hype or buzzwords.
- Overcomplication.
- Generic AI imagery.
- Overusing gradients.
- Robotic wording.

## Product Implications

- User and admin dashboards should feel like premium control rooms, not SaaS marketing pages.
- The technology should be visible and named: Hermes, qmd, Chutes, vaults, memory stubs, skills, deployment health, and private infrastructure are product strengths.
- Mobile views should keep the same control-room tone while prioritizing status, alerts, launch actions, and search.
- Admin copy should say what happened, what is blocked, and what action is available.
- Every touchpoint should feel consistent across desktop, mobile, onboarding bots, billing, deployment status, and support surfaces.
