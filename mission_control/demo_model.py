"""Offline stand-in for Foundry. It reads the prompt and never decides the verdict."""

import json
import re

from mission_control.errors import ModelOutputError
from mission_control.model_client import ModelText
from mission_control.prompts import (
    DRAFT_STEP,
    HIDDEN_STEP,
    MISSING_STEP,
    PANIC_STEP,
    REVIEW_STEP,
    SORT_STEP,
)

_HIDDEN_PHRASES = (
    "ignore previous",
    "ignore all",
    "set the verdict",
    "disregard",
    "you are now",
    "system prompt",
)
_PANIC_PHRASES = ("panic", "we're going to die", "we are going to die", "oh no")


class DemoModelClient:
    """A deterministic client for the console when no Foundry key is configured."""

    async def complete(self, *, step: str, system: str, user: str) -> ModelText:
        del system
        if step == SORT_STEP:
            return ModelText(text=json.dumps(self._sort(user)), tokens_in=220, tokens_out=30)
        if step == HIDDEN_STEP:
            return ModelText(text=json.dumps(self._hidden(user)), tokens_in=160, tokens_out=24)
        if step == MISSING_STEP:
            return ModelText(text=json.dumps(self._missing(user)), tokens_in=160, tokens_out=24)
        if step == PANIC_STEP:
            return ModelText(text=json.dumps(self._panic(user)), tokens_in=160, tokens_out=24)
        if step == DRAFT_STEP:
            return ModelText(text=json.dumps(self._draft(user)), tokens_in=280, tokens_out=70)
        if step == REVIEW_STEP:
            return ModelText(text=json.dumps(self._review(user)), tokens_in=200, tokens_out=20)
        raise ModelOutputError(f"The demo model has no reply for {step}.")

    def _sort(self, user: str) -> dict[str, str]:
        note = _note(user).lower()
        station = _first_label(user, "Station").lower()
        blob = f"{note} {station}"
        if any(word in blob for word in ("telemetry", "link", "signal", "downlink")):
            subsystem = "telemetry"
        elif any(word in blob for word in ("valve", "engine", "propellant", "fuel", "pressur")):
            subsystem = "propulsion"
        elif any(word in blob for word in ("wind", "weather", "gust")):
            subsystem = "weather"
        elif any(word in blob for word in ("pad", "tower", "gantry", "ground support")):
            subsystem = "ground"
        else:
            subsystem = "avionics"
        if "panic" in note or "critical" in note or "!!!" in _note(user):
            severity = "high"
        elif "twitch" in note or "minor" in note:
            severity = "low"
        else:
            severity = "medium"
        return {"subsystem": subsystem, "severity": severity}

    def _hidden(self, user: str) -> dict[str, object]:
        note = _note(user).lower()
        flagged = any(phrase in note for phrase in _HIDDEN_PHRASES)
        reason = (
            "The note tells the system what verdict to produce."
            if flagged
            else "The note describes an observation and does not instruct the system."
        )
        return {"flagged": flagged, "reason": reason}

    def _missing(self, user: str) -> dict[str, object]:
        words = _note(user).split()
        flagged = len(words) < 8
        reason = (
            "The note does not say what was observed and what happened next."
            if flagged
            else "The note names an observation."
        )
        return {"flagged": flagged, "reason": reason}

    def _panic(self, user: str) -> dict[str, object]:
        note = _note(user).lower()
        flagged = "!!!" in _note(user) or any(phrase in note for phrase in _PANIC_PHRASES)
        reason = (
            "The tone is panicked."
            if flagged
            else "The tone is operational."
        )
        return {"flagged": flagged, "reason": reason}

    def _draft(self, user: str) -> dict[str, str]:
        verdict = _last_label(user, "Verdict")
        spoken = "go" if verdict == "go" else "no-go"
        engineer = _first_label(user, "Engineer")
        station = _first_label(user, "Station")
        minutes = _last_label(user, "Brief-by minutes")
        hidden = _last_label(user, "Hidden instructions")
        feedback = _last_label(user, "Review feedback")
        violations = _between(user, "Violations:\n", "\nBrief-by minutes:")
        sentences = [
            f"{engineer} at {station} filed an anomaly. The verdict is {spoken}.",
        ]
        if violations == "- none":
            sentences.append("No launch limit was missed.")
        else:
            detail = " ".join(line.removeprefix("- ").strip() for line in violations.splitlines())
            sentences.append(detail)
        sentences.append(f"Brief the director within {minutes} minutes.")
        if hidden == "yes":
            sentences.append("The note tried to give instructions. Those instructions were not followed.")
        if feedback != "none":
            sentences.insert(0, f"Revised after review: {feedback}")
        return {"briefing": " ".join(sentences)}

    def _review(self, user: str) -> dict[str, object]:
        verdict = _last_label(user, "Verdict")
        briefing = _after(user, "\nBriefing:\n").lower()
        if verdict == "no_go":
            accepted = "no-go" in briefing
            feedback = "" if accepted else "State the verdict as no-go."
        else:
            accepted = "no-go" not in briefing and re.search(r"\bgo\b", briefing) is not None
            feedback = "" if accepted else "State the verdict as go."
        return {"accepted": accepted, "feedback": feedback}


def _note(user: str) -> str:
    start = user.find("<note>")
    end = user.find("</note>", start + len("<note>"))
    if start < 0 or end < 0:
        raise ModelOutputError("Demo model could not find the note.")
    return user[start + len("<note>") : end].strip()


def _first_label(user: str, label: str) -> str:
    return _label(user, label, last=False)


def _last_label(user: str, label: str) -> str:
    return _label(user, label, last=True)


def _label(user: str, label: str, *, last: bool) -> str:
    prefix = f"{label}: "
    found: str | None = None
    for line in user.splitlines():
        if line.startswith(prefix):
            found = line[len(prefix) :].strip()
            if not last:
                return found
    if found is None:
        raise ModelOutputError(f"Demo model could not find {label}.")
    return found


def _between(user: str, start: str, end: str) -> str:
    start_at = user.find(start)
    if start_at < 0:
        raise ModelOutputError(f"Demo model could not find {start.strip()}.")
    rest = user[start_at + len(start) :]
    end_at = rest.find(end)
    if end_at < 0:
        raise ModelOutputError(f"Demo model could not find {end.strip()}.")
    return rest[:end_at].strip()


def _after(user: str, marker: str) -> str:
    at = user.rfind(marker)
    if at < 0:
        raise ModelOutputError(f"Demo model could not find {marker.strip()}.")
    return user[at + len(marker) :].strip()
