# CANON-19 — Workspace & Dashboard — ADVERSARIAL VERIFY

Verifier: independent Opus 4.8 skeptic. Method: re-opened all five tracked files plus the
producers/consumers at each seam. Every line below was read in the live tree, not trusted from
the record.

## HEADLINE VERDICT
The record is **mostly accurate on the read-model / queueing / proxy mechanics**, but contains
**one decisive, security-relevant refutation**: its central DRIFT #1 / seam-#6 / INFO-risk claim
that the auth-proxy SSO cookie path is **dead code with no in-repo producer** is **FALSE**. There
is a fully wired in-repo producer chain that writes `sso_session_secret`/`sso_subject` into the
access file in Docker/domain mode. The SSO path is **live**, and it is a **per-user,
cross-deployment, domain-scoped auth cookie** — a real auth surface the record dismissed to INFO.
Because of this, the record's RISKS section is mis-calibrated (it understates a live SSO
single-sign-on surface) and its self-confidence ("dead by default", medium confidence) was wrong
in the direction that matters for security. Net: the record is **usable but must not be trusted on
the SSO claim**, and its seam #6 "both-ends-verified" marker is invalid.

---

## REFUTATIONS (record claim → finding)

### R1 — REFUTED (HIGH): "SSO cookie path is dead/dormant; no in-repo producer writes the SSO secret"
Record lines 128, 139, 155, 168, 148 all assert no producer writes `sso_session_secret`/
`sso_subject`, concluding the SSO machinery is "unreachable / dead / aspirational" (INFO).

Live producers DO exist, all in-repo:
- `bin/install-deployment-hermes-home.sh:163-171` writes `"sso_session_secret": sso_session_secret`
  and `"sso_subject": sso_subject` into the access-file payload (`arclink-web-access.json`).
- The value is sourced at `bin/install-deployment-hermes-home.sh:92-99` from
  `ARCLINK_DASHBOARD_SSO_SECRET` / `ARCLINK_DASHBOARD_SSO_SECRET_FILE` (or pre-existing access
  file).
- `arclink_provisioning.py:1372-1377` injects `ARCLINK_DASHBOARD_SSO_SECRET_FILE`,
  `ARCLINK_DASHBOARD_SSO_SUBJECT`, `ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN`,
  `ARCLINK_DASHBOARD_SSO_REVOKED_BEFORE` into the hermes-home installer container env.
- `bin/arclink-docker.sh:1895-1902` generates the `dashboard_sso_secret` file
  (`sso_secret_for_subject`) and mounts it as a compose secret
  (`/run/secrets/dashboard_sso_secret`, see `bin/arclink-docker.sh:2024-2026`).
- Consumer side then becomes live: `arclink_dashboard_auth_proxy.py:101-103` (`_sso_token_secret`),
  `:609-619` (`_make_sso_token`), `:674-693` (`_valid_sso_cookie`), and `_authorized` accepts a
  valid SSO cookie at `:701`.

The record's own self-check #1 admitted "I only grepped `python/` and `bin/`" — but the producer
**is in `bin/`** (`install-deployment-hermes-home.sh`). The grep was simply missed. CODE WINS:
the SSO path is reachable whenever the Docker provisioner mounts `dashboard_sso_secret`.

### R2 — REFUTED (calibration): SSO risk severity is mis-rated INFO; it is a live cross-deployment surface
Beyond mere reachability, `sso_secret_for_subject` (`bin/arclink-docker.sh:1676-1698`) keys the
SSO secret by **`user_id`** (subject = `record.user_id`, `:1672-1673`), and reuses one secret
across every deployment owned by that user (`:1680-1695`). The cookie is set with `Path=/;
Domain=<base_domain>` (`arclink_dashboard_auth_proxy.py:735`) and validated with `subject =
sso_subject` (the user_id) at `:686-692`. Therefore one SSO cookie authenticates the holder at
**every sibling agent dashboard on the same domain for that user** — an intentional fleet-wide
single-sign-on, but a genuine cross-deployment auth blast radius. The record neither documents the
per-user shared secret nor the cross-deployment scope; rating this INFO "dead code" is a
mis-calibration. Correct severity for a live, shared, domain-scoped SSO cookie is at least MEDIUM
(arguably HIGH given fleet-wide reuse). NOT refuting that SSO is *intended*; refuting that it is
*dead* and *INFO*.

### R3 — PARTIALLY REFUTED (seam #7 argv overstated): producer never passes `--agent-title`
Record seam #7 (line 130) lists the producer argv as including `--agent-title`. Neither in-repo
producer passes it:
- `arclink_enrollment_provisioner.py:1409-1422` (full seed) passes `--provider-spec-json
  --secret-path --bot-name --unix-user --user-name` — no `--agent-title`.
- `arclink_enrollment_provisioner.py:1579-1589` (identity-only refresh) passes `--identity-only
  --bot-name --unix-user --user-name` — no `--agent-title`.
`--agent-title` always defaults to `""` (`arclink_headless_hermes_setup.py:639`). Harmless in
effect, but the "BOTH-ENDS-VERIFIED yes" marker is invalid: the record asserted an argv key the
producer never sends. Stdout-as-JSON consume at `provisioner.py:1432` is correctly cited.

### R4 — NOT REFUTED but citation imprecise: `_safe_json` "calls reject_secret_material"
Record line 18/99 says `_safe_json` (`dashboard.py:777-778`) "calls `reject_secret_material`."
It actually calls `json_dumps_safe` (`arclink_boundary.py:65-73`), which *internally* calls
`reject_secret_material` (`arclink_boundary.py:72`). The secret-reject guarantee on
`queue_arclink_admin_action` metadata holds, but the citation chain skips a hop. Substance
confirmed, wording imprecise. refuted=false.

---

## CLAIMS INDEPENDENTLY RE-CONFIRMED (refuted=false)

- C1 `queue_arclink_admin_action` validation gauntlet: admin non-blank (`:2339`), action in
  `ARCLINK_ADMIN_ACTION_TYPES` (`:2341`), worker_support=="wired" (`:2343`), target kind+id
  (`:2345`), per-action target_kinds allowlist (`:2347-2352`), reason (`:2353`), key (`:2355`),
  metadata via `_safe_json` (`:2357`). Idempotent: same tuple returns existing row (`:2363-2372`),
  conflicting tuple raises (`:2365-2371`), INSERT `status='queued'` (`:2376-2381`), audit
  (`:2396-2405`), audit_id backfill (`:2406-2409`), commit (`:2410`). VERIFIED.
- C2 TOCTOU on idempotency is **closed by a UNIQUE INDEX** the record never cited:
  `idx_arclink_action_intents_idempotency` UNIQUE on `idempotency_key`
  (`arclink_control.py:2269-2270`). A concurrent double-insert raises IntegrityError, not a dup.
  Strengthens the record's idempotency claim.
- C3 Seam #2 both ends: producer INSERT `dashboard.py:2376-2409`; worker consumes
  `FROM arclink_action_intents WHERE status='queued'` (`arclink_action_worker.py:461-462`),
  claims via compare-and-swap `UPDATE ... SET status='running' ... WHERE ... AND status='queued'`
  (`:474-480`) — concurrency-safe claim. `:2251` is `recover_stale_actions` selecting
  `status='running'` (stale recovery, not the consume loop) — record's framing accurate but it is
  the recovery path. Worker dispatch table (`:836-1300`) handles every executable action_type;
  unknown type raises `unsupported action type` (`:1300`). VERIFIED.
- C4 Auth: `_valid_token` does `hmac.compare_digest` signature check (`:642`), audience (`:644`),
  subject (`:646`), scope (`:648`), iat<=revoked_before reject (`:652`), exp>now (`:654`). CSRF
  `_csrf_origin_ok` fail-closed: returns False when neither Origin nor Referer present for mutating
  methods (`:1104-1114`); `MUTATING_METHODS={DELETE,PATCH,POST,PUT}` (`:44`);
  `_origin_matches_host` uses `hmac.compare_digest` on normalized host (`:524-531`). Access load
  fail-closed: malformed -> `{}` -> no username/password -> 401 (`load_access:173-193`,
  `_authorized:699-700`). VERIFIED.
- C5 `_token_secret` fallback to `sha256("...fallback-v1"\0realm\0user\0password)` when
  `session_secret` blank (`:86-98`). Record's MEDIUM risk is real. Producer always sets
  `session_secret` (`install-deployment-hermes-home.sh:91`, `existing.get(...) or token_urlsafe(32)`).
  VERIFIED (record correct).
- C6 Cookie attrs `HttpOnly; Path=<mount or />; SameSite=Lax; Secure` (`:727`,
  `_cookie_path:768-769`). VERIFIED.
- C7 Read models are SELECT-only: `read_arclink_admin_dashboard` body (`:1825-2320`) contains no
  INSERT/UPDATE/DELETE/commit (verified by scan). `read_arclink_user_dashboard` likewise. Chutes
  enrichment via `.to_public()` emits only state names (`:1743-1763`). VERIFIED.
- C8 `request_arclink_backup_write_check` never runs git — ownership check then unconditional
  `record_arclink_backup_write_check_failed_closed` (`:1361-1384`). Drift #2 VERIFIED.
- C9 `request_arclink_backup_deploy_key`: BEGIN IMMEDIATE if not in txn (`:1207-1209`), ownership
  (`:1217-1218`), requires recorded private repo (`:1220-1222`), stages key only if absent
  (`:1226-1230`), UPDATE metadata + audit + commit (`:1243-1267`). Returns no private key.
  VERIFIED. MEDIUM key-persistence/no-rotation risk holds.
- C10 `build_scale_operations_snapshot` reads `os.environ` directly at `:705-706,715,748` despite
  taking `conn` — env-leak risk VERIFIED. Note: `admin_action_execution_readiness()` and
  `control_node_provisioning_readiness(conn)` at `:701-702` are also called without env injection,
  so the env coupling is slightly broader than the record framed.
- C11 Nextcloud: `OC_PASS` via `extra_env` (`:206,218`), `--password-from-env`, newline-reject
  (`:160-166`), `safe_slug` username (`:153-157`), `ENABLE_NEXTCLOUD` gate returns
  `{enabled:False}` (`:181-182`). VERIFIED.
- C12 Skill enablement: atomic write fsync+os.replace (`:151-165`), byte-preserving line surgery
  (`remove_skills_from_disabled:118-148`), unsafe-id reject `/ \ ..` (`:210-212`), fail-closed
  YAML-less parse (`parse_skills_config:92-115`), receipt (`:227-235`). VERIFIED.
- C13 Login throttle is process-local module dict `_LOGIN_FAILURES` (`:66`, `:392-413`). LOW risk
  VERIFIED.
- C14 `_action_worker_liveness_probe` trusts operator-written status JSON `finished_at`/
  `interval_seconds`/`status` (`:457-491`). INFO trust-internal risk VERIFIED.

---

## NEW GAPS (neither record nor prior docs flag)

### G1 (MEDIUM) — Two sibling modules mutate the SAME config.yaml with INCOMPATIBLE strategies
`arclink_headless_hermes_setup.py` mutates `config.yaml` via `hermes_cli.config.load_config` +
`save_config` — a **full YAML load-and-re-dump** (`:565,90,266`; imports at `:41,79,217-220`).
`arclink_skill_enablement.py` deliberately mutates the SAME `config.yaml` via **byte-preserving
line surgery, no YAML re-dump** (`:118-148`), explicitly to avoid reformatting. These two lanes
both run on the same file (headless at install/refresh; skill-enablement every 4h via
`arclink-user-agent-refresh.timer`). The record's Codex open-item #5 and self-check #5 worry
*only* about the line-surgery being fragile against flow-style YAML — it never notices that the
headless module's full re-dump on the same file would normalize/reformat exactly what the
line-surgery module assumes is byte-stable, and that the two have no shared lock. If they ever
interleave (path-watcher activation + scheduled headless refresh), there is no file lock guarding
config.yaml between these two writers. This sibling-vs-sibling inconsistency is inside this CANON-19
piece and is unflagged anywhere.

### G2 (LOW) — SSO secret is generated, not required: silent auth-secret materialization
`sso_secret_for_subject` (`bin/arclink-docker.sh:1696-1698`) **generates a fresh
`secrets.token_urlsafe(32)`** when no existing secret is found for the user, rather than failing.
Combined with R1, this means the Docker path silently stands up a live SSO auth secret with no
operator opt-in beyond running the provisioner. There is no env gate equivalent to
`ENABLE_NEXTCLOUD` for SSO; it is on by default in domain-ingress Docker mode. Not flagged.

### G3 (LOW) — `_deployment_urls` https-only filter does not constrain env-derived host
Confirms the record's self-check #5 but sharpens it: the stored-URL branch filters
`startswith("https://")`, yet the tailscale/domain branches build `f"https://{host}/u/{prefix}"`
from `os.environ.get("ARCLINK_TAILSCALE_DNS_NAME")` (`dashboard.py:797-819`) with no hostname
validation. A malformed env host (e.g. containing `/` or `@`) flows verbatim into dashboard
`access.urls` and downstream into SOUL/identity prefill. Operator-trust boundary, but unvalidated.

---

## SEAM MISMATCHES

- SEAM #6 (auth proxy ← access-file producer): record marks SSO keys "NO producer in this repo."
  MISMATCH — producer exists at `bin/install-deployment-hermes-home.sh:169-170` fed by
  `arclink_provisioning.py:1372-1377` + `bin/arclink-docker.sh:1895-1902`. The both-ends marker for
  SSO is wrong.
- SEAM #7 (headless ← provisioner): record lists `--agent-title` in producer argv; neither
  producer site sends it (`provisioner.py:1409-1422`, `:1579-1589`). Marker "yes" overstated.
- SEAM #2/#10: no mismatch found; #2 confirmed both ends, #10 correctly left producer-only.

---

## RISK RE-CALIBRATION
- RAISE: SSO cookie path INFO → **MEDIUM/HIGH** (live, per-user shared secret, cross-deployment,
  Domain-scoped). The record's single largest error.
- HOLD: `_token_secret` fallback (MEDIUM), backup deploy-key persistence (MEDIUM),
  scale-snapshot env leak (MEDIUM), stripe_customer_id exposure (LOW), process-local throttle
  (LOW), env-derived URLs (LOW), liveness-file trust (INFO).
- ADD: G1 config.yaml dual-writer inconsistency (MEDIUM).

## TRUSTWORTHINESS
The record is a competent, largely code-accurate map of the read-model/queueing/proxy mechanics
(C1–C14 reconfirmed). However it is **NOT trustworthy on the SSO subsystem**: it declared a live,
security-relevant, cross-deployment auth path "dead code" because the auditor's grep missed a
`bin/` producer it admitted not searching thoroughly. That single miss propagated into a wrong
DRIFT entry, a wrong seam-#6 both-ends marker, a wrong INFO risk rating, and a misleading VERDICT
("SSO cookie subsystem is dormant"). Treat all SSO statements in the record as refuted until the
provisioner chain is re-walked. Everything else stands.
