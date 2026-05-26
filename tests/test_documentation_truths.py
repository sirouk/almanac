#!/usr/bin/env python3
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PRODUCT_MATRIX = REPO / "research" / "PRODUCT_REALITY_MATRIX.md"
PRODUCT_MATRIX_STATUSES = {"real", "partial", "gap", "proof-gated", "policy-question"}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _section_between(body: str, start: str, end: str) -> str:
    try:
        start_index = body.index(start)
        end_index = body.index(end, start_index)
    except ValueError as exc:
        raise AssertionError(f"missing documentation section boundary: {exc}") from exc
    return body[start_index:end_index]


def _product_matrix_rows() -> list[tuple[int, str, str, str, str]]:
    rows: list[tuple[int, str, str, str, str]] = []
    for line_number, line in enumerate(PRODUCT_MATRIX.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) != 4 or parts[0] == "Claim":
            continue
        rows.append((line_number, parts[0], parts[1], parts[2], parts[3]))
    return rows


def _product_matrix_declared_totals() -> dict[str, int]:
    body = PRODUCT_MATRIX.read_text(encoding="utf-8")
    match = re.search(r"Current row totals: (?P<totals>.*?`policy-question`)\.", body, re.DOTALL)
    expect(bool(match), "PRODUCT_REALITY_MATRIX.md must declare current row totals.")
    return {status: int(count) for count, status in re.findall(r"(\d+)\s+`([^`]+)`", match.group("totals"))}


def _has_product_matrix_source_anchor(text: str) -> bool:
    inline_tokens = [
        token
        for token in re.findall(r"`([^`]+)`", text)
        if not token.startswith(("secret://", "$"))
    ]
    if inline_tokens:
        return True
    return bool(
        re.search(
            r"\b(API|adapter|dashboard|function|hosted|lifecycle|metadata|Next\.js|onboarding|"
            r"plugin|provisioning|provider-state|public bot|Raven|read-models?|route|service|"
            r"source-owned|state|Telegram|Discord|webhook|worker)\b",
            text,
            re.IGNORECASE,
        )
    )


def _has_product_matrix_proof_anchor(text: str) -> bool:
    return bool(
        re.search(
            r"\b(test|tests|coverage|fake|guard|guards|local|operator chose|operator decision|"
            r"policy decision|proof|regression|static search)\b",
            text,
            re.IGNORECASE,
        )
    )


def test_product_matrix_totals_match_rows_and_statuses_are_known() -> None:
    rows = _product_matrix_rows()
    expect(rows, "PRODUCT_REALITY_MATRIX.md should contain claim rows.")

    statuses = Counter(status for _, _, status, _, _ in rows)
    unknown = sorted(status for status in statuses if status not in PRODUCT_MATRIX_STATUSES)
    expect(not unknown, f"Unknown product matrix statuses: {unknown}")
    actual_totals = {status: statuses.get(status, 0) for status in PRODUCT_MATRIX_STATUSES}
    expect(
        _product_matrix_declared_totals() == actual_totals,
        f"Product matrix totals drifted. declared={_product_matrix_declared_totals()} actual={actual_totals}",
    )
    print("PASS test_product_matrix_totals_match_rows_and_statuses_are_known")


def test_product_matrix_real_rows_have_source_and_proof_anchors() -> None:
    offenders: list[str] = []
    for line_number, claim, status, evidence, action in _product_matrix_rows():
        if status != "real":
            continue
        text = f"{evidence} {action}"
        if not _has_product_matrix_source_anchor(text) or not _has_product_matrix_proof_anchor(text):
            offenders.append(f"{PRODUCT_MATRIX.relative_to(REPO)}:{line_number} {claim!r}")
    expect(
        not offenders,
        "Rows marked real need source-owned evidence plus local test/proof/policy anchors:\n"
        + "\n".join(offenders),
    )
    print("PASS test_product_matrix_real_rows_have_source_and_proof_anchors")


def test_product_matrix_gated_rows_keep_live_or_policy_boundaries() -> None:
    proof_offenders: list[str] = []
    policy_offenders: list[str] = []
    for line_number, claim, status, evidence, action in _product_matrix_rows():
        text = f"{claim} {evidence} {action}"
        if status == "proof-gated" and not re.search(
            r"\b(authori[sz]ation|authori[sz]ed|external|gated|live|proof|prove|run only|sandbox)\b",
            text,
            re.IGNORECASE,
        ):
            proof_offenders.append(f"{PRODUCT_MATRIX.relative_to(REPO)}:{line_number} {claim!r}")
        if status == "policy-question" and not re.search(
            r"\b(ask|choose|decision|disabled|operator|policy|product-owned|question)\b",
            text,
            re.IGNORECASE,
        ):
            policy_offenders.append(f"{PRODUCT_MATRIX.relative_to(REPO)}:{line_number} {claim!r}")
    expect(not proof_offenders, "Proof-gated rows need explicit live/external proof language:\n" + "\n".join(proof_offenders))
    expect(not policy_offenders, "Policy-question rows need explicit operator/product decision language:\n" + "\n".join(policy_offenders))
    print("PASS test_product_matrix_gated_rows_keep_live_or_policy_boundaries")


def test_agents_service_user_unit_list_matches_templates() -> None:
    body = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    section = _section_between(
        body,
        "Main service-user units installed for the ArcLink service user:",
        "Whether Curator uses onboarding services",
    )
    documented_units = set(re.findall(r"\barclink-[a-z0-9-]+\.(?:service|timer|path)\b", section))
    template_units = {path.name for path in (REPO / "systemd" / "user").iterdir() if path.is_file()}
    expect(
        documented_units == template_units,
        f"AGENTS.md service-user unit list drifted.\nmissing={sorted(template_units - documented_units)}\nextra={sorted(documented_units - template_units)}",
    )
    print("PASS test_agents_service_user_unit_list_matches_templates")


def test_org_profile_docs_mark_cli_as_shipped_contract() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    org_doc = (REPO / "docs" / "org-profile.md").read_text(encoding="utf-8")
    ctl = (REPO / "python" / "arclink_ctl.py").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())
    expect('subparsers.add_parser("org-profile")' in ctl, "org-profile CLI should be implemented")
    expect(
        "`arclink-ctl org-profile`" in readme
        and "build, validate, preview, apply, and doctor workflow" in normalized_readme,
        readme,
    )
    expect("The commands and receipts below are the shipped operator contract." in org_doc, org_doc)
    print("PASS test_org_profile_docs_mark_cli_as_shipped_contract")


def test_docs_do_not_claim_stripe_webhook_skip() -> None:
    forbidden = (
        "Stripe webhook skip",
        "skip for no-secret environments",
    )
    offenders = []
    for path in (REPO / "docs").rglob("*.md"):
        body = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            if phrase in body:
                offenders.append(f"{path.relative_to(REPO)} contains {phrase!r}")
    expect(not offenders, "\n".join(offenders))

    foundation = (REPO / "docs" / "arclink" / "foundation.md").read_text(encoding="utf-8")
    expect("stripe_webhook_secret_unset" in foundation, foundation)
    expect("status 503" in foundation, foundation)
    print("PASS test_docs_do_not_claim_stripe_webhook_skip")


def test_creative_brief_labels_live_external_proof_gates() -> None:
    brief = (REPO / "docs" / "arclink" / "CREATIVE_BRIEF.md").read_text(encoding="utf-8")
    expect(
        "implemented in the current `arclink` branch" not in brief,
        "Creative brief must not broadly claim live implementation without the local/fake-adapter boundary.",
    )
    expect("implemented as local public-repo behavior" in brief, brief)
    expect("live external\nproof remains gated" in brief, brief)
    for surface in ("Stripe", "Telegram", "Discord", "Notion", "Chutes", "Cloudflare", "Tailscale", "Docker"):
        expect(surface in brief, f"Creative brief proof-gate sentence should name {surface}.")
    expect("live workspace verification stays proof-gated" in brief, brief)
    expect("live runtime\n  access stays proof-gated" in brief, brief)
    expect("live provider key creation\n  and utilization proof stay gated" in brief, brief)
    expect("recorded Notion as ready for this ArcPod" not in brief, brief)
    expect("ready for dashboard verification" in brief, brief)
    print("PASS test_creative_brief_labels_live_external_proof_gates")


def test_shipped_docs_do_not_claim_live_external_proof_passed() -> None:
    forbidden = (
        "live proof passed",
        "live external proof passed",
        "live Stripe proof passed",
        "live Chutes proof passed",
        "live Notion proof passed",
        "live Cloudflare proof passed",
        "live Tailscale proof passed",
        "production host proof passed",
    )
    offenders = []
    for path in (REPO / "docs").rglob("*.md"):
        rel = path.relative_to(REPO)
        body = path.read_text(encoding="utf-8")
        lowered = body.lower()
        for phrase in forbidden:
            if phrase.lower() in lowered:
                offenders.append(f"{rel} contains {phrase!r}")
    expect(not offenders, "\n".join(offenders))
    print("PASS test_shipped_docs_do_not_claim_live_external_proof_passed")


def test_foundation_docs_align_with_control_node_boundary() -> None:
    foundation = (REPO / "docs" / "arclink" / "foundation.md").read_text(encoding="utf-8")
    runbook = (REPO / "docs" / "arclink" / "foundation-runbook.md").read_text(encoding="utf-8")
    control = (REPO / "docs" / "arclink" / "sovereign-control-node.md").read_text(encoding="utf-8")

    for required in (
        "control-web",
        "control-api",
        "control-provisioner",
        "control-action-worker",
        "control-llm-router",
    ):
        expect(required in control, f"Control Node docs should name shipped service {required}.")

    stale_claims = (
        "does not ship production adapters that execute customer deployment containers",
        "run live public bots",
        "authenticate dashboard sessions",
        "run a live automated admin-action worker",
        "They do not run live Telegram or Discord clients yet.",
        "production frontend stack, auth, RBAC, CSRF, rate limits, and live action execution are later gates",
        "Production routing, identity-provider integration, browser-session hardening, RBAC",
    )
    for body_name, body in (("foundation.md", foundation), ("foundation-runbook.md", runbook)):
        for phrase in stale_claims:
            expect(phrase not in body, f"{body_name} preserves stale Control Node boundary phrase: {phrase!r}")

    expect("Next.js `control-web` plus hosted `/api/v1` `control-api`" in foundation, foundation)
    expect("Live client/webhook entrypoints are owned by" in foundation, foundation)
    expect("Passing local tests or dry runs must not be\nreported as live customer provisioning" in runbook, runbook)
    expect("live action proof remain separate gates" in runbook, runbook)
    print("PASS test_foundation_docs_align_with_control_node_boundary")


def test_captain_facing_vocabulary_does_not_regress_to_sovereign_pod_copy() -> None:
    forbidden = (
        "Sovereign Pod",
        "Sovereign pod",
        "sovereign pod",
        "Sovereign pods",
        "sovereign pods",
        "Sovereign deployment",
        "sovereign deployment",
        "Sovereign-equivalent",
        "paid-customer pod",
        "customer pod",
        "per-user pod",
        "per-user Sovereign",
        "ArcLink Curator",
        "Curator manages",
        "Curator/plugin",
        "Curator's plugin",
        "Curator updates",
        "competent operator on comms",
        "working unit aboard",
    )
    scanned_roots = (
        REPO / "README.md",
        REPO / "AGENTS.md",
        REPO / "templates",
        REPO / "docs",
        REPO / "web" / "src",
        REPO / "python",
        REPO / "bin",
    )
    allowed = {
        Path("docs/arclink/vocabulary.md"),
    }
    offenders: list[str] = []
    for root in scanned_roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix not in {"", ".md", ".py", ".tsx", ".ts", ".sh", ".yaml", ".yml"}:
                continue
            rel = path.relative_to(REPO)
            if (
                rel in allowed
                or rel == Path("tests/test_documentation_truths.py")
                or "arclink-priv" in rel.parts
                or "openapi" in rel.parts
            ):
                continue
            body = path.read_text(encoding="utf-8", errors="ignore")
            for phrase in forbidden:
                if phrase in body:
                    offenders.append(f"{rel} contains stale vocabulary {phrase!r}")
    expect(not offenders, "\n".join(offenders))
    print("PASS test_captain_facing_vocabulary_does_not_regress_to_sovereign_pod_copy")


def main() -> int:
    test_product_matrix_totals_match_rows_and_statuses_are_known()
    test_product_matrix_real_rows_have_source_and_proof_anchors()
    test_product_matrix_gated_rows_keep_live_or_policy_boundaries()
    test_agents_service_user_unit_list_matches_templates()
    test_org_profile_docs_mark_cli_as_shipped_contract()
    test_docs_do_not_claim_stripe_webhook_skip()
    test_creative_brief_labels_live_external_proof_gates()
    test_shipped_docs_do_not_claim_live_external_proof_passed()
    test_foundation_docs_align_with_control_node_boundary()
    test_captain_facing_vocabulary_does_not_regress_to_sovereign_pod_copy()
    print("PASS all 10 documentation truth tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
