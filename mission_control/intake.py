"""Validate a filed report before any model sees it."""

import math

from mission_control.domain import ReportInput
from mission_control.errors import InvalidReport

_FIELDS = (
    "engineer_name",
    "station",
    "wind_knots",
    "temp_c",
    "fuel_pct",
    "note",
)
_MISSING = {
    "engineer_name": "Add the engineer name.",
    "station": "Add the station.",
    "wind_knots": "Add the wind.",
    "temp_c": "Add the temperature.",
    "fuel_pct": "Add the fuel.",
    "note": "Add the note.",
}


def parse_report_input(payload: object) -> ReportInput:
    """Accept the six filed fields and reject anything that could smuggle a verdict."""
    if not isinstance(payload, dict):
        raise InvalidReport("Send the report as a JSON object.")
    data: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise InvalidReport("Send the report as a JSON object.")
        data[key] = value
    for field in _FIELDS:
        if field not in data:
            raise InvalidReport(_MISSING[field])
    unexpected = [key for key in data if key not in _FIELDS]
    if unexpected:
        raise InvalidReport(f"Remove {unexpected[0]}. The verdict is decided by the console.")
    return ReportInput(
        engineer_name=_require_text(data["engineer_name"], "the engineer name", 120),
        station=_require_text(data["station"], "the station", 120),
        wind_knots=_require_reading(data["wind_knots"], "Wind", minimum=0),
        temp_c=_require_reading(data["temp_c"], "Temperature", minimum=None),
        fuel_pct=_require_reading(data["fuel_pct"], "Fuel", minimum=0),
        note=_require_text(data["note"], "the note", 4000),
    )


def _require_text(value: object, name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise InvalidReport(f"Write {name} as text.")
    stripped = value.strip()
    if not stripped:
        raise InvalidReport(f"Add {name}.")
    if len(stripped) > limit:
        raise InvalidReport(f"Keep {name} to {limit} characters or fewer.")
    return stripped


def _require_reading(value: object, label: str, *, minimum: int | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidReport(f"{label} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidReport(f"{label} must be a finite number.")
    if minimum is not None and number < minimum:
        bound = "zero" if minimum == 0 else str(minimum)
        raise InvalidReport(f"{label} must be {bound} or more.")
    return number
