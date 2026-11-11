"""Cost is tokens times the configured rates, calculated in code."""

from decimal import Decimal

from mission_control.domain.cost import Pricing, report_cost
from mission_control.domain import TraceStep
from tests.scripted import scripted
from tests.support import TEST_PRICING, run_report, reading


def test_cost_multiplies_tokens_by_the_rates() -> None:
    pricing = Pricing(
        input_usd_per_million=Decimal("1"),
        output_usd_per_million=Decimal("2"),
    )
    steps = [
        TraceStep(name="Sort the report", kind="model", tokens_in=1000, tokens_out=500, summary="telemetry, low."),
        TraceStep(name="Check launch limits", kind="code", tokens_in=0, tokens_out=0, summary="Go."),
    ]
    # 1000 * $1 / 1_000_000 + 500 * $2 / 1_000_000 = 0.002000
    assert report_cost(steps, pricing) == Decimal("0.002000")


def test_a_report_prices_every_model_step_and_ignores_code_steps() -> None:
    report = run_report(reading(), scripted())
    model_steps = [step for step in report.trace if step.kind == "model"]
    code_steps = [step for step in report.trace if step.kind == "code"]
    assert model_steps
    assert code_steps
    assert all(step.tokens_in == 0 and step.tokens_out == 0 for step in code_steps)
    assert all(step.tokens_in == 100 and step.tokens_out == 40 for step in model_steps)
    expected = report_cost(report.trace, TEST_PRICING)
    assert report.cost_usd == f"{expected:f}"
    assert Decimal(report.cost_usd) == expected
