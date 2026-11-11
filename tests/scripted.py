"""Scripted model replies for tests. Nothing here opens a socket."""

import json
from dataclasses import dataclass

from mission_control.model_client import ModelText


@dataclass(frozen=True)
class ScriptedReply:
    text: str
    tokens_in: int = 100
    tokens_out: int = 40


class ScriptExhausted(Exception):
    def __init__(self, step: str) -> None:
        super().__init__(f"No scripted reply left for {step}.")
        self.step = step


class ScriptedModelClient:
    def __init__(self, queues: dict[str, list[ScriptedReply]]) -> None:
        self._queues = {step: list(replies) for step, replies in queues.items()}
        self.calls: list[tuple[str, str, str]] = []

    async def complete(self, *, step: str, system: str, user: str) -> ModelText:
        self.calls.append((step, system, user))
        queue = self._queues.get(step)
        if queue is None or not queue:
            raise ScriptExhausted(step)
        reply = queue.pop(0)
        return ModelText(text=reply.text, tokens_in=reply.tokens_in, tokens_out=reply.tokens_out)


def as_json(
    payload: dict[str, object],
    *,
    tokens_in: int = 100,
    tokens_out: int = 40,
) -> ScriptedReply:
    return ScriptedReply(json.dumps(payload), tokens_in, tokens_out)


def scripted(
    *,
    sort: list[ScriptedReply] | None = None,
    hidden: list[ScriptedReply] | None = None,
    missing: list[ScriptedReply] | None = None,
    panic: list[ScriptedReply] | None = None,
    drafts: list[ScriptedReply] | None = None,
    reviews: list[ScriptedReply] | None = None,
) -> ScriptedModelClient:
    clear = as_json({"flagged": False, "reason": "Nothing in the note raised this check."})
    return ScriptedModelClient(
        {
            "sort": sort or [as_json({"subsystem": "telemetry", "severity": "low"})],
            "hidden_instructions": hidden or [clear],
            "missing_details": missing or [clear],
            "panic_tone": panic or [clear],
            "draft": drafts or [as_json({"briefing": "A short briefing for the flight director."})],
            "review": reviews or [as_json({"accepted": True, "feedback": ""})],
        }
    )
