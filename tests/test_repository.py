"""Report fields are columns, and the old single-field table is rewritten on open."""

import sqlite3
from pathlib import Path

from mission_control.domain import ReportRecord, ReportStatus
from mission_control.infrastructure.repository import Repository


def test_report_fields_are_columns(tmp_path: Path) -> None:
    database = tmp_path / "board.sqlite"
    pending = _report()
    repository = Repository(database)
    repository.add(pending)
    assert repository.get(pending.id) == pending

    approved = repository.approve(pending.id, "Grace Hopper")
    assert approved.status is ReportStatus.APPROVED
    assert approved.approved_by == "Grace Hopper"
    assert repository.list_reports() == [approved]

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(reports)")}
    assert "body" not in columns
    row = connection.execute("SELECT * FROM reports WHERE id = ?", (pending.id,)).fetchone()
    assert row["engineer_name"] == "Ada Lovelace"
    assert row["station"] == "LC-39A"
    assert row["wind_knots"] == 12
    assert row["temp_c"] == 18
    assert row["fuel_pct"] == 99
    assert row["note"] == pending.note
    assert row["subsystem"] == "telemetry"
    assert row["verdict"] == "no_go"
    assert row["status"] == "approved"
    assert row["approved_by"] == "Grace Hopper"
    violations = connection.execute(
        "SELECT message FROM report_violations WHERE report_id = ? ORDER BY position",
        (pending.id,),
    ).fetchall()
    assert [item["message"] for item in violations] == ["Fuel is 89 percent. The limit is 98 to 100 percent."]
    rounds = connection.execute(
        "SELECT round_number, accepted FROM report_rounds WHERE report_id = ?",
        (pending.id,),
    ).fetchall()
    assert [(item["round_number"], item["accepted"]) for item in rounds] == [(1, 1)]
    connection.close()


def test_legacy_body_column_is_split_on_open(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite"
    saved = _report().model_copy(update={"status": ReportStatus.APPROVED, "approved_by": "derick"})
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE reports (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            body TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO reports (id, status, created_at, body) VALUES (?, ?, ?, ?)",
        (saved.id, saved.status.value, saved.created_at, saved.model_dump_json()),
    )
    connection.commit()
    connection.close()

    loaded = Repository(database).get(saved.id)
    assert loaded == saved

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(reports)")}
    assert "body" not in columns
    row = connection.execute(
        "SELECT engineer_name, station, wind_knots, note, approved_by FROM reports"
    ).fetchone()
    assert row["engineer_name"] == "Ada Lovelace"
    assert row["station"] == "LC-39A"
    assert row["wind_knots"] == 12
    assert row["note"] == saved.note
    assert row["approved_by"] == "derick"
    connection.close()


def _report() -> ReportRecord:
    return ReportRecord.model_validate(
        {
            "id": "9cac9af0-fee4-4604-bb6f-20a8180b3338",
            "engineer_name": "Ada Lovelace",
            "station": "LC-39A",
            "wind_knots": 12,
            "temp_c": 18,
            "fuel_pct": 99,
            "note": "The valve on the pressurization line twitched once and then held steady.",
            "subsystem": "telemetry",
            "model_severity": "low",
            "effective_severity": "high",
            "verdict": "no_go",
            "violations": ["Fuel is 89 percent. The limit is 98 to 100 percent."],
            "brief_by_minutes": 5,
            "hidden_instruction": False,
            "missing_details": True,
            "panic_tone": False,
            "flagged_for_review": False,
            "briefing": "Verdict: no_go. Fuel is below the limit.",
            "rounds": [
                {
                    "round_number": 1,
                    "briefing": "Verdict: no_go. Fuel is below the limit.",
                    "accepted": True,
                    "feedback": "The briefing names the fuel violation.",
                }
            ],
            "status": "pending",
            "approved_by": None,
            "cost_usd": "0.019656",
            "trace": [
                {
                    "name": "Check launch limits",
                    "kind": "code",
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "summary": "No-go. Fuel is below the limit.",
                }
            ],
            "created_at": "2026-11-11T17:06:16.853882+00:00",
        }
    )
