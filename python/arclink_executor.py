#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shlex
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from arclink_secrets_regex import redact_then_truncate


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
    source_path: str = ""
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
        _write_private_file_atomic(output, str(value), trailing_newline=False)
        return ResolvedSecretFile(secret_ref=clean_ref, target_path=clean_target, source_path=str(output))


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
class CloudflareDnsTeardownRequest:
    deployment_id: str
    records: tuple[Mapping[str, Any], ...] = ()
    zone_id: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True)
class CloudflareDnsTeardownResult:
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


@dataclass(frozen=True)
class DockerComposeLifecycleRequest:
    deployment_id: str
    action: str  # stop, restart, inspect, teardown
    project_name: str = ""
    env_file: str = ""
    compose_file: str = ""
    idempotency_key: str = ""
    remove_volumes: bool = False


@dataclass(frozen=True)
class DockerComposeLifecycleResult:
    deployment_id: str
    live: bool
    status: str
    action: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class DockerRunner(Protocol):
    """Injectable interface for real Docker command execution."""
    def run(self, args: tuple[str, ...], *, project_name: str, env_file: str, compose_file: str) -> Mapping[str, Any]:
        ...


class ChutesKeyClient(Protocol):
    """Injectable interface for live Chutes key mutations."""

    def create_key(
        self,
        *,
        deployment_id: str,
        label: str,
        secret_ref: str,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        ...

    def rotate_key(
        self,
        *,
        deployment_id: str,
        label: str,
        secret_ref: str,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        ...

    def revoke_key(
        self,
        *,
        deployment_id: str,
        label: str,
        secret_ref: str,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        ...


class StripeActionClient(Protocol):
    """Injectable interface for live Stripe administrative mutations."""

    def refund(
        self,
        *,
        deployment_id: str,
        customer_ref: str,
        idempotency_key: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def cancel(
        self,
        *,
        deployment_id: str,
        customer_ref: str,
        idempotency_key: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...

    def portal(
        self,
        *,
        deployment_id: str,
        customer_ref: str,
        idempotency_key: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...


@dataclass
class FakeDockerRunner:
    """Records commands instead of executing them."""
    runs: list[dict[str, Any]] = field(default_factory=list)

    def run(self, args: tuple[str, ...], *, project_name: str, env_file: str, compose_file: str) -> Mapping[str, Any]:
        record = {
            "args": args,
            "project_name": project_name,
            "env_file": env_file,
            "compose_file": compose_file,
        }
        self.runs.append(record)
        return {"status": "ok", "args": args}


@dataclass(frozen=True)
class SubprocessDockerComposeRunner:
    """Run docker compose on the local worker after files are materialized."""

    docker_binary: str = "docker"

    def run(self, args: tuple[str, ...], *, project_name: str, env_file: str, compose_file: str) -> Mapping[str, Any]:
        cmd = (
            self.docker_binary,
            "compose",
            "--project-name",
            project_name,
            "--env-file",
            env_file,
            "-f",
            compose_file,
            *args,
        )
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
        if proc.returncode != 0:
            raise ArcLinkExecutorError(_safe_command_error("docker compose", proc.stderr or proc.stdout))
        return {"status": "ok", "returncode": proc.returncode, "stdout": _runner_stdout(args, proc.stdout)}


@dataclass(frozen=True)
class SshDockerComposeRunner:
    """Copy the rendered deployment root to a worker host and run docker compose there."""

    host: str
    user: str = "root"
    ssh_binary: str = "ssh"
    rsync_binary: str = "rsync"
    docker_binary: str = "docker"
    ssh_options: tuple[str, ...] = ("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")
    allowed_hosts: tuple[str, ...] = ()

    def _target(self) -> str:
        clean_host = str(self.host or "").strip()
        if not clean_host:
            raise ArcLinkExecutorError("ArcLink SSH Docker runner requires a worker host")
        _require_allowed_ssh_host(clean_host, self.allowed_hosts)
        clean_user = str(self.user or "root").strip() or "root"
        return f"{clean_user}@{clean_host}"

    def run(self, args: tuple[str, ...], *, project_name: str, env_file: str, compose_file: str) -> Mapping[str, Any]:
        target = self._target()
        root = str(Path(compose_file).resolve().parents[1])
        cleanup_required = bool(args and args[0] in {"up", "down"})
        secrets_root = str((Path(compose_file).parent / "secrets").resolve())
        mkdir = subprocess.run(
            (self.ssh_binary, *self.ssh_options, target, "mkdir", "-p", root),
            check=False,
            text=True,
            capture_output=True,
        )
        if mkdir.returncode != 0:
            raise ArcLinkExecutorError(_safe_command_error("ssh mkdir", mkdir.stderr or mkdir.stdout))
        sync = subprocess.run(
            (self.rsync_binary, "-a", "--delete", f"{root}/", f"{target}:{root}/"),
            check=False,
            text=True,
            capture_output=True,
        )
        if sync.returncode != 0:
            cleanup_error = (
                self._cleanup_remote_secrets(target=target, secrets_root=secrets_root)
                if cleanup_required
                else ""
            )
            message = _safe_command_error("rsync deployment root", sync.stderr or sync.stdout)
            if cleanup_error:
                message = f"{message}; {cleanup_error}"
            raise ArcLinkExecutorError(message)
        remote_cmd = " ".join(
            _shell_quote(part)
            for part in (
                self.docker_binary,
                "compose",
                "--project-name",
                project_name,
                "--env-file",
                env_file,
                "-f",
                compose_file,
                *args,
            )
        )
        run = subprocess.run(
            (self.ssh_binary, *self.ssh_options, target, remote_cmd),
            check=False,
            text=True,
            capture_output=True,
        )
        cleanup_error = self._cleanup_remote_secrets(target=target, secrets_root=secrets_root) if cleanup_required else ""
        if run.returncode != 0:
            message = _safe_command_error("ssh docker compose", run.stderr or run.stdout)
            if cleanup_error:
                message = f"{message}; {cleanup_error}"
            raise ArcLinkExecutorError(message)
        if cleanup_error:
            raise ArcLinkExecutorError(cleanup_error)
        return {"status": "ok", "returncode": run.returncode, "stdout": _runner_stdout(args, run.stdout), "worker_host": self.host}

    def _cleanup_remote_secrets(self, *, target: str, secrets_root: str) -> str:
        cleanup = subprocess.run(
            (self.ssh_binary, *self.ssh_options, target, f"rm -rf -- {_shell_quote(secrets_root)}"),
            check=False,
            text=True,
            capture_output=True,
        )
        if cleanup.returncode != 0:
            return _safe_command_error("ssh cleanup compose secrets", cleanup.stderr or cleanup.stdout)
        return ""


def _runner_stdout(args: tuple[str, ...], stdout: str) -> str:
    if "ps" in args and "json" in args:
        return stdout
    return stdout[-2000:]


@dataclass(frozen=True)
class DryRunStep:
    """A secret-free description of a planned Docker operation."""
    operation: str
    project_name: str
    services: tuple[str, ...]
    compose_file: str
    env_file: str


class ArcLinkExecutor:
    def __init__(
        self,
        *,
        config: ArcLinkExecutorConfig | None = None,
        secret_resolver: SecretResolver | None = None,
        docker_runner: DockerRunner | None = None,
        chutes_client: ChutesKeyClient | None = None,
        stripe_client: StripeActionClient | None = None,
        operation_conn: sqlite3.Connection | None = None,
    ) -> None:
        self.config = config or ArcLinkExecutorConfig()
        self.secret_resolver = secret_resolver
        self.docker_runner = docker_runner
        self.chutes_client = chutes_client
        self.stripe_client = stripe_client
        self.operation_conn = operation_conn
        self._fake_docker_runs: dict[str, dict[str, Any]] = {}
        self._fake_dns_runs: dict[str, dict[str, Any]] = {}
        self._fake_dns_teardown_runs: dict[str, dict[str, Any]] = {}
        self._fake_access_runs: dict[str, dict[str, Any]] = {}
        self._fake_chutes_runs: dict[str, dict[str, Any]] = {}
        self._fake_chutes_keys: dict[str, dict[str, Any]] = {}
        self._fake_stripe_runs: dict[str, dict[str, Any]] = {}
        self._live_chutes_runs: dict[str, dict[str, Any]] = {}
        self._live_stripe_runs: dict[str, dict[str, Any]] = {}
        self._fake_rollback_runs: dict[str, dict[str, Any]] = {}
        self._fake_lifecycle_runs: dict[str, dict[str, Any]] = {}

    def _require_live_enabled(self, operation: str) -> None:
        if not self.config.live_enabled:
            raise ArcLinkLiveExecutionRequired(f"{operation} requires ARCLINK live/E2E execution to be explicitly enabled")

    def docker_compose_dry_run(self, request: DockerComposeApplyRequest) -> DryRunStep:
        """Plan a Docker Compose apply without executing or revealing secrets."""
        intent = dict(request.intent)
        compose = dict(intent.get("compose") or {})
        services = dict(compose.get("services") or {})
        plan = _plan_docker_compose_apply(request=request, intent=intent, services=services)
        return DryRunStep(
            operation="docker_compose_apply",
            project_name=str(plan["project_name"]),
            services=tuple(plan["services"]),
            compose_file=str(plan["compose_file"]),
            env_file=str(plan["env_file"]),
        )

    def docker_compose_apply(self, request: DockerComposeApplyRequest) -> DockerComposeApplyResult:
        self._require_live_enabled("docker_compose_apply")
        intent = dict(request.intent)
        compose = dict(intent.get("compose") or {})
        services = dict(compose.get("services") or {})
        compose_secrets = dict(compose.get("secrets") or {})
        plan = _plan_docker_compose_apply(request=request, intent=intent, services=services)
        if self.config.adapter_name == "fake":
            return self._fake_docker_compose_apply(request=request, plan=plan, compose_secrets=compose_secrets)
        if self.docker_runner is None:
            raise ArcLinkExecutorError("ArcLink live Docker execution requires an injectable DockerRunner")
        resolved = self._materialize_compose_secrets(compose_secrets)
        try:
            if not isinstance(self.docker_runner, FakeDockerRunner):
                _materialize_docker_compose_files(intent=intent, plan=plan, resolved_secrets=resolved)
            self.docker_runner.run(
                ("up", "-d", "--remove-orphans"),
                project_name=str(plan["project_name"]),
                env_file=str(plan["env_file"]),
                compose_file=str(plan["compose_file"]),
            )
        except Exception:
            _cleanup_materialized_secret_files(resolved.values())
            raise
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

    def docker_compose_lifecycle(self, request: DockerComposeLifecycleRequest) -> DockerComposeLifecycleResult:
        self._require_live_enabled("docker_compose_lifecycle")
        action = str(request.action or "").strip().lower()
        if action not in {"stop", "restart", "inspect", "teardown"}:
            raise ArcLinkExecutorError(f"unsupported Docker Compose lifecycle action: {action}")
        if self.config.adapter_name == "fake":
            key = request.idempotency_key or f"{request.deployment_id}:{action}"
            operation_digest = _operation_digest(
                "docker_compose_lifecycle",
                request.deployment_id,
                {"action": action, "project_name": request.project_name, "remove_volumes": request.remove_volumes},
            )
            existing = self._fake_lifecycle_runs.get(key)
            if existing is not None:
                _require_matching_operation_digest(
                    existing=existing,
                    operation="docker_compose_lifecycle",
                    key=key,
                    operation_digest=operation_digest,
                )
                idempotent_replay = True
            else:
                self._fake_lifecycle_runs[key] = {
                    "operation_digest": operation_digest,
                    "deployment_id": request.deployment_id,
                    "action": action,
                    "status": "completed",
                }
                idempotent_replay = False
            self._fake_lifecycle_runs[key].update({
                "deployment_id": request.deployment_id,
                "action": action,
                "status": "completed",
            })
            return DockerComposeLifecycleResult(
                deployment_id=request.deployment_id,
                live=False,
                status="completed",
                action=action,
                metadata={
                    "adapter": "fake",
                    "idempotency_key": key,
                    "preserve_volumes": not request.remove_volumes,
                    "idempotent_replay": idempotent_replay,
                },
            )
        if self.docker_runner is None:
            raise ArcLinkExecutorError("ArcLink live Docker lifecycle requires an injectable DockerRunner")
        project_name = request.project_name or _compose_project_name(request.deployment_id)
        config_root = Path(f"/arcdata/deployments/{request.deployment_id}/config")
        env_file = request.env_file or str(config_root / "arclink.env")
        compose_file = request.compose_file or str(config_root / "compose.yaml")
        compose_args = {
            "stop": ("stop",),
            "restart": ("restart",),
            "inspect": ("ps", "--format", "json"),
            "teardown": ("down", "--remove-orphans", *(("--volumes",) if request.remove_volumes else ())),
        }[action]
        runner_result = self.docker_runner.run(
            compose_args,
            project_name=project_name,
            env_file=env_file,
            compose_file=compose_file,
        )
        if action == "teardown":
            _cleanup_materialized_secret_root(Path(compose_file).parent / "secrets")
        return DockerComposeLifecycleResult(
            deployment_id=request.deployment_id,
            live=True,
            status="completed",
            action=action,
            metadata={
                "adapter": self.config.adapter_name,
                "idempotency_key": request.idempotency_key,
                "project_name": project_name,
                "runner_status": str(runner_result.get("status") or ""),
                "preserve_volumes": not request.remove_volumes,
            },
        )

    def cloudflare_dns_teardown(self, request: CloudflareDnsTeardownRequest) -> CloudflareDnsTeardownResult:
        self._require_live_enabled("cloudflare_dns_teardown")
        records = tuple(_clean_cloudflare_teardown_record(record) for record in request.records)
        if self.config.adapter_name == "fake":
            return self._fake_cloudflare_dns_teardown(request=request, records=records)
        provider_records = _cloudflare_delete_dns_records(records=records, zone_id=request.zone_id)
        return CloudflareDnsTeardownResult(
            deployment_id=request.deployment_id,
            live=True,
            status="applied",
            records=tuple(record["hostname"] for record in records),
            metadata={
                "adapter": self.config.adapter_name,
                "zone_id": request.zone_id,
                "idempotency_key": request.idempotency_key,
                "provider_record_ids": tuple(provider_records),
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
            live=False,
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
        provider_records = _cloudflare_upsert_dns_records(records=records, zone_id=request.zone_id)
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
                "provider_record_ids": tuple(provider_records),
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
        if self.chutes_client is None:
            raise ArcLinkExecutorError("ArcLink live Chutes key execution requires an injectable ChutesKeyClient")
        operation = "chutes_key_apply"
        operation_inputs = {"action": action, "label": request.label, "secret_ref": secret_ref}
        operation_digest = _operation_digest(operation, request.deployment_id, operation_inputs)
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, operation_inputs)
        durable_replay = _replay_operation_idempotency(
            self.operation_conn,
            operation_kind=operation,
            idempotency_key=key,
            intent={"deployment_id": request.deployment_id, **operation_inputs},
        )
        if durable_replay is not None:
            return _chutes_result_from_idempotency_row(request=request, row=durable_replay)
        existing_run = self._live_chutes_runs.get(key)
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
        _reserve_operation_idempotency(
            self.operation_conn,
            operation_kind=operation,
            idempotency_key=key,
            intent={"deployment_id": request.deployment_id, **operation_inputs},
        )
        try:
            provider_result = _call_chutes_key_client(
                self.chutes_client,
                action=action,
                deployment_id=request.deployment_id,
                label=request.label,
                secret_ref=secret_ref,
                idempotency_key=key,
            )
            key_id = _provider_ref(provider_result, "key_id", "api_key_id", "id")
            if not key_id:
                raise ArcLinkExecutorError("ArcLink live Chutes key response did not include a provider key id")
        except Exception as exc:
            _fail_operation_idempotency(
                self.operation_conn,
                operation_kind=operation,
                idempotency_key=key,
                intent={"deployment_id": request.deployment_id, **operation_inputs},
                error=str(exc),
                result={
                    "deployment_id": request.deployment_id,
                    "status": "failed",
                    "action": action,
                    "key_id": "",
                    "secret_ref": secret_ref,
                    "metadata": {"adapter": self.config.adapter_name, "idempotency_key": key},
                },
            )
            raise
        status = str(provider_result.get("status") or "applied")
        metadata = {
            "adapter": self.config.adapter_name,
            "label": request.label,
            "idempotency_key": key,
            "provider_refs": {"chutes_key_id": key_id},
            "idempotent_replay": False,
        }
        run = {
            "operation_digest": operation_digest,
            "status": status,
            "action": action,
            "key_id": key_id,
            "secret_ref": secret_ref,
            "metadata": metadata,
        }
        self._live_chutes_runs[key] = run
        _complete_operation_idempotency(
            self.operation_conn,
            operation_kind=operation,
            idempotency_key=key,
            intent={"deployment_id": request.deployment_id, **operation_inputs},
            provider_refs={"chutes_key_id": key_id},
            result={
                "deployment_id": request.deployment_id,
                "status": status,
                "action": action,
                "key_id": key_id,
                "secret_ref": secret_ref,
                "metadata": metadata,
            },
        )
        return ChutesKeyApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status=status,
            action=action,
            key_id=key_id,
            secret_ref=secret_ref,
            metadata=metadata,
        )

    def stripe_action_apply(self, request: StripeActionApplyRequest) -> StripeActionApplyResult:
        self._require_live_enabled("stripe_action_apply")
        action = str(request.action or "").strip()
        if action not in {"refund", "cancel", "portal"}:
            raise ArcLinkExecutorError("unsupported ArcLink Stripe action")
        operation = "stripe_action_apply"
        metadata = dict(request.metadata)
        if request.customer_ref:
            metadata["customer_ref"] = _require_secret_ref(request.customer_ref)
        if self.config.adapter_name == "fake":
            return self._fake_stripe_action_apply(
                request=request,
                action=action,
                metadata=metadata,
            )
        if self.stripe_client is None:
            raise ArcLinkExecutorError("ArcLink live Stripe action execution requires an injectable StripeActionClient")
        operation_inputs = {"action": action, "customer_ref": metadata.get("customer_ref", ""), "metadata": metadata}
        operation_digest = _operation_digest(operation, request.deployment_id, operation_inputs)
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, operation_inputs)
        durable_replay = _replay_operation_idempotency(
            self.operation_conn,
            operation_kind=operation,
            idempotency_key=key,
            intent={"deployment_id": request.deployment_id, **operation_inputs},
        )
        if durable_replay is not None:
            return _stripe_result_from_idempotency_row(request=request, row=durable_replay)
        existing_run = self._live_stripe_runs.get(key)
        if existing_run is not None:
            _require_matching_operation_digest(
                existing=existing_run,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            return StripeActionApplyResult(
                deployment_id=request.deployment_id,
                live=True,
                status=str(existing_run["status"]),
                action=str(existing_run["action"]),
                metadata=dict(existing_run["metadata"], idempotent_replay=True),
            )
        _reserve_operation_idempotency(
            self.operation_conn,
            operation_kind=operation,
            idempotency_key=key,
            intent={"deployment_id": request.deployment_id, **operation_inputs},
        )
        try:
            provider_result = _call_stripe_action_client(
                self.stripe_client,
                action=action,
                deployment_id=request.deployment_id,
                customer_ref=str(metadata.get("customer_ref") or ""),
                idempotency_key=key,
                metadata=metadata,
            )
            provider_id = _provider_ref(provider_result, "refund_id", "cancellation_id", "session_id", "subscription_id", "id")
            if not provider_id:
                raise ArcLinkExecutorError("ArcLink live Stripe response did not include a provider reference id")
        except Exception as exc:
            _fail_operation_idempotency(
                self.operation_conn,
                operation_kind=operation,
                idempotency_key=key,
                intent={"deployment_id": request.deployment_id, **operation_inputs},
                error=str(exc),
                result={
                    "deployment_id": request.deployment_id,
                    "status": "failed",
                    "action": action,
                    "metadata": {"adapter": self.config.adapter_name, "idempotency_key": key},
                },
            )
            raise
        status = str(provider_result.get("status") or "applied")
        result_metadata = dict(metadata)
        result_metadata.update(
            {
                "adapter": self.config.adapter_name,
                "idempotency_key": key,
                "provider_refs": {"stripe_action_id": provider_id},
                "idempotent_replay": False,
            }
        )
        run = {
            "operation_digest": operation_digest,
            "status": status,
            "action": action,
            "metadata": result_metadata,
        }
        self._live_stripe_runs[key] = run
        _complete_operation_idempotency(
            self.operation_conn,
            operation_kind=operation,
            idempotency_key=key,
            intent={"deployment_id": request.deployment_id, **operation_inputs},
            provider_refs={"stripe_action_id": provider_id},
            result={
                "deployment_id": request.deployment_id,
                "status": status,
                "action": action,
                "metadata": result_metadata,
            },
        )
        return StripeActionApplyResult(
            deployment_id=request.deployment_id,
            live=True,
            status=status,
            action=action,
            metadata=result_metadata,
        )

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
            live=False,
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

    def _fake_cloudflare_dns_teardown(
        self,
        *,
        request: CloudflareDnsTeardownRequest,
        records: tuple[dict[str, Any], ...],
    ) -> CloudflareDnsTeardownResult:
        operation = "cloudflare_dns_teardown"
        operation_digest = _operation_digest(operation, request.deployment_id, {"records": records, "zone_id": request.zone_id})
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, {"records": records, "zone_id": request.zone_id})
        existing = self._fake_dns_teardown_runs.get(key)
        if existing is None:
            existing = {
                "operation_digest": operation_digest,
                "status": "applied",
                "records": tuple(record["hostname"] for record in records),
                "idempotent_replay": False,
            }
            self._fake_dns_teardown_runs[key] = existing
        else:
            _require_matching_operation_digest(
                existing=existing,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            existing = dict(existing)
            existing["idempotent_replay"] = True
        return CloudflareDnsTeardownResult(
            deployment_id=request.deployment_id,
            live=False,
            status=str(existing["status"]),
            records=tuple(existing["records"]),
            metadata={
                "adapter": self.config.adapter_name,
                "zone_id": request.zone_id,
                "idempotency_key": request.idempotency_key,
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
            live=False,
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
                live=False,
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
            live=False,
            status=status,
            action=action,
            key_id=key_id,
            secret_ref=secret_ref,
            metadata=metadata,
        )

    def _fake_stripe_action_apply(
        self,
        *,
        request: StripeActionApplyRequest,
        action: str,
        metadata: Mapping[str, Any],
    ) -> StripeActionApplyResult:
        operation = "stripe_action_apply"
        operation_inputs = {"action": action, "customer_ref": metadata.get("customer_ref", ""), "metadata": metadata}
        operation_digest = _operation_digest(operation, request.deployment_id, operation_inputs)
        key = request.idempotency_key or _stable_execution_key(operation, request.deployment_id, operation_inputs)
        existing = self._fake_stripe_runs.get(key)
        if existing is not None:
            _require_matching_operation_digest(
                existing=existing,
                operation=operation,
                key=key,
                operation_digest=operation_digest,
            )
            return StripeActionApplyResult(
                deployment_id=request.deployment_id,
                live=False,
                status=str(existing["status"]),
                action=str(existing["action"]),
                metadata=dict(existing["metadata"], idempotent_replay=True),
            )
        provider_id = _fake_stripe_action_id(request.deployment_id, action, key)
        result_metadata = dict(metadata)
        result_metadata.update(
            {
                "adapter": self.config.adapter_name,
                "idempotency_key": request.idempotency_key,
                "provider_refs": {"stripe_action_id": provider_id},
                "idempotent_replay": False,
            }
        )
        run = {
            "operation_digest": operation_digest,
            "status": "applied",
            "action": action,
            "metadata": result_metadata,
        }
        self._fake_stripe_runs[key] = run
        return StripeActionApplyResult(
            deployment_id=request.deployment_id,
            live=False,
            status="applied",
            action=action,
            metadata=result_metadata,
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
            live=False,
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


def _write_private_file_atomic(path: Path, value: str, *, trailing_newline: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    lock_path = path.with_name(f".{path.name}.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    tmp_name = ""
    try:
        with os.fdopen(lock_fd, "w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False) as tmp:
                tmp_name = tmp.name
                tmp.write(value)
                if trailing_newline:
                    tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        if tmp_name:
            try:
                Path(tmp_name).unlink()
            except OSError:
                pass
        raise


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


def _materialize_docker_compose_files(
    *,
    intent: Mapping[str, Any],
    plan: Mapping[str, Any],
    resolved_secrets: Mapping[str, ResolvedSecretFile],
) -> None:
    compose_file = Path(str(plan["compose_file"]))
    env_file = Path(str(plan["env_file"]))
    root = compose_file.parents[1]
    config_root = compose_file.parent
    secrets_root = config_root / "secrets"
    root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)
    secrets_root.mkdir(parents=True, exist_ok=True)
    secrets_root.chmod(0o700)
    for resolved in resolved_secrets.values():
        if resolved.source_path:
            Path(resolved.source_path).chmod(0o600)

    services = dict((intent.get("compose") or {}).get("services") or {}) if isinstance(intent.get("compose"), Mapping) else {}
    _ensure_volume_roots(services)
    env = {
        str(k): str(v)
        for k, v in (intent.get("environment") or {}).items()
        if str(k).strip()
    } if isinstance(intent.get("environment"), Mapping) else {}
    env_file.write_text("".join(f"{key}={_env_quote(value)}\n" for key, value in sorted(env.items())), encoding="utf-8")
    env_file.chmod(0o600)

    compose_services = {
        str(name): _compose_service_for_file(dict(service))
        for name, service in services.items()
        if isinstance(service, Mapping)
    }
    compose_secrets = {
        name: {"file": _compose_secret_file_path(name=name, resolved=resolved)}
        for name, resolved in resolved_secrets.items()
    }
    compose_doc: dict[str, Any] = {"services": compose_services}
    compose_networks = dict((intent.get("compose") or {}).get("networks") or {}) if isinstance(intent.get("compose"), Mapping) else {}
    if compose_networks:
        compose_doc["networks"] = compose_networks
    if compose_secrets:
        compose_doc["secrets"] = compose_secrets
    compose_file.write_text(json.dumps(compose_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compose_file.chmod(0o600)


def _compose_service_for_file(service: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("image", "entrypoint", "command", "environment", "labels", "depends_on", "deploy", "healthcheck", "networks"):
        value = service.get(key)
        if value not in (None, {}, []):
            out[key] = value
    volumes = []
    for volume in service.get("volumes", []) or []:
        if isinstance(volume, Mapping):
            source = str(volume.get("source") or "").strip()
            target = str(volume.get("target") or "").strip()
            if source and target:
                item: dict[str, Any] = {"type": "bind", "source": source, "target": target}
                if volume.get("read_only") is True:
                    item["read_only"] = True
                volumes.append(item)
        elif str(volume).strip():
            volumes.append(str(volume))
    if volumes:
        out["volumes"] = volumes
    secrets = []
    for secret in service.get("secrets", []) or []:
        if isinstance(secret, Mapping) and secret.get("source"):
            item = {"source": str(secret["source"])}
            if secret.get("target"):
                item["target"] = str(secret["target"])
            secrets.append(item)
        elif str(secret).strip():
            secrets.append(str(secret))
    if secrets:
        out["secrets"] = secrets
    return out


def _compose_secret_file_path(*, name: str, resolved: ResolvedSecretFile) -> str:
    if resolved.source_path:
        return resolved.source_path
    raise ArcLinkSecretResolutionError(f"ArcLink live compose secret {name!r} was not materialized to a source file")


def _cleanup_materialized_secret_files(resolved: Any) -> None:
    touched_roots: set[Path] = set()
    for item in resolved:
        source_path = str(getattr(item, "source_path", "") or "").strip()
        if not source_path:
            continue
        path = Path(source_path)
        touched_roots.add(path.parent)
        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
        except OSError as exc:
            raise ArcLinkSecretResolutionError(f"failed to clean materialized ArcLink secret copy: {path}") from exc
    for root in touched_roots:
        _cleanup_materialized_secret_root(root)


def _cleanup_materialized_secret_root(root: Path) -> None:
    try:
        clean_root = root.resolve()
    except OSError:
        clean_root = root
    if not str(clean_root).strip() or str(clean_root) in {"/", "/run/secrets"}:
        raise ArcLinkSecretResolutionError(f"refusing unsafe ArcLink secret cleanup path: {clean_root}")
    if not clean_root.exists():
        return
    for child in clean_root.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                continue
            child.unlink()
        except OSError as exc:
            raise ArcLinkSecretResolutionError(f"failed to clean materialized ArcLink secret copy: {child}") from exc
    try:
        clean_root.rmdir()
    except OSError:
        pass


def _require_allowed_ssh_host(host: str, allowed_hosts: tuple[str, ...]) -> None:
    clean_host = str(host or "").strip().lower()
    allowed = {str(item or "").strip().lower() for item in allowed_hosts if str(item or "").strip()}
    if not allowed:
        raise ArcLinkExecutorError("ArcLink SSH Docker runner requires an explicit host allowlist")
    if clean_host not in allowed:
        raise ArcLinkExecutorError("ArcLink SSH Docker runner host is not in the explicit allowlist")


def _ensure_volume_roots(services: Mapping[str, Any]) -> None:
    for source in _compose_source_volumes(services):
        if source.startswith("/"):
            Path(source).mkdir(parents=True, exist_ok=True)


def _env_quote(value: str) -> str:
    text = str(value)
    if not text:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", text):
        return text
    return shlex.quote(text)


def _shell_quote(value: str) -> str:
    return shlex.quote(str(value))


def _safe_command_error(operation: str, output: str) -> str:
    redacted = redact_then_truncate(output, limit=2000, tail=True)
    return f"{operation} failed: {redacted}"


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


def _clean_cloudflare_teardown_record(record: Mapping[str, Any]) -> dict[str, Any]:
    hostname = str(record.get("hostname") or "").strip().lower()
    record_type = str(record.get("record_type") or "CNAME").strip().upper()
    if not hostname:
        raise ArcLinkExecutorError("ArcLink DNS teardown record requires a hostname")
    return {
        "hostname": hostname,
        "record_type": record_type,
        "provider_record_id": str(record.get("provider_record_id") or "").strip(),
    }


def _dns_record_summary(record: Mapping[str, Any]) -> str:
    proxied = " proxied" if bool(record.get("proxied")) else ""
    return f"{record['record_type']} {record['hostname']} -> {record['target']}{proxied}"


def _cloudflare_upsert_dns_records(*, records: tuple[dict[str, Any], ...], zone_id: str) -> tuple[str, ...]:
    clean_zone = str(zone_id or os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
    token = str(os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    if not clean_zone:
        raise ArcLinkExecutorError("ArcLink Cloudflare DNS apply requires CLOUDFLARE_ZONE_ID")
    if not token:
        raise ArcLinkExecutorError("ArcLink Cloudflare DNS apply requires CLOUDFLARE_API_TOKEN")
    provider_ids: list[str] = []
    for record in records:
        existing = _cloudflare_find_dns_record(zone_id=clean_zone, token=token, record=record)
        body = {
            "type": str(record["record_type"]).upper(),
            "name": str(record["hostname"]).lower(),
            "content": str(record["target"]),
            "proxied": bool(record.get("proxied", True)),
            "ttl": 1,
        }
        if existing:
            result = _cloudflare_request(
                "PUT",
                f"/zones/{clean_zone}/dns_records/{existing['id']}",
                token=token,
                body=body,
            )
        else:
            result = _cloudflare_request("POST", f"/zones/{clean_zone}/dns_records", token=token, body=body)
        result_id = str((result.get("result") or {}).get("id") or "")
        provider_ids.append(result_id or str(existing.get("id") or ""))
    return tuple(provider_ids)


def _cloudflare_delete_dns_records(*, records: tuple[dict[str, Any], ...], zone_id: str) -> tuple[str, ...]:
    clean_zone = str(zone_id or os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
    token = str(os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    if not clean_zone:
        raise ArcLinkExecutorError("ArcLink Cloudflare DNS teardown requires CLOUDFLARE_ZONE_ID")
    if not token:
        raise ArcLinkExecutorError("ArcLink Cloudflare DNS teardown requires CLOUDFLARE_API_TOKEN")
    removed: list[str] = []
    for record in records:
        provider_id = str(record.get("provider_record_id") or "").strip()
        if not provider_id:
            found = _cloudflare_find_dns_record(zone_id=clean_zone, token=token, record=record)
            provider_id = str(found.get("id") or "")
        if not provider_id:
            continue
        _cloudflare_request("DELETE", f"/zones/{clean_zone}/dns_records/{provider_id}", token=token)
        removed.append(provider_id)
    return tuple(removed)


def _cloudflare_find_dns_record(*, zone_id: str, token: str, record: Mapping[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "type": str(record["record_type"]).upper(),
        "name": str(record["hostname"]).lower(),
        "per_page": "1",
    })
    payload = _cloudflare_request("GET", f"/zones/{zone_id}/dns_records?{query}", token=token)
    results = payload.get("result") or []
    return dict(results[0]) if isinstance(results, list) and results else {}


def _cloudflare_request(method: str, path: str, *, token: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.cloudflare.com/client/v4{path}"
    data = None if body is None else json.dumps(dict(body)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = redact_then_truncate(exc.read().decode("utf-8", errors="replace"), limit=1000, tail=True)
        raise ArcLinkExecutorError(f"Cloudflare API request failed with HTTP {exc.code}: {detail}") from exc
    if not isinstance(payload, dict) or not payload.get("success"):
        detail = redact_then_truncate(json.dumps(payload, sort_keys=True), limit=1000, tail=True)
        raise ArcLinkExecutorError(f"Cloudflare API request failed: {detail}")
    return payload


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


def _fake_stripe_action_id(deployment_id: str, action: str, key: str) -> str:
    digest = hashlib.sha256(f"{deployment_id}:{action}:{key}".encode("utf-8")).hexdigest()[:18]
    return f"stripe_{action}_{digest}"


def _provider_ref(result: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(result.get(key) or "").strip()
        if value:
            return value
    return ""


def _operation_result_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = str(row.get("result_json") or "{}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArcLinkExecutorError("ArcLink operation idempotency row contains invalid result JSON") from exc
    if not isinstance(parsed, Mapping):
        raise ArcLinkExecutorError("ArcLink operation idempotency row result must be an object")
    return dict(parsed)


def _replay_operation_idempotency(
    conn: sqlite3.Connection | None,
    *,
    operation_kind: str,
    idempotency_key: str,
    intent: Mapping[str, Any],
) -> dict[str, Any] | None:
    if conn is None:
        return None
    from arclink_control import replay_arclink_operation_idempotency

    try:
        return replay_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=idempotency_key,
            intent=dict(intent),
        )
    except ValueError as exc:
        raise ArcLinkExecutorError(str(exc)) from exc


def _reserve_operation_idempotency(
    conn: sqlite3.Connection | None,
    *,
    operation_kind: str,
    idempotency_key: str,
    intent: Mapping[str, Any],
) -> None:
    if conn is None:
        return
    from arclink_control import reserve_arclink_operation_idempotency

    try:
        reserve_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=idempotency_key,
            intent=dict(intent),
            status="running",
        )
    except ValueError as exc:
        raise ArcLinkExecutorError(str(exc)) from exc


def _complete_operation_idempotency(
    conn: sqlite3.Connection | None,
    *,
    operation_kind: str,
    idempotency_key: str,
    intent: Mapping[str, Any],
    provider_refs: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    if conn is None:
        return
    from arclink_control import complete_arclink_operation_idempotency

    try:
        complete_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=idempotency_key,
            intent=dict(intent),
            provider_refs=dict(provider_refs),
            result=dict(result),
        )
    except (KeyError, ValueError) as exc:
        raise ArcLinkExecutorError(str(exc)) from exc


def _fail_operation_idempotency(
    conn: sqlite3.Connection | None,
    *,
    operation_kind: str,
    idempotency_key: str,
    intent: Mapping[str, Any],
    error: str,
    result: Mapping[str, Any],
) -> None:
    if conn is None:
        return
    from arclink_control import fail_arclink_operation_idempotency

    try:
        fail_arclink_operation_idempotency(
            conn,
            operation_kind=operation_kind,
            idempotency_key=idempotency_key,
            intent=dict(intent),
            error=redact_then_truncate(error, limit=1000),
            result=dict(result),
        )
    except (KeyError, ValueError) as exc:
        raise ArcLinkExecutorError(str(exc)) from exc


def _chutes_result_from_idempotency_row(
    *,
    request: ChutesKeyApplyRequest,
    row: Mapping[str, Any],
) -> ChutesKeyApplyResult:
    payload = _operation_result_payload(row)
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {}
    metadata["idempotent_replay"] = True
    return ChutesKeyApplyResult(
        deployment_id=str(payload.get("deployment_id") or request.deployment_id),
        live=True,
        status=str(payload.get("status") or row.get("status") or "succeeded"),
        action=str(payload.get("action") or request.action),
        key_id=str(payload.get("key_id") or ""),
        secret_ref=str(payload.get("secret_ref") or request.secret_ref),
        metadata=metadata,
    )


def _stripe_result_from_idempotency_row(
    *,
    request: StripeActionApplyRequest,
    row: Mapping[str, Any],
) -> StripeActionApplyResult:
    payload = _operation_result_payload(row)
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata"), Mapping) else {}
    metadata["idempotent_replay"] = True
    return StripeActionApplyResult(
        deployment_id=str(payload.get("deployment_id") or request.deployment_id),
        live=True,
        status=str(payload.get("status") or row.get("status") or "succeeded"),
        action=str(payload.get("action") or request.action),
        metadata=metadata,
    )


def _call_chutes_key_client(
    client: ChutesKeyClient,
    *,
    action: str,
    deployment_id: str,
    label: str,
    secret_ref: str,
    idempotency_key: str,
) -> Mapping[str, Any]:
    method_name = {
        "create": "create_key",
        "rotate": "rotate_key",
        "revoke": "revoke_key",
    }[action]
    method = getattr(client, method_name, None)
    if method is None:
        raise ArcLinkExecutorError(f"ArcLink live Chutes client does not implement {method_name}")
    result = method(
        deployment_id=deployment_id,
        label=label,
        secret_ref=secret_ref,
        idempotency_key=idempotency_key,
    )
    if not isinstance(result, Mapping):
        raise ArcLinkExecutorError("ArcLink live Chutes client returned a non-object result")
    return result


def _call_stripe_action_client(
    client: StripeActionClient,
    *,
    action: str,
    deployment_id: str,
    customer_ref: str,
    idempotency_key: str,
    metadata: Mapping[str, Any],
) -> Mapping[str, Any]:
    method = getattr(client, action, None)
    if method is None:
        raise ArcLinkExecutorError(f"ArcLink live Stripe client does not implement {action}")
    result = method(
        deployment_id=deployment_id,
        customer_ref=customer_ref,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )
    if not isinstance(result, Mapping):
        raise ArcLinkExecutorError("ArcLink live Stripe client returned a non-object result")
    return result


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
        if state_roots.get(name)
        and name in {"root", "state", "vault", "linked_resources", "hermes_home", "qmd", "memory", "nextcloud", "code_workspace"}
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
