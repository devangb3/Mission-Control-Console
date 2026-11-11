"""Report cost from token counts. The model does not price a report."""

from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field

from mission_control.domain import TraceStep

_MILLION = Decimal("1000000")
_QUANTUM = Decimal("0.000001")


class Pricing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_usd_per_million: Decimal = Field(ge=0)
    output_usd_per_million: Decimal = Field(ge=0)


def report_cost(steps: list[TraceStep], pricing: Pricing) -> Decimal:
    """Sum input and output tokens across every step, then apply the rates."""
    total = Decimal("0")
    for step in steps:
        total += (Decimal(step.tokens_in) * pricing.input_usd_per_million) / _MILLION
        total += (Decimal(step.tokens_out) * pricing.output_usd_per_million) / _MILLION
    return total.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def format_cost(amount: Decimal) -> str:
    """Six decimal places, so a short report still shows a non-zero cost."""
    return f"{amount.quantize(_QUANTUM, rounding=ROUND_HALF_UP):f}"
