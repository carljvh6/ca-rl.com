"""Lap dataframe extraction helpers."""

from __future__ import annotations

import pandas as pd

from .session_provider import load_session

LAP_COLUMNS = [
    "Driver",
    "LapNumber",
    "LapTime",
    "Compound",
    "PitInTime",
    "PitOutTime",
]


def get_driver_laps_df(
    year: int,
    race: str,
    session_type: str,
    driver_code: str,
) -> pd.DataFrame:
    """Return normalized lap rows for one driver with the columns used by the MCP tools."""
    session = load_session(year, race, session_type)
    driver_laps = session.laps[session.laps.Driver == driver_code][LAP_COLUMNS].copy()
    if driver_laps.empty:
        return driver_laps

    driver_laps = driver_laps[pd.notna(driver_laps["LapTime"])].copy()
    if driver_laps.empty:
        return driver_laps

    driver_laps["LapNumber"] = pd.to_numeric(driver_laps["LapNumber"], errors="coerce")
    driver_laps = driver_laps[pd.notna(driver_laps["LapNumber"])].copy()
    if driver_laps.empty:
        return driver_laps

    driver_laps["LapNumber"] = driver_laps["LapNumber"].astype(int)
    driver_laps["LapTimeSeconds"] = pd.to_numeric(
        driver_laps["LapTime"].dt.total_seconds(),
        errors="coerce",
    )
    driver_laps = driver_laps[pd.notna(driver_laps["LapTimeSeconds"])].copy()
    if driver_laps.empty:
        return driver_laps

    driver_laps = driver_laps.sort_values("LapNumber").reset_index(drop=True)
    return driver_laps

