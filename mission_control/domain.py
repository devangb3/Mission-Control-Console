"""Facts the console stores for one anomaly report."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Subsystem(str, Enum):
    PROPULSION = "propulsion"
    AVIONICS = "avionics"
    TELEMETRY = "telemetry"
    GROUND = "ground"
    WEATHER = "weather"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Verdict(str, Enum):
    GO = "go"
    NO_GO = "no_go"


class ReportStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"


class ReportInput(BaseModel):
    """What an engineer files. The verdict is not one of these fields."""

    model_config = ConfigDict(extra="forbid")

    engineer_name: str
    station: str
    wind_knots: float
    temp_c: float
    fuel_pct: float
    note: str


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["model", "code"]
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    summary: str


class DraftRound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1, le=3)
    briefing: str
    accepted: bool
    feedback: str


class ReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    engineer_name: str
    station: str
    wind_knots: float
    temp_c: float
    fuel_pct: float
    note: str
    subsystem: Subsystem
    model_severity: Severity
    effective_severity: Severity
    verdict: Verdict
    violations: list[str]
    brief_by_minutes: int
    hidden_instruction: bool
    missing_details: bool
    panic_tone: bool
    flagged_for_review: bool
    briefing: str
    rounds: list[DraftRound]
    status: ReportStatus
    approved_by: str | None
    cost_usd: str
    trace: list[TraceStep]
    created_at: str
