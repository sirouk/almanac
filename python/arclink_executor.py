#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol


class ArcLinkExecutorError(RuntimeError):
    pass


class ArcLinkLiveExecutionRequired(ArcLinkExecutorError):
    pass


class ArcLinkSecretResolutionError(ArcLinkExecutorError):
    pass


_SECRET_REF_RE = re.compile(r"^secret://[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_RUN_SECRET_RE = re.compile(r"^/run/secrets/[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _require_secret_ref(secret_ref: str) -> str:
    clean = str(secret_ref or "").strip()
    if not _SECRET_REF_RE.fullmatch(clean):
        raise ArcLinkSecretResolutionError("ArcLink secret references must use secret://")
    return clean


def _require_run_secret_path(target_path: str) -> str:
    clean = str(target_path or "").strip()
    if not _RUN_SECRET_RE.fullmatch(clean):
        raise ArcLinkSecretResolutionError("ArcLink resolved secret targets must be under /run/secrets")
    return clean


@dataclass(frozen=True)
class ArcLinkExecutorConfig:
    live_enabled: bool = False
    adapter_name: str = "disabled"


@dataclass(frozen=True)
class ResolvedSecretFile:
    secret_ref: str
    target_path: str
    materialized: bool = True


class SecretResolver(Protocol):
    def materialize(self, secret_ref: str, target_path: str) -> ResolvedSecretFile:
        ...


@dataclass
class FakeSecretResolver:
    values: Mapping[str, str]
    resolved: list[ResolvedSecretFile] = field(default_factory=list)

    def materialize(self, secret_ref: str, target_path: str) -> ResolvedSecretFile:
        clean_ref = _require_secret_ref(secret_ref)
        clean_target = _require_run_secret_path(target_path)
        if clean_ref not in self.values:
            raise ArcLinkSecretResolutionError(f"missing ArcLink secret reference: {clean_ref}")
        if not str(self.values[clean_ref]):
            raise ArcLinkSecretResolutionError(f"empty ArcLink secret material: {clean_ref}")
        resolved = ResolvedSecretFile(secret_ref=clean_ref, target_path=clean_target)
        self.resolved.append(resolved)
        return resolved


@dataclass
class FileMaterializingSecretResolver:
    value_provider: Callable[[str], str]
    materialization_root: Path

    def materialize(self, secret_ref: str, target_path: str) -> ResolvedSecretFile:
        clean_ref = _require_secret_ref(secret_ref)
        clean_target = _require_run_secret_path(target_path)
        value = self.value_provider(clean_ref)
        if not str(value):
            raise ArcLinkSecretResolutionError(f"empty ArcLink secret material: {clean_ref}")
        output = self.materialization_root / Path(clean_target).name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(str(value), encoding="utf-8")
        output.chmod(0o600)
        return ResolvedSecretFile(secret_ref=clean_ref, target_path=clean_target)


@dataclass(frozen=True)
class DockerComposeApplyRequest:
    deployment_id: str
    intent: Mapping[str, Any]
    project_name: str = ""
    idempotency_key: str = ""
    fake_fail_after_services: int | None = None


@dataclass(frozen=True)
class DockerComposeApplyResult:
    deployment_id: str
    project_name: str
    live: bool
    status: str
    services: tuple[str, ...]
    volumes: tuple[str, ...]
    secrets: Mapping[str, str]
    env_file: str = ""
    compose_file: str = ""
    service_start_order: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CloudflareDnsApplyRequest:
    deployment_id: str
    dns: Mapping[str, Mapping[str, Any]]
    zone_id: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True)
class CloudflareDnsApplyResult:
    deployment_id: str
    live: bool
    status: str
    records: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CloudflareAccessApplyRequest:
    deployment_id: str
    access: Mapping[str, Any]
    idempotency_key: str = ""


@dataclass(frozen=True)
class CloudflareAccessApplyResult:
    deployment_id: str
    live: bool
    status: str
    applications: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChutesKeyApplyRequest:
    deployment_id: str
    action: str
    secret_ref: str = ""
    label: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True)
class ChutesKeyApplyResult:
    deployment_id: str
    live: bool
    status: str
    action: str
    key_id: str
    secret_ref: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StripeActionApplyRequest:
    deployment_id: str
    action: str
    customer_ref: str = ""
    idempotency_key: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StripeActionApplyResult:
    deployment_id: str
    live: bool
    status: str
    action: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RollbackApplyRequest:
    deployment_id: str
    plan: Mapping[str, Any]
    idempotency_key: str = ""


@dataclass(frozen=True)
class RollbackApplyResult:
    deployment_id: str
    live: bool
    status: str
    actions: tuple[str, ...]
    preserve_state_roots: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ArcLinkExecutor:
    def __init__(self, *, config: ArcLinkExecutorConfig | None = None, secret_resolver: SecretResolver | None = None) -> None:
        self.config = config or ArcLinkExecutorConfig()
        self.secret_resolver = secret_resolver
        self._fake_docker_runs: dict[str, dict[str, Any]] = {}
        self._fake_dns_runs: dict[str, dict[str, Any]] = {}
        self._fake_access_runs: dict[str, dict[str, Any]] = {}
        self._fake_chutes_runs: dict[str, dict[str, Any]] = {}
        self._fake_chutes_keys: dict[str, dict[str, Any]] = {}
        self._fake_rollback_runs: dict[str, dict[str, Any]] = {}

    def _require_live_enabled(self, operation: str) -> None:
        if not self.config.live_enabled:
            raise ArcLinkLiveExecutionRequired(f"{operation} requires ARCLINK live/E2E execution to be explicitly enabled")

    def docker_compose_apply(self, request: DockerComposeApplyRequest) -> DockerComposeApplyResult:
        self._require_live_enabled("docker_compose_apply")
        intent = dict(request.intent)
        compose = dict(intent.get("compose") or {})
        services = dict(compose.get("services") or {})
        compose_secrets = dict(compose.get("secrets") or {})
        plan = _plan_docker_compose_apply(request=request, intent=intent, services=services)
        if self.config.adapter_name == "fake":
            return self._fake_docker_compose_apply(request=request, plan=plan, compose_secrets=compose_secrets)
        resolved = self._materialize_compose_secrets(compose_secrets)
        return DockerComposeApplyResult(
            deployment_id=request.deployment_id,
            project_name=str(plan["project_name"]),
            live=True,
            status="applied",
            services=tuple(plan["services"]),
            volumes=tuple(plan["volumes"]),
            secrets={name: item.target_path for name, item in resolved.items()},
            env_file=str(plan["env_file"]),
            compose_file=str(plan["compose_file"]),
            service_start_order=tuple(plan["service_start_order"]),
            metadata={
                "adapter": self.config.adapter_name,
                "idempotency_key": request.idempotency_key,
                "service_count": len(services),
                "secret_count": len(resolved),
                "label_count": len(plan["labels"]),
            },
        )

    def _fake_docker_compose_apply(
        self,
        *,
        request: DockerComposeApplyRequest,
        plan: Mapping[str, Any],
        compose_secrets: Mapping[str, Any],
    ) -> DockerComposeApplyResult:
        idempotency_key = request.idempotency_key or str(plan["intent_digest"])
        intent_digest = str(plan["intent_digest"])
        existing = self._fake_docker_runs.get(idempotency_key)
        if existing is not None and str(existing.get("intent_digest") or "") != intent_digest:
            raise ArcLinkExecutorError(
                "ArcLink Docker Compose idempotency key was reused with a different rendered intent digest"
            )
        failure_limit = request.fake_fail_after_services
        if failure_limit is not None and failure_limit <= 0:
            raise ArcLinkExecutorError("fake Docker Compose failure limit must be greater than zero")
        if existing is not None and existing["status"] == "applied":
            return self._docker_compose_result_from_state(
                request=request,
                plan=plan,
                secret_targets=dict(existing.get("secret_targets") or {}),
                state=existing,
                idempotent_replay=True,
            )

        resolved = self._materialize_compose_secrets(compose_secrets)
        secret_targets = {name: item.target_path for name, item in resolved.items()}
        service_start_order = tuple(plan["service_start_order"])
        already_applied = tuple(existing.get("applied_services", ())) if existing else ()
        applied = list(already_applied)
        attempts = int(existing.get("attempts", 0)) + 1 if existing else 1
        status = "applied"
        error = ""

        for service_name in service_start_order[len(applied) :]:
            applied.append(service_name)
            if failure_limit is not None and len(applied) >= failure_limit:
                status = "failed"
                error = f"fake Docker Compose apply failed after {len(applied)} services"
                break

        state = {
            "deployment_id": request.deployment_id,
            "project_name": str(plan["project_name"]),
            "intent_digest": intent_digest,
            "status": status,
            "applied_services": tuple(applied),
            "secret_targets": secret_targets,
            "attempts": attempts,
            "error": error,
        }
        self._fake_docker_runs[idempotency_key] = state
        return self._docker_compose_result_from_state(
            request=request,
            plan=plan,
            secret_targets=secret_targets,
            state=state,
            idempotent_replay=False,
            resumed_from_service_count=len(already_applied),
        )

    def _docker_compose_result_from_state(
        self,
        *,
        request: DockerComposeApplyRequest,
        plan: Mapping[str, Any],
        secret_targets: Mapping[str, str],
        state: Mapping[str, Any],
        idempotent_replay: bool,
        resumed_from_service_count: int = 0,
    ) -> DockerComposeApplyResult:
        metadata = {
            "adapter": self.config.adapter_name,
            "idempotency_key": request.idempotency_key,
            "intent_digest": plan["intent_digest"],
            "service_count": len(plan["services"]),
            "secret_count": len(secret_targets),
            "label_count": len(plan["labels"]),
            "applied_services": tuple(state.get("applied_services", ())),
            "attempts": int(state.get("attempts", 0)),
            "idempotent_replay": idempotent_replay,
            "resumed_from_service_count": resumed_from_service_count,
        }
        if state.get("error"):
            metadata["error"] = str(state["error"])
        return DockerComposeApplyResult(
            deployment_id=request.deployment_id,
            project_name=str(plan["project_name"]),
            live=True,
            status=str(state["status"]),
            services=tuple(plan["services"]),
            volumes=tuple(plan["volumes"]),
            secrets=dict(secret_targets),
            env_file=str(plan["env_file"]),
            compose_file=str(plan["compose_file"]),
            service_start_order=tuple(plan["service_start_order"]),
            metadata=metadata,
        )

    def cloudflare_dns_apply(self, request: CloudflareDnsApplyRequest) -> CloudflareDnsApplyResult:
        self._require_live_enabled("cloudflare_dns_apply")
        records = _plan_cloudflare_dns_records(request.dns)
        if self.config.adapter_name == "fake":
            return self._fake_cloudflare_dns_apply(request=request, records=records)
        return CloudflareDnsApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status="applied",
            records=tuple(record["hostname"] for record in records),
            metadata={
                "adapter": self.config.adapter_name,
                "zone_id": request.zone_id,
                "idempotency_key": request.idempotency_key,
                "desired_records": tuple(_dns_record_summary(record) for record in records),
            },
        )

    def cloudflare_access_apply(self, request: CloudflareAccessApplyRequest) -> CloudflareAccessApplyResult:
        self._require_live_enabled("cloudflare_access_apply")
        plan = _plan_cloudflare_access(request.access)
        if self.config.adapter_name == "fake":
            return self._fake_cloudflare_access_apply(request=request, plan=plan)
        return CloudflareAccessApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status="applied",
            applications=tuple(plan["applications"]),
            metadata={
                "adapter": self.config.adapter_name,
                "idempotency_key": request.idempotency_key,
                "ssh_strategy": plan["ssh_strategy"],
                "ssh_hostname": plan["ssh_hostname"],
            },
        )

    def chutes_key_apply(self, request: ChutesKeyApplyRequest) -> ChutesKeyApplyResult:
        self._require_live_enabled("chutes_key_apply")
        action = str(request.action or "").strip()
        if action not in {"create", "rotate", "revoke"}:
            raise ArcLinkExecutorError("unsupported ArcLink Chutes key action")
        secret_ref = _require_secret_ref(request.secret_ref or f"secret://arclink/chutes/{request.deployment_id}")
        if self.config.adapter_name == "fake":
            return self._fake_chutes_key_apply(request=request, action=action, secret_ref=secret_ref)
        digest = hashlib.sha256(f"{request.deployment_id}:{action}:{request.idempotency_key}".encode("utf-8")).hexdigest()[:18]
        return ChutesKeyApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status="applied",
            action=action,
            key_id=f"chutes_key_{digest}",
            secret_ref=secret_ref,
            metadata={"adapter": self.config.adapter_name, "label": request.label, "idempotency_key": request.idempotency_key},
        )

    def stripe_action_apply(self, request: StripeActionApplyRequest) -> StripeActionApplyResult:
        self._require_live_enabled("stripe_action_apply")
        action = str(request.action or "").strip()
        if action not in {"refund", "cancel", "portal"}:
            raise ArcLinkExecutorError("unsupported ArcLink Stripe action")
        metadata = dict(request.metadata)
        if request.customer_ref:
            metadata["customer_ref"] = _require_secret_ref(request.customer_ref)
        metadata["adapter"] = self.config.adapter_name
        metadata["idempotency_key"] = request.idempotency_key
        return StripeActionApplyResult(deployment_id=request.deployment_id, live=True, status="applied", action=action, metadata=metadata)

    def rollback_apply(self, request: RollbackApplyRequest) -> RollbackApplyResult:
        self._require_live_enabled("rollback_apply")
        plan = _plan_rollback_apply(request.plan)
        if self.config.adapter_name == "fake":
            return self._fake_rollback_apply(request=request, plan=plan)
        return RollbackApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status="applied",
            actions=tuple(plan["actions"]),
            preserve_state_roots=True,
            metadata={
                "adapter": self.config.adapter_name,
                "idempotency_key": request.idempotency_key,
                "protected_state_roots": tuple(plan["protected_state_roots"]),
                "secret_refs_for_review": tuple(plan["secret_refs_for_review"]),
            },
        )

    def _fake_cloudflare_dns_apply(
        self,
        *,
        request: CloudflareDnsApplyRequest,
        records: tuple[dict[str, Any], ...],
    ) -> CloudflareDnsApplyResult:
        operation = "cloudflare_dns_apply"
        operation_digest = _operation_digest(operation, request.deployment_id, {"records": records, "zone_id": request.zone_id})
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, {"records": records, "zone_id": request.zone_id})
        existing = self._fake_dns_runs.get(key)
        if existing is None:
            existing = {
                "operation_digest": operation_digest,
                "status": "applied",
                "records": tuple(record["hostname"] for record in records),
                "desired_records": tuple(_dns_record_summary(record) for record in records),
                "proxied_count": sum(1 for record in records if bool(record["proxied"])),
                "idempotent_replay": False,
            }
            self._fake_dns_runs[key] = existing
        else:
            _require_matching_operation_digest(
                existing=existing,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            existing = dict(existing)
            existing["idempotent_replay"] = True
        return CloudflareDnsApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status=str(existing["status"]),
            records=tuple(existing["records"]),
            metadata={
                "adapter": self.config.adapter_name,
                "zone_id": request.zone_id,
                "idempotency_key": request.idempotency_key,
                "desired_records": tuple(existing["desired_records"]),
                "proxied_count": int(existing["proxied_count"]),
                "idempotent_replay": bool(existing["idempotent_replay"]),
            },
        )

    def _fake_cloudflare_access_apply(
        self,
        *,
        request: CloudflareAccessApplyRequest,
        plan: Mapping[str, Any],
    ) -> CloudflareAccessApplyResult:
        operation = "cloudflare_access_apply"
        operation_digest = _operation_digest(operation, request.deployment_id, plan)
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, plan)
        existing = self._fake_access_runs.get(key)
        if existing is None:
            existing = {
                "operation_digest": operation_digest,
                "status": "applied",
                "applications": tuple(plan["applications"]),
                "ssh_strategy": plan["ssh_strategy"],
                "ssh_hostname": plan["ssh_hostname"],
                "idempotent_replay": False,
            }
            self._fake_access_runs[key] = existing
        else:
            _require_matching_operation_digest(
                existing=existing,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            existing = dict(existing)
            existing["idempotent_replay"] = True
        return CloudflareAccessApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status=str(existing["status"]),
            applications=tuple(existing["applications"]),
            metadata={
                "adapter": self.config.adapter_name,
                "idempotency_key": request.idempotency_key,
                "ssh_strategy": existing["ssh_strategy"],
                "ssh_hostname": existing["ssh_hostname"],
                "application_count": len(existing["applications"]),
                "idempotent_replay": bool(existing["idempotent_replay"]),
            },
        )

    def _fake_chutes_key_apply(
        self,
        *,
        request: ChutesKeyApplyRequest,
        action: str,
        secret_ref: str,
    ) -> ChutesKeyApplyResult:
        operation = "chutes_key_apply"
        operation_inputs = {"action": action, "label": request.label, "secret_ref": secret_ref}
        operation_digest = _operation_digest(operation, request.deployment_id, operation_inputs)
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, operation_inputs)
        existing_run = self._fake_chutes_runs.get(key)
        if existing_run is not None:
            _require_matching_operation_digest(
                existing=existing_run,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            return ChutesKeyApplyResult(
                deployment_id=request.deployment_id,
                live=True,
                status=str(existing_run["status"]),
                action=str(existing_run["action"]),
                key_id=str(existing_run["key_id"]),
                secret_ref=str(existing_run["secret_ref"]),
                metadata=dict(existing_run["metadata"], idempotent_replay=True),
            )

        current = self._fake_chutes_keys.get(secret_ref)
        metadata: dict[str, Any] = {
            "adapter": self.config.adapter_name,
            "label": request.label,
            "idempotency_key": request.idempotency_key,
            "idempotent_replay": False,
        }
        status = "applied"
        if action == "revoke":
            if current is None:
                key_id = _fake_chutes_key_id(request.deployment_id, secret_ref, 0)
                status = "skipped"
                metadata["missing"] = True
            else:
                key_id = str(current["key_id"])
                current["status"] = "revoked"
                metadata["generation"] = int(current["generation"])
        elif action == "create" and current is not None and current.get("status") == "active":
            key_id = str(current["key_id"])
            metadata["generation"] = int(current["generation"])
            metadata["existing_active"] = True
        else:
            previous_key_id = str(current["key_id"]) if current is not None else ""
            generation = int(current.get("generation", 0)) + 1 if current is not None else 1
            key_id = _fake_chutes_key_id(request.deployment_id, secret_ref, generation)
            self._fake_chutes_keys[secret_ref] = {
                "key_id": key_id,
                "deployment_id": request.deployment_id,
                "secret_ref": secret_ref,
                "generation": generation,
                "status": "active",
            }
            metadata["generation"] = generation
            if previous_key_id:
                metadata["previous_key_id"] = previous_key_id

        run = {
            "operation_digest": operation_digest,
            "status": status,
            "action": action,
            "key_id": key_id,
            "secret_ref": secret_ref,
            "metadata": metadata,
        }
        self._fake_chutes_runs[key] = run
        return ChutesKeyApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status=status,
            action=action,
            key_id=key_id,
            secret_ref=secret_ref,
            metadata=metadata,
        )

    def _fake_rollback_apply(
        self,
        *,
        request: RollbackApplyRequest,
        plan: Mapping[str, Any],
    ) -> RollbackApplyResult:
        operation = "rollback_apply"
        operation_digest = _operation_digest(operation, request.deployment_id, plan)
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, plan)
        existing = self._fake_rollback_runs.get(key)
        if existing is None:
            existing = {
                "operation_digest": operation_digest,
                "status": "applied",
                "actions": tuple(plan["actions"]),
                "metadata": {
                    "adapter": self.config.adapter_name,
                    "idempotency_key": request.idempotency_key,
                    "stopped_services": tuple(plan["stopped_services"]),
                    "removed_unhealthy_services": tuple(plan["removed_unhealthy_services"]),
                    "protected_state_roots": tuple(plan["protected_state_roots"]),
                    "secret_refs_for_review": tuple(plan["secret_refs_for_review"]),
                    "audit_events": ("rollback_apply_requested", "rollback_apply_completed"),
                    "idempotent_replay": False,
                },
            }
            self._fake_rollback_runs[key] = existing
        else:
            _require_matching_operation_digest(
                existing=existing,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            existing = dict(existing)
            metadata = dict(existing["metadata"])
            metadata["idempotent_replay"] = True
            existing["metadata"] = metadata
        return RollbackApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status=str(existing["status"]),
            actions=tuple(existing["actions"]),
            preserve_state_roots=True,
            metadata=dict(existing["metadata"]),
        )

    def _materialize_compose_secrets(self, compose_secrets: Mapping[str, Any]) -> dict[str, ResolvedSecretFile]:
        if compose_secrets and self.secret_resolver is None:
            raise ArcLinkSecretResolutionError("ArcLink Docker Compose execution requires a secret resolver")
        resolved: dict[str, ResolvedSecretFile] = {}
        for name, spec in compose_secrets.items():
            if not isinstance(spec, Mapping):
                raise ArcLinkSecretResolutionError(f"invalid ArcLink compose secret spec: {name}")
            secret_ref = _require_secret_ref(str(spec.get("secret_ref") or ""))
            target = _require_run_secret_path(str(spec.get("target") or ""))
            resolved[str(name)] = self.secret_resolver.materialize(secret_ref, target)  # type: ignore[union-attr]
        return resolved


def _compose_project_name(deployment_id: str) -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "-", str(deployment_id or "").strip().lower()).strip("-_")
    if not clean:
        raise ArcLinkExecutorError("ArcLink Docker Compose project name requires a deployment id")
    return f"arclink-{clean}"


def _plan_docker_compose_apply(
    *,
    request: DockerComposeApplyRequest,
    intent: Mapping[str, Any],
    services: Mapping[str, Any],
) -> dict[str, Any]:
    roots = intent.get("state_roots") if isinstance(intent.get("state_roots"), Mapping) else {}
    root = str(roots.get("root") or f"/arcdata/deployments/{request.deployment_id}")
    config_root = str(roots.get("config") or f"{root.rstrip('/')}/config")
    project_name = request.project_name or _compose_project_name(request.deployment_id)
    labels = {
        service_name: dict(service.get("labels") or {})
        for service_name, service in services.items()
        if isinstance(service, Mapping) and service.get("labels")
    }
    return {
        "project_name": project_name,
        "env_file": f"{config_root.rstrip('/')}/arclink.env",
        "compose_file": f"{config_root.rstrip('/')}/compose.yaml",
        "services": tuple(services.keys()),
        "volumes": _compose_source_volumes(services),
        "labels": labels,
        "service_start_order": _compose_service_start_order(services),
        "intent_digest": _intent_digest(intent),
    }


def _compose_source_volumes(services: Mapping[str, Any]) -> tuple[str, ...]:
    volumes = {
        str(volume["source"])
        for service in services.values()
        if isinstance(service, Mapping)
        for volume in service.get("volumes", [])
        if isinstance(volume, Mapping) and volume.get("source")
    }
    return tuple(sorted(volumes))


def _compose_service_start_order(services: Mapping[str, Any]) -> tuple[str, ...]:
    visited: set[str] = set()
    visiting: set[str] = set()
    order: list[str] = []

    def visit(service_name: str) -> None:
        if service_name in visited:
            return
        if service_name in visiting:
            raise ArcLinkExecutorError("ArcLink Docker Compose services contain a dependency cycle")
        service = services.get(service_name)
        if not isinstance(service, Mapping):
            raise ArcLinkExecutorError(f"invalid ArcLink Docker Compose service: {service_name}")
        visiting.add(service_name)
        for dependency in _compose_depends_on(service):
            if dependency not in services:
                raise ArcLinkExecutorError(
                    f"ArcLink Docker Compose service {service_name!r} depends on missing service {dependency!r}"
                )
            visit(dependency)
        visiting.remove(service_name)
        visited.add(service_name)
        order.append(service_name)

    for service_name in services:
        visit(str(service_name))
    return tuple(order)


def _compose_depends_on(service: Mapping[str, Any]) -> tuple[str, ...]:
    depends_on = service.get("depends_on") or ()
    if isinstance(depends_on, Mapping):
        return tuple(str(name) for name in depends_on)
    if isinstance(depends_on, (list, tuple)):
        return tuple(str(name) for name in depends_on)
    raise ArcLinkExecutorError("ArcLink Docker Compose depends_on must be a list or object")


def _intent_digest(intent: Mapping[str, Any]) -> str:
    rendered = json.dumps(intent, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]


def _operation_digest(operation: str, deployment_id: str, *parts: Any) -> str:
    rendered = json.dumps([operation, deployment_id, *parts], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:24]


def _stable_execution_key(operation: str, deployment_id: str, *parts: Any) -> str:
    return f"{operation}:{_operation_digest(operation, deployment_id, *parts)}"


def _require_matching_operation_digest(
    *,
    existing: Mapping[str, Any],
    operation: str,
    key: str,
    operation_digest: str,
) -> None:
    existing_digest = str(existing.get("operation_digest") or "")
    if existing_digest != operation_digest:
        raise ArcLinkExecutorError(f"ArcLink {operation} idempotency key {key!r} was reused with different inputs")


def _plan_cloudflare_dns_records(dns: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    allowed_record_types = {"CNAME", "A", "AAAA", "TXT"}
    records: list[dict[str, Any]] = []
    for role, record in sorted(dns.items()):
        if not isinstance(record, Mapping):
            raise ArcLinkExecutorError(f"invalid ArcLink DNS record: {role}")
        hostname = str(record.get("hostname") or "").strip().lower()
        record_type = str(record.get("record_type") or "CNAME").strip().upper()
        target = str(record.get("target") or "").strip()
        if not hostname or not target:
            raise ArcLinkExecutorError(f"ArcLink DNS record requires hostname and target: {role}")
        if record_type not in allowed_record_types:
            allowed = ", ".join(sorted(allowed_record_types))
            raise ArcLinkExecutorError(f"unsupported ArcLink DNS record type {record_type!r}; allowed types: {allowed}")
        records.append(
            {
                "role": str(role),
                "hostname": hostname,
                "record_type": record_type,
                "target": target,
                "proxied": bool(record.get("proxied", True)),
            }
        )
    return tuple(records)


def _dns_record_summary(record: Mapping[str, Any]) -> str:
    proxied = " proxied" if bool(record.get("proxied")) else ""
    return f"{record['record_type']} {record['hostname']} -> {record['target']}{proxied}"


def _plan_cloudflare_access(access: Mapping[str, Any]) -> dict[str, Any]:
    urls = access.get("urls") if isinstance(access.get("urls"), Mapping) else {}
    applications = tuple(sorted(str(url).strip() for url in urls.values() if str(url).strip()))
    ssh = access.get("ssh") if isinstance(access.get("ssh"), Mapping) else {}
    ssh_strategy = str(ssh.get("strategy") or "").strip()
    if ssh and ssh_strategy != "cloudflare_access_tcp":
        raise ArcLinkExecutorError("ArcLink SSH access execution requires Cloudflare Access TCP")
    return {
        "applications": applications,
        "ssh_strategy": ssh_strategy,
        "ssh_hostname": str(ssh.get("hostname") or "").strip().lower() if ssh else "",
    }


def _fake_chutes_key_id(deployment_id: str, secret_ref: str, generation: int) -> str:
    digest = hashlib.sha256(f"{deployment_id}:{secret_ref}:{generation}".encode("utf-8")).hexdigest()[:18]
    return f"chutes_key_{digest}"


def _plan_rollback_apply(plan: Mapping[str, Any]) -> dict[str, Any]:
    requested_actions = tuple(str(action) for action in plan.get("actions", ()))
    if "preserve_state_roots" not in requested_actions:
        raise ArcLinkExecutorError("ArcLink rollback execution must preserve customer state roots")
    destructive = tuple(action for action in requested_actions if _is_destructive_state_delete(action))
    if destructive:
        raise ArcLinkExecutorError("ArcLink rollback execution must not delete customer state roots or vault data")

    services = _rollback_services(plan)
    unhealthy = _rollback_unhealthy_services(plan, services)
    executed: list[str] = list(requested_actions)
    if "stop_rendered_services" in requested_actions:
        executed.extend(f"stop:{service}" for service in services)
    if "remove_unhealthy_containers" in requested_actions:
        executed.extend(f"remove_unhealthy:{service}" for service in unhealthy)

    state_roots = plan.get("state_roots") if isinstance(plan.get("state_roots"), Mapping) else {}
    protected_roots = tuple(
        str(state_roots[name])
        for name in sorted(state_roots)
        if state_roots.get(name) and name in {"root", "state", "vault", "hermes_home", "qmd", "memory", "nextcloud", "code_workspace"}
    )
    secret_refs = plan.get("secret_refs") if isinstance(plan.get("secret_refs"), Mapping) else {}
    return {
        "actions": tuple(executed),
        "stopped_services": services if "stop_rendered_services" in requested_actions else (),
        "removed_unhealthy_services": unhealthy if "remove_unhealthy_containers" in requested_actions else (),
        "protected_state_roots": protected_roots,
        "secret_refs_for_review": tuple(sorted(str(value) for value in secret_refs.values() if str(value).startswith("secret://"))),
    }


def _is_destructive_state_delete(action: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(action or "").strip().lower())
    parts = {part for part in normalized.split("_") if part}
    if "delete" not in parts and "deletion" not in parts:
        return False
    return bool(parts.intersection({"state", "root", "roots", "vault"}))


def _rollback_services(plan: Mapping[str, Any]) -> tuple[str, ...]:
    services = plan.get("services") or plan.get("rendered_services")
    if isinstance(services, Mapping):
        return tuple(str(name) for name in services)
    if isinstance(services, (list, tuple)):
        return tuple(str(name) for name in services)
    compose = plan.get("compose") if isinstance(plan.get("compose"), Mapping) else {}
    compose_services = compose.get("services") if isinstance(compose.get("services"), Mapping) else {}
    return tuple(str(name) for name in compose_services)


def _rollback_unhealthy_services(plan: Mapping[str, Any], services: tuple[str, ...]) -> tuple[str, ...]:
    health = plan.get("service_health") if isinstance(plan.get("service_health"), Mapping) else {}
    unhealthy: list[str] = []
    for service in services:
        item = health.get(service)
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status and status not in {"healthy", "starting"}:
            unhealthy.append(service)
    return tuple(unhealthy)
