#!/usr/bin/env python3
"""Fail-closed Linode inventory adapter."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from arclink_http import HttpResponse, http_request, parse_json_object
from arclink_inventory import parse_probe_output
from arclink_secrets_regex import redact_then_truncate


class InventoryProviderError(RuntimeError):
    pass


HttpFn = Callable[..., HttpResponse]


class LinodeInventoryProvider:
    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.linode.com/v4",
        http_request_fn: HttpFn = http_request,
    ) -> None:
        clean = str(token or "").strip()
        if not clean:
            raise InventoryProviderError("linode token missing")
        self._token = clean
        self._base_url = base_url.rstrip("/")
        self._http = http_request_fn
        self._cache: dict[str, Any] = {}

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        key = f"{method}:{path}:{payload or {}}"
        if method.upper() == "GET" and key in self._cache:
            return dict(self._cache[key])
        try:
            response = self._http(
                f"{self._base_url}{path}",
                method=method,
                headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
                json_payload=dict(payload or {}) if payload is not None else None,
                timeout=20,
                allow_loopback_http=False,
            )
        except Exception as exc:
            raise InventoryProviderError(redact_then_truncate(str(exc), limit=240)) from exc
        if int(response.status_code) >= 400:
            body = redact_then_truncate(response.text.replace(self._token, "[REDACTED]"), limit=240)
            raise InventoryProviderError(f"linode api failed with {response.status_code}: {body}")
        parsed = parse_json_object(response, label="linode api")
        if method.upper() == "GET":
            self._cache[key] = dict(parsed)
        return parsed

    def list_servers(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/linode/instances")
        return [self._server(row) for row in payload.get("data", []) if isinstance(row, Mapping)]

    def list_server_types(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/linode/types")
        return [dict(row) for row in payload.get("data", []) if isinstance(row, Mapping)]

    def provision_server(
        self,
        *,
        label: str,
        linode_type: str,
        image: str,
        region: str,
        authorized_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "label": label,
            "type": linode_type,
            "image": image,
            "region": region,
            "authorized_keys": list(authorized_keys or []),
        }
        return self._server(self._request("POST", "/linode/instances", payload))

    def refresh_server(self, server_id: str) -> dict[str, Any]:
        return self._server(self._request("GET", f"/linode/instances/{server_id}"))

    def remove_server(self, server_id: str, *, destroy: bool = False) -> dict[str, Any]:
        if not destroy:
            raise InventoryProviderError("linode destroy requires explicit destroy=True")
        return self._request("DELETE", f"/linode/instances/{server_id}")

    def register_ssh_key(self, *, label: str, public_key: str) -> dict[str, Any]:
        return dict(self._request("POST", "/profile/sshkeys", {"label": label, "ssh_key": public_key}))

    def probe(self, machine: Mapping[str, Any], *, runner: Callable[..., Any]) -> dict[str, Any]:
        completed = runner(machine)
        stdout = getattr(completed, "stdout", completed if isinstance(completed, str) else "")
        return parse_probe_output(str(stdout))

    @staticmethod
    def _server(row: Mapping[str, Any]) -> dict[str, Any]:
        ipv4 = row.get("ipv4") if isinstance(row.get("ipv4"), list) else []
        specs = row.get("specs") if isinstance(row.get("specs"), Mapping) else {}
        ram_mb = float(specs.get("memory", 0) or 0)
        disk_mb = float(specs.get("disk", 0) or 0)
        return {
            "provider": "linode",
            "provider_resource_id": str(row.get("id", "")),
            "hostname": str(row.get("label", "")),
            "ssh_host": str(ipv4[0] if ipv4 else ""),
            "region": str(row.get("region", "")),
            "status": str(row.get("status", "")),
            "hardware_summary": {
                "vcpu_cores": specs.get("vcpus", 0),
                "ram_gib": round(ram_mb / 1024, 2),
                "disk_gib": round(disk_mb / 1024, 2),
            },
        }
