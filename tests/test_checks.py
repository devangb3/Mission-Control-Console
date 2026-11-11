"""The three note checks run together, and a hidden instruction cannot move the verdict."""

import asyncio

from mission_control.domain import ReportStatus, Verdict
from mission_control.limits import evaluate_limits
from mission_control.model_client import ModelText
from mission_control.prompts import HIDDEN_STEP, MISSING_STEP, PANIC_STEP
from tests.scripted import ScriptedModelClient, ScriptedReply, as_json, scripted
from tests.support import HIDDEN_INSTRUCTION_NOTE, run_report, reading

_CHECKS = {HIDDEN_STEP, MISSING_STEP, PANIC_STEP}


class _OverlappingChecks:
    def __init__(self, inner: ScriptedModelClient) -> None:
        self.inner = inner
        self._arrived = 0
        self._release = asyncio.Event()
        self.max_in_flight = 0
        self._in_flight = 0

    async def complete(self, *, step: str, system: str, user: str) -> ModelText:
        if step in _CHECKS:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
            self._arrived += 1
            if self._arrived == 3:
                self._release.set()
            await asyncio.wait_for(self._release.wait(), timeout=1)
            self._in_flight -= 1
        return await self.inner.complete(step=step, system=system, user=user)


def test_the_three_checks_run_at_the_same_time() -> None:
    overlapping = _OverlappingChecks(scripted())
    report = run_report(reading(), overlapping)
    assert overlapping.max_in_flight == 3
    steps = [step for step, _system, _user in overlapping.inner.calls]
    assert steps[0] == "sort"
    assert set(steps[1:4]) == _CHECKS
    assert steps[4] == "draft"
    assert report.status is ReportStatus.PENDING


def test_hidden_instruction_note_is_flagged_and_does_not_change_a_no_go() -> None:
    report = run_report(
        reading(wind_knots=40, note=HIDDEN_INSTRUCTION_NOTE),
        scripted(
            sort=[as_json({"subsystem": "telemetry", "severity": "low", "verdict": "go"})],
            hidden=[as_json({"flagged": True, "reason": "The note instructs the system."})],
        ),
    )
    expected = evaluate_limits(wind_knots=40, temp_c=18, fuel_pct=99)
    assert report.verdict is expected.verdict
    assert report.verdict is Verdict.NO_GO
    assert tuple(report.violations) == expected.violations
    assert report.hidden_instruction is True
    assert report.flagged_for_review is True
    assert report.status is ReportStatus.PENDING
    assert report.approved_by is None
    assert report.note == HIDDEN_INSTRUCTION_NOTE


def test_hidden_instruction_note_does_not_turn_a_go_into_no_go() -> None:
    report = run_report(
        reading(note=HIDDEN_INSTRUCTION_NOTE),
        scripted(hidden=[as_json({"flagged": True, "reason": "The note instructs the system."})]),
    )
    assert report.verdict is Verdict.GO
    assert report.violations == []
    assert report.hidden_instruction is True
    assert report.flagged_for_review is True


def test_an_unreadable_check_is_flagged() -> None:
    report = run_report(
        reading(),
        scripted(hidden=[ScriptedReply("nope")]),
    )
    assert report.hidden_instruction is True
    assert report.verdict is Verdict.GO
