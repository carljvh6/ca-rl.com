"""Session loading helpers for FastF1-backed F1 tools."""

from __future__ import annotations

from typing import Final

import fastf1

VALID_SESSION_TYPES: Final[set[str]] = {"FP1", "FP2", "FP3", "Q", "S", "SQ", "SS", "R"}


def normalize_session_type(session_type: str | None) -> str:
    """Normalize and validate FastF1 session types, defaulting to race sessions."""
    normalized = (session_type or "R").upper()
    if normalized not in VALID_SESSION_TYPES:
        raise ValueError(
            f"Invalid session_type '{session_type}'. Expected one of: {', '.join(sorted(VALID_SESSION_TYPES))}"
        )
    return normalized


def load_session(year: int, race: str, session_type: str = "R"):
    """Load and return a FastF1 session with consistent session-type validation."""
    normalized_session_type = normalize_session_type(session_type)
    session = fastf1.get_session(year, race, normalized_session_type)
    session.load()
    return session

