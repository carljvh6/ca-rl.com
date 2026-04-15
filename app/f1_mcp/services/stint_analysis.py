"""Stint detection and analysis helpers for race-like sessions."""

from __future__ import annotations

import math
from statistics import median

import pandas as pd


RACE_LIKE_SESSION_TYPES = {"R", "S"}
STINT_ANALYSIS_ERROR = "Stint analysis is only supported for race-like sessions (R, S)."
SC_TRACK_STATUS_FLAGS = {"4", "6", "7"}
TOO_CLOSE_DELTA_SECONDS = 0.05


def _has_value(value: object) -> bool:
    text = str(value)
    return bool(text) and text.lower() not in {"nat", "nan", "none", ""}


def _to_float_seconds(value: object) -> float | None:
    """Convert timing-like values to float seconds."""
    if value is None:
        return None
    if isinstance(value, pd.Timedelta):
        return float(value.total_seconds())
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    try:
        timedelta_value = pd.to_timedelta(value)
    except (TypeError, ValueError):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(numeric_value) else numeric_value
    if pd.isna(timedelta_value):
        return None
    return float(timedelta_value.total_seconds())


def _normalize_compound(value: object) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip().upper()
    aliases = {
        "S": "SOFT",
        "M": "MEDIUM",
        "H": "HARD",
        "INTERMEDIATE": "INTER",
        "INTERS": "INTER",
        "WETS": "WET",
    }
    return aliases.get(text, text)


def infer_stint_compound(stint_df: pd.DataFrame) -> tuple[str, str]:
    """Infer a display-safe stint compound from the first non-null compound value."""
    if "Compound" not in stint_df.columns:
        return "UNKNOWN", "unknown"
    compounds = stint_df["Compound"].map(_normalize_compound)
    first_valid_idx = next((idx for idx, compound in compounds.items() if compound is not None), None)
    if first_valid_idx is None:
        return "UNKNOWN", "unknown"
    source = "direct" if first_valid_idx == compounds.index[0] else "filled_from_stint"
    return str(compounds.loc[first_valid_idx]), source


def _contains_sc_marker(track_status: object) -> bool:
    if not _has_value(track_status):
        return False
    status_parts = {part.strip() for part in str(track_status).replace(",", " ").split() if part.strip()}
    return bool(status_parts & SC_TRACK_STATUS_FLAGS)


def is_race_like_session_type(session_type: str) -> bool:
    """Return whether the normalized session type supports stint analysis."""
    return str(session_type).upper() in RACE_LIKE_SESSION_TYPES


def _calculate_linear_slope(clean_df: pd.DataFrame) -> float | None:
    if len(clean_df) < 2:
        return None
    ordered = clean_df.reset_index(drop=True).copy()
    x = pd.Series(range(1, len(ordered) + 1), dtype=float)
    y = ordered["LapTimeSeconds"].astype(float).reset_index(drop=True)
    x_mean = float(x.mean())
    y_mean = float(y.mean())
    numerator = float(((x - x_mean) * (y - y_mean)).sum())
    denominator = float(((x - x_mean) ** 2).sum())
    if denominator == 0:
        return None
    return numerator / denominator


def _calculate_robust_pace_trend(clean_df: pd.DataFrame) -> float | None:
    if len(clean_df) < 3:
        return _calculate_linear_slope(clean_df)
    ordered = clean_df.sort_values("LapNumber").reset_index(drop=True)
    clean_count = len(ordered)
    window = max(1, min(3, clean_count // 2))
    first_window = ordered.head(window)
    last_window = ordered.tail(window)
    first_avg = float(first_window["LapTimeSeconds"].mean())
    last_avg = float(last_window["LapTimeSeconds"].mean())
    lap_gap = float(last_window["LapNumber"].median() - first_window["LapNumber"].median())
    if lap_gap <= 0:
        return None
    return (last_avg - first_avg) / lap_gap


def _calculate_late_stint_delta(clean_df: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    if len(clean_df) < 4:
        return None, None, None
    ordered = clean_df.sort_values("LapNumber").reset_index(drop=True)
    clean_count = len(ordered)
    window = min(3, clean_count // 2)
    if window < 2:
        return None, None, None
    first_avg = float(ordered.head(window)["LapTimeSeconds"].mean())
    last_avg = float(ordered.tail(window)["LapTimeSeconds"].mean())
    return first_avg, last_avg, last_avg - first_avg


def _prepare_stint_laps(laps_df: pd.DataFrame) -> pd.DataFrame:
    df = laps_df.sort_values("LapNumber").reset_index(drop=True).copy()
    if "LapTime" in df.columns:
        lap_time_from_laptime = df["LapTime"].map(_to_float_seconds)
    else:
        lap_time_from_laptime = pd.Series([None] * len(df), index=df.index, dtype="object")
    if "LapTimeSeconds" in df.columns:
        lap_time_from_seconds = df["LapTimeSeconds"].map(_to_float_seconds)
    else:
        lap_time_from_seconds = pd.Series([None] * len(df), index=df.index, dtype="object")
    df["LapTimeSeconds"] = lap_time_from_seconds.where(lap_time_from_seconds.notna(), lap_time_from_laptime)
    df["LapTimeSeconds"] = pd.to_numeric(df["LapTimeSeconds"], errors="coerce")

    df["HasPitIn"] = df.get("PitInTime", pd.Series(dtype="object")).map(_has_value)
    df["HasPitOut"] = df.get("PitOutTime", pd.Series(dtype="object")).map(_has_value)
    df["IsOutLap"] = df["HasPitOut"]
    df["IsInLap"] = df["HasPitIn"]
    df["HasValidLapTime"] = df["LapTimeSeconds"].notna()
    df["TrackStatus"] = df.get("TrackStatus", "")
    df["HasSCOrVSC"] = df["TrackStatus"].map(_contains_sc_marker)
    df["Compound"] = df.get("Compound", pd.Series(dtype="object")).map(_normalize_compound)
    if "Deleted" in df.columns:
        df["IsDeleted"] = df["Deleted"].astype(str).str.lower().isin({"1", "true", "yes"})
    else:
        df["IsDeleted"] = False
    if "IsAccurate" in df.columns:
        df["IsAccurate"] = ~df["IsAccurate"].astype(str).str.lower().isin({"0", "false", "no"})
    else:
        df["IsAccurate"] = True
    return df


def _split_stints(df: pd.DataFrame) -> list[pd.DataFrame]:
    if df.empty:
        return []

    stints: list[pd.DataFrame] = []
    start_idx = 0
    previous_compound = df.iloc[0].get("Compound")
    for idx in range(1, len(df)):
        row = df.iloc[idx]
        prev_row = df.iloc[idx - 1]
        current_compound = row.get("Compound") if row.get("Compound") is not None else previous_compound
        compound_changed = current_compound != previous_compound and current_compound is not None
        pit_boundary = bool(prev_row.get("HasPitIn")) or bool(row.get("HasPitOut"))
        if compound_changed or pit_boundary:
            stints.append(df.iloc[start_idx:idx].copy())
            start_idx = idx
            previous_compound = current_compound
        elif current_compound is not None:
            previous_compound = current_compound
    stints.append(df.iloc[start_idx:].copy())
    return stints


def _confidence_level(clean_lap_count: int) -> str:
    if clean_lap_count >= 8:
        return "high"
    if clean_lap_count >= 5:
        return "medium"
    return "low"


def _derive_confidence(
    *,
    clean_lap_count: int,
    excluded_lap_count: int,
    total_lap_count: int,
    sc_lap_count: int,
    lap_time_stddev_clean: float | None,
) -> tuple[str, list[str]]:
    confidence = _confidence_level(clean_lap_count)
    reasons = [f"{clean_lap_count} clean laps"]

    if total_lap_count > 0:
        excluded_ratio = excluded_lap_count / total_lap_count
        if excluded_ratio >= 0.4:
            confidence = "low" if confidence == "medium" else confidence
            confidence = "medium" if confidence == "high" else confidence
            reasons.append("large proportion of laps excluded")

    if sc_lap_count > 0:
        reasons.append("SC/VSC affected sample")
        if confidence == "high":
            confidence = "medium"
        elif confidence == "medium" and sc_lap_count >= 2:
            confidence = "low"

    if lap_time_stddev_clean is not None and lap_time_stddev_clean > 1.0:
        reasons.append("high clean-lap variance")
        if confidence == "high":
            confidence = "medium"
        elif confidence == "medium":
            confidence = "low"

    if clean_lap_count < 5:
        reasons.append("small clean-lap sample")

    return confidence, reasons


def _serialize_stint_lap(row: pd.Series, fallback_compound: str) -> dict:
    return {
        "lap_number": int(row.get("LapNumber")),
        "lap_time_seconds": float(row["LapTimeSeconds"]) if pd.notna(row.get("LapTimeSeconds")) else None,
        "compound": row.get("Compound") or fallback_compound,
        "is_out_lap": bool(row.get("IsOutLap")),
        "is_in_lap": bool(row.get("IsInLap")),
        "has_valid_lap_time": bool(row.get("HasValidLapTime")),
        "track_status": str(row.get("TrackStatus") or ""),
        "excluded_from_clean_metrics": bool(row.get("ExcludedFromCleanMetrics")),
    }


def _build_stint_payload(stint_number: int, stint_df: pd.DataFrame) -> dict:
    stint_df = stint_df.copy().reset_index(drop=True)
    compound, compound_source = infer_stint_compound(stint_df)
    stint_df["ExcludedFromCleanMetrics"] = (
        stint_df["IsOutLap"]
        | stint_df["IsInLap"]
        | (~stint_df["HasValidLapTime"])
        | stint_df["HasSCOrVSC"]
        | stint_df["IsDeleted"]
        | (~stint_df["IsAccurate"])
    )
    clean_df = stint_df[~stint_df["ExcludedFromCleanMetrics"]].copy()

    lap_times_all = pd.to_numeric(stint_df["LapTimeSeconds"], errors="coerce").dropna()
    lap_times_clean = pd.to_numeric(clean_df["LapTimeSeconds"], errors="coerce").dropna()
    best_lap_source = lap_times_clean if not lap_times_clean.empty else lap_times_all
    stddev_clean = float(lap_times_clean.std(ddof=0)) if len(lap_times_clean) > 1 else None
    first_n_clean_avg, last_n_clean_avg, late_stint_delta = _calculate_late_stint_delta(clean_df)
    raw_trend = _calculate_linear_slope(clean_df)
    robust_trend = _calculate_robust_pace_trend(clean_df)
    clean_lap_count = int(len(clean_df))
    excluded_lap_count = int(stint_df["ExcludedFromCleanMetrics"].sum())
    confidence, confidence_reasons = _derive_confidence(
        clean_lap_count=clean_lap_count,
        excluded_lap_count=excluded_lap_count,
        total_lap_count=int(len(stint_df)),
        sc_lap_count=int(stint_df["HasSCOrVSC"].sum()),
        lap_time_stddev_clean=stddev_clean,
    )
    suspicious_metric_notes: list[str] = []
    if raw_trend is not None and abs(raw_trend) > 0.5:
        suspicious_metric_notes.append("pace trend magnitude is unusually large for a race stint")
    if robust_trend is not None and abs(robust_trend) > 0.5:
        suspicious_metric_notes.append("robust pace trend magnitude is unusually large for a race stint")
    if late_stint_delta is not None and abs(late_stint_delta) > 5.0:
        suspicious_metric_notes.append("late-stint delta magnitude is unusually large")
    if late_stint_delta is None and clean_lap_count < 4:
        suspicious_metric_notes.append("insufficient clean laps for late-stint delta")
    if suspicious_metric_notes and confidence == "high":
        confidence = "medium"
    elif suspicious_metric_notes and confidence == "medium":
        confidence = "low"
    confidence_reasons = list(dict.fromkeys(confidence_reasons + suspicious_metric_notes))

    return {
        "stint_number": stint_number,
        "compound": compound,
        "inferred_compound_source": compound_source,
        "start_lap": int(stint_df["LapNumber"].min()),
        "end_lap": int(stint_df["LapNumber"].max()),
        "num_laps": int(len(stint_df)),
        "laps": [_serialize_stint_lap(row, compound) for _, row in stint_df.iterrows()],
        "avg_lap_seconds_all": float(lap_times_all.mean()) if not lap_times_all.empty else None,
        "avg_lap_seconds_clean": float(lap_times_clean.mean()) if not lap_times_clean.empty else None,
        "median_lap_seconds_clean": float(median(lap_times_clean)) if len(lap_times_clean) > 0 else None,
        "best_lap_seconds": float(best_lap_source.min()) if not best_lap_source.empty else None,
        "pace_trend_raw_seconds_per_lap": raw_trend,
        "pace_trend_robust_seconds_per_lap": robust_trend,
        "degradation_slope_seconds_per_lap": raw_trend,
        "clean_lap_count": clean_lap_count,
        "excluded_lap_count": excluded_lap_count,
        "lap_time_stddev_clean": stddev_clean,
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "first_n_clean_avg": first_n_clean_avg,
        "last_n_clean_avg": last_n_clean_avg,
        "late_stint_delta_seconds": late_stint_delta,
        "suspicious_metrics": bool(suspicious_metric_notes),
        "debug_notes": suspicious_metric_notes,
        "includes_out_lap": bool(stint_df["IsOutLap"].any()),
        "includes_in_lap": bool(stint_df["IsInLap"].any()),
    }


def _summary_pick(stints: list[dict], key: str, mode: str) -> dict | None:
    candidates = [stint for stint in stints if stint.get(key) is not None]
    if not candidates:
        return None
    winner = (
        min(candidates, key=lambda stint: float(stint[key]))
        if mode == "min"
        else max(candidates, key=lambda stint: float(stint[key]))
    )
    return {
        "stint_number": int(winner["stint_number"]),
        "compound": winner.get("compound"),
        key: winner.get(key),
        "confidence": winner.get("confidence"),
    }


def analyze_stints(laps_df: pd.DataFrame) -> dict:
    """Build a detailed stint analysis payload from a driver's lap dataframe."""
    if laps_df.empty:
        return {
            "stints": [],
            "summary": {
                "num_stints": 0,
                "best_stint_by_avg_clean": None,
                "longest_stint": None,
                "shortest_stint": None,
                "lowest_pace_trend_stint": None,
            },
        }

    prepared = _prepare_stint_laps(laps_df)
    stint_frames = _split_stints(prepared)
    stints = [_build_stint_payload(idx, stint_df) for idx, stint_df in enumerate(stint_frames, start=1)]

    summary = {
        "num_stints": len(stints),
        "best_stint_by_avg_clean": _summary_pick(stints, "avg_lap_seconds_clean", "min"),
        "longest_stint": _summary_pick(stints, "num_laps", "max"),
        "shortest_stint": _summary_pick(stints, "num_laps", "min"),
        "lowest_pace_trend_stint": _summary_pick(stints, "pace_trend_robust_seconds_per_lap", "min"),
    }
    return {"stints": stints, "summary": summary}


def summarize_stints(laps_df: pd.DataFrame) -> list[dict]:
    """Return a compact stint summary payload for legacy lap-time responses."""
    analysis = analyze_stints(laps_df)
    return [
        {
            "stint_number": stint["stint_number"],
            "compound": stint.get("compound"),
            "start_lap": stint["start_lap"],
            "end_lap": stint["end_lap"],
            "lap_count": stint["num_laps"],
            "avg_lap_time_seconds": stint.get("avg_lap_seconds_all"),
            "best_lap_time_seconds": stint.get("best_lap_seconds"),
            "pace_trend_seconds_per_lap": stint.get("pace_trend_robust_seconds_per_lap"),
            "confidence": stint.get("confidence"),
        }
        for stint in analysis["stints"]
    ]


def _matchup_confidence(stint1: dict, stint2: dict) -> tuple[str, list[str]]:
    ordering = {"low": 0, "medium": 1, "high": 2}
    reverse = {0: "low", 1: "medium", 2: "high"}
    level = min(ordering.get(stint1.get("confidence", "low"), 0), ordering.get(stint2.get("confidence", "low"), 0))
    reasons = list(dict.fromkeys((stint1.get("confidence_reasons") or []) + (stint2.get("confidence_reasons") or [])))
    return reverse[level], reasons


def _build_matchup(stint1: dict, stint2: dict, *, driver1_code: str, driver2_code: str, mode: str) -> dict:
    avg_delta = (
        float(stint1["avg_lap_seconds_clean"]) - float(stint2["avg_lap_seconds_clean"])
        if stint1.get("avg_lap_seconds_clean") is not None and stint2.get("avg_lap_seconds_clean") is not None
        else None
    )
    median_delta = (
        float(stint1["median_lap_seconds_clean"]) - float(stint2["median_lap_seconds_clean"])
        if stint1.get("median_lap_seconds_clean") is not None and stint2.get("median_lap_seconds_clean") is not None
        else None
    )
    best_delta = (
        float(stint1["best_lap_seconds"]) - float(stint2["best_lap_seconds"])
        if stint1.get("best_lap_seconds") is not None and stint2.get("best_lap_seconds") is not None
        else None
    )
    pace_trend_delta = (
        float(stint1["pace_trend_robust_seconds_per_lap"]) - float(stint2["pace_trend_robust_seconds_per_lap"])
        if stint1.get("pace_trend_robust_seconds_per_lap") is not None
        and stint2.get("pace_trend_robust_seconds_per_lap") is not None
        else None
    )
    confidence, confidence_reasons = _matchup_confidence(stint1, stint2)
    too_close_to_call = bool(avg_delta is not None and abs(avg_delta) < TOO_CLOSE_DELTA_SECONDS and confidence in {"low", "medium"})
    if avg_delta is None or too_close_to_call:
        faster_driver = None if avg_delta is None else "Too close to call"
    elif avg_delta < 0:
        faster_driver = driver1_code
    elif avg_delta > 0:
        faster_driver = driver2_code
    else:
        faster_driver = "TIE"

    notes = []
    if too_close_to_call:
        notes.append("clean-pace delta is too small relative to confidence")
    if confidence == "low":
        notes.append("low-confidence matchup")
    if stint1.get("compound") != stint2.get("compound"):
        notes.append("different compounds")
    if mode == "compound":
        notes.append("matched by compound")
    return {
        "driver1_stint_number": stint1["stint_number"],
        "driver2_stint_number": stint2["stint_number"],
        "driver1_compound": stint1.get("compound"),
        "driver2_compound": stint2.get("compound"),
        "avg_clean_delta_seconds": avg_delta,
        "median_clean_delta_seconds": median_delta,
        "best_lap_delta_seconds": best_delta,
        "pace_trend_delta_seconds_per_lap": pace_trend_delta,
        "degradation_delta_seconds_per_lap": pace_trend_delta,
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "notes": notes,
        "too_close_to_call": too_close_to_call,
        "faster_driver": faster_driver,
    }


def _build_ordinal_matchups(driver1_stints: list[dict], driver2_stints: list[dict], *, driver1_code: str, driver2_code: str) -> list[dict]:
    matchup_count = min(len(driver1_stints), len(driver2_stints))
    return [
        _build_matchup(driver1_stints[idx], driver2_stints[idx], driver1_code=driver1_code, driver2_code=driver2_code, mode="ordinal")
        for idx in range(matchup_count)
    ]


def _build_compound_matchups(driver1_stints: list[dict], driver2_stints: list[dict], *, driver1_code: str, driver2_code: str) -> list[dict]:
    matchups: list[dict] = []
    used_driver2_indexes: set[int] = set()
    for stint1 in driver1_stints:
        best_idx = None
        for idx, stint2 in enumerate(driver2_stints):
            if idx in used_driver2_indexes or stint2.get("compound") != stint1.get("compound"):
                continue
            best_idx = idx
            break
        if best_idx is None:
            continue
        used_driver2_indexes.add(best_idx)
        matchups.append(
            _build_matchup(
                stint1,
                driver2_stints[best_idx],
                driver1_code=driver1_code,
                driver2_code=driver2_code,
                mode="compound",
            )
        )
    return matchups


def compare_stints(driver1_stints: list[dict], driver2_stints: list[dict], *, driver1_code: str, driver2_code: str) -> dict:
    """Compare two stint payloads with ordinal and compound-aware matching."""
    ordinal_matchups = _build_ordinal_matchups(driver1_stints, driver2_stints, driver1_code=driver1_code, driver2_code=driver2_code)
    compound_matchups = _build_compound_matchups(driver1_stints, driver2_stints, driver1_code=driver1_code, driver2_code=driver2_code)

    compounds1 = [stint.get("compound") for stint in driver1_stints]
    compounds2 = [stint.get("compound") for stint in driver2_stints]
    strategies_align = len(driver1_stints) == len(driver2_stints) and compounds1[: len(ordinal_matchups)] == compounds2[: len(ordinal_matchups)]
    comparison_mode_used = "ordinal" if strategies_align or not compound_matchups else "compound"
    return {
        "comparison_mode_used": comparison_mode_used,
        "ordinal_matchups": ordinal_matchups,
        "compound_matchups": compound_matchups,
        "stint_matchups": ordinal_matchups if comparison_mode_used == "ordinal" else compound_matchups,
        "future_modes": ["overlap_window"],
    }
