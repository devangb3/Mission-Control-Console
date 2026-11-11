"""The form, bad input, restart, and the rule that only a person approves."""

from pathlib import Path

from fastapi.testclient import TestClient

from mission_control.factory import create_app
from mission_control.limits import evaluate_limits
from tests.scripted import as_json, scripted
from tests.support import HIDDEN_INSTRUCTION_NOTE, TEST_PRICING, reading


def test_the_form_sends_every_field() -> None:
    html = Path("static/index.html").read_text(encoding="utf-8")
    script = Path("static/console.js").read_text(encoding="utf-8")
    for field in ("engineer_name", "station", "wind_knots", "temp_c", "fuel_pct", "note"):
        assert f'name="{field}"' in html
        assert field in script


def test_bad_input_is_rejected_with_a_clear_message(tmp_path: Path) -> None:
    cases = [
        ({key: value for key, value in reading().items() if key != "station"}, "Add the station."),
        ({**reading(), "engineer_name": "   "}, "Add the engineer name."),
        ({**reading(), "note": ""}, "Add the note."),
        ({**reading(), "wind_knots": -1}, "Wind must be zero or more."),
        ({**reading(), "wind_knots": "fast"}, "Wind must be a number."),
        ({**reading(), "fuel_pct": -1}, "Fuel must be zero or more."),
        ({**reading(), "fuel_pct": True}, "Fuel must be a number."),
        ({**reading(), "status": "approved"}, "Remove status. The verdict is decided by the console."),
    ]
    with _client(tmp_path) as client:
        for body, message in cases:
            response = client.post("/api/reports", json=body)
            assert response.status_code == 422
            assert response.json()["detail"] == message
        assert client.get("/api/reports").json() == []


def test_boundaries_hold_through_the_api(tmp_path: Path) -> None:
    database = tmp_path / "board.sqlite"

    def post(body: dict[str, object]) -> object:
        with _client(tmp_path, database) as client:
            return client.post("/api/reports", json=body)

    on_the_limit = post(reading(wind_knots=25, temp_c=4, fuel_pct=98))
    assert on_the_limit.status_code == 201
    assert on_the_limit.json()["verdict"] == "go"
    assert on_the_limit.json()["violations"] == []

    just_past_wind = post(reading(wind_knots=25.1, temp_c=4, fuel_pct=100))
    assert just_past_wind.status_code == 201
    assert just_past_wind.json()["verdict"] == "no_go"
    assert any("25 knots or less" in item for item in just_past_wind.json()["violations"])

    cold = post(reading(wind_knots=25, temp_c=3.9, fuel_pct=100))
    assert cold.json()["verdict"] == "no_go"
    low_fuel = post(reading(wind_knots=25, temp_c=4, fuel_pct=97.9))
    assert low_fuel.json()["verdict"] == "no_go"
    rich_fuel = post(reading(wind_knots=25, temp_c=4, fuel_pct=100.1))
    assert rich_fuel.json()["verdict"] == "no_go"


def test_reports_are_still_there_after_a_restart(tmp_path: Path) -> None:
    database = tmp_path / "board.sqlite"
    with _client(tmp_path, database) as client:
        created = client.post("/api/reports", json=reading())
        assert created.status_code == 201
        report_id = created.json()["id"]
        assert created.json()["status"] == "pending"

    with _client(tmp_path, database) as restarted:
        listed = restarted.get("/api/reports")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [report_id]
        fetched = restarted.get(f"/api/reports/{report_id}")
        assert fetched.status_code == 200
        assert fetched.json()["note"] == reading()["note"]
        assert fetched.json()["wind_knots"] == 12


def test_only_a_person_can_approve(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post("/api/reports", json=reading())
        report_id = created.json()["id"]
        assert created.json()["status"] == "pending"
        assert created.json()["rounds"][0]["accepted"] is True

        missing = client.post(f"/api/reports/{report_id}/approve", json={})
        assert missing.status_code == 422
        assert missing.json()["detail"] == "Add your name to approve the briefing."

        approved = client.post(
            f"/api/reports/{report_id}/approve",
            json={"approver_name": "Grace Hopper"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["approved_by"] == "Grace Hopper"

        again = client.post(
            f"/api/reports/{report_id}/approve",
            json={"approver_name": "Grace Hopper"},
        )
        assert again.status_code == 409

        missing_report = client.post(
            "/api/reports/not-a-report/approve",
            json={"approver_name": "Grace Hopper"},
        )
        assert missing_report.status_code == 404


def test_hidden_instruction_note_is_flagged_and_leaves_the_verdict(tmp_path: Path) -> None:
    flagged = as_json({"flagged": True, "reason": "The note instructs the system."})
    with _client(tmp_path, model=scripted(hidden=[flagged])) as client:
        no_go = client.post(
            "/api/reports",
            json=reading(wind_knots=40, note=HIDDEN_INSTRUCTION_NOTE),
        )
        assert no_go.status_code == 201
        body = no_go.json()
        expected = evaluate_limits(wind_knots=40, temp_c=18, fuel_pct=99)
        assert body["verdict"] == expected.verdict.value
        assert body["hidden_instruction"] is True
        assert body["flagged_for_review"] is True
        assert body["status"] == "pending"
        assert body["brief_by_minutes"] == 5

    with _client(tmp_path, model=scripted(hidden=[flagged])) as client:
        still_go = client.post("/api/reports", json=reading(note=HIDDEN_INSTRUCTION_NOTE))
        assert still_go.status_code == 201
        assert still_go.json()["verdict"] == "go"
        assert still_go.json()["hidden_instruction"] is True
        assert still_go.json()["violations"] == []


def _client(tmp_path: Path, database: Path | None = None, model: object | None = None) -> TestClient:
    app = create_app(
        db_path=database if database is not None else tmp_path / "board.sqlite",
        model=model if model is not None else scripted(),
        pricing=TEST_PRICING,
    )
    return TestClient(app)
