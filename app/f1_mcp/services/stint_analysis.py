"""Stint detection and summary helpers for driver lap data."""

from __future__ import annotations

import pandas as pd

from f1_mcp.schemas.lap_models import StintSummary


def _timing_str_has_value(value) -> bool:
    text = str(value)
    return bool(text) and text.lower() not in {"nat", "nan", "none"}


def _calculate_degradation_slope(stint_df: pd.DataFrame) -> float | None:
    if len(stint_df) < 2:
        return None
    clean_df = stint_df[["LapNumber", "LapTimeSeconds"]].dropna().copy()
    if len(clean_df) < 2:
        return None
    x = clean_df["LapNumber"].astype(float)
    y = clean_df["LapTimeSeconds"].astype(float)
    slope = (y.iloc[-1] - y.iloc[0]) / (x.iloc[-1] - x.iloc[0]) if x.iloc[-1] != x.iloc[0] else None
    return float(slope) if slope is not None else None


def summarize_stints(laps_df: pd.DataFrame) -> list[dict]:
    """Infer stints from compound changes and pit markers and summarize each stint."""
    if laps_df.empty:
        return []

    df = laps_df.sort_values("LapNumber").reset_index(drop=True).copy()
    stints: list[pd.DataFrame] = []
    start_idx = 0
    previous_compound = df.iloc[0].get("Compound")

    for idx in range(1, len(df)):
        row = df.iloc[idx]
        prev_row = df.iloc[idx - 1]
        compound_changed = row.get("Compound") != previous_compound
        pit_boundary = _timing_str_has_value(prev_row.get("PitInTime")) or _timing_str_has_value(
            row.get("PitOutTime")
        )
        if compound_changed or pit_boundary:
            stints.append(df.iloc[start_idx:idx].copy())
            start_idx = idx
            previous_compound = row.get("Compound")
    stints.append(df.iloc[start_idx:].copy())

    summaries: list[dict] = []
    for stint_number, stint_df in enumerate(stints, start=1):
        lap_times = pd.to_numeric(stint_df["LapTimeSeconds"], errors="coerce").dropna()
        stint = StintSummary(
            stint_number=stint_number,
            compound=stint_df.iloc[0].get("Compound"),
            start_lap=int(stint_df["LapNumber"].min()),
            end_lap=int(stint_df["LapNumber"].max()),
            lap_count=int(len(stint_df)),
            avg_lap_time_seconds=float(lap_times.mean()) if not lap_times.empty else None,
            best_lap_time_seconds=float(lap_times.min()) if not lap_times.empty else None,
            degradation_slope=_calculate_degradation_slope(stint_df),
        )
        summaries.append(stint.to_dict())
    return summaries
