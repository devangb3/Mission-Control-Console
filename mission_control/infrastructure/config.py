"""Environment configuration and production model construction."""

import os
from decimal import Decimal, InvalidOperation
from pydantic import ValidationError
from mission_control.domain.cost import Pricing
from mission_control.domain.errors import FoundryConfigError
from mission_control.infrastructure.foundry import FoundryModelClient
from mission_control.application.model_client import ModelClient

def build_model_client() -> ModelClient:
    return FoundryModelClient.from_env()


def pricing_from_env() -> Pricing:
    raw_input = os.environ.get("FOUNDRY_INPUT_USD_PER_MILLION", "0.15")
    raw_output = os.environ.get("FOUNDRY_OUTPUT_USD_PER_MILLION", "0.60")
    try:
        return Pricing(
            input_usd_per_million=Decimal(raw_input),
            output_usd_per_million=Decimal(raw_output),
        )
    except (InvalidOperation, ValidationError) as exc:
        raise FoundryConfigError(
            "Token prices must be numbers, zero or more, in dollars per million tokens."
        ) from exc


def _default_pricing() -> Pricing:
    return Pricing(input_usd_per_million=Decimal("0.15"), output_usd_per_million=Decimal("0.60"))


