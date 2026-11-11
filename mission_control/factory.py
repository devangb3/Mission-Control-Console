"""Composition root: wire configuration, adapters, services, and HTTP."""

import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from mission_control.infrastructure.config import build_model_client, pricing_from_env, _default_pricing
from mission_control.domain.cost import Pricing
from mission_control.domain.errors import AppError
from mission_control.api.access_log import ApiAccessLog
from mission_control.api.http_errors import handle_app_error
from mission_control.application.model_client import ModelClient
from mission_control.application.pipeline import ReportPipeline
from mission_control.infrastructure.repository import Repository
from mission_control.api.routes import create_router
from mission_control.application.service import ReportService
from mission_control.log import configure_logging

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_DEFAULT_DB = Path("data/mission-control.sqlite")


def create_app(
    *,
    db_path: Path | None = None,
    model: ModelClient | None = None,
    pricing: Pricing | None = None,
) -> FastAPI:
    if model is None:
        load_dotenv(Path.cwd() / ".env")
    configure_logging()
    client: ModelClient
    if model is None:
        client = build_model_client()
        resolved_pricing = pricing if pricing is not None else pricing_from_env()
    else:
        client = model
        resolved_pricing = pricing if pricing is not None else _default_pricing()
    database = db_path if db_path is not None else _DEFAULT_DB
    repository = Repository(database)
    app = FastAPI(title="Mission Control")

    service = ReportService(repository, ReportPipeline(client, resolved_pricing))
    app.add_exception_handler(AppError, handle_app_error)
    app.add_middleware(ApiAccessLog)
    app.include_router(create_router(service, STATIC_DIR))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(
        "Mission Control is ready. Reports are stored in %s. "
        "Token prices are %s and %s dollars per million in and out.",
        database,
        resolved_pricing.input_usd_per_million,
        resolved_pricing.output_usd_per_million,
    )
    return app
