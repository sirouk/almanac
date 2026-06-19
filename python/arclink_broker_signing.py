#!/usr/bin/env python3
"""Shared HMAC request-signing for the GAP-019 trusted-host brokers/helpers.

This factors out the proven scheme that the operator-upgrade broker already
shipped (``arclink_operator_upgrade_broker._is_authorized`` /
``_record_nonce_if_unseen``):

  * a bearer broker token compared with ``hmac.compare_digest`` (timing-safe),
  * an HMAC-SHA256 signature over ``timestamp\\nnonce\\nsha256(body)`` keyed by
    the broker token, with a 300s timestamp window,
  * a nonce format check plus a bounded PERSISTENT per-service nonce cache so a
    captured request cannot be replayed, and
  * fail-closed behaviour when the nonce store cannot be loaded/persisted.

LOCK-STEP-SAFE ACCEPT-BOTH ROLLOUT
----------------------------------
Enforcement is gated on ``ARCLINK_BROKER_REQUIRE_SIGNED`` (default OFF). The
signature is purely ADDITIVE while the flag is off:

  * clients ALWAYS attach signature headers (``sign_broker_request``),
  * brokers verify-when-present for nonce/replay telemetry, but
  * a valid bare token ALWAYS admits — a missing or invalid signature never
    rejects an otherwise-valid bare-token request.

That makes deploying the new code a pure no-op for admission across version
skew (legacy client + new broker, new client + legacy-style request). Only a
SEPARATE future flip of ``ARCLINK_BROKER_REQUIRE_SIGNED`` to on enforces
signed+nonce and rejects bare/replayed requests.

Callers must read the request body BEFORE authenticating so the body-hash HMAC
covers the exact bytes that will be parsed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping


REQUEST_SIGNATURE_TTL_SECONDS = 300
MAX_SEEN_SIGNATURE_NONCES = 4096
NONCE_RE = re.compile(r"[A-Za-z0-9_.~+/=-]{16,160}")

# Canonical signature-header suffixes. Each broker keeps its own bearer-token
# header (legacy, unchanged) and appends these three additive headers.
TIMESTAMP_HEADER = "X-ArcLink-Broker-Timestamp"
NONCE_HEADER = "X-ArcLink-Broker-Nonce"
SIGNATURE_HEADER = "X-ArcLink-Broker-Signature"


def require_signed_enforced() -> bool:
    """True only when ARCLINK_BROKER_REQUIRE_SIGNED is explicitly enabled.

    Default OFF: the legacy bare-token compare still governs admission and the
    signature is additive telemetry only. A separate future flip to on enforces
    signed+nonce and rejects bare/replayed requests.
    """
    value = str(os.environ.get("ARCLINK_BROKER_REQUIRE_SIGNED") or "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}


def _body_hash(body_bytes: bytes) -> str:
    return hashlib.sha256(body_bytes).hexdigest()


def _signature(token: str, *, timestamp: str, nonce: str, body_bytes: bytes) -> str:
    body_hash = _body_hash(body_bytes)
    return hmac.new(
        token.encode("utf-8"),
        f"{timestamp}\n{nonce}\n{body_hash}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_broker_request(
    token: str,
    body_bytes: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build the additive signature headers for a broker request.

    Clients send these on EVERY request regardless of the require-signed flag so
    the deploy is lock-step-safe: a new client talking to a legacy broker is a
    no-op (the broker ignores unknown headers), and a new broker only enforces
    them once ARCLINK_BROKER_REQUIRE_SIGNED is flipped on.
    """
    clean_token = str(token or "").strip()
    if not clean_token:
        raise ValueError("broker request signing requires a non-empty token")
    ts = str(int(time.time()) if timestamp is None else int(timestamp))
    sig_nonce = nonce if nonce is not None else secrets.token_urlsafe(18)
    signature = _signature(clean_token, timestamp=ts, nonce=sig_nonce, body_bytes=body_bytes)
    return {
        TIMESTAMP_HEADER: ts,
        NONCE_HEADER: sig_nonce,
        SIGNATURE_HEADER: signature,
    }


class NonceStore:
    """Bounded, persistent per-service replay-nonce cache.

    This generalizes the operator-upgrade broker's ``_record_nonce_if_unseen``
    persistent store. It keeps an in-memory dict (process lifetime) backed by a
    per-service JSON file so replay protection survives broker restarts, prunes
    entries older than the TTL, bounds the cache size, and fails CLOSED if it
    cannot load or persist (so a write failure can never silently disable
    replay protection while require-signed is enforced).
    """

    def __init__(
        self,
        path_factory: Callable[[], Path | None],
        *,
        seen: dict[str, float] | None = None,
        max_entries: Callable[[], int] | None = None,
        loaded_from_get: Callable[[], str] | None = None,
        loaded_from_set: Callable[[str], None] | None = None,
    ) -> None:
        self._path_factory = path_factory
        # ``seen`` may be an externally-owned dict so a host module can expose the
        # live cache (e.g. for tests that clear/inspect it); defaults to private.
        self._seen: dict[str, float] = seen if seen is not None else {}
        self._lock = threading.Lock()
        self._loaded_from_local = ""
        # ``max_entries`` lets a host module override the cap at runtime (the
        # operator-upgrade broker tests shrink it); defaults to the module cap.
        self._max_entries = max_entries or (lambda: MAX_SEEN_SIGNATURE_NONCES)
        # ``loaded_from_*`` let a host module own the "loaded from" marker so a
        # test can reset it (simulating a broker restart) and have the store pick
        # the reset up. Defaults to a private attribute.
        self._loaded_from_get = loaded_from_get
        self._loaded_from_set = loaded_from_set

    @property
    def _loaded_from(self) -> str:
        if self._loaded_from_get is not None:
            return str(self._loaded_from_get() or "")
        return self._loaded_from_local

    def _set_loaded_from(self, value: str) -> None:
        self._loaded_from_local = value
        if self._loaded_from_set is not None:
            self._loaded_from_set(value)

    def _path(self) -> Path | None:
        try:
            return self._path_factory()
        except (ValueError, OSError):
            return None

    def _prune_locked(self, cutoff: float) -> None:
        for key, observed in list(self._seen.items()):
            if observed < cutoff:
                self._seen.pop(key, None)

    def _load_locked(self, path: Path | None, now: float) -> bool:
        if path is None:
            return True
        path_key = str(path)
        if self._loaded_from == path_key:
            return True
        cutoff = now - REQUEST_SIGNATURE_TTL_SECONDS
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        for key, observed in data.items():
            nonce = str(key or "")
            try:
                observed_at = float(observed)
            except (TypeError, ValueError):
                continue
            if observed_at >= cutoff and NONCE_RE.fullmatch(nonce):
                self._seen[nonce] = observed_at
        self._set_loaded_from(path_key)
        return True

    def _persist_locked(self, path: Path | None) -> bool:
        if path is None:
            return True
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(self._seen, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            return False
        return True

    def record_if_unseen(self, nonce: str, now: float | None = None) -> bool:
        observed_now = time.time() if now is None else now
        cutoff = observed_now - REQUEST_SIGNATURE_TTL_SECONDS
        with self._lock:
            path = self._path()
            if not self._load_locked(path, observed_now):
                return False
            self._prune_locked(cutoff)
            if nonce in self._seen:
                return False
            while len(self._seen) >= self._max_entries():
                oldest = min(self._seen, key=self._seen.get)
                self._seen.pop(oldest, None)
            self._seen[nonce] = observed_now
            if not self._persist_locked(path):
                self._seen.pop(nonce, None)
                return False
            return True


def _header_value(headers: Mapping[str, Any] | Any, name: str) -> str:
    getter = getattr(headers, "get", None)
    if callable(getter):
        return str(getter(name) or "").strip()
    return ""


def _signature_present(headers: Mapping[str, Any] | Any) -> bool:
    return bool(
        _header_value(headers, TIMESTAMP_HEADER)
        and _header_value(headers, NONCE_HEADER)
        and _header_value(headers, SIGNATURE_HEADER)
    )


def _verify_signature(
    token: str,
    headers: Mapping[str, Any] | Any,
    body_bytes: bytes,
    nonce_store: NonceStore | None,
) -> tuple[bool, str]:
    timestamp_raw = _header_value(headers, TIMESTAMP_HEADER)
    nonce = _header_value(headers, NONCE_HEADER)
    supplied_signature = _header_value(headers, SIGNATURE_HEADER)
    if not (timestamp_raw and nonce and supplied_signature):
        return False, "signature_missing"
    try:
        timestamp = int(timestamp_raw)
    except (TypeError, ValueError):
        return False, "timestamp_invalid"
    now = time.time()
    if abs(now - timestamp) > REQUEST_SIGNATURE_TTL_SECONDS:
        return False, "timestamp_expired"
    if not NONCE_RE.fullmatch(nonce):
        return False, "nonce_invalid"
    expected_signature = _signature(
        token, timestamp=str(timestamp), nonce=nonce, body_bytes=body_bytes
    )
    if not hmac.compare_digest(expected_signature, supplied_signature):
        return False, "signature_mismatch"
    if nonce_store is not None and not nonce_store.record_if_unseen(nonce, now):
        return False, "nonce_replayed"
    return True, "ok"


def verify_broker_request(
    token: str,
    headers: Mapping[str, Any] | Any,
    body_bytes: bytes,
    nonce_store: NonceStore | None,
    *,
    bearer_header: str,
    require_signed: bool | None = None,
) -> tuple[bool, str]:
    """Authenticate a broker request, lock-step-safe accept-both.

    Returns ``(ok, reason)``.

    Admission model:
      * The bearer token (``bearer_header``) is ALWAYS required and compared
        with ``hmac.compare_digest``. A missing/blank/mismatched bearer token is
        always rejected.
      * When ``require_signed`` is OFF (default), a valid bearer token ADMITS
        regardless of the signature. If signature headers are present they are
        still verified to feed the replay nonce store (telemetry), but a
        missing/invalid signature does NOT reject a valid-bare-token request.
      * When ``require_signed`` is ON, a valid signature (fresh timestamp, valid
        nonce, body-hash HMAC match, unseen nonce) is additionally required.

    ``body_bytes`` MUST be the exact bytes the caller read before authenticating
    so the body-hash HMAC covers them (and, with require-signed on, defeats an
    on-net body/field substitution such as a swapped gateway ``bot_token``).
    """
    enforce = require_signed_enforced() if require_signed is None else bool(require_signed)
    expected = str(token or "").strip()
    supplied = _header_value(headers, bearer_header)
    bearer_ok = bool(expected and supplied and hmac.compare_digest(expected, supplied))
    if not bearer_ok:
        return False, "bearer_token_invalid"

    if not enforce:
        # Accept-both: bare token admits. Verify the signature opportunistically
        # only to record the nonce for replay telemetry; never reject on it.
        if expected and _signature_present(headers):
            _verify_signature(expected, headers, body_bytes, nonce_store)
        return True, "bare_token_admitted"

    return _verify_signature(expected, headers, body_bytes, nonce_store)
