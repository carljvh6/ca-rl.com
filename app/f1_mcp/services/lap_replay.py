"""Lap replay payload builder for animated two-lap comparisons."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from f1_mcp.providers.session_provider import describe_session_type, is_qualifying_session_type, load_session, normalize_session_type
from f1_mcp.services.qualifying_analysis import assign_qualifying_segments, classify_qualifying_laps

SUPPORTED_LAP_SELECTORS = {
    "best_valid_lap",
    "best_valid_push_lap",
    "fastest_lap",
    "best_q1_lap",
    "best_q2_lap",
    "best_q3_lap",
}
REPLAY_SAMPLE_COUNT = 240
MAP_POINT_COUNT = 320


def compare_lap_replay(
    year: int,
    race: str,
    session_type: str,
    driver_code1: str,
    driver_code2: str,
    lap_selector1: str = "best_valid_lap",
    lap_selector2: str = "best_valid_lap",
) -> dict:
    """Resolve two laps, build telemetry-aligned samples, and return replay JSON."""
    normalized_session_type = normalize_session_type(session_type)
    session = load_session(year, race, normalized_session_type)
    all_laps = getattr(session, "laps", None)
    if all_laps is None or getattr(all_laps, "empty", True):
        return {"error": f"No lap data available for {year} - {race} ({normalized_session_type})"}

    driver_code1 = str(driver_code1).upper()
    driver_code2 = str(driver_code2).upper()
    driver_laps1 = _prepare_driver_laps(session, all_laps, driver_code1, normalized_session_type)
    driver_laps2 = _prepare_driver_laps(session, all_laps, driver_code2, normalized_session_type)

    if driver_laps1.empty:
        return {"error": f"No lap data found for driver {driver_code1} in {year} - {race} ({normalized_session_type})"}
    if driver_laps2.empty:
        return {"error": f"No lap data found for driver {driver_code2} in {year} - {race} ({normalized_session_type})"}

    resolved1 = _resolve_driver_lap(driver_laps1, driver_code1, lap_selector1, normalized_session_type)
    resolved2 = _resolve_driver_lap(driver_laps2, driver_code2, lap_selector2, normalized_session_type)
    if "error" in resolved1:
        return resolved1
    if "error" in resolved2:
        return resolved2

    lap1 = _build_lap_payload(session, resolved1)
    lap2 = _build_lap_payload(session, resolved2)
    circuit = _build_circuit_payload(session, lap1, lap2)
    real_time = _build_real_time_samples(lap1, lap2, circuit.get("corners", []))
    equal_progress = _build_equal_progress_samples(lap1, lap2, circuit.get("corners", []))

    session_label = describe_session_type(normalized_session_type)
    return {
        "year": year,
        "race": race,
        "session_type": normalized_session_type,
        "title": f"Lap Replay - {driver_code1} vs {driver_code2}",
        "subtitle": (
            f"{race} {year} {session_label}: "
            f"{_describe_resolved_lap(lap1)} vs {_describe_resolved_lap(lap2)}"
        ),
        "mode_default": "real_time",
        "drivers": {
            driver_code1: _lap_header_payload(lap1, "#ff6b57"),
            driver_code2: _lap_header_payload(lap2, "#4ea1ff"),
        },
        "circuit": circuit,
        "modes": {
            "real_time": real_time,
            "equal_progress": equal_progress,
        },
    }


def _prepare_driver_laps(session, all_laps: pd.DataFrame, driver_code: str, session_type: str) -> pd.DataFrame:
    driver_laps = all_laps[all_laps["Driver"] == driver_code].copy()
    if driver_laps.empty:
        return driver_laps
    driver_laps["LapNumber"] = pd.to_numeric(driver_laps.get("LapNumber"), errors="coerce")
    driver_laps = driver_laps[pd.notna(driver_laps["LapNumber"])].copy()
    if driver_laps.empty:
        return driver_laps
    driver_laps["LapNumber"] = driver_laps["LapNumber"].astype(int)
    if "LapTimeSeconds" not in driver_laps.columns:
        driver_laps["LapTimeSeconds"] = driver_laps.get("LapTime", pd.Series(dtype="object")).map(_to_seconds)
    else:
        driver_laps["LapTimeSeconds"] = driver_laps["LapTimeSeconds"].map(_to_seconds)

    if is_qualifying_session_type(session_type):
        driver_laps = assign_qualifying_segments(session, driver_laps, driver_code)
        driver_laps = classify_qualifying_laps(driver_laps)
    else:
        deleted = driver_laps["Deleted"].map(_to_bool) if "Deleted" in driver_laps.columns else False
        accurate = (
            driver_laps["IsAccurate"].map(lambda value: _to_bool(value, default=True))
            if "IsAccurate" in driver_laps.columns
            else True
        )
        driver_laps["IsValid"] = driver_laps["LapTimeSeconds"].notna() & (~deleted) & accurate
    return driver_laps.sort_values("LapNumber").reset_index(drop=True)


def _resolve_driver_lap(driver_laps: pd.DataFrame, driver_code: str, selector: str, session_type: str) -> dict:
    raw_selector = str(selector or "best_valid_lap").strip()
    selector_key = raw_selector.lower().replace("-", "_").replace(" ", "_")
    explicit_lap = _parse_explicit_lap_number(selector_key)
    if explicit_lap is not None:
        lap_df = driver_laps[driver_laps["LapNumber"] == explicit_lap]
        if lap_df.empty:
            return {"error": f"Lap {explicit_lap} was not found for driver {driver_code}."}
        lap = lap_df.iloc[0]
        if lap.get("LapTimeSeconds") is None or pd.isna(lap.get("LapTimeSeconds")):
            return {"error": f"Lap {explicit_lap} for driver {driver_code} has no telemetry-friendly lap time."}
        return {"driver_code": driver_code, "selector": raw_selector, "selector_label": f"Lap {explicit_lap}", "lap": lap}

    if selector_key not in SUPPORTED_LAP_SELECTORS:
        return {"error": f"Unsupported lap selector '{selector}'. Supported selectors: {', '.join(sorted(SUPPORTED_LAP_SELECTORS))}, or an explicit lap number."}

    if selector_key in {"best_valid_lap", "best_valid_push_lap"}:
        if is_qualifying_session_type(session_type):
            candidates = driver_laps[(driver_laps["LapType"] == "PUSH") & (driver_laps["IsValid"] == True)]
            label = "Best valid push lap"
        else:
            candidates = driver_laps[driver_laps["IsValid"] == True]
            label = "Best valid lap"
    elif selector_key == "fastest_lap":
        candidates = driver_laps[pd.notna(driver_laps["LapTimeSeconds"])]
        label = "Fastest lap"
    else:
        if not is_qualifying_session_type(session_type):
            return {"error": f"Selector '{selector}' requires a qualifying-style session (Q or SQ)."}
        segment = selector_key.split("_")[1].upper()
        candidates = driver_laps[
            (driver_laps["QualifyingSegment"] == segment)
            & (driver_laps["LapType"] == "PUSH")
            & (driver_laps["IsValid"] == True)
        ]
        label = f"Best {segment} lap"

    candidates = candidates[pd.notna(candidates["LapTimeSeconds"])].copy()
    if candidates.empty:
        return {"error": f"No lap matched selector '{selector}' for driver {driver_code}."}
    lap = candidates.sort_values(["LapTimeSeconds", "LapNumber"]).iloc[0]
    return {"driver_code": driver_code, "selector": raw_selector, "selector_label": label, "lap": lap}


def _build_lap_payload(session, resolved: dict) -> dict:
    lap = resolved["lap"]
    telemetry = _load_lap_telemetry(lap)
    lap_time_seconds = float(lap.get("LapTimeSeconds")) if pd.notna(lap.get("LapTimeSeconds")) else float(telemetry["time_seconds"].iloc[-1])
    telemetry = telemetry[telemetry["time_seconds"] <= lap_time_seconds + 1e-9].copy()
    telemetry["progress"] = _compute_progress(telemetry["x"], telemetry["y"])
    telemetry["elapsed_seconds"] = telemetry["time_seconds"].clip(lower=0.0, upper=lap_time_seconds)
    telemetry["map_y"] = -telemetry["y"]
    return {
        "driver_code": resolved["driver_code"],
        "selector": resolved["selector"],
        "selector_label": resolved["selector_label"],
        "lap_number": int(lap.get("LapNumber")),
        "lap_time_seconds": lap_time_seconds,
        "segment": lap.get("QualifyingSegment"),
        "telemetry": telemetry.reset_index(drop=True),
    }


def _load_lap_telemetry(lap: pd.Series) -> pd.DataFrame:
    merged = pd.DataFrame()
    car_data = getattr(lap, "get_car_data", None)
    pos_data = getattr(lap, "get_pos_data", None)
    if callable(car_data):
        merged = _normalize_car_data(car_data())
    if callable(pos_data):
        pos_df = _normalize_pos_data(pos_data())
        if merged.empty:
            merged = pos_df
        elif not pos_df.empty:
            merged = pd.merge_asof(
                merged.sort_values("time_seconds"),
                pos_df.sort_values("time_seconds"),
                on="time_seconds",
                direction="nearest",
            )
    if merged.empty or "x" not in merged.columns or "y" not in merged.columns:
        telemetry_getter = getattr(lap, "get_telemetry", None)
        if callable(telemetry_getter):
            merged = _normalize_combined_telemetry(telemetry_getter())
    if merged.empty:
        raise ValueError(f"No telemetry available for driver {lap.get('Driver')} lap {lap.get('LapNumber')}.")
    merged = merged.sort_values("time_seconds").reset_index(drop=True)
    merged = merged.drop_duplicates(subset=["time_seconds"], keep="first")
    merged["x"] = pd.to_numeric(merged["x"], errors="coerce").interpolate().ffill().bfill()
    merged["y"] = pd.to_numeric(merged["y"], errors="coerce").interpolate().ffill().bfill()
    for column in ("speed", "throttle", "brake", "gear"):
        if column not in merged.columns:
            merged[column] = 0.0 if column != "gear" else 0
        merged[column] = pd.to_numeric(merged[column], errors="coerce").interpolate().ffill().bfill()
    merged = merged[pd.notna(merged["time_seconds"]) & pd.notna(merged["x"]) & pd.notna(merged["y"])].copy()
    if merged.empty:
        raise ValueError(f"Telemetry for driver {lap.get('Driver')} lap {lap.get('LapNumber')} is empty after normalization.")
    return merged[["time_seconds", "x", "y", "speed", "throttle", "brake", "gear"]]


def _normalize_car_data(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame()
    out = pd.DataFrame({"time_seconds": _extract_time_seconds(df)})
    for source, target in {"Speed": "speed", "Throttle": "throttle", "Brake": "brake", "nGear": "gear"}.items():
        if source in df.columns:
            out[target] = df[source]
    return out


def _normalize_pos_data(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame()
    out = pd.DataFrame({"time_seconds": _extract_time_seconds(df)})
    for source, target in {"X": "x", "Y": "y"}.items():
        if source in df.columns:
            out[target] = df[source]
    return out


def _normalize_combined_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame()
    out = pd.DataFrame({"time_seconds": _extract_time_seconds(df)})
    for source, target in {"X": "x", "Y": "y", "Speed": "speed", "Throttle": "throttle", "Brake": "brake", "nGear": "gear"}.items():
        if source in df.columns:
            out[target] = df[source]
    return out


def _extract_time_seconds(df: pd.DataFrame) -> pd.Series:
    if "Time" in df.columns:
        return pd.to_timedelta(df["Time"], errors="coerce").dt.total_seconds()
    if "SessionTime" in df.columns:
        return pd.to_timedelta(df["SessionTime"], errors="coerce").dt.total_seconds()
    if "Date" in df.columns:
        date_series = pd.to_datetime(df["Date"], errors="coerce")
        if date_series.notna().any():
            return (date_series - date_series.dropna().iloc[0]).dt.total_seconds()
    if "time_seconds" in df.columns:
        return pd.to_numeric(df["time_seconds"], errors="coerce")
    return pd.Series(np.linspace(0, max(len(df) - 1, 0), len(df)), index=df.index, dtype=float)


def _compute_progress(xs: pd.Series, ys: pd.Series) -> pd.Series:
    x = pd.to_numeric(xs, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(ys, errors="coerce").to_numpy(dtype=float)
    if len(x) == 0:
        return pd.Series(dtype=float)
    deltas = np.sqrt(np.diff(x, prepend=x[0]) ** 2 + np.diff(y, prepend=y[0]) ** 2)
    cumulative = np.cumsum(deltas)
    total = float(cumulative[-1]) if len(cumulative) else 0.0
    if total <= 0.0:
        return pd.Series(np.linspace(0.0, 1.0, len(x)), dtype=float)
    return pd.Series(cumulative / total, dtype=float)


def _build_circuit_payload(session, lap1: dict, lap2: dict) -> dict:
    base_df = lap1["telemetry"] if len(lap1["telemetry"]) >= len(lap2["telemetry"]) else lap2["telemetry"]
    progress_targets = np.linspace(0.0, 1.0, MAP_POINT_COUNT)
    path_x = np.interp(progress_targets, base_df["progress"], base_df["x"])
    path_y = np.interp(progress_targets, base_df["progress"], base_df["map_y"])
    corners = _build_corner_markers(session, base_df)
    min_x = float(np.min(path_x))
    max_x = float(np.max(path_x))
    min_y = float(np.min(path_y))
    max_y = float(np.max(path_y))
    pad_x = max((max_x - min_x) * 0.08, 50.0)
    pad_y = max((max_y - min_y) * 0.08, 50.0)
    return {
        "view_box": [
            round(min_x - pad_x, 1),
            round(min_y - pad_y, 1),
            round((max_x - min_x) + pad_x * 2, 1),
            round((max_y - min_y) + pad_y * 2, 1),
        ],
        "path": [{"x": round(float(x), 1), "y": round(float(y), 1)} for x, y in zip(path_x, path_y, strict=False)],
        "corners": corners,
    }


def _build_corner_markers(session, base_df: pd.DataFrame) -> list[dict]:
    circuit_info = None
    if hasattr(session, "get_circuit_info") and callable(session.get_circuit_info):
        try:
            circuit_info = session.get_circuit_info()
        except Exception:
            circuit_info = None
    if circuit_info is None:
        circuit_info = getattr(session, "circuit_info", None)
    corners_df = getattr(circuit_info, "corners", None) if circuit_info is not None else None
    if corners_df is None:
        corners_df = getattr(circuit_info, "Corners", None) if circuit_info is not None else None
    if corners_df is None or getattr(corners_df, "empty", True):
        return []
    telemetry_points = base_df[["x", "map_y", "progress"]].to_numpy(dtype=float)
    markers: list[dict] = []
    for _, row in corners_df.iterrows():
        if pd.isna(row.get("X")) or pd.isna(row.get("Y")):
            continue
        target_x = float(row.get("X"))
        target_y = -float(row.get("Y"))
        deltas = telemetry_points[:, :2] - np.array([target_x, target_y], dtype=float)
        nearest_index = int(np.argmin(np.sum(deltas * deltas, axis=1)))
        number = str(row.get("Number") or "").strip()
        letter = str(row.get("Letter") or "").strip()
        label = f"T{number}{letter}".strip()
        if label == "T":
            continue
        markers.append({"label": label, "x": round(target_x, 1), "y": round(target_y, 1), "progress": round(float(telemetry_points[nearest_index][2]), 4)})
    markers.sort(key=lambda marker: marker["progress"])
    return markers


def _build_real_time_samples(lap1: dict, lap2: dict, corners: list[dict]) -> dict:
    duration = max(lap1["lap_time_seconds"], lap2["lap_time_seconds"])
    samples: list[dict] = []
    for current_time in np.linspace(0.0, duration, REPLAY_SAMPLE_COUNT):
        car1 = _snapshot_by_time(lap1, current_time)
        car2 = _snapshot_by_time(lap2, current_time)
        samples.append(
            {
                "t": round(float(current_time), 3),
                "cars": {lap1["driver_code"]: car1, lap2["driver_code"]: car2},
                "delta_progress": round(car1["progress"] - car2["progress"], 4),
                "corner_label": _corner_for_progress(corners, (car1["progress"] + car2["progress"]) / 2.0),
            }
        )
    return {"duration_seconds": round(float(duration), 3), "samples": samples}


def _build_equal_progress_samples(lap1: dict, lap2: dict, corners: list[dict]) -> dict:
    samples: list[dict] = []
    for idx, progress in enumerate(np.linspace(0.0, 1.0, REPLAY_SAMPLE_COUNT)):
        car1 = _snapshot_by_progress(lap1, progress)
        car2 = _snapshot_by_progress(lap2, progress)
        samples.append(
            {
                "t": round(float(idx / max(REPLAY_SAMPLE_COUNT - 1, 1)), 3),
                "progress": round(float(progress), 4),
                "cars": {lap1["driver_code"]: car1, lap2["driver_code"]: car2},
                "delta_seconds": round(car1["time_seconds"] - car2["time_seconds"], 3),
                "corner_label": _corner_for_progress(corners, progress),
            }
        )
    return {"duration_seconds": 1.0, "samples": samples}


def _snapshot_by_time(lap_payload: dict, current_time: float) -> dict:
    telemetry = lap_payload["telemetry"]
    clamped_time = min(max(float(current_time), 0.0), float(lap_payload["lap_time_seconds"]))
    return _interpolated_snapshot(telemetry["time_seconds"].to_numpy(dtype=float), telemetry, clamped_time)


def _snapshot_by_progress(lap_payload: dict, progress: float) -> dict:
    telemetry = lap_payload["telemetry"]
    clamped_progress = min(max(float(progress), 0.0), 1.0)
    snapshot = _interpolated_snapshot(telemetry["progress"].to_numpy(dtype=float), telemetry, clamped_progress)
    snapshot["progress"] = round(clamped_progress, 4)
    return snapshot


def _interpolated_snapshot(reference: np.ndarray, telemetry: pd.DataFrame, target: float) -> dict:
    def interp(column: str) -> float:
        return float(np.interp(target, reference, telemetry[column].to_numpy(dtype=float)))

    return {
        "x": round(interp("x"), 2),
        "y": round(interp("map_y"), 2),
        "progress": round(interp("progress"), 4),
        "time_seconds": round(interp("elapsed_seconds"), 3),
        "speed": int(round(interp("speed"))),
        "throttle": int(round(interp("throttle"))),
        "brake": int(round(interp("brake"))),
        "gear": int(round(interp("gear"))),
    }


def _corner_for_progress(corners: list[dict], progress: float) -> str | None:
    if not corners:
        return None
    best = min(corners, key=lambda corner: abs(float(corner.get("progress", 0.0)) - float(progress)))
    return str(best.get("label")) if best else None


def _lap_header_payload(lap_payload: dict, color: str) -> dict:
    return {
        "driver_code": lap_payload["driver_code"],
        "lap_number": lap_payload["lap_number"],
        "lap_time_seconds": round(float(lap_payload["lap_time_seconds"]), 3),
        "selector": lap_payload["selector"],
        "selector_label": lap_payload["selector_label"],
        "segment": lap_payload.get("segment"),
        "color": color,
    }


def _describe_resolved_lap(lap_payload: dict) -> str:
    segment = f" {lap_payload['segment']}" if lap_payload.get("segment") else ""
    return f"{lap_payload['driver_code']} {lap_payload['selector_label']}{segment} (Lap {lap_payload['lap_number']}, {_format_lap_time(lap_payload['lap_time_seconds'])})"


def _format_lap_time(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = float(seconds) - mins * 60
    return f"{mins}:{secs:06.3f}"


def _parse_explicit_lap_number(selector: str) -> int | None:
    if selector.isdigit():
        return int(selector)
    match = re.fullmatch(r"lap_?(\d+)", selector)
    if match:
        return int(match.group(1))
    return None


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _to_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, pd.Timedelta):
        return float(value.total_seconds())
    try:
        td = pd.to_timedelta(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(td):
        return None
    return float(td.total_seconds())
