#!/usr/bin/env python3
from __future__ import annotations

import json
import importlib.util
import os
import re
import shlex
import sqlite3
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
PYTHON_DIR = REPO / "python"
HOST_REPO_BIND = "${ARCLINK_DOCKER_HOST_REPO_DIR:-.}:${ARCLINK_DOCKER_HOST_REPO_DIR:-/home/arclink/arclink}"
HOST_REPO_BIND_RO = f"{HOST_REPO_BIND}:ro"
TRUSTED_HOST_RISK_ENV = "ARCLINK_DOCKER_TRUSTED_HOST_RISK_ACCEPTED"
TRUSTED_HOST_RISK_ACCEPTED = "accepted"
HIGH_AUTHORITY_SERVICES = (
    "deployment-exec-broker",
    "migration-capture-helper",
    "agent-user-helper",
    "agent-process-helper",
    "agent-supervisor-broker",
    "operator-upgrade-broker",
    "gateway-exec-broker",
)

os.environ.setdefault(TRUSTED_HOST_RISK_ENV, TRUSTED_HOST_RISK_ACCEPTED)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def load_python_module(path: Path, name: str):
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_agent_process_helper_repo_targets(repo: Path) -> None:
    for rel in (
        "bin/install-agent-user-services.sh",
        "bin/hermes-shell.sh",
        "bin/user-agent-refresh.sh",
    ):
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
    identity = repo / "python" / "arclink_headless_hermes_setup.py"
    identity.parent.mkdir(parents=True, exist_ok=True)
    identity.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    identity.chmod(0o644)


def extract(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def compose_service_blocks() -> dict[str, str]:
    body = read("compose.yaml")
    start = body.index("services:")
    end_match = re.search(r"^volumes:\s*$", body[start:], re.MULTILINE)
    end = start + end_match.start() if end_match else len(body)
    services_text = body[start:end]
    matches = list(re.finditer(r"^  ([A-Za-z0-9_-]+):\s*$", services_text, re.MULTILINE))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(services_text)
        blocks[match.group(1)] = services_text[match.start():block_end]
    return blocks


def compose_list_values(block: str, key: str) -> list[str]:
    match = re.search(
        rf"^\s+{re.escape(key)}:\s*\n(?P<items>(?:\s+-\s+[^\n]+\n)+)",
        block,
        re.MULTILINE,
    )
    if not match:
        return []
    values = []
    for raw in re.findall(r"^\s+-\s+(.+?)\s*$", match.group("items"), re.MULTILINE):
        values.append(raw.strip().strip('"').strip("'"))
    return values


def compose_service_networks(block: str) -> list[str]:
    return compose_list_values(block, "networks") or ["default"]


def compose_network_definitions() -> dict[str, dict[str, object]]:
    body = read("compose.yaml")
    match = re.search(r"^networks:\s*$", body, re.MULTILINE)
    if not match:
        return {}
    text = body[match.end() :]
    matches = list(re.finditer(r"^  ([A-Za-z0-9_-]+):(?:\s*\{\})?\s*$", text, re.MULTILINE))
    networks: dict[str, dict[str, object]] = {}
    for index, item in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[item.start() : block_end]
        networks[item.group(1)] = {
            "block": block,
            "internal": bool(re.search(r"^\s+internal:\s+true\s*$", block, re.MULTILINE)),
        }
    return networks


def compose_capability_boundary(block: str) -> str:
    cap_drop = compose_list_values(block, "cap_drop")
    cap_add = compose_list_values(block, "cap_add")
    if "ALL" in cap_drop:
        if cap_add:
            return "drop_all_add_" + "_".join(cap_add)
        return "all_dropped"
    if cap_add:
        return "default_add_" + "_".join(cap_add)
    return "default"


def docker_authority_inventory() -> dict[str, object]:
    inventory = json.loads(read("config/docker-authority-inventory.json"))
    expect(inventory.get("gap") == "GAP-019", "Docker authority inventory must be tied to GAP-019")
    expect(inventory.get("schema_version") == 52, "Docker authority inventory must carry the GAP-019-BD review schema")
    summary = inventory.get("gap_019_b2_summary")
    expect(isinstance(summary, dict), "Docker authority inventory must summarize GAP-019-B2")
    expect(summary.get("review_status") == "local_review_recorded", f"unexpected GAP-019-B2 summary: {summary}")
    expect("generic Docker socket proxy" in str(summary.get("reason") or ""), f"summary must record generic proxy decision: {summary}")
    gap_c = inventory.get("gap_019_c_summary")
    expect(isinstance(gap_c, dict), "Docker authority inventory must summarize GAP-019-C")
    expect(gap_c.get("selected_service") == "notification-delivery", f"unexpected GAP-019-C service: {gap_c}")
    expect("command allowlist" in str(gap_c.get("control_type") or ""), f"GAP-019-C must name the local command guard: {gap_c}")
    gap_d = inventory.get("gap_019_d_summary")
    expect(isinstance(gap_d, dict), "Docker authority inventory must summarize GAP-019-D")
    expect(gap_d.get("selected_service") == "curator-refresh", f"unexpected GAP-019-D service: {gap_d}")
    expect("removed Docker socket mount" in str(gap_d.get("control_type") or ""), f"GAP-019-D must record the removed authority: {gap_d}")
    gap_e = inventory.get("gap_019_e_summary")
    expect(isinstance(gap_e, dict), "Docker authority inventory must summarize GAP-019-E")
    expect(gap_e.get("selected_service") == "control-provisioner", f"unexpected GAP-019-E service: {gap_e}")
    expect("executor" in str(gap_e.get("control_type") or ""), f"GAP-019-E must name executor preflight: {gap_e}")
    gap_f = inventory.get("gap_019_f_summary")
    expect(isinstance(gap_f, dict), "Docker authority inventory must summarize GAP-019-F")
    expect(gap_f.get("selected_service") == "gateway-exec-broker", f"unexpected GAP-019-F service: {gap_f}")
    expect("broker" in str(gap_f.get("control_type") or ""), f"GAP-019-F must name gateway exec broker: {gap_f}")
    gap_g = inventory.get("gap_019_g_summary")
    expect(isinstance(gap_g, dict), "Docker authority inventory must summarize GAP-019-G")
    expect(gap_g.get("selected_service") == "deployment-exec-broker", f"unexpected GAP-019-G service: {gap_g}")
    expect("deployment" in str(gap_g.get("control_type") or ""), f"GAP-019-G must name deployment exec broker: {gap_g}")
    gap_h = inventory.get("gap_019_h_summary")
    expect(isinstance(gap_h, dict), "Docker authority inventory must summarize GAP-019-H")
    expect(gap_h.get("selected_service") == "control-action-worker", f"unexpected GAP-019-H service: {gap_h}")
    expect("removed Docker socket mount" in str(gap_h.get("control_type") or ""), f"GAP-019-H must record action-worker socket removal: {gap_h}")
    gap_i = inventory.get("gap_019_i_summary")
    expect(isinstance(gap_i, dict), "Docker authority inventory must summarize GAP-019-I")
    expect(gap_i.get("selected_service") == "agent-supervisor-broker", f"unexpected GAP-019-I service: {gap_i}")
    expect("broker" in str(gap_i.get("control_type") or ""), f"GAP-019-I must name agent supervisor broker: {gap_i}")
    gap_j = inventory.get("gap_019_j_summary")
    expect(isinstance(gap_j, dict), "Docker authority inventory must summarize GAP-019-J")
    expect(gap_j.get("selected_service") == "operator-upgrade-broker", f"unexpected GAP-019-J service: {gap_j}")
    expect("operator upgrade" in str(gap_j.get("control_type") or "").lower(), f"GAP-019-J must name operator upgrade broker controls: {gap_j}")
    gap_u = inventory.get("gap_019_u_summary")
    expect(isinstance(gap_u, dict), "Docker authority inventory must summarize GAP-019-U")
    expect(gap_u.get("selected_service") == "operator-upgrade-broker", f"unexpected GAP-019-U service: {gap_u}")
    expect("split" in str(gap_u.get("control_type") or "").lower(), f"GAP-019-U must name the broker split: {gap_u}")
    gap_v = inventory.get("gap_019_v_summary")
    expect(isinstance(gap_v, dict), "Docker authority inventory must summarize GAP-019-V")
    expect(gap_v.get("selected_service") == "control-ingress", f"unexpected GAP-019-V service: {gap_v}")
    expect("static file provider" in str(gap_v.get("control_type") or ""), f"GAP-019-V must name static Traefik routing: {gap_v}")
    expect("Docker socket" in str(gap_v.get("removed_authority") or ""), f"GAP-019-V must record removed socket authority: {gap_v}")
    gap_x = inventory.get("gap_019_x_summary")
    expect(isinstance(gap_x, dict), "Docker authority inventory must summarize GAP-019-X")
    expect(gap_x.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-X service: {gap_x}")
    expect("minimal service env" in str(gap_x.get("control_type") or ""), f"GAP-019-X must name minimal service env controls: {gap_x}")
    expect("container secrets" in str(gap_x.get("removed_authority") or ""), f"GAP-019-X must record removed secret authority: {gap_x}")
    gap_y = inventory.get("gap_019_y_summary")
    expect(isinstance(gap_y, dict), "Docker authority inventory must summarize GAP-019-Y")
    expect(gap_y.get("selected_service") == "gateway-exec-broker", f"unexpected GAP-019-Y service: {gap_y}")
    expect("minimal service env" in str(gap_y.get("control_type") or ""), f"GAP-019-Y must name gateway broker env controls: {gap_y}")
    expect("private config/state/secrets" in str(gap_y.get("removed_authority") or ""), f"GAP-019-Y must record removed private mounts: {gap_y}")
    gap_z = inventory.get("gap_019_z_summary")
    expect(isinstance(gap_z, dict), "Docker authority inventory must summarize GAP-019-Z")
    expect(gap_z.get("selected_service") == "agent-supervisor-broker", f"unexpected GAP-019-Z service: {gap_z}")
    expect("minimal service env" in str(gap_z.get("control_type") or ""), f"GAP-019-Z must name dashboard broker env controls: {gap_z}")
    expect("private config/state/secrets" in str(gap_z.get("removed_authority") or ""), f"GAP-019-Z must record removed private mounts: {gap_z}")
    gap_aa = inventory.get("gap_019_aa_summary")
    expect(isinstance(gap_aa, dict), "Docker authority inventory must summarize GAP-019-AA")
    expect(gap_aa.get("selected_service") == "deployment-exec-broker", f"unexpected GAP-019-AA service: {gap_aa}")
    expect("minimal service env" in str(gap_aa.get("control_type") or ""), f"GAP-019-AA must name deployment broker env controls: {gap_aa}")
    expect("broad *arclink-env" in str(gap_aa.get("removed_authority") or ""), f"GAP-019-AA must record removed broad env: {gap_aa}")
    gap_ab = inventory.get("gap_019_ab_summary")
    expect(isinstance(gap_ab, dict), "Docker authority inventory must summarize GAP-019-AB")
    expect(gap_ab.get("selected_service") == "operator-upgrade-broker", f"unexpected GAP-019-AB service: {gap_ab}")
    expect("minimal service env" in str(gap_ab.get("control_type") or ""), f"GAP-019-AB must name operator broker env controls: {gap_ab}")
    expect("child-process env allowlist" in str(gap_ab.get("control_type") or ""), f"GAP-019-AB must name child env controls: {gap_ab}")
    expect("broad *arclink-env" in str(gap_ab.get("removed_authority") or ""), f"GAP-019-AB must record removed broad env: {gap_ab}")
    gap_ac = inventory.get("gap_019_ac_summary")
    expect(isinstance(gap_ac, dict), "Docker authority inventory must summarize GAP-019-AC")
    expect(gap_ac.get("selected_service") == "migration-capture-helper", f"unexpected GAP-019-AC service: {gap_ac}")
    expect("minimal service env" in str(gap_ac.get("control_type") or ""), f"GAP-019-AC must name migration helper env controls: {gap_ac}")
    expect("configured state-root" in str(gap_ac.get("control_type") or ""), f"GAP-019-AC must name state-root confinement: {gap_ac}")
    expect("broad *arclink-env" in str(gap_ac.get("removed_authority") or ""), f"GAP-019-AC must record removed broad env: {gap_ac}")
    gap_ad = inventory.get("gap_019_ad_summary")
    expect(isinstance(gap_ad, dict), "Docker authority inventory must summarize GAP-019-AD")
    expect(gap_ad.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-AD service: {gap_ad}")
    expect("absolute setpriv" in str(gap_ad.get("control_type") or ""), f"GAP-019-AD must name absolute setpriv dispatch: {gap_ad}")
    expect("caller-controlled PATH" in str(gap_ad.get("removed_authority") or ""), f"GAP-019-AD must record removed PATH authority: {gap_ad}")
    gap_ae = inventory.get("gap_019_ae_summary")
    expect(isinstance(gap_ae, dict), "Docker authority inventory must summarize GAP-019-AE")
    expect(gap_ae.get("selected_service") == "agent-user-helper", f"unexpected GAP-019-AE service: {gap_ae}")
    expect("absolute root executable" in str(gap_ae.get("control_type") or ""), f"GAP-019-AE must name absolute root executable dispatch: {gap_ae}")
    expect("ambient helper PATH" in str(gap_ae.get("removed_authority") or ""), f"GAP-019-AE must record removed PATH authority: {gap_ae}")
    gap_af = inventory.get("gap_019_af_summary")
    expect(isinstance(gap_af, dict), "Docker authority inventory must summarize GAP-019-AF")
    expect(gap_af.get("selected_service") == "agent-supervisor-broker", f"unexpected GAP-019-AF service: {gap_af}")
    expect("Docker CLI" in str(gap_af.get("control_type") or ""), f"GAP-019-AF must name Docker CLI preflight: {gap_af}")
    expect("ARCLINK_DOCKER_BINARY" in str(gap_af.get("removed_authority") or ""), f"GAP-019-AF must record removed Docker binary steering: {gap_af}")
    gap_ag = inventory.get("gap_019_ag_summary")
    expect(isinstance(gap_ag, dict), "Docker authority inventory must summarize GAP-019-AG")
    expect(gap_ag.get("selected_service") == "deployment-exec-broker", f"unexpected GAP-019-AG service: {gap_ag}")
    expect("Docker CLI" in str(gap_ag.get("control_type") or ""), f"GAP-019-AG must name Docker CLI preflight: {gap_ag}")
    expect("ARCLINK_DOCKER_BINARY" in str(gap_ag.get("removed_authority") or ""), f"GAP-019-AG must record removed Docker binary steering: {gap_ag}")
    gap_ah = inventory.get("gap_019_ah_summary")
    expect(isinstance(gap_ah, dict), "Docker authority inventory must summarize GAP-019-AH")
    expect(gap_ah.get("selected_service") == "gateway-exec-broker", f"unexpected GAP-019-AH service: {gap_ah}")
    expect("Docker CLI" in str(gap_ah.get("control_type") or ""), f"GAP-019-AH must name Docker CLI preflight: {gap_ah}")
    expect("ARCLINK_DOCKER_BINARY" in str(gap_ah.get("removed_authority") or ""), f"GAP-019-AH must record removed Docker binary steering: {gap_ah}")
    gap_ay = inventory.get("gap_019_ay_summary")
    expect(isinstance(gap_ay, dict), "Docker authority inventory must summarize GAP-019-AY")
    expect(gap_ay.get("selected_service") == "gateway-exec-broker", f"unexpected GAP-019-AY service: {gap_ay}")
    expect("Compose fallback" in str(gap_ay.get("control_type") or ""), f"GAP-019-AY must name gateway fallback config controls: {gap_ay}")
    expect("symlinked" in str(gap_ay.get("removed_authority") or ""), f"GAP-019-AY must record removed symlink fallback authority: {gap_ay}")
    gap_az = inventory.get("gap_019_az_summary")
    expect(isinstance(gap_az, dict), "Docker authority inventory must summarize GAP-019-AZ")
    expect(gap_az.get("selected_service") == "agent-supervisor-broker", f"unexpected GAP-019-AZ service: {gap_az}")
    expect("private bind-root" in str(gap_az.get("control_type") or ""), f"GAP-019-AZ must name dashboard private bind-root controls: {gap_az}")
    expect("ARCLINK_DOCKER_HOST_PRIV_DIR" in str(gap_az.get("removed_authority") or ""), f"GAP-019-AZ must record host private-root steering: {gap_az}")
    expect("ARCLINK_DOCKER_CONTAINER_PRIV_DIR" in str(gap_az.get("removed_authority") or ""), f"GAP-019-AZ must record container private-root steering: {gap_az}")
    gap_ba = inventory.get("gap_019_ba_summary")
    expect(isinstance(gap_ba, dict), "Docker authority inventory must summarize GAP-019-BA")
    expect(gap_ba.get("selected_service") == "agent-user-helper", f"unexpected GAP-019-BA service: {gap_ba}")
    expect("uid/gid assignment file" in str(gap_ba.get("control_type") or ""), f"GAP-019-BA must name assignment file controls: {gap_ba}")
    expect(".arclink-user-ids.json.tmp" in str(gap_ba.get("removed_authority") or ""), f"GAP-019-BA must record temp-file steering: {gap_ba}")
    gap_bb = inventory.get("gap_019_bb_summary")
    expect(isinstance(gap_bb, dict), "Docker authority inventory must summarize GAP-019-BB")
    expect(gap_bb.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-BB service: {gap_bb}")
    expect("rejected-request incident" in str(gap_bb.get("control_type") or ""), f"GAP-019-BB must name rejection incidents: {gap_bb}")
    expect("rejections.jsonl" in str(gap_bb.get("reason") or ""), f"GAP-019-BB must name the incident path: {gap_bb}")
    gap_bc = inventory.get("gap_019_bc_summary")
    expect(isinstance(gap_bc, dict), "Docker authority inventory must summarize GAP-019-BC")
    expect(gap_bc.get("selected_service") == "gateway-exec-broker", f"unexpected GAP-019-BC service: {gap_bc}")
    expect("rejected-request incident" in str(gap_bc.get("control_type") or ""), f"GAP-019-BC must name gateway rejection incidents: {gap_bc}")
    expect("_broker-incidents/gateway-exec-broker/rejections.jsonl" in str(gap_bc.get("reason") or ""), f"GAP-019-BC must name the incident path: {gap_bc}")
    gap_bd = inventory.get("gap_019_bd_summary")
    expect(isinstance(gap_bd, dict), "Docker authority inventory must summarize GAP-019-BD")
    expect("rejected-request incidents" in str(gap_bd.get("control_type") or ""), f"GAP-019-BD must name rejection incidents: {gap_bd}")
    expect("deployment-exec-broker" in json.dumps(gap_bd), f"GAP-019-BD must name deployment broker incidents: {gap_bd}")
    expect("operator-upgrade-broker" in json.dumps(gap_bd), f"GAP-019-BD must name operator broker incidents: {gap_bd}")
    gap_ai = inventory.get("gap_019_ai_summary")
    expect(isinstance(gap_ai, dict), "Docker authority inventory must summarize GAP-019-AI")
    expect(gap_ai.get("selected_service") == "operator-upgrade-broker", f"unexpected GAP-019-AI service: {gap_ai}")
    expect("Docker CLI" in str(gap_ai.get("control_type") or ""), f"GAP-019-AI must name Docker CLI preflight: {gap_ai}")
    expect("ARCLINK_DOCKER_BINARY" in str(gap_ai.get("removed_authority") or ""), f"GAP-019-AI must record removed Docker binary steering: {gap_ai}")
    gap_av = inventory.get("gap_019_av_summary")
    expect(isinstance(gap_av, dict), "Docker authority inventory must summarize GAP-019-AV")
    expect(gap_av.get("selected_service") == "operator-upgrade-broker", f"unexpected GAP-019-AV service: {gap_av}")
    expect("fixed deploy.sh" in str(gap_av.get("control_type") or ""), f"GAP-019-AV must name fixed script preflight: {gap_av}")
    expect("symlinked" in str(gap_av.get("removed_authority") or ""), f"GAP-019-AV must record removed script target authority: {gap_av}")
    gap_aw = inventory.get("gap_019_aw_summary")
    expect(isinstance(gap_aw, dict), "Docker authority inventory must summarize GAP-019-AW")
    expect(gap_aw.get("selected_service") == "operator-upgrade-broker", f"unexpected GAP-019-AW service: {gap_aw}")
    expect("upstream deploy-key" in str(gap_aw.get("control_type") or ""), f"GAP-019-AW must name upstream deploy-key path confinement: {gap_aw}")
    expect("ARCLINK_UPSTREAM_DEPLOY_KEY_PATH" in str(gap_aw.get("removed_authority") or ""), f"GAP-019-AW must record removed upstream path steering: {gap_aw}")
    gap_ak = inventory.get("gap_019_ak_summary")
    expect(isinstance(gap_ak, dict), "Docker authority inventory must summarize GAP-019-AK")
    expect(gap_ak.get("review_status") == "local_compose_networks_scoped", f"unexpected GAP-019-AK status: {gap_ak}")
    expect("internal Compose networks" in str(gap_ak.get("control_type") or ""), f"GAP-019-AK must name scoped internal networks: {gap_ak}")
    expect("default network" in str(gap_ak.get("removed_authority") or ""), f"GAP-019-AK must record removed default network reachability: {gap_ak}")
    gap_al = inventory.get("gap_019_al_summary")
    expect(isinstance(gap_al, dict), "Docker authority inventory must summarize GAP-019-AL")
    expect(gap_al.get("review_status") == "local_trusted_host_acceptance_gate_added", f"unexpected GAP-019-AL status: {gap_al}")
    expect(TRUSTED_HOST_RISK_ENV in str(gap_al.get("control_type") or ""), f"GAP-019-AL must name the acceptance env: {gap_al}")
    expect("does not close GAP-019" in str(gap_al.get("remaining_gate") or ""), f"GAP-019-AL must preserve the residual gate: {gap_al}")
    gap_am = inventory.get("gap_019_am_summary")
    expect(isinstance(gap_am, dict), "Docker authority inventory must summarize GAP-019-AM")
    expect(gap_am.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-AM service: {gap_am}")
    expect("unapproved process env" in str(gap_am.get("control_type") or ""), f"GAP-019-AM must name process env controls: {gap_am}")
    expect("LD_" in str(gap_am.get("reason") or ""), f"GAP-019-AM must name dynamic-loader env rejection: {gap_am}")
    expect("GAP-019 remains open" in str(gap_am.get("remaining_gate") or ""), f"GAP-019-AM must preserve the residual gate: {gap_am}")
    gap_an = inventory.get("gap_019_an_summary")
    expect(isinstance(gap_an, dict), "Docker authority inventory must summarize GAP-019-AN")
    expect("agent-user-helper" in str(gap_an.get("selected_services") or ""), f"GAP-019-AN must name agent-user-helper: {gap_an}")
    expect("agent-process-helper" in str(gap_an.get("selected_services") or ""), f"GAP-019-AN must name agent-process-helper: {gap_an}")
    expect("symlink" in str(gap_an.get("control_type") or ""), f"GAP-019-AN must name symlink path controls: {gap_an}")
    expect("GAP-019 remains open" in str(gap_an.get("remaining_gate") or ""), f"GAP-019-AN must preserve the residual gate: {gap_an}")
    gap_ao = inventory.get("gap_019_ao_summary")
    expect(isinstance(gap_ao, dict), "Docker authority inventory must summarize GAP-019-AO")
    expect(gap_ao.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-AO service: {gap_ao}")
    expect("log directory" in str(gap_ao.get("control_type") or ""), f"GAP-019-AO must name log directory controls: {gap_ao}")
    expect("symlink" in str(gap_ao.get("removed_authority") or ""), f"GAP-019-AO must name symlink log redirection: {gap_ao}")
    expect("GAP-019 remains open" in str(gap_ao.get("remaining_gate") or ""), f"GAP-019-AO must preserve the residual gate: {gap_ao}")
    gap_ap = inventory.get("gap_019_ap_summary")
    expect(isinstance(gap_ap, dict), "Docker authority inventory must summarize GAP-019-AP")
    expect("loopback" in str(gap_ap.get("control_type") or ""), f"GAP-019-AP must name loopback listener defaults: {gap_ap}")
    expect("0.0.0.0" in str(gap_ap.get("removed_authority") or ""), f"GAP-019-AP must record removed broad direct-run bind: {gap_ap}")
    expect("GAP-019 remains open" in str(gap_ap.get("remaining_gate") or ""), f"GAP-019-AP must preserve the residual gate: {gap_ap}")
    gap_aq = inventory.get("gap_019_aq_summary")
    expect(isinstance(gap_aq, dict), "Docker authority inventory must summarize GAP-019-AQ")
    expect(gap_aq.get("selected_service") == "agent-supervisor", f"unexpected GAP-019-AQ service: {gap_aq}")
    expect("child-process env allowlist" in str(gap_aq.get("control_type") or ""), f"GAP-019-AQ must name child env controls: {gap_aq}")
    expect("os.environ.copy" in str(gap_aq.get("removed_authority") or ""), f"GAP-019-AQ must record removed full env inheritance: {gap_aq}")
    expect("GAP-019 remains open" in str(gap_aq.get("remaining_gate") or ""), f"GAP-019-AQ must preserve the residual gate: {gap_aq}")
    gap_ar = inventory.get("gap_019_ar_summary")
    expect(isinstance(gap_ar, dict), "Docker authority inventory must summarize GAP-019-AR")
    expect("agent-process-helper" in str(gap_ar.get("selected_services") or ""), f"GAP-019-AR must name agent-process-helper: {gap_ar}")
    expect("agent-supervisor-broker" in str(gap_ar.get("selected_services") or ""), f"GAP-019-AR must name agent-supervisor-broker: {gap_ar}")
    expect("dashboard backend host" in str(gap_ar.get("control_type") or ""), f"GAP-019-AR must name dashboard backend host controls: {gap_ar}")
    expect("wildcard" in str(gap_ar.get("removed_authority") or ""), f"GAP-019-AR must record removed wildcard/global host authority: {gap_ar}")
    expect("GAP-019 remains open" in str(gap_ar.get("remaining_gate") or ""), f"GAP-019-AR must preserve the residual gate: {gap_ar}")
    gap_as = inventory.get("gap_019_as_summary")
    expect(isinstance(gap_as, dict), "Docker authority inventory must summarize GAP-019-AS")
    expect("agent-user-helper" in str(gap_as.get("selected_services") or ""), f"GAP-019-AS must name agent-user-helper: {gap_as}")
    expect("agent-process-helper" in str(gap_as.get("selected_services") or ""), f"GAP-019-AS must name agent-process-helper: {gap_as}")
    expect("agent-home root" in str(gap_as.get("control_type") or ""), f"GAP-019-AS must name agent-home root controls: {gap_as}")
    expect("symlink" in str(gap_as.get("removed_authority") or ""), f"GAP-019-AS must record removed symlink root authority: {gap_as}")
    expect("GAP-019 remains open" in str(gap_as.get("remaining_gate") or ""), f"GAP-019-AS must preserve the residual gate: {gap_as}")
    gap_at = inventory.get("gap_019_at_summary")
    expect(isinstance(gap_at, dict), "Docker authority inventory must summarize GAP-019-AT")
    expect(gap_at.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-AT service: {gap_at}")
    expect("repo" in str(gap_at.get("control_type") or ""), f"GAP-019-AT must name repo/private/runtime controls: {gap_at}")
    expect("symlink" in str(gap_at.get("removed_authority") or ""), f"GAP-019-AT must record removed symlink authority: {gap_at}")
    expect("GAP-019 remains open" in str(gap_at.get("remaining_gate") or ""), f"GAP-019-AT must preserve the residual gate: {gap_at}")
    gap_k = inventory.get("gap_019_k_summary")
    expect(isinstance(gap_k, dict), "Docker authority inventory must summarize GAP-019-K")
    expect(gap_k.get("selected_service") == "control-action-worker", f"unexpected GAP-019-K service: {gap_k}")
    expect("root-capture opt-in" in str(gap_k.get("control_type") or ""), f"GAP-019-K must name root-capture opt-in controls: {gap_k}")
    gap_l = inventory.get("gap_019_l_summary")
    expect(isinstance(gap_l, dict), "Docker authority inventory must summarize GAP-019-L")
    expect(gap_l.get("selected_service") == "agent-supervisor", f"unexpected GAP-019-L service: {gap_l}")
    expect("metadata" in str(gap_l.get("control_type") or "").lower(), f"GAP-019-L must name metadata/path controls: {gap_l}")
    gap_m = inventory.get("gap_019_m_summary")
    expect(isinstance(gap_m, dict), "Docker authority inventory must summarize GAP-019-M")
    expect(gap_m.get("review_status") == "local_incident_controls_recorded", f"unexpected GAP-019-M status: {gap_m}")
    expect("incident response ledger" in str(gap_m.get("control_type") or ""), f"GAP-019-M must name incident controls: {gap_m}")
    gap_n = inventory.get("gap_019_n_summary")
    expect(isinstance(gap_n, dict), "Docker authority inventory must summarize GAP-019-N")
    expect(gap_n.get("selected_service") == "migration-capture-helper", f"unexpected GAP-019-N service: {gap_n}")
    expect("capture/materialization" in str(gap_n.get("control_type") or ""), f"GAP-019-N must name migration capture helper controls: {gap_n}")
    gap_o = inventory.get("gap_019_o_summary")
    expect(isinstance(gap_o, dict), "Docker authority inventory must summarize GAP-019-O")
    expect(gap_o.get("selected_service") == "agent-user-helper", f"unexpected GAP-019-O service: {gap_o}")
    expect("user/home setup" in str(gap_o.get("control_type") or ""), f"GAP-019-O must name agent user helper controls: {gap_o}")
    gap_p = inventory.get("gap_019_p_summary")
    expect(isinstance(gap_p, dict), "Docker authority inventory must summarize GAP-019-P")
    expect(gap_p.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-P service: {gap_p}")
    expect("setpriv" in str(gap_p.get("control_type") or ""), f"GAP-019-P must name agent process helper controls: {gap_p}")
    gap_q = inventory.get("gap_019_q_summary")
    expect(isinstance(gap_q, dict), "Docker authority inventory must summarize GAP-019-Q")
    expect(gap_q.get("selected_service") == "agent-user-helper", f"unexpected GAP-019-Q service: {gap_q}")
    expect("cap_drop ALL" in str(gap_q.get("control_type") or ""), f"GAP-019-Q must name the helper capability boundary: {gap_q}")
    gap_r = inventory.get("gap_019_r_summary")
    expect(isinstance(gap_r, dict), "Docker authority inventory must summarize GAP-019-R")
    expect(gap_r.get("selected_service") == "agent-process-helper", f"unexpected GAP-019-R service: {gap_r}")
    expect("argv/log" in str(gap_r.get("control_type") or ""), f"GAP-019-R must name argv/log env controls: {gap_r}")
    gap_s = inventory.get("gap_019_s_summary")
    expect(isinstance(gap_s, dict), "Docker authority inventory must summarize GAP-019-S")
    expect(
        gap_s.get("selected_services") == ["agent-user-helper", "agent-process-helper"],
        f"unexpected GAP-019-S services: {gap_s}",
    )
    expect("configured root" in str(gap_s.get("control_type") or ""), f"GAP-019-S must name configured-root controls: {gap_s}")
    gap_t = inventory.get("gap_019_t_summary")
    expect(isinstance(gap_t, dict), "Docker authority inventory must summarize GAP-019-T")
    expect(
        gap_t.get("selected_services") == ["agent-process-helper", "agent-supervisor", "curator-refresh"],
        f"unexpected GAP-019-T services: {gap_t}",
    )
    expect("read-only host repo" in str(gap_t.get("control_type") or ""), f"GAP-019-T must name read-only host repo controls: {gap_t}")
    return inventory


def compose_docker_authority_surface() -> dict[str, dict[str, object]]:
    surface: dict[str, dict[str, object]] = {}
    for service, block in compose_service_blocks().items():
        mount_modes = re.findall(
            r"^\s+- /var/run/docker\.sock:/var/run/docker\.sock(?P<ro>:ro)?\s*$",
            block,
            re.MULTILINE,
        )
        docker_socket = "none"
        if mount_modes:
            docker_socket = "read_only" if all(mode == ":ro" for mode in mount_modes) else "write"
        explicit_root = bool(re.search(r"^\s+user:\s*[\"']?0:0[\"']?\s*$", block, re.MULTILINE))
        if docker_socket != "none" or explicit_root:
            surface[service] = {
                "docker_socket": docker_socket,
                "explicit_root": explicit_root,
                "linux_capabilities": compose_capability_boundary(block),
                "compose_networks": compose_service_networks(block),
                "block": block,
            }
    return surface


def test_dockerfile_installs_pinned_runtime_assets() -> None:
    body = read("Dockerfile")
    expect("FROM node:22-bookworm-slim" in body, body)
    expect("config/pins.json" in body, body)
    expect("@tobilu/qmd@${qmd_version}" in body, body)
    expect("hermes-agent" in body and "hermes-venv" in body, body)
    expect("hermes-agent-src/hermes_cli/dashboard_auth" in body and '"dashboard_auth"' in body, body)
    expect("stripe" in body, body)
    expect("[ -f /home/arclink/arclink/web/package-lock.json ]" in body, body)
    expect("cd /home/arclink/arclink/web" in body and "npm run build" in body, body)
    expect("hermes-agent-src/ui-tui" in body and "npm run build" in body, body)
    expect("ARCLINK_API_INTERNAL_URL=http://control-api:8900" in body, body)
    expect("poppler-utils" in body and "inotify-tools" in body and "sqlite3" in body and "tmux" in body, body)
    expect("download.docker.com/linux/debian" in body and "docker-ce-cli" in body, body)
    expect("docker-compose-plugin" in body, body)
    expect("iproute2" in body, body)
    expect("ARG ARCLINK_UID=1000" in body and "ARG ARCLINK_GID=1000" in body, body)
    expect('getent passwd "$ARCLINK_UID"' in body and 'chown -R "$ARCLINK_UID:$ARCLINK_GID"' in body, body)
    expect("USER arclink" in body, body)
    print("PASS test_dockerfile_installs_pinned_runtime_assets")


def test_compose_defines_full_stack_services() -> None:
    body = read("compose.yaml")
    expect("arclink-app:" in body and "dockerfile: Dockerfile" in body, body)
    expect("ARCLINK_UID: ${ARCLINK_DOCKER_UID:-1000}" in body, body)
    expect("ARCLINK_GID: ${ARCLINK_DOCKER_GID:-1000}" in body, body)
    expect('profiles: ["build"]' in body, body)
    expect("ARCLINK_BACKEND_ALLOWED_CIDRS:" in body, body)
    expect("ARCLINK_BASE_DOMAIN:" in body and "ARCLINK_PRIMARY_PROVIDER:" in body, body)
    expect("ARCLINK_INGRESS_MODE:" in body and "ARCLINK_TAILSCALE_DNS_NAME:" in body, body)
    expect("ARCLINK_WIREGUARD_CONTROL_PUBLIC_KEY:" in body and "ARCLINK_WIREGUARD_CONTROL_ENDPOINT:" in body, body)
    expect("ARCLINK_WIREGUARD_ACTIVATE:" in body, body)
    expect("ARCLINK_CONTROL_PROVISIONER_ENABLED:" in body and "ARCLINK_EXECUTOR_ADAPTER:" in body, body)
    expect("ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED:" in body, body)
    expect("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST:" in body, body)
    expect("STRIPE_WEBHOOK_SECRET:" in body and "CLOUDFLARE_API_TOKEN:" in body and "CLOUDFLARE_API_TOKEN_REF:" in body and "CHUTES_API_KEY:" in body, body)
    expect("ARCLINK_SQLITE_JOURNAL_MODE: ${ARCLINK_SQLITE_JOURNAL_MODE:-DELETE}" in body, body)
    expect("QMD_MCP_HOST_PORT:" in body, body)
    expect("QMD_MCP_CONTAINER_PORT:" in body, body)
    expect("QMD_MCP_LOOPBACK_PORT:" in body, body)
    expect("ARCLINK_DOCKER_AGENT_HOME_ROOT:" in body, body)
    expect("ARCLINK_DOCKER_HOST_PRIV_DIR:" in body, body)
    expect("host.docker.internal:host-gateway" in body, body)
    expect("ARCLINK_DOCKER_UID: ${ARCLINK_DOCKER_UID:-1000}" in body, body)
    expect("ARCLINK_DOCKER_GID: ${ARCLINK_DOCKER_GID:-1000}" in body, body)
    expect("ARCLINK_UID: ${ARCLINK_DOCKER_UID:-1000}" in body, body)
    expect("ARCLINK_GID: ${ARCLINK_DOCKER_GID:-1000}" in body, body)
    expect("ARCLINK_HEALTH_WATCH_HEALTH_CMD: ./bin/docker-health.sh" in body, body)
    expect("POSTGRES_PASSWORD:?run ./deploy.sh control bootstrap first" in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD:?run ./deploy.sh control bootstrap first" in body, body)
    expect("ARCLINK_OPERATOR_NEXTCLOUD_DB_PASSWORD:?run ./deploy.sh control bootstrap first" in body, body)
    expect("ARCLINK_OPERATOR_NEXTCLOUD_ADMIN_PASSWORD:?run ./deploy.sh control bootstrap first" in body, body)
    expect("ARCLINK_AGENT_USER_HELPER_TOKEN:?run ./deploy.sh control bootstrap first" in body, body)
    expect("ARCLINK_AGENT_PROCESS_HELPER_TOKEN:?run ./deploy.sh control bootstrap first" in body, body)
    expect("ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN:?run ./deploy.sh control bootstrap first" in body, body)
    expect("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN:?run ./deploy.sh control bootstrap first" in body, body)
    expect("POSTGRES_PASSWORD:-change-me" not in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD:-change-me" not in body, body)
    for service in (
        "postgres:",
        "redis:",
        "nextcloud:",
        "arclink-mcp:",
        "qmd-mcp:",
        "control-operator-hermes-setup:",
        "control-operator-qmd-mcp:",
        "control-operator-hermes-gateway:",
        "control-operator-terminal-tmux:",
        "control-operator-hermes-dashboard:",
        "control-operator-vault-watch:",
        "control-operator-memory-synth:",
        "control-operator-nextcloud-db:",
        "control-operator-nextcloud-redis:",
        "control-operator-nextcloud:",
        "notion-webhook:",
        "control-api:",
        "control-llm-router:",
        "control-web:",
        "control-ingress:",
        "control-provisioner:",
        "control-action-worker:",
        "migration-capture-helper:",
        "vault-watch:",
        "agent-supervisor-broker:",
        "operator-upgrade-broker:",
        "agent-user-helper:",
        "agent-process-helper:",
        "agent-supervisor:",
        "ssot-batcher:",
        "gateway-exec-broker:",
        "notification-delivery:",
        "arclink-wrapped:",
        "health-watch:",
        "fleet-inventory-worker:",
        "fleet-share-reconcile:",
        "curator-refresh:",
        "qmd-refresh:",
        "pdf-ingest:",
        "memory-synth:",
        "hermes-docs-sync:",
        "quarto-render:",
        "backup:",
    ):
        expect(service in body, f"missing service {service}\n{body}")
    expect("127.0.0.1:${ARCLINK_MCP_PORT:-8282}:8282" in body, body)
    expect("127.0.0.1:${QMD_MCP_PORT:-8181}:8181" in body, body)
    expect("127.0.0.1:${NEXTCLOUD_PORT:-18080}:80" in body, body)
    expect("127.0.0.1:${ARCLINK_API_PORT:-8900}:8900" in body, body)
    expect("127.0.0.1:${ARCLINK_LLM_ROUTER_PORT:-8090}:8090" in body, body)
    expect("127.0.0.1:${ARCLINK_WEB_PORT:-3000}:8080" in body, body)
    expect("python/arclink_hosted_api.py" in body and "cd web && npm run start" in body, body)
    expect('"uvicorn", "arclink_llm_router:app"' in body, body)
    expect("ARCLINK_DB_PATH: /home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3" in body, body)
    expect("ARCLINK_LLM_ROUTER_CHUTES_API_KEY:" in body and "ARCLINK_LLM_ROUTER_CHUTES_BASE_URL:" in body, body)
    traefik_config = read("config/traefik-control.yaml")
    expect("traefik.http.routers." not in body and "traefik.enable=true" not in body, body)
    expect('rule: "PathPrefix(`/v1`)"' in traefik_config, traefik_config)
    llm_router_block = extract(body, "  control-llm-router:", "\n\n")
    for pool_env in (
        "ARCLINK_LLM_ROUTER_UPSTREAM_CONNECT_TIMEOUT_SECONDS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_READ_TIMEOUT_SECONDS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_WRITE_TIMEOUT_SECONDS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_POOL_TIMEOUT_SECONDS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_MAX_CONNECTIONS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_MAX_KEEPALIVE_CONNECTIONS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_KEEPALIVE_EXPIRY_SECONDS",
        "ARCLINK_LLM_ROUTER_UPSTREAM_WARMUP_ENABLED",
    ):
        expect(pool_env in llm_router_block, f"missing router pool env {pool_env}\n{llm_router_block}")
    expect("<<: *arclink-control-secret-env" not in llm_router_block, llm_router_block)
    expect("STRIPE_SECRET_KEY:" not in llm_router_block and "CLOUDFLARE_API_TOKEN:" not in llm_router_block, llm_router_block)
    expect("python/arclink_sovereign_worker.py" in body and "control-provisioner" in body, body)
    expect("python/arclink_action_worker.py" in body and "control-action-worker" in body, body)
    expect(
        '["./bin/docker-job-loop.sh", "notification-delivery", "1", "./bin/arclink-notification-delivery.sh"]'
        in body,
        "public-channel agent turns should stay on the broker-client delivery worker with a low-latency poll",
    )
    expect(
        '["python3", "python/arclink_gateway_exec_broker.py"]' in body,
        "public-channel gateway exec should be brokered by a dedicated service",
    )
    expect(
        '["python3", "python/arclink_agent_supervisor_broker.py"]' in body,
        "Docker-mode agent dashboard network/proxy work should be brokered by a dedicated service",
    )
    expect(
        '["python3", "python/arclink_operator_upgrade_broker.py"]' in body,
        "Docker-mode queued operator upgrades should be brokered by a dedicated service",
    )
    expect(
        '["python3", "python/arclink_migration_capture_helper.py"]' in body,
        "Docker-mode Pod migration capture should be brokered by a dedicated root helper",
    )
    expect(
        '["python3", "python/arclink_agent_user_helper.py"]' in body,
        "Docker-mode agent user/home setup should be brokered by a dedicated root helper",
    )
    expect(
        '["./bin/docker-job-loop.sh", "arclink-wrapped", "300", "./bin/arclink-wrapped.sh", "--json"]'
        in body,
        "ArcLink Wrapped should run as its own named job-loop service",
    )
    expect(
        '["./bin/docker-job-loop.sh", "fleet-inventory-worker", "30", "python3", "python/arclink_fleet_inventory_worker.py", "--once", "--json", "--notify"]'
        in body,
        "fleet inventory worker should run as a low-latency job-loop service",
    )
    expect("./arclink-priv/secrets/ssh:/root/.ssh" not in body, body)
    expect("./arclink-priv/secrets/ssh:/home/arclink/.ssh" in body, body)
    expect("ARCLINK_LOCAL_FLEET_SSH_USER: ${ARCLINK_LOCAL_FLEET_SSH_USER:-arclink}" in body, body)
    expect("ARCLINK_CONTROL_HOST_MAX_ARCPOD_SLOTS: ${ARCLINK_CONTROL_HOST_MAX_ARCPOD_SLOTS:-2}" in body, body)
    expect("ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED: ${ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED:-0}" in body, body)
    expect("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST: ${ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST:-}" in body, body)
    expect(
        "ARCLINK_FLEET_SSH_KEY_PATH: ${ARCLINK_FLEET_SSH_KEY_PATH:-/home/arclink/arclink/arclink-priv/secrets/ssh/id_ed25519}"
        in body,
        body,
    )
    expect("${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}:${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}" in body, body)
    expect("${ARCLINK_FLEET_SHARE_HUB_ROOT:-/arcdata/captains}:${ARCLINK_FLEET_SHARE_HUB_ROOT:-/arcdata/captains}" in body, body)
    expect("ARCLINK_AGENT_SERVICE_MANAGER: docker-supervisor" in body, body)
    expect("ARCLINK_DOCKER_NETWORK: ${ARCLINK_DOCKER_NETWORK:-arclink_default}" in body, body)
    expect("ARCLINK_DOCKER_SOCKET_GID: ${ARCLINK_DOCKER_SOCKET_GID:-0}" in body, body)
    expect("Intentional trusted-host boundary" in body, body)
    expect(
        HOST_REPO_BIND_RO in body
        and "available read-only at its host path" in body
        and "without overlaying /home/arclink/arclink" in body,
        "agent process services must keep the live checkout available read-only without hiding split private mounts",
    )
    expect(
        "\n      - .:/home/arclink/arclink\n" not in body,
        "curator-refresh must not overlay the image repo with a host checkout that may contain an arclink-priv symlink",
    )
    socket_mounts = re.findall(r"^\s+- /var/run/docker\.sock:/var/run/docker\.sock(?::ro)?\s*$", body, re.MULTILINE)
    expect(len(socket_mounts) == 4, f"unexpected Docker socket mount count: {socket_mounts}\n{body}")
    expect(body.count("/var/run/docker.sock:/var/run/docker.sock:ro") == 0, body)
    expect(body.count("/var/run/docker.sock:/var/run/docker.sock\n") == 4, body)
    expect(body.count("group_add:\n      - ${ARCLINK_DOCKER_SOCKET_GID:-0}") == 4, body)
    for socket_service in ("deployment-exec-broker", "agent-supervisor-broker", "operator-upgrade-broker", "gateway-exec-broker"):
        block = extract(body, f"  {socket_service}:", "\n\n")
        expect("group_add:" in block, f"{socket_service} missing socket gid group_add\n{block}")
    control_ingress_block = extract(body, "  control-ingress:", "\n\n")
    expect("--providers.file.filename=/etc/traefik/dynamic/arclink-control.yaml" in control_ingress_block, control_ingress_block)
    expect("--providers.file.watch=false" in control_ingress_block, control_ingress_block)
    expect("--providers.docker" not in control_ingress_block, control_ingress_block)
    expect("/var/run/docker.sock" not in control_ingress_block, control_ingress_block)
    expect("group_add:" not in control_ingress_block, control_ingress_block)
    expect("./config/traefik-control.yaml:/etc/traefik/dynamic/arclink-control.yaml:ro" in control_ingress_block, control_ingress_block)
    expect("${ARCLINK_CONTROL_PRIVATE_BIND_HOST:-127.0.0.1}:${ARCLINK_CONTROL_PRIVATE_HTTP_PORT:-13001}:8080" in control_ingress_block, control_ingress_block)
    for backend in ("notion-webhook", "control-web", "control-api", "control-llm-router"):
        expect(f"{backend}:" in control_ingress_block, control_ingress_block)
    for socket_service in (
        "control-ingress",
        "deployment-exec-broker",
        "migration-capture-helper",
        "control-provisioner",
        "agent-supervisor-broker",
        "operator-upgrade-broker",
        "agent-user-helper",
        "gateway-exec-broker",
        "notification-delivery",
        "curator-refresh",
    ):
        block = extract(body, f"  {socket_service}:", "\n\n")
        expect("cap_drop:\n      - ALL" in block, f"{socket_service} should drop Linux capabilities\n{block}")
    control_provisioner_block = extract(body, "  control-provisioner:", "\n\n")
    expect("/var/run/docker.sock" not in control_provisioner_block, control_provisioner_block)
    expect("group_add:" not in control_provisioner_block, control_provisioner_block)
    expect("ARCLINK_DEPLOYMENT_EXEC_BROKER_URL" in control_provisioner_block, control_provisioner_block)
    control_action_worker_block = extract(body, "  control-action-worker:", "\n\n")
    expect("/var/run/docker.sock" not in control_action_worker_block, control_action_worker_block)
    expect("group_add:" not in control_action_worker_block, control_action_worker_block)
    expect("ARCLINK_DEPLOYMENT_EXEC_BROKER_URL" in control_action_worker_block, control_action_worker_block)
    expect("ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN" in control_action_worker_block, control_action_worker_block)
    expect("ARCLINK_MIGRATION_CAPTURE_HELPER_URL" in control_action_worker_block, control_action_worker_block)
    expect("ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN" in control_action_worker_block, control_action_worker_block)
    expect("ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE" in control_action_worker_block, control_action_worker_block)
    expect("deployment-exec-broker:" in control_action_worker_block, control_action_worker_block)
    expect("migration-capture-helper:" in control_action_worker_block, control_action_worker_block)
    deployment_broker_block = extract(body, "  deployment-exec-broker:", "\n\n")
    expect("/var/run/docker.sock:/var/run/docker.sock" in deployment_broker_block, deployment_broker_block)
    expect("python/arclink_deployment_exec_broker.py" in deployment_broker_block, deployment_broker_block)
    expect("ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN" in deployment_broker_block, deployment_broker_block)
    notification_delivery_block = extract(body, "  notification-delivery:", "\n\n")
    expect("/var/run/docker.sock" not in notification_delivery_block, notification_delivery_block)
    expect("group_add:" not in notification_delivery_block, notification_delivery_block)
    expect("ARCLINK_GATEWAY_EXEC_BROKER_URL" in notification_delivery_block, notification_delivery_block)
    gateway_broker_block = extract(body, "  gateway-exec-broker:", "\n\n")
    expect("/var/run/docker.sock:/var/run/docker.sock" in gateway_broker_block, gateway_broker_block)
    expect("python/arclink_gateway_exec_broker.py" in gateway_broker_block, gateway_broker_block)
    expect("ARCLINK_GATEWAY_EXEC_BROKER_TOKEN" in gateway_broker_block, gateway_broker_block)
    curator_refresh_block = extract(body, "  curator-refresh:", "\n\n")
    expect("/var/run/docker.sock" not in curator_refresh_block, curator_refresh_block)
    expect("group_add:" not in curator_refresh_block, curator_refresh_block)
    expect(re.search(rf"^\s+- {re.escape(HOST_REPO_BIND_RO)}\s*$", curator_refresh_block, re.MULTILINE), curator_refresh_block)
    expect(not re.search(rf"^\s+- {re.escape(HOST_REPO_BIND)}\s*$", curator_refresh_block, re.MULTILINE), curator_refresh_block)
    control_action_worker_block = extract(body, "  control-action-worker:", "\n\n")
    expect('user: "0:0"' not in control_action_worker_block, f"control-action-worker should no longer own the root migration boundary\n{control_action_worker_block}")
    expect(
        "migration-capture-helper" in control_action_worker_block and "operator opt-in" in control_action_worker_block,
        f"control-action-worker must delegate Pod migration capture to the helper\n{control_action_worker_block}",
    )
    migration_helper_block = extract(body, "  migration-capture-helper:", "\n\n")
    expect('user: "0:0"' in migration_helper_block, f"migration-capture-helper root boundary must stay explicit\n{migration_helper_block}")
    expect("cap_drop:\n      - ALL" in migration_helper_block, migration_helper_block)
    expect("/var/run/docker.sock" not in migration_helper_block, migration_helper_block)
    expect("group_add:" not in migration_helper_block, migration_helper_block)
    expect("python/arclink_migration_capture_helper.py" in migration_helper_block, migration_helper_block)
    expect("ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN" in migration_helper_block, migration_helper_block)
    agent_user_helper_block = extract(body, "  agent-user-helper:", "\n\n")
    expect('user: "0:0"' in agent_user_helper_block, f"agent-user-helper root boundary must stay explicit\n{agent_user_helper_block}")
    expect("cap_drop:\n      - ALL" in agent_user_helper_block, agent_user_helper_block)
    expect(compose_list_values(agent_user_helper_block, "cap_add") == ["CHOWN", "DAC_OVERRIDE", "FOWNER"], agent_user_helper_block)
    expect("/var/run/docker.sock" not in agent_user_helper_block, agent_user_helper_block)
    expect("group_add:" not in agent_user_helper_block, agent_user_helper_block)
    expect("python/arclink_agent_user_helper.py" in agent_user_helper_block, agent_user_helper_block)
    expect("ARCLINK_AGENT_USER_HELPER_TOKEN" in agent_user_helper_block, agent_user_helper_block)
    expect("/home/arclink/arclink/arclink-priv/state/docker/users" in agent_user_helper_block, agent_user_helper_block)
    expect("/home/arclink/arclink/arclink-priv/vault" not in agent_user_helper_block, agent_user_helper_block)
    expect("/home/arclink/arclink/arclink-priv/secrets" not in agent_user_helper_block, agent_user_helper_block)
    agent_process_helper_block = extract(body, "  agent-process-helper:", "\n\n")
    expect('user: "0:0"' in agent_process_helper_block, f"agent-process-helper root boundary must stay explicit\n{agent_process_helper_block}")
    expect("cap_drop:\n      - ALL" in agent_process_helper_block, agent_process_helper_block)
    expect("/var/run/docker.sock" not in agent_process_helper_block, agent_process_helper_block)
    expect("group_add:" not in agent_process_helper_block, agent_process_helper_block)
    expect("python/arclink_agent_process_helper.py" in agent_process_helper_block, agent_process_helper_block)
    expect("ARCLINK_AGENT_PROCESS_HELPER_TOKEN" in agent_process_helper_block, agent_process_helper_block)
    expect(re.search(rf"^\s+- {re.escape(HOST_REPO_BIND_RO)}\s*$", agent_process_helper_block, re.MULTILINE), agent_process_helper_block)
    expect(not re.search(rf"^\s+- {re.escape(HOST_REPO_BIND)}\s*$", agent_process_helper_block, re.MULTILINE), agent_process_helper_block)
    agent_supervisor_block = extract(body, "  agent-supervisor:", "\n\n")
    expect('user: "0:0"' not in agent_supervisor_block, f"agent-supervisor should no longer own the root process boundary\n{agent_supervisor_block}")
    expect("/var/run/docker.sock" not in agent_supervisor_block, agent_supervisor_block)
    expect("group_add:" not in agent_supervisor_block, agent_supervisor_block)
    expect("ARCLINK_AGENT_USER_HELPER_URL" in agent_supervisor_block, agent_supervisor_block)
    expect("ARCLINK_AGENT_USER_HELPER_TOKEN" in agent_supervisor_block, agent_supervisor_block)
    expect("ARCLINK_AGENT_PROCESS_HELPER_URL" in agent_supervisor_block, agent_supervisor_block)
    expect("ARCLINK_AGENT_PROCESS_HELPER_TOKEN" in agent_supervisor_block, agent_supervisor_block)
    expect("ARCLINK_OPERATOR_UPGRADE_BROKER_URL" in agent_supervisor_block, agent_supervisor_block)
    expect("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN" in agent_supervisor_block, agent_supervisor_block)
    expect(
        "agent-user-helper" in agent_supervisor_block
        and "agent-process-helper" in agent_supervisor_block
        and "agent-supervisor-broker" in agent_supervisor_block
        and "operator-upgrade-broker" in agent_supervisor_block
        and "command-specific helpers/brokers" in agent_supervisor_block,
        f"agent-supervisor delegation boundary must be locally justified\n{agent_supervisor_block}",
    )
    expect(re.search(rf"^\s+- {re.escape(HOST_REPO_BIND_RO)}\s*$", agent_supervisor_block, re.MULTILINE), agent_supervisor_block)
    expect(not re.search(rf"^\s+- {re.escape(HOST_REPO_BIND)}\s*$", agent_supervisor_block, re.MULTILINE), agent_supervisor_block)
    agent_supervisor_broker_block = extract(body, "  agent-supervisor-broker:", "\n\n")
    expect("/var/run/docker.sock:/var/run/docker.sock" in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect("python/arclink_agent_supervisor_broker.py" in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN" in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect("<<: *arclink-env" not in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect("./arclink-priv/config:/home/arclink/arclink/arclink-priv/config" not in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect("./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" not in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect("arclink-priv/secrets/container" not in agent_supervisor_broker_block, agent_supervisor_broker_block)
    expect(
        "network/proxy sidecar authority" in agent_supervisor_broker_block
        and "./arclink-priv/state/docker/agent-supervisor-broker:/home/arclink/arclink/arclink-priv/state/docker/agent-supervisor-broker" in agent_supervisor_broker_block
        and not re.search(rf"^\s+- {re.escape(HOST_REPO_BIND)}(?::ro)?\s*$", agent_supervisor_broker_block, re.MULTILINE),
        f"agent-supervisor-broker must keep only a narrow incident mount and no host repo bind after the operator upgrade split\n{agent_supervisor_broker_block}",
    )
    agent_supervisor_broker_source = read("python/arclink_agent_supervisor_broker.py")
    expect("run_operator_upgrade" not in agent_supervisor_broker_source, agent_supervisor_broker_source)
    expect("run_pin_upgrade" not in agent_supervisor_broker_source, agent_supervisor_broker_source)
    operator_upgrade_broker_block = extract(body, "  operator-upgrade-broker:", "\n\n")
    expect("/var/run/docker.sock:/var/run/docker.sock" in operator_upgrade_broker_block, operator_upgrade_broker_block)
    expect("python/arclink_operator_upgrade_broker.py" in operator_upgrade_broker_block, operator_upgrade_broker_block)
    expect("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN" in operator_upgrade_broker_block, operator_upgrade_broker_block)
    expect(
        "queued" in operator_upgrade_broker_block
        and "operator upgrade execution" in operator_upgrade_broker_block
        and 'user: "0:0"' in operator_upgrade_broker_block
        and compose_list_values(operator_upgrade_broker_block, "cap_add") == ["DAC_OVERRIDE"]
        and re.search(rf"^\s+- {re.escape(HOST_REPO_BIND)}\s*$", operator_upgrade_broker_block, re.MULTILINE)
        and HOST_REPO_BIND_RO not in operator_upgrade_broker_block,
        f"operator-upgrade-broker must own the explicit writable host repo exception\n{operator_upgrade_broker_block}",
    )
    wrapped_block = extract(body, "  arclink-wrapped:", "\n\n")
    expect("/var/run/docker.sock" not in wrapped_block, wrapped_block)
    fleet_inventory_block = extract(body, "  fleet-inventory-worker:", "\n\n")
    expect("/var/run/docker.sock" not in fleet_inventory_block, fleet_inventory_block)
    fleet_share_reconcile_block = extract(body, "  fleet-share-reconcile:", "\n\n")
    expect("cap_drop:\n      - ALL" in fleet_share_reconcile_block, fleet_share_reconcile_block)
    expect("/var/run/docker.sock" not in fleet_share_reconcile_block, fleet_share_reconcile_block)
    expect("group_add:" not in fleet_share_reconcile_block, fleet_share_reconcile_block)
    expect("arclink-priv/secrets/container" not in fleet_share_reconcile_block, fleet_share_reconcile_block)
    expect("arclink-priv/vault" not in fleet_share_reconcile_block, fleet_share_reconcile_block)
    expect("*arclink-control-secret-env" not in fleet_share_reconcile_block, fleet_share_reconcile_block)
    llm_router_block = extract(body, "  control-llm-router:", "\n\n")
    expect("/var/run/docker.sock" not in llm_router_block and "group_add:" not in llm_router_block, llm_router_block)
    expect(
        "/var/run/docker.sock:/var/run/docker.sock" in body,
        "dashboard and operator-upgrade brokers must intentionally mount the Docker socket for their split authority",
    )
    expect("ARCLINK_AGENT_DASHBOARD_PROXY_PORT_RANGE" not in body, body)
    expect("./bin/docker-agent-supervisor.sh" in body, body)
    print("PASS test_compose_defines_full_stack_services")


def test_control_ingress_uses_static_traefik_config_without_docker_socket() -> None:
    body = read("compose.yaml")
    block = extract(body, "  control-ingress:", "\n\n")
    expect("image: ${ARCLINK_TRAEFIK_IMAGE:-docker.io/library/traefik:v3}" in block, block)
    expect("cap_drop:\n      - ALL" in block, block)
    expect("--providers.file.filename=/etc/traefik/dynamic/arclink-control.yaml" in block, block)
    expect("--providers.file.watch=false" in block, block)
    expect("--providers.docker" not in block, block)
    expect("/var/run/docker.sock" not in block, block)
    expect("group_add:" not in block, block)
    expect("./config/traefik-control.yaml:/etc/traefik/dynamic/arclink-control.yaml:ro" in block, block)
    expect("127.0.0.1:${ARCLINK_WEB_PORT:-3000}:8080" in block, block)
    expect("${ARCLINK_CONTROL_PRIVATE_BIND_HOST:-127.0.0.1}:${ARCLINK_CONTROL_PRIVATE_HTTP_PORT:-13001}:8080" in block, block)
    for backend in ("notion-webhook", "control-web", "control-api", "control-llm-router"):
        expect(f"{backend}:\n        condition: service_healthy" in block, block)
    for removed_label in (
        "traefik.enable=true",
        "traefik.http.routers.arclink-control-notion",
        "traefik.http.routers.arclink-control-api",
        "traefik.http.routers.arclink-control-llm-router",
        "traefik.http.routers.arclink-control-web",
    ):
        expect(removed_label not in body, f"stale Docker-provider Traefik label remains: {removed_label}\n{body}")
    print("PASS test_control_ingress_uses_static_traefik_config_without_docker_socket")


def test_compose_high_authority_brokers_and_helpers_are_scoped_off_default_network() -> None:
    blocks = compose_service_blocks()
    network_defs = compose_network_definitions()
    request_networks = {
        "deployment-exec-broker-net": {
            "deployment-exec-broker",
            "control-provisioner",
            "control-action-worker",
        },
        "migration-capture-helper-net": {
            "migration-capture-helper",
            "control-action-worker",
        },
        "agent-user-helper-net": {
            "agent-user-helper",
            "agent-supervisor",
        },
        "agent-process-helper-net": {
            "agent-process-helper",
            "agent-supervisor",
        },
        "agent-supervisor-broker-net": {
            "agent-supervisor-broker",
            "agent-supervisor",
        },
        "operator-upgrade-broker-net": {
            "operator-upgrade-broker",
            "agent-supervisor",
            "control-operator-hermes-gateway",
            "control-operator-hermes-dashboard",
        },
        "gateway-exec-broker-net": {
            "gateway-exec-broker",
            "notification-delivery",
            "control-operator-hermes-gateway",
            "control-operator-hermes-dashboard",
        },
    }
    egress_networks = {
        "agent-process-helper-egress-net": {"agent-process-helper"},
        "operator-upgrade-broker-egress-net": {"operator-upgrade-broker"},
    }

    for network, expected_services in request_networks.items():
        definition = network_defs.get(network)
        expect(isinstance(definition, dict), f"{network} must be declared in compose.yaml networks")
        expect(definition.get("internal") is True, f"{network} must be an internal request network: {definition}")
        attached = {
            service
            for service, block in blocks.items()
            if network in compose_service_networks(block)
        }
        expect(attached == expected_services, f"{network} attached services drifted: {sorted(attached)}")

    for network, expected_services in egress_networks.items():
        definition = network_defs.get(network)
        expect(isinstance(definition, dict), f"{network} must be declared in compose.yaml networks")
        expect(definition.get("internal") is False, f"{network} must stay non-internal for outbound-only runtime work: {definition}")
        attached = {
            service
            for service, block in blocks.items()
            if network in compose_service_networks(block)
        }
        expect(attached == expected_services, f"{network} attached services drifted: {sorted(attached)}")

    high_authority_expected = {
        "deployment-exec-broker": ["deployment-exec-broker-net"],
        "migration-capture-helper": ["migration-capture-helper-net"],
        "agent-user-helper": ["agent-user-helper-net"],
        "agent-process-helper": ["agent-process-helper-net", "agent-process-helper-egress-net"],
        "agent-supervisor-broker": ["agent-supervisor-broker-net"],
        "operator-upgrade-broker": ["operator-upgrade-broker-net", "operator-upgrade-broker-egress-net"],
        "gateway-exec-broker": ["gateway-exec-broker-net"],
    }
    for service, expected in high_authority_expected.items():
        networks = compose_service_networks(blocks[service])
        expect("default" not in networks, f"{service} must not be reachable on the default Compose network: {networks}")
        expect(networks == expected, f"{service} network boundary drifted: expected={expected} actual={networks}")

    caller_expected = {
        "control-provisioner": ["default", "deployment-exec-broker-net"],
        "control-action-worker": ["default", "deployment-exec-broker-net", "migration-capture-helper-net"],
        "agent-supervisor": [
            "default",
            "agent-user-helper-net",
            "agent-process-helper-net",
            "agent-supervisor-broker-net",
            "operator-upgrade-broker-net",
        ],
        "notification-delivery": ["default", "gateway-exec-broker-net"],
        "control-operator-hermes-gateway": ["default", "operator-upgrade-broker-net", "gateway-exec-broker-net"],
        "control-operator-hermes-dashboard": ["default", "operator-upgrade-broker-net", "gateway-exec-broker-net"],
    }
    for service, expected in caller_expected.items():
        networks = compose_service_networks(blocks[service])
        expect(networks == expected, f"{service} caller network boundary drifted: expected={expected} actual={networks}")
    print("PASS test_compose_high_authority_brokers_and_helpers_are_scoped_off_default_network")


def test_compose_high_authority_services_receive_trusted_host_acceptance_gate() -> None:
    blocks = compose_service_blocks()
    for service in HIGH_AUTHORITY_SERVICES:
        block = blocks.get(service)
        expect(block is not None, f"{service} service block missing")
        assert block is not None
        expected = f"{TRUSTED_HOST_RISK_ENV}: ${{{TRUSTED_HOST_RISK_ENV}:-}}"
        expect(expected in block, f"{service} missing trusted-host residual-risk acceptance env\n{block}")
    print("PASS test_compose_high_authority_services_receive_trusted_host_acceptance_gate")


def test_high_authority_helpers_default_to_loopback_outside_compose() -> None:
    modules = [
        (
            "deployment-exec-broker",
            "arclink_deployment_exec_broker.py",
            "ARCLINK_DEPLOYMENT_EXEC_BROKER_HOST",
            "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN",
        ),
        (
            "migration-capture-helper",
            "arclink_migration_capture_helper.py",
            "ARCLINK_MIGRATION_CAPTURE_HELPER_HOST",
            "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN",
        ),
        (
            "agent-user-helper",
            "arclink_agent_user_helper.py",
            "ARCLINK_AGENT_USER_HELPER_HOST",
            "ARCLINK_AGENT_USER_HELPER_TOKEN",
        ),
        (
            "agent-process-helper",
            "arclink_agent_process_helper.py",
            "ARCLINK_AGENT_PROCESS_HELPER_HOST",
            "ARCLINK_AGENT_PROCESS_HELPER_TOKEN",
        ),
        (
            "agent-supervisor-broker",
            "arclink_agent_supervisor_broker.py",
            "ARCLINK_AGENT_SUPERVISOR_BROKER_HOST",
            "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN",
        ),
        (
            "operator-upgrade-broker",
            "arclink_operator_upgrade_broker.py",
            "ARCLINK_OPERATOR_UPGRADE_BROKER_HOST",
            "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN",
        ),
        (
            "gateway-exec-broker",
            "arclink_gateway_exec_broker.py",
            "ARCLINK_GATEWAY_EXEC_BROKER_HOST",
            "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN",
        ),
    ]
    blocks = compose_service_blocks()
    old_env = os.environ.copy()
    try:
        os.environ[TRUSTED_HOST_RISK_ENV] = TRUSTED_HOST_RISK_ACCEPTED
        for service, filename, host_env, token_env in modules:
            module = load_python_module(PYTHON_DIR / filename, f"{filename.replace('.', '_')}_loopback_default_test")
            expect(module.DEFAULT_HOST == "127.0.0.1", f"{service} direct-run DEFAULT_HOST must be loopback")

            os.environ[token_env] = f"{service}-test-token"
            os.environ.pop(host_env, None)
            serve_calls: list[tuple[str, int]] = []
            module.serve = lambda *, host, port: serve_calls.append((str(host), int(port)))
            module.main([])
            expect(serve_calls == [("127.0.0.1", module.DEFAULT_PORT)], f"{service} direct-run default bind drifted: {serve_calls}")

            os.environ[host_env] = "0.0.0.0"
            serve_calls.clear()
            module.main([])
            expect(serve_calls == [("0.0.0.0", module.DEFAULT_PORT)], f"{service} env host override must still work: {serve_calls}")

            serve_calls.clear()
            module.main(["--host", "127.0.0.2"])
            expect(serve_calls == [("127.0.0.2", module.DEFAULT_PORT)], f"{service} CLI host override must still work: {serve_calls}")

            block = blocks.get(service)
            expect(block is not None, f"{service} service block missing")
            assert block is not None
            expect(f"{host_env}: 0.0.0.0" in block, f"{service} Compose env must explicitly opt into internal broad bind\n{block}")
            expect("http://127.0.0.1:" in block and "/health" in block, f"{service} healthcheck must stay loopback-local\n{block}")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_high_authority_helpers_default_to_loopback_outside_compose")


def test_trusted_host_acceptance_gate_blocks_brokers_and_helpers_before_work() -> None:
    modules = [
        ("deployment-exec-broker", "arclink_deployment_exec_broker.py", "run_deployment_exec_request", "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN"),
        ("migration-capture-helper", "arclink_migration_capture_helper.py", "run_migration_capture_request", "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN"),
        ("agent-user-helper", "arclink_agent_user_helper.py", "run_agent_user_helper_request", "ARCLINK_AGENT_USER_HELPER_TOKEN"),
        ("agent-process-helper", "arclink_agent_process_helper.py", "run_agent_process_helper_request", "ARCLINK_AGENT_PROCESS_HELPER_TOKEN"),
        ("agent-supervisor-broker", "arclink_agent_supervisor_broker.py", "run_agent_supervisor_request", "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN"),
        ("operator-upgrade-broker", "arclink_operator_upgrade_broker.py", "run_operator_upgrade_request", "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN"),
        ("gateway-exec-broker", "arclink_gateway_exec_broker.py", "run_gateway_exec_request", "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN"),
    ]
    old_env = os.environ.copy()
    try:
        os.environ.pop(TRUSTED_HOST_RISK_ENV, None)
        for _service, _filename, _run_func, token_env in modules:
            os.environ[token_env] = "test-token"
        for service, filename, run_func, _token_env in modules:
            module = load_python_module(PYTHON_DIR / filename, f"{filename.replace('.', '_')}_trusted_host_gate_test")
            serve_calls: list[tuple[str, int]] = []
            module.serve = lambda *, host, port: serve_calls.append((str(host), int(port)))
            try:
                module.main([])
            except SystemExit as exc:
                message = str(exc)
            else:
                raise AssertionError(f"{service} main should fail closed without trusted-host acceptance")
            expect("GAP-019" in message and TRUSTED_HOST_RISK_ENV in message and service in message, message)
            expect(serve_calls == [], f"{service} bound its HTTP listener without trusted-host acceptance: {serve_calls}")
            ok, payload = getattr(module, run_func)({})
            expect(ok is False, f"{service} direct request unexpectedly passed without trusted-host acceptance: {payload}")
            expect("GAP-019" in str(payload) and TRUSTED_HOST_RISK_ENV in str(payload), f"{service}: {payload}")

        os.environ[TRUSTED_HOST_RISK_ENV] = "false"
        boundary = load_python_module(PYTHON_DIR / "arclink_boundary.py", "arclink_boundary_trusted_host_gate_test")
        try:
            boundary.require_docker_trusted_host_risk_accepted(service="test-service")
        except RuntimeError as exc:
            expect("GAP-019" in str(exc) and TRUSTED_HOST_RISK_ENV in str(exc), str(exc))
        else:
            raise AssertionError("false trusted-host acceptance value should fail closed")

        os.environ[TRUSTED_HOST_RISK_ENV] = TRUSTED_HOST_RISK_ACCEPTED
        boundary.require_docker_trusted_host_risk_accepted(service="test-service")
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_trusted_host_acceptance_gate_blocks_brokers_and_helpers_before_work")


def test_control_ingress_static_routes_cover_control_api_web_llm_and_notion() -> None:
    body = read("config/traefik-control.yaml")
    expected_routes = {
        "arclink-control-notion": {
            "rule": 'PathPrefix(`/notion/webhook`)',
            "priority": "200",
            "url": "http://notion-webhook:8283",
        },
        "arclink-control-llm-router": {
            "rule": 'PathPrefix(`/v1`)',
            "priority": "180",
            "url": "http://control-llm-router:8090",
        },
        "arclink-control-api": {
            "rule": 'PathPrefix(`/api`)',
            "priority": "150",
            "url": "http://control-api:8900",
        },
        "arclink-control-web": {
            "rule": 'PathPrefix(`/`)',
            "priority": "1",
            "url": "http://control-web:3000",
        },
    }
    expect("http:\n  routers:" in body and "\n  services:" in body, body)
    service_section_start = body.index("\n  services:")
    routers_text = body[:service_section_start]
    services_text = body[service_section_start:]

    def yaml_child_block(text: str, marker: str, markers: list[str]) -> str:
        start = text.index(marker)
        ends = [text.find(candidate, start + len(marker)) for candidate in markers if candidate != marker]
        ends = [index for index in ends if index != -1]
        end = min(ends) if ends else len(text)
        return text[start:end]

    route_markers = [f"    {name}:\n" for name in expected_routes]
    for route, expected in expected_routes.items():
        route_block = yaml_child_block(routers_text, f"    {route}:\n", route_markers)
        expect(f'rule: "{expected["rule"]}"' in route_block, route_block)
        expect("entryPoints:\n        - web" in route_block, route_block)
        expect(f"priority: {expected['priority']}" in route_block, route_block)
        expect(f"service: {route}" in route_block, route_block)
        service_block = yaml_child_block(services_text, f"    {route}:\n", route_markers)
        expect(f'url: "{expected["url"]}"' in service_block, service_block)
    priorities = [200, 180, 150, 1]
    expect(priorities == sorted(priorities, reverse=True), "Control ingress route priorities must stay descending")
    print("PASS test_control_ingress_static_routes_cover_control_api_web_llm_and_notion")


def test_agent_user_helper_root_boundary_uses_explicit_minimum_capabilities() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("agent-user-helper")
    expect(block is not None, "agent-user-helper service block missing")
    assert block is not None
    expect('user: "0:0"' in block, f"agent-user-helper root boundary must stay explicit\n{block}")
    expect("/var/run/docker.sock" not in block, block)
    expect("group_add:" not in block, block)
    expect(compose_list_values(block, "cap_drop") == ["ALL"], block)
    expect(compose_list_values(block, "cap_add") == ["CHOWN", "DAC_OVERRIDE", "FOWNER"], block)
    expect(compose_capability_boundary(block) == "drop_all_add_CHOWN_DAC_OVERRIDE_FOWNER", block)

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "agent-user-helper"),
        None,
    )
    expect(isinstance(row, dict), "agent-user-helper inventory row missing")
    assert isinstance(row, dict)
    boundary = row.get("compose_boundary")
    expect(isinstance(boundary, dict), f"agent-user-helper inventory boundary missing: {row}")
    assert isinstance(boundary, dict)
    expect(
        boundary.get("linux_capabilities") == "drop_all_add_CHOWN_DAC_OVERRIDE_FOWNER",
        f"agent-user-helper inventory must not overclaim all_dropped when cap_add is present: {boundary}",
    )
    controls = row.get("gap_019_q_controls")
    expect(isinstance(controls, dict), f"agent-user-helper must record GAP-019-Q capability controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("allowed_linux_capabilities") == ["CHOWN", "DAC_OVERRIDE", "FOWNER"],
        f"agent-user-helper GAP-019-Q controls must record exact cap_add set: {controls}",
    )
    expect("default Linux capabilities" in str(controls.get("dropped_capability_boundary") or ""), controls)
    print("PASS test_agent_user_helper_root_boundary_uses_explicit_minimum_capabilities")


def test_agent_process_helper_compose_boundary_minimizes_env_and_secret_mounts() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("agent-process-helper")
    expect(block is not None, "agent-process-helper service block missing")
    assert block is not None
    expect('user: "0:0"' in block, f"agent-process-helper root boundary must stay explicit\n{block}")
    expect("<<: *arclink-env" not in block, f"agent-process-helper must not inherit broad app env\n{block}")
    expect(
        "*arclink-control-secret-env" not in block,
        f"agent-process-helper must not inherit control secret env\n{block}",
    )
    for forbidden_env in (
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CHUTES_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "ARCLINK_MEMORY_SYNTH_API_KEY",
        "ARCLINK_SESSION_HASH_PEPPER",
        "ARCLINK_FLEET_ENROLLMENT_SECRET",
    ):
        expect(forbidden_env not in block, f"agent-process-helper leaked broad env key {forbidden_env}\n{block}")
    expect("arclink-priv/secrets/container" not in block, f"agent-process-helper must not mount global container secrets\n{block}")
    expect(
        "/home/arclink/arclink/arclink-priv/secrets" not in block,
        f"agent-process-helper must not receive the global private secrets mount\n{block}",
    )
    for required_line in (
        'ARCLINK_DOCKER_MODE: "1"',
        "ARCLINK_CONTAINER_RUNTIME: docker",
        "ARCLINK_AGENT_SERVICE_MANAGER: docker-supervisor",
        "ARCLINK_REPO_DIR: /home/arclink/arclink",
        "ARCLINK_PRIV_DIR: /home/arclink/arclink/arclink-priv",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR: /home/arclink/arclink/arclink-priv",
        "ARCLINK_DOCKER_AGENT_HOME_ROOT: /home/arclink/arclink/arclink-priv/state/docker/users",
        "RUNTIME_DIR: /opt/arclink/runtime",
        "ARCLINK_AGENT_PROCESS_HELPER_TOKEN:",
        "ARCLINK_AGENT_PROCESS_HELPER_HOST: 0.0.0.0",
        "ARCLINK_AGENT_PROCESS_HELPER_PORT: 8916",
    ):
        expect(required_line in block, f"agent-process-helper missing required minimal env line {required_line}\n{block}")
    for required_mount in (
        "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config",
        "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state",
        "./arclink-priv/vault:/home/arclink/arclink/arclink-priv/vault",
        HOST_REPO_BIND_RO,
    ):
        expect(required_mount in block, f"agent-process-helper missing required non-secret mount {required_mount}\n{block}")

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "agent-process-helper"),
        None,
    )
    expect(isinstance(row, dict), "agent-process-helper inventory row missing")
    assert isinstance(row, dict)
    controls = row.get("gap_019_x_controls")
    expect(isinstance(controls, dict), f"agent-process-helper must record GAP-019-X controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("local_repair_status") == "agent_process_helper_service_env_and_secret_mount_narrowed",
        f"unexpected GAP-019-X status: {controls}",
    )
    expect("broad *arclink-env" in str(controls.get("removed_environment") or ""), controls)
    expect("arclink-priv/secrets/container" in str(controls.get("removed_mounts") or ""), controls)
    preserved = controls.get("preserved_service_env")
    expect(
        isinstance(preserved, list)
        and "ARCLINK_DOCKER_AGENT_HOME_ROOT" in preserved
        and "ARCLINK_AGENT_PROCESS_HELPER_TOKEN" in preserved,
        controls,
    )
    print("PASS test_agent_process_helper_compose_boundary_minimizes_env_and_secret_mounts")


def test_gateway_exec_broker_compose_boundary_minimizes_env_and_private_mounts() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("gateway-exec-broker")
    expect(block is not None, "gateway-exec-broker service block missing")
    assert block is not None
    expect("/var/run/docker.sock:/var/run/docker.sock" in block, block)
    expect("group_add:" in block, block)
    expect("cap_drop:\n      - ALL" in block, block)
    expect("<<: *arclink-env" not in block, f"gateway-exec-broker must not inherit broad app env\n{block}")
    expect(
        "*arclink-control-secret-env" not in block,
        f"gateway-exec-broker must not inherit control secret env\n{block}",
    )
    for forbidden_env in (
        "ARCLINK_CONFIG_FILE",
        "ARCLINK_PRIV_DIR",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        "ARCLINK_DB_PATH",
        "ARCLINK_SESSION_HASH_PEPPER",
        "ARCLINK_FLEET_ENROLLMENT_SECRET",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CHUTES_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "ARCLINK_MEMORY_SYNTH_API_KEY",
    ):
        expect(forbidden_env not in block, f"gateway-exec-broker leaked broad env key {forbidden_env}\n{block}")
    for forbidden_mount in (
        "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config",
        "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state",
        "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets",
        "/home/arclink/arclink/arclink-priv/secrets",
    ):
        expect(forbidden_mount not in block, f"gateway-exec-broker leaked broad private mount {forbidden_mount}\n{block}")
    for required_line in (
        "ARCLINK_STATE_ROOT_BASE: ${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}",
        "ARCLINK_DOCKER_BINARY: ${ARCLINK_DOCKER_BINARY:-docker}",
        "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN:",
        "ARCLINK_GATEWAY_EXEC_BROKER_HOST: 0.0.0.0",
        "ARCLINK_GATEWAY_EXEC_BROKER_PORT: 8911",
    ):
        expect(required_line in block, f"gateway-exec-broker missing required minimal env line {required_line}\n{block}")
    expect(
        "${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}:${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}" in block,
        f"gateway-exec-broker must keep deployment state-root bind for Compose fallback lookup\n{block}",
    )

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "gateway-exec-broker"),
        None,
    )
    expect(isinstance(row, dict), "gateway-exec-broker inventory row missing")
    assert isinstance(row, dict)
    boundary = row.get("compose_boundary")
    expect(isinstance(boundary, dict), f"gateway-exec-broker inventory boundary missing: {row}")
    assert isinstance(boundary, dict)
    expect(boundary.get("private_state_mounts") is False, f"gateway-exec-broker must not overclaim broad private-state mounts: {boundary}")
    expect(boundary.get("deployment_state_root_mount") is True, f"gateway-exec-broker must record deployment state-root bind: {boundary}")
    expect(boundary.get("global_container_secrets_mount") is False, f"gateway-exec-broker must not mount global container secrets: {boundary}")
    expect(boundary.get("inherits_broad_app_env") is False, f"gateway-exec-broker must not inherit broad app env: {boundary}")
    controls = row.get("gap_019_y_controls")
    expect(isinstance(controls, dict), f"gateway-exec-broker must record GAP-019-Y controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("local_repair_status") == "gateway_exec_broker_service_env_and_private_mount_narrowed",
        f"unexpected GAP-019-Y status: {controls}",
    )
    expect("broad *arclink-env" in str(controls.get("removed_environment") or ""), controls)
    removed_mounts = controls.get("removed_mounts")
    expect(
        isinstance(removed_mounts, list)
        and "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config" in removed_mounts
        and "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" in removed_mounts
        and "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets" in removed_mounts,
        controls,
    )
    preserved = controls.get("preserved_service_env")
    expect(
        isinstance(preserved, list)
        and "ARCLINK_STATE_ROOT_BASE" in preserved
        and "ARCLINK_DOCKER_BINARY" in preserved
        and "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN" in preserved,
        controls,
    )
    cli_controls = row.get("gap_019_ah_controls")
    expect(isinstance(cli_controls, dict), f"gateway-exec-broker must record GAP-019-AH controls: {row}")
    assert isinstance(cli_controls, dict)
    expect(
        cli_controls.get("local_repair_status") == "gateway_exec_broker_docker_cli_preflight_added",
        f"unexpected GAP-019-AH status: {cli_controls}",
    )
    expect("Docker CLI" in str(cli_controls.get("control_type") or ""), cli_controls)
    expect(
        "python/arclink_gateway_exec_broker.py:_docker_binary" in str(cli_controls.get("enforcement_paths") or ""),
        cli_controls,
    )
    ay_controls = row.get("gap_019_ay_controls")
    expect(isinstance(ay_controls, dict), f"gateway-exec-broker must record GAP-019-AY controls: {row}")
    assert isinstance(ay_controls, dict)
    expect(
        ay_controls.get("local_repair_status") == "gateway_exec_broker_fallback_config_file_preflight_added",
        f"unexpected GAP-019-AY status: {ay_controls}",
    )
    ay_enforcement = "\n".join(str(item) for item in ay_controls.get("enforcement_paths") or [])
    expect("_preflight_deployment_compose_config_files" in ay_enforcement, ay_controls)
    expect("symlinked config/arclink.env" in str(ay_controls.get("rejected_configuration") or ""), ay_controls)
    expect("before docker compose exec subprocess dispatch" in str(ay_controls.get("fail_closed_boundary") or ""), ay_controls)
    bc_controls = row.get("gap_019_bc_controls")
    expect(isinstance(bc_controls, dict), f"gateway-exec-broker must record GAP-019-BC controls: {row}")
    assert isinstance(bc_controls, dict)
    expect(
        bc_controls.get("local_repair_status") == "gateway_exec_broker_rejected_request_incidents_added",
        f"unexpected GAP-019-BC status: {bc_controls}",
    )
    expect("_broker-incidents/gateway-exec-broker/rejections.jsonl" in str(bc_controls.get("incident_path") or ""), bc_controls)
    bc_enforcement = "\n".join(str(item) for item in bc_controls.get("enforcement_paths") or [])
    expect("_record_rejection_incident" in bc_enforcement and "run_gateway_exec_request" in bc_enforcement, bc_controls)
    expect("bridge payload values" in str(bc_controls.get("redacted_fields") or ""), bc_controls)
    expect("bot tokens" in str(bc_controls.get("redacted_fields") or ""), bc_controls)
    expect("Accepted broker requests" in str(bc_controls.get("fail_closed_boundary") or ""), bc_controls)
    print("PASS test_gateway_exec_broker_compose_boundary_minimizes_env_and_private_mounts")


def test_deployment_exec_broker_compose_boundary_minimizes_env_and_private_mounts() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("deployment-exec-broker")
    expect(block is not None, "deployment-exec-broker service block missing")
    assert block is not None
    expect("/var/run/docker.sock:/var/run/docker.sock" in block, block)
    expect("group_add:" in block, block)
    expect("cap_drop:\n      - ALL" in block, block)
    expect("<<: *arclink-env" not in block, f"deployment-exec-broker must not inherit broad app env\n{block}")
    expect(
        "*arclink-control-secret-env" not in block,
        f"deployment-exec-broker must not inherit control secret env\n{block}",
    )
    for forbidden_env in (
        "ARCLINK_CONFIG_FILE",
        "ARCLINK_PRIV_DIR",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        "ARCLINK_DB_PATH",
        "ARCLINK_SESSION_HASH_PEPPER",
        "ARCLINK_FLEET_ENROLLMENT_SECRET",
        "ARCLINK_DEFAULT_PRICE_ID",
        "ARCLINK_BASE_DOMAIN",
        "ARCLINK_INGRESS_MODE",
        "ARCLINK_MEMORY_SYNTH_API_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CHUTES_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
    ):
        expect(forbidden_env not in block, f"deployment-exec-broker leaked broad env key {forbidden_env}\n{block}")
    for forbidden_mount in (
        "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config",
        "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state",
        "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets",
        "/home/arclink/arclink/arclink-priv/secrets",
    ):
        expect(forbidden_mount not in block, f"deployment-exec-broker leaked broad private mount {forbidden_mount}\n{block}")
    for required_line in (
        "ARCLINK_STATE_ROOT_BASE: ${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}",
        "ARCLINK_FLEET_SHARE_HUB_ROOT: ${ARCLINK_FLEET_SHARE_HUB_ROOT:-/arcdata/captains}",
        "ARCLINK_DOCKER_BINARY: ${ARCLINK_DOCKER_BINARY:-docker}",
        "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN:",
        "ARCLINK_DEPLOYMENT_EXEC_BROKER_HOST: 0.0.0.0",
        "ARCLINK_DEPLOYMENT_EXEC_BROKER_PORT: 8912",
    ):
        expect(required_line in block, f"deployment-exec-broker missing required minimal env line {required_line}\n{block}")
    expect(
        "${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}:${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}" in block,
        f"deployment-exec-broker must keep deployment state-root bind for rendered Compose files\n{block}",
    )
    expect(
        "${ARCLINK_FLEET_SHARE_HUB_ROOT:-/arcdata/captains}:${ARCLINK_FLEET_SHARE_HUB_ROOT:-/arcdata/captains}" in block,
        f"deployment-exec-broker must keep Captain fleet-share hub bind for local hub-backed ArcPods\n{block}",
    )

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "deployment-exec-broker"),
        None,
    )
    expect(isinstance(row, dict), "deployment-exec-broker inventory row missing")
    assert isinstance(row, dict)
    boundary = row.get("compose_boundary")
    expect(isinstance(boundary, dict), f"deployment-exec-broker inventory boundary missing: {row}")
    assert isinstance(boundary, dict)
    expect(boundary.get("private_state_mounts") is False, f"deployment-exec-broker must not overclaim broad private-state mounts: {boundary}")
    expect(boundary.get("deployment_state_root_mount") is True, f"deployment-exec-broker must record deployment state-root bind: {boundary}")
    expect(boundary.get("fleet_share_hub_root_mount") is True, f"deployment-exec-broker must record fleet-share hub root bind: {boundary}")
    expect(boundary.get("global_container_secrets_mount") is False, f"deployment-exec-broker must not mount global container secrets: {boundary}")
    expect(boundary.get("inherits_broad_app_env") is False, f"deployment-exec-broker must not inherit broad app env: {boundary}")
    controls = row.get("gap_019_aa_controls")
    expect(isinstance(controls, dict), f"deployment-exec-broker must record GAP-019-AA controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("local_repair_status") == "deployment_exec_broker_service_env_narrowed",
        f"unexpected GAP-019-AA status: {controls}",
    )
    expect("broad *arclink-env" in str(controls.get("removed_environment") or ""), controls)
    preserved = controls.get("preserved_service_env")
    expect(
        isinstance(preserved, list)
        and "ARCLINK_STATE_ROOT_BASE" in preserved
        and "ARCLINK_FLEET_SHARE_HUB_ROOT" in preserved
        and "ARCLINK_DOCKER_BINARY" in preserved
        and "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN" in preserved,
        controls,
    )
    expect("deployment state-root bind" in str(controls.get("preserved_mounts") or ""), controls)
    expect("fleet-share hub root bind" in str(controls.get("preserved_mounts") or ""), controls)
    expect("writeable Docker socket" in str(controls.get("remaining_gate") or ""), controls)
    print("PASS test_deployment_exec_broker_compose_boundary_minimizes_env_and_private_mounts")


def test_migration_capture_helper_compose_boundary_minimizes_env_and_confines_state_root() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("migration-capture-helper")
    expect(block is not None, "migration-capture-helper service block missing")
    assert block is not None
    expect('user: "0:0"' in block, f"migration-capture-helper root boundary must stay explicit\n{block}")
    expect("cap_drop:\n      - ALL" in block, block)
    expect("/var/run/docker.sock" not in block, block)
    expect("group_add:" not in block, block)
    expect("<<: *arclink-env" not in block, f"migration-capture-helper must not inherit broad app env\n{block}")
    expect(
        "*arclink-control-secret-env" not in block,
        f"migration-capture-helper must not inherit control secret env\n{block}",
    )
    for forbidden_env in (
        "ARCLINK_CONFIG_FILE",
        "ARCLINK_PRIV_DIR",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        "ARCLINK_DB_PATH",
        "ARCLINK_SESSION_HASH_PEPPER",
        "ARCLINK_FLEET_ENROLLMENT_SECRET",
        "ARCLINK_DEFAULT_PRICE_ID",
        "ARCLINK_BASE_DOMAIN",
        "ARCLINK_INGRESS_MODE",
        "ARCLINK_MEMORY_SYNTH_API_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CHUTES_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
    ):
        expect(forbidden_env not in block, f"migration-capture-helper leaked broad env key {forbidden_env}\n{block}")
    for required_line in (
        "ARCLINK_STATE_ROOT_BASE: ${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}",
        "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN:",
        "ARCLINK_MIGRATION_CAPTURE_HELPER_HOST: 0.0.0.0",
        "ARCLINK_MIGRATION_CAPTURE_HELPER_PORT: 8914",
    ):
        expect(required_line in block, f"migration-capture-helper missing required minimal env line {required_line}\n{block}")
    expect(
        "${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}:${ARCLINK_STATE_ROOT_BASE:-/arcdata/deployments}" in block,
        f"migration-capture-helper must keep only the deployment state-root bind\n{block}",
    )
    for forbidden_mount in (
        "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config",
        "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state",
        "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets",
        "/home/arclink/arclink/arclink-priv/secrets",
    ):
        expect(forbidden_mount not in block, f"migration-capture-helper leaked broad private mount {forbidden_mount}\n{block}")

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "migration-capture-helper"),
        None,
    )
    expect(isinstance(row, dict), "migration-capture-helper inventory row missing")
    assert isinstance(row, dict)
    boundary = row.get("compose_boundary")
    expect(isinstance(boundary, dict), f"migration-capture-helper inventory boundary missing: {row}")
    assert isinstance(boundary, dict)
    expect(boundary.get("private_state_mounts") is False, f"migration-capture-helper must not overclaim broad private-state mounts: {boundary}")
    expect(boundary.get("deployment_state_root_mount") is True, f"migration-capture-helper must record deployment state-root bind: {boundary}")
    expect(boundary.get("global_container_secrets_mount") is False, f"migration-capture-helper must not mount global container secrets: {boundary}")
    expect(boundary.get("inherits_broad_app_env") is False, f"migration-capture-helper must not inherit broad app env: {boundary}")
    controls = row.get("gap_019_ac_controls")
    expect(isinstance(controls, dict), f"migration-capture-helper must record GAP-019-AC controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("local_repair_status") == "migration_capture_helper_service_env_and_state_root_confinement_added",
        f"unexpected GAP-019-AC status: {controls}",
    )
    expect("broad *arclink-env" in str(controls.get("removed_environment") or ""), controls)
    preserved = controls.get("preserved_service_env")
    expect(
        isinstance(preserved, list)
        and "ARCLINK_STATE_ROOT_BASE" in preserved
        and "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN" in preserved,
        controls,
    )
    expect("ARCLINK_STATE_ROOT_BASE" in str(controls.get("path_confinement") or ""), controls)
    expect("root authority" in str(controls.get("remaining_gate") or ""), controls)
    print("PASS test_migration_capture_helper_compose_boundary_minimizes_env_and_confines_state_root")


def test_agent_supervisor_broker_compose_boundary_minimizes_env_and_private_mounts() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("agent-supervisor-broker")
    expect(block is not None, "agent-supervisor-broker service block missing")
    assert block is not None
    expect("/var/run/docker.sock:/var/run/docker.sock" in block, block)
    expect("group_add:" in block, block)
    expect("cap_drop:\n      - ALL" in block, block)
    expect("<<: *arclink-env" not in block, f"agent-supervisor-broker must not inherit broad app env\n{block}")
    expect(
        "*arclink-control-secret-env" not in block,
        f"agent-supervisor-broker must not inherit control secret env\n{block}",
    )
    for forbidden_env in (
        "ARCLINK_CONFIG_FILE",
        "ARCLINK_PRIV_DIR",
        "ARCLINK_DB_PATH",
        "ARCLINK_SESSION_HASH_PEPPER",
        "ARCLINK_FLEET_ENROLLMENT_SECRET",
        "ARCLINK_DEFAULT_PRICE_ID",
        "ARCLINK_BASE_DOMAIN",
        "ARCLINK_INGRESS_MODE",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CHUTES_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
        "ARCLINK_MEMORY_SYNTH_API_KEY",
    ):
        expect(forbidden_env not in block, f"agent-supervisor-broker leaked broad env key {forbidden_env}\n{block}")
    for forbidden_mount in (
        "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config",
        "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state",
        "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets",
        "/home/arclink/arclink/arclink-priv/secrets",
    ):
        expect(forbidden_mount not in block, f"agent-supervisor-broker leaked broad private mount {forbidden_mount}\n{block}")
    for required_line in (
        'ARCLINK_DOCKER_MODE: "1"',
        "ARCLINK_DOCKER_BINARY: ${ARCLINK_DOCKER_BINARY:-docker}",
        "ARCLINK_REPO_DIR: /home/arclink/arclink",
        "ARCLINK_DOCKER_IMAGE: ${ARCLINK_DOCKER_IMAGE:-arclink/app:local}",
        "ARCLINK_DOCKER_HOST_PRIV_DIR: ${ARCLINK_DOCKER_HOST_PRIV_DIR:-}",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR: /home/arclink/arclink/arclink-priv",
        "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN:",
        "ARCLINK_AGENT_SUPERVISOR_BROKER_HOST: 0.0.0.0",
        "ARCLINK_AGENT_SUPERVISOR_BROKER_PORT: 8913",
    ):
        expect(required_line in block, f"agent-supervisor-broker missing required minimal env line {required_line}\n{block}")

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "agent-supervisor-broker"),
        None,
    )
    expect(isinstance(row, dict), "agent-supervisor-broker inventory row missing")
    assert isinstance(row, dict)
    boundary = row.get("compose_boundary")
    expect(isinstance(boundary, dict), f"agent-supervisor-broker inventory boundary missing: {row}")
    assert isinstance(boundary, dict)
    expect(boundary.get("private_state_mounts") is False, f"agent-supervisor-broker must not overclaim broad private-state mounts: {boundary}")
    expect(boundary.get("global_container_secrets_mount") is False, f"agent-supervisor-broker must not mount global container secrets: {boundary}")
    expect(boundary.get("inherits_broad_app_env") is False, f"agent-supervisor-broker must not inherit broad app env: {boundary}")
    controls = row.get("gap_019_z_controls")
    expect(isinstance(controls, dict), f"agent-supervisor-broker must record GAP-019-Z controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("local_repair_status") == "agent_supervisor_broker_service_env_and_private_mount_narrowed",
        f"unexpected GAP-019-Z status: {controls}",
    )
    expect("broad *arclink-env" in str(controls.get("removed_environment") or ""), controls)
    removed_mounts = controls.get("removed_mounts")
    expect(
        isinstance(removed_mounts, list)
        and "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config" in removed_mounts
        and "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" in removed_mounts
        and "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets" in removed_mounts,
        controls,
    )
    preserved = controls.get("preserved_service_env")
    expect(
        isinstance(preserved, list)
        and "ARCLINK_DOCKER_HOST_PRIV_DIR" in preserved
        and "ARCLINK_DOCKER_CONTAINER_PRIV_DIR" in preserved
        and "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN" in preserved,
        controls,
    )
    print("PASS test_agent_supervisor_broker_compose_boundary_minimizes_env_and_private_mounts")


def test_operator_upgrade_broker_compose_boundary_minimizes_env_and_private_mounts() -> None:
    blocks = compose_service_blocks()
    block = blocks.get("operator-upgrade-broker")
    expect(block is not None, "operator-upgrade-broker service block missing")
    assert block is not None
    expect("/var/run/docker.sock:/var/run/docker.sock" in block, block)
    expect("group_add:" in block, block)
    expect(
        'user: "0:0"' in block,
        f"operator-upgrade-broker must run as the trusted root broker so /root-hosted live checkouts are traversable\n{block}",
    )
    expect("cap_drop:\n      - ALL" in block, block)
    expect(compose_list_values(block, "cap_add") == ["DAC_OVERRIDE"], block)
    expect("<<: *arclink-env" not in block, f"operator-upgrade-broker must not inherit broad app env\n{block}")
    expect(
        "*arclink-control-secret-env" not in block,
        f"operator-upgrade-broker must not inherit control secret env\n{block}",
    )
    for forbidden_env in (
        "ARCLINK_CONFIG_FILE",
        "ARCLINK_PRIV_DIR",
        "ARCLINK_DB_PATH",
        "ARCLINK_SESSION_HASH_PEPPER",
        "ARCLINK_FLEET_ENROLLMENT_SECRET",
        "ARCLINK_DEFAULT_PRICE_ID",
        "ARCLINK_BASE_DOMAIN",
        "ARCLINK_INGRESS_MODE",
        "ARCLINK_MEMORY_SYNTH_API_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "CLOUDFLARE_API_TOKEN",
        "CHUTES_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "DISCORD_BOT_TOKEN",
    ):
        expect(forbidden_env not in block, f"operator-upgrade-broker leaked broad env key {forbidden_env}\n{block}")
    for forbidden_mount in (
        "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config",
        "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state",
        "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets",
        "/home/arclink/arclink/arclink-priv/secrets",
    ):
        expect(forbidden_mount not in block, f"operator-upgrade-broker leaked broad private mount {forbidden_mount}\n{block}")
    for required_line in (
        'ARCLINK_DOCKER_MODE: "1"',
        "ARCLINK_CONTAINER_RUNTIME: docker",
        "ARCLINK_COMPONENT_UPGRADE_MODE: docker",
        "ARCLINK_REPO_DIR: /home/arclink/arclink",
        "ARCLINK_DOCKER_HOST_REPO_DIR: ${ARCLINK_DOCKER_HOST_REPO_DIR:-}",
        "ARCLINK_DOCKER_HOST_PRIV_DIR: ${ARCLINK_DOCKER_HOST_PRIV_DIR:-}",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR: /home/arclink/arclink/arclink-priv",
        "ARCLINK_DOCKER_BINARY: ${ARCLINK_DOCKER_BINARY:-docker}",
        "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN:",
        "ARCLINK_OPERATOR_UPGRADE_BROKER_HOST: 0.0.0.0",
        "ARCLINK_OPERATOR_UPGRADE_BROKER_PORT: 8917",
    ):
        expect(required_line in block, f"operator-upgrade-broker missing required minimal env line {required_line}\n{block}")
    expect(
        re.search(rf"^\s+- {re.escape(HOST_REPO_BIND)}\s*$", block, re.MULTILINE)
        and HOST_REPO_BIND_RO not in block,
        f"operator-upgrade-broker must keep the explicit writable host repo exception\n{block}",
    )

    inventory = docker_authority_inventory()
    row = next(
        (item for item in inventory.get("services", []) if isinstance(item, dict) and item.get("service") == "operator-upgrade-broker"),
        None,
    )
    expect(isinstance(row, dict), "operator-upgrade-broker inventory row missing")
    assert isinstance(row, dict)
    boundary = row.get("compose_boundary")
    expect(isinstance(boundary, dict), f"operator-upgrade-broker inventory boundary missing: {row}")
    assert isinstance(boundary, dict)
    expect(boundary.get("private_state_mounts") is False, f"operator-upgrade-broker must not overclaim broad private-state mounts: {boundary}")
    expect(boundary.get("host_repo_bind_includes_private_state") is True, f"operator-upgrade-broker must record private state through host repo bind: {boundary}")
    expect(boundary.get("global_container_secrets_mount") is False, f"operator-upgrade-broker must not mount global container secrets: {boundary}")
    expect(boundary.get("inherits_broad_app_env") is False, f"operator-upgrade-broker must not inherit broad app env: {boundary}")
    expect(boundary.get("linux_capabilities") == "drop_all_add_DAC_OVERRIDE", f"operator-upgrade-broker must record its exact cap_add set: {boundary}")
    controls = row.get("gap_019_ab_controls")
    expect(isinstance(controls, dict), f"operator-upgrade-broker must record GAP-019-AB controls: {row}")
    assert isinstance(controls, dict)
    expect(
        controls.get("local_repair_status") == "operator_upgrade_broker_service_env_and_child_env_narrowed",
        f"unexpected GAP-019-AB status: {controls}",
    )
    expect("broad *arclink-env" in str(controls.get("removed_environment") or ""), controls)
    removed_mounts = controls.get("removed_mounts")
    expect(
        isinstance(removed_mounts, list)
        and "./arclink-priv/config:/home/arclink/arclink/arclink-priv/config" in removed_mounts
        and "./arclink-priv/state:/home/arclink/arclink/arclink-priv/state" in removed_mounts
        and "./arclink-priv/secrets/container:/home/arclink/arclink/arclink-priv/secrets" in removed_mounts,
        controls,
    )
    expect("os.environ.copy" in str(controls.get("removed_child_process_env") or ""), controls)
    preserved = controls.get("preserved_service_env")
    expect(
        isinstance(preserved, list)
        and "ARCLINK_DOCKER_HOST_REPO_DIR" in preserved
        and "ARCLINK_DOCKER_HOST_PRIV_DIR" in preserved
        and "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN" in preserved,
        controls,
    )
    expect("writable host repo" in str(controls.get("remaining_gate") or ""), controls)
    print("PASS test_operator_upgrade_broker_compose_boundary_minimizes_env_and_private_mounts")


def test_docker_authority_inventory_matches_compose_boundary() -> None:
    surface = compose_docker_authority_surface()
    inventory = docker_authority_inventory()
    records = inventory.get("services")
    expect(isinstance(records, list) and records, "config/docker-authority-inventory.json must define services")
    by_service = {record.get("service"): record for record in records if isinstance(record, dict)}
    expect("control-ingress" not in by_service, "control-ingress should leave the socket/root authority inventory after GAP-019-V")
    expect("agent-supervisor" not in by_service, "agent-supervisor should leave the root/socket authority inventory after GAP-019-P")
    expect("agent-process-helper" in by_service, "agent-process-helper must own the remaining setpriv root boundary")

    expect(
        set(by_service) == set(surface),
        "Docker socket/root authority inventory drifted.\n"
        f"missing={sorted(set(surface) - set(by_service))}\n"
        f"extra={sorted(set(by_service) - set(surface))}",
    )

    required_fields = (
        "service",
        "authority_class",
        "purpose",
        "compose_boundary",
        "why_socket_needed",
        "proxy_or_broker_candidate_status",
        "monitoring_runbook_anchor",
        "residual_policy_state",
        "gap_019_b2_review",
    )
    for service, actual in surface.items():
        record = by_service[service]
        for field in required_fields:
            expect(record.get(field), f"{service} inventory record missing {field}: {record}")
        boundary = record.get("compose_boundary")
        expect(isinstance(boundary, dict), f"{service} compose_boundary must be a mapping: {record}")
        expect(
            boundary.get("docker_socket") == actual["docker_socket"],
            f"{service} Docker socket mode drifted: inventory={boundary} compose={actual['block']}",
        )
        expect(
            boundary.get("explicit_root") == actual["explicit_root"],
            f"{service} root boundary drifted: inventory={boundary} compose={actual['block']}",
        )
        expect(
            boundary.get("linux_capabilities") == actual["linux_capabilities"],
            f"{service} capability boundary drifted: inventory={boundary} compose={actual['block']}",
        )
        expect(
            boundary.get("compose_networks") == actual["compose_networks"],
            f"{service} Compose network boundary drifted: inventory={boundary} compose={actual['block']}",
        )
        expect(
            boundary.get("default_network") == ("default" in actual["compose_networks"]),
            f"{service} default network classification drifted: inventory={boundary} compose={actual['block']}",
        )
        if actual["explicit_root"]:
            expect(boundary.get("container_user") == "root", f"{service} root service must be explicit in inventory")
        if actual["docker_socket"] == "write":
            residual = str(record["residual_policy_state"])
            expect("host-root-equivalent" in residual and "GAP-019" in residual, f"{service} must preserve residual risk: {residual}")
            expect(
                "GAP-019-B2 reviewed" in str(record["proxy_or_broker_candidate_status"]),
                f"{service} writeable socket service must record the local B2 review: {record}",
            )
        if actual["docker_socket"] == "write" and not actual["explicit_root"]:
            expect(
                boundary.get("container_user") == "arclink",
                f"{service} non-root writer must remain classified as the app runtime user: {record}",
            )
            expect(boundary.get("linux_capabilities") == "all_dropped", f"{service} non-root writer must drop capabilities")

        review = record.get("gap_019_b2_review")
        expect(isinstance(review, dict), f"{service} must carry a GAP-019-B2 review record: {record}")
        expect(str(review.get("review_status") or "").startswith("reviewed-"), f"{service} has invalid B2 review status: {review}")
        operations = review.get("operation_allowlist")
        expect(isinstance(operations, list) and operations, f"{service} B2 review must include an operation allowlist: {review}")
        monitoring = review.get("monitoring_controls")
        expect(isinstance(monitoring, list) and monitoring, f"{service} B2 review must include monitoring controls: {review}")
        enforcement = review.get("runtime_enforcement_paths")
        expect(isinstance(enforcement, list) and enforcement, f"{service} B2 review must name runtime enforcement paths: {review}")

        al_controls = record.get("gap_019_al_controls")
        expect(isinstance(al_controls, dict), f"{service} must record GAP-019-AL trusted-host acceptance controls: {record}")
        assert isinstance(al_controls, dict)
        expect(
            al_controls.get("local_repair_status") == "trusted_host_residual_risk_acceptance_gate_added",
            f"{service} must record GAP-019-AL repair status: {al_controls}",
        )
        expect(al_controls.get("acceptance_env") == TRUSTED_HOST_RISK_ENV, al_controls)
        expect(al_controls.get("accepted_value") == TRUSTED_HOST_RISK_ACCEPTED, al_controls)
        expect("before HTTP listener bind" in str(al_controls.get("fail_closed_boundary") or ""), al_controls)
        expect("does not close GAP-019" in str(al_controls.get("remaining_gate") or ""), al_controls)
        al_enforcement = "\n".join(str(item) for item in al_controls.get("enforcement_paths") or [])
        expect("arclink_boundary.py:require_docker_trusted_host_risk_accepted" in al_enforcement, al_controls)
        expect("python/" in al_enforcement and "main" in al_enforcement, al_controls)
        ap_controls = record.get("gap_019_ap_controls")
        expect(isinstance(ap_controls, dict), f"{service} must record GAP-019-AP listener default controls: {record}")
        expect(
            ap_controls.get("local_repair_status") == "direct_run_listener_defaults_loopback",
            f"{service} must record GAP-019-AP repair status: {ap_controls}",
        )
        expect(ap_controls.get("default_host") == "127.0.0.1", ap_controls)
        expect("0.0.0.0" in str(ap_controls.get("compose_host_env") or ""), ap_controls)
        expect("loopback" in str(ap_controls.get("control_type") or ""), ap_controls)
        expect("GAP-019 remains open" in str(ap_controls.get("remaining_gate") or ""), ap_controls)
        ap_tests = "\n".join(str(item) for item in ap_controls.get("test_anchors") or [])
        expect("test_high_authority_helpers_default_to_loopback_outside_compose" in ap_tests, ap_controls)
        root_split = review.get("root_split_review")
        expect(isinstance(root_split, dict) and "decision" in root_split, f"{service} B2 review must include root split decision: {review}")
        if actual["docker_socket"] == "write":
            decision = str(review.get("broker_or_proxy_decision") or "")
            expect(
                "generic" in decision.lower() and ("no-go" in decision.lower() or "do not" in decision.lower()),
                f"{service} B2 review must explicitly reject generic socket proxy as closure: {review}",
            )
            expect(review.get("operator_decision_required") is True, f"{service} writeable socket residual risk requires operator decision: {review}")
            expect("GAP-019" in str(review.get("remaining_gate") or ""), f"{service} B2 review must preserve remaining GAP-019 gate: {review}")
        if actual["explicit_root"]:
            expect(root_split.get("required") is True, f"{service} explicit root service must require a root split review: {review}")
        if actual["docker_socket"] == "write" or actual["explicit_root"]:
            incident = record.get("gap_019_m_incident_controls")
            expect(isinstance(incident, dict), f"{service} must carry GAP-019-M incident controls: {record}")
            expect(
                incident.get("local_repair_status") == "incident_controls_recorded",
                f"{service} incident controls must record local repair status: {incident}",
            )
            for field in (
                "monitored_signals",
                "status_and_logs",
                "triage_steps",
                "fail_closed_actions",
            ):
                values = incident.get(field)
                expect(isinstance(values, list) and len(values) >= 3, f"{service} incident controls missing {field}: {incident}")
            incident_text = json.dumps(incident, sort_keys=True)
            expect(service in incident_text, f"{service} incident controls must name the service or service-specific signals: {incident}")
            expect("GAP-019" in str(incident.get("escalation_boundary") or ""), f"{service} incident escalation must preserve GAP-019 boundary: {incident}")
            expect(
                "manual " in incident_text.lower() or "raw command" in incident_text.lower() or "useradd" in incident_text.lower(),
                f"{service} incident controls must define a fail-closed manual/raw-command boundary: {incident}",
            )
        if service == "gateway-exec-broker":
            controls = record.get("gap_019_f_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-F local broker: {record}")
            expect(
                controls.get("local_repair_status") == "gateway_exec_broker_added",
                f"{service} must record the gateway exec broker repair status: {controls}",
            )
            allowed = controls.get("allowed_command_kinds")
            expect(
                allowed == ["docker-exec-hermes-gateway", "docker-compose-exec-hermes-gateway"],
                f"{service} must constrain public Agent bridge command kinds: {controls}",
            )
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_gateway_exec_broker.py" in enforcement_text, f"{service} must name the broker: {controls}")
            expect("_validate_public_agent_bridge_cmd" in enforcement_text, f"{service} must name the command validator: {controls}")
            expect("ARCLINK_STATE_ROOT_BASE" in str(controls.get("path_confinement") or ""), controls)
            expect("writeable Docker socket access remains host-root-equivalent" in str(controls.get("remaining_gate") or ""), controls)
            y_controls = record.get("gap_019_y_controls")
            expect(isinstance(y_controls, dict), f"{service} must record GAP-019-Y service boundary controls: {record}")
            expect(
                y_controls.get("local_repair_status") == "gateway_exec_broker_service_env_and_private_mount_narrowed",
                f"{service} must record GAP-019-Y repair status: {y_controls}",
            )
            expect("deployment state-root bind" in str(y_controls.get("preserved_mounts") or ""), y_controls)
            expect("writeable Docker socket" in str(y_controls.get("remaining_gate") or ""), y_controls)
            ay_controls = record.get("gap_019_ay_controls")
            expect(isinstance(ay_controls, dict), f"{service} must record GAP-019-AY fallback config controls: {record}")
            expect(
                ay_controls.get("local_repair_status") == "gateway_exec_broker_fallback_config_file_preflight_added",
                f"{service} must record GAP-019-AY repair status: {ay_controls}",
            )
            ay_enforcement = "\n".join(str(item) for item in ay_controls.get("enforcement_paths") or [])
            expect("_preflight_deployment_compose_config_files" in ay_enforcement, ay_controls)
            expect("symlinked config/arclink.env" in str(ay_controls.get("rejected_configuration") or ""), ay_controls)
            expect("before docker compose exec subprocess dispatch" in str(ay_controls.get("fail_closed_boundary") or ""), ay_controls)
            expect("writeable Docker socket authority" in str(ay_controls.get("remaining_gate") or ""), ay_controls)
            bc_controls = record.get("gap_019_bc_controls")
            expect(isinstance(bc_controls, dict), f"{service} must record GAP-019-BC rejection incident controls: {record}")
            expect(
                bc_controls.get("local_repair_status") == "gateway_exec_broker_rejected_request_incidents_added",
                f"{service} must record GAP-019-BC repair status: {bc_controls}",
            )
            expect("_broker-incidents/gateway-exec-broker/rejections.jsonl" in str(bc_controls.get("incident_path") or ""), bc_controls)
            bc_enforcement = "\n".join(str(item) for item in bc_controls.get("enforcement_paths") or [])
            expect("_record_rejection_incident" in bc_enforcement and "run_gateway_exec_request" in bc_enforcement, bc_controls)
            expect("bridge payload values" in str(bc_controls.get("redacted_fields") or ""), bc_controls)
            expect("bot tokens" in str(bc_controls.get("redacted_fields") or ""), bc_controls)
            expect("Accepted broker requests" in str(bc_controls.get("fail_closed_boundary") or ""), bc_controls)
            expect("writeable Docker socket authority" in str(bc_controls.get("remaining_gate") or ""), bc_controls)
        if service == "deployment-exec-broker":
            controls = record.get("gap_019_g_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-G local broker: {record}")
            expect(
                controls.get("local_repair_status") == "deployment_exec_broker_added",
                f"{service} must record the deployment exec broker repair status: {controls}",
            )
            allowed = controls.get("allowed_operation_kinds")
            expect(
                allowed == ["compose_up", "compose_ps", "compose_down"],
                f"{service} must constrain deployment executor operations: {controls}",
            )
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_deployment_exec_broker.py" in enforcement_text, f"{service} must name the broker: {controls}")
            expect("BrokeredDockerComposeRunner" in enforcement_text, f"{service} must name the broker client: {controls}")
            expect("ARCLINK_STATE_ROOT_BASE" in str(controls.get("path_confinement") or ""), controls)
            expect("writeable Docker socket access remains host-root-equivalent" in str(controls.get("remaining_gate") or ""), controls)
            aa_controls = record.get("gap_019_aa_controls")
            expect(isinstance(aa_controls, dict), f"{service} must record GAP-019-AA service boundary controls: {record}")
            expect(
                aa_controls.get("local_repair_status") == "deployment_exec_broker_service_env_narrowed",
                f"{service} must record GAP-019-AA repair status: {aa_controls}",
            )
            expect("broad *arclink-env" in str(aa_controls.get("removed_environment") or ""), aa_controls)
            expect("deployment state-root bind" in str(aa_controls.get("preserved_mounts") or ""), aa_controls)
            expect("writeable Docker socket" in str(aa_controls.get("remaining_gate") or ""), aa_controls)
            ag_controls = record.get("gap_019_ag_controls")
            expect(isinstance(ag_controls, dict), f"{service} must record GAP-019-AG Docker CLI controls: {record}")
            expect(
                ag_controls.get("local_repair_status") == "deployment_exec_broker_docker_cli_preflight_added",
                f"{service} must record GAP-019-AG repair status: {ag_controls}",
            )
            ag_enforcement = "\n".join(str(item) for item in ag_controls.get("enforcement_paths") or [])
            expect("_docker_binary" in ag_enforcement and "run_deployment_exec_request" in ag_enforcement, ag_controls)
            expect("ARCLINK_DOCKER_BINARY" in str(ag_controls.get("rejected_configuration") or ""), ag_controls)
            expect("before subprocess" in str(ag_controls.get("fail_closed_boundary") or ""), ag_controls)
            ax_controls = record.get("gap_019_ax_controls")
            expect(isinstance(ax_controls, dict), f"{service} must record GAP-019-AX rendered config file controls: {record}")
            expect(
                ax_controls.get("local_repair_status") == "deployment_exec_broker_config_file_preflight_added",
                f"{service} must record GAP-019-AX repair status: {ax_controls}",
            )
            ax_enforcement = "\n".join(str(item) for item in ax_controls.get("enforcement_paths") or [])
            expect("_validate_config_file" in ax_enforcement and "_validate_request" in ax_enforcement, ax_controls)
            expect("symlinked config/arclink.env" in str(ax_controls.get("rejected_configuration") or ""), ax_controls)
            expect("before Docker CLI lookup" in str(ax_controls.get("fail_closed_boundary") or ""), ax_controls)
            expect("writeable Docker socket access remains host-root-equivalent" in str(ax_controls.get("remaining_gate") or ""), ax_controls)
        if service == "control-action-worker":
            controls = record.get("gap_019_h_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-H local broker delegation: {record}")
            expect(
                controls.get("local_repair_status") == "action_worker_socket_removed",
                f"{service} must record the action-worker socket removal status: {controls}",
            )
            delegated = controls.get("delegated_operation_kinds")
            expect(
                delegated == ["compose_up", "compose_ps", "compose_down"],
                f"{service} must delegate local Docker lifecycle/apply operations to the deployment exec broker: {controls}",
            )
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_action_worker.py:_executor_from_env" in enforcement_text, f"{service} must name action worker env construction: {controls}")
            expect("BrokeredDockerComposeRunner" in enforcement_text, f"{service} must name the broker client: {controls}")
            expect("Pod migration capture" in str(controls.get("remaining_root_boundary") or ""), controls)
            expect("writeable Docker socket" not in str(record.get("residual_policy_state") or ""), record)
            k_controls = record.get("gap_019_k_controls")
            expect(isinstance(k_controls, dict), f"{service} must record the GAP-019-K root-capture guard: {record}")
            expect(
                k_controls.get("local_repair_status") == "root_capture_opt_in_added",
                f"{service} must record the root-capture opt-in repair status: {k_controls}",
            )
            expect("ARCLINK_ACTION_WORKER_ALLOW_ROOT_MIGRATION_CAPTURE" in str(k_controls.get("control_type") or ""), k_controls)
            k_enforcement = "\n".join(str(item) for item in k_controls.get("enforcement_paths") or [])
            expect("arclink_pod_migration.py:_require_root_capture_opt_in" in k_enforcement, k_controls)
            expect("arclink_pod_migration.py:_validate_capture_paths" in k_enforcement, k_controls)
            expect("operator-controlled migration window" in str(k_controls.get("remaining_gate") or ""), k_controls)
        if service == "migration-capture-helper":
            controls = record.get("gap_019_n_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-N root helper: {record}")
            expect(
                controls.get("local_repair_status") == "migration_capture_helper_added",
                f"{service} must record the migration capture helper repair status: {controls}",
            )
            expect(
                controls.get("allowed_operation_kinds") == ["capture", "materialize"],
                f"{service} must constrain migration helper operations: {controls}",
            )
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_migration_capture_helper.py" in enforcement_text, f"{service} must name the helper: {controls}")
            expect("_migration_capture_helper_config" in enforcement_text, f"{service} must name the helper client gate: {controls}")
            validated = controls.get("validated_fields")
            expect(isinstance(validated, list) and "migration_id" in validated and "prefix" in validated, controls)
            expect("raw commands" in json.dumps(record.get("gap_019_b2_review") or {}).lower(), record)
            expect("root authority" in str(controls.get("remaining_gate") or ""), controls)
            ac_controls = record.get("gap_019_ac_controls")
            expect(isinstance(ac_controls, dict), f"{service} must record GAP-019-AC service boundary controls: {record}")
            expect(
                ac_controls.get("local_repair_status") == "migration_capture_helper_service_env_and_state_root_confinement_added",
                f"{service} must record GAP-019-AC repair status: {ac_controls}",
            )
            expect("broad *arclink-env" in str(ac_controls.get("removed_environment") or ""), ac_controls)
            expect("ARCLINK_STATE_ROOT_BASE" in str(ac_controls.get("path_confinement") or ""), ac_controls)
        if service == "agent-user-helper":
            controls = record.get("gap_019_o_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-O root helper: {record}")
            expect(
                controls.get("local_repair_status") == "agent_user_helper_added",
                f"{service} must record the agent user helper repair status: {controls}",
            )
            expect(
                controls.get("allowed_operation_kinds") == ["ensure_user_home"],
                f"{service} must constrain agent user helper operations: {controls}",
            )
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_agent_user_helper.py" in enforcement_text, f"{service} must name the helper: {controls}")
            expect("agent_user_helper_request" in enforcement_text, f"{service} must name the helper client: {controls}")
            validated = controls.get("validated_fields")
            expect(isinstance(validated, list) and "unix_user" in validated and "home_root" in validated, controls)
            expect("ARCLINK_DOCKER_AGENT_HOME_ROOT" in str(controls.get("path_confinement") or ""), controls)
            expect("root authority" in str(controls.get("remaining_gate") or ""), controls)
            s_controls = record.get("gap_019_s_controls")
            expect(isinstance(s_controls, dict), f"{service} must record GAP-019-S configured-root controls: {record}")
            expect(
                s_controls.get("local_repair_status") == "configured_root_confinement_added",
                f"{service} must record GAP-019-S repair status: {s_controls}",
            )
            expect("ARCLINK_DOCKER_AGENT_HOME_ROOT" in str(s_controls.get("configured_roots") or ""), s_controls)
            expect("before subprocess or filesystem mutation" in str(s_controls.get("fail_closed_boundary") or ""), s_controls)
            an_controls = record.get("gap_019_an_controls")
            expect(isinstance(an_controls, dict), f"{service} must record GAP-019-AN symlink controls: {record}")
            expect(
                an_controls.get("local_repair_status") == "agent_user_helper_symlink_escape_rejected",
                f"{service} must record GAP-019-AN repair status: {an_controls}",
            )
            an_enforcement = "\n".join(str(item) for item in an_controls.get("enforcement_paths") or [])
            expect("_require_canonical_child_path" in an_enforcement and "_ensure_user_home" in an_enforcement, an_controls)
            expect("workspace symlink" in str(an_controls.get("rejected_path_class") or ""), an_controls)
            expect("before trusted executable preflight" in str(an_controls.get("fail_closed_boundary") or ""), an_controls)
            as_controls = record.get("gap_019_as_controls")
            expect(isinstance(as_controls, dict), f"{service} must record GAP-019-AS home-root symlink controls: {record}")
            expect(
                as_controls.get("local_repair_status") == "agent_user_helper_home_root_symlink_rejected",
                f"{service} must record GAP-019-AS repair status: {as_controls}",
            )
            as_enforcement = "\n".join(str(item) for item in as_controls.get("enforcement_paths") or [])
            expect("_require_no_symlink_components" in as_enforcement and "_ensure_user_home" in as_enforcement, as_controls)
            expect("ARCLINK_DOCKER_AGENT_HOME_ROOT" in str(as_controls.get("rejected_path_class") or ""), as_controls)
            expect("before trusted executable preflight" in str(as_controls.get("fail_closed_boundary") or ""), as_controls)
            expect("test_agent_helpers_reject_symlinked_home_root_before_root_work" in json.dumps(as_controls.get("test_anchors") or []), as_controls)
            ba_controls = record.get("gap_019_ba_controls")
            expect(isinstance(ba_controls, dict), f"{service} must record GAP-019-BA assignment file controls: {record}")
            expect(
                ba_controls.get("local_repair_status") == "agent_user_helper_assignment_file_preflight_added",
                f"{service} must record GAP-019-BA repair status: {ba_controls}",
            )
            ba_enforcement = "\n".join(str(item) for item in ba_controls.get("enforcement_paths") or [])
            expect("_require_id_assignment_file" in ba_enforcement and "_write_assignments" in ba_enforcement, ba_controls)
            expect(".arclink-user-ids.json.tmp" in str(ba_controls.get("rejected_path_class") or ""), ba_controls)
            expect("exclusive no-follow" in str(ba_controls.get("write_boundary") or ""), ba_controls)
            expect(
                "test_agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work"
                in json.dumps(ba_controls.get("test_anchors") or []),
                ba_controls,
            )
            ae_controls = record.get("gap_019_ae_controls")
            expect(isinstance(ae_controls, dict), f"{service} must record GAP-019-AE executable controls: {record}")
            expect(
                ae_controls.get("local_repair_status") == "agent_user_helper_root_executable_lookup_hardened",
                f"{service} must record GAP-019-AE repair status: {ae_controls}",
            )
            ae_enforcement = "\n".join(str(item) for item in ae_controls.get("enforcement_paths") or [])
            expect("_trusted_root_executable" in ae_enforcement and "_ensure_user_home" in ae_enforcement, ae_controls)
            absolute_bins = ae_controls.get("absolute_root_executables")
            expect(
                isinstance(absolute_bins, list)
                and "/usr/sbin/groupadd" in absolute_bins
                and "/usr/sbin/useradd" in absolute_bins
                and "/usr/bin/chown" in absolute_bins,
                ae_controls,
            )
            expect("before uid/gid assignment" in str(ae_controls.get("fail_closed_boundary") or ""), ae_controls)
        if service == "agent-process-helper":
            controls = record.get("gap_019_p_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-P root helper: {record}")
            expect(
                controls.get("local_repair_status") == "agent_process_helper_added",
                f"{service} must record the agent process helper repair status: {controls}",
            )
            expect(
                controls.get("allowed_operation_kinds") == ["run_once", "ensure_processes", "terminate_all"],
                f"{service} must constrain agent process helper operations: {controls}",
            )
            expect(controls.get("allowed_run_once_kinds") == ["install", "identity", "refresh", "cron"], controls)
            expect(controls.get("allowed_process_kinds") == ["gateway", "dashboard"], controls)
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_agent_process_helper.py" in enforcement_text, f"{service} must name the helper: {controls}")
            expect("agent_process_helper_request" in enforcement_text, f"{service} must name the helper client: {controls}")
            validated = controls.get("validated_fields")
            expect(isinstance(validated, list) and "uid/gid" in validated and "unix_user" in validated, controls)
            expect("ARCLINK_AGENT_PROCESS_HELPER_URL" in str(controls.get("path_confinement") or ""), controls)
            expect("root authority" in str(controls.get("remaining_gate") or ""), controls)
            r_controls = record.get("gap_019_r_controls")
            expect(isinstance(r_controls, dict), f"{service} must record GAP-019-R env exposure controls: {record}")
            expect(
                r_controls.get("local_repair_status") == "agent_process_env_argv_log_exposure_narrowed",
                f"{service} must record GAP-019-R repair status: {r_controls}",
            )
            r_enforcement = "\n".join(str(item) for item in r_controls.get("enforcement_paths") or [])
            expect("_setpriv_cmd" in r_enforcement and "_agent_process_env" in r_enforcement, r_controls)
            redacted = r_controls.get("redacted_surfaces")
            expect(isinstance(redacted, list) and "setpriv command argv" in redacted, r_controls)
            filtered = r_controls.get("filtered_supervisor_env_keys")
            expect(
                filtered
                == [
                    "ARCLINK_AGENT_PROCESS_HELPER_TOKEN",
                    "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN",
                    "ARCLINK_AGENT_USER_HELPER_TOKEN",
                    "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN",
                    "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN",
                    "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN",
                    "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN",
                ],
                r_controls,
            )
            w_controls = record.get("gap_019_w_controls")
            expect(isinstance(w_controls, dict), f"{service} must record GAP-019-W control-token env controls: {record}")
            expect(
                w_controls.get("local_repair_status") == "agent_process_control_token_env_rejected",
                f"{service} must record GAP-019-W repair status: {w_controls}",
            )
            w_enforcement = "\n".join(str(item) for item in w_controls.get("enforcement_paths") or [])
            expect("_require_env" in w_enforcement and "_agent_process_env" in w_enforcement, w_controls)
            rejected_keys = w_controls.get("rejected_env_keys")
            expect(
                isinstance(rejected_keys, list)
                and "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN" in rejected_keys
                and "future ARCLINK_*_TOKEN keys" in rejected_keys,
                w_controls,
            )
            expect("before log creation" in str(w_controls.get("fail_closed_boundary") or ""), w_controls)
            s_controls = record.get("gap_019_s_controls")
            expect(isinstance(s_controls, dict), f"{service} must record GAP-019-S configured-root controls: {record}")
            expect(
                s_controls.get("local_repair_status") == "configured_root_confinement_added",
                f"{service} must record GAP-019-S repair status: {s_controls}",
            )
            configured_roots = s_controls.get("configured_roots")
            expect(
                isinstance(configured_roots, list)
                and "ARCLINK_DOCKER_AGENT_HOME_ROOT" in configured_roots
                and "ARCLINK_REPO_DIR" in configured_roots
                and "RUNTIME_DIR" in configured_roots,
                s_controls,
            )
            expect("before log creation or subprocess" in str(s_controls.get("fail_closed_boundary") or ""), s_controls)
            an_controls = record.get("gap_019_an_controls")
            expect(isinstance(an_controls, dict), f"{service} must record GAP-019-AN symlink controls: {record}")
            expect(
                an_controls.get("local_repair_status") == "agent_process_helper_symlink_escape_rejected",
                f"{service} must record GAP-019-AN repair status: {an_controls}",
            )
            an_enforcement = "\n".join(str(item) for item in an_controls.get("enforcement_paths") or [])
            expect("_require_canonical_child_path" in an_enforcement and "_ensure_processes" in an_enforcement, an_controls)
            expect("agent home symlink" in str(an_controls.get("rejected_path_class") or ""), an_controls)
            expect("before helper log creation" in str(an_controls.get("fail_closed_boundary") or ""), an_controls)
            as_controls = record.get("gap_019_as_controls")
            expect(isinstance(as_controls, dict), f"{service} must record GAP-019-AS home-root symlink controls: {record}")
            expect(
                as_controls.get("local_repair_status") == "agent_process_helper_home_root_symlink_rejected",
                f"{service} must record GAP-019-AS repair status: {as_controls}",
            )
            as_enforcement = "\n".join(str(item) for item in as_controls.get("enforcement_paths") or [])
            expect("_require_no_symlink_components" in as_enforcement and "_ensure_processes" in as_enforcement, as_controls)
            expect("ARCLINK_DOCKER_AGENT_HOME_ROOT" in str(as_controls.get("rejected_path_class") or ""), as_controls)
            expect("before helper log creation" in str(as_controls.get("fail_closed_boundary") or ""), as_controls)
            expect("test_agent_helpers_reject_symlinked_home_root_before_root_work" in json.dumps(as_controls.get("test_anchors") or []), as_controls)
            at_controls = record.get("gap_019_at_controls")
            expect(isinstance(at_controls, dict), f"{service} must record GAP-019-AT configured-root symlink controls: {record}")
            expect(
                at_controls.get("local_repair_status") == "agent_process_helper_configured_root_symlinks_rejected",
                f"{service} must record GAP-019-AT repair status: {at_controls}",
            )
            at_enforcement = "\n".join(str(item) for item in at_controls.get("enforcement_paths") or [])
            expect("_configured_paths" in at_enforcement and "_require_state_dir" in at_enforcement, at_controls)
            rejected_paths = json.dumps(at_controls.get("rejected_path_class") or [])
            expect("ARCLINK_REPO_DIR" in rejected_paths and "RUNTIME_DIR" in rejected_paths, at_controls)
            expect("before helper log creation" in str(at_controls.get("fail_closed_boundary") or ""), at_controls)
            expect(
                "test_agent_process_helper_rejects_symlinked_configured_roots_before_work"
                in json.dumps(at_controls.get("test_anchors") or []),
                at_controls,
            )
            au_controls = record.get("gap_019_au_controls")
            expect(isinstance(au_controls, dict), f"{service} must record GAP-019-AU repo command target controls: {record}")
            expect(
                au_controls.get("local_repair_status") == "agent_process_helper_repo_command_targets_preflighted",
                f"{service} must record GAP-019-AU repair status: {au_controls}",
            )
            au_enforcement = "\n".join(str(item) for item in au_controls.get("enforcement_paths") or [])
            expect("_require_repo_command_target" in au_enforcement and "_process_command" in au_enforcement, au_controls)
            fixed_targets = json.dumps(au_controls.get("fixed_targets") or [])
            expect("bin/hermes-shell.sh" in fixed_targets and "arclink_headless_hermes_setup.py" in fixed_targets, au_controls)
            rejected_targets = json.dumps(au_controls.get("rejected_target_class") or [])
            expect("symlinked" in rejected_targets and "not a regular file" in rejected_targets, au_controls)
            expect("before helper log creation" in str(au_controls.get("fail_closed_boundary") or ""), au_controls)
            expect(
                "test_agent_process_helper_rejects_symlinked_or_missing_repo_command_targets_before_subprocess"
                in json.dumps(au_controls.get("test_anchors") or []),
                au_controls,
            )
            ao_controls = record.get("gap_019_ao_controls")
            expect(isinstance(ao_controls, dict), f"{service} must record GAP-019-AO log directory controls: {record}")
            expect(
                ao_controls.get("local_repair_status") == "agent_process_helper_log_directory_symlink_escape_rejected",
                f"{service} must record GAP-019-AO repair status: {ao_controls}",
            )
            ao_enforcement = "\n".join(str(item) for item in ao_controls.get("enforcement_paths") or [])
            expect("_require_log_dir" in ao_enforcement and "_log_path" in ao_enforcement, ao_controls)
            expect("state/docker/agent-process-helper" in str(ao_controls.get("rejected_path_class") or ""), ao_controls)
            expect("before log file creation" in str(ao_controls.get("fail_closed_boundary") or ""), ao_controls)
            expect("GAP-019" in str(ao_controls.get("remaining_gate") or ""), ao_controls)
            t_controls = record.get("gap_019_t_controls")
            expect(isinstance(t_controls, dict), f"{service} must record GAP-019-T host repo bind controls: {record}")
            expect(
                t_controls.get("local_repair_status") == "agent_process_host_repo_bind_read_only",
                f"{service} must record GAP-019-T repair status: {t_controls}",
            )
            expect("read-only" in str(t_controls.get("control_type") or ""), t_controls)
            ad_controls = record.get("gap_019_ad_controls")
            expect(isinstance(ad_controls, dict), f"{service} must record GAP-019-AD process lookup controls: {record}")
            expect(
                ad_controls.get("local_repair_status") == "agent_process_helper_pre_drop_lookup_hardened",
                f"{service} must record GAP-019-AD repair status: {ad_controls}",
            )
            ad_enforcement = "\n".join(str(item) for item in ad_controls.get("enforcement_paths") or [])
            expect("SETPRIV_BIN" in ad_enforcement and "_run_once_command" in ad_enforcement, ad_controls)
            expect("/usr/bin/setpriv" in str(ad_controls.get("absolute_root_executables") or ""), ad_controls)
            expect("SAFE_PATH" in str(ad_controls.get("rejected_env_values") or ""), ad_controls)
            expect("bare python3" in str(ad_controls.get("fail_closed_identity_boundary") or ""), ad_controls)
            aj_controls = record.get("gap_019_aj_controls")
            expect(isinstance(aj_controls, dict), f"{service} must record GAP-019-AJ process reconciliation controls: {record}")
            expect(
                aj_controls.get("local_repair_status") == "agent_process_helper_desired_signature_restart_added",
                f"{service} must record GAP-019-AJ repair status: {aj_controls}",
            )
            aj_enforcement = "\n".join(str(item) for item in aj_controls.get("enforcement_paths") or [])
            expect("_process_signature" in aj_enforcement and "_terminate_process" in aj_enforcement, aj_controls)
            expect("command" in str(aj_controls.get("signature_fields") or ""), aj_controls)
            expect("cwd" in str(aj_controls.get("signature_fields") or ""), aj_controls)
            expect("env" in str(aj_controls.get("signature_fields") or ""), aj_controls)
            expect("SIGTERM" in str(aj_controls.get("bounded_shutdown") or ""), aj_controls)
            expect("SIGKILL" in str(aj_controls.get("bounded_shutdown") or ""), aj_controls)
            expect("before replacement Popen" in str(aj_controls.get("fail_closed_boundary") or ""), aj_controls)
            ar_controls = record.get("gap_019_ar_controls")
            expect(isinstance(ar_controls, dict), f"{service} must record GAP-019-AR dashboard backend host controls: {record}")
            expect(
                ar_controls.get("local_repair_status") == "agent_process_dashboard_backend_host_rejected",
                f"{service} must record GAP-019-AR repair status: {ar_controls}",
            )
            ar_enforcement = "\n".join(str(item) for item in ar_controls.get("enforcement_paths") or [])
            expect("_require_dashboard_backend_host" in ar_enforcement and "_process_command" in ar_enforcement, ar_controls)
            rejected_hosts = json.dumps(ar_controls.get("rejected_host_classes") or [])
            expect("0.0.0.0" in rejected_hosts and "globally routable" in rejected_hosts and "non-IP" in rejected_hosts, ar_controls)
            expect("before helper log creation" in str(ar_controls.get("fail_closed_boundary") or ""), ar_controls)
            expect("test_agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess" in json.dumps(ar_controls.get("test_anchors") or []), ar_controls)
            bb_controls = record.get("gap_019_bb_controls")
            expect(isinstance(bb_controls, dict), f"{service} must record GAP-019-BB rejection incident controls: {record}")
            expect(
                bb_controls.get("local_repair_status") == "agent_process_helper_rejected_request_incidents_added",
                f"{service} must record GAP-019-BB repair status: {bb_controls}",
            )
            expect("rejections.jsonl" in str(bb_controls.get("incident_path") or ""), bb_controls)
            bb_enforcement = "\n".join(str(item) for item in bb_controls.get("enforcement_paths") or [])
            expect("_record_rejection_incident" in bb_enforcement and "run_agent_process_helper_request" in bb_enforcement, bb_controls)
            expect("raw request bodies" in str(bb_controls.get("redacted_fields") or ""), bb_controls)
            expect("env values" in str(bb_controls.get("redacted_fields") or ""), bb_controls)
            expect("Accepted run_once" in str(bb_controls.get("fail_closed_boundary") or ""), bb_controls)
            expect(
                "test_agent_process_helper_records_redacted_rejection_incident_before_subprocess"
                in json.dumps(bb_controls.get("test_anchors") or []),
                bb_controls,
            )
            am_controls = record.get("gap_019_am_controls")
            expect(isinstance(am_controls, dict), f"{service} must record GAP-019-AM process env controls: {record}")
            expect(
                am_controls.get("local_repair_status") == "agent_process_unapproved_env_keys_rejected",
                f"{service} must record GAP-019-AM repair status: {am_controls}",
            )
            am_enforcement = "\n".join(str(item) for item in am_controls.get("enforcement_paths") or [])
            expect("_require_env" in am_enforcement and "_agent_process_env" in am_enforcement, am_controls)
            rejected_env = am_controls.get("rejected_env_keys")
            expect(
                isinstance(rejected_env, list)
                and "LD_PRELOAD" in rejected_env
                and "PYTHONPATH" in rejected_env
                and "GIT_SSH_COMMAND" in rejected_env
                and "*_TOKEN" in rejected_env
                and "*_KEY" in rejected_env,
                am_controls,
            )
            expect("before log creation" in str(am_controls.get("fail_closed_boundary") or ""), am_controls)
            expect("GAP-019 remains open" in str(am_controls.get("remaining_gate") or ""), am_controls)
        if service == "agent-supervisor-broker":
            controls = record.get("gap_019_i_controls")
            expect(isinstance(controls, dict), f"{service} must record the GAP-019-I local broker: {record}")
            expect(
                controls.get("local_repair_status") == "agent_supervisor_broker_added",
                f"{service} must record the agent supervisor broker status: {controls}",
            )
            allowed = controls.get("allowed_operation_kinds")
            expect(
                allowed == [
                    "ensure_dashboard_network",
                    "ensure_dashboard_proxy",
                    "remove_dashboard_proxy",
                ],
                f"{service} must constrain agent supervisor Docker operations: {controls}",
            )
            enforcement_text = "\n".join(str(item) for item in controls.get("enforcement_paths") or [])
            expect("arclink_agent_supervisor_broker.py" in enforcement_text, f"{service} must name the broker: {controls}")
            expect("ARCLINK_DOCKER_CONTAINER_PRIV_DIR" in str(controls.get("path_confinement") or ""), controls)
            expect("writeable Docker socket access remains host-root-equivalent" in str(controls.get("remaining_gate") or ""), controls)
            z_controls = record.get("gap_019_z_controls")
            expect(isinstance(z_controls, dict), f"{service} must record GAP-019-Z service boundary controls: {record}")
            expect(
                z_controls.get("local_repair_status") == "agent_supervisor_broker_service_env_and_private_mount_narrowed",
                f"{service} must record GAP-019-Z repair status: {z_controls}",
            )
            expect("broad *arclink-env" in str(z_controls.get("removed_environment") or ""), z_controls)
            expect("writeable Docker socket" in str(z_controls.get("remaining_gate") or ""), z_controls)
            af_controls = record.get("gap_019_af_controls")
            expect(isinstance(af_controls, dict), f"{service} must record GAP-019-AF Docker CLI controls: {record}")
            expect(
                af_controls.get("local_repair_status") == "agent_supervisor_broker_docker_cli_preflight_added",
                f"{service} must record GAP-019-AF repair status: {af_controls}",
            )
            af_enforcement = "\n".join(str(item) for item in af_controls.get("enforcement_paths") or [])
            expect("_docker_binary" in af_enforcement and "_docker_command" in af_enforcement, af_controls)
            expect("ARCLINK_DOCKER_BINARY" in str(af_controls.get("rejected_configuration") or ""), af_controls)
            expect("before subprocess" in str(af_controls.get("fail_closed_boundary") or ""), af_controls)
            ar_controls = record.get("gap_019_ar_controls")
            expect(isinstance(ar_controls, dict), f"{service} must record GAP-019-AR dashboard backend host controls: {record}")
            expect(
                ar_controls.get("local_repair_status") == "agent_supervisor_broker_dashboard_backend_host_rejected",
                f"{service} must record GAP-019-AR repair status: {ar_controls}",
            )
            ar_enforcement = "\n".join(str(item) for item in ar_controls.get("enforcement_paths") or [])
            expect("_require_backend_host" in ar_enforcement and "_ensure_dashboard_proxy" in ar_enforcement, ar_controls)
            rejected_hosts = json.dumps(ar_controls.get("rejected_host_classes") or [])
            expect("0.0.0.0" in rejected_hosts and "globally routable" in rejected_hosts and "non-IP" in rejected_hosts, ar_controls)
            expect("before Docker CLI lookup" in str(ar_controls.get("fail_closed_boundary") or ""), ar_controls)
            expect("test_agent_supervisor_broker_rejects_unsafe_dashboard_backend_host" in json.dumps(ar_controls.get("test_anchors") or []), ar_controls)
            az_controls = record.get("gap_019_az_controls")
            expect(isinstance(az_controls, dict), f"{service} must record GAP-019-AZ private bind-root controls: {record}")
            expect(
                az_controls.get("local_repair_status") == "agent_supervisor_broker_private_bind_roots_rejected",
                f"{service} must record GAP-019-AZ repair status: {az_controls}",
            )
            az_enforcement = "\n".join(str(item) for item in az_controls.get("enforcement_paths") or [])
            expect("_require_private_bind_root" in az_enforcement and "_ensure_dashboard_proxy" in az_enforcement, az_controls)
            rejected_bind_roots = json.dumps(az_controls.get("rejected_configuration") or [])
            expect("ARCLINK_DOCKER_HOST_PRIV_DIR" in rejected_bind_roots, az_controls)
            expect("ARCLINK_DOCKER_CONTAINER_PRIV_DIR" in rejected_bind_roots, az_controls)
            expect("before proxy config hashing" in str(az_controls.get("fail_closed_boundary") or ""), az_controls)
            expect("before Docker CLI lookup" in str(az_controls.get("fail_closed_boundary") or ""), az_controls)
            expect("test_agent_supervisor_broker_rejects_unsafe_private_bind_roots_before_dashboard_proxy" in json.dumps(az_controls.get("test_anchors") or []), az_controls)
        if service == "operator-upgrade-broker":
            upgrade_controls = record.get("gap_019_j_controls")
            expect(isinstance(upgrade_controls, dict), f"{service} must record the GAP-019-J operator upgrade broker: {record}")
            expect(
                upgrade_controls.get("local_repair_status") == "operator_upgrade_broker_added",
                f"{service} must record the operator upgrade broker repair status: {upgrade_controls}",
            )
            expect(
                upgrade_controls.get("allowed_operation_kinds") == ["run_operator_upgrade", "run_pin_upgrade"],
                f"{service} must constrain operator upgrade operations: {upgrade_controls}",
            )
            upgrade_enforcement = "\n".join(str(item) for item in upgrade_controls.get("enforcement_paths") or [])
            expect("arclink_enrollment_provisioner.py:_run_brokered_host_upgrade" in upgrade_enforcement, upgrade_controls)
            expect("arclink_operator_upgrade_broker.py:_run_operator_upgrade" in upgrade_enforcement, upgrade_controls)
            expect("operator-actions" in str(upgrade_controls.get("path_confinement") or ""), upgrade_controls)
            u_controls = record.get("gap_019_u_controls")
            expect(isinstance(u_controls, dict), f"{service} must record GAP-019-U split controls: {record}")
            expect(
                u_controls.get("local_repair_status") == "operator_upgrade_broker_split_from_agent_supervisor",
                f"{service} must record GAP-019-U repair status: {u_controls}",
            )
            expect("agent-supervisor-broker" in str(u_controls.get("removed_authority") or ""), u_controls)
            t_controls = record.get("gap_019_t_controls")
            expect(isinstance(t_controls, dict), f"{service} must record GAP-019-T broker exception controls: {record}")
            expect(
                t_controls.get("local_repair_status") == "writable_host_repo_exception_recorded",
                f"{service} must record GAP-019-T broker exception status: {t_controls}",
            )
            expect("writable host repo" in str(t_controls.get("control_type") or ""), t_controls)
            ab_controls = record.get("gap_019_ab_controls")
            expect(isinstance(ab_controls, dict), f"{service} must record GAP-019-AB service/child-env controls: {record}")
            expect(
                ab_controls.get("local_repair_status") == "operator_upgrade_broker_service_env_and_child_env_narrowed",
                f"{service} must record GAP-019-AB repair status: {ab_controls}",
            )
            expect("broad *arclink-env" in str(ab_controls.get("removed_environment") or ""), ab_controls)
            expect("child-process env allowlist" in str(ab_controls.get("control_type") or ""), ab_controls)
            ai_controls = record.get("gap_019_ai_controls")
            expect(isinstance(ai_controls, dict), f"{service} must record GAP-019-AI Docker CLI controls: {record}")
            expect(
                ai_controls.get("local_repair_status") == "operator_upgrade_broker_docker_cli_preflight_added",
                f"{service} must record GAP-019-AI repair status: {ai_controls}",
            )
            ai_enforcement = "\n".join(str(item) for item in ai_controls.get("enforcement_paths") or [])
            expect("_docker_binary" in ai_enforcement and "_operator_env" in ai_enforcement, ai_controls)
            expect("ARCLINK_DOCKER_BINARY" in str(ai_controls.get("removed_authority") or ""), ai_controls)
            expect("before _run_logged_command" in str(ai_controls.get("fail_closed_boundary") or ""), ai_controls)
            av_controls = record.get("gap_019_av_controls")
            expect(isinstance(av_controls, dict), f"{service} must record GAP-019-AV fixed script controls: {record}")
            expect(
                av_controls.get("local_repair_status") == "operator_upgrade_broker_fixed_script_preflight_added",
                f"{service} must record GAP-019-AV repair status: {av_controls}",
            )
            av_enforcement = "\n".join(str(item) for item in av_controls.get("enforcement_paths") or [])
            expect("_require_operator_repo_script" in av_enforcement and "_run_pin_upgrade" in av_enforcement, av_controls)
            expect("deploy.sh" in str(av_controls.get("removed_authority") or ""), av_controls)
            expect("subprocess.run" in str(av_controls.get("fail_closed_boundary") or ""), av_controls)
            aw_controls = record.get("gap_019_aw_controls")
            expect(isinstance(aw_controls, dict), f"{service} must record GAP-019-AW upstream deploy-key path controls: {record}")
            expect(
                aw_controls.get("local_repair_status") == "operator_upgrade_broker_upstream_deploy_key_paths_confined",
                f"{service} must record GAP-019-AW repair status: {aw_controls}",
            )
            aw_enforcement = "\n".join(str(item) for item in aw_controls.get("enforcement_paths") or [])
            expect("_require_private_upstream_path" in aw_enforcement and "_operator_env" in aw_enforcement, aw_controls)
            expect("ARCLINK_UPSTREAM_DEPLOY_KEY_PATH" in str(aw_controls.get("removed_authority") or ""), aw_controls)
            expect("before private operator log" in str(aw_controls.get("fail_closed_boundary") or ""), aw_controls)

        anchor = str(record["monitoring_runbook_anchor"])
        doc_path = anchor.split("#", 1)[0]
        expect(doc_path.startswith("docs/"), f"{service} anchor must point at public docs: {anchor}")
        expect((REPO / doc_path).is_file(), f"{service} anchor doc is missing: {anchor}")

    docker_doc = read("docs/docker.md")
    operations_doc = read("docs/arclink/operations-runbook.md")
    data_safety_doc = read("docs/arclink/data-safety.md")
    expect("config/docker-authority-inventory.json" in docker_doc, docker_doc)
    expect("config/docker-authority-inventory.json" in operations_doc, operations_doc)
    expect("config/docker-authority-inventory.json" in data_safety_doc, data_safety_doc)
    expect("GAP-019-M" in docker_doc and "incident controls" in docker_doc, docker_doc)
    expect("GAP-019-M" in operations_doc and "incident controls" in operations_doc, operations_doc)
    expect("GAP-019-M" in data_safety_doc and "incident controls" in data_safety_doc, data_safety_doc)
    expect("GAP-019-Q" in docker_doc and "CHOWN" in docker_doc and "FOWNER" in docker_doc, docker_doc)
    expect("GAP-019-Q" in operations_doc and "CHOWN" in operations_doc and "FOWNER" in operations_doc, operations_doc)
    expect("GAP-019-Q" in data_safety_doc and "CHOWN" in data_safety_doc and "FOWNER" in data_safety_doc, data_safety_doc)
    expect("GAP-019-R" in docker_doc and "startup logs" in docker_doc, docker_doc)
    expect("GAP-019-R" in operations_doc and "setpriv argv" in operations_doc, operations_doc)
    expect("GAP-019-R" in data_safety_doc and "helper startup logs" in data_safety_doc, data_safety_doc)
    expect("GAP-019-T" in docker_doc and "read-only host repo" in docker_doc, docker_doc)
    expect("GAP-019-T" in operations_doc and "read-only host repo" in operations_doc, operations_doc)
    expect("GAP-019-T" in data_safety_doc and "read-only host repo" in data_safety_doc, data_safety_doc)
    expect("GAP-019-U" in docker_doc and "operator-upgrade-broker" in docker_doc, docker_doc)
    expect("GAP-019-U" in operations_doc and "operator-upgrade-broker" in operations_doc, operations_doc)
    expect("GAP-019-U" in data_safety_doc and "operator-upgrade-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-V" in docker_doc and "config/traefik-control.yaml" in docker_doc, docker_doc)
    expect("GAP-019-V" in operations_doc and "static Traefik" in operations_doc, operations_doc)
    expect("GAP-019-V" in data_safety_doc and "control-ingress" in data_safety_doc, data_safety_doc)
    expect("GAP-019-Y" in docker_doc and "gateway-exec-broker" in docker_doc and "deployment state-root" in docker_doc, docker_doc)
    expect("GAP-019-Y" in operations_doc and "gateway-exec-broker" in operations_doc, operations_doc)
    expect("GAP-019-Y" in data_safety_doc and "gateway-exec-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AA" in docker_doc and "deployment-exec-broker" in docker_doc and "minimal service env" in docker_doc, docker_doc)
    expect("GAP-019-AA" in operations_doc and "deployment-exec-broker" in operations_doc, operations_doc)
    expect("GAP-019-AA" in data_safety_doc and "deployment-exec-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AB" in docker_doc and "operator-upgrade-broker" in docker_doc and "child-process env allowlist" in docker_doc, docker_doc)
    expect("GAP-019-AB" in operations_doc and "operator-upgrade-broker" in operations_doc, operations_doc)
    expect("GAP-019-AB" in data_safety_doc and "operator-upgrade-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AC" in docker_doc and "migration-capture-helper" in docker_doc and "ARCLINK_STATE_ROOT_BASE" in docker_doc, docker_doc)
    expect("GAP-019-AC" in operations_doc and "migration-capture-helper" in operations_doc, operations_doc)
    expect("GAP-019-AC" in data_safety_doc and "migration-capture-helper" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AF" in docker_doc and "agent-supervisor-broker" in docker_doc and "Docker CLI" in docker_doc, docker_doc)
    expect("GAP-019-AF" in operations_doc and "agent-supervisor-broker" in operations_doc, operations_doc)
    expect("GAP-019-AF" in data_safety_doc and "agent-supervisor-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AG" in docker_doc and "deployment-exec-broker" in docker_doc and "Docker CLI" in docker_doc, docker_doc)
    expect("GAP-019-AG" in operations_doc and "deployment-exec-broker" in operations_doc, operations_doc)
    expect("GAP-019-AG" in data_safety_doc and "deployment-exec-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AH" in docker_doc and "gateway-exec-broker" in docker_doc and "Docker CLI" in docker_doc, docker_doc)
    expect("GAP-019-AH" in operations_doc and "gateway-exec-broker" in operations_doc, operations_doc)
    expect("GAP-019-AH" in data_safety_doc and "gateway-exec-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AY" in docker_doc and "gateway-exec-broker" in docker_doc and "config/arclink.env" in docker_doc, docker_doc)
    expect("GAP-019-AY" in operations_doc and "gateway-exec-broker" in operations_doc, operations_doc)
    expect("GAP-019-AY" in data_safety_doc and "gateway-exec-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-BC" in docker_doc and "gateway-exec-broker" in docker_doc and "_broker-incidents/gateway-exec-broker/rejections.jsonl" in docker_doc, docker_doc)
    expect("GAP-019-BC" in operations_doc and "gateway-exec-broker" in operations_doc, operations_doc)
    expect("GAP-019-BC" in data_safety_doc and "gateway-exec-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-BD" in docker_doc and "deployment-exec-broker" in docker_doc and "operator-upgrade-broker/rejections.jsonl" in docker_doc, docker_doc)
    expect("GAP-019-BD" in operations_doc and "agent-supervisor-broker" in operations_doc, operations_doc)
    expect("GAP-019-BD" in data_safety_doc and "agent-user-helper" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AI" in docker_doc and "operator-upgrade-broker" in docker_doc and "Docker CLI" in docker_doc, docker_doc)
    expect("GAP-019-AI" in operations_doc and "operator-upgrade-broker" in operations_doc, operations_doc)
    expect("GAP-019-AI" in data_safety_doc and "operator-upgrade-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AV" in docker_doc and "operator-upgrade-broker" in docker_doc and "deploy.sh" in docker_doc, docker_doc)
    expect("GAP-019-AV" in operations_doc and "operator-upgrade-broker" in operations_doc, operations_doc)
    expect("GAP-019-AV" in data_safety_doc and "operator-upgrade-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AW" in docker_doc and "operator-upgrade-broker" in docker_doc and "ARCLINK_UPSTREAM_DEPLOY_KEY_PATH" in docker_doc, docker_doc)
    expect("GAP-019-AW" in operations_doc and "operator-upgrade-broker" in operations_doc, operations_doc)
    expect("GAP-019-AW" in data_safety_doc and "operator-upgrade-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AK" in docker_doc and "internal Compose" in docker_doc and "default network" in docker_doc, docker_doc)
    expect("GAP-019-AK" in operations_doc and "internal Compose" in operations_doc, operations_doc)
    expect("GAP-019-AK" in data_safety_doc and "internal Compose" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AL" in docker_doc and TRUSTED_HOST_RISK_ENV in docker_doc and "accepted" in docker_doc, docker_doc)
    expect("GAP-019-AL" in operations_doc and TRUSTED_HOST_RISK_ENV in operations_doc and "accepted" in operations_doc, operations_doc)
    expect("GAP-019-AL" in data_safety_doc and TRUSTED_HOST_RISK_ENV in data_safety_doc and "accepted" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AP" in docker_doc and "127.0.0.1" in docker_doc and "0.0.0.0" in docker_doc, docker_doc)
    expect("GAP-019-AP" in operations_doc and "127.0.0.1" in operations_doc and "0.0.0.0" in operations_doc, operations_doc)
    expect("GAP-019-AP" in data_safety_doc and "127.0.0.1" in data_safety_doc and "0.0.0.0" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AQ" in docker_doc and "provisioner child" in docker_doc and "env allowlist" in docker_doc, docker_doc)
    expect("GAP-019-AQ" in operations_doc and "provisioner child" in operations_doc and "env allowlist" in operations_doc, operations_doc)
    expect("GAP-019-AQ" in data_safety_doc and "provisioner child" in data_safety_doc and "env allowlist" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AR" in docker_doc and "dashboard backend host" in docker_doc, docker_doc)
    expect("GAP-019-AR" in operations_doc and "dashboard backend host" in operations_doc, operations_doc)
    expect("GAP-019-AR" in data_safety_doc and "dashboard backend host" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AS" in docker_doc and "agent-home root" in docker_doc and "symlink" in docker_doc, docker_doc)
    expect("GAP-019-AS" in operations_doc and "agent-home root" in operations_doc and "symlink" in operations_doc, operations_doc)
    expect("GAP-019-AS" in data_safety_doc and "agent-home root" in data_safety_doc and "symlink" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AT" in docker_doc and "repo" in docker_doc and "runtime" in docker_doc and "symlink" in docker_doc, docker_doc)
    expect("GAP-019-AT" in operations_doc and "repo" in operations_doc and "runtime" in operations_doc, operations_doc)
    expect("GAP-019-AT" in data_safety_doc and "repo" in data_safety_doc and "runtime" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AU" in docker_doc and "command target" in docker_doc and "hermes-shell.sh" in docker_doc, docker_doc)
    expect("GAP-019-AU" in operations_doc and "command target" in operations_doc, operations_doc)
    expect("GAP-019-AU" in data_safety_doc and "command target" in data_safety_doc, data_safety_doc)
    print("PASS test_docker_authority_inventory_matches_compose_boundary")


def test_operator_upgrade_broker_runs_allowlisted_operator_upgrade() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(PYTHON_DIR / "arclink_operator_upgrade_broker.py", "arclink_operator_upgrade_broker_upgrade_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        container_priv = root / "container" / "arclink-priv"
        (repo / "bin").mkdir(parents=True)
        (priv / "state" / "operator-actions").mkdir(parents=True)
        (priv / "config").mkdir(parents=True)
        (repo / "deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "bin" / "component-upgrade.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "deploy.sh").chmod(0o755)
        (repo / "bin" / "component-upgrade.sh").chmod(0o755)
        docker_path = root / "trusted" / "docker"
        docker_path.parent.mkdir()
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)
        docker_binary = str(docker_path)
        old_env = os.environ.copy()
        os.environ["ARCLINK_DOCKER_HOST_REPO_DIR"] = str(repo)
        os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(container_priv)
        os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
        os.environ["ARCLINK_STATE_ROOT_BASE"] = "/arcdata/test-deployments"
        os.environ["ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN"] = "broker-token-must-not-reach-child"
        os.environ["ARCLINK_GATEWAY_EXEC_BROKER_TOKEN"] = "gateway-token-must-not-reach-child"
        os.environ["ARCLINK_FUTURE_CONTROL_TOKEN"] = "future-token-must-not-reach-child"
        os.environ["STRIPE_SECRET_KEY"] = "stripe-secret-must-not-reach-child"
        os.environ["CHUTES_API_KEY"] = "chutes-secret-must-not-reach-child"
        os.environ["DISCORD_BOT_TOKEN"] = "discord-secret-must-not-reach-child"
        os.environ["ARCLINK_SESSION_HASH_PEPPER"] = "pepper-must-not-reach-child"
        captured: list[dict[str, object]] = []

        def fake_run(args, **kwargs):
            captured.append({"args": list(args), "cwd": str(kwargs.get("cwd") or ""), "env": dict(kwargs.get("env") or {})})
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write("fake upgrade output\n")
            return subprocess.CompletedProcess(args=args, returncode=0)

        original_run = broker.subprocess.run
        original_which = broker.shutil.which
        original_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
        broker.subprocess.run = fake_run
        broker.shutil.which = lambda name: docker_binary if name == "docker" else None
        broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)
        try:
            requested_log_path = container_priv / "state" / "operator-actions" / "upgrade.log"
            log_path = priv / "state" / "operator-actions" / "upgrade.log"
            ok, payload = broker.run_operator_upgrade_request(
                {
                    "operation": "run_operator_upgrade",
                    "log_path": str(requested_log_path),
                    "upstream": {
                        "ARCLINK_UPSTREAM_REPO_URL": "git@example.com:arclink.git",
                        "ARCLINK_UPSTREAM_BRANCH": "arclink",
                    },
                }
            )
        finally:
            broker.subprocess.run = original_run
            broker.shutil.which = original_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = original_trusted
            os.environ.clear()
            os.environ.update(old_env)

        expect(ok is True, str(payload))
        expect(isinstance(payload, dict) and payload.get("returncode") == 0, str(payload))
        expect(captured and captured[0]["args"] == [str(repo / "deploy.sh"), "upgrade"], str(captured))
        env = captured[0]["env"]
        expect(isinstance(env, dict), str(captured))
        expect(env.get("ARCLINK_COMPONENT_UPGRADE_MODE") == "docker", str(env))
        expect(env.get("ARCLINK_BROKERED_CONTROL_UPGRADE") == "1", str(env))
        expect(env.get("ARCLINK_REPO_DIR") == str(repo), str(env))
        expect(env.get("ARCLINK_PRIV_DIR") == str(priv), str(env))
        expect(env.get("ARCLINK_UPSTREAM_BRANCH") == "arclink", str(env))
        expect(env.get("ARCLINK_DOCKER_HOST_REPO_DIR") == str(repo), str(env))
        expect(env.get("ARCLINK_DOCKER_HOST_PRIV_DIR") == str(priv), str(env))
        expect(env.get("ARCLINK_DOCKER_CONTAINER_PRIV_DIR") == str(container_priv), str(env))
        expect(env.get("ARCLINK_DOCKER_BINARY") == docker_binary, str(env))
        expect(env.get("ARCLINK_STATE_ROOT_BASE") == "/arcdata/test-deployments", str(env))
        for forbidden in (
            "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN",
            "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN",
            "ARCLINK_FUTURE_CONTROL_TOKEN",
            "STRIPE_SECRET_KEY",
            "CHUTES_API_KEY",
            "DISCORD_BOT_TOKEN",
            "ARCLINK_SESSION_HASH_PEPPER",
        ):
            expect(forbidden not in env, f"operator broker child env leaked {forbidden}: {env}")
        log_text = log_path.read_text(encoding="utf-8")
        expect("$ " in log_text and "deploy.sh upgrade" in log_text and "fake upgrade output" in log_text, log_text)
        expect(not requested_log_path.exists(), "container-style operator log path should be mapped to the host private bind")
    print("PASS test_operator_upgrade_broker_runs_allowlisted_operator_upgrade")


def test_operator_upgrade_broker_skips_deploy_when_pin_upgrade_noops() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(PYTHON_DIR / "arclink_operator_upgrade_broker.py", "arclink_operator_upgrade_broker_pin_noop_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        container_priv = root / "container" / "arclink-priv"
        (repo / "bin").mkdir(parents=True)
        (priv / "state" / "operator-actions").mkdir(parents=True)
        (priv / "config").mkdir(parents=True)
        (repo / "deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "bin" / "component-upgrade.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "deploy.sh").chmod(0o755)
        (repo / "bin" / "component-upgrade.sh").chmod(0o755)
        old_env = os.environ.copy()
        old_run = broker.subprocess.run
        os.environ["ARCLINK_DOCKER_HOST_REPO_DIR"] = str(repo)
        os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(container_priv)
        captured: list[list[str]] = []

        def fake_run(args, **kwargs):
            argv = list(args)
            captured.append(argv)
            stdout = kwargs.get("stdout")
            if argv[0].endswith("component-upgrade.sh"):
                if stdout is not None:
                    stdout.write("==> hermes-agent pin already at abc123 - no-op.\n")
                    stdout.write("ARCLINK_COMPONENT_UPGRADE_STATUS=noop\n")
            elif argv[0].endswith("deploy.sh"):
                raise AssertionError(f"stale no-op pin upgrade should not run deploy: {argv}")
            return subprocess.CompletedProcess(args=argv, returncode=0)

        try:
            broker.subprocess.run = fake_run
            requested_log_path = container_priv / "state" / "operator-actions" / "pin-upgrade.log"
            log_path = priv / "state" / "operator-actions" / "pin-upgrade.log"
            ok, payload = broker.run_operator_upgrade_request(
                {
                    "operation": "run_pin_upgrade",
                    "log_path": str(requested_log_path),
                    "install_items": [
                        {"component": "hermes-agent", "kind": "git-commit", "target": "abc123"},
                    ],
                }
            )
        finally:
            broker.subprocess.run = old_run
            os.environ.clear()
            os.environ.update(old_env)

        expect(ok is True and isinstance(payload, dict), str(payload))
        expect(payload.get("returncode") == 0, str(payload))
        expect(
            captured
            == [[str(repo / "bin" / "component-upgrade.sh"), "hermes-agent", "apply", "--ref", "abc123", "--skip-upgrade"]],
            str(captured),
        )
        log_text = log_path.read_text(encoding="utf-8")
        expect("ARCLINK_COMPONENT_UPGRADE_STATUS=noop" in log_text, log_text)
        expect("skipping deploy upgrade" in log_text and "deploy.sh upgrade" not in log_text, log_text)
        expect(not requested_log_path.exists(), "container-style operator log path should be mapped to the host private bind")
    print("PASS test_operator_upgrade_broker_skips_deploy_when_pin_upgrade_noops")


def test_operator_upgrade_broker_signature_replay_cache_is_bounded() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(PYTHON_DIR / "arclink_operator_upgrade_broker.py", "arclink_operator_upgrade_broker_replay_test")
    import hashlib
    import hmac

    body = b'{"operation":"run_operator_upgrade","log_path":"/priv/state/operator-actions/upgrade.log"}'

    def signed_headers(nonce: str, *, signature: str = "", timestamp: int = 0) -> dict[str, str]:
        clean_timestamp = timestamp or int(broker.time.time())
        if not signature:
            body_hash = hashlib.sha256(body).hexdigest()
            signature = hmac.new(
                b"test-operator-upgrade-token",
                f"{clean_timestamp}\n{nonce}\n{body_hash}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        return {
            broker.OPERATOR_UPGRADE_BROKER_TOKEN_HEADER: "test-operator-upgrade-token",
            broker.OPERATOR_UPGRADE_BROKER_TIMESTAMP_HEADER: str(clean_timestamp),
            broker.OPERATOR_UPGRADE_BROKER_NONCE_HEADER: nonce,
            broker.OPERATOR_UPGRADE_BROKER_SIGNATURE_HEADER: signature,
        }

    old_env = os.environ.copy()
    old_max = broker.MAX_SEEN_SIGNATURE_NONCES
    try:
        os.environ["ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN"] = "test-operator-upgrade-token"
        broker.MAX_SEEN_SIGNATURE_NONCES = 3
        broker._SEEN_SIGNATURE_NONCES.clear()

        reused_nonce = "nonce-reused-0001"
        expect(broker._is_authorized(signed_headers(reused_nonce, signature="0" * 64), body) is False, "bad signature accepted")
        expect(reused_nonce not in broker._SEEN_SIGNATURE_NONCES, "bad signature must not consume a replay-cache nonce")
        expect(broker._is_authorized(signed_headers(reused_nonce), body) is True, "valid signed request rejected")
        expect(broker._is_authorized(signed_headers(reused_nonce), body) is False, "valid nonce replay accepted")

        broker._SEEN_SIGNATURE_NONCES.clear()
        for index in range(4):
            nonce = f"nonce-bounded-{index:04d}"
            expect(broker._is_authorized(signed_headers(nonce), body) is True, f"valid nonce {nonce} rejected")
        expect(len(broker._SEEN_SIGNATURE_NONCES) <= 3, str(broker._SEEN_SIGNATURE_NONCES))
        expect("nonce-bounded-0000" not in broker._SEEN_SIGNATURE_NONCES, str(broker._SEEN_SIGNATURE_NONCES))
    finally:
        broker.MAX_SEEN_SIGNATURE_NONCES = old_max
        broker._SEEN_SIGNATURE_NONCES.clear()
        os.environ.clear()
        os.environ.update(old_env)
    print("PASS test_operator_upgrade_broker_signature_replay_cache_is_bounded")


def test_operator_upgrade_broker_rejects_raw_or_unsafe_requests() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(PYTHON_DIR / "arclink_operator_upgrade_broker.py", "arclink_operator_upgrade_broker_upgrade_reject_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        (repo / "bin").mkdir(parents=True)
        (priv / "state" / "operator-actions").mkdir(parents=True)
        (priv / "config").mkdir(parents=True)
        (repo / "deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "bin" / "component-upgrade.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "deploy.sh").chmod(0o755)
        (repo / "bin" / "component-upgrade.sh").chmod(0o755)
        old_env = os.environ.copy()
        os.environ["ARCLINK_DOCKER_HOST_REPO_DIR"] = str(repo)
        os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(priv)
        try:
            ok, error = broker.run_operator_upgrade_request(
                {
                    "operation": "run_operator_upgrade",
                    "command": [str(repo / "deploy.sh"), "upgrade"],
                    "log_path": str(priv / "state" / "operator-actions" / "upgrade.log"),
                }
            )
            expect(ok is False and "raw commands" in str(error), str(error))

            ok, error = broker.run_operator_upgrade_request(
                {
                    "operation": "run_operator_upgrade",
                    "log_path": str(root / "outside.log"),
                }
            )
            expect(ok is False and "operator log path" in str(error), str(error))

            ok, error = broker.run_operator_upgrade_request(
                {
                    "operation": "run_pin_upgrade",
                    "log_path": str(priv / "state" / "operator-actions" / "pin-upgrade.log"),
                    "install_items": [
                        {"component": "../bad", "kind": "git-commit", "target": "abc123"},
                    ],
                }
            )
            expect(ok is False and "component is not allowlisted" in str(error), str(error))
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_operator_upgrade_broker_rejects_raw_or_unsafe_requests")


def test_operator_upgrade_broker_rejects_symlinked_or_non_executable_repo_scripts_before_subprocess() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(
        PYTHON_DIR / "arclink_operator_upgrade_broker.py",
        "arclink_operator_upgrade_broker_script_target_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        container_priv = root / "container" / "arclink-priv"
        (repo / "bin").mkdir(parents=True)
        (priv / "state" / "operator-actions").mkdir(parents=True)
        (priv / "config").mkdir(parents=True)
        docker_path = root / "trusted" / "docker"
        docker_path.parent.mkdir()
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)

        old_env = os.environ.copy()
        old_run = broker.subprocess.run
        old_which = broker.shutil.which
        old_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
        captured: list[list[str]] = []

        def fake_run(args, **kwargs):
            captured.append(list(args))
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write("unexpected subprocess\n")
            return subprocess.CompletedProcess(args=args, returncode=0)

        def reset_repo_scripts() -> None:
            for path in (
                repo / "deploy.sh",
                repo / "deploy-real.sh",
                repo / "bin" / "component-upgrade.sh",
                repo / "bin" / "component-real.sh",
            ):
                if path.is_dir() and not path.is_symlink():
                    path.rmdir()
                elif path.exists() or path.is_symlink():
                    path.unlink()
            deploy = repo / "deploy.sh"
            component = repo / "bin" / "component-upgrade.sh"
            deploy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            component.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            deploy.chmod(0o755)
            component.chmod(0o755)

        upgrade_request = {
            "operation": "run_operator_upgrade",
            "log_path": str(container_priv / "state" / "operator-actions" / "upgrade.log"),
        }
        pin_request = {
            "operation": "run_pin_upgrade",
            "log_path": str(container_priv / "state" / "operator-actions" / "pin-upgrade.log"),
            "install_items": [{"component": "hermes-agent", "kind": "git-commit", "target": "abc123"}],
        }
        log_paths = [
            priv / "state" / "operator-actions" / "upgrade.log",
            priv / "state" / "operator-actions" / "pin-upgrade.log",
        ]

        def reject_case(label: str, mutate, request: dict[str, object]) -> None:
            reset_repo_scripts()
            for log_path in log_paths:
                if log_path.exists():
                    log_path.unlink()
            captured.clear()
            mutate()
            ok, payload = broker.run_operator_upgrade_request(request)
            expect(ok is False and "operator script" in str(payload), f"{label}: {payload}")
            expect(captured == [], f"{label}: unsafe script target reached subprocess.run: {captured}")
            for log_path in log_paths:
                expect(not log_path.exists(), f"{label}: rejected script target created private operator log {log_path}")

        def deploy_symlink() -> None:
            target = repo / "deploy-real.sh"
            target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            target.chmod(0o755)
            (repo / "deploy.sh").unlink()
            (repo / "deploy.sh").symlink_to(target)

        def deploy_directory() -> None:
            (repo / "deploy.sh").unlink()
            (repo / "deploy.sh").mkdir()

        def deploy_unreadable() -> None:
            deploy = repo / "deploy.sh"
            deploy.chmod(0o111)

        def deploy_non_executable() -> None:
            deploy = repo / "deploy.sh"
            deploy.chmod(0o644)

        def component_missing() -> None:
            (repo / "bin" / "component-upgrade.sh").unlink()

        def component_symlink() -> None:
            target = repo / "bin" / "component-real.sh"
            target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            target.chmod(0o755)
            (repo / "bin" / "component-upgrade.sh").unlink()
            (repo / "bin" / "component-upgrade.sh").symlink_to(target)

        def component_directory() -> None:
            (repo / "bin" / "component-upgrade.sh").unlink()
            (repo / "bin" / "component-upgrade.sh").mkdir()

        def component_unreadable() -> None:
            component = repo / "bin" / "component-upgrade.sh"
            component.chmod(0o111)

        def component_non_executable() -> None:
            component = repo / "bin" / "component-upgrade.sh"
            component.chmod(0o644)

        try:
            os.environ["ARCLINK_DOCKER_HOST_REPO_DIR"] = str(repo)
            os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
            os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(container_priv)
            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            broker.subprocess.run = fake_run
            broker.shutil.which = lambda name: str(docker_path) if name == "docker" else None
            broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)

            for label, mutate, request in (
                ("symlinked deploy.sh", deploy_symlink, upgrade_request),
                ("directory deploy.sh", deploy_directory, upgrade_request),
                ("unreadable deploy.sh", deploy_unreadable, upgrade_request),
                ("non-executable deploy.sh", deploy_non_executable, upgrade_request),
                ("missing component-upgrade.sh", component_missing, pin_request),
                ("symlinked component-upgrade.sh", component_symlink, pin_request),
                ("directory component-upgrade.sh", component_directory, pin_request),
                ("unreadable component-upgrade.sh", component_unreadable, pin_request),
                ("non-executable component-upgrade.sh", component_non_executable, pin_request),
            ):
                reject_case(label, mutate, request)
        finally:
            broker.subprocess.run = old_run
            broker.shutil.which = old_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = old_trusted
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_operator_upgrade_broker_rejects_symlinked_or_non_executable_repo_scripts_before_subprocess")


def test_operator_upgrade_broker_rejects_unscoped_upstream_deploy_key_paths_before_log_or_subprocess() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(
        PYTHON_DIR / "arclink_operator_upgrade_broker.py",
        "arclink_operator_upgrade_broker_upstream_path_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        container_priv = root / "container" / "arclink-priv"
        outside = root / "outside"
        (repo / "bin").mkdir(parents=True)
        (priv / "state" / "operator-actions").mkdir(parents=True)
        (priv / "config").mkdir(parents=True)
        outside.mkdir()
        (repo / "deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "bin" / "component-upgrade.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "deploy.sh").chmod(0o755)
        (repo / "bin" / "component-upgrade.sh").chmod(0o755)

        docker_path = root / "trusted" / "docker"
        docker_path.parent.mkdir()
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)

        safe_key = priv / "secrets" / "deploy-keys" / "arclink-upstream-ed25519"
        safe_known_hosts = priv / "secrets" / "deploy-keys" / "known_hosts"
        safe_key.parent.mkdir(parents=True)
        safe_key.write_text("redacted test key path only\n", encoding="utf-8")
        safe_known_hosts.write_text("github.com ssh-ed25519 redacted-test-key\n", encoding="utf-8")
        symlink_key = priv / "secrets" / "deploy-keys" / "symlink-key"
        symlink_known_hosts = priv / "secrets" / "deploy-keys" / "symlink-known-hosts"
        outside_key = outside / "arclink-upstream-ed25519"
        outside_known_hosts = outside / "known_hosts"
        outside_key.write_text("outside key\n", encoding="utf-8")
        outside_known_hosts.write_text("outside known hosts\n", encoding="utf-8")
        symlink_key.symlink_to(outside_key)
        symlink_known_hosts.symlink_to(outside_known_hosts)

        old_env = os.environ.copy()
        old_run = broker.subprocess.run
        old_which = broker.shutil.which
        old_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
        captured: list[dict[str, object]] = []

        def fake_run(args, **kwargs):
            captured.append({"args": list(args), "env": dict(kwargs.get("env") or {})})
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write("unexpected upstream path subprocess\n")
            return subprocess.CompletedProcess(args=args, returncode=0)

        def upgrade_request(*, key_path: str = "", known_hosts: str = "") -> dict[str, object]:
            upstream = {
                "ARCLINK_UPSTREAM_REPO_URL": "git@example.com:arclink.git",
                "ARCLINK_UPSTREAM_BRANCH": "arclink",
                "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED": "1",
                "ARCLINK_UPSTREAM_DEPLOY_KEY_USER": "operator",
            }
            if key_path:
                upstream["ARCLINK_UPSTREAM_DEPLOY_KEY_PATH"] = key_path
            if known_hosts:
                upstream["ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE"] = known_hosts
            return {
                "operation": "run_operator_upgrade",
                "log_path": str(container_priv / "state" / "operator-actions" / "upgrade.log"),
                "upstream": upstream,
            }

        log_path = priv / "state" / "operator-actions" / "upgrade.log"

        def reject_case(label: str, request: dict[str, object]) -> None:
            if log_path.exists():
                log_path.unlink()
            captured.clear()
            ok, payload = broker.run_operator_upgrade_request(request)
            expect(ok is False and "upstream" in str(payload) and "private" in str(payload), f"{label}: {payload}")
            expect(captured == [], f"{label}: unsafe upstream path reached subprocess.run: {captured}")
            expect(not log_path.exists(), f"{label}: unsafe upstream path created private operator log")

        try:
            os.environ["ARCLINK_DOCKER_HOST_REPO_DIR"] = str(repo)
            os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
            os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(container_priv)
            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            broker.subprocess.run = fake_run
            broker.shutil.which = lambda name: str(docker_path) if name == "docker" else None
            broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)

            reject_case(
                "outside upstream deploy key",
                upgrade_request(key_path=str(outside_key), known_hosts=str(safe_known_hosts)),
            )
            reject_case(
                "outside upstream known hosts",
                upgrade_request(key_path=str(safe_key), known_hosts=str(outside_known_hosts)),
            )
            reject_case(
                "relative upstream deploy key",
                upgrade_request(key_path="relative/key", known_hosts=str(safe_known_hosts)),
            )
            reject_case(
                "symlinked upstream deploy key",
                upgrade_request(key_path=str(symlink_key), known_hosts=str(safe_known_hosts)),
            )
            reject_case(
                "symlinked upstream known hosts",
                upgrade_request(key_path=str(safe_key), known_hosts=str(symlink_known_hosts)),
            )

            captured.clear()
            ok, payload = broker.run_operator_upgrade_request(
                upgrade_request(key_path=str(safe_key), known_hosts=str(safe_known_hosts))
            )
            expect(ok is True and isinstance(payload, dict), str(payload))
            expect(captured and captured[0]["args"] == [str(repo / "deploy.sh"), "upgrade"], str(captured))
            env = captured[0]["env"]
            expect(isinstance(env, dict), str(captured))
            expect(env.get("ARCLINK_BROKERED_CONTROL_UPGRADE") == "1", str(env))
            expect(env.get("ARCLINK_UPSTREAM_DEPLOY_KEY_PATH") == str(safe_key), str(env))
            expect(env.get("ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE") == str(safe_known_hosts), str(env))
        finally:
            broker.subprocess.run = old_run
            broker.shutil.which = old_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = old_trusted
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_operator_upgrade_broker_rejects_unscoped_upstream_deploy_key_paths_before_log_or_subprocess")


def test_operator_upgrade_broker_rejects_unsafe_docker_binary_before_subprocess() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(
        PYTHON_DIR / "arclink_operator_upgrade_broker.py",
        "arclink_operator_upgrade_broker_docker_binary_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        container_priv = root / "container" / "arclink-priv"
        (repo / "bin").mkdir(parents=True)
        (priv / "state" / "operator-actions").mkdir(parents=True)
        (priv / "config").mkdir(parents=True)
        (repo / "deploy.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "bin" / "component-upgrade.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        (repo / "deploy.sh").chmod(0o755)
        (repo / "bin" / "component-upgrade.sh").chmod(0o755)

        unsafe_dir = root / "unsafe"
        unsafe_dir.mkdir()
        unsafe_docker = unsafe_dir / "docker"
        unsafe_log = root / "unsafe-docker-called.log"
        unsafe_docker.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$0 $*\" >> {shlex.quote(str(unsafe_log))}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        unsafe_docker.chmod(0o755)

        trusted_docker = root / "trusted" / "docker"
        trusted_docker.parent.mkdir()
        trusted_docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        trusted_docker.chmod(0o755)
        trusted_docker_binary = str(trusted_docker)

        nonexec_docker = root / "nonexec" / "docker"
        nonexec_docker.parent.mkdir()
        nonexec_docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        requests = [
            {
                "operation": "run_operator_upgrade",
                "log_path": str(container_priv / "state" / "operator-actions" / "upgrade.log"),
            },
            {
                "operation": "run_pin_upgrade",
                "log_path": str(container_priv / "state" / "operator-actions" / "pin-upgrade.log"),
                "install_items": [
                    {"component": "hermes-agent", "kind": "git-commit", "target": "abc123"},
                ],
            },
        ]
        old_env = os.environ.copy()
        old_run = broker.subprocess.run
        old_which = broker.shutil.which
        old_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
        captured: list[dict[str, object]] = []

        def fake_run(args, **kwargs):
            captured.append({"args": list(args), "env": dict(kwargs.get("env") or {})})
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write("fake upgrade output\n")
            return subprocess.CompletedProcess(args=args, returncode=0)

        try:
            os.environ.clear()
            os.environ.update(old_env)
            os.environ["ARCLINK_DOCKER_HOST_REPO_DIR"] = str(repo)
            os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
            os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(container_priv)
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(root / "deployments")
            os.environ["ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN"] = "redacted-test-token"
            broker.subprocess.run = fake_run

            for configured in ("/bin/bash", "docker --host unix:///tmp/docker.sock", "relative/docker"):
                os.environ["ARCLINK_DOCKER_BINARY"] = configured
                ok, payload = broker.run_operator_upgrade_request(requests[0])
                expect(ok is False and "Docker CLI" in str(payload), f"{configured}: {payload}")

            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            os.environ["PATH"] = f"{unsafe_dir}:{old_env.get('PATH') or ''}"
            broker.shutil.which = old_which
            ok, payload = broker.run_operator_upgrade_request(requests[0])
            expect(ok is False and "not trusted" in str(payload), str(payload))
            expect(not unsafe_log.exists(), "PATH-injected fake docker must not be invoked")

            broker.TRUSTED_DOCKER_BINARY_PATHS = (nonexec_docker,)
            broker.shutil.which = lambda name: str(nonexec_docker) if name == "docker" else None
            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            ok, payload = broker.run_operator_upgrade_request(requests[0])
            expect(ok is False and "not executable" in str(payload), str(payload))

            broker.shutil.which = lambda name: None
            broker.TRUSTED_DOCKER_BINARY_PATHS = (trusted_docker,)
            ok, payload = broker.run_operator_upgrade_request(requests[0])
            expect(ok is False and "not available" in str(payload), str(payload))

            expect(captured == [], f"unsafe Docker binary must fail before subprocess.run: {captured}")

            broker.shutil.which = lambda name: trusted_docker_binary if name == "docker" else None
            for request in requests:
                os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
                ok, payload = broker.run_operator_upgrade_request(request)
                expect(ok is True and isinstance(payload, dict), str(payload))
            expect(len(captured) == 3, str(captured))
            for call in captured:
                env = call["env"]
                expect(isinstance(env, dict), str(call))
                expect(env.get("ARCLINK_DOCKER_BINARY") == trusted_docker_binary, str(env))
        finally:
            broker.subprocess.run = old_run
            broker.shutil.which = old_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = old_trusted
            os.environ.clear()
            os.environ.update(old_env)
    print("PASS test_operator_upgrade_broker_rejects_unsafe_docker_binary_before_subprocess")


def test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_docker_agent_supervisor.py",
        "arclink_docker_agent_supervisor_metadata_guard_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = SimpleNamespace(
            repo_dir=REPO,
            private_dir=root / "arclink-priv",
            state_dir=root / "arclink-priv" / "state",
            runtime_dir=root / "runtime",
            vault_dir=root / "arclink-priv" / "vault",
            agents_state_dir=root / "arclink-priv" / "state" / "agents",
        )
        home_root = cfg.state_dir / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        safe_agent = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "hermes_home": str(hermes_home),
            "channels_json": "[]",
        }
        old_home_root = os.environ.get("ARCLINK_DOCKER_AGENT_HOME_ROOT")
        os.environ.pop("ARCLINK_DOCKER_AGENT_HOME_ROOT", None)
        try:
            clean_agent, clean_home, clean_hermes_home = supervisor.validated_agent_context(cfg, safe_agent)
            expect(clean_agent["agent_id"] == "agent-test", str(clean_agent))
            expect(clean_agent["unix_user"] == "alex", str(clean_agent))
            expect(clean_home == home.resolve(strict=False), str(clean_home))
            expect(clean_hermes_home == hermes_home.resolve(strict=False), str(clean_hermes_home))

            def expect_rejected(fn, needle: str) -> None:
                try:
                    fn()
                except ValueError as exc:
                    expect(needle in str(exc), str(exc))
                    return
                raise AssertionError(f"expected rejection containing {needle!r}")

            helper_calls: list[tuple[str, dict[str, object]]] = []

            def fake_helper(operation, payload):
                helper_calls.append((operation, dict(payload)))
                return {"uid": 1234, "gid": 1234}

            old_helper = supervisor.agent_user_helper_request
            supervisor.agent_user_helper_request = fake_helper
            try:
                expect_rejected(
                    lambda: supervisor.ensure_container_user("agent-test", "bad;user", home, hermes_home, home_root=home_root),
                    "unix_user",
                )
                expect_rejected(
                    lambda: supervisor.ensure_container_user("agent-test", "alex", root / "outside" / "alex", hermes_home, home_root=home_root),
                    "agent home",
                )
            finally:
                supervisor.agent_user_helper_request = old_helper
            expect(helper_calls == [], f"unsafe metadata reached agent user helper operations: {helper_calls}")
            expect(not (root / "outside" / "alex").exists(), "unsafe home was created before validation")

            expect_rejected(
                lambda: supervisor.validated_agent_context(cfg, {**safe_agent, "agent_id": "../agent"}),
                "agent_id",
            )
            expect_rejected(
                lambda: supervisor.validated_agent_context(cfg, {**safe_agent, "hermes_home": str(root / "outside" / "hermes-home")}),
                "agent home",
            )
            expect_rejected(
                lambda: supervisor.user_env(cfg, {**safe_agent, "agent_id": "../agent"}, home, hermes_home),
                "agent_id",
            )
            expect(not (hermes_home / "workspace").exists(), "workspace was created before agent metadata validation")
            expect_rejected(lambda: supervisor.log_handle(cfg, "../bad"), "log name")
            expect(not (cfg.state_dir / "docker" / "bad.log").exists(), "unsafe log name escaped supervisor log directory")
            expect_rejected(lambda: supervisor.agent_process_context(cfg, {**safe_agent, "_docker_uid": "0", "_docker_gid": "23456"}, home, hermes_home), "agent uid")
            context = supervisor.agent_process_context(
                cfg,
                {**safe_agent, "_docker_uid": "23456", "_docker_gid": "23456"},
                home,
                hermes_home,
            )
            expect(context["uid"] == 23456 and context["gid"] == 23456, str(context))
            expect(context["home"] == str(home.resolve(strict=False)), str(context))
            expect(context["hermes_home"] == str(hermes_home.resolve(strict=False)), str(context))
            expect(context["workspace"] == str((hermes_home / "workspace").resolve(strict=False)), str(context))
            expect(context["env"]["ARCLINK_AGENT_UID"] == "23456", str(context))
            process_calls: list[tuple[str, dict[str, object]]] = []

            def fake_process_helper(operation, payload):
                process_calls.append((operation, dict(payload)))
                return {"desired": ["agent-test:gateway"], "started": [], "stopped": []}

            old_process_helper = supervisor.agent_process_helper_request
            supervisor.agent_process_helper_request = fake_process_helper
            try:
                supervisor.ensure_agent_processes([{**context, "kind": "gateway"}])
            finally:
                supervisor.agent_process_helper_request = old_process_helper
            expect(process_calls and process_calls[0][0] == "ensure_processes", str(process_calls))
            expect("command" not in process_calls[0][1] and "cmd" not in process_calls[0][1], str(process_calls))
        finally:
            if old_home_root is None:
                os.environ.pop("ARCLINK_DOCKER_AGENT_HOME_ROOT", None)
            else:
                os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = old_home_root
    print("PASS test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops")


def test_agent_user_helper_rejects_raw_commands_and_unscoped_paths() -> None:
    helper = load_python_module(PYTHON_DIR / "arclink_agent_user_helper.py", "arclink_agent_user_helper_contract_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home_root = root / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        def missing_entry(_value):
            raise KeyError(_value)

        old_run = helper.subprocess.run
        old_getpwnam = helper.pwd.getpwnam
        old_getpwuid = helper.pwd.getpwuid
        old_getgrnam = helper.grp.getgrnam
        old_getgrgid = helper.grp.getgrgid
        helper.subprocess.run = fake_run
        helper.pwd.getpwnam = missing_entry
        helper.pwd.getpwuid = missing_entry
        helper.grp.getgrnam = missing_entry
        helper.grp.getgrgid = missing_entry
        try:
            ok, payload = helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(home_root),
                    "home": str(home),
                    "hermes_home": str(hermes_home),
                    "workspace": str(workspace),
                }
            )
        finally:
            helper.subprocess.run = old_run
            helper.pwd.getpwnam = old_getpwnam
            helper.pwd.getpwuid = old_getpwuid
            helper.grp.getgrnam = old_getgrnam
            helper.grp.getgrgid = old_getgrgid

        expect(ok is True and isinstance(payload, dict), str(payload))
        groupadd = str(helper.TRUSTED_ROOT_EXECUTABLES["groupadd"])
        useradd = str(helper.TRUSTED_ROOT_EXECUTABLES["useradd"])
        chown = str(helper.TRUSTED_ROOT_EXECUTABLES["chown"])
        uid = payload.get("uid")
        gid = payload.get("gid")
        expect(isinstance(uid, int) and 20000 <= uid < 60000, str(payload))
        expect(uid == gid, str(payload))
        expect(home.is_dir() and hermes_home.is_dir() and workspace.is_dir(), "helper did not create canonical user paths")
        expect(any(command[:2] == [groupadd, "--gid"] and command[2] == str(gid) for command in commands), str(commands))
        expect(
            any(
                command[:1] == [useradd]
                and "--uid" in command
                and str(uid) in command
                and "--gid" in command
                and str(gid) in command
                and "--create-home" in command
                for command in commands
            ),
            str(commands),
        )
        expect(any(command[:3] == [chown, "-R", f"{uid}:{gid}"] and command[-1] == str(home) for command in commands), str(commands))
        assignment = json.loads((home_root / ".arclink-user-ids.json").read_text(encoding="utf-8"))
        expect(assignment.get("alex") == {"uid": uid, "gid": gid}, str(assignment))

        before = list(commands)
        ok, error = helper.run_agent_user_helper_request(
            {
                "operation": "ensure_user_home",
                "agent_id": "agent-test",
                "unix_user": "alex",
                "home_root": str(home_root),
                "home": str(home),
                "hermes_home": str(hermes_home),
                "cmd": ["useradd", "alex"],
            }
        )
        expect(ok is False and "raw commands" in str(error), str(error))
        ok, error = helper.run_agent_user_helper_request(
            {
                "operation": "ensure_user_home",
                "agent_id": "agent-test",
                "unix_user": "alex",
                "home_root": str(home_root),
                "home": str(root / "outside" / "alex"),
                "hermes_home": str(hermes_home),
            }
        )
        expect(ok is False and "agent home" in str(error), str(error))
        expect(commands == before, f"unsafe helper request reached subprocess: before={before} after={commands}")
    print("PASS test_agent_user_helper_rejects_raw_commands_and_unscoped_paths")


def test_agent_user_helper_requires_trusted_absolute_root_executables() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_user_helper.py",
        "arclink_agent_user_helper_trusted_executables_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home_root = root / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        def missing_entry(_value):
            raise KeyError(_value)

        old_run = helper.subprocess.run
        old_executables = dict(helper.TRUSTED_ROOT_EXECUTABLES)
        old_getpwnam = helper.pwd.getpwnam
        old_getpwuid = helper.pwd.getpwuid
        old_getgrnam = helper.grp.getgrnam
        old_getgrgid = helper.grp.getgrgid
        helper.subprocess.run = fake_run
        helper.TRUSTED_ROOT_EXECUTABLES["groupadd"] = root / "missing-groupadd"
        helper.pwd.getpwnam = missing_entry
        helper.pwd.getpwuid = missing_entry
        helper.grp.getgrnam = missing_entry
        helper.grp.getgrgid = missing_entry
        try:
            ok, error = helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(home_root),
                    "home": str(home),
                    "hermes_home": str(hermes_home),
                    "workspace": str(workspace),
                }
            )
        finally:
            helper.subprocess.run = old_run
            helper.TRUSTED_ROOT_EXECUTABLES.clear()
            helper.TRUSTED_ROOT_EXECUTABLES.update(old_executables)
            helper.pwd.getpwnam = old_getpwnam
            helper.pwd.getpwuid = old_getpwuid
            helper.grp.getgrnam = old_getgrnam
            helper.grp.getgrgid = old_getgrgid

        expect(ok is False and "required executable is unavailable" in str(error), str(error))
        expect(commands == [], f"missing trusted executable reached subprocess: {commands}")
        expect(not home.exists(), "missing trusted executable created the agent home")
        expect(
            not (home_root / ".arclink-user-ids.json").exists(),
            "missing trusted executable wrote a uid/gid assignment",
        )
    print("PASS test_agent_user_helper_requires_trusted_absolute_root_executables")


def test_agent_user_helper_rejects_configured_home_root_mismatch() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_user_helper.py",
        "arclink_agent_user_helper_configured_root_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        configured_home_root = root / "configured" / "users"
        requested_home_root = root / "requested" / "users"
        requested_home = requested_home_root / "alex"
        requested_hermes_home = requested_home / ".local" / "share" / "arclink-agent" / "hermes-home"
        requested_workspace = requested_hermes_home / "workspace"
        valid_home = configured_home_root / "alex"
        valid_hermes_home = valid_home / ".local" / "share" / "arclink-agent" / "hermes-home"
        valid_workspace = valid_hermes_home / "workspace"
        commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        def missing_entry(_value):
            raise KeyError(_value)

        old_env = os.environ.copy()
        old_run = helper.subprocess.run
        old_getpwnam = helper.pwd.getpwnam
        old_getpwuid = helper.pwd.getpwuid
        old_getgrnam = helper.grp.getgrnam
        old_getgrgid = helper.grp.getgrgid
        os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(configured_home_root)
        helper.subprocess.run = fake_run
        helper.pwd.getpwnam = missing_entry
        helper.pwd.getpwuid = missing_entry
        helper.grp.getgrnam = missing_entry
        helper.grp.getgrgid = missing_entry
        try:
            ok, error = helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(requested_home_root),
                    "home": str(requested_home),
                    "hermes_home": str(requested_hermes_home),
                    "workspace": str(requested_workspace),
                }
            )
            expect(ok is False and "ARCLINK_DOCKER_AGENT_HOME_ROOT" in str(error), str(error))
            expect(commands == [], f"configured-root mismatch reached subprocess: {commands}")
            expect(not requested_home.exists(), "configured-root mismatch created attacker-chosen home")
            expect(
                not (requested_home_root / ".arclink-user-ids.json").exists(),
                "configured-root mismatch wrote an attacker-chosen uid/gid assignment",
            )

            ok, payload = helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(configured_home_root),
                    "home": str(valid_home),
                    "hermes_home": str(valid_hermes_home),
                    "workspace": str(valid_workspace),
                }
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            helper.subprocess.run = old_run
            helper.pwd.getpwnam = old_getpwnam
            helper.pwd.getpwuid = old_getpwuid
            helper.grp.getgrnam = old_getgrnam
            helper.grp.getgrgid = old_getgrgid

        expect(ok is True and isinstance(payload, dict), str(payload))
        expect(valid_home.is_dir() and valid_hermes_home.is_dir() and valid_workspace.is_dir(), str(payload))
        expect(commands and commands[-1][:2] == [str(helper.TRUSTED_ROOT_EXECUTABLES["chown"]), "-R"], str(commands))
    print("PASS test_agent_user_helper_rejects_configured_home_root_mismatch")


def test_agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_user_helper.py",
        "arclink_agent_user_helper_assignment_file_test",
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_executables: dict[str, Path] = {}
        for name in ("groupadd", "useradd", "chown"):
            executable = fake_bin / name
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            fake_executables[name] = executable

        commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        def missing_entry(_value):
            raise KeyError(_value)

        def request_for(case_root: Path) -> tuple[dict[str, str], Path, Path, Path, Path]:
            home_root = case_root / "users"
            home = home_root / "alex"
            hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
            workspace = hermes_home / "workspace"
            return (
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(home_root),
                    "home": str(home),
                    "hermes_home": str(hermes_home),
                    "workspace": str(workspace),
                },
                home_root,
                home,
                hermes_home,
                workspace,
            )

        def reject_case(case_name: str, setup) -> None:
            case_root = root / case_name
            request, home_root, home, hermes_home, workspace = request_for(case_root)
            del hermes_home, workspace
            home_root.mkdir(parents=True)
            escaped_target = root / f"{case_name}-escaped.json"
            escaped_target.write_text("ORIGINAL\n", encoding="utf-8")
            setup(home_root, escaped_target)
            before_commands = list(commands)
            ok, error = helper.run_agent_user_helper_request(request)
            expect(ok is False and "id assignment" in str(error), f"{case_name}: {error}")
            expect(
                "ORIGINAL\n" == escaped_target.read_text(encoding="utf-8"),
                f"{case_name}: escaped assignment target was modified",
            )
            expect(commands == before_commands, f"{case_name}: reached root command: {commands}")
            expect(not home.exists(), f"{case_name}: created agent home before rejection")

        old_run = helper.subprocess.run
        old_executables = dict(helper.TRUSTED_ROOT_EXECUTABLES)
        old_getpwnam = helper.pwd.getpwnam
        old_getpwuid = helper.pwd.getpwuid
        old_getgrnam = helper.grp.getgrnam
        old_getgrgid = helper.grp.getgrgid
        helper.subprocess.run = fake_run
        helper.TRUSTED_ROOT_EXECUTABLES.clear()
        helper.TRUSTED_ROOT_EXECUTABLES.update(fake_executables)
        helper.pwd.getpwnam = missing_entry
        helper.pwd.getpwuid = missing_entry
        helper.grp.getgrnam = missing_entry
        helper.grp.getgrgid = missing_entry
        try:
            reject_case(
                "tmp-symlink",
                lambda home_root, escaped_target: (home_root / ".arclink-user-ids.json.tmp").symlink_to(
                    escaped_target
                ),
            )
            reject_case(
                "assignment-symlink",
                lambda home_root, escaped_target: (home_root / ".arclink-user-ids.json").symlink_to(
                    escaped_target
                ),
            )
            reject_case(
                "tmp-directory",
                lambda home_root, escaped_target: (home_root / ".arclink-user-ids.json.tmp").mkdir(),
            )
            reject_case(
                "assignment-directory",
                lambda home_root, escaped_target: (home_root / ".arclink-user-ids.json").mkdir(),
            )

            valid_request, valid_home_root, valid_home, valid_hermes, valid_workspace = request_for(root / "valid")
            ok, payload = helper.run_agent_user_helper_request(valid_request)
            expect(ok is True and isinstance(payload, dict), str(payload))
            expect(valid_home.is_dir() and valid_hermes.is_dir() and valid_workspace.is_dir(), str(payload))
            assignment = json.loads((valid_home_root / ".arclink-user-ids.json").read_text(encoding="utf-8"))
            expect(assignment.get("alex") == {"uid": payload.get("uid"), "gid": payload.get("gid")}, str(assignment))
        finally:
            helper.subprocess.run = old_run
            helper.TRUSTED_ROOT_EXECUTABLES.clear()
            helper.TRUSTED_ROOT_EXECUTABLES.update(old_executables)
            helper.pwd.getpwnam = old_getpwnam
            helper.pwd.getpwuid = old_getpwuid
            helper.grp.getgrnam = old_getgrnam
            helper.grp.getgrgid = old_getgrgid
    print("PASS test_agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work")


def test_agent_helpers_reject_symlink_escaped_agent_paths() -> None:
    user_helper = load_python_module(
        PYTHON_DIR / "arclink_agent_user_helper.py",
        "arclink_agent_user_helper_symlink_escape_test",
    )
    process_helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_symlink_escape_test",
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_executables: dict[str, Path] = {}
        for name in ("groupadd", "useradd", "chown"):
            executable = fake_bin / name
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            fake_executables[name] = executable

        user_commands: list[list[str]] = []
        process_run_commands: list[list[str]] = []
        process_popen_commands: list[list[str]] = []

        def fake_user_run(args, **kwargs):
            del kwargs
            user_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        def fake_process_run(args, **kwargs):
            del kwargs
            process_run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                process_popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        def missing_entry(_value):
            raise KeyError(_value)

        def process_env(home: Path, hermes_home: Path, workspace: Path) -> dict[str, str]:
            return {
                "PATH": process_helper.SAFE_PATH,
                "HOME": str(home.resolve(strict=False)),
                "USER": "alex",
                "LOGNAME": "alex",
                "HERMES_HOME": str(hermes_home.resolve(strict=False)),
                "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "ARCLINK_AGENT_UID": "23456",
                "ARCLINK_AGENT_GID": "23456",
            }

        def common_process_request(
            case_root: Path,
            home_root: Path,
            home: Path,
            hermes_home: Path,
            workspace: Path,
        ) -> dict[str, object]:
            repo = case_root / "repo"
            priv = case_root / "arclink-priv"
            state = priv / "state"
            runtime = case_root / "runtime"
            (repo / "bin").mkdir(parents=True, exist_ok=True)
            state.mkdir(parents=True, exist_ok=True)
            runtime.mkdir(parents=True, exist_ok=True)
            write_agent_process_helper_repo_targets(repo)
            return {
                "operation": "run_once",
                "kind": "refresh",
                "agent_id": "agent-test",
                "unix_user": "alex",
                "home_root": str(home_root),
                "home": str(home),
                "hermes_home": str(hermes_home),
                "workspace": str(workspace),
                "uid": 23456,
                "gid": 23456,
                "repo_dir": str(repo),
                "priv_dir": str(priv),
                "state_dir": str(state),
                "runtime_dir": str(runtime),
                "env": process_env(home, hermes_home, workspace),
            }

        def reject_user_case(
            case_root: Path,
            home_root: Path,
            home: Path,
            hermes_home: Path,
            workspace: Path,
        ) -> None:
            before = list(user_commands)
            ok, error = user_helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(home_root),
                    "home": str(home),
                    "hermes_home": str(hermes_home),
                    "workspace": str(workspace),
                }
            )
            expect(ok is False and "resolve outside" in str(error), str(error))
            expect(user_commands == before, f"symlink escape reached root user command: {user_commands}")
            expect(
                not (home_root / ".arclink-user-ids.json").exists(),
                "symlink escape wrote a uid/gid assignment before rejection",
            )

        def reject_process_case(
            case_root: Path,
            home_root: Path,
            home: Path,
            hermes_home: Path,
            workspace: Path,
        ) -> None:
            before_run = list(process_run_commands)
            before_popen = list(process_popen_commands)
            request = common_process_request(case_root, home_root, home, hermes_home, workspace)
            ok, error = process_helper.run_agent_process_helper_request(request)
            expect(ok is False and "resolve outside" in str(error), str(error))
            expect(
                process_run_commands == before_run,
                f"symlink escape reached subprocess.run: {process_run_commands}",
            )
            expect(
                process_popen_commands == before_popen,
                f"symlink escape reached subprocess.Popen: {process_popen_commands}",
            )
            log_dir = case_root / "arclink-priv" / "state" / "docker" / "agent-process-helper"
            expect(not log_dir.exists(), "symlink escape created process-helper logs before rejection")

        def home_escape(case_name: str) -> tuple[Path, Path, Path, Path, Path]:
            case_root = root / case_name
            home_root = case_root / "arclink-priv" / "state" / "docker" / "users"
            escaped_home = case_root / "escaped" / "alex"
            escaped_workspace = (
                escaped_home / ".local" / "share" / "arclink-agent" / "hermes-home" / "workspace"
            )
            home_root.mkdir(parents=True)
            escaped_workspace.mkdir(parents=True)
            (home_root / "alex").symlink_to(escaped_home, target_is_directory=True)
            home = home_root / "alex"
            hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
            workspace = hermes_home / "workspace"
            return case_root, home_root, home, hermes_home, workspace

        def hermes_escape(case_name: str) -> tuple[Path, Path, Path, Path, Path]:
            case_root = root / case_name
            home_root = case_root / "arclink-priv" / "state" / "docker" / "users"
            home = home_root / "alex"
            escaped_local = case_root / "escaped-local"
            escaped_workspace = escaped_local / "share" / "arclink-agent" / "hermes-home" / "workspace"
            home.mkdir(parents=True)
            escaped_workspace.mkdir(parents=True)
            (home / ".local").symlink_to(escaped_local, target_is_directory=True)
            hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
            workspace = hermes_home / "workspace"
            return case_root, home_root, home, hermes_home, workspace

        def workspace_escape(case_name: str) -> tuple[Path, Path, Path, Path, Path]:
            case_root = root / case_name
            home_root = case_root / "arclink-priv" / "state" / "docker" / "users"
            home = home_root / "alex"
            hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
            escaped_workspace = case_root / "escaped-workspace"
            hermes_home.mkdir(parents=True)
            escaped_workspace.mkdir(parents=True)
            (hermes_home / "workspace").symlink_to(escaped_workspace, target_is_directory=True)
            workspace = hermes_home / "workspace"
            return case_root, home_root, home, hermes_home, workspace

        old_user_run = user_helper.subprocess.run
        old_user_executables = dict(user_helper.TRUSTED_ROOT_EXECUTABLES)
        old_getpwnam = user_helper.pwd.getpwnam
        old_getpwuid = user_helper.pwd.getpwuid
        old_getgrnam = user_helper.grp.getgrnam
        old_getgrgid = user_helper.grp.getgrgid
        old_process_run = process_helper.subprocess.run
        old_process_popen = process_helper.subprocess.Popen
        user_helper.subprocess.run = fake_user_run
        user_helper.TRUSTED_ROOT_EXECUTABLES.clear()
        user_helper.TRUSTED_ROOT_EXECUTABLES.update(fake_executables)
        user_helper.pwd.getpwnam = missing_entry
        user_helper.pwd.getpwuid = missing_entry
        user_helper.grp.getgrnam = missing_entry
        user_helper.grp.getgrgid = missing_entry
        process_helper.subprocess.run = fake_process_run
        process_helper.subprocess.Popen = FakePopen
        process_helper.PROCESSES.clear()
        try:
            for factory, prefix in (
                (home_escape, "home"),
                (hermes_escape, "hermes"),
                (workspace_escape, "workspace"),
            ):
                user_case = factory(f"user-{prefix}")
                reject_user_case(*user_case)
                process_case = factory(f"process-{prefix}")
                reject_process_case(*process_case)

            valid_root = root / "valid"
            valid_home_root = valid_root / "arclink-priv" / "state" / "docker" / "users"
            valid_home = valid_home_root / "alex"
            valid_hermes = valid_home / ".local" / "share" / "arclink-agent" / "hermes-home"
            valid_workspace = valid_hermes / "workspace"
            ok, payload = user_helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(valid_home_root),
                    "home": str(valid_home),
                    "hermes_home": str(valid_hermes),
                    "workspace": str(valid_workspace),
                }
            )
            expect(ok is True and isinstance(payload, dict), str(payload))
            expect(valid_home.is_dir() and valid_hermes.is_dir() and valid_workspace.is_dir(), str(payload))

            process_request = common_process_request(
                valid_root,
                valid_home_root,
                valid_home,
                valid_hermes,
                valid_workspace,
            )
            ok, payload = process_helper.run_agent_process_helper_request(process_request)
            expect(ok is True and payload.get("returncode") == 0, str(payload))
            expect(
                process_run_commands and process_run_commands[-1][0] == process_helper.SETPRIV_BIN,
                str(process_run_commands),
            )
        finally:
            user_helper.subprocess.run = old_user_run
            user_helper.TRUSTED_ROOT_EXECUTABLES.clear()
            user_helper.TRUSTED_ROOT_EXECUTABLES.update(old_user_executables)
            user_helper.pwd.getpwnam = old_getpwnam
            user_helper.pwd.getpwuid = old_getpwuid
            user_helper.grp.getgrnam = old_getgrnam
            user_helper.grp.getgrgid = old_getgrgid
            process_helper.PROCESSES.clear()
            process_helper.subprocess.run = old_process_run
            process_helper.subprocess.Popen = old_process_popen
    print("PASS test_agent_helpers_reject_symlink_escaped_agent_paths")


def test_agent_helpers_reject_symlinked_home_root_before_root_work() -> None:
    user_helper = load_python_module(
        PYTHON_DIR / "arclink_agent_user_helper.py",
        "arclink_agent_user_helper_home_root_symlink_test",
    )
    process_helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_home_root_symlink_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        escaped_root = root / "escaped-users"
        configured_parent = root / "configured"
        escaped_root.mkdir()
        configured_parent.mkdir()
        home_root = configured_parent / "users"
        home_root.symlink_to(escaped_root, target_is_directory=True)
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"

        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_executables: dict[str, Path] = {}
        for name in ("groupadd", "useradd", "chown"):
            executable = fake_bin / name
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            fake_executables[name] = executable

        user_commands: list[list[str]] = []
        process_run_commands: list[list[str]] = []
        process_popen_commands: list[list[str]] = []

        def fake_user_run(args, **kwargs):
            del kwargs
            user_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        def fake_process_run(args, **kwargs):
            del kwargs
            process_run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                process_popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

        def missing_entry(_value):
            raise KeyError(_value)

        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        (repo / "bin").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir()

        process_request = {
            "operation": "run_once",
            "kind": "refresh",
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": {
                "PATH": process_helper.SAFE_PATH,
                "HOME": str(home),
                "USER": "alex",
                "LOGNAME": "alex",
                "HERMES_HOME": str(hermes_home),
                "ARCLINK_WORKSPACE_ROOT": str(workspace),
                "DRIVE_WORKSPACE_ROOT": str(workspace),
                "CODE_WORKSPACE_ROOT": str(workspace),
                "TERMINAL_WORKSPACE_ROOT": str(workspace),
                "ARCLINK_AGENT_UID": "23456",
                "ARCLINK_AGENT_GID": "23456",
            },
        }

        old_env = os.environ.copy()
        old_user_run = user_helper.subprocess.run
        old_user_executables = dict(user_helper.TRUSTED_ROOT_EXECUTABLES)
        old_getpwnam = user_helper.pwd.getpwnam
        old_getpwuid = user_helper.pwd.getpwuid
        old_getgrnam = user_helper.grp.getgrnam
        old_getgrgid = user_helper.grp.getgrgid
        old_process_run = process_helper.subprocess.run
        old_process_popen = process_helper.subprocess.Popen
        os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(home_root)
        os.environ["ARCLINK_REPO_DIR"] = str(repo)
        os.environ["ARCLINK_PRIV_DIR"] = str(priv)
        os.environ["RUNTIME_DIR"] = str(runtime)
        user_helper.subprocess.run = fake_user_run
        user_helper.TRUSTED_ROOT_EXECUTABLES.clear()
        user_helper.TRUSTED_ROOT_EXECUTABLES.update(fake_executables)
        user_helper.pwd.getpwnam = missing_entry
        user_helper.pwd.getpwuid = missing_entry
        user_helper.grp.getgrnam = missing_entry
        user_helper.grp.getgrgid = missing_entry
        process_helper.subprocess.run = fake_process_run
        process_helper.subprocess.Popen = FakePopen
        try:
            ok, error = user_helper.run_agent_user_helper_request(
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-test",
                    "unix_user": "alex",
                    "home_root": str(home_root),
                    "home": str(home),
                    "hermes_home": str(hermes_home),
                    "workspace": str(workspace),
                }
            )
            expect(ok is False and "agent home root" in str(error) and "symlink" in str(error), str(error))
            expect(user_commands == [], f"symlinked home root reached root user command: {user_commands}")
            expect(
                not (escaped_root / ".arclink-user-ids.json").exists(),
                "symlinked home root wrote a uid/gid assignment before rejection",
            )

            ok, error = process_helper.run_agent_process_helper_request(process_request)
            expect(ok is False and "agent home root" in str(error) and "symlink" in str(error), str(error))
            expect(
                process_run_commands == [],
                f"symlinked home root reached subprocess.run: {process_run_commands}",
            )
            expect(
                process_popen_commands == [],
                f"symlinked home root reached subprocess.Popen: {process_popen_commands}",
            )
            expect(
                (state / "docker" / "agent-process-helper" / "rejections.jsonl").exists(),
                "symlinked home root did not record a process-helper rejection incident",
            )
            expect(
                sorted(path.name for path in (state / "docker" / "agent-process-helper").glob("*.log")) == [],
                "symlinked home root created normal process-helper logs before rejection",
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            user_helper.subprocess.run = old_user_run
            user_helper.TRUSTED_ROOT_EXECUTABLES.clear()
            user_helper.TRUSTED_ROOT_EXECUTABLES.update(old_user_executables)
            user_helper.pwd.getpwnam = old_getpwnam
            user_helper.pwd.getpwuid = old_getpwuid
            user_helper.grp.getgrnam = old_getgrnam
            user_helper.grp.getgrgid = old_getgrgid
            process_helper.subprocess.run = old_process_run
            process_helper.subprocess.Popen = old_process_popen
    print("PASS test_agent_helpers_reject_symlinked_home_root_before_root_work")


def test_agent_process_helper_rejects_symlink_escaped_log_directory() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_log_symlink_escape_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_commands: list[list[str]] = []
        popen_commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        def common_request(case_root: Path) -> tuple[dict[str, object], Path, Path]:
            repo = case_root / "repo"
            priv = case_root / "arclink-priv"
            state = priv / "state"
            runtime = case_root / "runtime"
            home_root = state / "docker" / "users"
            home = home_root / "alex"
            hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
            workspace = hermes_home / "workspace"
            for path in (repo / "bin", workspace, runtime, state / "docker"):
                path.mkdir(parents=True, exist_ok=True)
            write_agent_process_helper_repo_targets(repo)
            env = {
                "PATH": helper.SAFE_PATH,
                "HOME": str(home.resolve(strict=False)),
                "USER": "alex",
                "LOGNAME": "alex",
                "HERMES_HOME": str(hermes_home.resolve(strict=False)),
                "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "ARCLINK_AGENT_UID": "23456",
                "ARCLINK_AGENT_GID": "23456",
            }
            request = {
                "agent_id": "agent-test",
                "unix_user": "alex",
                "home_root": str(home_root),
                "home": str(home),
                "hermes_home": str(hermes_home),
                "workspace": str(workspace),
                "uid": 23456,
                "gid": 23456,
                "repo_dir": str(repo),
                "priv_dir": str(priv),
                "state_dir": str(state),
                "runtime_dir": str(runtime),
                "env": env,
            }
            return request, state, case_root / "escaped-logs"

        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        helper.PROCESS_SIGNATURES.clear()
        try:
            common, state, escaped_logs = common_request(root / "escaped-run-once")
            escaped_logs.mkdir()
            (state / "docker" / "agent-process-helper").symlink_to(escaped_logs, target_is_directory=True)
            ok, error = helper.run_agent_process_helper_request(
                {**common, "operation": "run_once", "kind": "refresh"}
            )
            expect(ok is False and "log directory" in str(error) and "symlink" in str(error), str(error))
            expect(run_commands == [], f"log symlink escape reached subprocess.run: {run_commands}")
            expect(
                not (escaped_logs / "agent-test-refresh.log").exists(),
                "run_once wrote a helper log through a symlinked log directory",
            )

            common, state, escaped_logs = common_request(root / "escaped-ensure-processes")
            escaped_logs.mkdir()
            (state / "docker" / "agent-process-helper").symlink_to(escaped_logs, target_is_directory=True)
            ok, error = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [{**common, "kind": "gateway"}]}
            )
            expect(ok is False and "log directory" in str(error) and "symlink" in str(error), str(error))
            expect(popen_commands == [], f"log symlink escape reached subprocess.Popen: {popen_commands}")
            expect(
                not (escaped_logs / "agent-test-gateway.log").exists(),
                "ensure_processes wrote a helper log through a symlinked log directory",
            )

            common, state, _escaped_logs = common_request(root / "valid")
            ok, payload = helper.run_agent_process_helper_request(
                {**common, "operation": "run_once", "kind": "refresh"}
            )
            expect(ok is True and payload.get("returncode") == 0, str(payload))
            expect(run_commands and run_commands[-1][0] == helper.SETPRIV_BIN, str(run_commands))
            expect((state / "docker" / "agent-process-helper" / "agent-test-refresh.log").exists(), str(payload))

            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [{**common, "kind": "gateway"}]}
            )
            expect(ok is True and payload.get("desired") == ["agent-test:gateway"], str(payload))
            expect(popen_commands and popen_commands[-1][0] == helper.SETPRIV_BIN, str(popen_commands))
            expect((state / "docker" / "agent-process-helper" / "agent-test-gateway.log").exists(), str(payload))
        finally:
            helper.PROCESSES.clear()
            helper.PROCESS_SIGNATURES.clear()
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_rejects_symlink_escaped_log_directory")


def test_agent_process_helper_rejects_symlinked_or_missing_repo_command_targets_before_subprocess() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_repo_command_target_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_commands: list[list[str]] = []
        popen_commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        def common_request(case_name: str) -> dict[str, object]:
            case_root = root / case_name
            repo = case_root / "repo"
            priv = case_root / "arclink-priv"
            state = priv / "state"
            runtime = case_root / "runtime"
            home_root = state / "docker" / "users"
            home = home_root / "alex"
            hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
            workspace = hermes_home / "workspace"
            for path in (repo / "bin", repo / "python", workspace, runtime / "hermes-venv" / "bin", state):
                path.mkdir(parents=True, exist_ok=True)
            python_bin = runtime / "hermes-venv" / "bin" / "python3"
            python_bin.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            python_bin.chmod(0o755)
            env = {
                "PATH": helper.SAFE_PATH,
                "HOME": str(home.resolve(strict=False)),
                "USER": "alex",
                "LOGNAME": "alex",
                "HERMES_HOME": str(hermes_home.resolve(strict=False)),
                "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "ARCLINK_AGENT_UID": "23456",
                "ARCLINK_AGENT_GID": "23456",
            }
            return {
                "agent_id": "agent-test",
                "unix_user": "alex",
                "home_root": str(home_root),
                "home": str(home),
                "hermes_home": str(hermes_home),
                "workspace": str(workspace),
                "uid": 23456,
                "gid": 23456,
                "repo_dir": str(repo),
                "priv_dir": str(priv),
                "state_dir": str(state),
                "runtime_dir": str(runtime),
                "env": env,
            }

        def log_dir(request: dict[str, object]) -> Path:
            return Path(str(request["state_dir"])) / "docker" / "agent-process-helper"

        def expect_rejected(request: dict[str, object], call: dict[str, object], expected: str) -> None:
            before_run = list(run_commands)
            before_popen = list(popen_commands)
            ok, error = helper.run_agent_process_helper_request(call)
            expect(ok is False and "command target" in str(error) and expected in str(error), str(error))
            expect(run_commands == before_run, f"unsafe repo command target reached subprocess.run: {run_commands}")
            expect(popen_commands == before_popen, f"unsafe repo command target reached subprocess.Popen: {popen_commands}")
            expect(not log_dir(request).exists(), "unsafe repo command target created helper logs before rejection")

        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        helper.PROCESS_SIGNATURES.clear()
        try:
            missing_refresh = common_request("missing-refresh")
            expect_rejected(
                missing_refresh,
                {**missing_refresh, "operation": "run_once", "kind": "refresh"},
                "missing",
            )

            symlink_gateway = common_request("symlink-gateway")
            symlink_repo = Path(str(symlink_gateway["repo_dir"]))
            escaped_shell = root / "escaped-hermes-shell.sh"
            escaped_shell.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            escaped_shell.chmod(0o755)
            (symlink_repo / "bin" / "hermes-shell.sh").symlink_to(escaped_shell)
            expect_rejected(
                symlink_gateway,
                {"operation": "ensure_processes", "processes": [{**symlink_gateway, "kind": "gateway"}]},
                "symlink",
            )

            directory_install = common_request("directory-install")
            directory_repo = Path(str(directory_install["repo_dir"]))
            write_agent_process_helper_repo_targets(directory_repo)
            (directory_repo / "bin" / "install-agent-user-services.sh").unlink()
            (directory_repo / "bin" / "install-agent-user-services.sh").mkdir()
            expect_rejected(
                directory_install,
                {
                    **directory_install,
                    "operation": "run_once",
                    "kind": "install",
                    "channels": ["telegram"],
                },
                "regular file",
            )

            unreadable_cron = common_request("unreadable-cron")
            unreadable_repo = Path(str(unreadable_cron["repo_dir"]))
            write_agent_process_helper_repo_targets(unreadable_repo)
            (unreadable_repo / "bin" / "hermes-shell.sh").chmod(0o111)
            expect_rejected(
                unreadable_cron,
                {**unreadable_cron, "operation": "run_once", "kind": "cron"},
                "readable",
            )

            non_executable_dashboard = common_request("non-executable-dashboard")
            non_executable_repo = Path(str(non_executable_dashboard["repo_dir"]))
            write_agent_process_helper_repo_targets(non_executable_repo)
            (non_executable_repo / "bin" / "hermes-shell.sh").chmod(0o644)
            expect_rejected(
                non_executable_dashboard,
                {
                    "operation": "ensure_processes",
                    "processes": [
                        {
                            **non_executable_dashboard,
                            "kind": "dashboard",
                            "dashboard_backend_host": "127.0.0.1",
                            "dashboard_backend_port": "8100",
                        }
                    ],
                },
                "executable",
            )

            missing_identity = common_request("missing-identity")
            expect_rejected(
                missing_identity,
                {
                    **missing_identity,
                    "operation": "run_once",
                    "kind": "identity",
                    "bot_name": "Alex Bot",
                    "user_name": "Alex",
                },
                "missing",
            )

            symlink_identity = common_request("symlink-identity")
            symlink_identity_repo = Path(str(symlink_identity["repo_dir"]))
            escaped_identity = root / "escaped-identity.py"
            escaped_identity.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            escaped_identity.chmod(0o644)
            (symlink_identity_repo / "python" / "arclink_headless_hermes_setup.py").symlink_to(escaped_identity)
            expect_rejected(
                symlink_identity,
                {
                    **symlink_identity,
                    "operation": "run_once",
                    "kind": "identity",
                    "bot_name": "Alex Bot",
                    "user_name": "Alex",
                },
                "symlink",
            )

            valid = common_request("valid")
            write_agent_process_helper_repo_targets(Path(str(valid["repo_dir"])))
            ok, payload = helper.run_agent_process_helper_request({**valid, "operation": "run_once", "kind": "refresh"})
            expect(ok is True and payload.get("returncode") == 0, str(payload))
            expect(run_commands and run_commands[-1][0] == helper.SETPRIV_BIN, str(run_commands))
            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [{**valid, "kind": "gateway"}]}
            )
            expect(ok is True and payload.get("desired") == ["agent-test:gateway"], str(payload))
            expect(popen_commands and popen_commands[-1][0] == helper.SETPRIV_BIN, str(popen_commands))
        finally:
            helper.PROCESSES.clear()
            helper.PROCESS_SIGNATURES.clear()
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_rejects_symlinked_or_missing_repo_command_targets_before_subprocess")


def test_docker_agent_supervisor_requires_user_helper_before_root_user_ops() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_docker_agent_supervisor.py",
        "arclink_docker_agent_supervisor_user_helper_required_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home_root = root / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        old_env = os.environ.copy()
        try:
            os.environ.pop("ARCLINK_AGENT_USER_HELPER_URL", None)
            os.environ.pop("ARCLINK_AGENT_USER_HELPER_TOKEN", None)
            try:
                supervisor.ensure_container_user("agent-test", "alex", home, hermes_home, home_root=home_root)
            except RuntimeError as exc:
                expect("ARCLINK_AGENT_USER_HELPER_URL" in str(exc), str(exc))
            else:
                raise AssertionError("expected Docker agent supervisor to fail closed without agent user helper config")
            expect(not home.exists(), "supervisor created the user home without helper config")

            os.environ["ARCLINK_AGENT_USER_HELPER_URL"] = "http://agent-user-helper.test"
            os.environ["ARCLINK_AGENT_USER_HELPER_TOKEN"] = "helper-token"
            captured: list[tuple[str, dict[str, object]]] = []

            def fake_helper(operation, payload):
                captured.append((operation, dict(payload)))
                return {"uid": 1234, "gid": 1234}

            old_helper = supervisor.agent_user_helper_request
            supervisor.agent_user_helper_request = fake_helper
            try:
                uid, gid = supervisor.ensure_container_user("agent-test", "alex", home, hermes_home, home_root=home_root)
            finally:
                supervisor.agent_user_helper_request = old_helper
        finally:
            os.environ.clear()
            os.environ.update(old_env)

        expect((uid, gid) == (1234, 1234), f"unexpected helper uid/gid: {(uid, gid)}")
        expect(len(captured) == 1, str(captured))
        operation, payload = captured[0]
        expect(operation == "ensure_user_home", str(captured))
        expect(payload["agent_id"] == "agent-test" and payload["unix_user"] == "alex", str(payload))
        expect(payload["home_root"] == str(home_root.resolve(strict=False)), str(payload))
        expect(payload["home"] == str(home.resolve(strict=False)), str(payload))
        expect(payload["hermes_home"] == str(hermes_home.resolve(strict=False)), str(payload))
        expect(payload["workspace"] == str((hermes_home / "workspace").resolve(strict=False)), str(payload))
        expect(not any(key in payload for key in ("args", "cmd", "command")), str(payload))
    print("PASS test_docker_agent_supervisor_requires_user_helper_before_root_user_ops")


def test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops() -> None:
    helper = load_python_module(PYTHON_DIR / "arclink_agent_process_helper.py", "arclink_agent_process_helper_contract_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        home_root = state / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        (repo / "bin").mkdir(parents=True)
        (repo / "python").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir(parents=True)
        write_agent_process_helper_repo_targets(repo)
        env = {
            "PATH": helper.SAFE_PATH,
            "HOME": str(home.resolve(strict=False)),
            "USER": "alex",
            "LOGNAME": "alex",
            "HERMES_HOME": str(hermes_home.resolve(strict=False)),
            "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "ARCLINK_AGENT_UID": "23456",
            "ARCLINK_AGENT_GID": "23456",
        }
        common = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": env,
        }
        run_commands: list[list[str]] = []
        run_envs: list[dict[str, str]] = []
        popen_commands: list[list[str]] = []
        popen_envs: list[dict[str, str]] = []
        terminated: list[bool] = []

        def fake_run(args, **kwargs):
            run_commands.append(list(args))
            run_envs.append(dict(kwargs.get("env") or {}))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                self.args = list(args)
                self.returncode = None
                popen_commands.append(self.args)
                popen_envs.append(dict(kwargs.get("env") or {}))

            def poll(self):
                return self.returncode

            def terminate(self):
                terminated.append(True)
                self.returncode = -15

        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        try:
            ok, payload = helper.run_agent_process_helper_request(
                {
                    **common,
                    "operation": "run_once",
                    "kind": "install",
                    "channels": ["telegram"],
                }
            )
            expect(ok is True and payload.get("returncode") == 0, str(payload))
            expect(run_commands and run_commands[0][0] == helper.SETPRIV_BIN, str(run_commands))
            expect(Path(run_commands[0][0]).is_absolute(), str(run_commands))
            expect("install-agent-user-services.sh" in " ".join(run_commands[0]), str(run_commands))
            expect("HOME=" not in " ".join(run_commands[0]) and "HERMES_HOME=" not in " ".join(run_commands[0]), str(run_commands))
            expect(run_envs and run_envs[0].get("HERMES_HOME") == str(hermes_home.resolve(strict=False)), str(run_envs))
            expect(run_envs[0].get("PATH") == helper.SAFE_PATH, str(run_envs))
            before = list(run_commands)
            ok, error = helper.run_agent_process_helper_request({**common, "operation": "run_once", "kind": "refresh", "cmd": ["bad"]})
            expect(ok is False and "raw commands" in str(error), str(error))
            ok, error = helper.run_agent_process_helper_request({**common, "operation": "run_once", "kind": "refresh", "env": {**env, "bad-key": "x"}})
            expect(ok is False and "env key" in str(error), str(error))
            ok, error = helper.run_agent_process_helper_request(
                {
                    **common,
                    "operation": "run_once",
                    "kind": "refresh",
                    "env": {**env, "PATH": str(root / "malicious-bin")},
                }
            )
            expect(ok is False and "safe helper PATH" in str(error), str(error))
            ok, error = helper.run_agent_process_helper_request(
                {
                    **common,
                    "operation": "run_once",
                    "kind": "refresh",
                    "env": {**env, "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN": "fake-local-token"},
                }
            )
            expect(ok is False and "control token" in str(error), str(error))
            ok, error = helper.run_agent_process_helper_request(
                {
                    **common,
                    "operation": "run_once",
                    "kind": "refresh",
                    "env": {**env, "ARCLINK_FUTURE_HELPER_TOKEN": "fake-local-token"},
                }
            )
            expect(ok is False and "control token" in str(error), str(error))
            expect(run_commands == before, f"unsafe helper request reached subprocess: before={before} after={run_commands}")
            ok, error = helper.run_agent_process_helper_request(
                {
                    **common,
                    "operation": "run_once",
                    "kind": "identity",
                    "bot_name": "Alex Bot",
                    "user_name": "Alex",
                }
            )
            expect(ok is False and "identity python interpreter" in str(error), str(error))
            expect(run_commands == before, f"missing runtime python reached subprocess: before={before} after={run_commands}")
            python_bin = runtime / "hermes-venv" / "bin" / "python3"
            python_bin.parent.mkdir(parents=True, exist_ok=True)
            python_bin.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            ok, payload = helper.run_agent_process_helper_request(
                {
                    **common,
                    "operation": "run_once",
                    "kind": "identity",
                    "bot_name": "Alex Bot",
                    "user_name": "Alex",
                }
            )
            expect(ok is True and payload.get("returncode") == 0, str(payload))
            identity_command = run_commands[-1]
            expect(identity_command[0] == helper.SETPRIV_BIN, str(identity_command))
            expect(identity_command[identity_command.index("--") + 1] == str(python_bin), str(identity_command))
            expect("python3" != identity_command[identity_command.index("--") + 1], str(identity_command))
            ok, error = helper.run_agent_process_helper_request(
                {
                    "operation": "ensure_processes",
                    "processes": [
                        {
                            **common,
                            "kind": "gateway",
                            "env": {**env, "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN": "fake-local-token"},
                        }
                    ],
                }
            )
            expect(ok is False and "control token" in str(error), str(error))
            expect(popen_commands == [], f"unsafe helper process request reached Popen: {popen_commands}")
            ok, error = helper.run_agent_process_helper_request(
                {
                    "operation": "ensure_processes",
                    "processes": [
                        {
                            **common,
                            "kind": "gateway",
                            "env": {**env, "PATH": str(root / "malicious-bin")},
                        }
                    ],
                }
            )
            expect(ok is False and "safe helper PATH" in str(error), str(error))
            expect(popen_commands == [], f"malicious PATH process request reached Popen: {popen_commands}")
            ok, payload = helper.run_agent_process_helper_request(
                {
                    "operation": "ensure_processes",
                    "processes": [{**common, "kind": "gateway"}],
                }
            )
            expect(ok is True and payload.get("desired") == ["agent-test:gateway"], str(payload))
            expect(popen_commands and popen_commands[0][0] == helper.SETPRIV_BIN, str(popen_commands))
            expect(Path(popen_commands[0][0]).is_absolute(), str(popen_commands))
            expect("gateway" in popen_commands[0] and "run" in popen_commands[0] and "--replace" in popen_commands[0], str(popen_commands))
            expect("HOME=" not in " ".join(popen_commands[0]) and "HERMES_HOME=" not in " ".join(popen_commands[0]), str(popen_commands))
            expect(popen_envs and popen_envs[0].get("HOME") == str(home.resolve(strict=False)), str(popen_envs))
            expect(popen_envs[0].get("PATH") == helper.SAFE_PATH, str(popen_envs))
            ok, payload = helper.run_agent_process_helper_request({"operation": "ensure_processes", "processes": []})
            expect(ok is True and terminated, str(payload))
        finally:
            helper.PROCESSES.clear()
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops")


def test_agent_process_helper_records_redacted_rejection_incident_before_subprocess() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_rejection_incident_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        home_root = state / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        (repo / "bin").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir(parents=True)
        workspace.mkdir(parents=True)
        write_agent_process_helper_repo_targets(repo)
        env = {
            "PATH": helper.SAFE_PATH,
            "HOME": str(home.resolve(strict=False)),
            "USER": "alex",
            "LOGNAME": "alex",
            "HERMES_HOME": str(hermes_home.resolve(strict=False)),
            "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "ARCLINK_AGENT_UID": "23456",
            "ARCLINK_AGENT_GID": "23456",
        }
        common = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": env,
        }
        incident_path = state / "docker" / "agent-process-helper" / "rejections.jsonl"
        run_commands: list[list[str]] = []
        popen_commands: list[list[str]] = []
        private_path_marker = str(root)
        command_marker = "raw-command-marker"
        env_value_marker = "env-value-marker"
        host_marker = "8.8.8.8"

        def fake_run(args, **kwargs):
            del kwargs
            run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        old_env = os.environ.copy()
        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        os.environ[TRUSTED_HOST_RISK_ENV] = TRUSTED_HOST_RISK_ACCEPTED
        os.environ["ARCLINK_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(home_root)
        os.environ["ARCLINK_REPO_DIR"] = str(repo)
        os.environ["RUNTIME_DIR"] = str(runtime)
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        helper.PROCESS_SIGNATURES.clear()
        try:
            unsafe_requests = [
                (
                    {**common, "operation": "run_once", "kind": "refresh", "cmd": [command_marker]},
                    "raw_command_rejected",
                ),
                (
                    {
                        **common,
                        "operation": "run_once",
                        "kind": "refresh",
                        "env": {**env, "PYTHONPATH": str(root / env_value_marker)},
                    },
                    "unapproved_env_rejected",
                ),
                (
                    {
                        "operation": "ensure_processes",
                        "processes": [
                            {
                                **common,
                                "kind": "dashboard",
                                "dashboard_backend_host": host_marker,
                                "dashboard_backend_port": "8100",
                            }
                        ],
                    },
                    "dashboard_backend_host_rejected",
                ),
            ]
            for request, expected_reason in unsafe_requests:
                ok, error = helper.run_agent_process_helper_request(request)
                expect(ok is False, f"unsafe request unexpectedly succeeded: {error}")
                expect(expected_reason.split("_")[0] in str(error) or "not approved" in str(error), str(error))

            expect(run_commands == [] and popen_commands == [], f"rejected request reached subprocess: {run_commands} {popen_commands}")
            expect(helper.PROCESSES == {} and helper.PROCESS_SIGNATURES == {}, "rejected request mutated process state")
            expect(incident_path.exists(), "rejected helper requests did not create a private-state incident log")
            rows = [json.loads(line) for line in incident_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            expect([row.get("reason") for row in rows] == [item[1] for item in unsafe_requests], str(rows))
            for row in rows:
                expect(row.get("service") == "agent-process-helper", str(row))
                expect(row.get("agent_id") == "agent-test", str(row))
                expect(row.get("trusted_host_acknowledged") is True, str(row))
                expect(row.get("error_class") == "ValueError", str(row))
                expect(str(row.get("timestamp") or "").endswith("Z"), str(row))
            incident_text = incident_path.read_text(encoding="utf-8")
            for forbidden in (
                private_path_marker,
                command_marker,
                env_value_marker,
                host_marker,
                "PYTHONPATH",
                '"cmd"',
                '"command"',
                "raw-command-marker",
            ):
                expect(forbidden not in incident_text, f"incident log leaked {forbidden}: {incident_text}")
            normal_logs = sorted(path.name for path in incident_path.parent.glob("*.log"))
            expect(normal_logs == [], f"rejected requests created normal helper logs: {normal_logs}")
            ok, payload = helper.run_agent_process_helper_request({"operation": "terminate_all"})
            expect(ok is True and payload.get("stopped") == [], str(payload))
            rows_after_terminate = [
                json.loads(line) for line in incident_path.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            expect(rows_after_terminate == rows, "terminate_all appended a rejection incident")
        finally:
            helper.PROCESSES.clear()
            helper.PROCESS_SIGNATURES.clear()
            os.environ.clear()
            os.environ.update(old_env)
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_records_redacted_rejection_incident_before_subprocess")


def test_remaining_high_authority_services_record_redacted_rejection_incidents() -> None:
    deployment = load_python_module(
        PYTHON_DIR / "arclink_deployment_exec_broker.py",
        "arclink_deployment_exec_broker_rejection_incident_test",
    )
    migration = load_python_module(
        PYTHON_DIR / "arclink_migration_capture_helper.py",
        "arclink_migration_capture_helper_rejection_incident_test",
    )
    user_helper = load_python_module(
        PYTHON_DIR / "arclink_agent_user_helper.py",
        "arclink_agent_user_helper_rejection_incident_test",
    )
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_agent_supervisor_broker.py",
        "arclink_agent_supervisor_broker_rejection_incident_test",
    )
    operator = load_python_module(
        PYTHON_DIR / "arclink_operator_upgrade_broker.py",
        "arclink_operator_upgrade_broker_rejection_incident_test",
    )

    old_env = os.environ.copy()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state_root = root / "deployments"
        priv = root / "arclink-priv"
        home_root = priv / "state" / "docker" / "users"
        state_root.mkdir()
        (priv / "state" / "docker").mkdir(parents=True)
        home_root.mkdir(parents=True)
        os.environ.clear()
        os.environ.update(old_env)
        os.environ[TRUSTED_HOST_RISK_ENV] = TRUSTED_HOST_RISK_ACCEPTED
        os.environ["ARCLINK_STATE_ROOT_BASE"] = str(state_root)
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = str(priv)
        os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(home_root)

        forbidden_secret = "incident-secret-token-should-not-log"
        forbidden_command = "--privileged"
        cases = [
            (
                "deployment-exec-broker",
                deployment.run_deployment_exec_request,
                {
                    "operation": "compose_up",
                    "deployment_id": "arcdep_demo",
                    "project_name": "arclink-arcdep_demo",
                    "env_file": str(root / "secret-env-path"),
                    "compose_file": str(root / "secret-compose-path"),
                    "cmd": ["docker", "run", forbidden_command, forbidden_secret],
                },
                state_root / "_broker-incidents" / "deployment-exec-broker" / "rejections.jsonl",
                "deployment_exec_broker_request_rejected",
                "raw_command_rejected",
            ),
            (
                "migration-capture-helper",
                migration.run_migration_capture_request,
                {
                    "operation": "capture",
                    "deployment_id": "arcdep_demo",
                    "prefix": "arc-demo",
                    "migration_id": "mig_demo",
                    "source_state_root": str(root / "secret-source"),
                    "target_state_root": str(root / "secret-target"),
                    "capture_dir": str(root / "secret-capture"),
                    "command": [forbidden_command, forbidden_secret],
                },
                state_root / "_helper-incidents" / "migration-capture-helper" / "rejections.jsonl",
                "migration_capture_helper_request_rejected",
                "raw_command_rejected",
            ),
            (
                "agent-user-helper",
                user_helper.run_agent_user_helper_request,
                {
                    "operation": "ensure_user_home",
                    "agent_id": "agent-demo",
                    "unix_user": "alex",
                    "home_root": str(home_root),
                    "home": str(home_root / "alex"),
                    "hermes_home": str(home_root / "alex" / ".local/share/arclink-agent/hermes-home"),
                    "workspace": str(home_root / "alex" / ".local/share/arclink-agent/hermes-home/workspace"),
                    "args": [forbidden_command, forbidden_secret],
                },
                home_root / ".helper-incidents" / "agent-user-helper" / "rejections.jsonl",
                "agent_user_helper_request_rejected",
                "raw_command_rejected",
            ),
            (
                "agent-supervisor-broker",
                supervisor.run_agent_supervisor_request,
                {
                    "operation": "ensure_dashboard_network",
                    "agent_id": "agent-demo",
                    "supervisor_container": "arclink-agent-supervisor-1",
                    "cmd": ["docker", "network", "connect", forbidden_command, forbidden_secret],
                },
                priv / "state" / "docker" / "agent-supervisor-broker" / "rejections.jsonl",
                "agent_supervisor_broker_request_rejected",
                "raw_command_rejected",
            ),
            (
                "operator-upgrade-broker",
                operator.run_operator_upgrade_request,
                {
                    "operation": "run_operator_upgrade",
                    "log_path": str(priv / "state" / "operator-actions" / "secret.log"),
                    "cmd": ["./deploy.sh", "docker", "upgrade", forbidden_command, forbidden_secret],
                },
                priv / "state" / "docker" / "operator-upgrade-broker" / "rejections.jsonl",
                "operator_upgrade_broker_request_rejected",
                "raw_command_rejected",
            ),
        ]

        for service, runner, request, incident_path, event, reason in cases:
            ok, error = runner(request)
            expect(ok is False, f"{service} raw command request unexpectedly succeeded: {error}")
            expect("secret" not in str(error).lower(), f"{service} leaked request detail in error: {error}")
            expect(incident_path.exists(), f"{service} did not write {incident_path}")
            rows = [json.loads(line) for line in incident_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            expect(len(rows) == 1, f"{service} wrote unexpected incident rows: {rows}")
            row = rows[0]
            expect(row.get("service") == service, str(row))
            expect(row.get("event") == event, str(row))
            expect(row.get("reason") == reason, str(row))
            expect(row.get("trusted_host_acknowledged") is True, str(row))
            expect(row.get("error_class") == "ValueError", str(row))
            expect("timestamp" in row and str(row["timestamp"]).endswith("Z"), str(row))
            incident_text = incident_path.read_text(encoding="utf-8")
            for forbidden in (
                forbidden_secret,
                forbidden_command,
                "secret-env-path",
                "secret-compose-path",
                "secret-source",
                "secret-target",
                "secret-capture",
                "secret.log",
                '"cmd"',
                '"command"',
                '"args"',
            ):
                expect(forbidden not in incident_text, f"{service} incident log leaked {forbidden}: {incident_text}")
    os.environ.clear()
    os.environ.update(old_env)
    print("PASS test_remaining_high_authority_services_record_redacted_rejection_incidents")


def test_agent_process_helper_rejects_unapproved_agent_env_keys_before_subprocess() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_unapproved_env_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        home_root = state / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        (repo / "bin").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir(parents=True)
        write_agent_process_helper_repo_targets(repo)
        env = {
            "PATH": helper.SAFE_PATH,
            "HOME": str(home.resolve(strict=False)),
            "USER": "alex",
            "LOGNAME": "alex",
            "HERMES_HOME": str(hermes_home.resolve(strict=False)),
            "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "ARCLINK_AGENT_UID": "23456",
            "ARCLINK_AGENT_GID": "23456",
        }
        common = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": env,
        }
        unapproved_keys = {
            "LD_PRELOAD": "/tmp/not-allowed.so",
            "LD_LIBRARY_PATH": "/tmp/not-allowed",
            "PYTHONPATH": str(root / "pythonpath"),
            "PYTHONHOME": str(root / "pythonhome"),
            "BASH_ENV": str(root / "bashenv"),
            "ENV": str(root / "env"),
            "GIT_SSH_COMMAND": "ssh -i /tmp/key",
            "SSH_AUTH_SOCK": str(root / "agent.sock"),
            "OPENAI_API_TOKEN": "secret-token-not-for-agent",
            "APP_SECRET": "secret-not-for-agent",
            "DB_PASSWORD": "password-not-for-agent",
            "DEPLOY_KEY": "key-not-for-agent",
        }
        run_commands: list[list[str]] = []
        popen_commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        try:
            for key, value in unapproved_keys.items():
                request = {
                    **common,
                    "operation": "run_once",
                    "kind": "refresh",
                    "env": {**env, key: value},
                }
                ok, error = helper.run_agent_process_helper_request(request)
                expect(ok is False and "not approved" in str(error), f"{key} was not rejected before run_once subprocess: {error}")

                ok, error = helper.run_agent_process_helper_request(
                    {
                        "operation": "ensure_processes",
                        "processes": [
                            {
                                **common,
                                "kind": "gateway",
                                "env": {**env, key: value},
                            }
                        ],
                    }
                )
                expect(ok is False and "not approved" in str(error), f"{key} was not rejected before Popen: {error}")

            expect(run_commands == [], f"unapproved env reached subprocess.run: {run_commands}")
            expect(popen_commands == [], f"unapproved env reached subprocess.Popen: {popen_commands}")
            expect(
                not (state / "docker" / "agent-process-helper").exists(),
                "unapproved env created process-helper log directory before rejection",
            )
        finally:
            helper.PROCESSES.clear()
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_rejects_unapproved_agent_env_keys_before_subprocess")


def test_agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_dashboard_host_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        home_root = state / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        (repo / "bin").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir(parents=True)
        workspace.mkdir(parents=True)
        write_agent_process_helper_repo_targets(repo)
        env = {
            "PATH": helper.SAFE_PATH,
            "HOME": str(home.resolve(strict=False)),
            "USER": "alex",
            "LOGNAME": "alex",
            "HERMES_HOME": str(hermes_home.resolve(strict=False)),
            "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "ARCLINK_AGENT_UID": "23456",
            "ARCLINK_AGENT_GID": "23456",
        }
        common = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": env,
        }
        popen_commands: list[list[str]] = []

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        old_popen = helper.subprocess.Popen
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        try:
            for backend_host in ("0.0.0.0", "::", "8.8.8.8", "224.0.0.1", "not-a-host"):
                ok, error = helper.run_agent_process_helper_request(
                    {
                        "operation": "ensure_processes",
                        "processes": [
                            {
                                **common,
                                "kind": "dashboard",
                                "dashboard_backend_host": backend_host,
                                "dashboard_backend_port": "8100",
                            }
                        ],
                    }
                )
                expect(ok is False and "dashboard backend host" in str(error), f"{backend_host} was not rejected: {error}")
            expect(popen_commands == [], f"unsafe dashboard backend host reached subprocess.Popen: {popen_commands}")
            expect(
                not (state / "docker" / "agent-process-helper").exists(),
                "unsafe dashboard backend host created process-helper log directory before rejection",
            )

            ok, payload = helper.run_agent_process_helper_request(
                {
                    "operation": "ensure_processes",
                    "processes": [
                        {
                            **common,
                            "kind": "dashboard",
                            "dashboard_backend_host": "172.24.0.4",
                            "dashboard_backend_port": "8100",
                        }
                    ],
                }
            )
            expect(ok is True and payload.get("started") == ["agent-test:dashboard"], str(payload))
            expect(popen_commands and "--host" in popen_commands[-1] and "172.24.0.4" in popen_commands[-1], str(popen_commands))
        finally:
            helper.PROCESSES.clear()
            helper.PROCESS_SIGNATURES.clear()
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess")


def test_agent_process_helper_rejects_configured_root_mismatch() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_configured_root_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        configured_repo = root / "configured" / "repo"
        configured_priv = configured_repo / "arclink-priv"
        configured_state = configured_priv / "state"
        configured_runtime = root / "configured" / "runtime"
        configured_home_root = configured_state / "docker" / "users"
        configured_home = configured_home_root / "alex"
        configured_hermes = configured_home / ".local" / "share" / "arclink-agent" / "hermes-home"
        configured_workspace = configured_hermes / "workspace"
        requested_repo = root / "requested" / "repo"
        requested_priv = requested_repo / "arclink-priv"
        requested_state = requested_priv / "state"
        requested_runtime = root / "requested" / "runtime"
        requested_home_root = requested_state / "docker" / "users"
        requested_home = requested_home_root / "alex"
        requested_hermes = requested_home / ".local" / "share" / "arclink-agent" / "hermes-home"
        requested_workspace = requested_hermes / "workspace"
        for path in (
            configured_repo / "bin",
            configured_state,
            configured_runtime,
            requested_repo / "bin",
            requested_state,
            requested_runtime,
        ):
            path.mkdir(parents=True, exist_ok=True)
        write_agent_process_helper_repo_targets(configured_repo)
        write_agent_process_helper_repo_targets(requested_repo)

        def env_for(home: Path, hermes_home: Path, workspace: Path) -> dict[str, str]:
            return {
                "PATH": helper.SAFE_PATH,
                "HOME": str(home.resolve(strict=False)),
                "USER": "alex",
                "LOGNAME": "alex",
                "HERMES_HOME": str(hermes_home.resolve(strict=False)),
                "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
                "ARCLINK_AGENT_UID": "23456",
                "ARCLINK_AGENT_GID": "23456",
            }

        common = {
            "operation": "run_once",
            "kind": "refresh",
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(configured_home_root),
            "home": str(configured_home),
            "hermes_home": str(configured_hermes),
            "workspace": str(configured_workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(configured_repo),
            "priv_dir": str(configured_priv),
            "state_dir": str(configured_state),
            "runtime_dir": str(configured_runtime),
            "env": env_for(configured_home, configured_hermes, configured_workspace),
        }
        mismatches = [
            {
                **common,
                "home_root": str(requested_home_root),
                "home": str(requested_home),
                "hermes_home": str(requested_hermes),
                "workspace": str(requested_workspace),
                "env": env_for(requested_home, requested_hermes, requested_workspace),
            },
            {**common, "repo_dir": str(requested_repo)},
            {**common, "priv_dir": str(requested_priv), "state_dir": str(requested_state)},
            {**common, "state_dir": str(configured_priv / "other-state")},
            {**common, "runtime_dir": str(requested_runtime)},
        ]
        run_commands: list[list[str]] = []
        popen_commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        old_env = os.environ.copy()
        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(configured_home_root)
        os.environ["ARCLINK_REPO_DIR"] = str(configured_repo)
        os.environ["ARCLINK_PRIV_DIR"] = str(configured_priv)
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(configured_priv)
        os.environ["RUNTIME_DIR"] = str(configured_runtime)
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        try:
            for request in mismatches:
                ok, error = helper.run_agent_process_helper_request(request)
                expect(
                    ok is False and ("configured" in str(error) or "canonical child" in str(error)),
                    str(error),
                )
            expect(run_commands == [] and popen_commands == [], f"configured-root mismatch reached subprocess: {run_commands} {popen_commands}")
            expect(
                not (requested_state / "docker" / "agent-process-helper").exists(),
                "configured-root mismatch created attacker-chosen process-helper log dir",
            )
            configured_log_dir = configured_state / "docker" / "agent-process-helper"
            incident_path = configured_log_dir / "rejections.jsonl"
            expect(incident_path.exists(), "configured-root mismatch did not record a private-state rejection incident")
            incidents = [json.loads(line) for line in incident_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            expect(len(incidents) == len(mismatches), str(incidents))
            expect(all(row.get("reason") == "configured_root_rejected" for row in incidents), str(incidents))
            expect(
                sorted(path.name for path in configured_log_dir.glob("*.log")) == [],
                "configured-root mismatch created normal process-helper logs before a valid request",
            )

            ok, payload = helper.run_agent_process_helper_request(common)
        finally:
            helper.PROCESSES.clear()
            os.environ.clear()
            os.environ.update(old_env)
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen

        expect(ok is True and payload.get("returncode") == 0, str(payload))
        expect(run_commands and run_commands[0][0] == helper.SETPRIV_BIN, str(run_commands))
        expect(Path(run_commands[0][0]).is_absolute(), str(run_commands))
        expect((configured_state / "docker" / "agent-process-helper" / "agent-test-refresh.log").exists(), str(payload))
    print("PASS test_agent_process_helper_rejects_configured_root_mismatch")


def test_agent_process_helper_rejects_symlinked_configured_roots_before_work() -> None:
    helper = load_python_module(
        PYTHON_DIR / "arclink_agent_process_helper.py",
        "arclink_agent_process_helper_configured_root_symlink_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home_root = root / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        workspace.mkdir(parents=True)
        run_commands: list[list[str]] = []
        popen_commands: list[list[str]] = []

        def fake_run(args, **kwargs):
            del kwargs
            run_commands.append(list(args))
            return subprocess.CompletedProcess(args=args, returncode=0)

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                popen_commands.append(list(args))
                self.returncode = None

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        def env_for() -> dict[str, str]:
            return {
                "PATH": helper.SAFE_PATH,
                "HOME": str(home),
                "USER": "alex",
                "LOGNAME": "alex",
                "HERMES_HOME": str(hermes_home),
                "ARCLINK_WORKSPACE_ROOT": str(workspace),
                "DRIVE_WORKSPACE_ROOT": str(workspace),
                "CODE_WORKSPACE_ROOT": str(workspace),
                "TERMINAL_WORKSPACE_ROOT": str(workspace),
                "ARCLINK_AGENT_UID": "23456",
                "ARCLINK_AGENT_GID": "23456",
            }

        def request_for(repo: Path, priv: Path, runtime: Path, *, state: Path | None = None) -> dict[str, object]:
            return {
                "operation": "run_once",
                "kind": "refresh",
                "agent_id": "agent-test",
                "unix_user": "alex",
                "home_root": str(home_root),
                "home": str(home),
                "hermes_home": str(hermes_home),
                "workspace": str(workspace),
                "uid": 23456,
                "gid": 23456,
                "repo_dir": str(repo),
                "priv_dir": str(priv),
                "state_dir": str(state or priv / "state"),
                "runtime_dir": str(runtime),
                "env": env_for(),
            }

        def symlink_case(case_name: str, symlinked_label: str) -> tuple[dict[str, object], Path, Path]:
            case_root = root / case_name
            safe = case_root / "safe"
            escaped = case_root / "escaped"
            repo = safe / "repo"
            priv = safe / "arclink-priv"
            state = priv / "state"
            runtime = safe / "runtime"
            for path in (repo / "bin", state, runtime, escaped):
                path.mkdir(parents=True, exist_ok=True)

            if symlinked_label == "repo":
                target = escaped / "repo"
                target.mkdir()
                shutil.rmtree(repo)
                repo.symlink_to(target, target_is_directory=True)
            elif symlinked_label == "priv":
                target = escaped / "arclink-priv"
                target.mkdir()
                shutil.rmtree(priv)
                priv.symlink_to(target, target_is_directory=True)
                state = priv / "state"
            elif symlinked_label == "state":
                target = escaped / "state"
                target.mkdir()
                shutil.rmtree(state)
                state.symlink_to(target, target_is_directory=True)
            elif symlinked_label == "runtime":
                target = escaped / "runtime"
                target.mkdir()
                shutil.rmtree(runtime)
                runtime.symlink_to(target, target_is_directory=True)
            else:
                raise AssertionError(f"unknown symlink case {symlinked_label}")

            return request_for(repo, priv, runtime, state=state), state, escaped

        old_env = os.environ.copy()
        old_run = helper.subprocess.run
        old_popen = helper.subprocess.Popen
        helper.subprocess.run = fake_run
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        helper.PROCESS_SIGNATURES.clear()
        try:
            for label in ("repo", "priv", "state", "runtime"):
                request, state, escaped = symlink_case(f"symlinked-{label}", label)
                os.environ.clear()
                os.environ.update(old_env)
                os.environ[TRUSTED_HOST_RISK_ENV] = TRUSTED_HOST_RISK_ACCEPTED
                os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(home_root)
                os.environ["ARCLINK_REPO_DIR"] = str(request["repo_dir"])
                os.environ["ARCLINK_PRIV_DIR"] = str(request["priv_dir"])
                os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(request["priv_dir"])
                os.environ["RUNTIME_DIR"] = str(request["runtime_dir"])

                before_run = list(run_commands)
                before_popen = list(popen_commands)
                ok, error = helper.run_agent_process_helper_request(request)
                expect(ok is False and "symlink" in str(error), f"{label} symlink was not rejected: {error}")
                expect(run_commands == before_run, f"{label} symlink reached subprocess.run: {run_commands}")
                expect(popen_commands == before_popen, f"{label} symlink reached subprocess.Popen: {popen_commands}")
                log_dir = state / "docker" / "agent-process-helper"
                if label in {"repo", "runtime"}:
                    expect((log_dir / "rejections.jsonl").exists(), f"{label} symlink did not record a rejection incident")
                    expect(
                        sorted(path.name for path in log_dir.glob("*.log")) == [],
                        f"{label} symlink created normal process-helper logs before rejection",
                    )
                else:
                    expect(not log_dir.exists(), f"{label} symlink created process-helper logs before rejection")
                expect(
                    not list(escaped.glob("**/agent-test-refresh.log")),
                    f"{label} symlink wrote helper logs through escaped target",
                )

                ok, error = helper.run_agent_process_helper_request(
                    {"operation": "ensure_processes", "processes": [{**request, "kind": "gateway"}]}
                )
                expect(ok is False and "symlink" in str(error), f"{label} process symlink was not rejected: {error}")
                expect(run_commands == before_run, f"{label} process symlink reached subprocess.run: {run_commands}")
                expect(popen_commands == before_popen, f"{label} process symlink reached subprocess.Popen: {popen_commands}")

            valid_repo = root / "valid" / "repo"
            valid_priv = root / "valid" / "arclink-priv"
            valid_state = valid_priv / "state"
            valid_runtime = root / "valid" / "runtime"
            for path in (valid_repo / "bin", valid_state, valid_runtime):
                path.mkdir(parents=True, exist_ok=True)
            write_agent_process_helper_repo_targets(valid_repo)
            valid = request_for(valid_repo, valid_priv, valid_runtime)
            os.environ.clear()
            os.environ.update(old_env)
            os.environ[TRUSTED_HOST_RISK_ENV] = TRUSTED_HOST_RISK_ACCEPTED
            os.environ["ARCLINK_DOCKER_AGENT_HOME_ROOT"] = str(home_root)
            os.environ["ARCLINK_REPO_DIR"] = str(valid_repo)
            os.environ["ARCLINK_PRIV_DIR"] = str(valid_priv)
            os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = str(valid_priv)
            os.environ["RUNTIME_DIR"] = str(valid_runtime)

            ok, payload = helper.run_agent_process_helper_request(valid)
            expect(ok is True and payload.get("returncode") == 0, str(payload))
            expect(run_commands and run_commands[-1][0] == helper.SETPRIV_BIN, str(run_commands))
            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [{**valid, "kind": "gateway"}]}
            )
            expect(ok is True and payload.get("desired") == ["agent-test:gateway"], str(payload))
            expect(popen_commands and popen_commands[-1][0] == helper.SETPRIV_BIN, str(popen_commands))
        finally:
            helper.PROCESSES.clear()
            helper.PROCESS_SIGNATURES.clear()
            os.environ.clear()
            os.environ.update(old_env)
            helper.subprocess.run = old_run
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_rejects_symlinked_configured_roots_before_work")


def test_agent_process_helper_does_not_log_or_argv_env_values() -> None:
    helper = load_python_module(PYTHON_DIR / "arclink_agent_process_helper.py", "arclink_agent_process_helper_redaction_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        home_root = state / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        (repo / "bin").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir(parents=True)
        workspace.mkdir(parents=True)
        write_agent_process_helper_repo_targets(repo)
        marker = "fake-token-value-for-redaction-test"
        env = {
            "PATH": helper.SAFE_PATH,
            "HOME": str(home.resolve(strict=False)),
            "USER": "alex",
            "LOGNAME": "alex",
            "HERMES_HOME": str(hermes_home.resolve(strict=False)),
            "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "ARCLINK_AGENT_UID": "23456",
            "ARCLINK_AGENT_GID": "23456",
            "ARCLINK_DASHBOARD_AGENT_LABEL": marker,
        }
        common = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": env,
        }
        popen_calls: list[tuple[list[str], dict[str, str]]] = []

        class FakePopen:
            def __init__(self, args, **kwargs):
                self.args = list(args)
                self.returncode = None
                popen_calls.append((self.args, dict(kwargs.get("env") or {})))

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

        old_popen = helper.subprocess.Popen
        helper.subprocess.Popen = FakePopen
        helper.PROCESSES.clear()
        try:
            ok, payload = helper.run_agent_process_helper_request(
                {
                    "operation": "ensure_processes",
                    "processes": [{**common, "kind": "gateway"}],
                }
            )
            expect(ok is True and payload.get("desired") == ["agent-test:gateway"], str(payload))
            expect(len(popen_calls) == 1, str(popen_calls))
            command, process_env = popen_calls[0]
            joined_command = " ".join(command)
            log_path = state / "docker" / "agent-process-helper" / "agent-test-gateway.log"
            log_text = log_path.read_text(encoding="utf-8")
            expect(marker not in joined_command, joined_command)
            expect(marker not in log_text, log_text)
            expect("ARCLINK_DASHBOARD_AGENT_LABEL=" not in joined_command, joined_command)
            expect("ARCLINK_DASHBOARD_AGENT_LABEL=" not in log_text, log_text)
            expect(process_env.get("HERMES_HOME") == str(hermes_home.resolve(strict=False)), str(process_env))
            expect(process_env.get("ARCLINK_AGENT_UID") == "23456", str(process_env))
            expect(process_env.get("ARCLINK_DASHBOARD_AGENT_LABEL") == marker, str(process_env))
        finally:
            helper.PROCESSES.clear()
            helper.subprocess.Popen = old_popen
    print("PASS test_agent_process_helper_does_not_log_or_argv_env_values")


def test_agent_process_helper_restarts_processes_when_desired_signature_changes() -> None:
    helper = load_python_module(PYTHON_DIR / "arclink_agent_process_helper.py", "arclink_agent_process_helper_signature_test")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        priv = root / "arclink-priv"
        state = priv / "state"
        runtime = root / "runtime"
        home_root = state / "docker" / "users"
        home = home_root / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        workspace = hermes_home / "workspace"
        (repo / "bin").mkdir(parents=True)
        state.mkdir(parents=True)
        runtime.mkdir(parents=True)
        workspace.mkdir(parents=True)
        write_agent_process_helper_repo_targets(repo)
        env = {
            "PATH": helper.SAFE_PATH,
            "HOME": str(home.resolve(strict=False)),
            "USER": "alex",
            "LOGNAME": "alex",
            "HERMES_HOME": str(hermes_home.resolve(strict=False)),
            "ARCLINK_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "DRIVE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "CODE_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "TERMINAL_WORKSPACE_ROOT": str(workspace.resolve(strict=False)),
            "ARCLINK_AGENT_UID": "23456",
            "ARCLINK_AGENT_GID": "23456",
        }
        common = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "home_root": str(home_root),
            "home": str(home),
            "hermes_home": str(hermes_home),
            "workspace": str(workspace),
            "uid": 23456,
            "gid": 23456,
            "repo_dir": str(repo),
            "priv_dir": str(priv),
            "state_dir": str(state),
            "runtime_dir": str(runtime),
            "env": env,
        }
        popen_commands: list[list[str]] = []
        wait_timeouts: list[float] = []
        killpg_calls: list[tuple[int, int]] = []
        processes_by_pid: dict[int, object] = {}

        class FakePopen:
            def __init__(self, args, **kwargs):
                del kwargs
                self.args = list(args)
                self.pid = 4100 + len(popen_commands)
                self.returncode = None
                processes_by_pid[self.pid] = self
                popen_commands.append(self.args)

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                wait_timeouts.append(timeout)
                if self.returncode is None:
                    raise subprocess.TimeoutExpired(cmd=self.args, timeout=timeout)
                return self.returncode

            def terminate(self):
                self.returncode = -15

            def kill(self):
                self.returncode = -9

        def fake_killpg(pid, signum):
            killpg_calls.append((pid, signum))
            process = processes_by_pid[pid]
            process.returncode = -int(signum)

        def dashboard(port: str) -> dict[str, object]:
            return {
                **common,
                "kind": "dashboard",
                "dashboard_backend_host": "127.0.0.1",
                "dashboard_backend_port": port,
            }

        def gateway(label: str) -> dict[str, object]:
            return {
                **common,
                "kind": "gateway",
                "env": {**env, "ARCLINK_DASHBOARD_AGENT_LABEL": label},
            }

        old_popen = helper.subprocess.Popen
        old_killpg = helper.os.killpg
        helper.subprocess.Popen = FakePopen
        helper.os.killpg = fake_killpg
        helper.PROCESSES.clear()
        helper.PROCESS_SIGNATURES.clear()
        try:
            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [dashboard("8100")]}
            )
            expect(ok is True and payload.get("started") == ["agent-test:dashboard"], str(payload))
            expect(len(popen_commands) == 1 and popen_commands[-1][-2] == "8100", str(popen_commands))

            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [dashboard("8100")]}
            )
            expect(ok is True and payload.get("started") == [] and payload.get("stopped") == [], str(payload))
            expect(len(popen_commands) == 1 and killpg_calls == [], f"identical desired process churned: {popen_commands} {killpg_calls}")

            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [dashboard("8200")]}
            )
            expect(ok is True and payload.get("started") == ["agent-test:dashboard"], str(payload))
            expect(payload.get("stopped") == ["agent-test:dashboard"], str(payload))
            expect(payload.get("stop_results", {}).get("agent-test:dashboard") == "terminated", str(payload))
            expect(len(popen_commands) == 2 and popen_commands[-1][-2] == "8200", str(popen_commands))
            expect(killpg_calls and killpg_calls[-1][1] == helper.signal.SIGTERM, str(killpg_calls))

            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [dashboard("8200"), gateway("one")]}
            )
            expect(ok is True and payload.get("started") == ["agent-test:gateway"], str(payload))
            expect(payload.get("stopped") == [], str(payload))
            expect(len(popen_commands) == 3, str(popen_commands))

            ok, payload = helper.run_agent_process_helper_request(
                {"operation": "ensure_processes", "processes": [dashboard("8200"), gateway("two")]}
            )
            expect(ok is True and payload.get("started") == ["agent-test:gateway"], str(payload))
            expect(payload.get("stopped") == ["agent-test:gateway"], str(payload))
            expect(payload.get("stop_results", {}).get("agent-test:gateway") == "terminated", str(payload))
            expect(len(popen_commands) == 4, str(popen_commands))

            ok, payload = helper.run_agent_process_helper_request({"operation": "terminate_all"})
            expect(ok is True, str(payload))
            expect(payload.get("stopped") == ["agent-test:dashboard", "agent-test:gateway"], str(payload))
            expect(payload.get("stop_results", {}).get("agent-test:dashboard") == "terminated", str(payload))
            expect(payload.get("stop_results", {}).get("agent-test:gateway") == "terminated", str(payload))
            expect(helper.PROCESSES == {} and helper.PROCESS_SIGNATURES == {}, "process state was not cleared after terminate_all")
            expect(wait_timeouts and helper.PROCESS_STOP_TIMEOUT_SECONDS in wait_timeouts, str(wait_timeouts))
        finally:
            helper.PROCESSES.clear()
            helper.PROCESS_SIGNATURES.clear()
            helper.subprocess.Popen = old_popen
            helper.os.killpg = old_killpg
    print("PASS test_agent_process_helper_restarts_processes_when_desired_signature_changes")


def test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_docker_agent_supervisor.py",
        "arclink_docker_agent_supervisor_token_env_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = SimpleNamespace(
            repo_dir=REPO,
            private_dir=root / "arclink-priv",
            state_dir=root / "arclink-priv" / "state",
            runtime_dir=root / "runtime",
            vault_dir=root / "arclink-priv" / "vault",
            agents_state_dir=root / "arclink-priv" / "state" / "agents",
        )
        home = cfg.state_dir / "docker" / "users" / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        hermes_home.mkdir(parents=True)
        agent = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "hermes_home": str(hermes_home),
            "channels_json": json.dumps(["telegram"]),
            "_docker_uid": "23456",
            "_docker_gid": "23456",
        }
        old_env = os.environ.copy()
        os.environ.update(
            {
                "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN": "supervisor-broker-token-for-helper-calls",
                "ARCLINK_AGENT_USER_HELPER_TOKEN": "user-helper-token-not-for-agent",
                "ARCLINK_AGENT_PROCESS_HELPER_TOKEN": "process-helper-token-not-for-agent",
                "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN": "deployment-broker-token-not-for-agent",
                "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN": "gateway-broker-token-not-for-agent",
                "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN": "migration-helper-token-not-for-agent",
                "ARCLINK_FUTURE_CONTROL_TOKEN": "future-control-token-not-for-agent",
            }
        )
        try:
            raw_env = supervisor.user_env(cfg, agent, home, hermes_home)
            filtered_env = supervisor._agent_process_env(
                {**raw_env, "ARCLINK_FUTURE_CONTROL_TOKEN": "future-control-token-not-for-agent"}
            )
            context = supervisor.agent_process_context(cfg, agent, home, hermes_home)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        expect(raw_env.get("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN") == "supervisor-broker-token-for-helper-calls", str(raw_env))
        expect("ARCLINK_FUTURE_CONTROL_TOKEN" not in filtered_env, str(filtered_env))
        process_env = context.get("env")
        expect(isinstance(process_env, dict), str(context))
        for key in supervisor.AGENT_PROCESS_ENV_BLOCKLIST:
            expect(key not in process_env, f"{key} leaked into agent process env: {process_env}")
        expect(process_env.get("HOME") == str(home.resolve(strict=False)), str(process_env))
        expect(process_env.get("HERMES_HOME") == str(hermes_home.resolve(strict=False)), str(process_env))
        expect(process_env.get("ARCLINK_AGENT_UID") == "23456", str(process_env))
        expect(process_env.get("ARCLINK_AGENT_GID") == "23456", str(process_env))
    print("PASS test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes")


def test_agent_supervisor_provisioner_child_env_is_allowlisted() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_docker_agent_supervisor.py",
        "arclink_docker_agent_supervisor_provisioner_child_env_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = SimpleNamespace(
            repo_dir=REPO,
            private_dir=root / "arclink-priv",
            state_dir=root / "arclink-priv" / "state",
            runtime_dir=root / "runtime",
            vault_dir=root / "arclink-priv" / "vault",
            agents_state_dir=root / "arclink-priv" / "state" / "agents",
            db_path=root / "arclink-priv" / "state" / "arclink-control.sqlite3",
        )
        (REPO / "bin").mkdir(exist_ok=True)
        captured: list[dict[str, object]] = []

        def fake_run(args, **kwargs):
            captured.append(
                {
                    "args": list(args),
                    "cwd": str(kwargs.get("cwd") or ""),
                    "env": dict(kwargs.get("env") or {}),
                }
            )
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write("fake enrollment provisioner output\n")
            return subprocess.CompletedProcess(args=args, returncode=0)

        old_env = os.environ.copy()
        old_run = supervisor.subprocess.run
        try:
            os.environ.clear()
            os.environ.update(
                {
                    "HOME": "/home/arclink",
                    "LANG": "C.UTF-8",
                    "ARCLINK_DOCKER_HOST_REPO_DIR": "/srv/arclink",
                    "ARCLINK_DOCKER_HOST_PRIV_DIR": "/srv/arclink-priv",
                    "ARCLINK_DOCKER_AGENT_HOME_ROOT": "/srv/arclink-priv/state/docker/users",
                    "ARCLINK_DOCKER_NETWORK": "arclink_test",
                    "ARCLINK_MCP_URL": "http://arclink-mcp:8282/mcp",
                    "ARCLINK_BOOTSTRAP_URL": "http://arclink-mcp:8282/mcp",
                    "ARCLINK_QMD_URL": "http://qmd-mcp:8181/mcp",
                    "ARCLINK_AGENT_USER_HELPER_URL": "http://agent-user-helper:8915",
                    "ARCLINK_AGENT_USER_HELPER_TOKEN": "user-helper-token-for-provisioner",
                    "ARCLINK_AGENT_PROCESS_HELPER_URL": "http://agent-process-helper:8916",
                    "ARCLINK_AGENT_PROCESS_HELPER_TOKEN": "process-helper-token-for-provisioner",
                    "ARCLINK_AGENT_SUPERVISOR_BROKER_URL": "http://agent-supervisor-broker:8913",
                    "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN": "supervisor-broker-token-for-provisioner",
                    "ARCLINK_OPERATOR_UPGRADE_BROKER_URL": "http://operator-upgrade-broker:8917",
                    "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN": "operator-upgrade-token-for-provisioner",
                    "ARCLINK_OPERATOR_SQLITE_RETRY_SECONDS": "12",
                    "STRIPE_SECRET_KEY": "stripe-secret-must-not-reach-child",
                    "STRIPE_WEBHOOK_SECRET": "stripe-webhook-must-not-reach-child",
                    "CHUTES_API_KEY": "chutes-secret-must-not-reach-child",
                    "CLOUDFLARE_API_TOKEN": "cloudflare-secret-must-not-reach-child",
                    "TELEGRAM_BOT_TOKEN": "telegram-token-must-not-reach-child",
                    "DISCORD_BOT_TOKEN": "discord-token-must-not-reach-child",
                    "ARCLINK_MEMORY_SYNTH_API_KEY": "memory-key-must-not-reach-child",
                    "ARCLINK_SESSION_HASH_PEPPER": "pepper-must-not-reach-child",
                    "ARCLINK_FLEET_ENROLLMENT_SECRET": "fleet-secret-must-not-reach-child",
                    "ARCLINK_FUTURE_CONTROL_TOKEN": "future-token-must-not-reach-child",
                    "PYTHONPATH": "/tmp/pythonpath-must-not-reach-child",
                    "GIT_SSH_COMMAND": "ssh -i /tmp/key-must-not-reach-child",
                }
            )
            supervisor.subprocess.run = fake_run
            supervisor.run_provisioner(cfg)
        finally:
            supervisor.subprocess.run = old_run
            os.environ.clear()
            os.environ.update(old_env)

        expect(captured and captured[0]["args"] == [str(REPO / "bin" / "arclink-enrollment-provision.sh")], str(captured))
        env = captured[0]["env"]
        expect(isinstance(env, dict), str(captured))
        expect(env.get("PATH") == supervisor.SAFE_PATH, str(env))
        expect(env.get("ARCLINK_DOCKER_MODE") == "1", str(env))
        expect(env.get("ARCLINK_CONTAINER_RUNTIME") == "docker", str(env))
        expect(env.get("ARCLINK_AGENT_SERVICE_MANAGER") == "docker-supervisor", str(env))
        expect(env.get("ARCLINK_CONFIG_FILE") == str(cfg.private_dir / "config" / "docker.env"), str(env))
        expect(env.get("ARCLINK_REPO_DIR") == str(REPO), str(env))
        expect(env.get("ARCLINK_PRIV_DIR") == str(cfg.private_dir), str(env))
        expect(env.get("ARCLINK_PRIV_CONFIG_DIR") == str(cfg.private_dir / "config"), str(env))
        expect(env.get("STATE_DIR") == str(cfg.state_dir), str(env))
        expect(env.get("VAULT_DIR") == str(cfg.vault_dir), str(env))
        expect(env.get("ARCLINK_DB_PATH") == str(cfg.db_path), str(env))
        expect(env.get("RUNTIME_DIR") == str(cfg.runtime_dir), str(env))
        expect(env.get("ARCLINK_AGENTS_STATE_DIR") == str(cfg.agents_state_dir), str(env))
        expect(env.get("ARCLINK_DOCKER_AGENT_HOME_ROOT") == "/srv/arclink-priv/state/docker/users", str(env))
        expect(env.get("ARCLINK_AGENT_USER_HELPER_TOKEN") == "user-helper-token-for-provisioner", str(env))
        expect(env.get("ARCLINK_AGENT_PROCESS_HELPER_TOKEN") == "process-helper-token-for-provisioner", str(env))
        expect(env.get("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN") == "operator-upgrade-token-for-provisioner", str(env))
        for forbidden in (
            "STRIPE_SECRET_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "CHUTES_API_KEY",
            "CLOUDFLARE_API_TOKEN",
            "TELEGRAM_BOT_TOKEN",
            "DISCORD_BOT_TOKEN",
            "ARCLINK_MEMORY_SYNTH_API_KEY",
            "ARCLINK_SESSION_HASH_PEPPER",
            "ARCLINK_FLEET_ENROLLMENT_SECRET",
            "ARCLINK_FUTURE_CONTROL_TOKEN",
            "PYTHONPATH",
            "GIT_SSH_COMMAND",
        ):
            expect(forbidden not in env, f"agent-supervisor provisioner child env leaked {forbidden}: {env}")
    print("PASS test_agent_supervisor_provisioner_child_env_is_allowlisted")


def test_docker_agent_supervisor_rejects_unapproved_agent_process_env_keys() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_docker_agent_supervisor.py",
        "arclink_docker_agent_supervisor_unapproved_env_test",
    )
    clean = supervisor._agent_process_env(
        {
            "HOME": "/tmp/agent-home",
            "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN": "helper-call-token",
            "ARCLINK_FUTURE_CONTROL_TOKEN": "future-helper-call-token",
        }
    )
    expect("ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN" not in clean, str(clean))
    expect("ARCLINK_FUTURE_CONTROL_TOKEN" not in clean, str(clean))
    expect(clean.get("HOME") == "/tmp/agent-home", str(clean))

    for key, value in {
        "LD_PRELOAD": "/tmp/not-allowed.so",
        "LD_LIBRARY_PATH": "/tmp/not-allowed",
        "PYTHONPATH": "/tmp/pythonpath",
        "PYTHONHOME": "/tmp/pythonhome",
        "BASH_ENV": "/tmp/bashenv",
        "ENV": "/tmp/env",
        "GIT_SSH_COMMAND": "ssh -i /tmp/key",
        "SSH_AUTH_SOCK": "/tmp/agent.sock",
        "OPENAI_API_TOKEN": "secret-token-not-for-agent",
        "APP_SECRET": "secret-not-for-agent",
        "DB_PASSWORD": "password-not-for-agent",
        "DEPLOY_KEY": "key-not-for-agent",
    }.items():
        try:
            supervisor._agent_process_env({"HOME": "/tmp/agent-home", key: value})
        except ValueError as exc:
            expect("not approved" in str(exc), str(exc))
        else:
            raise AssertionError(f"{key} was not rejected before helper payload construction")
    print("PASS test_docker_agent_supervisor_rejects_unapproved_agent_process_env_keys")


def test_docker_agent_supervisor_delegates_process_launch_to_process_helper() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    supervisor = load_python_module(
        PYTHON_DIR / "arclink_docker_agent_supervisor.py",
        "arclink_docker_agent_supervisor_process_helper_test",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = SimpleNamespace(
            repo_dir=REPO,
            private_dir=root / "arclink-priv",
            state_dir=root / "arclink-priv" / "state",
            runtime_dir=root / "runtime",
            vault_dir=root / "arclink-priv" / "vault",
            agents_state_dir=root / "arclink-priv" / "state" / "agents",
        )
        home = cfg.state_dir / "docker" / "users" / "alex"
        hermes_home = home / ".local" / "share" / "arclink-agent" / "hermes-home"
        (hermes_home / "state").mkdir(parents=True)
        (hermes_home / "state" / "arclink-web-access.json").write_text(
            json.dumps({"dashboard_backend_port": "8765", "dashboard_proxy_port": "8766"}),
            encoding="utf-8",
        )
        agent = {
            "agent_id": "agent-test",
            "unix_user": "alex",
            "hermes_home": str(hermes_home),
            "channels_json": json.dumps(["telegram"]),
            "agent_label": "Alex Agent",
            "user_label": "Alex",
            "_docker_uid": "23456",
            "_docker_gid": "23456",
        }
        calls: list[tuple[str, dict[str, object]]] = []

        def fake_process_helper(operation, payload):
            calls.append((operation, dict(payload)))
            if operation == "run_once":
                return {"returncode": 0}
            return {"desired": [], "started": [], "stopped": []}

        old_process_helper = supervisor.agent_process_helper_request
        old_network = supervisor.ensure_dashboard_backend_network
        old_proxy = supervisor.ensure_dashboard_proxy
        supervisor.agent_process_helper_request = fake_process_helper
        supervisor.ensure_dashboard_backend_network = lambda _agent_id: ("arclink-agent-dashboard-agent-test", "172.30.0.2")
        supervisor.ensure_dashboard_proxy = lambda **_kwargs: "arclink-agent-dashboard-proxy-agent-test"
        try:
            supervisor.install_agent_assets(cfg, agent, home, hermes_home, ["telegram"])
            supervisor.run_refresh(cfg, agent, home, hermes_home, cron_tick=False)
            supervisor.run_refresh(cfg, agent, home, hermes_home, cron_tick=True)
            specs, proxies = supervisor.desired_specs(cfg, agent, home, hermes_home)
            supervisor.ensure_agent_processes(specs)
        finally:
            supervisor.agent_process_helper_request = old_process_helper
            supervisor.ensure_dashboard_backend_network = old_network
            supervisor.ensure_dashboard_proxy = old_proxy

        run_once_kinds = [payload.get("kind") for operation, payload in calls if operation == "run_once"]
        expect(run_once_kinds == ["install", "identity", "refresh", "cron"], str(calls))
        ensure_calls = [payload for operation, payload in calls if operation == "ensure_processes"]
        expect(len(ensure_calls) == 1, str(calls))
        process_kinds = [process.get("kind") for process in ensure_calls[0].get("processes", [])]
        expect(process_kinds == ["gateway", "dashboard"], str(ensure_calls))
        expect(proxies == {"arclink-agent-dashboard-proxy-agent-test"}, str(proxies))
        for _operation, payload in calls:
            text = json.dumps(payload, sort_keys=True)
            expect('"cmd"' not in text and '"command"' not in text and '"args"' not in text, text)
            expect("ARCLINK_AGENT_UID" in text and "23456" in text, text)
        source = read("python/arclink_docker_agent_supervisor.py")
        expect('"setpriv"' not in source and "subprocess.Popen" not in source, source)
    print("PASS test_docker_agent_supervisor_delegates_process_launch_to_process_helper")


def test_docker_operator_commands_are_present() -> None:
    body = read("bin/arclink-docker.sh")
    deploy = read("bin/deploy.sh")
    component_upgrade = read("bin/component-upgrade.sh")
    job_loop = read("bin/docker-job-loop.sh")
    ctl = read("python/arclink_ctl.py")
    rotate = body[body.index("docker_rotate_nextcloud_secrets()"):body.index("docker_pins_show()")]
    for command in (
        "bootstrap)",
        "write-config)",
        "config)",
        "build)",
        "up)",
        "down)",
        "ports)",
        "logs)",
        "health)",
        "tailnet-publish)",
        "provision-once)",
        "notion-ssot)",
        "notion-migrate)",
        "notion-transfer)",
        "enrollment-status)",
        "enrollment-trace)",
        "enrollment-align)",
        "enrollment-reset)",
        "curator-setup)",
        "rotate-nextcloud-secrets)",
        "agent-payload|agent)",
        "pins-show)",
        "pins-check)",
        "pin-upgrade-notify)",
        "teardown)",
        "remove)",
    ):
        expect(command in body, f"missing command case {command}\n{body}")
    expect('DOCKER_ENV_FILE="${ARCLINK_DOCKER_ENV_FILE:-$REPO_DIR/arclink-priv/config/docker.env}"' in body, body)
    expect('ARCLINK_DOCKER_REWRITE_CONFIG="${ARCLINK_DOCKER_REWRITE_CONFIG:-0}"' in body, body)
    expect('env_args=(--env-file "$DOCKER_ENV_FILE")' in body, body)
    expect('docker compose "${env_args[@]}" -f "$COMPOSE_FILE"' in body, body)
    expect("compose build arclink-app" in body, body)
    expect("compose config -q" in body, "docker config should validate without printing expanded secrets by default")
    expect("--unsafe-print" in body, "full Docker config output should require an explicit unsafe flag")
    expect('elif [[ "$1" == "--unsafe-print" ]]' in body and 'compose config "$@"' in body, "full compose config should be reachable only behind --unsafe-print")
    expect("reserve_docker_ports()" in body, body)
    expect("repair_docker_app_named_volumes()" in body and "arclink_arclink-qmd" in body, body)
    expect("compose up -d --no-build" in body, body)
    up_block = extract(body, "    up)", "\n      ;;")
    expect(
        "docker_repair_deployment_dashboard_plugin_mounts || true" in up_block
        and "docker_refresh_deployment_managed_plugins || true" in up_block,
        "ordinary Docker/control upgrades must refresh existing ArcPod dashboard plugin copies\n" + up_block,
    )
    expect("show_ports()" in body, body)
    expect("docker_port_set_available()" in body, body)
    expect("host_port_available_for_service \"$web_port\" control-ingress 8080" in body, body)
    expect("QMD_MCP_PORT" in body and "ARCLINK_MCP_PORT" in body and "ARCLINK_API_PORT" in body and "ARCLINK_WEB_PORT" in body, body)
    expect("18181 + offset" in body and "18282 + offset" in body and "28080 + offset" in body, body)
    expect("18900 + offset" in body and "13000 + offset" in body, body)
    expect("ports.json" in body, body)
    expect("agent-supervisor" in body, body)
    expect("control-provisioner" in body, body)
    expect("http://127.0.0.1/status.php" in body, body)
    expect("http://127.0.0.1:8900/api/v1/health" in body and "http://127.0.0.1:3000" in body, body)
    expect("docker_provision_once()" in body and "arclink_sovereign_worker.py" in body, body)
    expect('ensure_env_file_value ARCLINK_LOCAL_FLEET_SSH_USER "arclink"' in body, body)
    expect('ensure_env_file_value ARCLINK_CONTROL_HOST_MAX_ARCPOD_SLOTS "2"' in body, body)
    expect('ensure_env_file_value ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED "0"' in body, body)
    expect('ensure_env_file_value ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST ""' in body, body)
    expect(
        'ensure_env_file_value ARCLINK_FLEET_SSH_KEY_PATH "/home/arclink/arclink/arclink-priv/secrets/ssh/id_ed25519"'
        in body,
        body,
    )
    expect(
        'ensure_env_file_value ARCLINK_DOCKER_SOCKET_GID "$(stat -c %g /var/run/docker.sock 2>/dev/null || printf ' in body,
        body,
    )
    expect('ensure_env_file_value ARCLINK_DOCKER_UID "$(docker_default_runtime_uid)"' in body, body)
    expect("ensure_docker_app_bind_permissions()" in body, body)
    expect('-path "$REPO_DIR/arclink-priv/state/nextcloud" -prune' in body, body)
    expect('-path "$REPO_DIR/arclink-priv/state/operator/nextcloud" -prune' in body, body)
    expect('chown -R 33:33 "$REPO_DIR/arclink-priv/state/operator/nextcloud/html"' in body, body)
    expect('chown -R 70:70 "$REPO_DIR/arclink-priv/state/operator/nextcloud/db"' in body, body)
    expect('chown -R 999:1000 "$REPO_DIR/arclink-priv/state/operator/nextcloud/redis"' in body, body)
    expect("qmd-mcp" in body and "qmd --version" in body, body)
    expect('pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' in body, body)
    expect("health-watch" in body and "compose exec -T health-watch ./bin/docker-health.sh" in body, body)
    expect("docker_reconcile()" in body and "./bin/arclink-ctl org-profile apply --yes" in body, body)
    expect("docker_publish_tailnet_deployment_apps()" in body and "tailscale serve --bg --yes --https" in body, body)
    expect("tailnet-publish)" in body, "host-side tailnet publisher must be invokable without a health run")
    expect(
        "docker_ensure_tailnet_forward" in body
        and "docker_prune_tailnet_forwards" in body
        and "docker_tailnet_local_http_probe" in body
        and "systemd-run" in body
        and "arclink-tailnet-forward-" in body
        and "-o ControlMaster=no" in body
        and '-L "127.0.0.1:$port:127.0.0.1:$port"' in body,
        body,
    )
    # Nohup fallback forwards must be tracked by pidfile so pruning can stop
    # them, and the healthy-port short-circuit must require a tracked owner.
    expect(
        "docker_tailnet_forward_pidfile()" in body
        and "docker_tailnet_forward_tracked_alive()" in body
        and "docker_kill_tracked_tailnet_forward_pid()" in body
        and 'printf \'%s\\n\' "$forward_pid" >"$pid_file"' in body,
        "tailnet nohup forwards must write a pidfile next to the .log",
    )
    expect(
        'docker_tailnet_forward_tracked_alive "$deployment_id" "$port" && docker_tailnet_local_http_probe "$port"' in body,
        "tailnet local-http short-circuit must be scoped to a tracked forward for this deployment+port",
    )
    ensure_prune_block = extract(body, "docker_prune_tailnet_forwards()", "\ndocker_ensure_tailnet_forward()")
    expect(
        '.pid"}\' "$routes_file"' in ensure_prune_block
        and 'rm -f "$pid_file"' in ensure_prune_block,
        "tailnet forward pruning must kill tracked pids that left the desired route set\n" + ensure_prune_block,
    )
    expect("docker_refresh_deployment_service_health()" in body and "docker compose" in body and "upsert_arclink_service_health" in body, body)
    expect("docker_refresh_deployment_managed_plugins()" in body, body)
    expect("sync-dashboard-user-passwords.py" in body and "control-provisioner" in body, body)
    expect("managed-context-install" in body and "--force-recreate hermes-gateway" in body and "--force-recreate hermes-dashboard" in body, body)
    refresh_block = extract(body, "docker_refresh_deployment_managed_plugins()", "\ndocker_reconcile()")
    expect(
        "_executor_for_host" in refresh_block
        and "runner.run(" in refresh_block
        and "arclink_deployment_placements" in refresh_block
        and "host_metadata_json" in refresh_block,
        "deployment plugin refresh must route through the fleet executor for the selected ArcPod host\n"
        + refresh_block,
    )
    expect(
        'os.environ.get("ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN")'
        in refresh_block
        and 'not os.environ.get("ARCLINK_DEPLOYMENT_EXEC_BROKER_URL")'
        in refresh_block
        and 'os.environ.pop("ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN", None)'
        in refresh_block,
        "host-side deployment plugin refresh must not inherit a container-only broker token without a host-reachable URL\n"
        + refresh_block,
    )
    expect(
        "run\", \"--rm\", \"--no-deps\", \"managed-context-install" in refresh_block
        and "up\", \"-d\", \"--no-deps\", \"--force-recreate\", \"--remove-orphans" in refresh_block,
        "deployment plugin refresh must rerun managed-context install and recreate dashboard-facing services\n"
        + refresh_block,
    )
    expect(
        "Skipping deployment plugin refresh for {deployment_id}: no active fleet placement." in refresh_block,
        "active ArcPod plugin refresh must fail closed without an active fleet placement instead of creating local shadows\n"
        + refresh_block,
    )
    expect(
        "metadata.get(\"operator_agent\")" in refresh_block
        and "PRAGMA busy_timeout = 10000" in refresh_block
        and "deployment status lookup failed" in refresh_block
        and "(\"down\", \"--remove-orphans\")" in refresh_block
        and "RETIRED_STATUSES" in refresh_block
        and "teardown_complete" in refresh_block,
        "deployment plugin refresh must skip and stop retiring or retired ArcPods and the in-stack operator identity\n" + refresh_block,
    )
    expect("--force-recreate dashboard" in body, body)
    expect("--force-recreate nextcloud" in body, body)
    expect("--force-recreate memory-synth" in body, body)
    expect("Refreshed deployment-managed Hermes plugins" in body, body)
    expect("docker_repair_deployment_compose_secret_dirs()" in body, body)
    expect("docker_repair_deployment_compose_secret_dirs || true" in up_block, up_block)
    expect("Repaired ArcPod compose secret directories" in body, body)
    expect("docker_repair_deployment_dashboard_plugin_mounts()" in body, body)
    expect("run-hermes-dashboard-proxy.sh" in body, body)
    dashboard_proxy = read("bin/run-hermes-dashboard-proxy.sh")
    expect("yaml.safe_load" in dashboard_proxy and "config.plugins.enabled missing" in dashboard_proxy, dashboard_proxy)
    deployment_install = read("bin/install-deployment-hermes-home.sh")
    expect(
        "secret file is configured but cannot be read" in deployment_install
        and "secret file is configured but empty" in deployment_install,
        "ArcPod dashboard credential install must fail closed when mounted secrets are unreadable or empty",
    )
    expect("DRIVE_ROOT" in body and "CODE_WORKSPACE_ROOT" in body, body)
    expect("TERMINAL_ALLOW_ROOT" in body and "HERMES_TUI_DIR" in body, body)
    expect("ARCLINK_DASHBOARD_THEME" in body and "ARCLINK_DASHBOARD_AGENT_LABEL" in body, body)
    expect("dashboard_sso_secret" in body and "ARCLINK_DASHBOARD_SSO_SECRET_FILE" in body, body)
    expect("ARCLINK_CREW_DASHBOARDS_JSON" in body and "_crew_dashboard_links" in body, body)
    expect("sso_secret_for_subject" in body and "secrets.token_urlsafe(32)" in body, body)
    expect("os.chown(path, owner.st_uid, owner.st_gid)" in body and "path.chmod(0o600)" in body, body)
    expect("default_arclink_agent_profile" in body and "deployment_identities = load_deployment_identities()" in body, body)
    expect('"VAULT_DIR": "/srv/vault"' in body and '"/srv/vault/Agents_KB/hermes-agent-docs"' in body, body)
    expect('services.pop("code-server", None)' in body, body)
    expect('compose_secrets.pop("code_server_password", None)' in body, body)
    expect('env.pop("CODE_SERVER_PASSWORD_REF", None)' in body, body)
    expect("services.pop(\"code-server\", None)" in body and "\"--remove-orphans\"" in refresh_block, body)
    expect("Repaired Hermes dashboard plugin mounts" in body, body)
    expect("ensure_control_network(gateway, prefix=prefix, service_name=\"hermes-gateway\")" in body, body)
    expect("ARCLINK_TAILNET_SERVICE_PORT_BASE" in body, body)
    expect(
        "wait_for_docker_agent_reconcile()" in body
        and "arclink-vault-reconciler.json" in body
        and "PYTHONPATH=/home/arclink/arclink/python" in body,
        body,
    )
    expect("docker_record_release_state()" in body and '"deployed_from": "docker-checkout"' in body, body)
    expect('"revision_mode": revision_mode' in body, body)
    expect('"checkout_commit": checkout_commit' in body, body)
    expect('"baked_image_commit": baked_commit' in body, body)
    expect('"image_name": image_name' in body and '"image_created": image_created' in body, body)
    expect(
        "arclink-upgrade-check" in body
        and "arclink_upgrade_last_seen_sha" in body
        and "recorded by Docker release" in body,
        "Docker record-release should refresh upgrade-check DB state so health does not false-warn after a clean upgrade",
    )
    expect("docker_live_agent_smoke()" in body and "./bin/live-agent-tool-smoke.sh" in body, body)
    expect("COMPOSE_PROFILES=curator,quarto,backup" in body, body)
    expect("FAIL Docker Compose config is valid, but no ArcLink services are running." in body, body)
    expect("docker_enrollment_status()" in body, body)
    expect("docker_notion_migrate()" in body and "compose stop arclink-mcp ssot-batcher agent-supervisor" in body, body)
    expect("Docker supervisor loop (not systemd)" in body, body)
    expect("docker_enrollment_align()" in body and "./bin/arclink-enrollment-provision.sh" in body, body)
    expect("docker_enrollment_reset()" in body and "--remove-nextcloud-user" in body, body)
    expect("docker_rotate_nextcloud_secrets()" in body, body)
    expect("user:resetpassword --password-from-env" in body, body)
    expect("ALTER ROLE" in body and "PASSWORD" in body, body)
    expect(
        '-e OC_PASS="$new_admin_password"' not in rotate,
        "Docker Nextcloud rotation should not expose the admin password in compose argv",
    )
    expect(
        "sys.argv[2]" not in rotate,
        "Docker Nextcloud rotation should not pass the new database password through Python argv",
    )
    expect(
        "ARCLINK_NEXTCLOUD_DB_PASSWORD" in rotate and "-e ARCLINK_NEXTCLOUD_DB_PASSWORD" in rotate,
        "Docker Nextcloud rotation should pass the database password through environment passthrough",
    )
    expect("docker_component_upgrade_apply()" in body, body)
    expect("ARCLINK_COMPONENT_UPGRADE_MODE=docker" in body, body)
    expect("retired_shared_host_docker_mode()" in deploy and "legacy-docker" in deploy, deploy)
    expect(
        "arclink-docker-tailnet-publisher.service" in deploy
        and "arclink-docker-tailnet-publisher.timer" in deploy
        and "install_control_tailnet_publisher_timer" in deploy,
        "control install/upgrade must install the host-side tailnet publisher loop\n" + deploy,
    )
    expect("deploy.sh control install" in deploy and "control-install" in deploy and "control-provision-once" in deploy, deploy)
    expect("docker-enrollment-status" in deploy and "docker-rotate-nextcloud-secrets" in deploy, deploy)
    expect("qmd-upgrade-check" in deploy and "node-upgrade" in deploy, deploy)
    expect('ARCLINK_COMPONENT_UPGRADE_MODE:-}" == "docker"' in component_upgrade, component_upgrade)
    expect('"$REPO_DIR/deploy.sh" upgrade' in component_upgrade, component_upgrade)
    expect('os.environ.get("ARCLINK_DOCKER_MODE") == "1"' in ctl and '["docker", "rm", "-f", container_name]' in ctl, ctl)
    expect("docker health passed" not in body.lower() or "Docker health passed." in body, body)
    expect("redact_output" in job_loop and 'cat "$output_file"' not in job_loop, "Docker job loop must redact failure output before logs/state")
    print("PASS test_docker_operator_commands_are_present")


def test_docker_repair_backfills_dashboard_sso_and_crew_links() -> None:
    snippet = extract(
        read("bin/arclink-docker.sh"),
        "docker_repair_deployment_dashboard_plugin_mounts() {",
        "\ncompose_service_secrets_available() {",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        deployments = root / "deployments"
        state = repo / "arclink-priv" / "state"
        state.mkdir(parents=True)
        (repo / "python").symlink_to(REPO / "python")
        db_path = state / "arclink-control.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  prefix TEXT,
                  base_domain TEXT,
                  agent_name TEXT,
                  agent_title TEXT,
                  status TEXT,
                  metadata_json TEXT,
                  created_at TEXT
                )
                """
            )
            rows = [
                ("arcdep_one", "user_1", "amber-one", "example.test", "Vela", "Systems Builder", 1),
                ("arcdep_two", "user_1", "amber-two", "example.test", "Atlas", "Mission Operator", 2),
            ]
            for deployment_id, user_id, prefix, base_domain, agent_name, agent_title, index in rows:
                metadata = {
                    "onboarding_session_id": "onb_test",
                    "bundle_primary_deployment_id": "arcdep_one",
                    "bundle_agent_index": index,
                    "bundle_agent_count": 2,
                }
                conn.execute(
                    """
                    INSERT INTO arclink_deployments (
                      deployment_id, user_id, prefix, base_domain, agent_name, agent_title,
                      status, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        deployment_id,
                        user_id,
                        prefix,
                        base_domain,
                        agent_name,
                        agent_title,
                        json.dumps(metadata, sort_keys=True),
                        f"2026-01-01T00:00:0{index}+00:00",
                    ),
                )
            conn.commit()

        for deployment_id, _user_id, prefix, base_domain, agent_name, _agent_title, _index in rows:
            config = deployments / f"{deployment_id}-{prefix}" / "config"
            config.mkdir(parents=True)
            payload = {
                "services": {
                    "code-server": {"image": "legacy"},
                    "hermes-dashboard": {
                        "command": ["legacy-dashboard"],
                        "environment": {
                            "ARCLINK_BASE_DOMAIN": base_domain,
                            "ARCLINK_INGRESS_MODE": "domain",
                            "ARCLINK_PREFIX": prefix,
                            "ARCLINK_HERMES_URL": f"https://hermes-{prefix}.{base_domain}",
                        },
                        "volumes": [],
                    },
                    "hermes-gateway": {
                        "environment": {"ARCLINK_PREFIX": prefix},
                        "volumes": [],
                    },
                    "managed-context-install": {
                        "command": ["legacy-installer"],
                        "environment": {},
                        "secrets": [],
                        "volumes": [],
                    },
                },
                "secrets": {"code_server_password": {"file": str(root / f"{agent_name}.secret")}},
            }
            (config / "compose.yaml").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        script = f"""
set -euo pipefail
REPO_DIR={shlex.quote(str(repo))}
configured_or_default() {{
  case "$1" in
    ARCLINK_STATE_ROOT_BASE) printf '%s\\n' {shlex.quote(str(deployments))} ;;
    *) printf '%s\\n' "${{2:-}}" ;;
  esac
}}
{snippet}
docker_repair_deployment_dashboard_plugin_mounts
"""
        result = subprocess.run(
            ["bash", "-lc", script],
            cwd=REPO,
            env={**os.environ, "PYTHONPATH": str(REPO / "python")},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        expect(result.returncode == 0, f"repair failed: stdout={result.stdout!r} stderr={result.stderr!r}")

        loaded = {}
        secrets_by_deployment = {}
        for deployment_id, _user_id, prefix, _base_domain, _agent_name, _agent_title, _index in rows:
            deployment_root = deployments / f"{deployment_id}-{prefix}"
            compose = json.loads((deployment_root / "config" / "compose.yaml").read_text(encoding="utf-8"))
            loaded[deployment_id] = compose
            secret_path = deployment_root / "config" / "secrets" / "dashboard_sso_secret"
            secrets_by_deployment[deployment_id] = secret_path.read_text(encoding="utf-8").strip()
            expect(secret_path.stat().st_mode & 0o777 == 0o600, f"secret permissions not narrowed for {secret_path}")
            expect(
                (secret_path.stat().st_uid, secret_path.stat().st_gid)
                == ((deployment_root / "config" / "secrets").stat().st_uid, (deployment_root / "config" / "secrets").stat().st_gid),
                f"secret ownership must follow the private secrets directory for container readability: {secret_path}",
            )
            expect("code-server" not in compose["services"], json.dumps(compose, sort_keys=True))
            expect("code_server_password" not in compose["secrets"], json.dumps(compose["secrets"], sort_keys=True))
            expect(compose["secrets"]["dashboard_sso_secret"] == {"file": str(secret_path)}, str(compose["secrets"]))
            dashboard = compose["services"]["hermes-dashboard"]
            installer = compose["services"]["managed-context-install"]
            expect(dashboard["command"] == ["./bin/run-hermes-dashboard-proxy.sh"], str(dashboard))
            expect({"source": "dashboard_sso_secret", "target": "/run/secrets/dashboard_sso_secret"} in installer["secrets"], str(installer))
            expect(installer["environment"]["ARCLINK_DASHBOARD_SSO_SECRET_FILE"] == "/run/secrets/dashboard_sso_secret", str(installer))
            expect(installer["environment"]["ARCLINK_DASHBOARD_SSO_SUBJECT"] == "user_1", str(installer))
            expect(installer["environment"]["ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN"] == "example.test", str(installer))
            crew = json.loads(dashboard["environment"]["ARCLINK_CREW_DASHBOARDS_JSON"])
            expect([item["deployment_id"] for item in crew] == ["arcdep_one", "arcdep_two"], str(crew))
            expect(sum(1 for item in crew if item.get("current")) == 1, str(crew))
            expect(any(item["label"] == "Vela" for item in crew) and any(item["label"] == "Atlas" for item in crew), str(crew))
            expect(dashboard["environment"]["ARCLINK_DASHBOARD_SSO_COOKIE_DOMAIN"] == "example.test", str(dashboard))
            expect(installer["environment"]["ARCLINK_CREW_DASHBOARDS_JSON"] == dashboard["environment"]["ARCLINK_CREW_DASHBOARDS_JSON"], str(installer))
        expect(secrets_by_deployment["arcdep_one"] == secrets_by_deployment["arcdep_two"], str(secrets_by_deployment))
    print("PASS test_docker_repair_backfills_dashboard_sso_and_crew_links")


def test_docker_repair_strips_control_network_for_remote_deployments() -> None:
    snippet = extract(
        read("bin/arclink-docker.sh"),
        "docker_repair_deployment_dashboard_plugin_mounts() {",
        "\ncompose_service_secrets_available() {",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        deployments = root / "deployments"
        state = repo / "arclink-priv" / "state"
        state.mkdir(parents=True)
        (repo / "python").symlink_to(REPO / "python")
        db_path = state / "arclink-control.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  user_id TEXT,
                  prefix TEXT,
                  base_domain TEXT,
                  agent_name TEXT,
                  agent_title TEXT,
                  status TEXT,
                  metadata_json TEXT,
                  created_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO arclink_deployments (
                  deployment_id, user_id, prefix, base_domain, agent_name, agent_title,
                  status, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    "arcdep_remote",
                    "user_1",
                    "remote-one",
                    "example.test",
                    "Remote",
                    "Fleet Worker",
                    json.dumps({"private_dns_name": "10.44.0.12", "fleet_host_hostname": "arclink-002"}),
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            conn.commit()
        config = deployments / "arcdep_remote-remote-one" / "config"
        config.mkdir(parents=True)
        payload = {
            "networks": {"arclink-control": {"external": True, "name": "arclink_default"}},
            "services": {
                "hermes-dashboard": {
                    "command": ["legacy-dashboard"],
                    "environment": {
                        "ARCLINK_BASE_DOMAIN": "example.test",
                        "ARCLINK_INGRESS_MODE": "domain",
                        "ARCLINK_PREFIX": "remote-one",
                    },
                    "volumes": [],
                },
                "hermes-gateway": {
                    "environment": {"ARCLINK_PREFIX": "remote-one", "ARCLINK_ARCPOD_CONTROL_NETWORK_MODE": "remote"},
                    "networks": {"default": {}, "arclink-control": {"aliases": ["arclink-remote-one-hermes-gateway"]}},
                    "volumes": [],
                },
                "managed-context-install": {
                    "command": ["legacy-installer"],
                    "environment": {},
                    "secrets": [],
                    "volumes": [],
                },
            },
            "secrets": {},
        }
        (config / "compose.yaml").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        script = f"""
set -euo pipefail
REPO_DIR={shlex.quote(str(repo))}
configured_or_default() {{
  case "$1" in
    ARCLINK_STATE_ROOT_BASE) printf '%s\\n' {shlex.quote(str(deployments))} ;;
    *) printf '%s\\n' "${{2:-}}" ;;
  esac
}}
{snippet}
docker_repair_deployment_dashboard_plugin_mounts
"""
        result = subprocess.run(
            ["bash", "-lc", script],
            cwd=REPO,
            env={**os.environ, "PYTHONPATH": str(REPO / "python")},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        expect(result.returncode == 0, f"repair failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        repaired = json.loads((config / "compose.yaml").read_text(encoding="utf-8"))
        expect("arclink-control" not in repaired.get("networks", {}), json.dumps(repaired, sort_keys=True))
        gateway_networks = repaired["services"]["hermes-gateway"].get("networks", {})
        expect(gateway_networks == {"default": {}}, json.dumps(gateway_networks, sort_keys=True))
    print("PASS test_docker_repair_strips_control_network_for_remote_deployments")


def test_deployment_hermes_home_installer_seeds_runtime_knowledge() -> None:
    body = read("bin/install-deployment-hermes-home.sh")
    expect("sync-hermes-bundled-skills.sh" in body, body)
    expect("install-arclink-skills.sh" in body, body)
    expect("install-arclink-plugins.sh" in body, body)
    expect("migrate-hermes-config.sh" in body, body)
    expect("reconcile-vault-layout.py" in body and "--hermes-skills-dir" in body, body)
    expect("sync-hermes-docs-into-vault.sh" in body, body)
    expect("ARCLINK_CONFIG_FILE=/dev/null" in body, body)
    expect("ARCLINK_ALLOW_SCAFFOLD_DEFAULTS=1" in body, body)
    expect('ARCLINK_HERMES_DOCS_VAULT_DIR="$docs_vault_dir"' in body, body)
    expect("Hermes docs sync failed; continuing" in body, body)
    expect("--identity-only" in body, "deployment installer must refresh SOUL.md even when provider credentials are unavailable")
    expect("captain_name=" in body and '--user-name "$captain_name"' in body, body)
    print("PASS test_deployment_hermes_home_installer_seeds_runtime_knowledge")


def test_docker_tailnet_publish_uses_dashboard_native_plugin_urls() -> None:
    body = read("bin/arclink-docker.sh")
    snippet = extract(body, "docker_host_priv_path() {", "docker_configure_deployment_nextcloud_overwrite() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        state = repo / "arclink-priv" / "state"
        state.mkdir(parents=True)
        (repo / "python").symlink_to(REPO / "python")
        db_path = state / "arclink-control.sqlite3"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  prefix TEXT,
                  base_domain TEXT,
                  status TEXT,
                  metadata_json TEXT,
                  created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE arclink_deployment_placements (
                  placement_id TEXT PRIMARY KEY,
                  deployment_id TEXT,
                  host_id TEXT,
                  status TEXT,
                  placed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE arclink_fleet_hosts (
                  host_id TEXT PRIMARY KEY,
                  hostname TEXT,
                  metadata_json TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO arclink_deployments (
                  deployment_id, prefix, base_domain, status, metadata_json, created_at
                ) VALUES ('dep_1', 'amber-vault-1a2b', 'worker.example.ts.net', 'active', '{}', '2026-01-01T00:00:00+00:00')
                """
            )
            conn.commit()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log_path = root / "tailscale.log"
        (bin_dir / "tailscale").write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log_path))}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bin_dir / "tailscale").chmod(0o755)
        script = f"""
set -euo pipefail
{snippet}
REPO_DIR={shlex.quote(str(repo))}
configured_or_default() {{
  case "$1" in
    ARCLINK_INGRESS_MODE) printf '%s\\n' tailscale ;;
    ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY) printf '%s\\n' path ;;
    ARCLINK_TAILSCALE_DNS_NAME) printf '%s\\n' worker.example.ts.net ;;
    ARCLINK_WEB_PORT) printf '%s\\n' 3000 ;;
    ARCLINK_TAILNET_SERVICE_PORT_BASE) printf '%s\\n' 8443 ;;
    *) printf '%s\\n' "${{2:-}}" ;;
  esac
}}
docker_configure_deployment_nextcloud_overwrite() {{
  printf 'called\\n' >> {shlex.quote(str(root / "nextcloud-called"))}
}}
docker_wait_tailnet_local_http() {{
  return 0
}}
docker_publish_tailnet_deployment_apps
"""
        result = subprocess.run(
            ["bash", "-lc", script],
            cwd=REPO,
            env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"tailnet publish probe failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        with sqlite3.connect(db_path) as conn:
            metadata = json.loads(conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()[0])
        expect(metadata["tailnet_app_publication"]["status"] == "published", str(metadata))
        expect(metadata["tailnet_app_publication"]["failed_roles"] == [], str(metadata))
        expect(metadata["access_urls"]["dashboard"] == "https://worker.example.ts.net:8443", str(metadata))
        expect(metadata["access_urls"]["hermes"] == "https://worker.example.ts.net:8443", str(metadata))
        expect(metadata["access_urls"]["files"] == "https://worker.example.ts.net:8443/drive", str(metadata))
        expect(metadata["access_urls"]["code"] == "https://worker.example.ts.net:8443/code", str(metadata))
        expect(metadata["access_urls"]["notion"] == "https://worker.example.ts.net/u/amber-vault-1a2b/notion/webhook", str(metadata))
        expect(metadata["tailnet_service_ports"] == {"hermes": 8443}, str(metadata))
        expect("http://127.0.0.1:8443" in log_path.read_text(encoding="utf-8"), log_path.read_text(encoding="utf-8"))
        expect(not (root / "nextcloud-called").exists(), "Nextcloud overwrite must not be configured for dashboard-native Drive")
        print("PASS test_docker_tailnet_publish_uses_dashboard_native_plugin_urls")


def test_docker_tailnet_forward_pidfile_tracking_prunes_nohup_forwards() -> None:
    body = read("bin/arclink-docker.sh")
    snippet = extract(body, "docker_tailnet_forward_socket() {", "docker_ensure_tailnet_forward() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        forwards = repo / "arclink-priv" / "state" / "tailnet-forwards"
        forwards.mkdir(parents=True)
        driver = root / "driver.sh"
        driver.write_text(
            "#!/usr/bin/env bash\n"
            "set -uo pipefail\n"
            f"REPO_DIR={shlex.quote(str(repo))}\n"
            + snippet
            + "\n"
            'dir="$REPO_DIR/arclink-priv/state/tailnet-forwards"\n'
            "sleep 300 & stale_pid=$!\n"
            'printf \'%s\\n\' "$stale_pid" > "$dir/dep-stale-9001.pid"\n'
            "sleep 300 & live_pid=$!\n"
            'printf \'%s\\n\' "$live_pid" > "$dir/dep-live-9002.pid"\n'
            'printf \'dep-live\\tprefix\\t9002\\thost\\tuser\\t22\\n\' > "$REPO_DIR/routes.tsv"\n'
            'docker_prune_tailnet_forwards "$REPO_DIR/routes.tsv"\n'
            "for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 \"$stale_pid\" 2>/dev/null || break; sleep 0.2; done\n"
            'if kill -0 "$stale_pid" 2>/dev/null; then echo "FAIL stale forward pid survived prune"; exit 1; fi\n'
            'if [[ -f "$dir/dep-stale-9001.pid" ]]; then echo "FAIL stale pidfile survived prune"; exit 1; fi\n'
            'kill -0 "$live_pid" 2>/dev/null || { echo "FAIL desired forward pid was killed"; exit 1; }\n'
            '[[ -f "$dir/dep-live-9002.pid" ]] || { echo "FAIL desired pidfile was removed"; exit 1; }\n'
            'docker_tailnet_forward_tracked_alive "dep-live" "9002" || { echo "FAIL tracked_alive false for live forward"; exit 1; }\n'
            'kill "$live_pid" 2>/dev/null; wait "$live_pid" 2>/dev/null\n'
            'if docker_tailnet_forward_tracked_alive "dep-live" "9002"; then echo "FAIL tracked_alive true for dead forward"; exit 1; fi\n'
            'if [[ -f "$dir/dep-live-9002.pid" ]]; then echo "FAIL dead pidfile retained"; exit 1; fi\n'
            'echo "TAILNET_FORWARD_TRACKING_OK"\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            ["bash", str(driver)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        expect(
            result.returncode == 0 and "TAILNET_FORWARD_TRACKING_OK" in result.stdout,
            f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
    print("PASS test_docker_tailnet_forward_pidfile_tracking_prunes_nohup_forwards")


def test_docker_tailnet_publish_failure_withholds_app_urls() -> None:
    body = read("bin/arclink-docker.sh")
    snippet = extract(body, "docker_host_priv_path() {", "docker_configure_deployment_nextcloud_overwrite() {")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        state = repo / "arclink-priv" / "state"
        state.mkdir(parents=True)
        (repo / "python").symlink_to(REPO / "python")
        db_path = state / "arclink-control.sqlite3"
        existing_metadata = json.dumps(
            {
                "tailnet_service_ports": {"hermes": 8443},
                "access_urls": {"dashboard": "https://old.example.test"},
            }
        )
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE arclink_deployments (
                  deployment_id TEXT PRIMARY KEY,
                  prefix TEXT,
                  base_domain TEXT,
                  status TEXT,
                  metadata_json TEXT,
                  created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE arclink_deployment_placements (
                  placement_id TEXT PRIMARY KEY,
                  deployment_id TEXT,
                  host_id TEXT,
                  status TEXT,
                  placed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE arclink_fleet_hosts (
                  host_id TEXT PRIMARY KEY,
                  hostname TEXT,
                  metadata_json TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO arclink_deployments (
                  deployment_id, prefix, base_domain, status, metadata_json, created_at
                ) VALUES (?, 'amber-vault-1a2b', 'worker.example.ts.net', 'active', ?, '2026-01-01T00:00:00+00:00')
                """,
                ("dep_1", existing_metadata),
            )
            conn.commit()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        log_path = root / "tailscale.log"
        (bin_dir / "tailscale").write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log_path))}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        (bin_dir / "tailscale").chmod(0o755)
        script = f"""
set -euo pipefail
{snippet}
REPO_DIR={shlex.quote(str(repo))}
configured_or_default() {{
  case "$1" in
    ARCLINK_INGRESS_MODE) printf '%s\\n' tailscale ;;
    ARCLINK_TAILSCALE_DEPLOYMENT_HOST_STRATEGY) printf '%s\\n' path ;;
    ARCLINK_TAILSCALE_DNS_NAME) printf '%s\\n' worker.example.ts.net ;;
    ARCLINK_WEB_PORT) printf '%s\\n' 3000 ;;
    ARCLINK_TAILNET_SERVICE_PORT_BASE) printf '%s\\n' 8443 ;;
    *) printf '%s\\n' "${{2:-}}" ;;
  esac
}}
docker_wait_tailnet_local_http() {{
  return 1
}}
docker_publish_tailnet_deployment_apps
"""
        result = subprocess.run(
            ["bash", "-lc", script],
            cwd=REPO,
            env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
            text=True,
            capture_output=True,
            check=False,
        )
        expect(result.returncode == 0, f"tailnet publish failure probe failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        with sqlite3.connect(db_path) as conn:
            metadata = json.loads(conn.execute("SELECT metadata_json FROM arclink_deployments WHERE deployment_id = 'dep_1'").fetchone()[0])
        expect(metadata["tailnet_app_publication"]["status"] == "unavailable", str(metadata))
        expect(metadata["tailnet_app_publication"]["failed_roles"] == ["hermes"], str(metadata))
        expect("access_urls" not in metadata, str(metadata))
        expect("message" in metadata["tailnet_app_publication"], str(metadata))
        log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        expect("http://127.0.0.1:8443" not in log_text, log_text)
        print("PASS test_docker_tailnet_publish_failure_withholds_app_urls")


def test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = root / "repo"
        (repo / "bin").mkdir(parents=True)
        (repo / "arclink-priv" / "config").mkdir(parents=True)
        shutil.copy(REPO / "bin" / "arclink-docker.sh", repo / "bin" / "arclink-docker.sh")
        fake_component_upgrade = repo / "bin" / "component-upgrade.sh"
        capture = root / "capture.txt"
        fake_component_upgrade.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    "{",
                    '  printf "mode=%s\\n" "${ARCLINK_COMPONENT_UPGRADE_MODE:-}"',
                    '  printf "config=%s\\n" "${ARCLINK_CONFIG_FILE:-}"',
                    '  printf "repo=%s\\n" "${ARCLINK_UPSTREAM_REPO_URL:-}"',
                    '  printf "branch=%s\\n" "${ARCLINK_UPSTREAM_BRANCH:-}"',
                    '  printf "key_enabled=%s\\n" "${ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED:-}"',
                    '  printf "key_user=%s\\n" "${ARCLINK_UPSTREAM_DEPLOY_KEY_USER:-}"',
                    '  printf "key_path=%s\\n" "${ARCLINK_UPSTREAM_DEPLOY_KEY_PATH:-}"',
                    '  printf "known_hosts=%s\\n" "${ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE:-}"',
                    '  printf "args=%s\\n" "$*"',
                    '} >"$CAPTURE"',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fake_component_upgrade.chmod(0o755)
        docker_env = repo / "arclink-priv" / "config" / "docker.env"
        docker_env.write_text(
            "\n".join(
                [
                    "ARCLINK_UPSTREAM_REPO_URL=git@github.com:example/arclink.git",
                    "ARCLINK_UPSTREAM_BRANCH=arclink",
                    "ARCLINK_UPSTREAM_DEPLOY_KEY_ENABLED=1",
                    "ARCLINK_UPSTREAM_DEPLOY_KEY_USER=operator",
                    f"ARCLINK_UPSTREAM_DEPLOY_KEY_PATH={root}/arclink-upstream-ed25519",
                    f"ARCLINK_UPSTREAM_KNOWN_HOSTS_FILE={root}/known_hosts",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "bash",
                str(repo / "bin" / "arclink-docker.sh"),
                "hermes-upgrade",
                "--ref",
                "abc123",
                "--skip-upgrade",
            ],
            cwd=repo,
            env={**os.environ, "CAPTURE": str(capture)},
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        expect(result.returncode == 0, combined)
        captured = capture.read_text(encoding="utf-8")
        expect("mode=docker" in captured, captured)
        expect(f"config={docker_env}" in captured, captured)
        expect("repo=git@github.com:example/arclink.git" in captured, captured)
        expect("branch=arclink" in captured, captured)
        expect("key_enabled=1" in captured, captured)
        expect("key_user=operator" in captured, captured)
        expect(f"key_path={root}/arclink-upstream-ed25519" in captured, captured)
        expect(f"known_hosts={root}/known_hosts" in captured, captured)
        expect("args=hermes-agent apply --ref abc123 --skip-upgrade" in captured, captured)
    print("PASS test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config")


def test_docker_agent_supervisor_replaces_user_systemd_units() -> None:
    supervisor = read("python/arclink_docker_agent_supervisor.py")
    broker = read("python/arclink_agent_supervisor_broker.py")
    helper = read("python/arclink_agent_user_helper.py")
    process_helper = read("python/arclink_agent_process_helper.py")
    installer = read("bin/install-agent-user-services.sh")
    provisioner = read("python/arclink_enrollment_provisioner.py")
    expect("def ensure_container_user" in supervisor, supervisor)
    expect("agent_user_helper_request" in supervisor, supervisor)
    expect("ARCLINK_AGENT_USER_HELPER_URL" in supervisor and "ARCLINK_AGENT_USER_HELPER_TOKEN" in supervisor, supervisor)
    expect('"useradd"' not in supervisor and '"chown"' not in supervisor and "os.chown" not in supervisor, supervisor)
    expect("run_agent_user_helper_request" in helper and '"useradd"' in helper and '"chown"' in helper, helper)
    expect('"setpriv"' not in supervisor and '"runuser"' not in supervisor, supervisor)
    expect("agent_process_helper_request" in supervisor, supervisor)
    expect("ARCLINK_AGENT_PROCESS_HELPER_URL" in supervisor and "ARCLINK_AGENT_PROCESS_HELPER_TOKEN" in supervisor, supervisor)
    expect("ARCLINK_AGENT_PROCESS_HELPER_REQUEST_TIMEOUT_SECONDS" in supervisor, supervisor)
    expect("run_agent_process_helper_request" in process_helper and 'SETPRIV_BIN = "/usr/bin/setpriv"' in process_helper, process_helper)
    expect("subprocess.Popen" not in supervisor and "subprocess.Popen" in process_helper, supervisor)
    expect("agent user helper does not accept raw commands" in helper, helper)
    expect("agent process helper does not accept raw commands" in process_helper, process_helper)
    expect('"gateway", "run", "--replace"' in process_helper, process_helper)
    expect("ensure_dashboard_backend_network" in supervisor, supervisor)
    expect("agent_supervisor_broker_request" in supervisor, supervisor)
    expect("ensure_dashboard_proxy" in supervisor, supervisor)
    expect('"ensure_dashboard_network"' in supervisor, supervisor)
    expect('"ensure_dashboard_proxy"' in supervisor, supervisor)
    expect('"docker", "network", "create", "--internal"' not in supervisor, supervisor)
    expect('"docker", "network", "connect"' not in supervisor, supervisor)
    expect('"network", "create", "--internal"' in broker, broker)
    expect('"network",\n                "connect"' in broker, broker)
    expect("startswith(container_name)" in broker, broker)
    expect('"dashboard_backend_host": dashboard_backend_host' in supervisor, supervisor)
    expect('"--host",' in process_helper and '"dashboard_backend_host"' in process_helper, process_helper)
    expect('"--target",\n        f"http://{backend_host}:{backend_port}"' in broker, broker)
    expect('"--host",\n                        "0.0.0.0"' not in supervisor, supervisor)
    expect("arclink_dashboard_auth_proxy.py" in broker, broker)
    expect('"run",\n        "-d"' in broker, broker)
    expect('"docker",\n                    "run"' not in supervisor, supervisor)
    expect('"--network"' in broker and "ARCLINK_DOCKER_NETWORK" in supervisor, supervisor)
    expect('"ARCLINK_DOCKER_CONTAINER_NAME"' not in supervisor, supervisor)
    expect("AGENT_SUPERVISOR_BROKER_TOKEN_HEADER" in supervisor and "AGENT_SUPERVISOR_BROKER_TOKEN_HEADER" in broker, broker)
    expect("AGENT_USER_HELPER_TOKEN_HEADER" in supervisor and "AGENT_USER_HELPER_TOKEN_HEADER" in helper, helper)
    expect("AGENT_PROCESS_HELPER_TOKEN_HEADER" in supervisor and "AGENT_PROCESS_HELPER_TOKEN_HEADER" in process_helper, process_helper)
    expect("run-agent-code-server.sh" not in supervisor, supervisor)
    expect('"cron", "tick"' in process_helper, process_helper)
    expect('refresh_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_REFRESH_SECONDS", "14400"))' in supervisor, supervisor)
    expect('cron_seconds = int(os.environ.get("ARCLINK_DOCKER_AGENT_CRON_SECONDS", "60"))' in supervisor, supervisor)
    expect('run_agent_once(cfg, agent, home, hermes_home, "cron")' in supervisor, supervisor)
    expect('run_agent_once(cfg, agent, home, hermes_home, "refresh")' in supervisor, supervisor)
    expect("ensure_agent_mcp_auth" in supervisor and "ensure_agent_mcp_bootstrap_token" in supervisor, supervisor)
    expect('"docker-agent-supervisor"' in supervisor, supervisor)
    expect("run_headless_identity_setup" in supervisor and "arclink_headless_hermes_setup.py" in process_helper, process_helper)
    expect('"--identity-only"' in process_helper and "agent_label" in supervisor and "user_label" in supervisor, process_helper)
    expect('ARCLINK_AGENT_SERVICE_MANAGER:-systemd' in installer, installer)
    expect("def _ensure_docker_user_ready" in provisioner, provisioner)
    expect('"ARCLINK_AGENT_SERVICE_MANAGER": "docker-supervisor"' in provisioner, provisioner)
    expect("arclink_dashboard_auth_proxy.py" in broker and "arclink-web-access.json" in supervisor, supervisor)
    print("PASS test_docker_agent_supervisor_replaces_user_systemd_units")


def test_agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy() -> None:
    broker = load_python_module(
        PYTHON_DIR / "arclink_agent_supervisor_broker.py",
        "arclink_agent_supervisor_broker_contract_test",
    )
    ok, error = broker.run_agent_supervisor_request(
        {
            "operation": "ensure_dashboard_proxy",
            "agent_id": "agent_1",
            "cmd": ["docker", "ps"],
        }
    )
    expect(ok is False and "raw commands" in str(error), str(error))

    old_env = {key: os.environ.get(key) for key in (
        "ARCLINK_DOCKER_BINARY",
        "ARCLINK_DOCKER_HOST_PRIV_DIR",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        "ARCLINK_DOCKER_IMAGE",
        "ARCLINK_REPO_DIR",
    )}
    old_run = broker.subprocess.run
    old_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
    old_which = broker.shutil.which
    commands: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        del args, kwargs
        commands.append(list(command))
        if list(command)[:3] == [docker_binary, "container", "inspect"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="container-id\n", stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        docker_path = Path(tmp) / "docker"
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)
        docker_binary = str(docker_path)
        try:
            broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)
            broker.shutil.which = lambda name: docker_binary if name == "docker" else None
            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = "/srv/arclink-priv"
            os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = "/home/arclink/arclink/arclink-priv"
            os.environ["ARCLINK_DOCKER_IMAGE"] = "arclink/app:test"
            os.environ["ARCLINK_REPO_DIR"] = "/home/arclink/arclink"
            broker.subprocess.run = fake_run
            ok, payload = broker.run_agent_supervisor_request(
                {
                    "operation": "ensure_dashboard_proxy",
                    "agent_id": "agent_1",
                    "network": "arclink-agent-dashboard-agent_1",
                    "container_name": "arclink-agent-dashboard-proxy-agent_1",
                    "backend_host": "172.24.0.4",
                    "backend_port": 7601,
                    "proxy_port": 17601,
                    "access_file": "/home/arclink/arclink/arclink-priv/state/docker/users/alice/.local/share/arclink-agent/hermes-home/state/arclink-web-access.json",
                }
            )
        finally:
            broker.subprocess.run = old_run
            broker.TRUSTED_DOCKER_BINARY_PATHS = old_trusted
            broker.shutil.which = old_which
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    expect(ok is True and isinstance(payload, dict), str(payload))
    expect(payload.get("container") == "arclink-agent-dashboard-proxy-agent_1", str(payload))
    run_cmds = [command for command in commands if command[:3] == [docker_binary, "run", "-d"]]
    expect(len(run_cmds) == 1, str(commands))
    run_cmd = run_cmds[0]
    expect("--rm" in run_cmd and "--pull" in run_cmd and "never" in run_cmd, str(run_cmd))
    expect("--network" in run_cmd and "arclink-agent-dashboard-agent_1" in run_cmd, str(run_cmd))
    expect("-p" in run_cmd and "127.0.0.1:17601:17601" in run_cmd, str(run_cmd))
    expect("-v" in run_cmd and "/srv/arclink-priv:/home/arclink/arclink/arclink-priv:rw" in run_cmd, str(run_cmd))
    expect("--label" in run_cmd and "arclink.agent_id=agent_1" in run_cmd, str(run_cmd))
    expect("--access-file" in run_cmd and run_cmd[run_cmd.index("--access-file") + 1].startswith("/home/arclink/arclink/arclink-priv/"), str(run_cmd))
    expect("arclink/app:test" in run_cmd and "arclink_dashboard_auth_proxy.py" in " ".join(run_cmd), str(run_cmd))
    print("PASS test_agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy")


def test_agent_supervisor_broker_rejects_unsafe_dashboard_backend_host() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(
        PYTHON_DIR / "arclink_agent_supervisor_broker.py",
        "arclink_agent_supervisor_broker_dashboard_host_test",
    )
    old_env = {key: os.environ.get(key) for key in (
        "ARCLINK_DOCKER_HOST_PRIV_DIR",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        "ARCLINK_DOCKER_IMAGE",
        "ARCLINK_REPO_DIR",
    )}
    old_run = broker.subprocess.run
    old_docker_binary = broker._docker_binary
    commands: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        del args, kwargs
        commands.append(list(command))
        if list(command)[1:3] == ["container", "inspect"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="container-id\n", stderr="")

    base_request = {
        "operation": "ensure_dashboard_proxy",
        "agent_id": "agent_1",
        "network": "arclink-agent-dashboard-agent_1",
        "container_name": "arclink-agent-dashboard-proxy-agent_1",
        "backend_port": 7601,
        "proxy_port": 17601,
        "access_file": "/home/arclink/arclink/arclink-priv/state/agents/agent_1/arclink-web-access.json",
    }
    try:
        os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = "/srv/arclink-priv"
        os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = "/home/arclink/arclink/arclink-priv"
        os.environ["ARCLINK_DOCKER_IMAGE"] = "arclink/app:test"
        os.environ["ARCLINK_REPO_DIR"] = "/home/arclink/arclink"
        broker.subprocess.run = fake_run
        broker._docker_binary = lambda: "/usr/bin/docker"

        for backend_host in ("0.0.0.0", "::", "8.8.8.8", "224.0.0.1", "not-a-host"):
            ok, error = broker.run_agent_supervisor_request({**base_request, "backend_host": backend_host})
            expect(ok is False and "backend host" in str(error), f"{backend_host} was not rejected: {error}")
        expect(commands == [], f"unsafe dashboard backend host reached subprocess.run: {commands}")

        ok, payload = broker.run_agent_supervisor_request({**base_request, "backend_host": "172.24.0.4"})
        expect(ok is True and payload.get("container") == "arclink-agent-dashboard-proxy-agent_1", str(payload))
    finally:
        broker.subprocess.run = old_run
        broker._docker_binary = old_docker_binary
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    run_cmds = [command for command in commands if command[:3] == ["/usr/bin/docker", "run", "-d"]]
    expect(len(run_cmds) == 1, str(commands))
    expect("--target" in run_cmds[0] and "http://172.24.0.4:7601" in run_cmds[0], str(run_cmds[0]))
    print("PASS test_agent_supervisor_broker_rejects_unsafe_dashboard_backend_host")


def test_agent_supervisor_broker_rejects_unsafe_private_bind_roots_before_dashboard_proxy() -> None:
    broker = load_python_module(
        PYTHON_DIR / "arclink_agent_supervisor_broker.py",
        "arclink_agent_supervisor_broker_private_bind_roots_test",
    )
    old_env = {key: os.environ.get(key) for key in (
        "ARCLINK_DOCKER_HOST_PRIV_DIR",
        "ARCLINK_DOCKER_CONTAINER_PRIV_DIR",
        "ARCLINK_DOCKER_IMAGE",
        "ARCLINK_REPO_DIR",
    )}
    old_run = broker.subprocess.run
    old_docker_binary = broker._docker_binary
    commands: list[list[str]] = []
    docker_lookups: list[str] = []

    def fail_run(command, *args, **kwargs):
        del args, kwargs
        commands.append(list(command))
        raise AssertionError(f"unsafe private bind root reached subprocess.run: {command}")

    def fail_docker_binary():
        docker_lookups.append("lookup")
        raise AssertionError("unsafe private bind root reached Docker CLI lookup")

    valid_host_priv = "/srv/arclink-priv"
    valid_container_priv = "/home/arclink/arclink/arclink-priv"
    request = {
        "operation": "ensure_dashboard_proxy",
        "agent_id": "agent_1",
        "network": "arclink-agent-dashboard-agent_1",
        "container_name": "arclink-agent-dashboard-proxy-agent_1",
        "backend_host": "172.24.0.4",
        "backend_port": 7601,
        "proxy_port": 17601,
        "access_file": "/home/arclink/arclink/arclink-priv/state/docker/users/alice/.local/share/arclink-agent/hermes-home/state/arclink-web-access.json",
    }
    unsafe_cases = [
        ("relative host private root", "relative/arclink-priv", valid_container_priv),
        ("filesystem root host private root", "/", valid_container_priv),
        ("newline host private root", "/srv/arclink-priv\nsteered", valid_container_priv),
        ("colon host private root", "/srv/arclink-priv:/escaped", valid_container_priv),
        ("dotdot host private root", "/srv/arclink-priv/../escaped", valid_container_priv),
        ("wrong-name host private root", "/srv/not-private", valid_container_priv),
        ("relative container private root", valid_host_priv, "home/arclink/arclink/arclink-priv"),
        ("filesystem root container private root", valid_host_priv, "/"),
        ("carriage-return container private root", valid_host_priv, "/home/arclink/arclink/arclink-priv\rsteered"),
        ("colon container private root", valid_host_priv, "/home/arclink/arclink/arclink-priv:/escaped"),
        ("dot component container private root", valid_host_priv, "/home/arclink/./arclink/arclink-priv"),
        ("dotdot container private root", valid_host_priv, "/home/arclink/arclink/arclink-priv/.."),
        ("wrong container private root", valid_host_priv, "/tmp/arclink-priv"),
    ]
    try:
        os.environ["ARCLINK_DOCKER_IMAGE"] = "arclink/app:test"
        os.environ["ARCLINK_REPO_DIR"] = "/home/arclink/arclink"
        broker.subprocess.run = fail_run
        broker._docker_binary = fail_docker_binary
        for label, host_priv, container_priv in unsafe_cases:
            os.environ["ARCLINK_DOCKER_HOST_PRIV_DIR"] = host_priv
            os.environ["ARCLINK_DOCKER_CONTAINER_PRIV_DIR"] = container_priv
            ok, error = broker.run_agent_supervisor_request(request)
            error_text = str(error)
            expect(ok is False and "private bind root" in error_text, f"{label}: {error_text}")
            expect(host_priv not in error_text and container_priv not in error_text, f"{label}: unredacted path in {error_text!r}")
        for label, value, container in (
            ("NUL host private root", "/srv/arclink-priv\x00steered", False),
            ("NUL container private root", "/home/arclink/arclink/arclink-priv\x00steered", True),
        ):
            try:
                broker._require_private_bind_root(value, container=container)
            except ValueError as exc:
                expect("private bind root" in str(exc), f"{label}: {exc}")
                expect(value not in str(exc), f"{label}: unredacted path in {exc!r}")
            else:
                raise AssertionError(f"{label} was not rejected")
    finally:
        broker.subprocess.run = old_run
        broker._docker_binary = old_docker_binary
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    expect(commands == [], f"unsafe private bind roots reached subprocess.run: {commands}")
    expect(docker_lookups == [], f"unsafe private bind roots reached Docker CLI lookup: {docker_lookups}")
    print("PASS test_agent_supervisor_broker_rejects_unsafe_private_bind_roots_before_dashboard_proxy")


def test_deployment_exec_broker_rejects_unsafe_docker_binary_before_subprocess() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(
        PYTHON_DIR / "arclink_deployment_exec_broker.py",
        "arclink_deployment_exec_broker_docker_binary_test",
    )
    old_env = {key: os.environ.get(key) for key in ("ARCLINK_DOCKER_BINARY", "ARCLINK_STATE_ROOT_BASE")}
    old_run = broker.executor.subprocess.run
    old_which = broker.shutil.which
    old_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
    commands: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        del args, kwargs
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = root / "dep-one" / "config"
        config.mkdir(parents=True)
        env_file = config / "arclink.env"
        compose_file = config / "compose.yaml"
        env_file.write_text("", encoding="utf-8")
        compose_file.write_text("", encoding="utf-8")
        request = {
            "deployment_id": "dep-one",
            "operation": "compose_ps",
            "project_name": "arclink-dep-one",
            "env_file": str(env_file),
            "compose_file": str(compose_file),
        }
        docker_path = root / "docker"
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)

        try:
            os.environ["ARCLINK_STATE_ROOT_BASE"] = str(root)
            broker.executor.subprocess.run = fake_run

            os.environ["ARCLINK_DOCKER_BINARY"] = "bash"
            ok, payload = broker.run_deployment_exec_request(request)

            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            broker.shutil.which = lambda name: None
            missing_ok, missing_payload = broker.run_deployment_exec_request(request)

            expect(commands == [], f"unsafe Docker binary must fail before subprocess.run: {commands}")
            expect(ok is False and "Docker CLI" in str(payload), str(payload))
            expect(missing_ok is False and "not available" in str(missing_payload), str(missing_payload))

            docker_binary = str(docker_path)
            broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)
            broker.shutil.which = lambda name: docker_binary if name == "docker" else None
            valid_ok, valid_payload = broker.run_deployment_exec_request(request)
        finally:
            broker.executor.subprocess.run = old_run
            broker.shutil.which = old_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = old_trusted
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    expect(valid_ok is True and isinstance(valid_payload, dict), str(valid_payload))
    expect(commands and commands[-1][0] == docker_binary and commands[-1][1] == "compose", str(commands))
    print("PASS test_deployment_exec_broker_rejects_unsafe_docker_binary_before_subprocess")


def test_gateway_exec_broker_rejects_unsafe_docker_binary_before_subprocess() -> None:
    if str(PYTHON_DIR) not in sys.path:
        sys.path.insert(0, str(PYTHON_DIR))
    broker = load_python_module(
        PYTHON_DIR / "arclink_gateway_exec_broker.py",
        "arclink_gateway_exec_broker_docker_binary_test",
    )
    old_env = {key: os.environ.get(key) for key in ("ARCLINK_DOCKER_BINARY", "PATH")}
    old_run = broker.subprocess.run
    old_which = broker.shutil.which
    old_trusted = broker.TRUSTED_DOCKER_BINARY_PATHS
    commands: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        del args, kwargs
        commands.append(list(command))
        if list(command)[:2] == [docker_binary, "ps"]:
            return subprocess.CompletedProcess(command, 0, stdout="arclink-dep-one-hermes-gateway-1\n", stderr="")
        if list(command)[:2] == [docker_binary, "exec"]:
            return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}\n', stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected docker command")

    request = {
        "deployment_id": "dep-one",
        "project_name": "arclink-dep-one",
        "payload": {
            "platform": "telegram",
            "bot_token": "token",
            "chat_id": "123",
            "user_id": "123",
            "text": "hello",
        },
    }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        unsafe_dir = root / "unsafe"
        unsafe_dir.mkdir()
        unsafe_docker = unsafe_dir / "docker"
        unsafe_log = root / "unsafe-docker-called.log"
        unsafe_docker.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$0 $*\" >> {shlex.quote(str(unsafe_log))}\n"
            "printf '{\"ok\": true}\\n'\n",
            encoding="utf-8",
        )
        unsafe_docker.chmod(0o755)

        docker_path = root / "trusted" / "docker"
        docker_path.parent.mkdir()
        docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker_path.chmod(0o755)
        docker_binary = str(docker_path)

        try:
            broker.subprocess.run = fake_run

            os.environ["ARCLINK_DOCKER_BINARY"] = "bash"
            unsafe_ok, unsafe_error = broker.run_gateway_exec_request(request)

            os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
            os.environ["PATH"] = f"{unsafe_dir}:{old_env.get('PATH') or ''}"
            path_ok, path_error = broker.run_gateway_exec_request(request)

            broker.shutil.which = lambda name: None
            missing_ok, missing_error = broker.run_gateway_exec_request(request)

            expect(commands == [], f"unsafe Docker binary must fail before subprocess.run: {commands}")
            expect(unsafe_ok is False and "Docker CLI" in unsafe_error, unsafe_error)
            expect(path_ok is False and "not trusted" in path_error, path_error)
            expect(missing_ok is False and "not available" in missing_error, missing_error)
            expect(not unsafe_log.exists(), "PATH-injected fake docker must not be invoked")

            broker.TRUSTED_DOCKER_BINARY_PATHS = (docker_path,)
            broker.shutil.which = lambda name: docker_binary if name == "docker" else None
            valid_ok, valid_error = broker.run_gateway_exec_request(request)
        finally:
            broker.subprocess.run = old_run
            broker.shutil.which = old_which
            broker.TRUSTED_DOCKER_BINARY_PATHS = old_trusted
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    expect(valid_ok is True and valid_error == "", valid_error)
    expect(commands and commands[-2][:2] == [docker_binary, "ps"], str(commands))
    expect(commands[-1][:2] == [docker_binary, "exec"], str(commands))
    print("PASS test_gateway_exec_broker_rejects_unsafe_docker_binary_before_subprocess")


def test_agent_supervisor_broker_rejects_unsafe_docker_binary_before_subprocess() -> None:
    broker = load_python_module(
        PYTHON_DIR / "arclink_agent_supervisor_broker.py",
        "arclink_agent_supervisor_broker_docker_binary_test",
    )
    old_env = os.environ.get("ARCLINK_DOCKER_BINARY")
    old_run = broker.subprocess.run
    old_which = broker.shutil.which
    commands: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        del args, kwargs
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    try:
        os.environ["ARCLINK_DOCKER_BINARY"] = "bash"
        broker.subprocess.run = fake_run
        ok, payload = broker.run_agent_supervisor_request(
            {
                "operation": "ensure_dashboard_network",
                "agent_id": "agentone",
                "network": "arclink-agent-dashboard-agentone",
                "supervisor_container": "supervisor",
            }
        )
        os.environ["ARCLINK_DOCKER_BINARY"] = "docker"
        broker.shutil.which = lambda name: None
        missing_ok, missing_payload = broker.run_agent_supervisor_request(
            {
                "operation": "ensure_dashboard_network",
                "agent_id": "agentone",
                "network": "arclink-agent-dashboard-agentone",
                "supervisor_container": "supervisor",
            }
        )
    finally:
        broker.subprocess.run = old_run
        broker.shutil.which = old_which
        if old_env is None:
            os.environ.pop("ARCLINK_DOCKER_BINARY", None)
        else:
            os.environ["ARCLINK_DOCKER_BINARY"] = old_env

    expect(ok is False and "Docker CLI" in str(payload), str(payload))
    expect(missing_ok is False and "not available" in str(missing_payload), str(missing_payload))
    expect(commands == [], f"unsafe Docker binary must fail before subprocess.run: {commands}")
    print("PASS test_agent_supervisor_broker_rejects_unsafe_docker_binary_before_subprocess")


def test_docker_entrypoint_generates_fresh_secrets() -> None:
    body = read("bin/docker-entrypoint.sh")
    expect("generate_secret()" in body, body)
    expect("runtime_env_config_enabled()" in body, body)
    expect("write_runtime_env_config()" in body, body)
    expect("secrets.token_urlsafe(32)" in body, body)
    expect("config_file_can_write()" in body and "config_file_can_repair()" in body, body)
    expect('repair_placeholder_secret POSTGRES_PASSWORD "$PRIV_DIR/state/nextcloud/db/PG_VERSION"' in body, body)
    expect(
        'repair_placeholder_secret NEXTCLOUD_ADMIN_PASSWORD "$PRIV_DIR/state/nextcloud/html/config/config.php"' in body,
        body,
    )
    expect("POSTGRES_PASSWORD=$postgres_password" in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD=$nextcloud_admin_password" in body, body)
    expect("ARCLINK_AGENT_USER_HELPER_TOKEN=$agent_user_helper_token" in body, body)
    expect("set_config_value ARCLINK_AGENT_USER_HELPER_TOKEN" in body, body)
    expect("ARCLINK_AGENT_PROCESS_HELPER_TOKEN=$agent_process_helper_token" in body, body)
    expect("set_config_value ARCLINK_AGENT_PROCESS_HELPER_TOKEN" in body, body)
    expect("ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN=$operator_upgrade_broker_token" in body, body)
    expect("set_config_value ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN" in body, body)
    expect("ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN=$migration_capture_helper_token" in body, body)
    expect("set_config_value ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN" in body, body)
    expect("local trusted_host_risk_accepted=" in body, body)
    expect(f"{TRUSTED_HOST_RISK_ENV}=$trusted_host_risk_accepted" in body, body)
    expect(f"{TRUSTED_HOST_RISK_ENV}={TRUSTED_HOST_RISK_ACCEPTED}" not in body, body)
    docker_wrapper = read("bin/arclink-docker.sh")
    deploy = read("bin/deploy.sh")
    expect(f'ensure_env_file_value {TRUSTED_HOST_RISK_ENV} ""' in docker_wrapper, docker_wrapper)
    expect(f'write_kv {TRUSTED_HOST_RISK_ENV} "${{{TRUSTED_HOST_RISK_ENV}:-}}"' in deploy, deploy)
    expect("ARCLINK_EXECUTOR_MACHINE_MODE_ENABLED=0" in body, body)
    expect("ARCLINK_EXECUTOR_MACHINE_HOST_ALLOWLIST=" in body, body)
    expect("POSTGRES_PASSWORD=change-me" not in body, body)
    expect("NEXTCLOUD_ADMIN_PASSWORD=change-me" not in body, body)
    expect(
        "rsync -a --no-owner --no-group --no-perms --omit-dir-times --ignore-existing" in body,
        "rootless Docker entrypoint rsync must not preserve owner/group/perms or dir times on split bind mounts",
    )
    expect(
        "split private mounts may provide it at runtime" in body,
        "Docker entrypoint must tolerate split private mounts with an unwritable arclink-priv symlink parent",
    )
    expect(
        "unable to seed private template defaults" in body and '[[ -d "$PRIV_DIR" && -w "$PRIV_DIR" ]]' in body,
        "Docker entrypoint must skip template seeding when split private mounts make the arclink-priv parent unwritable",
    )
    expect(
        "unable to write Docker config" in body and "split private mounts may provide runtime config through Compose" in body,
        "Docker entrypoint must not crash when split private mounts make the generated config path unwritable",
    )
    expect(
        "unable to repair Docker config secrets" in body and "split private mounts may provide sealed runtime values" in body,
        "Docker entrypoint must not crash when split private mounts make config secret repair impossible",
    )
    expect(
        "unable to create Nextcloud data directory" in body and "split private mounts may provide it to the Nextcloud service" in body,
        "Docker entrypoint must not crash when non-Nextcloud services lack the split Nextcloud data mount",
    )
    expect('[[ -d "$live_data" && ! -w "$live_data" ]]' in body, body)
    expect('[[ ! -w "$(dirname "$nextcloud_config")" ]]' in body, body)
    print("PASS test_docker_entrypoint_generates_fresh_secrets")


def test_docker_entrypoint_runtime_env_config_preserves_pod_paths_without_secret_spill() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime_config = Path(tmp) / "runtime.env"
        result = subprocess.run(
            [
                "bash",
                str(REPO / "bin" / "docker-entrypoint.sh"),
                "bash",
                "-lc",
                "source \"$ARCLINK_REPO_DIR/bin/common.sh\"; "
                "printf 'config=%s\\nvault=%s\\nstate=%s\\nqmd=%s\\nmem=%s\\n' "
                "\"$ARCLINK_CONFIG_FILE\" \"$VAULT_DIR\" \"$STATE_DIR\" \"$QMD_INDEX_NAME\" \"$ARCLINK_MEMORY_SYNTH_STATE_DIR\"",
            ],
            cwd=REPO,
            env={
                **os.environ,
                "ARCLINK_REPO_DIR": str(REPO),
                "ARCLINK_RUNTIME_ENV_CONFIG": "1",
                "ARCLINK_RUNTIME_CONFIG_FILE": str(runtime_config),
                "ARCLINK_OPERATOR_ARTIFACT_FILE": str(Path(tmp) / "missing-operator.env"),
                "VAULT_DIR": "/srv/vault",
                "STATE_DIR": "/srv/memory",
                "QMD_INDEX_NAME": "vault-dep_1",
                "ARCLINK_MEMORY_SYNTH_STATE_DIR": "/srv/memory",
                "ARCLINK_MEMORY_SYNTH_API_KEY": "must-not-be-written",
                "CHUTES_API_KEY": "must-not-be-written-either",
            },
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        expect(result.returncode == 0, f"entrypoint runtime config failed: stdout={result.stdout!r} stderr={result.stderr!r}")
        expect(f"config={runtime_config}" in result.stdout, result.stdout)
        expect("vault=/srv/vault" in result.stdout, result.stdout)
        expect("state=/srv/memory" in result.stdout, result.stdout)
        expect("qmd=vault-dep_1" in result.stdout, result.stdout)
        expect("mem=/srv/memory" in result.stdout, result.stdout)
        body = runtime_config.read_text(encoding="utf-8")
        expect("ARCLINK_MEMORY_SYNTH_API_KEY" not in body, body)
        expect("CHUTES_API_KEY" not in body, body)
        expect("must-not-be-written" not in body, body)
    print("PASS test_docker_entrypoint_runtime_env_config_preserves_pod_paths_without_secret_spill")


def test_docker_health_script_checks_container_runtime() -> None:
    body = read("bin/docker-health.sh")
    expect("http://arclink-mcp:8282/health" in body, body)
    expect("http://notion-webhook:8283/health" in body, body)
    expect("http://nextcloud/status.php" in body, body)
    expect("Host: $host_header" in body, body)
    expect('check_optional_tcp_with_fallback "qmd-mcp" "${QMD_MCP_CONTAINER_PORT:-8181}"' in body, body)
    expect('"host.docker.internal" "${QMD_MCP_HOST_PORT:-${QMD_MCP_PORT:-8181}}"' in body, body)
    qmd_daemon = read("bin/qmd-daemon.sh")
    expect("QMD MCP TCP forwarder listening" in qmd_daemon, qmd_daemon)
    expect('QMD_PROXY_BIND_HOST:-127.0.0.1' in qmd_daemon, qmd_daemon)
    expect('QMD_PROXY_BIND_HOST: ${QMD_PROXY_BIND_HOST:-0.0.0.0}' in read("compose.yaml"), read("compose.yaml"))
    expect('"postgres" "5432"' in body, body)
    expect('"redis" "6379"' in body, body)
    expect("check_docker_agent_mcp_auth" in body, body)
    expect('"control-ingress" "8080" "Traefik ingress (HTTP)"' in body, body)
    expect("check_control_ingress_https()" in body, body)
    compose_body = read("compose.yaml")
    expect("--ping=true" in compose_body and "--ping.entrypoint=web" in compose_body, compose_body)
    expect('"$control_url" == http://* || "$control_url" == https://*' in body, body)
    expect('ARCLINK_CONTROL_PRIVATE_BASE_URL:-' in body, body)
    expect('ARCLINK_WIREGUARD_CONTROL_URL:-' in body, body)
    expect('ARCLINK_CONTROL_PRIVATE_BIND_HOST:-' in compose_body, compose_body)
    expect('ARCLINK_CONTROL_PRIVATE_HTTP_PORT:-' in compose_body, compose_body)
    expect('ARCLINK_TAILSCALE_CONTROL_URL:-' in body, body)
    expect("configured private/Tailscale route" in body, body)
    expect('status in ("warn", "warning", "disabled")' in body, body)
    for job in (
        "control-provisioner",
        "control-action-worker",
        "ssot-batcher",
        "notification-delivery",
        "health-watch",
        "fleet-inventory-worker",
        "curator-refresh",
        "qmd-refresh",
        "pdf-ingest",
        "memory-synth",
        "hermes-docs-sync",
    ):
        expect(job in body, f"docker health must inspect recurring job {job}\n{body}")
    expect('data.get("job_name") or data.get("job")' in body, body)
    expect('data.get("exit_code") if "exit_code" in data else data.get("returncode", 0)' in body, body)
    expect('eval "$(' not in body, "docker health must not eval JSON status fields")
    expect("validate_token" in body and "MCP token validates" in body, body)
    expect("arclink-managed-context" in body and "SOUL.md" in body, body)
    expect("arclink-vault-reconciler.json" in body, body)
    expect("Summary: %d ok, %d warn, %d fail" in body, body)
    print("PASS test_docker_health_script_checks_container_runtime")


def test_dockerignore_excludes_sensitive_and_generated_context() -> None:
    body = read(".dockerignore")
    for pattern in (
        "/.env",
        "/.env.*",
        "/config/arclink.env",
        "/config/install.answers.env",
        "/.arclink-operator.env",
        "/arclink-priv",
        "/logs",
        "/consensus",
        "/completion_log",
        "/.ralphie",
        "HUMAN_INSTRUCTIONS.md",
        "/research/HUMAN_FEEDBACK.md",
        "arclink-priv/**",
        "node_modules",
        "**/node_modules",
        ".next",
        "**/.next",
        "*.sqlite3",
        "*.sqlite3-shm",
        "*.sqlite3-wal",
    ):
        expect(pattern in body, f"missing .dockerignore pattern {pattern}\n{body}")
    print("PASS test_dockerignore_excludes_sensitive_and_generated_context")


def test_docker_docs_cover_socket_and_private_state_boundaries() -> None:
    body = read("docs/docker.md")
    for service in ("deployment-exec-broker", "migration-capture-helper", "agent-user-helper", "agent-process-helper", "gateway-exec-broker"):
        expect(f"| `{service}` |" in body, f"docs/docker.md must document socket boundary for {service}\n{body}")
    expect("| `control-ingress` |" not in body, body)
    expect("control-ingress` now uses a static Traefik file-provider config" in body, body)
    expect("config/traefik-control.yaml" in body, body)
    expect("control-provisioner` no longer mounts the Docker socket" in body, body)
    expect("control-action-worker` no longer mounts the Docker socket" in body, body)
    expect("control-action-worker` no longer runs as root" in body, body)
    expect("migration-capture-helper` intentionally runs as root" in body, body)
    expect("agent-user-helper`" in body and "ensure_user_home" in body, body)
    expect("agent-process-helper`" in body and "ARCLINK_AGENT_PROCESS_HELPER_TOKEN" in body, body)
    expect("GAP-019-X" in body and "broad `*arclink-env`" in body and "arclink-priv/secrets/container" in body, body)
    expect("GAP-019-AJ" in body and "desired-process signature" in body and "SIGTERM" in body and "SIGKILL" in body, body)
    expect("GAP-019-AM" in body and "LD_*" in body and "secret-looking" in body, body)
    expect("GAP-019-Z" in body and "agent-supervisor-broker`" in body and "broad private config/state/secrets" in body, body)
    expect("GAP-019-AZ" in body and "ARCLINK_DOCKER_HOST_PRIV_DIR" in body and "private bind roots" in body, body)
    expect("GAP-019-BA" in body and ".arclink-user-ids.json.tmp" in body and "exclusive no-follow" in body, body)
    expect("GAP-019-BB" in body and "rejections.jsonl" in body and "raw request bodies" in body, body)
    expect("GAP-019-BC" in body and "_broker-incidents/gateway-exec-broker/rejections.jsonl" in body, body)
    expect("GAP-019-BD" in body and "_helper-incidents/migration-capture-helper/rejections.jsonl" in body, body)
    operations_doc = read("docs/arclink/operations-runbook.md")
    data_safety_doc = read("docs/arclink/data-safety.md")
    expect("GAP-019-BA" in operations_doc and ".arclink-user-ids.json.tmp" in operations_doc, operations_doc)
    expect("GAP-019-BA" in data_safety_doc and ".arclink-user-ids.json.tmp" in data_safety_doc, data_safety_doc)
    expect("GAP-019-BB" in operations_doc and "rejections.jsonl" in operations_doc, operations_doc)
    expect("GAP-019-BB" in data_safety_doc and "rejections.jsonl" in data_safety_doc, data_safety_doc)
    expect("GAP-019-BC" in operations_doc and "_broker-incidents/gateway-exec-broker/rejections.jsonl" in operations_doc, operations_doc)
    expect("GAP-019-BC" in data_safety_doc and "_broker-incidents/gateway-exec-broker/rejections.jsonl" in data_safety_doc, data_safety_doc)
    expect("GAP-019-BD" in operations_doc and "operator-upgrade-broker" in operations_doc, operations_doc)
    expect("GAP-019-BD" in data_safety_doc and "operator-upgrade-broker" in data_safety_doc, data_safety_doc)
    expect("GAP-019-AY" in body and "gateway-exec-broker`" in body and "config/arclink.env" in body, body)
    expect("notification-delivery` also no longer mounts the Docker socket" in body, body)
    expect("curator-refresh` no longer mounts the Docker socket" in body, body)
    expect("writeable Docker socket access has host-root-equivalent capabilities" in body, body)
    expect("control-ingress` no longer mounts the Docker socket" in body, body)
    expect("Non-root socket services drop all Linux capabilities" in body, body)
    expect("GAP-019-B2" in body and "generic Docker socket proxy" in body, body)
    expect("GAP-019-M" in body and "incident controls" in body and "fail closed" in body, body)
    expect("GAP-019-AL" in body and TRUSTED_HOST_RISK_ENV in body and "accepted" in body, body)
    expect("GAP-019-AP" in body and "127.0.0.1" in body and "0.0.0.0" in body, body)
    expect("ARCLINK_DOCKER_SOCKET_GID" in body and "shared ArcLink app image as the `arclink` Unix user" in body, body)
    expect("recurring" in body and "job status files" in body, body)
    expect("health-watch` service does not mount the Docker socket" in body, body)
    print("PASS test_docker_docs_cover_socket_and_private_state_boundaries")


def test_readme_keeps_canonical_host_layout_root() -> None:
    body = read("README.md")
    expect("Sovereign Control Node" in body, body)
    expect("ArcPods as Docker deployments on registered fleet workers" in body, body)
    print("PASS test_readme_keeps_canonical_host_layout_root")


def test_readme_distinguishes_control_shared_host_and_docker_paths() -> None:
    body = read("README.md")
    expect("## Current Architecture" in body, body)
    expect("| Sovereign Control Node |" in body, body)
    expect("| Fleet Inventory |" in body, body)
    expect("| ArcPods |" in body, body)
    expect("The public install surface is now one lane" in body, body)
    expect("./deploy.sh control install" in body and "./deploy.sh install     # control install" in body, body)
    expect("./deploy.sh docker install" not in body, body)
    expect("The old Shared Host/systemd installer and the public Shared Host Docker menu" in body, body)
    expect("Fleet growth now happens by registering worker machines" in body, body)
    expect("Component apply commands commit/push the pin change" in body, body)
    print("PASS test_readme_distinguishes_control_shared_host_and_docker_paths")


def test_sovereign_ingress_docs_cover_domain_and_tailscale_modes() -> None:
    ingress = read("docs/arclink/ingress-plan.md")
    live = read("docs/arclink/live-e2e-secrets-needed.md")
    control_node = read("docs/arclink/sovereign-control-node.md")
    expect("ARCLINK_INGRESS_MODE=domain" in ingress and "ARCLINK_INGRESS_MODE=tailscale" in ingress, ingress)
    expect("u-{prefix}.{base_domain}" in ingress and "hermes-{prefix}.{base_domain}" in ingress, ingress)
    expect("https://{tailscale_dns_name}/u/{prefix}/drive" in ingress, ingress)
    expect("cloudflare_access_tcp" in ingress and "tailscale_direct_ssh" in ingress, ingress)
    expect("Domain mode:" in live and "Tailscale mode:" in live, live)
    expect("ARCLINK_INGRESS_MODE=domain" in control_node and "tailscale" in control_node, control_node)
    print("PASS test_sovereign_ingress_docs_cover_domain_and_tailscale_modes")


def test_docker_compose_config_validates_when_docker_is_available() -> None:
    docker = subprocess.run(["bash", "-lc", "command -v docker >/dev/null && docker compose version >/dev/null"], cwd=REPO)
    if docker.returncode != 0:
        print("SKIP test_docker_compose_config_validates_when_docker_is_available")
        return
    result = subprocess.run(
        ["docker", "compose", "-f", "compose.yaml", "config", "-q"],
        cwd=REPO,
        env={
            **os.environ,
            "POSTGRES_PASSWORD": "compose-config-test-postgres",
            "NEXTCLOUD_ADMIN_PASSWORD": "compose-config-test-nextcloud",
            "ARCLINK_OPERATOR_NEXTCLOUD_DB_PASSWORD": "compose-config-test-operator-postgres",
            "ARCLINK_OPERATOR_NEXTCLOUD_ADMIN_PASSWORD": "compose-config-test-operator-nextcloud",
            "ARCLINK_GATEWAY_EXEC_BROKER_TOKEN": "compose-config-test-broker-token",
            "ARCLINK_DEPLOYMENT_EXEC_BROKER_TOKEN": "compose-config-test-deployment-broker-token",
            "ARCLINK_AGENT_SUPERVISOR_BROKER_TOKEN": "compose-config-test-agent-supervisor-broker-token",
            "ARCLINK_OPERATOR_UPGRADE_BROKER_TOKEN": "compose-config-test-operator-upgrade-broker-token",
            "ARCLINK_AGENT_USER_HELPER_TOKEN": "compose-config-test-agent-user-helper-token",
            "ARCLINK_AGENT_PROCESS_HELPER_TOKEN": "compose-config-test-agent-process-helper-token",
            "ARCLINK_MIGRATION_CAPTURE_HELPER_TOKEN": "compose-config-test-migration-helper-token",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    expect(result.returncode == 0, f"compose config failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    print("PASS test_docker_compose_config_validates_when_docker_is_available")


def main() -> int:
    test_dockerfile_installs_pinned_runtime_assets()
    test_compose_defines_full_stack_services()
    test_control_ingress_uses_static_traefik_config_without_docker_socket()
    test_control_ingress_static_routes_cover_control_api_web_llm_and_notion()
    test_compose_high_authority_brokers_and_helpers_are_scoped_off_default_network()
    test_compose_high_authority_services_receive_trusted_host_acceptance_gate()
    test_high_authority_helpers_default_to_loopback_outside_compose()
    test_trusted_host_acceptance_gate_blocks_brokers_and_helpers_before_work()
    test_agent_user_helper_root_boundary_uses_explicit_minimum_capabilities()
    test_agent_process_helper_compose_boundary_minimizes_env_and_secret_mounts()
    test_gateway_exec_broker_compose_boundary_minimizes_env_and_private_mounts()
    test_deployment_exec_broker_compose_boundary_minimizes_env_and_private_mounts()
    test_migration_capture_helper_compose_boundary_minimizes_env_and_confines_state_root()
    test_agent_supervisor_broker_compose_boundary_minimizes_env_and_private_mounts()
    test_operator_upgrade_broker_compose_boundary_minimizes_env_and_private_mounts()
    test_docker_authority_inventory_matches_compose_boundary()
    test_operator_upgrade_broker_runs_allowlisted_operator_upgrade()
    test_operator_upgrade_broker_skips_deploy_when_pin_upgrade_noops()
    test_operator_upgrade_broker_signature_replay_cache_is_bounded()
    test_operator_upgrade_broker_rejects_raw_or_unsafe_requests()
    test_operator_upgrade_broker_rejects_unscoped_upstream_deploy_key_paths_before_log_or_subprocess()
    test_operator_upgrade_broker_rejects_unsafe_docker_binary_before_subprocess()
    test_docker_agent_supervisor_rejects_unsafe_metadata_before_root_ops()
    test_agent_user_helper_rejects_raw_commands_and_unscoped_paths()
    test_agent_user_helper_requires_trusted_absolute_root_executables()
    test_agent_user_helper_rejects_configured_home_root_mismatch()
    test_agent_user_helper_rejects_symlinked_uid_assignment_files_before_root_work()
    test_agent_helpers_reject_symlink_escaped_agent_paths()
    test_agent_helpers_reject_symlinked_home_root_before_root_work()
    test_agent_process_helper_rejects_symlink_escaped_log_directory()
    test_agent_process_helper_rejects_symlinked_or_missing_repo_command_targets_before_subprocess()
    test_docker_agent_supervisor_requires_user_helper_before_root_user_ops()
    test_agent_process_helper_rejects_raw_commands_and_runs_allowlisted_agent_ops()
    test_remaining_high_authority_services_record_redacted_rejection_incidents()
    test_agent_process_helper_rejects_unapproved_agent_env_keys_before_subprocess()
    test_agent_process_helper_rejects_unsafe_dashboard_backend_host_before_subprocess()
    test_agent_process_helper_rejects_configured_root_mismatch()
    test_agent_process_helper_rejects_symlinked_configured_roots_before_work()
    test_agent_process_helper_does_not_log_or_argv_env_values()
    test_agent_process_helper_restarts_processes_when_desired_signature_changes()
    test_docker_agent_supervisor_does_not_forward_helper_tokens_to_agent_processes()
    test_agent_supervisor_provisioner_child_env_is_allowlisted()
    test_docker_agent_supervisor_rejects_unapproved_agent_process_env_keys()
    test_docker_agent_supervisor_delegates_process_launch_to_process_helper()
    test_docker_operator_commands_are_present()
    test_docker_repair_backfills_dashboard_sso_and_crew_links()
    test_docker_repair_strips_control_network_for_remote_deployments()
    test_deployment_hermes_home_installer_seeds_runtime_knowledge()
    test_docker_tailnet_publish_uses_dashboard_native_plugin_urls()
    test_docker_tailnet_forward_pidfile_tracking_prunes_nohup_forwards()
    test_docker_tailnet_publish_failure_withholds_app_urls()
    test_docker_component_upgrade_apply_loads_upstream_env_from_docker_config()
    test_docker_agent_supervisor_replaces_user_systemd_units()
    test_agent_supervisor_broker_rejects_raw_commands_and_builds_dashboard_proxy()
    test_agent_supervisor_broker_rejects_unsafe_dashboard_backend_host()
    test_agent_supervisor_broker_rejects_unsafe_private_bind_roots_before_dashboard_proxy()
    test_deployment_exec_broker_rejects_unsafe_docker_binary_before_subprocess()
    test_gateway_exec_broker_rejects_unsafe_docker_binary_before_subprocess()
    test_agent_supervisor_broker_rejects_unsafe_docker_binary_before_subprocess()
    test_docker_entrypoint_generates_fresh_secrets()
    test_docker_entrypoint_runtime_env_config_preserves_pod_paths_without_secret_spill()
    test_docker_health_script_checks_container_runtime()
    test_dockerignore_excludes_sensitive_and_generated_context()
    test_docker_docs_cover_socket_and_private_state_boundaries()
    test_readme_keeps_canonical_host_layout_root()
    test_readme_distinguishes_control_shared_host_and_docker_paths()
    test_sovereign_ingress_docs_cover_domain_and_tailscale_modes()
    test_docker_compose_config_validates_when_docker_is_available()
    print("PASS all 61 ArcLink Docker regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
