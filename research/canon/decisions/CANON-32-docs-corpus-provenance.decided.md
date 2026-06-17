<<<DECIDED CANON-32 docs-corpus-provenance>>>
# CANON-32 — Documentation Corpus & Federation Provenance — FINAL DECIDED

Final adjudicator: Claude Opus 4.8 (1M). Mode: DECISION / Federation convergence with
Codex (GPT-5.5 xhigh) proposal in
`research/canon/decisions/CANON-32-docs-corpus-provenance.codex.md`.

Method: re-opened the live code (`tests/test_public_repo_hygiene.py`,
`tests/test_arclink_evidence.py`, `python/arclink_secrets_regex.py`), ran both named
proofs, and checked git tracking state. The symphony is intent; the code is reality;
the plan moves code toward the symphony while failing closed.

---

## DECISION 1 — Provider-name hygiene policy for canonical specs and redaction tests

**[VERDICT: agree-codex]** (with one factual correction + a guard-rail the operator
must hold going forward)

### The question (from NEEDS_DECISION.md CANON-32)
> `python3 tests/test_public_repo_hygiene.py` currently fails on provider-name hits in
> immutable/current spec text (`CANON.md`) and unrelated `tests/test_arclink_evidence.py`.
> Fixing that requires a hygiene policy/allowlist decision outside CANON-32's repair scope.

Net policy question: **is a provider name (`Chutes`) a secret that must be scrubbed
from every public file, or public-but-controlled provider context that may appear in
source-owned provenance/security/provider files?** And how do we keep the redaction
gate honest while answering that?

### My independent reasoning (code-grounded, before reconciling)

1. **The provider NAME is not a secret; the provider TOKEN is.** The real secret family
   is the Chutes API key shape `cpk_(live|test)[A-Za-z0-9_-]{8,}`
   (`python/arclink_secrets_regex.py:31`), sitting alongside OpenAI `sk-…` and Anthropic
   `sk-ant-…`. That regex — and only that regex — is what the symphony's "must never
   contain secret values" rule binds. The literal string "Chutes" is provider
   branding/context, exactly like "Stripe", "Cloudflare", or "Tailscale", which the
   symphony itself names in plaintext (`sovereign-control-node-symphony.md:1044`).

2. **The redaction PROOF is real and owned by CANON-23, not CANON-32.**
   `tests/test_arclink_evidence.py:55-65` (`test_redact_text_uses_shared_secret_families`)
   feeds `"chutes cpk_live" + "d"*12` through `evidence.redact_text` and asserts the
   token is redacted. That is the named local regression proof that provider *tokens*
   fail closed. It contains the word "Chutes" only because it is the test that proves
   the Chutes token redacts — scrubbing the name out of that file would gut the very
   evidence the symphony wants preserved.

3. **The fix Codex recommends is ALREADY in the tree and committed.** Re-opening the
   code: `tests/test_public_repo_hygiene.py:65-139` already carries a `PROVIDER_CODE_PATHS`
   path allowlist that includes `CANON.md` (`:71`), `DISSECT.md` (`:72`), and
   `tests/test_arclink_evidence.py` (`:123`), plus `PROVIDER_CONTEXT_DIRS = {research}`
   (`:137-139`). The gate (`provider_context_path`, `:162-163`; the scan,
   `test_provider_name_is_only_used_for_model_provider_context`, `:200-218`) allows a
   `Chutes` line only if (a) the file is a source-owned provider/provenance path, OR
   (b) the LINE itself matches `PROVIDER_CONTEXT_RE` (`:58-64`:
   inference/provider/model/key/secret/…). This is precisely the "narrow path/context
   allowlist" Codex describes — it is implemented, committed at HEAD `7cf2565`, and both
   named proofs PASS:
   - `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_public_repo_hygiene.py` → `PASS`, exit 0.
   - `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_arclink_evidence.py` → `OK` (30 tests), exit 0.

4. **The NEEDS_DECISION text is STALE.** It was authored when CANON.md/DISSECT.md were
   untracked `??` scratch files (matching the session-start git snapshot) and the
   allowlist had not landed. The "decision" the operator was asked to make has already
   been actioned correctly. So this is not "what should we build" — it is "ratify the
   shape that exists, and decide the standing review discipline."

5. **The gate still FAILS CLOSED on stray branding.** Simulated: a non-allowlisted file
   with `"Welcome to Chutes, the best place to be!"` (no provider-context keyword) is
   flagged (True); a contextual line `"Configure the Chutes inference provider key"` is
   allowed. So the in-context files that legitimately mention the provider
   (`AGENTS.md`, `GAPS.md`, `USER_JOURNEY.md`, `mission_status.md`) pass *line-by-line on
   context*, not via blanket allowlist — branding leakage outside provider context is
   still caught everywhere. The toothless-regex failure mode Codex warns about is
   avoided.

### Where I agree / differ from Codex

- **AGREE (core):** Treat the provider name as public-but-controlled context, not a
  secret. Keep `test_provider_name_is_only_used_for_model_provider_context()` fail-closed
  for general public files; explicitly allow source-owned provider/security/provenance
  contexts (`CANON.md`, `DISSECT.md`, `research/**`, provider docs/code/tests, and the
  evidence test). Do not rewrite CANON to hide provider truth; do not weaken
  private-operator-term scanning (`test_no_private_operator_names_in_public_files`,
  `:184-197`, untouched). Ratify the existing shape. Regression proofs are exactly the
  two named commands. **Codex is right on every load-bearing point.**

- **DIFFER (factual sharpening, not direction):** Codex frames this as a change to make
  ("Current `…:65-138` already matches this shape; ratify it"). Correct — and stronger
  than Codex states: it is **already committed at HEAD and both gates already pass**, so
  there is *no code change to land*; the deliverable is a one-line ratification note plus
  a standing review rule. I also pin the precise division of ownership Codex leaves
  implicit: the *name*-hygiene gate is CANON-32-owned (`test_public_repo_hygiene.py`); the
  *token*-redaction proof is CANON-23-owned (`test_arclink_evidence.py:55-65`,
  `arclink_secrets_regex.py:31`). The two must not be conflated — that separation is what
  lets us allowlist the name without ever touching the secret guard.

- **ADD (guard-rail Codex gestures at but doesn't operationalize):** allowlist additions
  to `PROVIDER_CODE_PATHS` are **policy changes**, not mechanical fixes, and must be
  reviewed as such. Concretely: any new entry should require the file to be a genuine
  source-owned provider/provenance/security artifact whose lines either carry provider
  context or are deep code-cited analysis. The cheap default for a *new* file that
  happens to mention the provider is to write the line in provider context (so it passes
  on `PROVIDER_CONTEXT_RE`), NOT to add the whole path to the allowlist.

### FINAL PLAN

1. **Ratify the committed policy as-is. No code change.** The path/context allowlist in
   `tests/test_public_repo_hygiene.py:65-218` is the correct, symphony-aligned resolution
   and is already live at HEAD `7cf2565`. Mark CANON-32's deferred item RESOLVED.

2. **Record the ownership split in the corpus** (1-line each, in the CANON-32 record /
   COVERAGE_MATRIX so it doesn't re-defer): name-hygiene gate = CANON-32
   (`test_public_repo_hygiene.py`); provider-token redaction proof = CANON-23
   (`test_arclink_evidence.py:55-65` over `arclink_secrets_regex.py:31`). Provider name =
   controlled public context; provider token = secret, fails closed.

3. **Standing review rule (policy, not code):** treat any future addition to
   `PROVIDER_CODE_PATHS` / `PROVIDER_CONTEXT_DIRS` as a reviewed policy change. New files
   should prefer in-context phrasing (caught by `PROVIDER_CONTEXT_RE`) over a blanket
   path allowlist; only genuine source-owned provider/provenance/security docs earn a
   path entry. Do **not** broaden `PROVIDER_CONTEXT_RE` to wave through every `Chutes`
   line — that would make the gate toothless (Codex's residual-risk warning, ratified).

4. **Keep the named proofs as the regression gate.** Both already run in this repair pass
   and pass; they are the standing local regression for this policy:
   `tests/test_public_repo_hygiene.py` (name hygiene + fail-closed on stray branding) and
   `tests/test_arclink_evidence.py` (token redaction). No new live-proof gate is required
   — this is a static-source/redaction policy with no external system, so a local
   regression proof is the complete proof obligation.

### Symphony anchor (quoted)

- **Secrets, Keys, And Rotation** (`sovereign-control-node-symphony.md:1047-1048`):
  > "Public docs, chat transcripts, logs, evidence artifacts, command arguments, and
  > generated markdown must never contain **secret values**."

  The binding object is *secret values* (the `cpk_…` token), which the gate redacts and
  the evidence test proves — not the provider name, which the symphony itself prints in
  the clear (`:1044` lists "Chutes/provider" as a named credential family, naming the
  provider while protecting its token).

- **Whole-System Traversal** (`:158-160`):
  > "Every step should have a local source owner, a local regression or dry-run proof
  > where possible, and a named live proof gate where external systems are required."

  Satisfied exactly: name-hygiene gate owned by CANON-32, token-redaction proof owned by
  CANON-23, both with passing local regressions; no external system, so no live gate is
  owed.

- **Cross-Surface Experience Standard / same-truth principle** (Whole-System Traversal
  step 9, `:152-153`: "Operator Raven, admin dashboard, CLI, diagnostics, live proof, and
  evidence rails show the **same system truth**"): scrubbing the provider name out of
  CANON/DISSECT/evidence would make the corpus *less* truthful than the running system,
  violating same-truth. Keeping the name (token-protected) preserves it.

### Effort / blast-radius

- **Effort: low.** Zero code change (already committed); deliverable is a ratification
  note + ownership line in the corpus + a standing review rule. Codex estimated "low";
  I lower it further to "essentially documentation only" because the implementation
  already landed and both gates are green.

- **Blast-radius: minimal.** Touches policy/provenance docs only. The hygiene gate and
  redaction proof are unchanged and passing. No runtime, schema, surface, or release
  artifact is affected. The only residual risk (Codex's, ratified) is human:
  allowlisted files can over-use the provider name, so allowlist growth must be reviewed
  as policy — captured as the standing review rule above.

---

## STANDING DISAGREEMENTS

**None.** This is not a product fork — there is a single correct, symphony-aligned
resolution and it is already implemented. The operator's only ongoing obligation is the
review discipline (item 3 of the Final Plan): keep `PROVIDER_CODE_PATHS` additions
reviewed as policy and never broaden `PROVIDER_CONTEXT_RE` into a blanket pass.

<<<END DECIDED CANON-32>>>
