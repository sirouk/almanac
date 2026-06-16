#!/usr/bin/env bash
# Federation driver: Codex (GPT-5.5 xhigh) independent ratification of each CANON piece.
# Each piece: Codex re-verifies the Claude record against real code (read-only),
# adjudicates every disputed item, hunts missed gaps, and signs off RATIFY/OBJECT/REJECT.
# Output (between markers) captured to research/canon/codex/<id>-<slug>.codex.md
set -uo pipefail
cd /root/arclink || exit 2
mkdir -p research/canon/codex research/canon/codex/logs research/canon/codex/prompts
MAXJOBS="${MAXJOBS:-3}"
TIMEOUT="${TIMEOUT:-1500}"

pieces=(
  "CANON-01:control-plane-schema" "CANON-02:hosted-api-transport"
  "CANON-03:web-product-surface" "CANON-04:onboarding-provider-auth"
  "CANON-05:public-bots" "CANON-06:curator-onboarding"
  "CANON-07:billing-entitlements" "CANON-08:provisioning-enrollment"
  "CANON-09:ingress-dns" "CANON-10:inventory-capacity"
  "CANON-11:executor" "CANON-12:gateway-brokers"
  "CANON-13:pod-migration" "CANON-14:operator-admin-control"
  "CANON-15:operator-upgrade-pipeline" "CANON-16:llm-router-providers"
  "CANON-17:academy-crew-soul" "CANON-18:knowledge-memory-notion-mcp"
  "CANON-19:workspace-dashboard" "CANON-20:sharing-fleet-folder"
  "CANON-21:org-profile" "CANON-22:backup-restore-wrapped"
  "CANON-23:diagnostics-health-evidence" "CANON-24:deploy-install-lane"
  "CANON-25:compose-containers" "CANON-26:systemd-units"
  "CANON-27:config-environment" "CANON-28:ci-smoke-gates"
  "CANON-29:test-corpus" "CANON-30:hermes-plugins"
  "CANON-31:ops-scripts-skills-templates" "CANON-32:docs-corpus-provenance"
)

build_prompt() {
  local id="$1" slug="$2"
  cat <<EOF
You are GPT-5.5 (xhigh) acting as an INDEPENDENT auditor and ratifier in the ArcLink
"Federation" — a two-model (Claude Opus 4.8 + you) ground-truth dissection of the ArcLink
codebase into CANON.md. Working dir: /root/arclink (git branch arclink). You ratify piece
${id} (${slug}).

The Claude half already produced, for ${id}:
  - deep record:        research/canon/sections/${id}-${slug}.md
  - adversarial verify: research/canon/verify/${id}-${slug}.verify.md
The consolidated /root/arclink/CANON.md holds, tagged "${id}":
  - Section 3 = unified risk register (the ${id} HIGH/MEDIUM/LOW risks, each path:line cited)
  - Section 2 = cross-piece seam graph (seams touching ${id})
  - Section 5 = disagreement register: A. refuted Claude-auditor claims (verifier overturned
    the auditor), B. open-for-Codex investigations, C. residual severity disputes.

BINDING METHOD — NON-NEGOTIABLE: Prove, do not guess. Comments, docstrings, identifier
names, READMEs, and prior claims (including the Claude record) are CLAIMS, not evidence —
only an executed code path is evidence. Cite path:line for every load-bearing statement and
OPEN the file to read the actual lines (rg / sed -n / git are available read-only). Where
code disagrees with a comment, a name, or a prior claim, the CODE WINS and you say so. No
human-language intent satisfies a claim.

TASK (read-only — read any file, run read-only shell; do NOT modify anything):
1. Read the Claude record + verify file for ${id}, and the ${id}-tagged items in CANON.md
   Sections 2/3/5. (Use: sed -n, rg "${id}" CANON.md.)
2. Independently re-verify each load-bearing claim, contract, seam, and RISK against the real
   code. Do NOT trust Claude's citations — re-open each path:line yourself.
3. Adjudicate EVERY ${id}-tagged disputed item (§A/§B/§C) and every ${id} HIGH/MEDIUM risk:
   return CONFIRM / REFUTE / REFINE, each with YOUR own code cite.
4. Hunt for defects BOTH Claude passes missed (unhappy paths, fail-open, TOCTOU, replay,
   nonce/lock races, silent no-ops, secret handling).
5. Sign off at the piece level: RATIFY (you agree) / OBJECT (agree with specific refinements)
   / REJECT (record is materially wrong).

OUTPUT: print ONLY the block between the markers (no preamble). Be concise but code-cited.
<<<CODEX-VERDICT-START ${id}>>>
## ${id} — Codex (GPT-5.5 xhigh) ratification
SIGN-OFF: <RATIFY | OBJECT(n) | REJECT>
ONE-LINE VERDICT: <...>
### Adjudication (each: CONFIRM/REFUTE/REFINE + path:line)
- ...
### New findings both Claude passes missed (severity + path:line)
- ...
### Claude citations re-confirmed or corrected
- ...
### Residual disagreement with the Claude half (for final reconciliation)
- ...
<<<CODEX-VERDICT-END ${id}>>>
EOF
}

run_piece() {
  local entry="$1"
  local id="${entry%%:*}" slug="${entry#*:}"
  local pf="research/canon/codex/prompts/${id}.prompt.txt"
  local out="research/canon/codex/${id}-${slug}.codex.md"
  local log="research/canon/codex/logs/${id}.log"
  build_prompt "$id" "$slug" > "$pf"
  local start; start="$(date +%s)"
  timeout "$TIMEOUT" codex exec -s read-only -c 'mcp_servers={}' - < "$pf" > "${out}.raw" 2> "$log"
  local rc=$?
  # Extract only the verdict block between markers; fall back to raw if markers absent
  if grep -q "CODEX-VERDICT-START ${id}" "${out}.raw"; then
    sed -n "/<<<CODEX-VERDICT-START ${id}>>>/,/<<<CODEX-VERDICT-END ${id}>>>/p" "${out}.raw" > "$out"
  else
    cp "${out}.raw" "$out"
  fi
  local end; end="$(date +%s)"
  local bytes; bytes="$(wc -c < "$out" 2>/dev/null || echo 0)"
  echo "[$(date +%H:%M:%S)] ${id} rc=${rc} ${bytes}B $((end-start))s"
}

# If args given, run only those pieces (entries id:slug); else run all.
targets=( "$@" )
[ "${#targets[@]}" -eq 0 ] && targets=( "${pieces[@]}" )

echo "=== Codex overlay: ${#targets[@]} pieces, MAXJOBS=${MAXJOBS}, timeout=${TIMEOUT}s ==="
for entry in "${targets[@]}"; do
  while [ "$(jobs -r | wc -l)" -ge "$MAXJOBS" ]; do wait -n; done
  run_piece "$entry" &
done
wait
echo "=== ALL CODEX OVERLAYS COMPLETE ($(date +%H:%M:%S)) ==="
# Summary of sign-offs
echo "--- sign-offs ---"
for entry in "${targets[@]}"; do
  id="${entry%%:*}"; f=$(ls research/canon/codex/${id}-*.codex.md 2>/dev/null | head -1)
  [ -n "$f" ] && printf '%s: %s\n' "$id" "$(grep -m1 'SIGN-OFF:' "$f" | sed 's/SIGN-OFF://')" || printf '%s: <no output>\n' "$id"
done
