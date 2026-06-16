# Codex Overlay Brief — the GPT-5.5 half of the CANON Federation

This documents the **second half** of the CANON.md federation: an independent
**GPT-5.5 (xhigh, via Codex CLI)** ratification pass over each of the 32 pieces, run
model-to-model against the Claude Opus 4.8 half. It mirrors how `DISSECT.md` was ratified.

## Engines

| Half | Engine | Effort | Role |
|---|---|---|---|
| Claude half (landed) | Claude Opus 4.8 | xhigh | per-piece audit + independent adversarial verify + synthesis |
| Codex half (this) | GPT-5.5 (`codex-cli 0.140.0`, `model=gpt-5.5`) | xhigh | independent re-verification + adjudication + sign-off |
| Final reconciliation | Claude Opus 4.8 adjudicator | xhigh | re-verify every disputed point vs code, produce both-model-signed records |

## Binding method (identical for both engines)

Prove, do not guess. Comments / docstrings / names / prior claims (including the *other*
model's record) are **claims, not evidence** — only executed code paths are. Every
load-bearing statement cites `path:line`, read from the actual file. Where code disagrees
with a comment, a name, or a prior claim, the **code wins**. Disagreement is preserved.

## What Codex does per piece (read-only)

Driver: `research/canon/run_codex_overlay.sh` (concurrency 3, `codex exec -s read-only`,
MCP disabled). For piece `CANON-NN`, Codex:
1. Reads the Claude record (`research/canon/sections/CANON-NN-*.md`), the adversarial verify
   verdict (`research/canon/verify/CANON-NN-*.verify.md`), and the `CANON-NN`-tagged items in
   `CANON.md` Sections 2 (seams) / 3 (risks) / 5 (disagreement register §A/§B/§C).
2. **Independently re-verifies** each load-bearing claim, contract, seam, and risk against the
   real code — it does **not** trust Claude's citations; it re-opens each `path:line`.
3. Adjudicates every disputed item: **CONFIRM / REFUTE / REFINE**, each with its own cite.
4. Hunts for defects both Claude passes missed.
5. Signs off: **RATIFY** (agree) / **OBJECT(n)** (agree with n refinements) / **REJECT**.

Output is captured between `<<<CODEX-VERDICT-START CANON-NN>>>` … `<<<CODEX-VERDICT-END>>>`
markers into `research/canon/codex/CANON-NN-*.codex.md`.

## Pilot result (CANON-15, validated before the full run)

`SIGN-OFF: OBJECT(6)` in 409s / 218k tokens. Codex **confirmed** H1 (poison-file drain wedge),
M2 (nonce replay), M4 (component allowlist downstream-only), M6 (decode error escape), the
stale/ghost re-execution, and queue growth; **downgraded** M3 (dismissed-but-active) and M5
(authority-inventory prose) to LOW/doc-drift with reasons; **corrected** several Claude
citations (incl. an impossible `broker.py:866`); and surfaced **two new defects both Claude
passes missed**: (a) the provisioner's 30s HTTP timeout is shorter than the broker's own wait
window → a host result inside the grace period is reported as failed → retry/double-execute
(`arclink_enrollment_provisioner.py:297-356` vs `arclink_operator_upgrade_broker.py:340-365`);
(b) malformed poll-seconds env is parsed *after* the pending JSON is written → broker returns
rejection while the queued host mutation still executes.

## Reconciliation & sign-off protocol (after all 32 Codex verdicts land)

For each piece, a Claude adjudicator re-verifies every disputed point **against code** and resolves:
- **Codex RATIFY** → promote piece to `both-model agreed`.
- **Codex OBJECT(refinements)** → fold each refinement after re-verifying it in code; promote to
  `both-model agreed (with refinements)`; apply agreed severity changes to the risk register.
- **Codex REJECT / residual disagreement** → adjudicate against code; the side proven by code
  wins; if genuinely undecidable, record it as a **standing two-model disagreement** (never averaged).

Then `CANON.md` is updated: provenance table (Codex pass + reconciliation LANDED), a per-piece
**sign-off** column, the disagreement register annotated with each resolution, the risk register
re-leveled, and a Federation sign-off section. Pieces are promoted to two-model-signed exactly
as `DISSECT.md`'s pieces were.
