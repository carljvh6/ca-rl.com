"""Typed structures for two-driver lap comparisons."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class PitStopRecord:
    """Serializable pit stop marker for one lap."""

    lap: int
    pit_in: str | None
    pit_out: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SignificantDeltaLap:
    """Significant same-lap pace delta between two drivers."""

    lap: int
    driver1_time: float
    driver2_time: float
    difference: float
    slower_driver: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class ComparisonSummary:
    """Serializable comparison output shared by services, tools, and the web UI."""

    driver1_code: str
    driver2_code: str
    driver1_avg: float | None
    driver2_avg: float | None
    driver1_best: float | None
    driver2_best: float | None
    driver1_slowest: float | None
    driver2_slowest: float | None
    same_lap_deltas: list[dict]
    driver1_pit_stops: list[dict]
    driver2_pit_stops: list[dict]
    significant_delta_laps: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)

