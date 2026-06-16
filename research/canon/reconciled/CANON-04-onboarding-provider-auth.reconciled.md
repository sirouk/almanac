# CANON-04 — Onboarding & Provider Auth — RECONCILED (both-model truth)

Adjudicator: Claude Opus 4.8 (1M) final reconciler. Method: every disputed point re-opened
in code this session (Read/grep/exec). Code wins over any prior claim, comment, or name.

- **Codex (GPT-5.5 xhigh) sign-off:** OBJECT(4) — "Mostly ratified, but the webhook HIGH is
  mechanistically wrong as written: code commits mid-webhook, then fails/replays; it does not
  roll the paid entitlement back."
- **Federation sign-off:** **BOTH-MODEL-AGREED** — every material point reconciled to one
  code-grounded truth. Codex's central OBJECT (N1 mechanism) is **upheld**: the HIGH stands but
  the mechanism is rewritten. No standing disagreements remain.

---

## RESOLUTION TABLE (disputed / refined points)

| Point | Winner | Deciding cite |
|-------|--------|---------------|
| N1 webhook wedge: does the PAID entitlement get rolled back? | **codex** | `arclink_onboarding.py:337` calls `expire_stale_...` with default `commit=True` (`:271`,`:324-325`) → `conn.commit()` flushes the paid write (`arclink_entitlements.py:725-740`) + gate (`:741`) BEFORE the terminal raise (`arclink_onboarding.py:339-340`); the outer `rollback` (`arclink_entitlements.py:800-801`) finds them already durable. Paid is NOT undone. |
| N1 wedge exists at all (replay-forever failure) | **both** | Terminal/missing session raises (`arclink_onboarding.py:338-340`); webhook marks failed-replayable and re-raises (`arclink_entitlements.py:802-809`); session never un-terminalizes → permanent replay loop. |
| Severity of N1 | **both** | HIGH retained — a paid customer's checkout completing after 24h TTL expiry wedges the webhook permanently. |
| R1 "secret-hostile / cannot hold provider keys" claim | **both** (REFUTE the absolute) | Executed `_PLAINTEXT_SECRET_RE` (`arclink_onboarding.py:116-126`): catches Stripe/GitHub/Slack/Notion/telegram; ESCAPES Anthropic `sk-ant-`, OpenAI `sk-`/`sk-proj-`, Chutes `cpk_`, AWS `AKIA`. Hints stored at `:533/:544/:493`. |
| R2 `arclink_api_auth.py:1093` is the `_update_session` bypass | **codex** (Claude record REFUTED; Claude verify already self-corrected) | `:1094` binds `_json(...)` → `_json` (`:221-222`) → `json_dumps_safe` → `reject_secret_material` (`arclink_boundary.py:65-73`). Line IS scanned. |
| `_update_session` (`:344-383`) has no centralized secret scan | **both** (true but no reachable exploit) | `:344-383` writes allowed fields with no scan; grep shows no external caller; every internal caller passes scanned/scalar data. Risk = regex coverage, not the path. |
| Dead statuses `payment_pending`/`paid`/`completed` never set by NEW machine | **both** | Status set defs (`:23-43`); forward writes are only `provisioning_ready` (`:815`) and `first_contacted` (`:890`); schema CHECK pins dead values (`arclink_control.py:1313`). |
| Chutes is API-key not OAuth | **both** | `arclink_onboarding_provider_auth.py:153-165` (`auth_flow="api-key"`); OAuth only Codex `:300` / Anthropic `:385`. |
| `normalize_anthropic_credential` always raises | **both** | `arclink_onboarding_provider_auth.py:466-470`. |
| Plaintext shared password emitted to chat pre-ack | **both** | `arclink_onboarding_completion.py:411-432,440-456`. |
| OLD path live outbound HTTP to OpenAI/Anthropic | **both** | `arclink_onboarding_provider_auth.py:300,326,408,507`. |
| N2 `sync_...` False is a silent no-op (caller ignores return) | **both** | `arclink_onboarding.py:808-810` returns False; `arclink_entitlements.py:744-750` does not capture it. |
| N3 first-contact has no terminal guard (resurrects terminal session) | **both** | `arclink_onboarding.py:880-902` calls `_update_session(status="first_contacted")` directly, no `_active_session_or_error`; `first_contacted` is active (`:31`) and in partial unique index (`arclink_control.py:2237-2245`). |
| 7 cross-piece seams shape-correct | **both** | Seams 1/3/5/6 fully both-ends; 2/4 correct on shape, unsafe on unhappy path (N1/N3). |

## CODEX NEW FINDINGS — CONFIRMED vs REJECTED

**CONFIRMED (net-new federation risks):**
1. **MEDIUM — late cancel regresses a paid/provisioning session.** Cancel API short-circuit
   (`arclink_api_auth.py:5039`) excludes `provisioning_ready` and `first_contacted`; both are
   ACTIVE not TERMINAL (`arclink_onboarding.py:30-42`), so `cancel_arclink_onboarding_session`
   (`:748-760`) falls through and rewrites a paid session to `abandoned`. Gated by the
   `browser_cancel_proof_hash` (`arclink_api_auth.py:5046-5048`) — reachable by the legitimate
   session holder, hence MEDIUM, not HIGH.
2. **LOW — public `question_key` stored unscanned/uncapped as `current_step` and reflected.**
   `arclink_onboarding.py:527` sets `current_step=str(question_key).strip()` with no length cap
   and no `_reject_secret_material` (the scan loop `:528-544` covers only hint fields); request
   body → `arclink_hosted_api.py:746` → `arclink_api_auth.py:1132`; reflected by
   `_public_onboarding_session` (`arclink_api_auth.py:319-323`, all fields except `metadata_json`).

**REJECTED:** none. Both Codex new findings hold in code.

## SEVERITY CHANGES (code-supported)

| Risk | From | To | Cite |
|------|------|----|------|
| N1 webhook wedge — mechanism rewritten (premature commit + failed-replay loop, NOT entitlement rollback) | HIGH (rollback) | HIGH (premature-commit replay loop) | `arclink_onboarding.py:337`,`:324-325`; `arclink_entitlements.py:725-741`,`:800-809` |
| Record "secret-hostile, cannot hold keys" strength → real partial-protection gap | strength claim | **HIGH gap** (Anthropic/OpenAI/Chutes/AWS escape) | `arclink_onboarding.py:116-126` (exec-verified) |
| Record RISK#2 "secret-rejection entry-point-only / `_update_session` bypass via `:1093`" | MEDIUM | **LOW/INFO** (`:1093` is scanned; no reachable bypass) | `arclink_api_auth.py:1092-1095`,`:221-222`; `arclink_boundary.py:65-73` |

Risks re-confirmed unchanged at cited lines: plaintext completion password (MEDIUM,
`arclink_onboarding_completion.py:411-432`); OLD-path live HTTP (MEDIUM,
`arclink_onboarding_provider_auth.py:300,326,408`); expire-on-read-path (LOW,
`arclink_onboarding.py:337`); IN-placeholder cosmetic (LOW, `:237-249`); Chutes-OAuth drift
(INFO, `arclink_onboarding_provider_auth.py:153-165`). N2 (MEDIUM), N3 (MEDIUM), N4 orphan
deployment on Stripe failure (INFO, `arclink_onboarding.py:656` before `:664`, no try/except)
retained.

## STANDING DISAGREEMENTS

None. Codex's lone OBJECT (the N1 rollback wording) is resolved in Codex's favor by code:
the paid entitlement is committed by the premature `expire_stale` commit, not rolled back.
The HIGH severity survives unchanged; only the mechanism description is corrected. Every other
point was already CONFIRM/agreed across both Claude passes and Codex.

## FINAL BOTH-MODEL VERDICT

CANON-04 is an honest two-system piece (NEW public-bot SQL state machine + OLD curator
provider-auth flow). The NEW machine's seams to CANON-01/07/08 are byte-for-byte correct on the
happy path. The piece carries one real **HIGH**: the Stripe entitlement webhook is non-atomic —
`sync_arclink_onboarding_after_entitlement` triggers a premature `conn.commit()` (via
`expire_stale_...(commit=True)`), so a terminal/expired session at `checkout.session.completed`
time durably commits the paid entitlement + gate but then raises, marking the webhook
failed-replayable forever (the paid write is NOT rolled back — Codex's correction stands). A real
**HIGH gap** in the "secret-hostile" claim: the value regex lets Anthropic/OpenAI/Chutes(primary
provider)/AWS keys through into free-text hints. Plus net-new MEDIUM (late-cancel regression) and
LOW (`current_step` reflection) from Codex, and MEDIUM N2/N3 fail-modes. The record's
`:1093` "bypass" is refuted (it is scanned). Dead statuses, Chutes-API-key drift, and the OLD
provider-auth trace all re-confirm. **BOTH-MODEL-AGREED.**
