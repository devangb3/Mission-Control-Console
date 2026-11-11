"""One access line per API request: method, path, status, and duration."""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mission_control.log import elapsed_ms, one_line

logger = logging.getLogger(__name__)


class ApiAccessLog:
    """Log ``/api`` responses. Pages and static files stay out of this log."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = scope["path"]
        if not path.startswith("/api/"):
            await self._app(scope, receive, send)
            return
        method = scope["method"]
        started = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status = message["status"]
                assert isinstance(status, int)
                status_code = status
            await send(message)

        try:
            await self._app(scope, receive, send_with_status)
        except Exception:
            logger.error(
                "%s %s failed after %d ms.",
                method,
                one_line(path),
                elapsed_ms(started),
            )
            raise
        logger.info(
            "%s %s -> %s in %d ms.",
            method,
            one_line(path),
            status_code,
            elapsed_ms(started),
        )
