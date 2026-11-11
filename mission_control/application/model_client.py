"""The only interface the pipeline uses to call a model."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelText:
    text: str
    tokens_in: int
    tokens_out: int

    def __post_init__(self) -> None:
        assert self.tokens_in >= 0
        assert self.tokens_out >= 0


class ModelClient(Protocol):
    async def complete(self, *, step: str, system: str, user: str) -> ModelText:
        """Return the model text and the token counts for this step."""
