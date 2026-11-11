"""Launch limits are code, including the exact boundary and the step just past it."""

import inspect

import pytest

from mission_control.domain import Verdict
from mission_control.domain.limits import evaluate_limits

@pytest.mark.parametrize(
    ("wind", "temp", "fuel", "verdict", "count"),
    [
        (25, 4, 98, Verdict.GO, 0),
        (25, 4, 100, Verdict.GO, 0),
        (0, 4, 98, Verdict.GO, 0),
        (24.9, 4, 99, Verdict.GO, 0),
        (25.1, 4, 100, Verdict.NO_GO, 1),
        (26, 4, 99, Verdict.NO_GO, 1),
        (25, 3.9, 99, Verdict.NO_GO, 1),
        (25, 3, 99, Verdict.NO_GO, 1),
        (25, 4, 97.9, Verdict.NO_GO, 1),
        (25, 4, 97, Verdict.NO_GO, 1),
        (25, 4, 100.1, Verdict.NO_GO, 1),
        (25, 4, 101, Verdict.NO_GO, 1),
        (26, 3, 50, Verdict.NO_GO, 3),
    ],
)
def test_limits_on_the_boundary_and_just_past(
    wind: float,
    temp: float,
    fuel: float,
    verdict: Verdict,
    count: int,
) -> None:
    result = evaluate_limits(wind_knots=wind, temp_c=temp, fuel_pct=fuel)
    assert result.verdict is verdict
    assert len(result.violations) == count
    if wind > 25:
        assert any("25 knots or less" in item for item in result.violations)
    if temp < 4:
        assert any("4 C or more" in item for item in result.violations)
    if fuel < 98 or fuel > 100:
        assert any("98 to 100 percent" in item for item in result.violations)


def test_limits_do_not_read_the_note() -> None:
    assert "note" not in inspect.signature(evaluate_limits).parameters
