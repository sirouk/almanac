#!/usr/bin/env python3
"""Fail-closed Hetzner Cloud inventory adapter."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from arclink_http import HttpResponse, http_request, parse_json_object
from arclink_inventory import parse_probe_output
from arclink_secrets_regex import redact_then_truncate


class InventoryProviderError(RuntimeError):
    pass


HttpFn = Callable[..., HttpResponse]


class HetznerInventoryProvider:
    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.hetzner.cloud/v1",
        http_request_fn: HttpFn = http_request,
    ) -> None:
        clean = str(token or "").strip()
        if not clean:
            raise InventoryProviderError("hetzner token missing")
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
            raise InventoryProviderError(f"hetzner api failed with {response.status_code}: {body}")
        parsed = parse_json_object(response, label="hetzner api")
        if method.upper() == "GET":
            self._cache[key] = dict(parsed)
        return parsed

    def list_servers(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/servers")
        return [self._server(row) for row in payload.get("servers", []) if isinstance(row, Mapping)]

    def list_server_types(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/server_types")
        return [dict(row) for row in payload.get("server_types", []) if isinstance(row, Mapping)]

    def provision_server(
        self,
        *,
        name: str,
        server_type: str,
        image: str,
        location: str,
        ssh_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "server_type": server_type,
            "image": image,
            "location": location,
            "ssh_keys": list(ssh_keys or []),
        }
        return self._server(self._request("POST", "/servers", payload).get("server", {}))

    def refresh_server(self, server_id: str) -> dict[str, Any]:
        return self._server(self._request("GET", f"/servers/{server_id}").get("server", {}))

    def remove_server(self, server_id: str, *, destroy: bool = False) -> dict[str, Any]:
        if not destroy:
            raise InventoryProviderError("hetzner destroy requires explicit destroy=True")
        return self._request("DELETE", f"/servers/{server_id}")

    def register_ssh_key(self, *, name: str, public_key: str) -> dict[str, Any]:
        return dict(self._request("POST", "/ssh_keys", {"name": name, "public_key": public_key}).get("ssh_key", {}))

    def probe(self, machine: Mapping[str, Any], *, runner: Callable[..., Any]) -> dict[str, Any]:
        completed = runner(machine)
        stdout = getattr(completed, "stdout", completed if isinstance(completed, str) else "")
        return parse_probe_output(str(stdout))

    @staticmethod
    def _server(row: Mapping[str, Any]) -> dict[str, Any]:
        public_net = row.get("public_net") if isinstance(row.get("public_net"), Mapping) else {}
        ipv4 = public_net.get("ipv4") if isinstance(public_net.get("ipv4"), Mapping) else {}
        server_type = row.get("server_type") if isinstance(row.get("server_type"), Mapping) else {}
        datacenter = row.get("datacenter") if isinstance(row.get("datacenter"), Mapping) else {}
        location = datacenter.get("location") if isinstance(datacenter.get("location"), Mapping) else {}
        return {
            "provider": "hetzner",
            "provider_resource_id": str(row.get("id", "")),
            "hostname": str(row.get("name", "")),
            "ssh_host": str(ipv4.get("ip", "")),
            "region": str(location.get("name", "")),
            "status": str(row.get("status", "")),
            "hardware_summary": {
                "vcpu_cores": server_type.get("cores", 0),
                "ram_gib": server_type.get("memory", 0),
                "disk_gib": server_type.get("disk", 0),
            },
        }
