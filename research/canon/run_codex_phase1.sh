#!/usr/bin/env bash
# Phase 1 (live security holes) IMPLEMENTATION driver: Codex (GPT-5.5 xhigh,
# workspace-write) implements ONE converged decision-item per invocation against its
# .decided.md FINAL PLAN, adds local regression tests, runs them. Claude reviews the
# diff + re-runs tests + commits before the next item (serial — items share files).
# Output (between markers) -> research/canon/phase1/<item>.fix.md
set -uo pipefail
cd /root/arclink || exit 2
mkdir -p research/canon/phase1 research/canon/phase1/logs research/canon/phase1/prompts
TIMEOUT="${TIMEOUT:-2400}"

# item -> "pieces|decisions|slugs|goal|forknote"
declare -A ITEMS=(
  [W1]="CANON-02|D1|hosted-api-transport|Session pepper must FAIL CLOSED: an unset pepper must NOT silently fall back to a dev constant in production parity; opt IN to the dev constant only for an explicit local/test domain.|"
  [W2]="CANON-08|D3|provisioning-enrollment|Fleet callback source_ip must be RESOLVED server-side via the shared _remote_ip_from_headers (trusted-proxy aware), never accepted from a client-asserted field.|F1=A: when ARCLINK_TRUSTED_PROXY_CIDRS is unset, trust no proxy / ignore XFF (fail closed) — _remote_ip_from_headers must honor that."
  [W3]="CANON-07|D1|billing-entitlements|The FIRST entitlement binding must be LOCAL-SOURCE-OWNED (derived from ArcLink's own verified checkout/session state), never asserted from Stripe-supplied metadata; real imports go through an operator-only, audited recovery path.|"
  [W4]="CANON-16|D1|llm-router-providers|The operator unlimited-budget lane must be authorized SERVER-SIDE from operator settings, never from client/request metadata; a spoofed unlimited claim demotes to the capped lane and leaves redacted evidence.|"
  [W5]="CANON-18|D1|knowledge-memory-notion-mcp|Gate Notion signed-event processing on notion_webhook_verified_at — reject (HTTP 412) until the webhook is operator-confirmed (LEG B). Closes the currently-OPEN forged-reindex hole.|"
  [W6]="CANON-02,CANON-03|D2,D1|hosted-api-transport,web-product-surface|Split the proxy-trust CIDR set from the admin-allow CIDR set (distinct vars/roles); resolve client IP only from trusted proxies. Land both pieces together (shared _remote_ip_from_headers).|F1=A: unset ARCLINK_TRUSTED_PROXY_CIDRS => fail closed (trust no proxy, ignore all XFF, use direct socket IP); canonical lanes auto-render the bridge range."
  [W7]="CANON-08|D1|provisioning-enrollment|Replace the request_source STRING convention on operator_actions with a server-minted HMAC AUTHORIZATION ENVELOPE (signed by an operator-held key), verified before any privileged action; unsigned/forged => fail closed.|"
)

item="${1:-}"
[ -z "$item" ] && { echo "usage: $0 <W1..W7>"; exit 2; }
spec="${ITEMS[$item]:-}"
[ -z "$spec" ] && { echo "unknown item: $item"; exit 2; }
IFS='|' read -r pieces decisions slugs goal forknote <<<"$spec"

# Build decided-file path list
decided_paths=""
IFS=',' read -ra P <<<"$pieces"; IFS=',' read -ra S <<<"$slugs"
for i in "${!P[@]}"; do decided_paths="${decided_paths} research/canon/decisions/${P[$i]}-${S[$i]}.decided.md"; done

pf="research/canon/phase1/prompts/${item}.prompt.txt"
out="research/canon/phase1/${item}.fix.md"
log="research/canon/phase1/logs/${item}.log"

cat > "$pf" <<EOF
You are GPT-5.5 (xhigh) in the ArcLink two-model "Federation", IMPLEMENTATION mode
(Phase 1 — live security holes). Working dir: /root/arclink (workspace-write). You
implement item ${item} = ${pieces} decision(s) ${decisions}.

GOAL: ${goal}

THE CONVERGED PLAN (already symphony-anchored + operator-fork-resolved) is binding —
read the relevant "## DECISION ${decisions}" section(s), especially **FINAL PLAN**, in:
${decided_paths}
Operator fork resolution in force (2026-06-17): ${forknote:-none directly applicable; honor the global posture: fail-closed, preserve-state, operator-owned}.

NORTH STAR (symphony) — read the relevant sections of
docs/arclink/sovereign-control-node-symphony.md: every step has a local source owner,
a local regression proof, a named live-proof gate where external systems are required,
and FAILS CLOSED; preserve state by default; same truth across surfaces; operators own
policy. The code is reality, the plan is intent; prove with path:line, code wins over
comment.

DO, in order:
1. Implement the FINAL PLAN exactly. Fail closed. Single source owner. Preserve state.
   Keep the change tight and on-target (do not refactor unrelated code).
2. Add LOCAL REGRESSION TESTS that prove the fix (and prove the OLD hole is closed) in
   the appropriate tests/test_*.py, and WIRE them into that file's __main__ runner
   (the documentation_truths test enforces this).
3. Run the affected tests yourself: TERMINAL_DISABLE_TMUX=1 ARCLINK_FLEET_WORKER_CONFIG=/tmp/none python3 tests/test_<X>.py
   — iterate until green. Also run any sibling suite your change could affect.
4. DO NOT edit CANON.md, DISSECT.md, DECISIONS.md, POST_CAMPAIGN_TEST_STATUS.md, or
   anything under research/canon/ EXCEPT your own report file below. DO NOT git commit
   (the .git dir is read-only here; Claude reviews your diff, re-runs tests, and commits).
5. Write your report to ${out} (between the markers): files+functions changed, how each
   maps to the FINAL PLAN, the OLD-hole-closed proof, tests added + their pass output,
   and any residual / NEEDS-DECISION.

Output ONLY between the markers (no preamble):
<<<CODEX-PHASE1-START ${item}>>>
## ${item} (${pieces} ${decisions}) — Codex implementation report
### Changed
### FINAL-PLAN mapping
### Old hole closed (proof)
### Tests added + results
### Residual / NEEDS-DECISION
<<<CODEX-PHASE1-END ${item}>>>
EOF

start="$(date +%s)"
timeout "$TIMEOUT" codex exec -s workspace-write -c 'mcp_servers={}' - < "$pf" > "${out}.raw" 2> "$log"
rc=$?
if grep -q "CODEX-PHASE1-START ${item}" "${out}.raw"; then
  sed -n "/<<<CODEX-PHASE1-START ${item}>>>/,/<<<CODEX-PHASE1-END ${item}>>>/p" "${out}.raw" > "$out"
else cp "${out}.raw" "$out"; fi
end="$(date +%s)"
echo "[$(date +%H:%M:%S)] ${item} rc=${rc} $((end-start))s $(wc -c < "$out" 2>/dev/null)B"
echo "changed files:"; git -C /root/arclink status -s | grep -vE 'research/canon/' | head -20
