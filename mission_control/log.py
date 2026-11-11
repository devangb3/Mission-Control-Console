"""Process logging for Mission Control.

Domain code stays quiet. Callers log decisions and outcomes, never the API key,
the filed note, or a model prompt. A report id bound here is copied onto every
line emitted while that report is in flight.
"""

import contextvars
import logging
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_report_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mission_control_report_id",
    default=None,
)
_handler_installed = False


class LoggingConfigError(Exception):
    """``LOG_LEVEL`` is set and is not a level this process can use."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def configure_logging() -> None:
    """Send ``mission_control`` logs to stderr. Safe to call more than once."""
    _install_handler()
    logging.getLogger("mission_control").setLevel(_level_from_env())


def one_line(value: str, *, limit: int = 160) -> str:
    """Collapse whitespace so a filed value cannot forge a second log line."""
    if limit < 1:
        raise ValueError("The log field limit must be at least 1.")
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    if limit == 1:
        return "…"
    return collapsed[: limit - 1] + "…"


def elapsed_ms(started: float) -> int:
    """Whole milliseconds since ``started``, taken from a monotonic clock."""
    elapsed = time.perf_counter() - started
    assert elapsed >= 0
    return int(elapsed * 1000)


@contextmanager
def report_context(report_id: str) -> Iterator[None]:
    """Attach a report id to log lines on this task until the block exits."""
    safe = one_line(report_id, limit=80)
    if safe == "":
        yield
        return
    token = _report_id.set(safe)
    try:
        yield
    finally:
        _report_id.reset(token)


def _level_from_env() -> int:
    raw = os.environ.get("LOG_LEVEL")
    if raw is None:
        return logging.INFO
    name = raw.strip().upper()
    level = _LEVELS.get(name)
    if level is None:
        raise LoggingConfigError(
            "LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
        )
    return level


def _install_handler() -> None:
    global _handler_installed
    if _handler_installed:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        _UtcFormatter(
            "%(asctime)sZ %(levelname)s %(name)s %(report_prefix)s%(message)s",
            "%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(_ReportContext())
    logging.getLogger("mission_control").addHandler(handler)
    _handler_installed = True


class _UtcFormatter(logging.Formatter):
    converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "report_prefix"):
            record.report_prefix = ""
        return super().format(record)


class _ReportContext(logging.Filter):
    """Copy the current report id onto the record before it is formatted.

    The filter sits on the handler. Logger filters do not see records that
    propagate up from a child logger, and the pipeline, Foundry, and the API
    each use their own logger.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        report_id = _report_id.get()
        if report_id is None:
            record.report_id = ""
            record.report_prefix = ""
        else:
            record.report_id = report_id
            record.report_prefix = f"[{report_id}] "
        return True
