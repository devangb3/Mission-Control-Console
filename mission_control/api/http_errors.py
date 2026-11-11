"""Translate application failures into HTTP responses."""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from mission_control.domain.errors import (
    AppError, InvalidReport, ModelCallError, ModelOutputError,
    ReportNotFound, AlreadyApproved, FoundryConfigError,
)

logger = logging.getLogger(__name__)


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    status = _status_code(exc)
    logger.log(
        logging.ERROR if status >= 500 else logging.WARNING,
        "%s %s -> %s: %s",
        request.method,
        request.url.path,
        status,
        exc.message,
    )
    return JSONResponse(status_code=status, content={"detail": exc.message})


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
