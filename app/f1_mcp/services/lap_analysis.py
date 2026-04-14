"""Helpers for normalizing laps and computing summary metrics."""

from __future__ import annotations

import pandas as pd

from f1_mcp.schemas.lap_models import LapRecord, LapSummary


def build_lap_records(laps_df: pd.DataFrame) -> list[dict]:
    """Convert a normalized lap dataframe into the existing serialized lap payload."""
    if laps_df.empty:
        return []

    lap_data = laps_df[
        ["LapNumber", "LapTime", "LapTimeSeconds", "Compound", "PitInTime", "PitOutTime"]
    ].copy()
    lap_data["LapTime"] = lap_data["LapTime"].astype(str)
    lap_data["PitInTime"] = lap_data["PitInTime"].astype(str)
    lap_data["PitOutTime"] = lap_data["PitOutTime"].astype(str)

    records: list[dict] = []
    for row in lap_data.to_dict("records"):
        record = LapRecord(**row)
        records.append(record.to_dict())
    return records


def summarize_laps(laps_df: pd.DataFrame) -> dict:
    """Compute core lap summary metrics from normalized lap rows."""
    if laps_df.empty:
        summary = LapSummary(
            lap_count=0,
            valid_lap_count=0,
            avg_lap_time_seconds=None,
            best_lap_time_seconds=None,
        )
        return summary.to_dict()

    lap_times = pd.to_numeric(laps_df["LapTimeSeconds"], errors="coerce").dropna()
    summary = LapSummary(
        lap_count=int(len(laps_df)),
        valid_lap_count=int(len(lap_times)),
        avg_lap_time_seconds=float(lap_times.mean()) if not lap_times.empty else None,
        best_lap_time_seconds=float(lap_times.min()) if not lap_times.empty else None,
    )
    return summary.to_dict()
