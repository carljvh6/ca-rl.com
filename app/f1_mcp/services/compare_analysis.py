"""Reusable two-driver comparison analysis for MCP tools and web routes."""

from __future__ import annotations

import pandas as pd

from f1_mcp.schemas.comparison_models import (
    ComparisonSummary,
    PitStopRecord,
    SignificantDeltaLap,
)


def _timing_str_has_value(value) -> bool:
    text = str(value)
    return bool(text) and text.lower() not in {"nat", "nan", "none"}


def extract_pit_stops(lap_data: list[dict]) -> list[dict]:
    """Extract pit stop records from serialized lap payloads."""
    pit_stops: list[dict] = []
    for lap in lap_data:
        pit_in = lap.get("PitInTime")
        pit_out = lap.get("PitOutTime")
        if _timing_str_has_value(pit_in) or _timing_str_has_value(pit_out):
            pit_stop = PitStopRecord(
                lap=int(lap.get("LapNumber")),
                pit_in=str(pit_in) if _timing_str_has_value(pit_in) else None,
                pit_out=str(pit_out) if _timing_str_has_value(pit_out) else None,
            )
            pit_stops.append(pit_stop.to_dict())
    return pit_stops


def extract_pit_stop_laps(lap_data: list[dict]) -> list[int]:
    """Return lap numbers where pit-in or pit-out timing exists."""
    return [pit_stop["lap"] for pit_stop in extract_pit_stops(lap_data)]


def compare_two_drivers(
    driver1_code: str,
    driver1_lap_data: list[dict],
    driver2_code: str,
    driver2_lap_data: list[dict],
    significant_delta_threshold: float = 0.5,
) -> dict:
    """Compute a reusable comparison summary from two serialized lap datasets."""
    driver1_df = pd.DataFrame(driver1_lap_data)
    driver2_df = pd.DataFrame(driver2_lap_data)

    for df in (driver1_df, driver2_df):
        if not df.empty:
            df["LapNumber"] = pd.to_numeric(df["LapNumber"], errors="coerce")
            df["LapTimeSeconds"] = pd.to_numeric(df["LapTimeSeconds"], errors="coerce")
            df.dropna(subset=["LapNumber", "LapTimeSeconds"], inplace=True)
            df["LapNumber"] = df["LapNumber"].astype(int)

    merged = pd.merge(
        driver1_df[["LapNumber", "LapTimeSeconds"]],
        driver2_df[["LapNumber", "LapTimeSeconds"]],
        on="LapNumber",
        how="inner",
        suffixes=(f"_{driver1_code}", f"_{driver2_code}"),
    ).sort_values("LapNumber")

    same_lap_deltas: list[dict] = []
    significant_delta_laps: list[dict] = []
    for row in merged.to_dict("records"):
        driver1_time = float(row[f"LapTimeSeconds_{driver1_code}"])
        driver2_time = float(row[f"LapTimeSeconds_{driver2_code}"])
        delta = driver1_time - driver2_time
        same_lap_deltas.append(
            {
                "lap": int(row["LapNumber"]),
                f"{driver1_code}_time": driver1_time,
                f"{driver2_code}_time": driver2_time,
                "delta_seconds": delta,
                "faster_driver": driver1_code if delta < 0 else driver2_code if delta > 0 else "TIE",
            }
        )
        if abs(delta) > significant_delta_threshold:
            significant = SignificantDeltaLap(
                lap=int(row["LapNumber"]),
                driver1_time=driver1_time,
                driver2_time=driver2_time,
                difference=abs(delta),
                slower_driver=driver1_code if delta > 0 else driver2_code,
            )
            significant_record = significant.to_dict()
            significant_record[f"{driver1_code}_time"] = significant_record.pop("driver1_time")
            significant_record[f"{driver2_code}_time"] = significant_record.pop("driver2_time")
            significant_delta_laps.append(significant_record)

    driver1_times = driver1_df.get("LapTimeSeconds", pd.Series(dtype=float))
    driver2_times = driver2_df.get("LapTimeSeconds", pd.Series(dtype=float))
    summary = ComparisonSummary(
        driver1_code=driver1_code,
        driver2_code=driver2_code,
        driver1_avg=float(driver1_times.mean()) if not driver1_times.empty else None,
        driver2_avg=float(driver2_times.mean()) if not driver2_times.empty else None,
        driver1_best=float(driver1_times.min()) if not driver1_times.empty else None,
        driver2_best=float(driver2_times.min()) if not driver2_times.empty else None,
        driver1_slowest=float(driver1_times.max()) if not driver1_times.empty else None,
        driver2_slowest=float(driver2_times.max()) if not driver2_times.empty else None,
        same_lap_deltas=same_lap_deltas,
        driver1_pit_stops=extract_pit_stops(driver1_lap_data),
        driver2_pit_stops=extract_pit_stops(driver2_lap_data),
        significant_delta_laps=significant_delta_laps,
    )
    return summary.to_dict()
