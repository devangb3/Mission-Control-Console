"""SQLite storage. A new process opening the same file still sees the reports."""

import sqlite3
from pathlib import Path

from mission_control.domain import ReportRecord, ReportStatus
from mission_control.domain.errors import AlreadyApproved, ReportNotFound


class Repository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    body TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def add(self, report: ReportRecord) -> None:
        assert report.status is ReportStatus.PENDING
        assert report.approved_by is None
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO reports (id, status, created_at, body) VALUES (?, ?, ?, ?)",
                (report.id, report.status.value, report.created_at, report.model_dump_json()),
            )
            connection.commit()
        finally:
            connection.close()

    def list_reports(self) -> list[ReportRecord]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, status, body FROM reports ORDER BY created_at DESC"
            ).fetchall()
            return [self._load(row) for row in rows]
        finally:
            connection.close()

    def get(self, report_id: str) -> ReportRecord:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT id, status, body FROM reports WHERE id = ?",
                (report_id,),
            ).fetchone()
            if row is None:
                raise ReportNotFound("That report is not on the board.")
            return self._load(row)
        finally:
            connection.close()

    def approve(self, report_id: str, approver_name: str) -> ReportRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id, status, body FROM reports WHERE id = ?",
                (report_id,),
            ).fetchone()
            if row is None:
                raise ReportNotFound("That report is not on the board.")
            report = self._load(row)
            if report.status is not ReportStatus.PENDING:
                raise AlreadyApproved("This briefing is already approved.")
            updated = report.model_copy(
                update={"status": ReportStatus.APPROVED, "approved_by": approver_name}
            )
            cursor = connection.execute(
                "UPDATE reports SET status = ?, body = ? WHERE id = ? AND status = ?",
                (updated.status.value, updated.model_dump_json(), report_id, ReportStatus.PENDING.value),
            )
            if cursor.rowcount != 1:
                raise AlreadyApproved("This briefing is already approved.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return updated

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _load(self, row: sqlite3.Row) -> ReportRecord:
        report = ReportRecord.model_validate_json(row["body"])
        assert report.id == row["id"]
        assert report.status.value == row["status"]
        return report
