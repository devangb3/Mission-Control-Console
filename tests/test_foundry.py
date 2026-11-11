"""Foundry client configuration and the chat-completions request. No live call."""

import json

import httpx
import pytest

from mission_control.errors import FoundryConfigError, ModelCallError
from mission_control.foundry import FoundryModelClient, normalize_base_url


def test_base_url_points_at_the_openai_v1_route() -> None:
    assert (
        normalize_base_url("https://meridian.openai.azure.com")
        == "https://meridian.openai.azure.com/openai/v1/"
    )
    assert (
        normalize_base_url("https://meridian.openai.azure.com/openai/v1")
        == "https://meridian.openai.azure.com/openai/v1/"
    )
    assert (
        normalize_base_url("https://meridian.services.ai.azure.com/openai/v1/")
        == "https://meridian.services.ai.azure.com/openai/v1/"
    )


def test_a_non_foundry_host_is_rejected() -> None:
    with pytest.raises(FoundryConfigError):
        normalize_base_url("https://example.com")
    with pytest.raises(FoundryConfigError):
        normalize_base_url("http://meridian.openai.azure.com")


def test_from_env_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("FOUNDRY_BASE_URL", "https://meridian.openai.azure.com")
    monkeypatch.setenv("FOUNDRY_MODEL", "mission-briefing")
    with pytest.raises(FoundryConfigError, match="FOUNDRY_API_KEY"):
        FoundryModelClient.from_env()


def test_chat_completion_sends_the_deployment_and_reads_tokens() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "mission-briefing",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": '{"subsystem": "telemetry", "severity": "low"}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )

    client = FoundryModelClient(
        api_key="test-key",
        base_url="https://meridian.openai.azure.com",
        model="mission-briefing",
        temperature=0,
        json_mode=True,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    import asyncio

    result = asyncio.run(
        client.complete(step="sort", system="Return JSON.", user="Station: LC-39A")
    )
    assert result.tokens_in == 11
    assert result.tokens_out == 7
    assert "telemetry" in result.text
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path.endswith("/chat/completions")
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content.decode())
    assert body["model"] == "mission-briefing"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0


def test_a_refused_key_is_a_clear_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "nope"}})

    client = FoundryModelClient(
        api_key="test-key",
        base_url="https://meridian.openai.azure.com",
        model="mission-briefing",
        temperature=None,
        json_mode=False,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    import asyncio

    with pytest.raises(ModelCallError, match="API key"):
        asyncio.run(client.complete(step="sort", system="Return JSON.", user="Hello"))
