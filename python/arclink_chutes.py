#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib import request as urlrequest

from arclink_product import chutes_base_url, chutes_default_model


REQUIRED_CHUTES_CAPABILITIES = ("tools", "reasoning", "structured_outputs")


@dataclass(frozen=True)
class ChutesModel:
    model_id: str
    supports_tools: bool
    supports_reasoning: bool
    supports_structured_outputs: bool
    confidential_compute: bool
    raw: Mapping[str, Any]

    def missing_capabilities(self, *, require_confidential_compute: bool = True) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.supports_tools:
            missing.append("tools")
        if not self.supports_reasoning:
            missing.append("reasoning")
        if not self.supports_structured_outputs:
            missing.append("structured_outputs")
        if require_confidential_compute and not self.confidential_compute:
            missing.append("confidential_compute")
        return tuple(missing)


class ChutesCatalogError(RuntimeError):
    pass


class ChutesHttpClient(Protocol):
    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        ...


class UrlLibChutesHttpClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_json(self, path: str, *, headers: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        request = urlrequest.Request(self.base_url + path, headers=dict(headers or {}))
        with urlrequest.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ChutesCatalogError("Chutes catalog response was not an object")
        return payload


class ChutesCatalogClient:
    def __init__(self, http_client: ChutesHttpClient | None = None, *, base_url: str = "") -> None:
        self.http_client = http_client or UrlLibChutesHttpClient(base_url or chutes_base_url())

    def list_models(self, *, api_key: str = "", auth_strategy: str = "x-api-key") -> dict[str, ChutesModel]:
        headers: dict[str, str] = {}
        if api_key:
            if auth_strategy == "x-api-key":
                headers["X-API-Key"] = api_key
            elif auth_strategy == "bearer":
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                raise ChutesCatalogError(f"unsupported Chutes auth strategy: {auth_strategy}")
        payload = self.http_client.get_json("/models", headers=headers)
        return parse_chutes_models(payload)


def _bool_from_model(model: Mapping[str, Any], *keys: str) -> bool:
    capabilities = model.get("capabilities")
    if isinstance(capabilities, Mapping):
        for key in keys:
            if bool(capabilities.get(key)):
                return True
    for key in keys:
        if bool(model.get(key)):
            return True
    return False


def parse_chutes_models(payload: Mapping[str, Any]) -> dict[str, ChutesModel]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ChutesCatalogError("Chutes catalog response is missing data[]")
    models: dict[str, ChutesModel] = {}
    for item in data:
        if not isinstance(item, Mapping):
            continue
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        models[model_id] = ChutesModel(
            model_id=model_id,
            supports_tools=_bool_from_model(item, "tools", "tool_calls", "function_calling"),
            supports_reasoning=_bool_from_model(item, "reasoning", "thinking"),
            supports_structured_outputs=_bool_from_model(item, "structured_outputs", "json_schema"),
            confidential_compute=_bool_from_model(item, "confidential_compute", "tee", "trusted_execution"),
            raw=dict(item),
        )
    return models


def validate_default_chutes_model(
    models: Mapping[str, ChutesModel],
    *,
    env: Mapping[str, str] | None = None,
    require_confidential_compute: bool = True,
) -> ChutesModel:
    model_id = chutes_default_model(env)
    model = models.get(model_id)
    if model is None:
        raise ChutesCatalogError(f"configured default Chutes model is not in catalog: {model_id}")
    missing = model.missing_capabilities(require_confidential_compute=require_confidential_compute)
    if missing:
        raise ChutesCatalogError(f"configured default Chutes model lacks required capabilities: {', '.join(missing)}")
    return model


class FakeChutesKeyManager:
    def __init__(self) -> None:
        self.keys: dict[str, dict[str, str]] = {}

    @staticmethod
    def _clean_deployment_id(deployment_id: str) -> str:
        clean_id = str(deployment_id or "").strip()
        if not clean_id:
            raise ValueError("deployment_id is required")
        return clean_id

    @staticmethod
    def _key_id_for(deployment_id: str) -> str:
        return f"fake_chutes_key_{deployment_id}"

    def create_key(self, deployment_id: str, *, label: str = "") -> dict[str, str]:
        clean_id = self._clean_deployment_id(deployment_id)
        key_id = self._key_id_for(clean_id)
        secret_ref = f"secret://arclink/chutes/{clean_id}"
        record = {"key_id": key_id, "deployment_id": clean_id, "label": label, "secret_ref": secret_ref, "status": "active"}
        self.keys[key_id] = record
        return dict(record)

    def rotate_key(self, deployment_id: str, *, label: str = "") -> dict[str, str]:
        clean_id = self._clean_deployment_id(deployment_id)
        old_key_id = self._key_id_for(clean_id)
        if old_key_id in self.keys:
            self.keys[old_key_id]["status"] = "rotated"
        return self.create_key(clean_id, label=label or "rotated")

    def revoke_key(self, key_id: str) -> dict[str, str]:
        clean_id = str(key_id or "").strip()
        if clean_id not in self.keys:
            raise KeyError(clean_id)
        self.keys[clean_id]["status"] = "revoked"
        return dict(self.keys[clean_id])

    def key_state(self, deployment_id: str) -> dict[str, str] | None:
        clean_id = self._clean_deployment_id(deployment_id)
        key_id = self._key_id_for(clean_id)
        return dict(self.keys[key_id]) if key_id in self.keys else None


class FakeChutesInferenceClient:
    """Fake inference client for smoke testing without live credentials."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        api_key: str = "",
    ) -> dict[str, Any]:
        record = {"model": model, "messages": messages, "api_key_provided": bool(api_key)}
        self.calls.append(record)
        if self._fail:
            raise ChutesCatalogError(f"fake inference failure for model {model}")
        return {
            "id": f"fake_cmpl_{len(self.calls)}",
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": "Hello from fake inference."}}],
        }
