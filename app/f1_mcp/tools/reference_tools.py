"""Reference-style MCP tool implementations for schedules and results."""

from __future__ import annotations

import logging

from f1_mcp.providers.schedule_provider import get_schedule_df
from f1_mcp.providers.session_provider import load_session, normalize_session_type
from f1_mcp.schemas.session_models import ScheduleEntry

logger = logging.getLogger("f1_mcp_server")


def get_f1_results(year: int, race: str, session_type: str = "R") -> dict:
    """Get F1 session results while preserving the current race-results payload shape."""
    logger.info("Getting F1 results for %s - %s (%s)", year, race, session_type)
    try:
        normalized_session_type = normalize_session_type(session_type)
        session = load_session(year, race, normalized_session_type)
        if not hasattr(session, "results") or session.results is None or session.results.empty:
            return {"error": f"No race data available for {year} - {race}"}

        preferred_cols = ["BroadcastName", "TeamName", "Position", "Time", "Status"]
        cls = [col for col in preferred_cols if col in session.results.columns]
        df = session.results[cls].sort_values(by="Position", ascending=True).copy()
        for col in ("Time", "Status"):
            if col in df.columns:
                df[col] = df[col].astype(str)
        return {
            "year": year,
            "race": race,
            "session_type": normalized_session_type,
            "results": df.to_dict("records"),
        }
    except Exception as exc:
        logger.error("Error getting F1 results: %s", exc)
        return {"error": str(exc)}


def get_f1_schedule(year: int) -> dict:
    """Get the season schedule while preserving the current payload shape."""
    logger.info("Getting F1 schedule for %s", year)
    try:
        schedule_df = get_schedule_df(year)
        if schedule_df.empty:
            return {"error": f"No schedule data available for {year}"}

        cols = ["RoundNumber", "EventName", "Country", "Location", "EventDate"]
        records = []
        for row in schedule_df[cols].copy().to_dict("records"):
            row["EventDate"] = str(row.get("EventDate")) if row.get("EventDate") is not None else None
            records.append(ScheduleEntry(**row).to_dict())
        return {"year": year, "schedule": records}
    except Exception as exc:
        logger.error("Error getting F1 schedule: %s", exc)
        return {"error": str(exc)}
