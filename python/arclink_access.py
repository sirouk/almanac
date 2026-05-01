#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass


ARCLINK_NEXTCLOUD_ISOLATION_MODEL = "dedicated_per_deployment"
ARCLINK_SSH_ACCESS_STRATEGY = "cloudflare_access_tcp"


class ArcLinkAccessError(ValueError):
    pass


@dataclass(frozen=True)
class SshAccessRecord:
    strategy: str
    username: str
    hostname: str
    command_hint: str


def arclink_nextcloud_isolation_model() -> str:
    return ARCLINK_NEXTCLOUD_ISOLATION_MODEL


def build_arclink_ssh_access_record(
    *,
    username: str,
    hostname: str,
    strategy: str = ARCLINK_SSH_ACCESS_STRATEGY,
) -> SshAccessRecord:
    clean_strategy = str(strategy or "").strip().lower()
    clean_username = str(username or "").strip()
    clean_hostname = str(hostname or "").strip().lower()
    if clean_strategy in {"raw_http", "ssh_over_http"}:
        raise ArcLinkAccessError("ArcLink must not advertise raw SSH over HTTP")
    if clean_hostname.startswith(("http://", "https://")):
        raise ArcLinkAccessError("ArcLink SSH access requires a TCP hostname, not an HTTP URL")
    if clean_strategy != ARCLINK_SSH_ACCESS_STRATEGY:
        raise ArcLinkAccessError(f"unsupported ArcLink SSH access strategy: {clean_strategy}")
    if not clean_username or not clean_hostname:
        raise ArcLinkAccessError("ArcLink SSH access requires username and hostname")
    return SshAccessRecord(
        strategy=clean_strategy,
        username=clean_username,
        hostname=clean_hostname,
        command_hint=f"cloudflared access ssh --hostname {clean_hostname} --url ssh://{clean_username}@{clean_hostname}",
    )
