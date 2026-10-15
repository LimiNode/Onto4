import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from onto4.providers import (
    EndpointAuthKind,
    OpenAICompatibleClient,
    ProviderProfile,
    ProviderTransportError,
)


class FakeResponse:
    def __init__(self, payload, *, content_length=None):
        self._payload = json.dumps(payload).encode("utf-8")
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self._payload if size < 0 else self._payload[:size]


def test_provider_profile_is_non_secret_and_normalizes_endpoint():
    profile = ProviderProfile(
        base_url="http://127.0.0.1:8080/v1/",
        model="  bonsai  ",
        auth="bearer",
    )

    assert profile.base_url == "http://127.0.0.1:8080/v1"
    assert profile.model == "bonsai"
    assert profile.auth is EndpointAuthKind.Bearer
    assert "secret" not in repr(profile).lower()
    assert "bearer_token" not in repr(profile).lower()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "", "model": "model"},
        {"base_url": "ftp://example.test/v1", "model": "model"},
        {"base_url": "http://user:pass@example.test/v1", "model": "model"},
        {"base_url": "http://example.test/v1?secret=x", "model": "model"},
        {"base_url": "http://example.test/v1", "model": ""},
        {"base_url": "http://example.test/v1", "model": "model", "timeout_seconds": 0},
        {"base_url": "http://example.test/v1", "model": "model", "max_output_tokens": 0},
        {"base_url": "http://example.test/v1", "model": "model", "temperature": -0.1},
        {"base_url": "http://example.test/v1", "model": "model", "temperature": "cold"},
        {"base_url": "http://example.test/v1", "model": "model", "max_response_bytes": 0},
    ],
)
def test_provider_profile_rejects_invalid_connection_schema(kwargs):
    with pytest.raises(ValueError):
        ProviderProfile(**kwargs)


def test_bearer_token_is_required_but_not_part_of_profile():
    profile = ProviderProfile(
        base_url="http://example.test/v1",
        model="model",
        auth=EndpointAuthKind.Bearer,
    )

    with pytest.raises(ValueError, match="bearer token"):
        OpenAICompatibleClient(profile)


def test_list_models_sends_no_token_for_none_authentication():
    captured = {}

    def urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"data": [{"id": "bonsai"}]})

    client = OpenAICompatibleClient(
        ProviderProfile(base_url="http://example.test/v1", model="bonsai"),
        urlopen=urlopen,
    )

    assert client.list_models() == ("bonsai",)
    assert captured["request"].full_url == "http://example.test/v1/models"
    assert captured["request"].get_header("Authorization") is None
    assert captured["timeout"] == 30.0


def test_complete_sends_bearer_token_and_returns_raw_json_envelope():
    captured = {}

    def urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse({"id": "completion", "choices": []})

    client = OpenAICompatibleClient(
        ProviderProfile(
            base_url="http://example.test/v1",
            model="bonsai",
            auth=EndpointAuthKind.Bearer,
        ),
        bearer_token="secret",
        urlopen=urlopen,
    )

    result = client.complete(
        [{"role": "user", "content": "Hello"}],
        temperature=0.2,
        max_tokens=32,
        response_format={"type": "json_object"},
    )

    request_body = json.loads(captured["request"].data.decode("utf-8"))
    assert result == {"id": "completion", "choices": []}
    assert captured["request"].full_url == "http://example.test/v1/chat/completions"
    assert captured["request"].get_header("Authorization") == "Bearer secret"
    assert request_body == {
        "model": "bonsai",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.2,
        "max_tokens": 32,
        "response_format": {"type": "json_object"},
    }


def test_complete_applies_profile_output_token_bound_when_call_omits_one():
    captured = {}

    def urlopen(request, *, timeout):
        captured["request"] = request
        return FakeResponse({"choices": []})

    client = OpenAICompatibleClient(
        ProviderProfile(
            base_url="http://example.test/v1",
            model="bonsai",
            max_output_tokens=321,
        ),
        urlopen=urlopen,
    )

    client.complete([{"role": "user", "content": "Hello"}])

    request_body = json.loads(captured["request"].data.decode("utf-8"))
    assert request_body["max_tokens"] == 321
    assert request_body["temperature"] == 0.0
    assert "chat_template_kwargs" not in request_body


def test_complete_can_disable_provider_side_thinking_explicitly():
    captured = {}

    def urlopen(request, *, timeout):
        captured["request"] = request
        return FakeResponse({"choices": []})

    client = OpenAICompatibleClient(
        ProviderProfile(
            base_url="http://example.test/v1",
            model="bonsai",
            disable_thinking=True,
        ),
        urlopen=urlopen,
    )

    client.complete([{"role": "user", "content": "Hello"}])

    request_body = json.loads(captured["request"].data.decode("utf-8"))
    assert request_body["chat_template_kwargs"] == {"enable_thinking": False}


def test_complete_can_opt_into_provider_side_thinking():
    captured = {}

    def urlopen(request, *, timeout):
        captured["request"] = request
        return FakeResponse({"choices": []})

    client = OpenAICompatibleClient(
        ProviderProfile(
            base_url="http://example.test/v1",
            model="bonsai",
            disable_thinking=False,
        ),
        urlopen=urlopen,
    )

    client.complete([{"role": "user", "content": "Hello"}])

    request_body = json.loads(captured["request"].data.decode("utf-8"))
    assert "chat_template_kwargs" not in request_body


def test_transport_rejects_invalid_json_and_oversized_response():
    profile = ProviderProfile(
        base_url="http://example.test/v1",
        model="bonsai",
        max_response_bytes=4,
    )

    def oversized(request, *, timeout):
        return FakeResponse({"data": []}, content_length=100)

    with pytest.raises(ProviderTransportError, match="size limit"):
        OpenAICompatibleClient(profile, urlopen=oversized).list_models()

    class InvalidJsonResponse(FakeResponse):
        def __init__(self):
            self.headers = {}

        def read(self, size=-1):
            return b"not-json"

    with pytest.raises(ProviderTransportError, match="JSON"):
        OpenAICompatibleClient(
            ProviderProfile(base_url="http://example.test/v1", model="bonsai"),
            urlopen=lambda request, *, timeout: InvalidJsonResponse(),
        ).list_models()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_bearer_redirect_is_rejected_without_forwarding_a_second_request(status):
    forwarded_headers = []

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/v1/models":
                self.send_response(status)
                self.send_header("Location", "/collect")
                self.end_headers()
                return
            if self.path == "/collect":
                forwarded_headers.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"data": []}')

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = OpenAICompatibleClient(
            ProviderProfile(
                base_url=f"http://{host}:{port}/v1",
                model="bonsai",
                auth=EndpointAuthKind.Bearer,
            ),
            bearer_token="secret",
        )
        with pytest.raises(ProviderTransportError, match="redirect"):
            client.list_models()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert forwarded_headers == []
