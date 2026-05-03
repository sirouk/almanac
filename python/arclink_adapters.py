#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Any


class StripeWebhookError(ValueError):
    pass


class FakeStripeClient:
    def __init__(self) -> None:
        self.checkout_sessions: dict[str, dict[str, Any]] = {}
        self.portal_sessions: dict[str, dict[str, Any]] = {}

    def create_checkout_session(
        self,
        *,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        client_reference_id: str = "",
        metadata: dict[str, str] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        if idempotency_key:
            digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:18]
            session_id = f"cs_test_{digest}"
        else:
            session_id = f"cs_test_{len(self.checkout_sessions) + 1}"
        session = {
            "id": session_id,
            "user_id": user_id,
            "price_id": price_id,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": client_reference_id or user_id,
            "metadata": dict(metadata or {}),
            "subscription_data": {"metadata": dict(metadata or {})},
            "url": f"https://stripe.test/checkout/{session_id}",
        }
        self.checkout_sessions[session_id] = session
        return dict(session)

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict[str, Any]:
        session_id = f"bps_test_{len(self.portal_sessions) + 1}"
        session = {"id": session_id, "customer_id": customer_id, "return_url": return_url, "url": f"https://stripe.test/portal/{session_id}"}
        self.portal_sessions[session_id] = session
        return dict(session)


class LiveStripeClient:
    """Live Stripe client that delegates to the stripe SDK.

    Requires STRIPE_SECRET_KEY to be set. Refuses to construct without it.
    """

    def __init__(self, *, secret_key: str = "") -> None:
        key = secret_key or ""
        if not key.strip():
            raise ValueError("LiveStripeClient requires a non-blank STRIPE_SECRET_KEY")
        self._key = key.strip()

    def _stripe_module(self):
        import stripe as _stripe  # deferred import: only needed for live path
        _stripe.api_key = self._key
        return _stripe

    def create_checkout_session(
        self,
        *,
        user_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        client_reference_id: str = "",
        metadata: dict[str, str] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        _stripe = self._stripe_module()
        params: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": client_reference_id or user_id,
            "metadata": dict(metadata or {}),
            "subscription_data": {"metadata": dict(metadata or {})},
            "allow_promotion_codes": True,
            "billing_address_collection": "auto",
            "custom_text": {
                "submit": {
                    "message": (
                        "Raven will watch for payment confirmation and move your ArcLink agent into provisioning."
                    )
                }
            },
        }
        kwargs: dict[str, Any] = {}
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key
        session = _stripe.checkout.Session.create(**params, **kwargs)
        return {"id": session.id, "url": session.url}

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict[str, Any]:
        _stripe = self._stripe_module()
        session = _stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"id": session.id, "url": session.url}


def resolve_stripe_client(env: dict[str, str] | None = None) -> FakeStripeClient | LiveStripeClient:
    """Return a LiveStripeClient if STRIPE_SECRET_KEY is set, else FakeStripeClient."""
    import os
    source = env if env is not None else dict(os.environ)
    key = str(source.get("STRIPE_SECRET_KEY") or "").strip()
    if key:
        return LiveStripeClient(secret_key=key)
    return FakeStripeClient()


def sign_stripe_webhook(payload: str, secret: str, *, timestamp: int | None = None) -> str:
    stamp = int(time.time()) if timestamp is None else int(timestamp)
    signed_payload = f"{stamp}.{payload}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def verify_stripe_webhook(payload: str, signature: str, secret: str, *, tolerance_seconds: int = 300) -> dict[str, Any]:
    if not str(secret or "").strip():
        raise StripeWebhookError("Stripe webhook secret must be non-blank")
    parts: dict[str, str] = {}
    for item in signature.split(","):
        key, _, value = item.partition("=")
        if key and value:
            parts[key] = value
    try:
        timestamp = int(parts["t"])
    except (KeyError, ValueError) as exc:
        raise StripeWebhookError("missing Stripe webhook timestamp") from exc
    if abs(int(time.time()) - timestamp) > tolerance_seconds:
        raise StripeWebhookError("Stripe webhook timestamp is outside tolerance")
    expected = sign_stripe_webhook(payload, secret, timestamp=timestamp).split("v1=", 1)[1]
    if not hmac.compare_digest(parts.get("v1", ""), expected):
        raise StripeWebhookError("Stripe webhook signature mismatch")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise StripeWebhookError("Stripe webhook payload must be an object")
    return parsed


@dataclass(frozen=True)
class DnsRecord:
    hostname: str
    record_type: str
    target: str
    proxied: bool = True


class FakeCloudflareClient:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], DnsRecord] = {}

    def upsert_record(self, record: DnsRecord) -> DnsRecord:
        key = (record.hostname, record.record_type.upper())
        stored = DnsRecord(
            hostname=record.hostname,
            record_type=record.record_type.upper(),
            target=record.target,
            proxied=record.proxied,
        )
        self.records[key] = stored
        return stored

    def drift(self, desired: list[DnsRecord]) -> list[str]:
        drift: list[str] = []
        for record in desired:
            key = (record.hostname, record.record_type.upper())
            actual = self.records.get(key)
            if actual is None:
                drift.append(f"missing {record.record_type.upper()} {record.hostname}")
            elif actual.target != record.target or actual.proxied != record.proxied:
                drift.append(f"changed {record.record_type.upper()} {record.hostname}")
        return drift

    def delete_record(self, hostname: str, record_type: str) -> bool:
        key = (hostname.lower(), record_type.upper())
        if key in self.records:
            del self.records[key]
            return True
        return False

    def teardown_records(self, hostnames: list[str], record_type: str = "CNAME") -> list[str]:
        removed: list[str] = []
        for hostname in hostnames:
            if self.delete_record(hostname, record_type):
                removed.append(hostname)
        return removed


def arclink_hostnames(prefix: str, base_domain: str) -> dict[str, str]:
    clean_prefix = str(prefix or "").strip().lower()
    clean_domain = str(base_domain or "").strip().lower().strip(".")
    if not clean_prefix or not clean_domain:
        raise ValueError("prefix and base_domain are required")
    return {
        "dashboard": f"u-{clean_prefix}.{clean_domain}",
        "files": f"files-{clean_prefix}.{clean_domain}",
        "code": f"code-{clean_prefix}.{clean_domain}",
        "hermes": f"hermes-{clean_prefix}.{clean_domain}",
    }


def arclink_tailscale_hostnames(prefix: str, tailscale_dns_name: str, *, strategy: str = "path") -> dict[str, str]:
    clean_prefix = str(prefix or "").strip().lower()
    clean_host = str(tailscale_dns_name or "").strip().lower().strip(".")
    clean_strategy = str(strategy or "path").strip().lower()
    if not clean_prefix or not clean_host:
        raise ValueError("prefix and tailscale_dns_name are required")
    if clean_strategy == "path":
        return {role: clean_host for role in ("dashboard", "files", "code", "hermes")}
    if clean_strategy == "subdomain":
        return {
            "dashboard": f"u-{clean_prefix}.{clean_host}",
            "files": f"files-{clean_prefix}.{clean_host}",
            "code": f"code-{clean_prefix}.{clean_host}",
            "hermes": f"hermes-{clean_prefix}.{clean_host}",
        }
    raise ValueError("ArcLink Tailscale host strategy must be path or subdomain")


def arclink_role_path_prefixes(prefix: str) -> dict[str, str]:
    clean_prefix = re.sub(r"[^a-z0-9-]+", "-", str(prefix or "").strip().lower()).strip("-")
    if not clean_prefix:
        raise ValueError("prefix is required")
    root = f"/u/{clean_prefix}"
    return {
        "dashboard": root,
        "files": f"{root}/files",
        "code": f"{root}/code",
        "hermes": f"{root}/hermes",
    }


def arclink_access_urls(
    *,
    prefix: str,
    base_domain: str,
    ingress_mode: str = "domain",
    tailscale_dns_name: str = "",
    tailscale_host_strategy: str = "path",
) -> dict[str, str]:
    mode = str(ingress_mode or "domain").strip().lower()
    strategy = str(tailscale_host_strategy or "path").strip().lower()
    if mode == "tailscale":
        hostnames = arclink_tailscale_hostnames(
            prefix,
            tailscale_dns_name or base_domain,
            strategy=strategy,
        )
        if strategy == "path":
            prefixes = arclink_role_path_prefixes(prefix)
            return {role: f"https://{hostnames[role]}{prefixes[role]}" for role in hostnames}
        return {role: f"https://{hostname}" for role, hostname in hostnames.items()}
    if mode != "domain":
        raise ValueError("ArcLink ingress mode must be domain or tailscale")
    return {role: f"https://{hostname}" for role, hostname in arclink_hostnames(prefix, base_domain).items()}


def render_traefik_http_labels(
    *,
    service_name: str,
    hostname: str,
    port: int,
    docker_network: str = "",
    priority: int = 0,
) -> dict[str, str]:
    router = f"arclink-{service_name}"
    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{router}.rule": f"Host(`{hostname}`)",
        f"traefik.http.routers.{router}.entrypoints": "web",
        f"traefik.http.services.{router}.loadbalancer.server.port": str(int(port)),
    }
    clean_network = str(docker_network or "").strip()
    if clean_network:
        labels["traefik.docker.network"] = clean_network
    if int(priority or 0) > 0:
        labels[f"traefik.http.routers.{router}.priority"] = str(int(priority))
    return labels


def render_traefik_http_path_labels(
    *,
    service_name: str,
    hostname: str,
    path_prefix: str,
    port: int,
    docker_network: str = "",
    priority: int = 0,
) -> dict[str, str]:
    router = f"arclink-{service_name}"
    middleware = f"{router}-strip"
    clean_path = str(path_prefix or "").strip()
    if not clean_path.startswith("/"):
        clean_path = f"/{clean_path}"
    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{router}.rule": f"Host(`{hostname}`) && PathPrefix(`{clean_path}`)",
        f"traefik.http.routers.{router}.entrypoints": "web",
        f"traefik.http.routers.{router}.middlewares": middleware,
        f"traefik.http.middlewares.{middleware}.stripprefix.prefixes": clean_path,
        f"traefik.http.services.{router}.loadbalancer.server.port": str(int(port)),
    }
    clean_network = str(docker_network or "").strip()
    if clean_network:
        labels["traefik.docker.network"] = clean_network
    if int(priority or 0) > 0:
        labels[f"traefik.http.routers.{router}.priority"] = str(int(priority))
    return labels
