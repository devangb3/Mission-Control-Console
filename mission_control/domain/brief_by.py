"""Brief-by time. Any limit violation counts as high, which is 5 minutes."""

from mission_control.domain import Severity

MINUTES_BY_SEVERITY: dict[Severity, int] = {
    Severity.HIGH: 5,
    Severity.MEDIUM: 15,
    Severity.LOW: 30,
}


def brief_by_minutes(*, severity: Severity, violation_count: int) -> tuple[Severity, int]:
    """Return the severity that sets the clock, and the minutes until the brief."""
    if violation_count < 0:
        raise ValueError("Violation count cannot be negative.")
    effective = Severity.HIGH if violation_count > 0 else severity
    minutes = MINUTES_BY_SEVERITY[effective]
    assert minutes in (5, 15, 30)
    return effective, minutes
