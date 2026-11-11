"""Foundry client configuration and the Responses API request. No live call."""

import json

import httpx
import pytest

from mission_control.domain.errors import FoundryConfigError, ModelCallError
from mission_control.infrastructure.foundry import FoundryModelClient, normalize_base_url


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


@pytest.mark.parametrize("json_mode", [True, False])
def test_response_sends_the_deployment_and_reads_tokens(
    json_mode: bool,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "resp-test",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "mission-briefing",
                "output": [
                    {"id": "reasoning-test", "type": "reasoning", "summary": []},
                    {
                        "id": "msg-test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": '{"subsystem": "telemetry", ', "annotations": []},
                            {"type": "output_text", "text": '"severity": "low"}', "annotations": []},
                        ],
                    }
                ],
                "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            },
        )

    client = FoundryModelClient(
        api_key="test-key",
        base_url="https://meridian.openai.azure.com",
        model="mission-briefing",
        json_mode=json_mode,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    import asyncio

    result = asyncio.run(
        client.complete(step="sort", system="Return JSON.", user="Station: LC-39A")
    )
    assert result.tokens_in == 11
    assert result.tokens_out == 7
    assert json.loads(result.text) == {"subsystem": "telemetry", "severity": "low"}
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/openai/v1/responses"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content.decode())
    assert body["model"] == "mission-briefing"
    assert body["input"] == [
        {"role": "system", "content": "Return JSON."},
        {"role": "user", "content": "Station: LC-39A"},
    ]
    assert "messages" not in body
    assert "response_format" not in body
    if json_mode:
        assert body["text"] == {"format": {"type": "json_object"}}
    else:
        assert "text" not in body


def test_a_refused_key_is_a_clear_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "nope"}})

    client = FoundryModelClient(
        api_key="test-key",
        base_url="https://meridian.openai.azure.com",
        model="mission-briefing",
        json_mode=False,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    import asyncio

    with pytest.raises(ModelCallError, match="API key"):
        asyncio.run(client.complete(step="sort", system="Return JSON.", user="Hello"))


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"status": "incomplete"}, "did not complete"),
        ({"status": "failed"}, "did not complete"),
        ({"output": []}, "empty reply"),
        ({"usage": None}, "token counts"),
        ({"usage": {"input_tokens": 1}}, "token counts"),
        ({"usage": {"input_tokens": -1, "output_tokens": 7}}, "negative token"),
    ],
)
def test_unusable_responses_raise_clear_errors(overrides: dict, error: str) -> None:
    payload = {
        "id": "resp-test",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "mission-briefing",
        "output": [{
            "id": "msg-test",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "{}", "annotations": []}],
        }],
        "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
    }
    payload.update(overrides)
    client = FoundryModelClient(
        api_key="test-key",
        base_url="https://meridian.services.ai.azure.com/openai/v1",
        model="mission-briefing",
        json_mode=False,
        http_client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        )),
    )
    import asyncio

    with pytest.raises(ModelCallError, match=error):
        asyncio.run(client.complete(step="sort", system="Return JSON.", user="Hello"))
