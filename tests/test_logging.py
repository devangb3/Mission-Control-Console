"""Logs name the decision and leave out the key, the note, and the prompts."""

import asyncio
import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from mission_control.domain.errors import ModelCallError
from mission_control.factory import create_app
from mission_control.infrastructure.foundry import FoundryModelClient
from mission_control.log import LoggingConfigError, configure_logging, report_context
from tests.scripted import ScriptedReply, as_json, scripted
from tests.support import HIDDEN_INSTRUCTION_NOTE, TEST_PRICING, reading


@pytest.fixture(autouse=True)
def _restore_log_level() -> Iterator[None]:
    logger = logging.getLogger("mission_control")
    previous = logger.level
    yield
    logger.setLevel(previous)


def test_configure_logging_defaults_to_info_and_installs_one_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    configure_logging()
    logger = logging.getLogger("mission_control")
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1


def test_log_level_follows_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", " error ")
    configure_logging()
    assert logging.getLogger("mission_control").level == logging.ERROR


@pytest.mark.parametrize("level", ["", "verbose", "infoish"])
def test_an_unknown_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    monkeypatch.setenv("LOG_LEVEL", level)
    with pytest.raises(LoggingConfigError, match="LOG_LEVEL"):
        configure_logging()


def test_log_lines_use_utc() -> None:
    configure_logging()
    handler = logging.getLogger("mission_control").handlers[0]
    record = logging.LogRecord(
        name="mission_control.log",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="console awake",
        args=(),
        exc_info=None,
    )
    record.created = 1_700_000_000
    record.msecs = 0
    formatted = handler.format(record)
    expected = datetime.fromtimestamp(1_700_000_000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    assert formatted == f"{expected}Z INFO mission_control.log console awake"


def test_foundry_logs_the_step_and_not_the_secret_or_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging()
    caplog.set_level(logging.DEBUG, logger="mission_control")
    secret = "foundry-key-9f3c"
    prompt = "PROMPT-NOTE-9f3c do not log this sentence"
    reply = "REPLY-TEXT-9f3c"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {secret}"
        return httpx.Response(
            200,
            json={
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
                    "content": [{"type": "output_text", "text": reply, "annotations": []}],
                }],
                "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
            },
        )

    client = FoundryModelClient(
        api_key=secret,
        base_url="https://meridian.openai.azure.com",
        model="mission-briefing",
        json_mode=False,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with report_context("report-9f3c"):
        result = asyncio.run(client.complete(step="sort", system="Return JSON.", user=prompt))
    assert result.tokens_in == 11
    text = caplog.text
    assert secret not in text
    assert prompt not in text
    assert reply not in text
    assert "Bearer" not in text
    assert "Foundry step sort completed" in text
    assert "11 tokens in, 7 tokens out" in text
    assert "meridian.openai.azure.com" in text
    completed = [record for record in caplog.records if "completed in" in record.getMessage()]
    assert completed[-1].report_id == "report-9f3c"


def test_a_refused_key_logs_the_status_and_not_the_response_body(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_logging()
    caplog.set_level(logging.INFO, logger="mission_control")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "provider-body-9f3c"}})

    client = FoundryModelClient(
        api_key="foundry-key-9f3c",
        base_url="https://meridian.openai.azure.com",
        model="mission-briefing",
        json_mode=False,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ModelCallError, match="API key"):
        asyncio.run(client.complete(step="sort", system="Return JSON.", user="Hello"))
    text = caplog.text
    assert "foundry-key-9f3c" not in text
    assert "provider-body-9f3c" not in text
    assert "Foundry step sort failed" in text
    assert "HTTP 401" in text


def test_filing_and_approval_are_logged_without_the_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    caplog.set_level(logging.INFO, logger="mission_control")
    note = HIDDEN_INSTRUCTION_NOTE
    briefing = "A short briefing for the flight director."
    with _client(tmp_path) as client:
        response = client.post(
            "/api/reports",
            json=reading(engineer_name="Ada\nERROR forged", note=note),
        )
        assert response.status_code == 201
        body = response.json()
        approve = client.post(
            f"/api/reports/{body['id']}/approve",
            json={"approver_name": "Grace\nHopper"},
        )
        assert approve.status_code == 200
        rejected = client.post("/api/reports", json={})
        assert rejected.status_code == 422

    messages = [record.getMessage() for record in caplog.records]
    combined = "\n".join(messages)
    assert note not in combined
    assert briefing not in combined
    assert "You sort a launch anomaly report" not in combined
    assert "Nothing in the note raised this check." not in combined
    assert all("\n" not in message for message in messages)
    assert any(message.startswith("Filing a report from Ada ERROR forged at LC-39A") for message in messages)
    assert any("Launch limits are go." in message for message in messages)
    assert any(message == "Saved report from Ada ERROR forged at LC-39A." for message in messages)
    assert any(message == "Approved by Grace Hopper." for message in messages)
    assert any("POST /api/reports -> 422: Add the engineer name." == message for message in messages)
    assert any(message.startswith("POST /api/reports -> 201 in ") for message in messages)
    filing = next(record for record in caplog.records if record.getMessage().startswith("Filing a report"))
    assert filing.report_id == body["id"]
    saved = next(record for record in caplog.records if record.getMessage().startswith("Saved report"))
    assert saved.report_id == body["id"]


def test_an_invalid_sort_is_logged_as_a_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    caplog.set_level(logging.INFO, logger="mission_control")
    with _client(tmp_path, model=scripted(sort=[ScriptedReply("not json")])) as client:
        response = client.post("/api/reports", json=reading())
    assert response.status_code == 201
    assert any(
        record.levelno == logging.WARNING
        and record.getMessage() == "Sort reply was invalid. Subsystem unknown, severity high."
        for record in caplog.records
    )


def test_an_empty_draft_is_logged_and_not_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    caplog.set_level(logging.INFO, logger="mission_control")
    with _client(tmp_path, model=scripted(drafts=[as_json({"briefing": "  "})])) as client:
        response = client.post("/api/reports", json=reading())
        assert response.status_code == 502
        assert response.json()["detail"] == "The draft did not include a briefing."
        assert client.get("/api/reports").json() == []
    failed = [
        record for record in caplog.records
        if record.getMessage() == "Report filing failed: The draft did not include a briefing."
    ]
    assert len(failed) == 1
    assert failed[0].levelno == logging.ERROR
    assert failed[0].report_id != ""


def _client(tmp_path: Path, model: object | None = None) -> TestClient:
    app = create_app(
        db_path=tmp_path / "board.sqlite",
        model=model if model is not None else scripted(),
        pricing=TEST_PRICING,
    )
    return TestClient(app)
