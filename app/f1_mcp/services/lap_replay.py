"""Lap replay payload builder for animated two-lap comparisons."""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np
import pandas as pd

from f1_mcp.providers.session_provider import (
    describe_session_type,
    is_qualifying_session_type,
    load_session,
    normalize_session_type,
)
from f1_mcp.services.qualifying_analysis import assign_qualifying_segments, classify_qualifying_laps

logger = logging.getLogger("f1_mcp.services.lap_replay")

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
CORE_TELEMETRY_FIELDS = ("speed", "throttle", "brake", "gear")
POSITION_FIELDS = ("x", "y")
ALL_STATUS_FIELDS = CORE_TELEMETRY_FIELDS + POSITION_FIELDS


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
    telemetry, telemetry_source_used, telemetry_status, debug_meta = _choose_best_telemetry_source(lap)
    lap_time_seconds = float(lap.get("LapTimeSeconds")) if pd.notna(lap.get("LapTimeSeconds")) else float(telemetry["time_seconds"].iloc[-1])
    telemetry = telemetry[telemetry["time_seconds"] <= lap_time_seconds + 1e-9].copy()
    telemetry["progress"] = _compute_progress(telemetry["x"], telemetry["y"])
    telemetry["elapsed_seconds"] = telemetry["time_seconds"].clip(lower=0.0, upper=lap_time_seconds)
    telemetry["map_y"] = -telemetry["y"]
    lap_payload = {
        "driver_code": resolved["driver_code"],
        "selector": resolved["selector"],
        "selector_label": resolved["selector_label"],
        "lap_number": int(lap.get("LapNumber")),
        "lap_time_seconds": lap_time_seconds,
        "segment": lap.get("QualifyingSegment"),
        "telemetry": telemetry.reset_index(drop=True),
        "telemetry_source_used": telemetry_source_used,
        "telemetry_status": telemetry_status,
        "telemetry_field_status": telemetry_status,
        "telemetry_time_min": debug_meta["telemetry_time_min"],
        "telemetry_time_max": debug_meta["telemetry_time_max"],
    }
    first_preview, mid_preview = _build_sample_previews(lap_payload)
    lap_payload["first_sample_preview"] = first_preview
    lap_payload["mid_sample_preview"] = mid_preview
    return lap_payload


def _choose_best_telemetry_source(lap: pd.Series) -> tuple[pd.DataFrame, str, dict[str, str], dict[str, Any]]:
    driver_code = str(lap.get("Driver") or lap.get("driver_code") or "")
    lap_number = int(lap.get("LapNumber"))
    car_raw = _get_source_df(lap, "get_car_data")
    pos_raw = _get_source_df(lap, "get_pos_data")
    combined_raw = _get_source_df(lap, "get_telemetry")

    _log_source_overview("Car data", driver_code, lap_number, car_raw)
    _log_source_overview("Pos data", driver_code, lap_number, pos_raw)
    _log_source_overview("Combined telemetry", driver_code, lap_number, combined_raw)

    car_norm = _normalize_car_data(car_raw)
    pos_norm = _normalize_pos_data(pos_raw)
    combined_norm = _normalize_combined_telemetry(combined_raw)
    merged_norm = _merge_car_and_pos_data(car_norm, pos_norm)

    candidates = [
        _build_source_candidate("merged car+position", merged_norm, driver_code, lap_number),
        _build_source_candidate("get_telemetry fallback", combined_norm, driver_code, lap_number),
    ]

    best = max(candidates, key=_source_score)
    source_name = str(best["name"])
    source_df = best["data"]
    field_status = dict(best["field_status"])
    _log_field_status(source_name, driver_code, lap_number, field_status)

    if source_df.empty or field_status["x"] != "ok" or field_status["y"] != "ok":
        raise ValueError(f"Telemetry extraction failed for {driver_code} lap {lap_number}: missing circuit position data.")
    if all(field_status[field] == "missing" for field in CORE_TELEMETRY_FIELDS):
        logger.warning(
            "Telemetry extraction for %s lap %s produced no core car telemetry fields. source=%s status=%s",
            driver_code,
            lap_number,
            source_name,
            field_status,
        )
        raise ValueError(f"Telemetry extraction failed for {driver_code} lap {lap_number}: no speed/throttle/brake/gear data available.")

    if source_name == "get_telemetry fallback":
        logger.info("Using get_telemetry fallback for %s lap %s", driver_code, lap_number)
    else:
        logger.info("Using merged car+position data for %s lap %s", driver_code, lap_number)

    debug_meta = {
        "telemetry_time_min": _series_min(source_df["time_seconds"]) if "time_seconds" in source_df.columns else None,
        "telemetry_time_max": _series_max(source_df["time_seconds"]) if "time_seconds" in source_df.columns else None,
    }
    return source_df, source_name, field_status, debug_meta


def _get_source_df(lap: pd.Series, method_name: str) -> pd.DataFrame:
    getter = getattr(lap, method_name, None)
    if not callable(getter):
        return pd.DataFrame()
    try:
        result = getter()
    except Exception as exc:
        logger.warning(
            "Telemetry getter %s failed for %s lap %s: %s",
            method_name,
            lap.get("Driver"),
            lap.get("LapNumber"),
            exc,
        )
        return pd.DataFrame()
    return result if isinstance(result, pd.DataFrame) else pd.DataFrame(result)


def _log_source_overview(label: str, driver_code: str, lap_number: int, df: pd.DataFrame) -> None:
    logger.info(
        "%s columns for %s lap %s: %s",
        label,
        driver_code,
        lap_number,
        list(df.columns) if isinstance(df, pd.DataFrame) else [],
    )
    logger.info(
        "%s row count for %s lap %s: %s",
        label,
        driver_code,
        lap_number,
        0 if df is None else len(df),
    )


def _log_field_status(source_name: str, driver_code: str, lap_number: int, field_status: dict[str, str]) -> None:
    logger.info(
        "Telemetry field availability for %s lap %s: speed=%s throttle=%s brake=%s gear=%s x=%s y=%s (source=%s)",
        driver_code,
        lap_number,
        "yes" if field_status["speed"] == "ok" else "no",
        "yes" if field_status["throttle"] == "ok" else "no",
        "yes" if field_status["brake"] == "ok" else "no",
        "yes" if field_status["gear"] == "ok" else "no",
        "yes" if field_status["x"] == "ok" else "no",
        "yes" if field_status["y"] == "ok" else "no",
        source_name,
    )


def _build_source_candidate(name: str, df: pd.DataFrame, driver_code: str, lap_number: int) -> dict[str, Any]:
    finalized = _finalize_telemetry_frame(df.copy()) if not df.empty else pd.DataFrame()
    field_status = _field_status_from_df(finalized)
    if "time_seconds" in finalized.columns and not finalized.empty:
        logger.info(
            "%s time range for %s lap %s: min=%s max=%s",
            name,
            driver_code,
            lap_number,
            _series_min(finalized["time_seconds"]),
            _series_max(finalized["time_seconds"]),
        )
    return {"name": name, "data": finalized, "field_status": field_status}


def _source_score(candidate: dict[str, Any]) -> tuple[int, int, int, int]:
    status = candidate["field_status"]
    has_xy = int(status["x"] == "ok" and status["y"] == "ok")
    core_count = sum(1 for field in CORE_TELEMETRY_FIELDS if status[field] == "ok")
    total_count = sum(1 for field in ALL_STATUS_FIELDS if status[field] == "ok")
    preference = 1 if candidate["name"] == "get_telemetry fallback" and has_xy and core_count > 0 else 0
    return (has_xy, core_count, preference, total_count)


def _merge_car_and_pos_data(car_df: pd.DataFrame, pos_df: pd.DataFrame) -> pd.DataFrame:
    if car_df.empty and pos_df.empty:
        return pd.DataFrame()
    if car_df.empty:
        return pos_df.copy()
    if pos_df.empty:
        return car_df.copy()
    left = car_df.sort_values("time_seconds").reset_index(drop=True)
    right = pos_df.sort_values("time_seconds").reset_index(drop=True)
    return pd.merge_asof(left, right, on="time_seconds", direction="nearest")


def _normalize_car_data(df: pd.DataFrame) -> pd.DataFrame:
    return _normalize_source_frame(
        df,
        {"Speed": "speed", "Throttle": "throttle", "Brake": "brake", "nGear": "gear"},
    )


def _normalize_pos_data(df: pd.DataFrame) -> pd.DataFrame:
    return _normalize_source_frame(df, {"X": "x", "Y": "y"})


def _normalize_combined_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    return _normalize_source_frame(
        df,
        {"X": "x", "Y": "y", "Speed": "speed", "Throttle": "throttle", "Brake": "brake", "nGear": "gear"},
    )


def _normalize_source_frame(df: pd.DataFrame, rename_map: dict[str, str]) -> pd.DataFrame:
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame()
    out = pd.DataFrame({"time_seconds": _extract_time_seconds(df)})
    for source, target in rename_map.items():
        if source not in df.columns:
            continue
        series = pd.to_numeric(df[source], errors="coerce")
        if series.notna().any():
            out[target] = series
    out["time_seconds"] = pd.to_numeric(out["time_seconds"], errors="coerce")
    out = out[pd.notna(out["time_seconds"])].copy()
    if out.empty:
        return pd.DataFrame()
    out["time_seconds"] = out["time_seconds"] - float(out["time_seconds"].min())
    return out.sort_values("time_seconds").reset_index(drop=True)


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


def _finalize_telemetry_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "time_seconds" not in df.columns:
        return pd.DataFrame()
    result = df.sort_values("time_seconds").reset_index(drop=True)
    result = result.drop_duplicates(subset=["time_seconds"], keep="first")
    result["time_seconds"] = pd.to_numeric(result["time_seconds"], errors="coerce")
    result = result[pd.notna(result["time_seconds"])].copy()
    if result.empty:
        return pd.DataFrame()

    for column in POSITION_FIELDS:
        result[column] = _interpolate_series(result[column]) if column in result.columns else pd.Series(np.nan, index=result.index, dtype=float)
    if result["x"].notna().sum() == 0 or result["y"].notna().sum() == 0:
        return pd.DataFrame()

    for column in CORE_TELEMETRY_FIELDS:
        if column not in result.columns:
            result[column] = pd.Series(np.nan, index=result.index, dtype=float)
        else:
            result[column] = _interpolate_series(result[column])
    return result[["time_seconds", "x", "y", "speed", "throttle", "brake", "gear"]]


def _interpolate_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return pd.Series(np.nan, index=series.index, dtype=float)
    return numeric.interpolate(limit_direction="both")


def _field_status_from_df(df: pd.DataFrame) -> dict[str, str]:
    status: dict[str, str] = {}
    for field in ALL_STATUS_FIELDS:
        status[field] = "ok" if field in df.columns and pd.to_numeric(df[field], errors="coerce").notna().any() else "missing"
    return status


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
        markers.append(
            {
                "label": label,
                "x": round(target_x, 1),
                "y": round(target_y, 1),
                "progress": round(float(telemetry_points[nearest_index][2]), 4),
            }
        )
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
    return {
        "duration_seconds": round(float(duration), 3),
        "initial_time_seconds": _find_meaningful_initial_time(samples),
        "samples": samples,
    }


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
    return {
        "duration_seconds": 1.0,
        "initial_time_seconds": _find_meaningful_initial_time(samples),
        "samples": samples,
    }


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
    def interp(column: str) -> float | None:
        values = pd.to_numeric(telemetry[column], errors="coerce").to_numpy(dtype=float)
        finite_mask = np.isfinite(values)
        if not finite_mask.any():
            return None
        if finite_mask.all():
            return float(np.interp(target, reference, values))
        return float(np.interp(target, reference[finite_mask], values[finite_mask]))

    speed = interp("speed")
    throttle = interp("throttle")
    brake = interp("brake")
    gear = interp("gear")
    return {
        "x": round(float(np.interp(target, reference, telemetry["x"].to_numpy(dtype=float))), 2),
        "y": round(float(np.interp(target, reference, telemetry["map_y"].to_numpy(dtype=float))), 2),
        "progress": round(float(np.interp(target, reference, telemetry["progress"].to_numpy(dtype=float))), 4),
        "time_seconds": round(float(np.interp(target, reference, telemetry["elapsed_seconds"].to_numpy(dtype=float))), 3),
        "speed": None if speed is None else int(round(speed)),
        "throttle": None if throttle is None else int(round(throttle)),
        "brake": None if brake is None else int(round(brake)),
        "gear": None if gear is None else int(round(gear)),
    }


def _find_meaningful_initial_time(samples: list[dict]) -> float:
    for sample in samples:
        for car in sample.get("cars", {}).values():
            speed = car.get("speed")
            if isinstance(speed, (int, float)) and speed > 0:
                return float(sample.get("t") or 0.0)
            if any(car.get(field) is not None for field in ("throttle", "brake", "gear")):
                return float(sample.get("t") or 0.0)
    return 0.0


def _build_sample_previews(lap_payload: dict) -> tuple[dict, dict]:
    telemetry = lap_payload["telemetry"]
    first = _interpolated_snapshot(telemetry["time_seconds"].to_numpy(dtype=float), telemetry, float(telemetry["time_seconds"].iloc[0]))
    middle_index = len(telemetry) // 2
    middle = _interpolated_snapshot(telemetry["time_seconds"].to_numpy(dtype=float), telemetry, float(telemetry["time_seconds"].iloc[middle_index]))
    return first, middle


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
        "telemetry_source_used": lap_payload["telemetry_source_used"],
        "telemetry_status": lap_payload["telemetry_status"],
        "telemetry_field_status": lap_payload["telemetry_field_status"],
        "telemetry_time_min": lap_payload["telemetry_time_min"],
        "telemetry_time_max": lap_payload["telemetry_time_max"],
        "first_sample_preview": lap_payload["first_sample_preview"],
        "mid_sample_preview": lap_payload["mid_sample_preview"],
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


def _series_min(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce")
    return None if numeric.notna().sum() == 0 else round(float(numeric.min()), 3)


def _series_max(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce")
    return None if numeric.notna().sum() == 0 else round(float(numeric.max()), 3)


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
