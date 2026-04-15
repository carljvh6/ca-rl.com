"""Lap and stint-facing typed structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class LapRecord:
    """Serializable lap record preserving the existing MCP payload shape."""

    LapNumber: int
    LapTime: str
    LapTimeSeconds: float
    Compound: str | None
    PitInTime: str
    PitOutTime: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class LapSummary:
    """Summary metrics for a driver's laps."""

    lap_count: int
    valid_lap_count: int
    avg_lap_time_seconds: float | None
    best_lap_time_seconds: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class StintSummary:
    """Structured stint summary for higher-level analysis workflows."""

    stint_number: int
    compound: str | None
    start_lap: int
    end_lap: int
    lap_count: int
    avg_lap_time_seconds: float | None
    best_lap_time_seconds: float | None
    degradation_slope: float | None

    def to_dict(self) -> dict:
        return asdict(self)

