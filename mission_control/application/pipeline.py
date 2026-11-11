"""Run one report from filing to a briefing that is waiting for a person."""

import asyncio
import uuid
from datetime import datetime, timezone

from mission_control.domain.brief_by import brief_by_minutes
from mission_control.domain.cost import Pricing, format_cost, report_cost
from mission_control.domain import (
    DraftRound,
    ReportInput,
    ReportRecord,
    ReportStatus,
    TraceStep,
    Verdict,
)
from mission_control.domain.limits import evaluate_limits
from mission_control.application.model_client import ModelClient, ModelText
from mission_control.application.parsing import parse_check, parse_draft, parse_review, parse_sort
from mission_control.application.prompts import (
    DRAFT_STEP,
    HIDDEN_STEP,
    MISSING_STEP,
    PANIC_STEP,
    REVIEW_STEP,
    SORT_STEP,
    check_prompt,
    draft_prompt,
    review_prompt,
    sort_prompt,
)

_MAX_ROUNDS = 3


class ReportPipeline:
    """Reusable report workflow; each invocation keeps its own execution state."""

    def __init__(self, model: ModelClient, pricing: Pricing) -> None:
        self._model = model
        self._pricing = pricing

    async def build(self, report_input: ReportInput) -> ReportRecord:
        """Sort, judge the readings in code, check the note, and draft a briefing.

        The verdict comes only from ``evaluate_limits``. A note that tries to give
        instructions is flagged and the briefing stays pending for a person.
        """
        trace: list[TraceStep] = []

        sort_system, sort_user = sort_prompt(report_input)
        sort_text = await self._model.complete(step=SORT_STEP, system=sort_system, user=sort_user)
        sort = parse_sort(sort_text.text)
        sort_summary = f"{sort.subsystem.value}, {sort.severity.value}."
        if sort.used_fallback:
            sort_summary = f"{sort_summary} An invalid value fell back to this."
        trace.append(_model_step("Sort the report", sort_text, sort_summary))

        limits = evaluate_limits(
            wind_knots=report_input.wind_knots,
            temp_c=report_input.temp_c,
            fuel_pct=report_input.fuel_pct,
        )
        if limits.verdict is Verdict.GO:
            limit_summary = "Go. Every reading is inside its limit."
        else:
            limit_summary = "No-go. " + " ".join(limits.violations)
        trace.append(_code_step("Check launch limits", limit_summary))

        effective, minutes = brief_by_minutes(
            severity=sort.severity,
            violation_count=len(limits.violations),
        )
        if limits.violations:
            brief_summary = f"{minutes} minutes. A missed limit counts as high."
        else:
            brief_summary = f"{minutes} minutes, from {effective.value} severity."
        trace.append(_code_step("Set the brief-by time", brief_summary))

        hidden_system, hidden_user = check_prompt(report_input, HIDDEN_STEP)
        missing_system, missing_user = check_prompt(report_input, MISSING_STEP)
        panic_system, panic_user = check_prompt(report_input, PANIC_STEP)
        hidden_text, missing_text, panic_text = await asyncio.gather(
            self._model.complete(step=HIDDEN_STEP, system=hidden_system, user=hidden_user),
            self._model.complete(step=MISSING_STEP, system=missing_system, user=missing_user),
            self._model.complete(step=PANIC_STEP, system=panic_system, user=panic_user),
        )
        hidden = parse_check(hidden_text.text)
        missing = parse_check(missing_text.text)
        panic = parse_check(panic_text.text)
        trace.append(_model_step("Check for hidden instructions", hidden_text, _check_summary(hidden.flagged, hidden.reason)))
        trace.append(_model_step("Check for missing details", missing_text, _check_summary(missing.flagged, missing.reason)))
        trace.append(_model_step("Check the tone", panic_text, _check_summary(panic.flagged, panic.reason)))

        if hidden.flagged:
            hold_summary = (
                "Hidden instructions were flagged. A person has to approve this briefing. "
                "The verdict was not changed."
            )
        else:
            hold_summary = "No hidden instructions. A person still has to approve this briefing."
        trace.append(_code_step("Hold for the flight director", hold_summary))

        feedback = ""
        rounds: list[DraftRound] = []
        briefing = ""
        for number in range(1, _MAX_ROUNDS + 1):
            draft_system, draft_user = draft_prompt(
                report=report_input,
                verdict=limits.verdict,
                violations=limits.violations,
                brief_by=minutes,
                effective_severity=effective,
                hidden_instruction=hidden.flagged,
                missing_details=missing.flagged,
                panic_tone=panic.flagged,
                feedback=feedback,
            )
            draft_text = await self._model.complete(step=DRAFT_STEP, system=draft_system, user=draft_user)
            briefing = parse_draft(draft_text.text)
            draft_name = "Draft the briefing" if number == 1 else f"Draft the briefing, round {number}"
            trace.append(_model_step(draft_name, draft_text, briefing))

            review_system, review_user = review_prompt(
                report=report_input,
                verdict=limits.verdict,
                violations=limits.violations,
                briefing=briefing,
                hidden_instruction=hidden.flagged,
            )
            review_text = await self._model.complete(step=REVIEW_STEP, system=review_system, user=review_user)
            review = parse_review(review_text.text)
            review_name = "Review the briefing" if number == 1 else f"Review the briefing, round {number}"
            if review.accepted:
                review_summary = "Accepted."
            else:
                review_summary = f"Changes requested. {review.feedback}"
            trace.append(_model_step(review_name, review_text, review_summary))
            rounds.append(
                DraftRound(
                    round_number=number,
                    briefing=briefing,
                    accepted=review.accepted,
                    feedback=review.feedback,
                )
            )
            if review.accepted:
                break
            feedback = review.feedback

        assert 1 <= len(rounds) <= _MAX_ROUNDS
        assert limits.verdict is evaluate_limits(
            wind_knots=report_input.wind_knots,
            temp_c=report_input.temp_c,
            fuel_pct=report_input.fuel_pct,
        ).verdict

        record = ReportRecord(
            id=str(uuid.uuid4()),
            engineer_name=report_input.engineer_name,
            station=report_input.station,
            wind_knots=report_input.wind_knots,
            temp_c=report_input.temp_c,
            fuel_pct=report_input.fuel_pct,
            note=report_input.note,
            subsystem=sort.subsystem,
            model_severity=sort.severity,
            effective_severity=effective,
            verdict=limits.verdict,
            violations=list(limits.violations),
            brief_by_minutes=minutes,
            hidden_instruction=hidden.flagged,
            missing_details=missing.flagged,
            panic_tone=panic.flagged,
            flagged_for_review=hidden.flagged,
            briefing=briefing,
            rounds=rounds,
            status=ReportStatus.PENDING,
            approved_by=None,
            cost_usd=format_cost(report_cost(trace, self._pricing)),
            trace=trace,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        assert record.status is ReportStatus.PENDING
        assert record.approved_by is None
        return record


async def build_report(
    report_input: ReportInput, model: ModelClient, pricing: Pricing,
) -> ReportRecord:
    """Compatibility entry point for callers using the functional API."""
    return await ReportPipeline(model, pricing).build(report_input)


def _model_step(name: str, result: ModelText, summary: str) -> TraceStep:
    return TraceStep(
        name=name,
        kind="model",
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        summary=summary,
    )


def _code_step(name: str, summary: str) -> TraceStep:
    return TraceStep(name=name, kind="code", tokens_in=0, tokens_out=0, summary=summary)


def _check_summary(flagged: bool, reason: str) -> str:
    prefix = "Flagged. " if flagged else "Clear. "
    return prefix + reason
