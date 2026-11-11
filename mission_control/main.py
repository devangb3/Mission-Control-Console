"""Process entry point. ``make start`` loads this module."""

from mission_control.errors import FoundryConfigError
from mission_control.factory import create_app

try:
    app = create_app()
except FoundryConfigError as exc:
    raise SystemExit(exc.message) from exc
