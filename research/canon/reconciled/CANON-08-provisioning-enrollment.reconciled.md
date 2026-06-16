# CANON-08 — Provisioning & Enrollment — RECONCILED (both-model truth)

Adjudicator: Claude Opus 4.8 final adjudicator (ArcLink two-model Federation).
Method: every DISPUTED / REFUTE / REFINE / new-finding point re-opened in code at path:line;
code wins over comment/name/prior claim. Codex CONFIRM items where both models already
agreed are ratified one-line. Working dir /root/arclink, branch arclink.

## SIGN-OFF
- Codex (GPT-5.5 xhigh): **OBJECT(3)** — three objections: (1) fleet audit-chain soundness
  overstated, (2) fleet consume has committed pre-guard side effects, (3) operator-source gate is
  a current-writer convention, not a hard capability boundary.
- Final federation sign-off: **BOTH-MODEL-AGREED**. All three Codex objections are confirmed in
  code and adopted into the reconciled truth; the verifier's one over-strong conclusion (TOCTOU
  "no orphan inventory row") is overturned by the same code. No point remains unsettleable from
  code alone.

---

## RESOLUTION TABLE (point | winner | deciding cite)

| # | Disputed point | Winner | Deciding cite (re-opened) |
|---|---|---|---|
| 1 | Fleet consume leaves committed side effects when token consume later fails (orphan inventory/fleet-host) | **codex** | `arclink_inventory.py:262` (`conn.commit()` in `register_inventory_machine`) + `arclink_fleet.py:247` (`conn.commit()` in `register_fleet_host`) BOTH precede the consume guard `arclink_fleet_enrollment.py:689-698` |
| 2 | Verifier's TOCTOU "clean single-winner, no orphan inventory row" | **neither (verifier refuted)** | committed INSERTs at `arclink_inventory.py:262` are NOT rolled back by the loser's `raise` at `arclink_fleet_enrollment.py:698`; only the post-register UPDATEs (`:670`,`:680`) in the loser's open txn roll back |
| 3 | Fleet audit chain "cryptographically sound … P0 on tamper" overstated (unkeyed-SHA256 downgrade) | **both (codex + verifier)** | `arclink_fleet_enrollment.py:469-472` (unkeyed fallback) + `:891-902` (legacy branch re-verifies with `secret=""`) + `:904` (P0 only when `errors`) |
| 4 | operator-raven confirmed-source gate is a capability boundary | **codex (REFINE)** | gate is pure string eq `enrollment:2292-2297`; producer `request_operator_action` persists caller-supplied `request_source` verbatim `arclink_control.py:8302`. Currently only Operator Raven emits it for upgrade/pin kinds (`arclink_operator_raven.py:1311,1562`) — convention, not crypto boundary |
| 5 | UnicodeDecodeError "strands a running row" permanently | **codex+verifier (REFINE)** | escape real (except tuple `enrollment:342` excludes `ValueError`/`UnicodeDecodeError`, decode at `:335`); recovered by `_fail_stale_running_operator_actions(stale_seconds=1800)` run FIRST next `main()` at `enrollment:2323-2329` |
| 6 | Non-Docker pin-upgrade lacks component allowlist (MEDIUM) | **both** | `_pin_upgrade_command_args` gates only non-empty component/target + valid kind flag `enrollment:429-448`; `ALLOWED_PIN_COMPONENTS` only in broker `operator_upgrade_broker.py:267-273` |
| 7 | agent_access state file "owned by agent uid/gid" | **codex+verifier (overstated)** | `os.chown`+`chmod` in `try/except OSError: pass` `arclink_agent_access.py:71-75` → ownership silently degrades on EPERM |
| 8 | host_readiness ingress check is a gate | **codex+verifier (tautology)** | both branches return `ok=True` `arclink_host_readiness.py:158-161` |
| 9 | HMAC broker seam byte-match | **both (CONFIRM)** | client `enrollment:310-330` vs broker `operator_upgrade_broker.py:686-716` — ratified |
| 10 | `validate_no_plaintext_secrets` is final gate before return | **both (CONFIRM)** | `provisioning.py:1398-1421` + runs at `:1781` before `:1701-1782` return — ratified |
| 11 | Hosted-API → consume_fleet_enrollment seam (Bearer+JSON, 401 on fail) | **both (CONFIRM)** | `hosted_api:2035-2050` — ratified |
| 12 | Fleet token dual compare (sig + stored hash) + reject non-pending | **both (CONFIRM)** | `fleet_enrollment.py:92-123` — ratified |
| 13 | host_readiness excludes `secret_*` from `ready` roll-up | **both (CONFIRM)** | `host_readiness.py:183` — ratified |

### One-line ratifications of Codex CONFIRM items not in the original record's headline set
- **SSO seam live (not dead):** provisioning emits `dashboard_sso_secret`, install writes SSO
  fields, proxy loads + emits SSO cookie — `provisioning.py:666-669`, `bin/install-deployment-hermes-home.sh:163-170`,
  `dashboard_auth_proxy.py:180-186,729-735`. Ratified; consistent with record, changes no verdict.
- **`secret_refs.llm_router_api_key` absent in `direct_chutes` mode; migration silently skips when
  absent:** `provisioning.py:657-665`, `pod_migration.py:736-739`. Ratified as benign-by-design.

---

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

### CONFIRMED (net-new federation risks)

1. **[MEDIUM] Fleet enrollment consume is not transaction-clean — committed pre-guard side effects.**
   `consume_fleet_enrollment` calls `register_inventory_machine` (which `conn.commit()`s at
   `arclink_inventory.py:262`, and may call `register_fleet_host` which `conn.commit()`s at
   `arclink_fleet.py:247`) BEFORE the single-use token guard `UPDATE … status='pending'` /
   `rowcount != 1 → raise` (`arclink_fleet_enrollment.py:689-698`). On the losing side of a
   same-token race — or any failure at/after the consume guard — the inventory machine row and
   fleet-host row are already durably committed and are NOT rolled back by the `raise` at `:698`
   (that only discards the loser's still-open post-register UPDATEs at `:670`,`:680`). The dedup
   guards (`fleet_enrollment.py:635-649` hostname/fingerprint check; `arclink_inventory.py:184-193`
   provider+hostname upsert) mean a same-hostname re-run UPDATEs rather than duplicates, but the
   row is still left as an orphaned `pending`/`awaiting_control_probe` machine with a `degraded`
   drained fleet-host when the token consume fails. **This overturns the verifier's TOCTOU "no
   orphan inventory row" conclusion.** Gated behind a hosted-API request that already presented a
   valid pending token, so impact is a stale orphan row, not privilege escalation — MEDIUM.
   `[python/arclink_fleet_enrollment.py:651-698; python/arclink_inventory.py:173-182,262; python/arclink_fleet.py:238-248]`

### REJECTED
- None. All Codex adjudications and its one new finding re-verified true in code.

---

## SEVERITY CHANGES (only where code supports)

| Risk | from | to | Cite |
|---|---|---|---|
| Fleet audit-chain integrity | record VERDICT: "cryptographically sound … queues a P0 on tamper" (implied no-gap) | **MEDIUM** known unkeyed-SHA256 downgrade (DB-write attacker can re-forge a whole inventory chain undetected, no P0) | `arclink_fleet_enrollment.py:469-472,891-902,904` |
| Fleet enrollment consume transactionality | not rated in record (verifier called it TOCTOU-clean) | **MEDIUM** committed pre-guard side effects / orphan rows on failed consume | `arclink_inventory.py:262; arclink_fleet.py:247; arclink_fleet_enrollment.py:689-698` |
| UnicodeDecodeError escape | record: LOW "strands the row in running" | **LOW (text refined)**: "strands until the ≤30-min stale reaper recovers it" — severity unchanged, permanence claim corrected | `arclink_enrollment_provisioner.py:335,342,2323-2329,613-647` |
| operator-raven confirmed-source gate | record framed it as defense-in-depth gate | **characterization refined** (no rating change): current-writer convention / string gate, not a capability boundary | `arclink_control.py:8302; arclink_enrollment_provisioner.py:2292-2297` |

Net new MEDIUMs vs the original record: **two** (audit-chain unkeyed downgrade; consume non-atomicity).
The original record's existing MEDIUM (non-Docker pin allowlist) stands. LOW/INFO items
(plaintext-http GAP-019, broker-URL no-allowlist, `_docker_mode` truthy divergence, readiness
secret-roll-up exclusion, ingress tautology, agent_access chown swallow, spoofable `source_ip`,
fragile operator_agent substring exclusion) all stand as cited.

---

## STANDING DISAGREEMENTS
None. Every material point reconciled to a single code-grounded truth:
- The fleet-consume non-atomicity is settled by `arclink_inventory.py:262` + `arclink_fleet.py:247`
  committing before the guard — Codex wins, verifier's TOCTOU proof overturned.
- The audit-chain downgrade is settled by the legacy unkeyed branch `:891-902` — both models agree.
- The operator-raven gate is settled as a string convention by `arclink_control.py:8302` — Codex's
  REFINE adopted; matches the record's own self-check #3 contingency.

---

## FINAL BOTH-MODEL VERDICT
**Provably YES — the piece does its job, with FOUR genuine weaknesses (two MEDIUM, two carried).**
The intent renderer (`render_arclink_provisioning_intent`) deterministically renders a fully
secret-ref'd compose/env/DNS/traefik intent and fails closed through `validate_no_plaintext_secrets`
before returning (`provisioning.py:1781`). The dispatcher's HMAC seam to the operator-upgrade-broker
is byte-for-byte verified at both ends (signed-string format, headers, body-hash-over-raw-bytes,
nonce alphabet, TTL, operation allowlist), missing url/token fails before any I/O, and the
confirmed-source string gate plus stale-running reaper give real defense-in-depth for host mutation.

Reconciled weaknesses:
1. **[MEDIUM]** Non-Docker pin-upgrade path lacks the `ALLOWED_PIN_COMPONENTS` allowlist the Docker
   broker enforces (producer AND `_pin_upgrade_command_args` both ungated) — `enrollment:429-448`.
2. **[MEDIUM]** Fleet audit chain accepts unkeyed legacy SHA-256 entries, so a DB-write attacker can
   re-forge a whole inventory chain with zero verification errors and no P0 — the "cryptographically
   sound … P0 on tamper" claim must be demoted to "tamper-evident against partial linkage edits,
   downgradeable to unkeyed sha256" — `fleet_enrollment.py:891-902`.
3. **[MEDIUM]** Fleet enrollment consume is not transaction-clean: `register_inventory_machine` /
   `register_fleet_host` commit before the single-use token guard, so a lost same-token race or a
   post-register failure leaves a committed orphan inventory/fleet-host row even when the token
   consume `raise`s — `inventory.py:262`, `fleet.py:247`, `fleet_enrollment.py:689-698`.
4. **[LOW]** A non-UTF-8 broker success body escapes the returncode-2 contract and strands the
   `operator_actions` row in `running` until the ≤30-min stale reaper recovers it (low reachability;
   in-repo broker always emits UTF-8) — `enrollment:335,342,2323-2329`.

The operator-source gate is honored as a current-writer convention (only Operator Raven emits
`operator-raven` for upgrade/pin kinds today), not a cryptographic authorization boundary, because
`request_operator_action` persists the caller-supplied `request_source` verbatim
(`control.py:8302`). Plaintext-http broker transport remains an accepted Docker-internal GAP-019
trust assumption, not a code defect. Sovereign-worker live execution stays operator-/proof-gated
(PG-FLEET/PG-PROVISION).

**Federation sign-off: BOTH-MODEL-AGREED.**
