#!/usr/bin/env python3
"""ArcLink Academy weekly forward-maintenance scheduler.

Iterates graduated, forward-maintained Trainees, performs bounded weekly live
public-source crawl observations, and runs the no-write continuing-education
review for each (see arclink_academy_programs.academy_continuing_education). It
records crawl-observation, control-plane event, audit, and notification rows so
the dashboard / Operator Raven can surface the weekly status.

This job stores NO raw fetched content and performs NO Agent SOUL/skills/qmd/vault
writes. Crawl observations are metadata + content hashes only. Changed, removed,
or unsafe sources go to review/block states; the real apply remains behind the
PG-HERMES `academy_apply` action.

CLI mirrors the action worker: `--once --json` for the docker job loop.
"""
from __future__ import annotations

import argparse
import ipaddress
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from arclink_control import (
    Config,
    append_arclink_audit,
    append_arclink_event,
    connect_db,
    queue_notification,
    utc_now_iso,
)
from arclink_academy_programs import (
    academy_continuing_education,
    academy_trainer_client_from_env,
    academy_trainer_live_authorized_from_env,
    list_academy_trainees,
    read_academy_proposals,
    read_central_specialist_sources,
    refresh_specialist_capsule,
    run_academy_trainer_review,
    seed_default_academy_programs,
)
from arclink_secrets_regex import contains_secret_material


DEFAULT_FORWARD_MAINTENANCE_LIMIT = 200
DEFAULT_LIVE_CRAWL_LIMIT = 100
DEFAULT_LIVE_CRAWL_PER_HOST_LIMIT = 20
DEFAULT_LIVE_CRAWL_TIMEOUT_SECONDS = 12
DEFAULT_LIVE_CRAWL_MAX_BYTES = 750_000
ACADEMY_CRAWL_USER_AGENT = "ArcLinkAcademyCrawler/1.0 (+https://arclink.online/policy)"
LIVE_CRAWL_SOURCE_LANES = frozenset(
    {
        "web_article",
        "wikimedia",
        "scholarly_standard",
        "github_repository",
    }
)
_CrawlFetcher = Callable[..., Mapping[str, Any]]


def _env_bool(env: Mapping[str, str] | None, key: str, *, default: bool = False) -> bool:
    raw = str((env or {}).get(key, os.environ.get(key, ""))).strip().lower()
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _env_int(env: Mapping[str, str] | None, key: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = str((env or {}).get(key, os.environ.get(key, ""))).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return default
    return loaded if isinstance(loaded, type(default)) else default


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _safe_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:32]


def _host_key(url: str) -> str:
    try:
        return str(urllib.parse.urlsplit(url).hostname or "").strip().lower()
    except Exception:
        return ""


def _html_to_observation_text(text: str) -> str:
    body = str(text or "")
    body = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", body)
    body = re.sub(r"(?is)<!--.*?-->", " ", body)
    body = re.sub(r"(?is)<[^>]+>", " ", body)
    body = re.sub(r"&(?:nbsp|amp|lt|gt|quot|apos);", " ", body)
    return " ".join(body.split())[:80_000]


def _crawl_text_unsafe(text: str) -> bool:
    if contains_secret_material(text[:20_000], allow_safe_refs=False):
        return True
    lowered = text[:20_000].casefold()
    prompt_markers = (
        "ignore previous instructions",
        "ignore all prior instructions",
        "system prompt",
        "developer message",
        "reveal your instructions",
        "exfiltrate",
        "send your secrets",
    )
    return any(marker in lowered for marker in prompt_markers)


def _is_public_ip_address(value: str) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        addr.is_loopback
        or addr.is_private
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _url_allowed_for_live_crawl(
    url: str,
    *,
    env: Mapping[str, str] | None,
    fetcher: _CrawlFetcher | None,
) -> tuple[bool, str]:
    raw = str(url or "").strip()
    if not raw:
        return False, "missing URL"
    try:
        parsed = urllib.parse.urlsplit(raw)
    except Exception:
        return False, "invalid URL"
    if parsed.scheme not in {"https", "http"}:
        return False, "unsupported URL scheme"
    allow_test_urls = bool(fetcher is not None) and _env_bool(env, "ARCLINK_ACADEMY_CE_ALLOW_TEST_URLS", default=False)
    if parsed.scheme != "https" and not allow_test_urls:
        return False, "live crawl requires https"
    if parsed.username or parsed.password:
        return False, "URL userinfo is not allowed"
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return False, "missing host"
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return False, "loopback host is not allowed"
    if parsed.port is not None and parsed.port not in ({443, 80} if allow_test_urls else {443}):
        return False, "non-standard port is not allowed"
    if allow_test_urls and host.endswith((".test", ".example", ".invalid")):
        return True, ""
    if _is_public_ip_address(host):
        return True, ""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        return False, f"DNS resolution failed: {exc}"
    addresses = {item[4][0] for item in infos if item and item[4]}
    if not addresses:
        return False, "DNS resolution returned no addresses"
    if not all(_is_public_ip_address(address) for address in addresses):
        return False, "host resolves to non-public address"
    return True, ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _default_fetch_url(
    *,
    url: str,
    headers: Mapping[str, str],
    timeout: int,
    max_bytes: int,
) -> Mapping[str, Any]:
    request = urllib.request.Request(str(url), headers=dict(headers), method="GET")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:  # noqa: S310 - URL was SSRF-validated above
            data = response.read(max_bytes + 1)
            return {
                "status_code": int(response.status),
                "headers": {str(k).lower(): str(v) for k, v in response.headers.items()},
                "text": data[:max_bytes].decode("utf-8", errors="replace"),
                "truncated": len(data) > max_bytes,
            }
    except urllib.error.HTTPError as exc:
        data = exc.read(max_bytes + 1) if hasattr(exc, "read") else b""
        headers_out = {}
        if getattr(exc, "headers", None) is not None:
            headers_out = {str(k).lower(): str(v) for k, v in exc.headers.items()}
        return {
            "status_code": int(exc.code),
            "headers": headers_out,
            "text": data[:max_bytes].decode("utf-8", errors="replace"),
            "truncated": len(data) > max_bytes,
        }
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise RuntimeError(str(getattr(exc, "reason", exc))[:200]) from exc


def _fetch_url(
    fetcher: _CrawlFetcher | None,
    *,
    url: str,
    headers: Mapping[str, str],
    timeout: int,
    max_bytes: int,
) -> Mapping[str, Any]:
    if fetcher is None:
        return _default_fetch_url(url=url, headers=headers, timeout=timeout, max_bytes=max_bytes)
    try:
        return fetcher(url=url, headers=headers, timeout=timeout, max_bytes=max_bytes)
    except TypeError:
        return fetcher(url, headers, timeout, max_bytes)  # type: ignore[misc]


def _robots_allowed(
    url: str,
    *,
    env: Mapping[str, str] | None,
    fetcher: _CrawlFetcher | None,
    user_agent: str,
    timeout: int,
    max_bytes: int,
) -> tuple[bool, str]:
    if not _env_bool(env, "ARCLINK_ACADEMY_CE_RESPECT_ROBOTS", default=True):
        return True, ""
    parsed = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    allowed, reason = _url_allowed_for_live_crawl(robots_url, env=env, fetcher=fetcher)
    if not allowed:
        return False, f"robots policy blocked: {reason}"
    try:
        response = _fetch_url(
            fetcher,
            url=robots_url,
            headers={"User-Agent": user_agent, "Accept": "text/plain"},
            timeout=timeout,
            max_bytes=min(max_bytes, 128_000),
        )
    except Exception as exc:  # noqa: BLE001 - fail closed when robots cannot be checked
        return False, f"robots fetch failed: {str(exc)[:160]}"
    status = int(response.get("status_code") or 0)
    if status in {401, 403}:
        return False, "robots.txt denied access"
    if 300 <= status < 400:
        return False, "robots.txt redirected; redirect not followed by crawler policy"
    if status >= 400:
        return True, ""
    parser = urllib.robotparser.RobotFileParser(robots_url)
    parser.parse(str(response.get("text") or "").splitlines())
    return (parser.can_fetch(user_agent, url), "robots.txt disallows this URL")


def _normalize_headers(value: Mapping[str, Any] | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in dict(value or {}).items()}


def _crawl_source(
    *,
    url: str,
    accepted_hash: str,
    enrichment: Mapping[str, Any],
    env: Mapping[str, str] | None,
    fetcher: _CrawlFetcher | None,
) -> dict[str, Any]:
    timeout = _env_int(
        env,
        "ARCLINK_ACADEMY_CE_CRAWL_TIMEOUT_SECONDS",
        default=DEFAULT_LIVE_CRAWL_TIMEOUT_SECONDS,
        minimum=2,
        maximum=60,
    )
    max_bytes = _env_int(
        env,
        "ARCLINK_ACADEMY_CE_CRAWL_MAX_BYTES",
        default=DEFAULT_LIVE_CRAWL_MAX_BYTES,
        minimum=32_000,
        maximum=2_000_000,
    )
    user_agent = str((env or {}).get("ARCLINK_ACADEMY_CE_CRAWL_USER_AGENT") or ACADEMY_CRAWL_USER_AGENT)
    allowed, reason = _url_allowed_for_live_crawl(url, env=env, fetcher=fetcher)
    if not allowed:
        return {"status": "blocked", "reason": reason, "observed": {}}
    robots_ok, robots_reason = _robots_allowed(
        url,
        env=env,
        fetcher=fetcher,
        user_agent=user_agent,
        timeout=timeout,
        max_bytes=max_bytes,
    )
    if not robots_ok:
        return {"status": "blocked", "reason": robots_reason, "observed": {}}
    crawl_state = enrichment.get("crawl") if isinstance(enrichment.get("crawl"), Mapping) else {}
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,text/plain,application/xhtml+xml,application/xml;q=0.8,*/*;q=0.2",
        "Accept-Language": "en-US,en;q=0.8",
    }
    if crawl_state.get("etag"):
        headers["If-None-Match"] = str(crawl_state.get("etag"))
    if crawl_state.get("last_modified"):
        headers["If-Modified-Since"] = str(crawl_state.get("last_modified"))
    started = time.monotonic()
    try:
        response = _fetch_url(fetcher, url=url, headers=headers, timeout=timeout, max_bytes=max_bytes)
    except Exception as exc:  # noqa: BLE001 - a fetch failure becomes an observation, not a crash
        return {"status": "failed", "reason": str(exc)[:180], "observed": {}}
    elapsed_ms = int((time.monotonic() - started) * 1000)
    status_code = int(response.get("status_code") or 0)
    response_headers = _normalize_headers(response.get("headers") if isinstance(response.get("headers"), Mapping) else {})
    if status_code == 304:
        return {
            "status": "unchanged",
            "reason": "not modified",
            "http_status": status_code,
            "elapsed_ms": elapsed_ms,
            "headers": response_headers,
            "content_hash": str(accepted_hash or ""),
            "observed": {"content_hash": str(accepted_hash or "")} if accepted_hash else {},
        }
    if status_code in {404, 410}:
        return {
            "status": "removed",
            "reason": "source disappeared",
            "http_status": status_code,
            "elapsed_ms": elapsed_ms,
            "headers": response_headers,
            "observed": {"removed": True},
        }
    if status_code in {451}:
        return {
            "status": "tombstoned",
            "reason": "source is legally unavailable",
            "http_status": status_code,
            "elapsed_ms": elapsed_ms,
            "headers": response_headers,
            "observed": {"tombstoned": True},
        }
    if status_code < 200 or status_code >= 300:
        return {
            "status": "failed",
            "reason": f"http {status_code}",
            "http_status": status_code,
            "elapsed_ms": elapsed_ms,
            "headers": response_headers,
            "observed": {},
        }
    normalized = _html_to_observation_text(str(response.get("text") or ""))
    if len(normalized) < 80:
        return {
            "status": "failed",
            "reason": "fetched content too small for safe review",
            "http_status": status_code,
            "elapsed_ms": elapsed_ms,
            "headers": response_headers,
            "observed": {},
        }
    observed_hash = _safe_hash(normalized)
    unsafe = _crawl_text_unsafe(normalized)
    if unsafe:
        return {
            "status": "tombstoned",
            "reason": "fetched content tripped prompt-injection or secret screen",
            "http_status": status_code,
            "elapsed_ms": elapsed_ms,
            "headers": response_headers,
            "content_hash": observed_hash,
            "observed": {"tombstoned": True},
        }
    status = "changed" if accepted_hash and observed_hash != accepted_hash else "unchanged"
    return {
        "status": status,
        "reason": "source digest changed" if status == "changed" else "source digest unchanged",
        "http_status": status_code,
        "elapsed_ms": elapsed_ms,
        "headers": response_headers,
        "content_hash": observed_hash,
        "observed_chars": len(normalized),
        "truncated": bool(response.get("truncated")),
        "observed": {"content_hash": observed_hash},
    }


def _observation_id(*, source_ref_kind: str, source_ref_id: str, trainee_id: str, observed_at: str) -> str:
    seed = f"{source_ref_kind}|{source_ref_id}|{trainee_id}|{observed_at}"
    return "acrawl_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def _record_crawl_observation(
    conn: sqlite3.Connection,
    *,
    source_ref_kind: str,
    source_ref_id: str,
    source_uid: str,
    specialist_uid: str,
    trainee: Mapping[str, Any],
    lane_id: str,
    canonical_url: str,
    crawl: Mapping[str, Any],
    observed_at: str,
) -> None:
    metadata = {
        "live_crawl": True,
        "reason": str(crawl.get("reason") or "")[:240],
        "elapsed_ms": int(crawl.get("elapsed_ms") or 0),
        "observed_chars": int(crawl.get("observed_chars") or 0),
        "truncated": bool(crawl.get("truncated")),
        "etag": str((_normalize_headers(crawl.get("headers") if isinstance(crawl.get("headers"), Mapping) else {}) or {}).get("etag") or "")[:240],
        "last_modified": str((_normalize_headers(crawl.get("headers") if isinstance(crawl.get("headers"), Mapping) else {}) or {}).get("last-modified") or "")[:240],
        "raw_stored": False,
    }
    conn.execute(
        """
        INSERT INTO academy_source_crawl_observations (
          observation_id, source_ref_kind, source_ref_id, source_uid, specialist_uid,
          trainee_id, user_id, deployment_id, lane_id, canonical_url, status,
          content_hash, http_status, reason, metadata_json, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _observation_id(
                source_ref_kind=source_ref_kind,
                source_ref_id=source_ref_id,
                trainee_id=str(trainee.get("trainee_id") or ""),
                observed_at=observed_at,
            ),
            source_ref_kind,
            source_ref_id,
            source_uid,
            specialist_uid,
            str(trainee.get("trainee_id") or ""),
            str(trainee.get("user_id") or ""),
            str(trainee.get("deployment_id") or ""),
            lane_id,
            canonical_url,
            str(crawl.get("status") or "observed"),
            str(crawl.get("content_hash") or ""),
            int(crawl.get("http_status") or 0),
            str(crawl.get("reason") or "")[:500],
            _dumps(metadata),
            observed_at,
        ),
    )


def _update_central_source_crawl_state(
    conn: sqlite3.Connection,
    *,
    source_uid: str,
    crawl: Mapping[str, Any],
    observed_at: str,
) -> None:
    row = conn.execute("SELECT enrichment_json FROM academy_sources WHERE source_uid = ?", (source_uid,)).fetchone()
    if row is None:
        return
    enrichment = _loads(row["enrichment_json"], default={})
    if not isinstance(enrichment, dict):
        enrichment = {}
    headers = _normalize_headers(crawl.get("headers") if isinstance(crawl.get("headers"), Mapping) else {})
    enrichment["crawl"] = {
        "last_crawled_at": observed_at,
        "status": str(crawl.get("status") or ""),
        "http_status": int(crawl.get("http_status") or 0),
        "observed_content_hash": str(crawl.get("content_hash") or ""),
        "etag": headers.get("etag", ""),
        "last_modified": headers.get("last-modified", ""),
        "raw_stored": False,
        "review_required": str(crawl.get("status") or "") in {"changed", "removed", "tombstoned"},
    }
    conn.execute(
        """
        UPDATE academy_sources
        SET enrichment_json = ?, last_observed_at = ?, updated_at = ?
        WHERE source_uid = ?
        """,
        (_dumps(enrichment), observed_at, observed_at, source_uid),
    )


def _update_proposal_crawl_state(
    conn: sqlite3.Connection,
    *,
    proposal_id: str,
    crawl: Mapping[str, Any],
    observed_at: str,
) -> None:
    row = conn.execute(
        "SELECT trainer_review_json FROM academy_resource_proposals WHERE proposal_id = ?", (proposal_id,)
    ).fetchone()
    if row is None:
        return
    review = _loads(row["trainer_review_json"], default={})
    if not isinstance(review, dict):
        review = {}
    review["weekly_crawl"] = {
        "last_crawled_at": observed_at,
        "status": str(crawl.get("status") or ""),
        "http_status": int(crawl.get("http_status") or 0),
        "observed_content_hash": str(crawl.get("content_hash") or ""),
        "raw_stored": False,
        "review_required": str(crawl.get("status") or "") in {"changed", "removed", "tombstoned"},
    }
    conn.execute(
        "UPDATE academy_resource_proposals SET trainer_review_json = ?, updated_at = ? WHERE proposal_id = ?",
        (_dumps(review), observed_at, proposal_id),
    )


def _crawlable_source_rows(
    conn: sqlite3.Connection,
    trainee: Mapping[str, Any],
    *,
    specialist_uid: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_central_specialist_sources(conn, trainee_id=str(trainee.get("trainee_id") or "")):
        lane = str(row.get("lane_id") or "").strip()
        if lane not in LIVE_CRAWL_SOURCE_LANES:
            continue
        rows.append(
            {
                "source_ref_kind": "central_source",
                "source_ref_id": str(row.get("source_uid") or ""),
                "source_uid": str(row.get("source_uid") or ""),
                "specialist_uid": str(specialist_uid or ""),
                "lane_id": lane,
                "canonical_url": str(row.get("canonical_url") or ""),
                "accepted_hash": str(row.get("content_hash") or ""),
                "enrichment": _loads(row.get("enrichment_json"), default={}),
            }
        )
    for proposal in read_academy_proposals(
        conn,
        trainee_id=str(trainee.get("trainee_id") or ""),
        statuses=("proposed", "review_pending", "accepted", "deduped"),
    ):
        lane = str(proposal.get("lane_id") or "").strip()
        if lane not in LIVE_CRAWL_SOURCE_LANES:
            continue
        url = str(proposal.get("origin_url") or "").strip()
        if not url:
            continue
        rows.append(
            {
                "source_ref_kind": "trainee_proposal",
                "source_ref_id": str(proposal.get("proposal_id") or ""),
                "source_uid": "",
                "specialist_uid": "",
                "lane_id": lane,
                "canonical_url": url,
                "accepted_hash": _safe_hash(str(proposal.get("summary") or "")),
                "enrichment": _loads(proposal.get("trainer_review"), default={}),
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    seen_urls: set[str] = set()
    for row in rows:
        key = (str(row.get("source_ref_kind") or ""), str(row.get("source_ref_id") or ""))
        url_key = str(row.get("canonical_url") or "").strip().lower()
        if key in seen or (url_key and url_key in seen_urls):
            continue
        seen.add(key)
        if url_key:
            seen_urls.add(url_key)
        deduped.append(row)
    return deduped


def _live_crawl_observed_sources(
    conn: sqlite3.Connection,
    *,
    trainee: Mapping[str, Any],
    specialist_uid: str = "",
    env: Mapping[str, str] | None,
    fetcher: _CrawlFetcher | None,
    observed_at: str,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    if not _env_bool(env, "ARCLINK_ACADEMY_CE_LIVE_CRAWL", default=True):
        return {}, {
            "enabled": False,
            "attempted": 0,
            "fetched": 0,
            "unchanged": 0,
            "changed": 0,
            "blocked": 0,
            "failed": 0,
            "removed": 0,
            "tombstoned": 0,
            "skipped": 0,
        }
    limit = _env_int(
        env,
        "ARCLINK_ACADEMY_CE_CRAWL_LIMIT",
        default=DEFAULT_LIVE_CRAWL_LIMIT,
        minimum=0,
        maximum=1000,
    )
    per_host_limit = _env_int(
        env,
        "ARCLINK_ACADEMY_CE_CRAWL_PER_HOST_LIMIT",
        default=DEFAULT_LIVE_CRAWL_PER_HOST_LIMIT,
        minimum=1,
        maximum=200,
    )
    summary = {
        "enabled": True,
        "attempted": 0,
        "fetched": 0,
        "unchanged": 0,
        "changed": 0,
        "blocked": 0,
        "failed": 0,
        "removed": 0,
        "tombstoned": 0,
        "skipped": 0,
    }
    observed: dict[str, Mapping[str, Any]] = {}
    by_host: dict[str, int] = {}
    for source in _crawlable_source_rows(conn, trainee, specialist_uid=specialist_uid):
        if limit and int(summary["attempted"]) >= limit:
            summary["skipped"] += 1
            continue
        url = str(source.get("canonical_url") or "").strip()
        host = _host_key(url)
        if host and by_host.get(host, 0) >= per_host_limit:
            summary["skipped"] += 1
            crawl = {"status": "skipped", "reason": "per-host crawl limit reached", "observed": {}}
        else:
            by_host[host] = by_host.get(host, 0) + 1
            summary["attempted"] += 1
            crawl = _crawl_source(
                url=url,
                accepted_hash=str(source.get("accepted_hash") or ""),
                enrichment=source.get("enrichment") if isinstance(source.get("enrichment"), Mapping) else {},
                env=env,
                fetcher=fetcher,
            )
        status = str(crawl.get("status") or "")
        if status in summary:
            summary[status] += 1
        if status in {"unchanged", "changed"}:
            summary["fetched"] += 1
        if status in {"removed", "tombstoned", "changed", "unchanged"} and isinstance(crawl.get("observed"), Mapping):
            observed[str(source.get("source_ref_id") or "")] = dict(crawl.get("observed") or {})
        _record_crawl_observation(
            conn,
            source_ref_kind=str(source.get("source_ref_kind") or ""),
            source_ref_id=str(source.get("source_ref_id") or ""),
            source_uid=str(source.get("source_uid") or ""),
            specialist_uid=str(source.get("specialist_uid") or ""),
            trainee=trainee,
            lane_id=str(source.get("lane_id") or ""),
            canonical_url=url,
            crawl=crawl,
            observed_at=observed_at,
        )
        if source.get("source_ref_kind") == "central_source":
            _update_central_source_crawl_state(
                conn,
                source_uid=str(source.get("source_uid") or ""),
                crawl=crawl,
                observed_at=observed_at,
            )
        elif source.get("source_ref_kind") == "trainee_proposal":
            _update_proposal_crawl_state(
                conn,
                proposal_id=str(source.get("source_ref_id") or ""),
                crawl=crawl,
                observed_at=observed_at,
            )
    return observed, summary


def _academy_week_key(value: str) -> str:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except Exception:
        return str(value or "")[:10] or "unknown-week"


def _rotation_setting_key(specialist_uid: str) -> str:
    return "academy.forward_maintenance.rotation." + hashlib.sha256(
        str(specialist_uid or "").encode("utf-8")
    ).hexdigest()[:20]


def _read_rotation_state(conn: sqlite3.Connection, specialist_uid: str) -> dict[str, Any]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (_rotation_setting_key(specialist_uid),)).fetchone()
    if row is None:
        return {}
    state = _loads(row["value"], default={})
    return state if isinstance(state, dict) else {}


def _write_rotation_state(
    conn: sqlite3.Connection,
    *,
    specialist_uid: str,
    trainee_id: str,
    week_key: str,
    updated_at: str,
) -> None:
    payload = {
        "specialist_uid": specialist_uid,
        "last_trainee_id": trainee_id,
        "last_week": week_key,
        "updated_at": updated_at,
    }
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (_rotation_setting_key(specialist_uid), _dumps(payload), updated_at),
    )


def _rotating_forward_maintenance_candidates(
    conn: sqlite3.Connection,
    graduates: list[dict[str, Any]],
    *,
    created_at: str,
) -> tuple[list[dict[str, Any]], int, dict[str, str]]:
    """Pick one subscribed trainee per shared specialist for this weekly turn."""

    by_id = {str(item.get("trainee_id") or ""): item for item in graduates if str(item.get("trainee_id") or "")}
    if not by_id:
        return [], 0, {}
    placeholders = ",".join("?" for _ in by_id)
    rows = conn.execute(
        f"""
        SELECT specialist_uid, trainee_id
        FROM academy_specialist_subscriptions
        WHERE trainee_id IN ({placeholders})
        ORDER BY specialist_uid, trainee_id
        """,
        tuple(by_id.keys()),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    grouped_trainees: set[str] = set()
    for row in rows:
        specialist_uid = str(row["specialist_uid"] or "")
        trainee_id = str(row["trainee_id"] or "")
        if not specialist_uid or trainee_id not in by_id:
            continue
        grouped.setdefault(specialist_uid, []).append(trainee_id)
        grouped_trainees.add(trainee_id)

    selected_ids: set[str] = set()
    rotation_for: dict[str, str] = {}
    deferred = 0
    week_key = _academy_week_key(created_at)
    for specialist_uid, trainee_ids in grouped.items():
        ordered = sorted(set(trainee_ids))
        if not ordered:
            continue
        state = _read_rotation_state(conn, specialist_uid)
        last = str(state.get("last_trainee_id") or "")
        if last in ordered:
            chosen = ordered[(ordered.index(last) + 1) % len(ordered)]
        else:
            chosen = ordered[0]
        _write_rotation_state(
            conn,
            specialist_uid=specialist_uid,
            trainee_id=chosen,
            week_key=week_key,
            updated_at=created_at,
        )
        selected_ids.add(chosen)
        rotation_for[chosen] = specialist_uid
        deferred += max(0, len(ordered) - 1)

    for trainee_id in by_id:
        if trainee_id not in grouped_trainees:
            selected_ids.add(trainee_id)

    selected = [item for item in graduates if str(item.get("trainee_id") or "") in selected_ids]
    return selected, deferred, rotation_for


def run_academy_forward_maintenance(
    conn: sqlite3.Connection,
    *,
    env: Mapping[str, str] | None = None,
    limit: int = DEFAULT_FORWARD_MAINTENANCE_LIMIT,
    created_at: str | None = None,
    fetcher: _CrawlFetcher | None = None,
) -> dict[str, Any]:
    """Run the weekly live-crawl continuing-education review for graduates.

    Returns a redacted summary. ``limit`` bounds the number of trainees handled
    in a single run; if more are eligible the overflow count is reported (never
    silently dropped). Public-lane crawling is autonomous and digest-only; Agent
    SOUL/skill/vault writes remain behind the separate Academy apply gate.
    """
    clean_env = dict(env or {})
    now = str(created_at or utc_now_iso())
    seed_default_academy_programs(conn)
    graduates = [t for t in list_academy_trainees(conn, status="graduated") if t.get("forward_maintained")]
    eligible = len(graduates)
    rotation_candidates, rotation_deferred, rotation_for = _rotating_forward_maintenance_candidates(
        conn,
        graduates,
        created_at=now,
    )
    # Explicit cap semantics: limit <= 0 means "process all eligible" (unbounded);
    # a positive limit caps this run and reports the remainder as deferred.
    n = int(limit)
    capped = len(rotation_candidates) if n <= 0 else min(n, len(rotation_candidates))
    batch = rotation_candidates[:capped]
    deferred = rotation_deferred + (len(rotation_candidates) - len(batch))

    reviews: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    notify_targets: list[dict[str, str]] = []
    crawl_totals = {
        "enabled": _env_bool(clean_env, "ARCLINK_ACADEMY_CE_LIVE_CRAWL", default=True),
        "attempted": 0,
        "fetched": 0,
        "unchanged": 0,
        "changed": 0,
        "blocked": 0,
        "failed": 0,
        "removed": 0,
        "tombstoned": 0,
        "skipped": 0,
    }
    for trainee in batch:
        trainee_id = str(trainee.get("trainee_id") or "")
        try:
            observed_sources, crawl_summary = _live_crawl_observed_sources(
                conn,
                trainee=trainee,
                specialist_uid=rotation_for.get(trainee_id, ""),
                env=clean_env,
                fetcher=fetcher,
                observed_at=now,
            )
            for key, value in crawl_summary.items():
                if key == "enabled":
                    crawl_totals["enabled"] = bool(crawl_totals["enabled"]) or bool(value)
                elif key in crawl_totals:
                    crawl_totals[key] = int(crawl_totals[key]) + int(value or 0)
            plan = academy_continuing_education(
                conn,
                trainee_id=trainee_id,
                observed_sources=observed_sources,
                created_at=now,
            )
        except Exception as exc:  # noqa: BLE001 - one bad trainee must not abort the run
            errors.append({"trainee_id": trainee_id, "error": str(exc)[:200]})
            continue
        review = {
            "trainee_id": trainee_id,
            "user_id": str(trainee.get("user_id") or ""),
            "deployment_id": str(trainee.get("deployment_id") or ""),
            "name": str(trainee.get("name") or ""),
            "manifest_id": str(plan.get("manifest_id") or ""),
            "status": str(plan.get("status") or ""),
            "agent_update_status": str(plan.get("agent_update_status") or ""),
            "review_needed_count": int(plan.get("review_needed_count") or 0),
            "blocked_source_count": int(plan.get("blocked_source_count") or 0),
            "next_review_at": str(plan.get("next_review_at") or ""),
            "proof_gates": list(plan.get("proof_gates") or []),
            "rotation_specialist_uid": rotation_for.get(trainee_id, ""),
            "rotation_week": _academy_week_key(now),
            "live_crawl": crawl_summary,
        }
        reviews.append(review)
        subject_id = review["deployment_id"] or trainee_id
        subject_kind = "deployment" if review["deployment_id"] else "user"
        append_arclink_event(
            conn,
            subject_kind=subject_kind,
            subject_id=subject_id,
            event_type="academy_forward_maintenance_recorded",
            metadata={**review, "no_write": True, "writes_enabled": False, "live_crawl_enabled": crawl_summary.get("enabled")},
            commit=False,
        )
        append_arclink_audit(
            conn,
            action="academy_forward_maintenance_recorded",
            actor_id="system:academy_scheduler",
            target_kind=subject_kind,
            target_id=subject_id,
            reason="Weekly Academy continuing-education review recorded; no Agent write was performed",
            metadata={**review, "no_write": True, "writes_enabled": False, "live_crawl_enabled": crawl_summary.get("enabled")},
            commit=False,
        )
        if review["user_id"]:
            notify_targets.append(review)

    # "Living academy": refresh the central specialist capsules each week (derived
    # notes only; the live LLM Trainer enrichment + Agent-side observed-source sweep
    # layer on top behind PG-PROVIDER) and bump only when content actually changed.
    capsules_refreshed = 0
    trainer_reviews = 0
    live_trainer_reviews = 0
    live_trainer_authorized = academy_trainer_live_authorized_from_env(clean_env)
    live_trainer_client = academy_trainer_client_from_env(clean_env) if live_trainer_authorized else None
    specialist_uids = [
        str(row["specialist_uid"])
        for row in conn.execute(
            "SELECT DISTINCT specialist_uid FROM academy_corpus_specialists "
            "WHERE status = 'active' AND share_scope = 'redacted_public'"
        ).fetchall()
    ]
    for specialist_uid in specialist_uids:
        try:
            if live_trainer_authorized:
                result = run_academy_trainer_review(
                    conn,
                    specialist_uid=specialist_uid,
                    client=live_trainer_client,
                    live_authorized=True,
                    actor="system:academy_scheduler",
                    commit=False,
                )
                trainer_reviews += 1
                if result.get("live"):
                    live_trainer_reviews += 1
            else:
                result = refresh_specialist_capsule(
                    conn, specialist_uid=specialist_uid, actor="system:academy_scheduler",
                    only_if_changed=True, commit=False,
                )
            if result.get("changed"):
                capsules_refreshed += 1
        except Exception as exc:  # noqa: BLE001 - one bad specialist must not abort the run
            errors.append({"specialist_uid": specialist_uid, "error": str(exc)[:200]})
    conn.commit()

    # Notify each Captain of their weekly review (vision: "notifies the Captain").
    # queue_notification commits per row, so it runs AFTER the batch commit above.
    notified = 0
    for review in notify_targets:
        try:
            label = review["name"] or review["deployment_id"] or review["trainee_id"]
            queue_notification(
                conn,
                target_kind="user",
                target_id=review["user_id"],
                channel_kind="academy",
                message=(
                    f"Academy weekly review for {label}: "
                    f"{review['review_needed_count']} source(s) to review, "
                    f"{review['blocked_source_count']} blocked. Next review {review['next_review_at'] or 'TBD'}."
                ),
                extra={
                    "kind": "academy_forward_maintenance",
                    "trainee_id": review["trainee_id"],
                    "deployment_id": review["deployment_id"],
                    "rotation_specialist_uid": review.get("rotation_specialist_uid", ""),
                    "rotation_week": review.get("rotation_week", ""),
                    "review_needed_count": review["review_needed_count"],
                    "blocked_source_count": review["blocked_source_count"],
                    "agent_update_status": review["agent_update_status"],
                    "next_review_at": review["next_review_at"],
                    "live_crawl": review.get("live_crawl") or {},
                },
            )
            notified += 1
        except Exception as exc:  # noqa: BLE001 - notification failure must not abort the run
            errors.append({"trainee_id": review.get("trainee_id", ""), "error": f"notify: {str(exc)[:160]}"})
    return {
        "status": "ok",
        "eligible": eligible,
        "processed": len(reviews),
        "deferred_to_next_run": deferred,
        "shared_rotation_deferred": rotation_deferred,
        "errors": errors,
        "reviews": reviews,
        "captains_notified": notified,
        "central_capsules_refreshed": capsules_refreshed,
        "trainer_reviews": trainer_reviews,
        "live_trainer_reviews": live_trainer_reviews,
        "live_crawl": crawl_totals,
        "no_write": True,
        "writes_enabled": False,
        "proof_gates": ["PG-PROVIDER", "PG-HERMES"],
    }


def _db_connect(path: str) -> sqlite3.Connection:
    db_path = str(path or os.environ.get("ARCLINK_DB_PATH") or "/home/arclink/arclink/arclink-priv/state/arclink-control.sqlite3")
    cfg = Config.from_env()
    cfg = replace(cfg, db_path=Path(db_path).resolve(), state_dir=Path(db_path).resolve().parent)
    return connect_db(cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the weekly ArcLink Academy forward-maintenance review.")
    parser.add_argument("--db", default=os.environ.get("ARCLINK_DB_PATH", ""))
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("ARCLINK_ACADEMY_CE_LIMIT", str(DEFAULT_FORWARD_MAINTENANCE_LIMIT))),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    with _db_connect(args.db) as conn:
        payload = run_academy_forward_maintenance(conn, env=os.environ, limit=args.limit)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Academy forward-maintenance: processed {payload['processed']}/{payload['eligible']} graduate(s), "
            f"deferred {payload['deferred_to_next_run']}, errors {len(payload['errors'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
