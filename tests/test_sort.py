"""A sort reply is checked against a closed schema, and a bad value falls back."""

from mission_control.domain import Severity, Subsystem, Verdict
from mission_control.application.parsing import parse_sort
from tests.scripted import ScriptedReply, as_json, scripted
from tests.support import run_report, reading


def test_invalid_subsystem_and_severity_fall_back() -> None:
    decision = parse_sort('{"subsystem": "warp_core", "severity": "extreme"}')
    assert decision.subsystem is Subsystem.UNKNOWN
    assert decision.severity is Severity.HIGH
    assert decision.used_fallback is True


def test_invalid_json_falls_back_to_unknown_and_high() -> None:
    decision = parse_sort("not json")
    assert decision.subsystem is Subsystem.UNKNOWN
    assert decision.severity is Severity.HIGH
    assert decision.used_fallback is True


def test_a_bad_field_does_not_discard_a_good_one() -> None:
    decision = parse_sort('{"subsystem": "warp_core", "severity": "low"}')
    assert decision.subsystem is Subsystem.UNKNOWN
    assert decision.severity is Severity.LOW
    assert decision.used_fallback is True


def test_pipeline_uses_the_fallback_for_the_brief_by_clock() -> None:
    report = run_report(
        reading(),
        scripted(sort=[as_json({"subsystem": "warp_core", "severity": "extreme"})]),
    )
    assert report.subsystem is Subsystem.UNKNOWN
    assert report.model_severity is Severity.HIGH
    assert report.effective_severity is Severity.HIGH
    assert report.brief_by_minutes == 5
    assert report.verdict is Verdict.GO
    assert report.trace[0].summary.endswith("An invalid value fell back to this.")


def test_unreadable_sort_still_keeps_the_code_verdict() -> None:
    report = run_report(
        reading(wind_knots=30),
        scripted(sort=[ScriptedReply("this is not json")]),
    )
    assert report.subsystem is Subsystem.UNKNOWN
    assert report.model_severity is Severity.HIGH
    assert report.verdict is Verdict.NO_GO
    assert report.brief_by_minutes == 5
