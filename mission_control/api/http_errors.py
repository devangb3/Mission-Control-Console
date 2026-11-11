"""Translate application failures into HTTP responses."""

from fastapi import Request
from fastapi.responses import JSONResponse
from mission_control.domain.errors import (
    AppError, InvalidReport, ModelCallError, ModelOutputError,
    ReportNotFound, AlreadyApproved, FoundryConfigError,
)

async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=_status_code(exc), content={"detail": exc.message})


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
