"""HTTP routes for the console. Model calls stay behind ``ModelClient``."""

import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from mission_control.cost import Pricing
from mission_control.domain import ReportRecord
from dotenv import load_dotenv
from mission_control.errors import (
    AlreadyApproved,
    AppError,
    FoundryConfigError,
    InvalidReport,
    ModelCallError,
    ModelOutputError,
    ReportNotFound,
)
from mission_control.foundry import FoundryModelClient
from mission_control.intake import parse_report_input
from mission_control.model_client import ModelClient
from mission_control.pipeline import build_report
from mission_control.repository import Repository

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_DEFAULT_DB = Path("data/mission-control.sqlite")


def create_app(
    *,
    db_path: Path | None = None,
    model: ModelClient | None = None,
    pricing: Pricing | None = None,
) -> FastAPI:
    client: ModelClient
    if model is None:
        load_dotenv(Path.cwd() / ".env")
        client = build_model_client()
        resolved_pricing = pricing if pricing is not None else pricing_from_env()
    else:
        client = model
        resolved_pricing = pricing if pricing is not None else _default_pricing()
    repository = Repository(db_path if db_path is not None else _DEFAULT_DB)
    app = FastAPI(title="Mission Control")

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=_status_code(exc), content={"detail": exc.message})

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/reports", response_model=list[ReportRecord])
    def list_reports() -> list[ReportRecord]:
        return repository.list_reports()

    @app.get("/api/reports/{report_id}", response_model=ReportRecord)
    def get_report(report_id: str) -> ReportRecord:
        return repository.get(report_id)

    @app.post("/api/reports", status_code=201, response_model=ReportRecord)
    async def create_report(request: Request) -> ReportRecord:
        try:
            payload: object = await request.json()
        except json.JSONDecodeError as exc:
            raise InvalidReport("Send the report as JSON.") from exc
        report = await build_report(parse_report_input(payload), client, resolved_pricing)
        repository.add(report)
        return report

    @app.post("/api/reports/{report_id}/approve", response_model=ReportRecord)
    async def approve_report(report_id: str, request: Request) -> ReportRecord:
        try:
            payload: object = await request.json()
        except json.JSONDecodeError as exc:
            raise InvalidReport("Send the approver name as JSON.") from exc
        if not isinstance(payload, dict):
            raise InvalidReport("Send the approver name as JSON.")
        raw_name = payload.get("approver_name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise InvalidReport("Add your name to approve the briefing.")
        approver_name = raw_name.strip()
        if len(approver_name) > 120:
            raise InvalidReport("Keep the approver name to 120 characters or fewer.")
        return repository.approve(report_id, approver_name)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def build_model_client() -> ModelClient:
    return FoundryModelClient.from_env()


def pricing_from_env() -> Pricing:
    raw_input = os.environ.get("FOUNDRY_INPUT_USD_PER_MILLION", "0.15")
    raw_output = os.environ.get("FOUNDRY_OUTPUT_USD_PER_MILLION", "0.60")
    try:
        return Pricing(
            input_usd_per_million=Decimal(raw_input),
            output_usd_per_million=Decimal(raw_output),
        )
    except (InvalidOperation, ValidationError) as exc:
        raise FoundryConfigError(
            "Token prices must be numbers, zero or more, in dollars per million tokens."
        ) from exc


def _default_pricing() -> Pricing:
    return Pricing(input_usd_per_million=Decimal("0.15"), output_usd_per_million=Decimal("0.60"))


def _status_code(exc: AppError) -> int:
    if isinstance(exc, InvalidReport):
        return 422
    if isinstance(exc, (ModelCallError, ModelOutputError)):
        return 502
    if isinstance(exc, ReportNotFound):
        return 404
    if isinstance(exc, AlreadyApproved):
        return 409
    if isinstance(exc, FoundryConfigError):
        return 500
    return 500
