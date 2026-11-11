"""HTTP transport: decode requests and delegate report operations."""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from mission_control.domain import ReportRecord
from mission_control.domain.errors import InvalidReport
from mission_control.application.service import ReportService


def create_router(service: ReportService, static_dir: Path) -> APIRouter:
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @router.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @router.get("/api/reports", response_model=list[ReportRecord])
    def list_reports() -> list[ReportRecord]:
        return service.list_reports()

    @router.get("/api/reports/{report_id}", response_model=ReportRecord)
    def get_report(report_id: str) -> ReportRecord:
        return service.get(report_id)

    @router.post("/api/reports", status_code=201, response_model=ReportRecord)
    async def create_report(request: Request) -> ReportRecord:
        try:
            payload: object = await request.json()
        except ValueError as exc:
            # JSON syntax, invalid encoding, and oversized integer literals.
            raise InvalidReport("Send the report as JSON.") from exc
        return await service.create(payload)

    @router.post("/api/reports/{report_id}/approve", response_model=ReportRecord)
    async def approve_report(report_id: str, request: Request) -> ReportRecord:
        try:
            payload: object = await request.json()
        except ValueError as exc:
            raise InvalidReport("Send the approver name as JSON.") from exc
        return service.approve(report_id, payload)

    return router
