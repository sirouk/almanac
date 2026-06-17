# CANON-30 — Hermes Plugins & Bridges — DECIDED (final adjudication)

- Piece: CANON-30 (Hermes Plugins & Bridges)
- Codex proposal: `research/canon/decisions/CANON-30-hermes-plugins.codex.md`
- Adjudicator: Claude Opus 4.8 (1M) final adjudicator, DECISION mode.
- Method: formed an independent view per decision from the symphony north star + re-opened
  code, then converged with Codex. Code wins over name/comment/prior-claim. Symphony is intent.
- Convergence: **2/2 decisions converged to a single recommended plan.** One genuine product
  fork surfaced inside Decision 1 (dependency policy) and is recorded as a standing operator
  call.

---

## DECISION 1 — Replace installer regex YAML edits with a comment-preserving parser

[VERDICT: refine]

### The question
The four `python3` heredoc editors in `bin/install-arclink-plugins.sh` mutate
`$HERMES_HOME/config.yaml` by indentation/regex surgery (`:64-167` plugins,
`:169-261` theme, `:263-372` hidden, `:374-456` visible). The deferred call: replace
this with a real comment-preserving YAML round-trip editor. The repair already added a
single full-file backup (`backup_config_file_once`, `:53-58,660`).

### My independent reasoning (symphony + code first)
The symphony makes `config.yaml` a **Captain/operator-owned source surface that must be
preserved**: Configuration/Schema/Migration — "understand which config/state files they own
and which private files they must preserve"; and "fail with a clear upgrade requirement"
rather than silently corrupt. So the *contract* Codex anchors to is exactly right: this YAML
must survive comments, order, and future nested keys.

But the code reality moves the urgency. I ran the focused suite: the regex editor **already
passes** the two contract tests the repair installed —
`test_install_arclink_plugins_preserves_comments_and_future_nested_config`
(`tests/test_arclink_plugins.py:320-368`) asserts the operator comment, the
`defaults:\n    future:\n      nested: preserve-me` nested block, and the `mcp_servers`
block all survive; the preservation/theme tests pass too (`PASS all ArcLink plugin tests`).
So today the regex editor is **not silently corrupting** the documented shapes; the adjudicated
risk is **MEDIUM "adversarial/tab-indented config could be mis-edited"**, not an active defect.

I also caught two inaccuracies in Codex's plan that I will not carry forward:
- The `.arclink-config.yaml.lock` "existing convention" Codex cites **does not exist** —
  `rg` finds no lock/flock in `bin/install-arclink-plugins.sh`. There is no lock to reuse.
- `ruamel.yaml` is **not** pinned anywhere; `requirements-dev.txt:5` pins only `PyYAML`, and
  PyYAML drops comments — so it cannot be the parser, and `ruamel.yaml` is a genuinely *new*
  third-party dependency, not a re-use.

The dependency placement matters because the editor runs **on host/runtime install lanes**,
not just dev: `bin/init.sh:296,317`, `bin/install-deployment-hermes-home.sh`,
`bin/bootstrap-curator.sh:1002,1021`, `bin/refresh-agent-install.sh`. Adding a pip
dependency that must be importable on every admitted host is a real Supply-Chain expansion
("Python dependencies ... built from known source and validated before deployment") — it must
be pinned and **preflighted**, and the script must **fail closed with a clear upgrade
requirement** if it is missing, exactly as the Migration section demands.

### Where I agree / differ from Codex
- AGREE: extract the four heredocs into ONE source-owned Python helper
  (`python/arclink_hermes_config.py`) that edits only `plugins.enabled/disabled`,
  `dashboard.theme`, `dashboard.hidden_plugins`; preserves comments/order/anchors; writes
  atomically; reuses the existing backup; and **fails closed** if round-trip parsing is
  unavailable. This is the right structural move and the right symphony anchor.
- DIFFER (refine, not adopt-as-written):
  1. Drop the non-existent `.arclink-config.yaml.lock` claim — there is nothing to reuse.
  2. Treat `ruamel.yaml` as a NEW host-lane dependency, so the **dependency-vs-no-dependency
     choice is a genuine operator fork** (see Standing Disagreements). Codex assumed
     ruamel is acceptable on every host; that is the operator's supply-chain call, not ours
     to bake in silently.
  3. Sequencing: because the regex editor currently passes CI, this is **hardening, not a
     break-fix**. It should land behind the same green contract tests plus a NEW adversarial
     fixture ("tab-indented + anchored config round-trips byte-stable" and "parser missing ->
     clear exit-with-upgrade-requirement"). The new fixture is the named local regression
     proof; live install on a host is the named live-proof gate (it folds into the existing
     `PG-HERMES` install proof, not a new gate).

### FINAL PLAN
1. Add `python/arclink_hermes_config.py` exporting one editor (e.g.
   `apply_managed_plugin_config(config_path, *, enable, disable_remove, theme, hidden_add,
   visible_remove)`) that:
   - tries `ruamel.yaml` (round-trip) first; on `ImportError` **exits non-zero with a clear
     "comment-preserving YAML editor unavailable; install ruamel.yaml to manage
     config.yaml" message** — never falls back to lossy PyYAML, never silently writes.
   - edits only the four managed keys; preserves comments/order/anchors/flow.
   - writes atomically (temp + `os.replace`) after the existing `*.arclink-pre-plugin-install.bak`
     backup is taken.
2. Replace the four heredocs in `bin/install-arclink-plugins.sh:64-456` with calls to it.
3. Pin `ruamel.yaml` in `requirements-dev.txt` AND the **runtime/host-install dependency path**
   that the install lanes actually use (the same lane `Dockerfile`/bootstrap installs deploy
   deps), and add a one-line preflight in the installer (or its bootstrap) so the failure is
   "clear upgrade requirement," not an import traceback mid-install.
4. Tests: keep the two existing preservation/comment tests green; add (a) an adversarial
   tab/anchor/flow-style round-trip fixture, and (b) a "parser missing fails closed with the
   upgrade message" fixture. These are the local regression proof.

OPERATOR FORK (must decide before build): adopt `ruamel.yaml` on host install lanes
(Codex's path, cleanest), OR keep a **pure-stdlib hardened tokenizer** (no new dependency,
but bounded to the documented shapes and still regex-class). My recommendation is
`ruamel.yaml` *if* the operator accepts one more pinned, preflighted host dependency; the
boringly-reliable-underneath principle favors a real parser over an ever-growing regex.

### Symphony anchor (quoted)
`Configuration, Schema, And Migration` — "all understand which config/state files they own and
which private files they must preserve" and "remain compatible within a release or **fail with a
clear upgrade requirement**." `Supply Chain, Build, And Release Integrity` — "Python
dependencies ... built from known source and validated before deployment."

### Effort / blast-radius
Effort: **med**. Blast radius: `bin/install-arclink-plugins.sh`, new `python/arclink_hermes_config.py`,
runtime+dev dependency manifests + installer preflight, focused plugin tests. Runs on every host
install lane, so the fail-closed-on-missing-parser behavior is the load-bearing safety property.

---

## DECISION 2 — Redesign Drive path safety around root policy + fd-anchored operations

[VERDICT: refine]

### The question
Drive's sensitive-file protection is a filename/dir **denylist** heuristic
(`_is_sensitive_path` `:588-609`) and its access check resolves with `strict=False`
(`_assert_accessible_path` `:1168-1181`, `resolve(strict=False)` `:1169,1176`), so a symlink
swapped between check and use (TOCTOU) is conceivable and an unlisted secret name under a root
is browsable. The repair fixed the empty-root guard only. The deferred call: full
denylist/TOCTOU redesign — likely fd-anchored ops + an allowlist root policy.

### My independent reasoning (symphony + code first)
The symphony is unambiguous that the **boundary is roots+isolation, not filenames**:
Pods/Isolation/SOUL — "Pods cannot read or write another Captain's state" and "Dashboard,
Drive, Code, Terminal ... routes are scoped by deployment/user identity"; Abuse/Safety —
"Upload/file safeguards for ... symlink, path escape ... cases in Drive." A denylist of secret
names can never be the security boundary (it always misses the next unlisted name), and
`resolve(strict=False)` followed by an unguarded open is a classic TOCTOU window. So Codex's
direction — make the **operator/provisioner-owned root allowlist** the authorization boundary,
keep the secret-name checks only as defense-in-depth, and close the race with **fd-anchored**
helpers (`openat`/`dir_fd`, `O_NOFOLLOW`, `fstat`, atomic `renameat`/`replace`) — is the
correct symphony-grounded shape.

Two code facts sharpen the plan and one tempers the urgency:
- **The allowlist root model already half-exists.** Linked writes are *already* gated through a
  manifest-approved `source_path` (`_linked_writable_source` `:261-289`, `_linked_target_allowed`
  `:251-258`). So "linked roots only cross into manifest-approved source_path, then become a new
  anchored root" is **extending an existing pattern**, not inventing one. Good — lower risk than
  Codex's "high" framing implies for that sub-part.
- **Symlink-escape coverage is genuinely partial.** `_assert_no_symlink_escape` is applied
  ONLY on copy (`:1457`), not on move/upload/mkdir/trash/restore (`:1859,2013,1834,1942,1963`).
  So the fd-anchoring is the real gap-closer and must cover all mutating paths, exactly as
  Codex lists.
- **Drive and Code share the SAME resolve-then-act shape but in SEPARATE code.** Drive
  `_assert_accessible_path` `:1168` and Code `_assert_accessible_path`
  (`code/dashboard/plugin_api.py:799-815`) both `resolve(strict=False)` and both act
  afterward. So Codex's instinct — "likely shared root-policy tests so Drive and Code do not
  present conflicting filesystem truth" — is verified: the redesign must cover **both
  plugins** to keep cross-surface truth aligned (Cross-Surface Experience Standard: "same truth
  across surfaces").

Tempering: this is a **risk-reduction redesign of an already-confined surface** (denylist
+ `..` rejection + root confinement + Linked-403 are all live and the path is reverse-proxied
behind ArcLink's signed session, GAP-019 Docker-mode-only). The adjudicated severity is **LOW**.
So it is the right shape but **high effort against a low-severity, pre-confined surface** — it
should be staged, not rushed, and must FAIL CLOSED at every step.

### Where I agree / differ from Codex
- AGREE with the whole architecture: root allowlist = authorization; denylist = defense in
  depth (keep `:588-614`); fd-anchored helpers for read/preview/download/upload/mkdir/move/copy/
  trash/restore; linked roots cross only into manifest-approved `source_path` then anchor;
  arbitrary symlinks rejected; redacted 403/409 evidence; cover Code too for surface parity.
- DIFFER (refine): (1) Lower the framing from net-new-design to **extend the existing
  manifest-approved-root model** (`_linked_writable_source`) — it is already the allowlist Codex
  describes. (2) **Stage it** behind a shared root-policy + symlink-race test harness *first*
  (cheap, names the regression proof), then convert mutating ops to fd-anchored helpers
  op-by-op, each landing fail-closed. (3) Make explicit the residual-risk **documentation** Codex
  flags (a secret deliberately stored inside an exposed workspace is visible to that Pod owner —
  that is policy, mitigated by keeping secrets in private state/secrets paths, which
  `_is_sensitive_path` already blocks for `$HERMES_HOME/{secrets,state}`).

### FINAL PLAN
1. **Land the test harness first** (low cost, names the proof): a symlink-race / TOCTOU fixture
   that swaps a symlink between check and use across move/upload/mkdir/trash/restore/copy, plus a
   shared root-policy assertion that Drive and Code reject the same escape set identically. This
   is the local regression proof and prevents regressions during the staged conversion.
2. **Make the allowlist explicit**: formalize the operator/provisioner-owned exposed-root set
   (Workspace/Fleet/Linked + manifest-approved Linked `source_path` entries) as the authorization
   boundary, reusing `_linked_writable_source`/`_linked_target_allowed`. Keep
   `_is_sensitive_path`/`_assert_not_sensitive` (`:588-614`) as defense-in-depth only.
3. **Convert mutating ops to fd-anchored helpers** op-by-op (`openat`/`dir_fd`, `O_NOFOLLOW`,
   `fstat` parent-dir checks, atomic `os.replace`/`renameat`-class), starting with the ops that
   today lack symlink-escape coverage (move/upload/mkdir/trash/restore) since copy already has
   `_assert_no_symlink_escape`. Each op fails closed on race detection (403/409, redacted).
4. **Mirror in Code** (`code/dashboard/plugin_api.py:799-815`) so the two plugins present
   identical filesystem truth.
5. **Document the residual policy**: secrets deliberately placed inside an exposed workspace are
   visible to that Pod's owner; secrets belong in private state/secrets paths (already blocked).
6. Named live-proof gate: folds into `PG-HERMES` (authorized browser proof of Drive/Code file
   ops), no new gate.

### Symphony anchor (quoted)
`Pods, Isolation, And SOUL` — "Pods cannot read or write another Captain's state" and "Dashboard,
Drive, Code, Terminal, MCP, Notion, SSOT, and share routes are scoped by deployment/user
identity." `Abuse, Safety, And Platform Boundaries` — "Upload/file safeguards for ... symlink,
path escape ... cases in Drive."

### Effort / blast-radius
Effort: **high** (but stageable; step 1 is low and de-risks the rest). Blast radius: Drive
backend path layer (all mutating ops), Code path layer for parity, linked-share semantics,
upload/trash/copy/move/restore behavior, shared root-policy tests. Pre-confined LOW-severity
surface, so the value is hardening + cross-surface truth, and every step must fail closed.

---

## STANDING DISAGREEMENTS (genuine operator product forks)

1. **Decision 1 dependency policy — adopt `ruamel.yaml` on host install lanes, or stay
   stdlib?** Codex assumes ruamel is acceptable; I treat it as a NEW pinned host-lane
   dependency. The operator must choose: (a) add a pinned, preflighted `ruamel.yaml` to the
   runtime/host install path (cleanest, a real parser, my recommendation), or (b) keep a pure
   stdlib hardened tokenizer (no new dependency, but bounded to documented shapes and still
   regex-class). Either way the editor must fail closed and preserve comments — only the
   dependency posture is the operator's call.
