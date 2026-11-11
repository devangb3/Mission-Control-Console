"""Launch limits. This module never reads the note and never calls a model."""

import math
from dataclasses import dataclass

from mission_control.domain import Verdict

WIND_LIMIT_KNOTS = 25
TEMP_LIMIT_C = 4
FUEL_MIN_PCT = 98
FUEL_MAX_PCT = 100


@dataclass(frozen=True)
class LimitResult:
    verdict: Verdict
    violations: tuple[str, ...]


def format_reading(value: float) -> str:
    """Render a reading without trailing zeros, for a violation sentence."""
    if not math.isfinite(value):
        raise ValueError("A reading used in a limit check must be finite.")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def evaluate_limits(*, wind_knots: float, temp_c: float, fuel_pct: float) -> LimitResult:
    """Set go or no-go from the three readings.

    Wind must be 25 knots or less, temperature 4 C or more, and fuel 98 to 100
    percent. A reading exactly on a limit passes. Any reading outside its limit
    makes the verdict no-go.
    """
    violations: list[str] = []
    if wind_knots > WIND_LIMIT_KNOTS:
        violations.append(
            f"Wind is {format_reading(wind_knots)} knots. The limit is 25 knots or less."
        )
    if temp_c < TEMP_LIMIT_C:
        violations.append(
            f"Temperature is {format_reading(temp_c)} C. The limit is 4 C or more."
        )
    if fuel_pct < FUEL_MIN_PCT or fuel_pct > FUEL_MAX_PCT:
        violations.append(
            f"Fuel is {format_reading(fuel_pct)} percent. The limit is 98 to 100 percent."
        )
    verdict = Verdict.NO_GO if violations else Verdict.GO
    assert (verdict is Verdict.NO_GO) == (len(violations) > 0)
    return LimitResult(verdict=verdict, violations=tuple(violations))
