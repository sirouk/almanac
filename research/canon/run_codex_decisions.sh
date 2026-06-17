#!/usr/bin/env bash
# Federation DECISION mode: Codex (GPT-5.5 xhigh, read-only) recommends a resolution
# for each deferred NEEDS-DECISION item, anchored to the symphony design vision.
# Output (between markers) -> research/canon/decisions/<id>-<slug>.codex.md
set -uo pipefail
cd /root/arclink || exit 2
mkdir -p research/canon/decisions research/canon/decisions/logs research/canon/decisions/prompts
MAXJOBS="${MAXJOBS:-3}"     # read-only — safe to parallelize, no file-write conflicts
TIMEOUT="${TIMEOUT:-1500}"

declare -A SLUG=(
  [CANON-01]=control-plane-schema [CANON-02]=hosted-api-transport
  [CANON-03]=web-product-surface [CANON-04]=onboarding-provider-auth
  [CANON-05]=public-bots [CANON-06]=curator-onboarding
  [CANON-07]=billing-entitlements [CANON-08]=provisioning-enrollment
  [CANON-09]=ingress-dns [CANON-10]=inventory-capacity
  [CANON-11]=executor [CANON-12]=gateway-brokers
  [CANON-13]=pod-migration [CANON-14]=operator-admin-control
  [CANON-15]=operator-upgrade-pipeline [CANON-16]=llm-router-providers
  [CANON-17]=academy-crew-soul [CANON-18]=knowledge-memory-notion-mcp
  [CANON-19]=workspace-dashboard [CANON-20]=sharing-fleet-folder
  [CANON-21]=org-profile [CANON-22]=backup-restore-wrapped
  [CANON-23]=diagnostics-health-evidence [CANON-24]=deploy-install-lane
  [CANON-25]=compose-containers [CANON-26]=systemd-units
  [CANON-27]=config-environment [CANON-28]=ci-smoke-gates
  [CANON-29]=test-corpus [CANON-30]=hermes-plugins
  [CANON-31]=ops-scripts-skills-templates [CANON-32]=docs-corpus-provenance
)

build_prompt() {
  local id="$1" slug="$2"
  local items
  items="$(awk -v id="## ${id} " 'index($0,id)==1{p=1;print;next} /^## CANON-/{p=0} p' research/canon/NEEDS_DECISION.md)"
  cat <<EOF
You are GPT-5.5 (xhigh) in the ArcLink two-model "Federation", now in DECISION mode.
The repair campaign fixed genuine defects but DEFERRED the operator decisions below for
piece ${id} (${slug}) — schema/contract/threat-model calls that are the operator's to make.
For EACH, recommend the resolution that best fits the canonical design vision in
docs/arclink/sovereign-control-node-symphony.md. Working dir: /root/arclink (read-only).

NORTH STAR (symphony) — anchor every recommendation to it:
- Operators own hosts/secrets/fleet/policy/upgrades/backups/live-proof/rollout; Captains own
  their Pods + Crew, NOT the host.
- "Boringly reliable underneath, mythic on top." Every step must have a local source owner, a
  local regression / dry-run proof where possible, a NAMED live-proof gate where external
  systems are required, and must FAIL CLOSED.
- Surfaces stay in lock-step with the installed release; every surface shows the SAME system
  truth; state is PRESERVED by default and actions leave REDACTED evidence.
READ the relevant symphony sections for this piece (e.g. "Secrets, Keys, And Rotation";
"Configuration, Schema, And Migration"; "Inference And Router Policy"; "Pods, Isolation, And
SOUL"; "Academy Trainer And Subject-Matter Formation"; "Billing, Entitlements, And Refuel";
"Fleet, Provisioning, Ingress, And Recovery"; "API, Webhook, And Extension Contracts";
"Identity, Access, And Session Governance"; "Supply Chain, Build, And Release Integrity";
"Notifications, Incidents, And Evidence"; "Abuse, Safety, And Platform Boundaries").

THE DEFERRED DECISIONS FOR ${id}:
${items}

CONTEXT (code-cited): research/canon/reconciled/${id}-${slug}.reconciled.md and
research/canon/sections/${id}-${slug}.md cite the exact code; re-open the code (rg/sed -n) to
ground each recommendation — prove, don't guess; the symphony is the design intent, the code is
the current reality, and your plan must move the code toward the symphony while failing closed.

For EACH deferred decision, output this block:
  ### DECISION <n>: <one-line restatement>
  - RECOMMENDATION: <the concrete plan — exactly what to do, code-level where it helps>
  - SYMPHONY ANCHOR: <section name + a quoted line/principle it satisfies>
  - RATIONALE: <why this fits the vision: source-owner / fail-closed / state-preserving /
    same-truth / operator-owns-policy>
  - TRADEOFFS & ALTERNATIVES: <what you weighed and rejected, and any residual risk>
  - EFFORT / BLAST-RADIUS: <low|med|high + which surfaces it touches>

Output ONLY between the markers (no preamble):
<<<CODEX-DECISIONS-START ${id}>>>
## ${id} — Codex (GPT-5.5 xhigh) decision recommendations (symphony-anchored)
...
<<<CODEX-DECISIONS-END ${id}>>>
EOF
}

run_piece() {
  local id="$1" slug="${SLUG[$1]}"
  local pf="research/canon/decisions/prompts/${id}.prompt.txt"
  local out="research/canon/decisions/${id}-${slug}.codex.md"
  local log="research/canon/decisions/logs/${id}.log"
  build_prompt "$id" "$slug" > "$pf"
  local start; start="$(date +%s)"
  timeout "$TIMEOUT" codex exec -s read-only -c 'mcp_servers={}' - < "$pf" > "${out}.raw" 2> "$log"
  local rc=$?
  if grep -q "CODEX-DECISIONS-START ${id}" "${out}.raw"; then
    sed -n "/<<<CODEX-DECISIONS-START ${id}>>>/,/<<<CODEX-DECISIONS-END ${id}>>>/p" "${out}.raw" > "$out"
  else cp "${out}.raw" "$out"; fi
  local end; end="$(date +%s)"
  echo "[$(date +%H:%M:%S)] ${id} rc=${rc} $((end-start))s $(wc -c < "$out" 2>/dev/null)B"
}

targets=( "$@" )
[ "${#targets[@]}" -eq 0 ] && targets=( $(printf '%s\n' "${!SLUG[@]}" | sort) )

echo "=== Codex DECISION pass: ${#targets[@]} pieces, MAXJOBS=${MAXJOBS}, branch=$(git branch --show-current) ==="
for id in "${targets[@]}"; do
  while [ "$(jobs -r | wc -l)" -ge "$MAXJOBS" ]; do wait -n; done
  run_piece "$id" &
done
wait
echo "=== CODEX DECISION PASS COMPLETE ($(date +%H:%M:%S)) ==="
