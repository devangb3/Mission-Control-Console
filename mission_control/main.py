"""Process entry point. ``make start`` loads this module."""

import logging

from mission_control.domain.errors import FoundryConfigError
from mission_control.factory import create_app
from mission_control.log import LoggingConfigError

try:
    app = create_app()
except (FoundryConfigError, LoggingConfigError) as exc:
    logging.getLogger("mission_control").error("%s", exc.message)
    raise SystemExit(exc.message) from exc
