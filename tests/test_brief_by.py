"""Brief-by time follows severity, and any violation counts as high."""

import pytest

from mission_control.domain.brief_by import brief_by_minutes
from mission_control.domain import Severity


@pytest.mark.parametrize(
    ("severity", "violations", "effective", "minutes"),
    [
        (Severity.LOW, 0, Severity.LOW, 30),
        (Severity.MEDIUM, 0, Severity.MEDIUM, 15),
        (Severity.HIGH, 0, Severity.HIGH, 5),
        (Severity.LOW, 1, Severity.HIGH, 5),
        (Severity.MEDIUM, 2, Severity.HIGH, 5),
    ],
)
def test_brief_by_time(
    severity: Severity,
    violations: int,
    effective: Severity,
    minutes: int,
) -> None:
    assert brief_by_minutes(severity=severity, violation_count=violations) == (effective, minutes)
