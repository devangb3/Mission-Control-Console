"""Turn model text into the schema each step requires."""

import json
import re
from dataclasses import dataclass

from mission_control.domain import Severity, Subsystem
from mission_control.errors import ModelOutputError

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_SUBSYSTEMS = {item.value for item in Subsystem}
_SEVERITIES = {item.value for item in Severity}


@dataclass(frozen=True)
class SortDecision:
    subsystem: Subsystem
    severity: Severity
    used_fallback: bool


@dataclass(frozen=True)
class CheckDecision:
    flagged: bool
    reason: str
    used_fallback: bool


@dataclass(frozen=True)
class ReviewDecision:
    accepted: bool
    feedback: str
    used_fallback: bool


def single_line(value: str) -> str:
    """Collapse whitespace so a labeled prompt field cannot spill onto the next line."""
    return " ".join(value.split())


def parse_json_object(text: str) -> dict[str, object]:
    """Read one JSON object, including a reply wrapped in a markdown fence."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        value: object = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ModelOutputError("The model did not return JSON.") from exc
    if not isinstance(value, dict):
        raise ModelOutputError("The model did not return a JSON object.")
    parsed: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ModelOutputError("The model returned a JSON object with a non-text key.")
        parsed[key] = item
    return parsed


def parse_sort(text: str) -> SortDecision:
    """Accept a known subsystem and severity. Anything else falls back safely.

    An unknown subsystem becomes ``unknown``. An unknown severity becomes
    ``high``, so the brief-by clock is the short one.
    """
    try:
        payload = parse_json_object(text)
    except ModelOutputError:
        return SortDecision(Subsystem.UNKNOWN, Severity.HIGH, True)

    used_fallback = False
    raw_subsystem = payload.get("subsystem")
    raw_severity = payload.get("severity")
    if isinstance(raw_subsystem, str) and raw_subsystem in _SUBSYSTEMS:
        subsystem = Subsystem(raw_subsystem)
    else:
        subsystem = Subsystem.UNKNOWN
        used_fallback = True
    if isinstance(raw_severity, str) and raw_severity in _SEVERITIES:
        severity = Severity(raw_severity)
    else:
        severity = Severity.HIGH
        used_fallback = True
    return SortDecision(subsystem, severity, used_fallback)


def parse_check(text: str) -> CheckDecision:
    """A check that is not a boolean plus a reason is treated as flagged."""
    try:
        payload = parse_json_object(text)
        flagged = payload.get("flagged")
        reason = payload.get("reason")
        if not isinstance(flagged, bool) or not isinstance(reason, str) or not reason.strip():
            raise ModelOutputError("The check reply is missing flagged or reason.")
        return CheckDecision(flagged, reason.strip(), False)
    except ModelOutputError:
        return CheckDecision(True, "The check was unreadable, so it was flagged.", True)


def parse_draft(text: str) -> str:
    """Return the briefing text. An empty draft is a hard failure."""
    payload = parse_json_object(text)
    briefing = payload.get("briefing")
    if not isinstance(briefing, str) or not briefing.strip():
        raise ModelOutputError("The draft did not include a briefing.")
    return briefing.strip()


def parse_review(text: str) -> ReviewDecision:
    """An unreadable review asks for another draft. It does not accept one."""
    try:
        payload = parse_json_object(text)
        accepted = payload.get("accepted")
        feedback = payload.get("feedback")
        if not isinstance(accepted, bool) or not isinstance(feedback, str):
            raise ModelOutputError("The review reply is missing accepted or feedback.")
        return ReviewDecision(accepted, single_line(feedback), False)
    except ModelOutputError:
        return ReviewDecision(
            False,
            "The review was unreadable. Rewrite the briefing from the recorded facts.",
            True,
        )
