"""Session loading helpers for FastF1-backed F1 tools."""

from __future__ import annotations

from typing import Final

import fastf1

SUPPORTED_SESSION_TYPES: Final[tuple[str, ...]] = ("R", "Q", "SQ", "S", "FP1", "FP2", "FP3")
SESSION_TYPE_ALIASES: Final[dict[str, str]] = {
    "R": "R",
    "RACE": "R",
    "Q": "Q",
    "QUALI": "Q",
    "QUALIFYING": "Q",
    "Q3": "Q",
    "S": "S",
    "SPRINT": "S",
    "SQ": "SQ",
    "SPRINT QUALIFYING": "SQ",
    "SPRINT SHOOTOUT": "SQ",
    "SS": "SQ",
    "FP1": "FP1",
    "PRACTICE 1": "FP1",
    "P1": "FP1",
    "FP2": "FP2",
    "PRACTICE 2": "FP2",
    "P2": "FP2",
    "FP3": "FP3",
    "PRACTICE 3": "FP3",
    "P3": "FP3",
}


def session_type_error_payload(session_type: str | None) -> dict:
    """Return the standard user-facing error payload for unsupported session types."""
    return {
        "error": (
            f"Unsupported session_type '{session_type}'. Use one of: "
            f"{', '.join(SUPPORTED_SESSION_TYPES)}."
        )
    }


def describe_session_type(session_type: str | None) -> str:
    """Return a human-readable label for the normalized session type."""
    normalized = normalize_session_type(session_type)
    labels = {
        "R": "Race",
        "Q": "Qualifying",
        "SQ": "Sprint Qualifying",
        "S": "Sprint",
        "FP1": "Practice 1",
        "FP2": "Practice 2",
        "FP3": "Practice 3",
    }
    return labels[normalized]


def is_qualifying_session_type(session_type: str | None) -> bool:
    """Return whether the normalized session type is qualifying-style."""
    return normalize_session_type(session_type) in {"Q", "SQ"}


def normalize_session_type(session_type: str | None) -> str:
    """Normalize supported session aliases to FastF1 session types."""
    raw_value = " ".join(str(session_type or "R").strip().upper().split())
    normalized = SESSION_TYPE_ALIASES.get(raw_value)
    if normalized is None:
        raise ValueError(session_type_error_payload(session_type)["error"])
    return normalized


def load_session(year: int, race: str, session_type: str = "R"):
    """Load and return a FastF1 session with consistent session-type validation."""
    normalized_session_type = normalize_session_type(session_type)
    session = fastf1.get_session(year, race, normalized_session_type)
    session.load()
    return session
