#!/usr/bin/env bash
# Codex (GPT-5.5 xhigh) repair campaign driver. Per piece: read the reconciled
# Federation findings, fix genuine defects (all severities), skip+document
# risk-accepted/standing items, add/adjust tests, run the piece's tests, and make
# ONE tests-gated commit per piece. Workspace-write sandbox. SERIAL by default.
set -uo pipefail
cd /root/arclink || exit 2
mkdir -p research/canon/fixes research/canon/fixes/logs research/canon/fixes/prompts
MAXJOBS="${MAXJOBS:-1}"          # serial: pieces share files via seams
TIMEOUT="${TIMEOUT:-2700}"       # 45 min per piece

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
  cat <<EOF
You are GPT-5.5 (xhigh) implementing the fixes that the ArcLink two-model "Federation"
(Claude Opus 4.8 + you) proved against real code. Working dir: /root/arclink, git branch
arclink-canon-fixes. You OWN repairs for piece ${id} (${slug}).

THE SPEC (read these — they are the adjudicated, code-cited truth; do NOT re-litigate them):
  - Reconciled findings (authoritative): research/canon/reconciled/${id}-${slug}.reconciled.md
  - Deep record (contracts/risks):       research/canon/sections/${id}-${slug}.md
  - Adversarial verdict:                  research/canon/verify/${id}-${slug}.verify.md
  - Your earlier ratification:            research/canon/codex/${id}-${slug}.codex.md
Also read the ${id} rows in /root/arclink/CANON.md Section 3 (risk register, incl. the
"Federation-added (Codex-found, code-confirmed)" subsection). The canon files under
research/canon/ AND the root CANON.md / DISSECT.md are the immutable SPEC — read them, but do
NOT modify any of them (the human reviewer maintains CANON.md, incl. its repair ledger).

BINDING METHOD: prove, do not guess. Before changing code, re-open the cited path:line and
confirm the defect is real in the CURRENT tree. Fix the CAUSE, not the symptom.

JUDGMENT POLICY — read carefully, this is the crux:
- FIX every genuine defect across ALL severities (HIGH, MEDIUM, LOW; and INFO when it is a
  clear, safe quick win): correctness bugs, crashes/unhandled exceptions, security holes,
  secret/credential leaks, data loss, contract/seam mismatches, resource/FD leaks, fail-OPEN
  where fail-CLOSED is intended, TOCTOU/replay/lock races, silent no-ops that hide failure.
- DO NOT "fix" deliberate, risk-accepted, or out-of-scope designs. Specifically SKIP (and
  document why) anything that is: a GAP-019 risk-accepted trusted-host/root-equivalence
  property; a broker binding 0.0.0.0 that is contained by compose internal:true; a surface the
  canon labels "prototype, not production"; GAP-031 "no live Chutes relay"; or a STANDING
  DISAGREEMENT that the canon says needs live-container / external-pinned-binary / live-API /
  threat-model resolution (you cannot settle those from code).
- If you are NOT SURE whether a behavior is an intentional design choice, a public-contract
  change with wide blast radius, or a risk-accepted property: DO NOT change it. Mark it
  NEEDS-DECISION with your reasoning and move on. A wrong "fix" is worse than a deferred one.

QUALITY BAR:
- Minimal, surgical diffs that match the surrounding code style. No drive-by refactors, no
  reformatting, no renames beyond what the fix requires. Preserve public function signatures
  and DB/wire contracts unless the fix IS that contract change (then note the blast radius).
- Stay within ${id}'s own files. If a fix genuinely requires editing a file owned by another
  piece (e.g. a shared helper in arclink_control.py), make the MINIMAL change and FLAG it as a
  cross-piece edit in your report (so the reviewer can check for conflicts).
- For any behavior change, add or adjust a regression test under tests/ (each tests/test_*.py
  is runnable as \`python3 tests/test_<name>.py\`; no live secrets — keep it hermetic/fake).

VERIFY — DO NOT COMMIT (a human reviewer commits after reviewing your diff):
1. Run the piece's relevant test file(s): discover via \`ls tests/test_*<module>*.py\` for your
   modules, run each with \`python3 tests/<file>\`, plus any test you added. Capture pass/fail.
2. If a fix breaks a test that passed before AND you cannot reconcile it correctly, REVERT
   just that one fix (\`git checkout -- <file>\`, or re-edit) and mark it NEEDS-REVIEW — never
   leave a known regression in the tree.
3. DO NOT run git add / git commit / git checkout of OTHER pieces' files / git history ops.
   Leave your code+test edits in the working tree for review. Do NOT edit anything under
   research/canon/ (that is the spec) or .git. Report the exact files you changed.

OUTPUT: print ONLY between the markers (no preamble):
<<<CODEX-FIX-START ${id}>>>
## ${id} — Codex (GPT-5.5 xhigh) repair report
FILES-CHANGED: <comma-separated paths you edited/created, or NONE>
TESTS: <e.g. 4 files run, all pass | 3 pass / 1 NEEDS-REVIEW>
### Fixed (severity — what — path:line)
- ...
### Skipped (risk-accepted / standing / out-of-scope — why)
- ...
### NEEDS-DECISION (ambiguous; left for human)
- ...
### Cross-piece edits made (if any) + tests added
- ...
<<<CODEX-FIX-END ${id}>>>
EOF
}

run_piece() {
  local id="$1" slug="${SLUG[$1]}"
  local pf="research/canon/fixes/prompts/${id}.prompt.txt"
  local out="research/canon/fixes/${id}-${slug}.fix.md"
  local log="research/canon/fixes/logs/${id}.log"
  build_prompt "$id" "$slug" > "$pf"
  local start; start="$(date +%s)"
  timeout "$TIMEOUT" codex exec -s workspace-write -c 'mcp_servers={}' - < "$pf" > "${out}.raw" 2> "$log"
  local rc=$?
  if grep -q "CODEX-FIX-START ${id}" "${out}.raw"; then
    sed -n "/<<<CODEX-FIX-START ${id}>>>/,/<<<CODEX-FIX-END ${id}>>>/p" "${out}.raw" > "$out"
  else cp "${out}.raw" "$out"; fi
  local end; end="$(date +%s)"
  local files; files="$(grep -m1 'FILES-CHANGED:' "$out" | sed 's/.*FILES-CHANGED://' | xargs)"
  echo "[$(date +%H:%M:%S)] ${id} rc=${rc} $((end-start))s files=[${files:-?}]"
}

targets=( "$@" )
[ "${#targets[@]}" -eq 0 ] && targets=( $(printf '%s\n' "${!SLUG[@]}" | sort) )

echo "=== Codex FIX campaign: ${#targets[@]} pieces, MAXJOBS=${MAXJOBS}, timeout=${TIMEOUT}s, branch=$(git branch --show-current) ==="
for id in "${targets[@]}"; do
  while [ "$(jobs -r | wc -l)" -ge "$MAXJOBS" ]; do wait -n; done
  run_piece "$id" &
done
wait
echo "=== FIX CAMPAIGN BATCH COMPLETE ($(date +%H:%M:%S)) — edits left UNCOMMITTED for review ==="
echo "--- working tree changes (review these) ---"
git status -s | grep -vE 'research/canon/' | head -60
echo "--- per-piece reports ---"
for id in "${targets[@]}"; do
  f="research/canon/fixes/${id}-${SLUG[$id]}.fix.md"
  [ -f "$f" ] && printf '%s: %s | %s\n' "$id" \
    "$(grep -m1 'FILES-CHANGED:' "$f" | sed 's/.*FILES-CHANGED://' | xargs)" \
    "$(grep -m1 'TESTS:' "$f" | sed 's/.*TESTS://' | xargs)"
done
