"""SQLite storage. Each report field is a column, and a new process opening the same file still sees the reports."""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from mission_control.domain import ReportRecord, ReportStatus
from mission_control.domain.errors import AlreadyApproved, ReportNotFound
from mission_control.log import one_line

logger = logging.getLogger(__name__)


class StorageSchemaError(Exception):
    """The database file is not a reports table this console can open."""


_REPORT_COLUMNS = (
    "id",
    "engineer_name",
    "station",
    "wind_knots",
    "temp_c",
    "fuel_pct",
    "note",
    "subsystem",
    "model_severity",
    "effective_severity",
    "verdict",
    "brief_by_minutes",
    "hidden_instruction",
    "missing_details",
    "panic_tone",
    "flagged_for_review",
    "briefing",
    "status",
    "approved_by",
    "cost_usd",
    "created_at",
)


class Repository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            with _transaction(connection, write=True):
                schema_event = self._ensure_schema(connection)
        finally:
            connection.close()
        logger.info("Opened the report database at %s.", one_line(str(self._path)))
        if schema_event is None:
            logger.debug("Report database schema is current.")
        else:
            logger.info("%s", schema_event)

    def add(self, report: ReportRecord) -> None:
        assert report.status is ReportStatus.PENDING
        assert report.approved_by is None
        connection = self._connect()
        try:
            with _transaction(connection, write=True):
                self._insert(connection, report)
        finally:
            connection.close()

    def list_reports(self) -> list[ReportRecord]:
        connection = self._connect()
        try:
            with _transaction(connection, write=False):
                rows = connection.execute(
                    f"SELECT {', '.join(_REPORT_COLUMNS)} FROM reports ORDER BY created_at DESC"
                ).fetchall()
                return self._records(connection, rows)
        finally:
            connection.close()

    def get(self, report_id: str) -> ReportRecord:
        connection = self._connect()
        try:
            with _transaction(connection, write=False):
                row = connection.execute(
                    f"SELECT {', '.join(_REPORT_COLUMNS)} FROM reports WHERE id = ?",
                    (report_id,),
                ).fetchone()
                if row is None:
                    raise ReportNotFound("That report is not on the board.")
                return self._one(connection, row)
        finally:
            connection.close()

    def approve(self, report_id: str, approver_name: str) -> ReportRecord:
        connection = self._connect()
        try:
            with _transaction(connection, write=True):
                row = connection.execute(
                    f"SELECT {', '.join(_REPORT_COLUMNS)} FROM reports WHERE id = ?",
                    (report_id,),
                ).fetchone()
                if row is None:
                    raise ReportNotFound("That report is not on the board.")
                report = self._one(connection, row)
                if report.status is not ReportStatus.PENDING:
                    raise AlreadyApproved("This briefing is already approved.")
                updated = report.model_copy(
                    update={"status": ReportStatus.APPROVED, "approved_by": approver_name}
                )
                cursor = connection.execute(
                    """
                    UPDATE reports
                    SET status = ?, approved_by = ?
                    WHERE id = ? AND status = ?
                    """,
                    (updated.status.value, approver_name, report_id, ReportStatus.PENDING.value),
                )
                if cursor.rowcount != 1:
                    raise AlreadyApproved("This briefing is already approved.")
        finally:
            connection.close()
        return updated

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> str | None:
        columns = _column_names(connection, "reports")
        if not columns:
            self._create_tables(connection)
            return "Created the report tables."
        if "body" in columns:
            if "engineer_name" in columns:
                raise _schema_error("reports has both a body column and report columns.")
            moved = self._replace_blob_table(connection)
            return f"Moved {moved} reports out of the blob table into columns."
        missing = [name for name in _REPORT_COLUMNS if name not in columns]
        if missing:
            raise _schema_error(f"reports is missing columns: {', '.join(missing)}")
        self._create_child_tables(connection)
        return None

    def _replace_blob_table(self, connection: sqlite3.Connection) -> int:
        rows = connection.execute("SELECT id, status, created_at, body FROM reports").fetchall()
        saved = [_record_from_blob(row) for row in rows]
        connection.execute("DROP TABLE reports")
        self._create_tables(connection)
        for report in saved:
            self._insert(connection, report)
        return len(saved)

    def _create_tables(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                engineer_name TEXT NOT NULL,
                station TEXT NOT NULL,
                wind_knots REAL NOT NULL,
                temp_c REAL NOT NULL,
                fuel_pct REAL NOT NULL,
                note TEXT NOT NULL,
                subsystem TEXT NOT NULL,
                model_severity TEXT NOT NULL,
                effective_severity TEXT NOT NULL,
                verdict TEXT NOT NULL,
                brief_by_minutes INTEGER NOT NULL,
                hidden_instruction INTEGER NOT NULL CHECK (hidden_instruction IN (0, 1)),
                missing_details INTEGER NOT NULL CHECK (missing_details IN (0, 1)),
                panic_tone INTEGER NOT NULL CHECK (panic_tone IN (0, 1)),
                flagged_for_review INTEGER NOT NULL CHECK (flagged_for_review IN (0, 1)),
                briefing TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved')),
                approved_by TEXT,
                cost_usd TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._create_child_tables(connection)

    def _create_child_tables(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS report_violations (
                report_id TEXT NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                message TEXT NOT NULL,
                PRIMARY KEY (report_id, position)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS report_rounds (
                report_id TEXT NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
                round_number INTEGER NOT NULL,
                briefing TEXT NOT NULL,
                accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
                feedback TEXT NOT NULL,
                PRIMARY KEY (report_id, round_number)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS report_trace (
                report_id TEXT NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('model', 'code')),
                tokens_in INTEGER NOT NULL,
                tokens_out INTEGER NOT NULL,
                summary TEXT NOT NULL,
                PRIMARY KEY (report_id, position)
            )
            """
        )

    def _insert(self, connection: sqlite3.Connection, report: ReportRecord) -> None:
        connection.execute(
            f"""
            INSERT INTO reports ({", ".join(_REPORT_COLUMNS)})
            VALUES ({", ".join("?" for _ in _REPORT_COLUMNS)})
            """,
            _report_values(report),
        )
        connection.executemany(
            "INSERT INTO report_violations (report_id, position, message) VALUES (?, ?, ?)",
            [
                (report.id, position, message)
                for position, message in enumerate(report.violations)
            ],
        )
        connection.executemany(
            """
            INSERT INTO report_rounds (report_id, round_number, briefing, accepted, feedback)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (report.id, draft.round_number, draft.briefing, int(draft.accepted), draft.feedback)
                for draft in report.rounds
            ],
        )
        connection.executemany(
            """
            INSERT INTO report_trace (
                report_id, position, name, kind, tokens_in, tokens_out, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (report.id, position, step.name, step.kind, step.tokens_in, step.tokens_out, step.summary)
                for position, step in enumerate(report.trace)
            ],
        )

    def _records(self, connection: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[ReportRecord]:
        if not rows:
            return []
        ids = [_text(row["id"]) for row in rows]
        marks = ", ".join("?" for _ in ids)
        violations = _group(
            connection.execute(
                f"""
                SELECT report_id, position, message
                FROM report_violations
                WHERE report_id IN ({marks})
                ORDER BY position
                """,
                ids,
            ).fetchall()
        )
        rounds = _group(
            connection.execute(
                f"""
                SELECT report_id, round_number, briefing, accepted, feedback
                FROM report_rounds
                WHERE report_id IN ({marks})
                ORDER BY round_number
                """,
                ids,
            ).fetchall()
        )
        trace = _group(
            connection.execute(
                f"""
                SELECT report_id, position, name, kind, tokens_in, tokens_out, summary
                FROM report_trace
                WHERE report_id IN ({marks})
                ORDER BY position
                """,
                ids,
            ).fetchall()
        )
        return [
            _record_from_row(
                row,
                violations.get(_text(row["id"]), []),
                rounds.get(_text(row["id"]), []),
                trace.get(_text(row["id"]), []),
            )
            for row in rows
        ]

    def _one(self, connection: sqlite3.Connection, row: sqlite3.Row) -> ReportRecord:
        records = self._records(connection, [row])
        assert len(records) == 1
        return records[0]


@contextmanager
def _transaction(connection: sqlite3.Connection, *, write: bool) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        yield
    except Exception:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    assert table in {"reports", "report_violations", "report_rounds", "report_trace"}
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return {_text(row["name"]) for row in rows}


def _schema_error(message: str) -> StorageSchemaError:
    logger.error("%s", message)
    return StorageSchemaError(message)


def _record_from_blob(row: sqlite3.Row) -> ReportRecord:
    report_id = _text(row["id"])
    body = row["body"]
    if not isinstance(body, str):
        raise _schema_error(f"Saved report {report_id} has a body that is not text.")
    try:
        report = ReportRecord.model_validate_json(body)
    except ValidationError as exc:
        raise _schema_error(f"Saved report {report_id} is not a report record.") from exc
    if report.id != report_id or report.status.value != row["status"] or report.created_at != row["created_at"]:
        raise _schema_error(
            f"Saved report {report_id} does not match its id, status, and created_at columns."
        )
    return report


def _record_from_row(
    row: sqlite3.Row,
    violations: list[sqlite3.Row],
    rounds: list[sqlite3.Row],
    trace: list[sqlite3.Row],
) -> ReportRecord:
    positions = [_whole(item["position"]) for item in violations]
    assert positions == list(range(len(positions)))
    round_numbers = [_whole(item["round_number"]) for item in rounds]
    assert round_numbers == sorted(set(round_numbers))
    trace_positions = [_whole(item["position"]) for item in trace]
    assert trace_positions == list(range(len(trace_positions)))
    report = ReportRecord.model_validate(
        {
            "id": _text(row["id"]),
            "engineer_name": _text(row["engineer_name"]),
            "station": _text(row["station"]),
            "wind_knots": _number(row["wind_knots"]),
            "temp_c": _number(row["temp_c"]),
            "fuel_pct": _number(row["fuel_pct"]),
            "note": _text(row["note"]),
            "subsystem": _text(row["subsystem"]),
            "model_severity": _text(row["model_severity"]),
            "effective_severity": _text(row["effective_severity"]),
            "verdict": _text(row["verdict"]),
            "violations": [_text(item["message"]) for item in violations],
            "brief_by_minutes": _whole(row["brief_by_minutes"]),
            "hidden_instruction": _flag(row["hidden_instruction"]),
            "missing_details": _flag(row["missing_details"]),
            "panic_tone": _flag(row["panic_tone"]),
            "flagged_for_review": _flag(row["flagged_for_review"]),
            "briefing": _text(row["briefing"]),
            "rounds": [
                {
                    "round_number": _whole(item["round_number"]),
                    "briefing": _text(item["briefing"]),
                    "accepted": _flag(item["accepted"]),
                    "feedback": _text(item["feedback"]),
                }
                for item in rounds
            ],
            "status": _text(row["status"]),
            "approved_by": _optional_text(row["approved_by"]),
            "cost_usd": _text(row["cost_usd"]),
            "trace": [
                {
                    "name": _text(item["name"]),
                    "kind": _text(item["kind"]),
                    "tokens_in": _whole(item["tokens_in"]),
                    "tokens_out": _whole(item["tokens_out"]),
                    "summary": _text(item["summary"]),
                }
                for item in trace
            ],
            "created_at": _text(row["created_at"]),
        }
    )
    assert report.id == row["id"]
    assert report.status.value == row["status"]
    return report


def _report_values(report: ReportRecord) -> tuple[object, ...]:
    return (
        report.id,
        report.engineer_name,
        report.station,
        report.wind_knots,
        report.temp_c,
        report.fuel_pct,
        report.note,
        report.subsystem.value,
        report.model_severity.value,
        report.effective_severity.value,
        report.verdict.value,
        report.brief_by_minutes,
        int(report.hidden_instruction),
        int(report.missing_details),
        int(report.panic_tone),
        int(report.flagged_for_review),
        report.briefing,
        report.status.value,
        report.approved_by,
        report.cost_usd,
        report.created_at,
    )


def _group(rows: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(_text(row["report_id"]), []).append(row)
    return grouped


def _text(value: object) -> str:
    assert isinstance(value, str)
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    assert isinstance(value, str)
    return value


def _number(value: object) -> float:
    assert isinstance(value, (int, float))
    assert not isinstance(value, bool)
    return float(value)


def _whole(value: object) -> int:
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _flag(value: object) -> bool:
    assert value in (0, 1)
    return value == 1
