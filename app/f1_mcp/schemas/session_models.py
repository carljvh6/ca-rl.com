"""Schedule and session-facing typed structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class ScheduleEntry:
    """Serializable schedule entry used between provider and tool layers."""

    RoundNumber: int | None
    EventName: str | None
    Country: str | None
    Location: str | None
    EventDate: str | None

    def to_dict(self) -> dict:
        return asdict(self)

