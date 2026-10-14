"""Small, provider-agnostic transport for OpenAI-compatible endpoints.

This module deliberately stops at the transport boundary.  It does not parse a
model response into Onto4 interpretations or produce an Onto4 verdict.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit


class EndpointAuthKind(str, Enum):
    """Authentication modes supported by the first transport slice."""

    None_ = "none"
    Bearer = "bearer"


@dataclass(frozen=True)
class ProviderProfile:
    """Non-secret connection profile for an OpenAI-compatible endpoint.

    Credentials are intentionally not a field on this object.  A runtime token
    is supplied to :class:`OpenAICompatibleClient` for one process/session and
    is never part of a serializable provider profile.
    """

    base_url: str
    model: str
    auth: EndpointAuthKind = EndpointAuthKind.None_
    protocol: str = "openai-compatible"
    timeout_seconds: float = 30.0
    max_response_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if self.protocol != "openai-compatible":
            raise ValueError("Only the openai-compatible protocol is supported.")
        normalized = self.base_url.rstrip("/")
        try:
            auth = EndpointAuthKind(self.auth)
        except ValueError as exc:
            raise ValueError("auth must be none or bearer.") from exc
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL.")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain embedded credentials.")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query or fragment.")
        if not self.model.strip():
            raise ValueError("model must not be empty.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive.")
        object.__setattr__(self, "base_url", normalized)
        object.__setattr__(self, "model", self.model.strip())
        object.__setattr__(self, "auth", auth)


class ProviderTransportError(RuntimeError):
    """Raised when an endpoint cannot produce a valid JSON transport response."""


UrlOpen = Callable[..., Any]


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Make endpoint redirects visible instead of forwarding credentials."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _urlopen_without_redirects(request: urllib.request.Request, *, timeout: float) -> Any:
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


class OpenAICompatibleClient:
    """Issue bounded requests to an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        profile: ProviderProfile,
        *,
        bearer_token: str | None = None,
        urlopen: UrlOpen | None = None,
    ) -> None:
        if profile.auth is EndpointAuthKind.Bearer and not bearer_token:
            raise ValueError("A bearer token is required by this provider profile.")
        if profile.auth is EndpointAuthKind.None_ and bearer_token is not None:
            raise ValueError("A bearer token cannot be supplied for unauthenticated profile.")
        self.profile = profile
        self._bearer_token = bearer_token
        self._urlopen = _urlopen_without_redirects if urlopen is None else urlopen

    def list_models(self) -> tuple[str, ...]:
        """Run a non-generative connection check against ``GET /models``."""

        payload = self._request("GET", "/models")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderTransportError("The models response must contain a data list.")
        model_ids: list[str] = []
        for item in data:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                raise ProviderTransportError("Every model entry must contain a string id.")
            model_ids.append(item["id"])
        return tuple(model_ids)

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Return the raw validated JSON envelope from ``chat/completions``."""

        if not messages:
            raise ValueError("messages must not be empty.")
        normalized_messages: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, Mapping):
                raise ValueError("Every message must be a mapping.")
            role = message.get("role")
            content = message.get("content")
            if not isinstance(role, str) or not role:
                raise ValueError("Every message must have a non-empty role.")
            if not isinstance(content, str):
                raise ValueError("Every message must have string content.")
            normalized_messages.append({"role": role, "content": content})
        body: dict[str, Any] = {"model": self.profile.model, "messages": normalized_messages}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = dict(response_format)
        return self._request("POST", "/chat/completions", body)

    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        url = f"{self.profile.base_url}{path}"
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._urlopen(request, timeout=self.profile.timeout_seconds) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        content_length_value = int(content_length)
                    except (TypeError, ValueError) as exc:
                        raise ProviderTransportError(
                            "Provider response has an invalid Content-Length."
                        ) from exc
                    if content_length_value > self.profile.max_response_bytes:
                        raise ProviderTransportError(
                            "Provider response exceeds the configured size limit."
                        )
                raw = response.read(self.profile.max_response_bytes + 1)
        except ProviderTransportError:
            raise
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code <= 399:
                raise ProviderTransportError(
                    "Provider endpoint redirects are not followed."
                ) from exc
            raise ProviderTransportError(
                f"Provider endpoint returned HTTP {exc.code}."
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderTransportError("Provider endpoint request failed.") from exc
        if len(raw) > self.profile.max_response_bytes:
            raise ProviderTransportError("Provider response exceeds the configured size limit.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderTransportError("Provider response is not valid UTF-8 JSON.") from exc
        if not isinstance(payload, Mapping):
            raise ProviderTransportError("Provider response must be a JSON object.")
        return payload


__all__ = [
    "EndpointAuthKind",
    "OpenAICompatibleClient",
    "ProviderProfile",
    "ProviderTransportError",
]
