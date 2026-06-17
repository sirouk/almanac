# CANON-27 — Config & Environment — DECIDED (final adjudication)

Adjudicator: Claude Opus 4.8 (1M) FINAL ADJUDICATOR, DECISION mode.
Method: formed an independent view per deferred item against the symphony north star
and re-opened code (Read / rg / python parse / live test run), THEN reconciled with
Codex (GPT-5.5 xhigh) recommendations in
`research/canon/decisions/CANON-27-config-environment.codex.md`. Code wins over name,
comment, or prior claim. Baseline verified green:
`test_docker_authority_inventory_matches_compose_boundary`,
`test_operator_upgrade_broker_compose_boundary_minimizes_env_and_private_mounts`, and all
10 repo-sync regressions PASS today.

Federation outcome: **2 decisions, both `refine` (Codex is right in direction; I sharpen
the plan with code facts Codex's proposal under-specified or slightly overstated).** No
standing disagreements; no product fork the operator must arbitrate.

---

## DECISION 1 — `team-resources.example.tsv` is pipe-delimited despite the `.tsv` name  [VERDICT: refine]

### The question (deferred)
`config/team-resources.example.tsv` remains pipe (`|`) delimited despite the `.tsv`
extension; renaming is a public/operator contract change. Keep-and-document, rename, or
support both?

### Independent reasoning (code-grounded)
The name is a misnomer, but it is a *load-bearing operator contract*, not a bug:
- `config/team-resources.example.tsv:1` header is literally `# slug|git-url|branch|note`;
  rows 5-7 are pipe-delimited.
- `bin/clone-team-resources.sh:54` parses `IFS='|' read -r SLUG URL BRANCH NOTE_TEXT`.
  The default private path is `arclink-priv/config/team-resources.tsv`
  (`bin/clone-team-resources.sh:25`), and the operator may redirect it via
  `ARCLINK_TEAM_RESOURCES_MANIFEST` (`:25`).
- `docs/org-profile.md:74,83` documents both the private `.tsv` and the public example
  `.tsv` as the contract.
- A regression already pins the *security* contract:
  `tests/test_arclink_repo_sync.py:641` (`test_clone_team_resources_rejects_unsafe_slugs_before_git_operations`)
  proves unsafe slugs are rejected **before** any git call (`:696` asserts the fake git log
  never gets written).

So the real risk is narrow and specific: a tab-delimited manifest (the footgun the `.tsv`
name actively invites) does **not** fail closed. In `clone-team-resources.sh`, a tab line
`slug\turl\tbranch` read with `IFS='|'` lands the entire line in `$SLUG`. The slug guard
(`safe_resource_slug`, `:65`) would likely reject it as unsafe — but the line could also
contain embedded whitespace that passes after trimming (`:55-62`), and at minimum the
operator gets a confusing "unsafe slug" rejection instead of "wrong delimiter." There is no
explicit "this is the wrong format" signal, and no test proving a tab manifest fails before
git work for the *format* reason rather than incidentally via the slug guard.

Renaming to `.psv` is the "clean" option but it is exactly the
move the symphony tells us NOT to make: it breaks the public example, the documented private
path, the `docs/org-profile.md` contract, every operator's already-copied private manifest,
and the override env var semantics — for zero functional gain. Supporting both `.tsv` and
`.psv` manifests creates two truths for the same data (violates "same truth across
surfaces"). Both are wrong.

### Where I agree / differ from Codex
Agree with Codex's core call: **keep the filename and delimiter as the v1 contract; make
the contract explicit; add a fail-closed preflight + a test.** That is the symphony-correct
path (preserve private operator state, make the actual behavior locally test-proven).

I refine two things:
1. Codex proposes a *new* `bin/clone-team-resources.sh --check` flag and a *new*
   `tests/test_arclink_repo_sync.py` test "for valid pipe manifests and malformed tab
   manifests." Good intent, but the test file **already exists and is writable** and already
   owns this script's regressions (`:641,:711`). So I scope the test as an *addition to the
   existing file's `main()` runner*, not a new file — keeping CANON-27/CANON-31 test
   ownership in one place and avoiding a stray new file.
2. The preflight should be **inline and always-on (fail-closed by default), not an opt-in
   `--check` flag.** A flag the operator must remember to pass is not "fails closed." The
   right shape: when a non-comment, non-blank manifest line contains a TAB and no `|`,
   `warn` with a redacted line number and the expected `slug|git-url|branch|note` syntax,
   then `exit 1` **before** the git/mkdir/sudo loop body. (Today the sudo check at `:45-48`
   and `mkdir` at `:52` already run before the parse loop; the format preflight must run
   before those side effects too — read the manifest once, validate, then proceed.)

### FINAL PLAN
1. `config/team-resources.example.tsv`: keep filename + pipe delimiter. Strengthen the
   header comment to name the legacy-extension reality explicitly, e.g. add a line:
   `# NOTE: this file is PIPE-delimited (|), not tab. The .tsv extension is a legacy name.`
2. `bin/clone-team-resources.sh`: add an always-on format preflight that runs once over the
   manifest before the clone loop (and before the `mkdir -p "$VAULT_REPOS_DIR"` side effect):
   for each non-comment (`#`), non-blank line, require at least one `|`; if a line contains a
   TAB and no `|`, emit `warn "manifest line N looks tab-delimited; expected slug|git-url|branch|note (pipe-delimited)"`
   using the **line number only** (no line contents → redacted), and `exit 1`. Lines that are
   valid pipe lines with a missing URL keep today's per-line skip behavior (`:69-72`) — the
   preflight only fails closed on the structural wrong-delimiter case, preserving the
   intentional "skip bad row, keep going" semantics for content errors.
3. `tests/test_arclink_repo_sync.py`: add
   `test_clone_team_resources_rejects_tab_delimited_manifest_before_git` modeled on the
   existing slug test (`:641`): write a tab-delimited manifest, run the script with the same
   fake `sudo`/`git` shims, assert `returncode != 0`, assert the fake git log was never
   written, and assert the warning names the expected pipe syntax. Add a positive companion
   (or extend the existing test) proving a valid pipe manifest still reaches the (faked) git
   path. Register both in `main()` (`:701-712`) and bump the count string.
4. `docs/org-profile.md`: one-line note next to the `.tsv` references (`:74,83`) that the
   manifest is pipe-delimited despite the extension.

### Symphony anchor
Governance And Proof (line 1656): "A claim is local-real only when source and regression
tests prove it." — the fail-closed wrong-delimiter behavior becomes source + test, not just
a name. Configuration, Schema, And Migration (line 1075): deploy flows "understand which
config/state files they own and which **private files they must preserve**" — keeping the
private `team-resources.tsv` filename/contract honors that; renaming would silently
invalidate already-copied private manifests. Also Governance And Proof (line 1657): a live
claim is real only "after authorized live proof" — the script "FAILS CLOSED" on malformed
input before doing privileged git/sudo work.

### Effort / blast-radius
**low.** Touches `config/team-resources.example.tsv` (comment), `bin/clone-team-resources.sh`
(one preflight loop), `tests/test_arclink_repo_sync.py` (one+ test + runner line),
`docs/org-profile.md` (one note). No public-contract rename, no two-format ambiguity, no
change to the slug-safety regression. Backward compatible with every existing private
manifest.

---

## DECISION 2 — do NOT derive every Docker-authority inventory field from Compose without CANON-12/25 owner agreement  [VERDICT: refine]

### The question (deferred)
Expanding the docker-authority inventory drift test to derive *every* structured field from
Compose crosses CANON-12/25 boundaries and needs owner agreement. Expand to full derivation,
keep as-is, or take a middle path?

### Independent reasoning (code-grounded)
Re-opened the parser and test. What Compose actually authors today and what the test derives:
- `tests/test_arclink_docker.py:401-421` `compose_docker_authority_surface()` parses from the
  raw compose block: `docker_socket` (from the `/var/run/docker.sock` mount + `:ro` mode,
  `:404-411`), `explicit_root` (regex `user: "0:0"`, `:412`), `linux_capabilities`
  (`compose_capability_boundary`, `:417`), `compose_networks` (`:418`).
- The drift test (`:1755-1773`) cross-checks exactly those four plus `default_network`
  (derived as `"default" in compose_networks`, `:1771-1772`). Five Compose-derived facts.
- `container_user` is the documented overstatement (CONTRACT #4 in the reconciled record):
  `:1775-1776` only asserts `container_user == "root"` *conditioned on* the already-derived
  `explicit_root`; `:1784-1788` asserts `container_user == "arclink"` *conditioned on*
  socket=="write" and not-root. Neither parses a `user:` line for the value itself.

I parsed compose to settle whether `container_user` is even Compose-derivable. The three
`arclink` socket-writer brokers — `deployment-exec-broker`, `agent-supervisor-broker`,
`gateway-exec-broker` — have **NO `user:` line and no `image:`/`build:` line** in their
blocks. Their runtime user `arclink` comes from the shared image's default
(Dockerfile/entrypoint, operator-owned build context), NOT from Compose. The only `user:`
lines among authority services are `user: "0:0"` (`compose.yaml:680,848,886,919`), which is
already the source for `explicit_root`.

This is decisive. It means:
- The `"root"` half of `container_user` IS Compose-derivable, but only redundantly — it is
  the *same* `user: "0:0"` line `explicit_root` already parses. Deriving it adds a second
  read of one fact.
- The `"arclink"` half is **provably NOT Compose-authored** — there is no Compose token to
  parse. Mechanically deriving it from Compose is impossible; it is an image/operator policy
  fact. Any "derive from compose" rule would have to fall back to a literal here anyway.

And the genuinely operator/policy-owned fields the inventory carries — `authority_class`,
`purpose`, `why_socket_needed`, `residual_policy_state`, `proxy_or_broker_candidate_status`,
the `gap_019_b2_review` allowlist/monitoring/enforcement records (`:1791-1799`),
`gap_019_al_controls` (`:1801-1808`), the `trusted_host_risk_acceptance_gate` — are the
THREAT MODEL and RISK-ACCEPTANCE evidence. Compose is the runtime fact source; it is not and
must not become the *author* of the residual-risk story. Mechanically deriving these would
flatten human-reviewed policy into brittle parser guesses and manufacture false confidence —
the opposite of what the symphony asks.

### Where I agree / differ from Codex
Agree fully with Codex's thesis and its three-bucket structure: (a) Compose-owned objective
fields stay parsed + compared; (b) inventory/operator-owned policy fields stay explicit
policy evidence; (c) keep the targeted minimization test. This is the symphony-correct middle
path: increase local proof for objective facts without pretending Compose can author policy.

I refine Codex's one concrete code change. Codex says "fix the current overstatement by
deriving `container_user` from `user:` instead of literals where possible." My compose parse
shows "where possible" reduces to *only the root case, which is redundant with
`explicit_root`*, and is *impossible for the `arclink` case*. So the cleaner fix is NOT to
add a half-working `container_user` parser. Instead:
1. **Tighten the root case to use the existing derivation directly** — i.e. assert
   `container_user == "root"` *iff* `explicit_root` is true and assert it is `"arclink"`
   *iff* the service is in the image-default set (socket-writer, not explicit-root). That is
   what the test already does at `:1775-1788`; the fix is to make the field-ownership
   **explicit and documented** so the overstatement ("both-ends-verified from parsed
   compose") is corrected to its true status ("derived for root via explicit_root;
   image-default classification for arclink, asserted by policy"). No new fragile parser.
2. Add an explicit **field-ownership matrix** as a comment/docstring block at the top of the
   drift test (or a small `# field ownership:` table) naming, per field: Compose-derived
   (`docker_socket`, `explicit_root`, `linux_capabilities`, `compose_networks`,
   `default_network`) vs. image/operator-policy (`container_user`-as-`arclink`,
   `authority_class`, `purpose`, `why_socket_needed`, `residual_policy_state`,
   `gap_019_b2_review`, `gap_019_al_controls`, `trusted_host_risk_acceptance_gate`). This is
   the "tests encode the policy decision" the symphony demands.

I also drop Codex's tentative additions ("default/internal/egress network classification,
broad env/secret/private mount presence where parseable") from the *required scope* of this
decision: `default_network` is already derived (`:1771`); internal/egress and env/mount
presence are real but they are CANON-12/25-owned expansions that this decision explicitly
says need owner agreement — folding them in here would re-commit the boundary crossing we are
declining. Keep them as a recorded follow-up for CANON-12/25, gated on owner agreement, not
as CANON-27 work.

### FINAL PLAN
1. Do **not** expand the drift test to mechanically derive every structured/policy field
   from Compose. Hold the CANON-12/25 boundary.
2. `tests/test_arclink_docker.py`: add an explicit field-ownership comment/matrix at the top
   of `test_docker_authority_inventory_matches_compose_boundary` (near `:1738`) splitting the
   inventory fields into **Compose-derived** (cross-checked: `docker_socket`, `explicit_root`,
   `linux_capabilities`, `compose_networks`, `default_network`) vs.
   **image/operator-policy** (asserted as policy evidence: `container_user` for the `arclink`
   case, `authority_class`, `purpose`, `why_socket_needed`, `residual_policy_state`,
   `proxy_or_broker_candidate_status`, `gap_019_b2_review`, `gap_019_al_controls`,
   trusted-host acceptance gate). Correct any inline comment that implies `container_user` is
   "parsed from compose."
3. Keep the existing conditional `container_user` assertions (`:1775-1788`) — they correctly
   tie the `"root"` classification to the Compose-derived `explicit_root` and the `"arclink"`
   classification to the image-default (no-`user:`-line) socket writers. Do NOT add a
   `user:`-line parser for `container_user`: it is redundant for root and impossible for
   `arclink` (verified: brokers carry no `user:`/`image:`/`build:` line).
4. Keep the targeted minimization test
   `test_operator_upgrade_broker_compose_boundary_minimizes_env_and_private_mounts`
   (`:1612`) as the model for objective env/mount-presence proof.
5. If/when CANON-12/25 owners agree, open a follow-up (not CANON-27) to add Compose-derived
   internal/egress network classification and broad env/secret/private-mount presence checks.
   Record it as a residual, owner-gated expansion.

### Symphony anchor
Governance And Proof (line 1659): "A policy choice stays a policy question until the
operator/product decision is recorded and **tests encode it**." — the field-ownership matrix
records, in the test, which fields are Compose-objective and which are operator policy.
Governance And Proof (line 1661): "A residual risk stays visible until removed or explicitly
accepted." — `residual_policy_state` / `gap_019_*` / the trusted-host acceptance gate stay
operator-owned policy evidence, not parser output. Ground Truth Boundary spirit (operators
own hosts/secrets/policy; "boringly reliable underneath"): Compose is the boring runtime
fact source; the threat model is the operator's, and the drift test must not pretend
otherwise.

### Effort / blast-radius
**med.** Touches `tests/test_arclink_docker.py` (comment/matrix + corrected inline
wording; the assertions already pass so no behavioral test change is forced), and optionally
`config/docker-authority-inventory.json` only if a field-ownership label or the stale
"writeable Docker socket" / egress prose is updated in the same pass (those are separate
LOW prose-drift items already tracked in the reconciled record — fold in only if desired).
No change to the Compose parser, no CANON-12/25 boundary crossing, baseline tests stay green.

---

## STANDING DISAGREEMENTS
None. Both decisions are `refine` over Codex — same direction, sharpened with the compose
parse facts (the `arclink` brokers have no `user:`/`image:` line, so `container_user` is not
Compose-derivable; the repo-sync test file already exists and is writable, so the new
coverage is an addition not a new file; the preflight should be always-on, not an opt-in
flag). No genuine product fork requiring an operator pick.
