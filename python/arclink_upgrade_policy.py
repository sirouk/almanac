#!/usr/bin/env python3
"""Source-owned upgrade policy for ArcLink dependencies and ArcPod rollouts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


PIN_UPGRADE_COMPONENTS = (
    "hermes",
    "qmd",
    "nextcloud",
    "postgres",
    "redis",
    "nvm",
    "node",
)

STATEFUL_PIN_UPGRADE_COMPONENTS = frozenset({"nextcloud", "postgres", "redis"})


@dataclass(frozen=True)
class UpgradePolicy:
    component: str
    label: str
    scope: str
    operator_command: str
    rollout_order: int
    strategy: str
    downtime_posture: str
    default_batch_size: str
    preflight_checks: tuple[str, ...]
    proof_gates: tuple[str, ...]
    rollback_contract: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("preflight_checks", "proof_gates", "rollback_contract", "notes"):
            payload[key] = list(payload[key])
        return payload


_POLICIES: tuple[UpgradePolicy, ...] = (
    UpgradePolicy(
        component="arclink-control",
        label="ArcLink Control Plane",
        scope="control-plane",
        operator_command="/upgrade",
        rollout_order=10,
        strategy="Upgrade the Control Node first, then run health/readiness before any ArcPod batch starts.",
        downtime_posture="Short control-surface maintenance is acceptable; live ArcPods must keep serving from their existing worker homes.",
        default_batch_size="one control stack",
        preflight_checks=(
            "upstream branch and deploy-key write/read health",
            "control DB schema backup",
            "container build and static configuration render",
            "admin action worker and operator-action broker readiness",
        ),
        proof_gates=("PG-PROD", "PG-UPGRADE"),
        rollback_contract=(
            "preserve arclink-priv and control DB state",
            "restore previous release metadata",
            "keep pending action queues durable",
        ),
        notes=("This is the parent release gate for dependency and ArcPod rollouts.",),
    ),
    UpgradePolicy(
        component="hermes",
        label="Hermes Runtime",
        scope="arcpod-runtime",
        operator_command="/pin_upgrade hermes, then /rollout <target>",
        rollout_order=20,
        strategy="Pin and stage centrally, canary one ArcPod, then bounded ArcPod batches with stop-on-failure.",
        downtime_posture="Target near-zero downtime per Captain by leaving non-batch Pods untouched and restarting only the selected Pod services.",
        default_batch_size="1 canary, then ARCLINK_ARCPOD_UPDATE_BATCH_SIZE capped by ARCLINK_ARCPOD_UPDATE_MAX_BATCH_SIZE",
        preflight_checks=(
            "candidate deployment state roots",
            "Hermes gateway/dashboard/qmd health",
            "managed-context token repair",
            "bundled skills and docs ref alignment",
        ),
        proof_gates=("PG-UPGRADE", "PG-HERMES"),
        rollback_contract=(
            "preserve vault, state, SOUL.md, and Hermes home",
            "restore previous runtime ref",
            "restart previous services on failed batch",
        ),
    ),
    UpgradePolicy(
        component="hermes-docs",
        label="Hermes Documentation",
        scope="arcpod-runtime",
        operator_command="/rollout <target> after the docs ref is pinned with the runtime",
        rollout_order=25,
        strategy="Ship docs with the same ArcPod refresh batch as Hermes so agent-facing guidance cannot drift ahead of runtime behavior.",
        downtime_posture="No independent downtime; docs sync rides the ArcPod refresh.",
        default_batch_size="same as Hermes runtime rollout",
        preflight_checks=("pinned docs ref", "Hermes docs sync smoke", "managed recall-stub render"),
        proof_gates=("PG-UPGRADE", "PG-HERMES"),
        rollback_contract=("restore previous docs ref", "preserve agent vault and memory stubs"),
    ),
    UpgradePolicy(
        component="dashboard-plugins",
        label="Drive, Code, Terminal, and Managed Context Plugins",
        scope="arcpod-runtime",
        operator_command="/rollout <target>",
        rollout_order=30,
        strategy="Install from ArcLink wrappers during ArcPod refresh, then verify plugin manifests and sidebar exposure per Pod.",
        downtime_posture="No fleet-wide downtime; plugin refresh is per-Pod and batch bounded.",
        default_batch_size="same as Hermes runtime rollout",
        preflight_checks=("plugin manifest presence", "dashboard auth proxy health", "Drive/Code/Terminal surface smoke"),
        proof_gates=("PG-UPGRADE", "PG-HERMES", "PG-BOTS"),
        rollback_contract=("preserve plugin config", "restore previous ArcLink plugin bundle"),
    ),
    UpgradePolicy(
        component="qmd",
        label="qmd Retrieval",
        scope="knowledge-plane",
        operator_command="/pin_upgrade qmd, then /rollout <target> for ArcPods that consume the new index path",
        rollout_order=35,
        strategy="Upgrade the shared qmd service/pin first, then refresh per-Pod qmd collection wiring in rollout batches.",
        downtime_posture="Search may be briefly stale during re-index; chat and dashboards should continue serving.",
        default_batch_size="control service first, then ArcPod batches",
        preflight_checks=("vault/qmd collection definitions", "index freshness", "memory synthesis cache bounds"),
        proof_gates=("PG-UPGRADE", "PG-HERMES"),
        rollback_contract=("keep previous qmd index data until new index proves healthy", "preserve vault source files"),
    ),
    UpgradePolicy(
        component="academy",
        label="Academy Trainer and Continuing Education",
        scope="knowledge-plane",
        operator_command="/academy_status, /academy_roster, academy_apply actions after proof",
        rollout_order=40,
        strategy="Keep live acquisition/provider work gated; roll schema, scheduler, and apply handoff first, then prove source lanes before automatic application.",
        downtime_posture="No downtime; Academy jobs are asynchronous and no-write unless an authorized apply action runs.",
        default_batch_size="scheduler fan-out with per-graduate idempotency",
        preflight_checks=("source-lane policy", "trainer review gate", "post-apply qmd/memory/skill refresh request"),
        proof_gates=("PG-PROVIDER", "PG-HERMES"),
        rollback_contract=("preserve graduate records", "replace only marker-bounded Academy SOUL section", "retain prior capsule version"),
    ),
    UpgradePolicy(
        component="memory-synth",
        label="Memory Synthesis",
        scope="knowledge-plane",
        operator_command="rolls with ArcPod refresh and vault-watch synthesis jobs",
        rollout_order=45,
        strategy="Keep synthesis off the chat critical path; request async refreshes after vault/shared/Academy changes and skip unchanged signatures.",
        downtime_posture="No downtime; stale memory cards degrade to retrieval hints rather than blocking chat.",
        default_batch_size="timer/watch driven, bounded by source signatures",
        preflight_checks=("vault signature cache", "shared Fleet/Linked source scope", "card output bounds"),
        proof_gates=("PG-HERMES",),
        rollback_contract=("preserve source files", "retain older cards until replacement cards are valid"),
    ),
    UpgradePolicy(
        component="node",
        label="Node.js Runtime",
        scope="build-runtime",
        operator_command="/pin_upgrade node",
        rollout_order=50,
        strategy="Pin centrally, rebuild web/control images, then ship ArcPod dashboard assets through normal rollout gates.",
        downtime_posture="Control web may restart; live ArcPods keep running until their batch refresh.",
        default_batch_size="control build first, then ArcPod batches if dashboard assets changed",
        preflight_checks=("npm ci", "web lint", "web tests", "web build"),
        proof_gates=("PG-PROD", "PG-UPGRADE"),
        rollback_contract=("restore previous node pin", "restore previous built image/release"),
    ),
    UpgradePolicy(
        component="nvm",
        label="nvm Installer",
        scope="build-runtime",
        operator_command="/pin_upgrade nvm",
        rollout_order=55,
        strategy="Treat as a build-lane dependency: update before Node only when the install/bootstrap lane needs it.",
        downtime_posture="No user downtime by itself.",
        default_batch_size="control/bootstrap lane only",
        preflight_checks=("bootstrap smoke", "node pin still resolves"),
        proof_gates=("PG-UPGRADE",),
        rollback_contract=("restore previous nvm pin",),
    ),
    UpgradePolicy(
        component="postgres",
        label="Postgres",
        scope="stateful-infra",
        operator_command="/pin_upgrade postgres",
        rollout_order=60,
        strategy="Stateful maintenance lane: snapshot/backup first, upgrade one primary service, validate schema and queue drains, then resume.",
        downtime_posture="Brief planned maintenance is acceptable; do not pretend this is a stateless rolling update.",
        default_batch_size="one stateful service",
        preflight_checks=("backup freshness", "schema migration dry-run", "disk headroom", "operator maintenance window"),
        proof_gates=("PG-PROD", "PG-UPGRADE"),
        rollback_contract=("restore database backup/snapshot", "preserve action queues and audit log"),
    ),
    UpgradePolicy(
        component="redis",
        label="Redis",
        scope="stateful-infra",
        operator_command="/pin_upgrade redis",
        rollout_order=65,
        strategy="Upgrade as control-plane cache/queue infrastructure after draining or pausing volatile workers as needed.",
        downtime_posture="Brief queue/cache interruption is acceptable if action queues remain durable in SQLite/control DB.",
        default_batch_size="one stateful service",
        preflight_checks=("control DB queues durable", "worker pause/drain plan", "cache warmup after restart"),
        proof_gates=("PG-PROD", "PG-UPGRADE"),
        rollback_contract=("restore previous Redis image", "replay durable queues from control DB"),
    ),
    UpgradePolicy(
        component="nextcloud",
        label="Nextcloud / Shared File Service",
        scope="stateful-infra",
        operator_command="/pin_upgrade nextcloud",
        rollout_order=70,
        strategy="Snapshot shared file state, pause risky file mutation if needed, upgrade, then run sharing/read-write proof.",
        downtime_posture="Short shared-drive maintenance is acceptable; ArcPods should keep local state and retry shared access.",
        default_batch_size="one shared file service",
        preflight_checks=("shared folder permissions", "read/write proof", "backup freshness"),
        proof_gates=("PG-PROD", "PG-HERMES", "PG-BACKUP"),
        rollback_contract=("restore shared file snapshot", "preserve share ACLs and Fleet/Linked ownership"),
    ),
    UpgradePolicy(
        component="docker",
        label="Docker / Worker Runtime",
        scope="worker-fabric",
        operator_command="/fleet_drain <worker>, perform worker maintenance, /fleet_resume <worker>",
        rollout_order=80,
        strategy="Drain one worker, move or leave new placements away from it, update worker runtime, smoke local ArcPod lifecycle, then resume.",
        downtime_posture="No planned Captain downtime if capacity exists; otherwise block unless the operator forces a maintenance window.",
        default_batch_size="one worker at a time",
        preflight_checks=("other eligible worker capacity", "WireGuard control reachability", "ArcPod placement headroom"),
        proof_gates=("PG-FLEET", "PG-PROVISION", "PG-UPGRADE"),
        rollback_contract=("resume previous worker runtime", "keep deployment state roots on disk", "do not delete ArcPod homes during maintenance"),
    ),
    UpgradePolicy(
        component="wireguard",
        label="WireGuard Fleet Mesh",
        scope="worker-fabric",
        operator_command="/fleet_drain <worker>, rotate/repair mesh, /fleet_resume <worker>",
        rollout_order=85,
        strategy="Rotate or repair one peer at a time through the control-owned mesh, preserving SSH keys and port 22 policy.",
        downtime_posture="No fleet-wide downtime; affected worker is drained before mesh work.",
        default_batch_size="one worker peer",
        preflight_checks=("control endpoint", "peer public key", "private control URL", "firewall allowance"),
        proof_gates=("PG-FLEET", "PG-UPGRADE"),
        rollback_contract=("restore previous peer config", "do not remove unrelated SSH keys or change sshd_config"),
    ),
)

_ALIASES = {
    "control": "arclink-control",
    "control-plane": "arclink-control",
    "arclink": "arclink-control",
    "plugins": "dashboard-plugins",
    "dashboard_plugins": "dashboard-plugins",
    "drive": "dashboard-plugins",
    "code": "dashboard-plugins",
    "terminal": "dashboard-plugins",
    "docs": "hermes-docs",
    "hermes_docs": "hermes-docs",
    "memory": "memory-synth",
    "memory_synth": "memory-synth",
    "wg": "wireguard",
}


def normalize_upgrade_component(component: str) -> str:
    clean = str(component or "").strip().lower().replace("_", "-")
    return _ALIASES.get(clean, clean)


def upgrade_policy_catalog() -> list[dict[str, Any]]:
    return [policy.to_dict() for policy in sorted(_POLICIES, key=lambda item: item.rollout_order)]


def upgrade_policy_for(component: str) -> dict[str, Any]:
    clean = normalize_upgrade_component(component)
    for policy in _POLICIES:
        if policy.component == clean:
            return policy.to_dict()
    known = ", ".join(policy.component for policy in sorted(_POLICIES, key=lambda item: item.component))
    raise ValueError(f"unknown ArcLink upgrade component '{component}'. Known components: {known}")


def upgrade_policy_summary(component: str = "") -> dict[str, Any]:
    if str(component or "").strip():
        policy = upgrade_policy_for(component)
        return {
            "mode": "component",
            "component": policy["component"],
            "policy": policy,
            "mutation_performed": False,
        }
    catalog = upgrade_policy_catalog()
    groups: dict[str, list[str]] = {}
    for policy in catalog:
        groups.setdefault(str(policy["scope"]), []).append(str(policy["component"]))
    return {
        "mode": "catalog",
        "catalog": catalog,
        "groups": groups,
        "mutation_performed": False,
        "default_sequence": [str(policy["component"]) for policy in catalog],
    }


def policy_components_by_scope(summary: Mapping[str, Any]) -> list[tuple[str, list[str]]]:
    groups = summary.get("groups") if isinstance(summary, Mapping) else {}
    if not isinstance(groups, Mapping):
        return []
    return [(str(scope), [str(item) for item in components]) for scope, components in sorted(groups.items())]
