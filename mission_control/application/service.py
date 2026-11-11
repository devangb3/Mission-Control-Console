"""Application use cases independent of HTTP and concrete storage."""

from mission_control.domain import ReportRecord
from mission_control.domain.errors import InvalidReport
from mission_control.application.intake import parse_report_input
from mission_control.application.ports import ReportBuilder, ReportStore


class ReportService:
    def __init__(self, repository: ReportStore, builder: ReportBuilder) -> None:
        self._repository = repository
        self._builder = builder

    def list_reports(self) -> list[ReportRecord]:
        return self._repository.list_reports()

    def get(self, report_id: str) -> ReportRecord:
        return self._repository.get(report_id)

    async def create(self, payload: object) -> ReportRecord:
        report = await self._builder.build(parse_report_input(payload))
        self._repository.add(report)
        return report

    def approve(self, report_id: str, payload: object) -> ReportRecord:
        if not isinstance(payload, dict):
            raise InvalidReport("Send the approver name as JSON.")
        raw_name = payload.get("approver_name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise InvalidReport("Add your name to approve the briefing.")
        approver_name = raw_name.strip()
        if len(approver_name) > 120:
            raise InvalidReport("Keep the approver name to 120 characters or fewer.")
        return self._repository.approve(report_id, approver_name)
