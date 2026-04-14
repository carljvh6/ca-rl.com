"""Qualifying-specific lap classification, run grouping, and comparisons."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


QUALIFYING_SEGMENTS = ("Q1", "Q2", "Q3")
LAP_TYPE_OUT = "OUT"
LAP_TYPE_PUSH = "PUSH"
LAP_TYPE_COOL = "COOL"
LAP_TYPE_IN = "IN"
LAP_TYPE_ABORTED = "ABORTED"
LAP_TYPE_UNKNOWN = "UNKNOWN"


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "nan", "nat", "none"}
    return not pd.isna(value)


def _to_seconds(value: object) -> float | None:
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


def _to_bool(value: object, default: bool = False) -> bool:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _normalize_segment_name(value: object) -> str | None:
    if not _has_value(value):
        return None
    text = str(value).strip().upper()
    if text in QUALIFYING_SEGMENTS:
        return text
    if text in {"1", "PART1", "Q1"}:
        return "Q1"
    if text in {"2", "PART2", "Q2"}:
        return "Q2"
    if text in {"3", "PART3", "Q3"}:
        return "Q3"
    return None


def _segment_count_from_results(session, driver_code: str) -> int:
    results = getattr(session, "results", None)
    if results is None or getattr(results, "empty", True):
        return 1
    if "Abbreviation" in results.columns:
        driver_rows = results[results["Abbreviation"] == driver_code]
    elif "DriverNumber" in results.columns:
        driver_rows = results[results["DriverNumber"] == driver_code]
    else:
        driver_rows = results.iloc[0:0]
    if driver_rows.empty:
        return 1
    row = driver_rows.iloc[0]
    if _has_value(row.get("Q3")):
        return 3
    if _has_value(row.get("Q2")):
        return 2
    return 1


def _split_times_from_session(session) -> list[pd.Timedelta]:
    raw = getattr(session, "_session_split_times", None)
    if raw is None:
        return []
    split_times: list[pd.Timedelta] = []
    if isinstance(raw, Iterable):
        for value in raw:
            try:
                td = pd.to_timedelta(value)
            except (TypeError, ValueError):
                continue
            if pd.isna(td):
                continue
            split_times.append(td)
    if len(split_times) >= 3:
        return split_times[:3]
    return split_times


def _assign_segments_by_gaps(df: pd.DataFrame, segment_count: int) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)

    segment_names = list(QUALIFYING_SEGMENTS[: max(1, min(segment_count, 3))])
    if len(segment_names) == 1:
        return pd.Series(["Q1"] * len(df), index=df.index, dtype="object")

    time_col = "LapStartTime" if "LapStartTime" in df.columns else "Time" if "Time" in df.columns else None
    if time_col is None:
        return pd.Series([segment_names[0]] * len(df), index=df.index, dtype="object")

    times = pd.to_timedelta(df[time_col], errors="coerce")
    gaps: list[tuple[int, float]] = []
    for idx in range(1, len(df)):
        current = times.iloc[idx]
        previous = times.iloc[idx - 1]
        if pd.isna(current) or pd.isna(previous):
            continue
        gaps.append((idx, float((current - previous).total_seconds())))

    if not gaps:
        return pd.Series([segment_names[0]] * len(df), index=df.index, dtype="object")

    boundaries = sorted(idx for idx, _gap in sorted(gaps, key=lambda item: item[1], reverse=True)[: len(segment_names) - 1])
    labels: list[str] = []
    current_segment = 0
    boundary_iter = iter(boundaries)
    next_boundary = next(boundary_iter, None)
    for idx in range(len(df)):
        if next_boundary is not None and idx >= next_boundary and current_segment < len(segment_names) - 1:
            current_segment += 1
            next_boundary = next(boundary_iter, None)
        labels.append(segment_names[current_segment])
    return pd.Series(labels, index=df.index, dtype="object")


def assign_qualifying_segments(session, driver_laps: pd.DataFrame, driver_code: str) -> pd.DataFrame:
    """Attach Q1/Q2/Q3 segment labels using explicit metadata or chronological fallback."""
    if driver_laps.empty:
        result = driver_laps.copy()
        result["QualifyingSegment"] = pd.Series(dtype="object")
        return result

    laps = driver_laps.copy().reset_index(drop=True)
    explicit_column = next(
        (
            col
            for col in ("QualifyingSegment", "SessionPart", "SessionPartName")
            if col in laps.columns and laps[col].map(_normalize_segment_name).notna().any()
        ),
        None,
    )
    if explicit_column is not None:
        laps["QualifyingSegment"] = laps[explicit_column].map(_normalize_segment_name).fillna("Q1")
        return laps

    split_times = _split_times_from_session(session)
    time_col = "Time" if "Time" in laps.columns else "LapStartTime" if "LapStartTime" in laps.columns else None
    if split_times and time_col is not None:
        boundaries = split_times[1:3] if len(split_times) >= 3 else split_times[:2]
        times = pd.to_timedelta(laps[time_col], errors="coerce")

        def label_time(value: object) -> str:
            if pd.isna(value):
                return "Q1"
            if len(boundaries) >= 2 and value >= boundaries[1]:
                return "Q3"
            if len(boundaries) >= 1 and value >= boundaries[0]:
                return "Q2"
            return "Q1"

        laps["QualifyingSegment"] = times.map(label_time)
        return laps

    segment_count = _segment_count_from_results(session, driver_code)
    laps["QualifyingSegment"] = _assign_segments_by_gaps(laps, segment_count)
    return laps


def classify_qualifying_laps(driver_laps: pd.DataFrame) -> pd.DataFrame:
    """Classify qualifying laps as out, push, cooldown, in, aborted, or unknown."""
    if driver_laps.empty:
        result = driver_laps.copy()
        for col in ("LapType", "IsValid", "LapTimeSeconds"):
            result[col] = pd.Series(dtype="object")
        return result

    laps = driver_laps.copy().reset_index(drop=True)
    if "LapTimeSeconds" not in laps.columns:
        laps["LapTimeSeconds"] = laps.get("LapTime", pd.Series(dtype="object")).map(_to_seconds)
    else:
        laps["LapTimeSeconds"] = laps["LapTimeSeconds"].map(_to_seconds)

    laps["IsDeletedLap"] = (
        laps["Deleted"].map(_to_bool)
        if "Deleted" in laps.columns
        else False
    )
    laps["HasPitOut"] = laps["PitOutTime"].map(_has_value) if "PitOutTime" in laps.columns else False
    laps["HasPitIn"] = laps["PitInTime"].map(_has_value) if "PitInTime" in laps.columns else False
    laps["IsPersonalBestLap"] = (
        laps["IsPersonalBest"].map(_to_bool)
        if "IsPersonalBest" in laps.columns
        else False
    )
    laps["IsAccurateLap"] = (
        laps["IsAccurate"].map(lambda value: _to_bool(value, default=True))
        if "IsAccurate" in laps.columns
        else True
    )

    sectors_complete = pd.Series([False] * len(laps))
    sector_columns = [col for col in ("Sector1Time", "Sector2Time", "Sector3Time") if col in laps.columns]
    if sector_columns:
        sectors_complete = laps[sector_columns].notna().all(axis=1)

    has_lap_time = laps["LapTimeSeconds"].notna()
    complete_timed_lap = has_lap_time | sectors_complete
    laps["IsValid"] = (~laps["IsDeletedLap"]) & laps["IsAccurateLap"] & complete_timed_lap
    laps["LapType"] = LAP_TYPE_UNKNOWN

    laps.loc[laps["HasPitOut"], "LapType"] = LAP_TYPE_OUT
    laps.loc[~laps["HasPitOut"] & laps["HasPitIn"], "LapType"] = LAP_TYPE_IN
    laps.loc[
        (laps["LapType"] == LAP_TYPE_UNKNOWN) & (~laps["IsValid"]),
        "LapType",
    ] = LAP_TYPE_ABORTED

    for segment_name in [value for value in laps.get("QualifyingSegment", pd.Series(dtype="object")).dropna().unique()]:
        segment_mask = laps["QualifyingSegment"] == segment_name
        segment_indices = list(laps[segment_mask].index)
        run_indices: list[list[int]] = []
        current_run: list[int] = []
        for idx in segment_indices:
            if not current_run:
                current_run = [idx]
                continue
            prev_idx = current_run[-1]
            if bool(laps.at[idx, "HasPitOut"]) or bool(laps.at[prev_idx, "HasPitIn"]):
                run_indices.append(current_run)
                current_run = [idx]
            else:
                current_run.append(idx)
        if current_run:
            run_indices.append(current_run)

        for indices in run_indices:
            candidate_indices = [
                idx
                for idx in indices
                if laps.at[idx, "LapType"] == LAP_TYPE_UNKNOWN and pd.notna(laps.at[idx, "LapTimeSeconds"])
            ]
            if not candidate_indices:
                continue
            valid_candidate_indices = [idx for idx in candidate_indices if bool(laps.at[idx, "IsValid"])]
            best_valid = min(
                (laps.at[idx, "LapTimeSeconds"] for idx in valid_candidate_indices if laps.at[idx, "LapTimeSeconds"] is not None),
                default=None,
            )
            previous_push_time: float | None = None
            for offset, idx in enumerate(candidate_indices):
                lap_seconds = laps.at[idx, "LapTimeSeconds"]
                if lap_seconds is None:
                    laps.at[idx, "LapType"] = LAP_TYPE_ABORTED
                    continue
                is_valid = bool(laps.at[idx, "IsValid"])
                is_personal_best = bool(laps.at[idx, "IsPersonalBestLap"])
                next_valid_seconds = None
                for next_idx in indices[indices.index(idx) + 1 :]:
                    if bool(laps.at[next_idx, "IsValid"]) and pd.notna(laps.at[next_idx, "LapTimeSeconds"]):
                        next_valid_seconds = laps.at[next_idx, "LapTimeSeconds"]
                        break

                if not is_valid:
                    laps.at[idx, "LapType"] = LAP_TYPE_ABORTED
                    continue
                if previous_push_time is None:
                    laps.at[idx, "LapType"] = LAP_TYPE_PUSH
                    previous_push_time = lap_seconds
                    continue
                if is_personal_best or (best_valid is not None and lap_seconds <= best_valid + 1.0):
                    laps.at[idx, "LapType"] = LAP_TYPE_PUSH
                    previous_push_time = lap_seconds
                    continue
                if next_valid_seconds is not None and lap_seconds > min(previous_push_time, next_valid_seconds) + 0.75:
                    laps.at[idx, "LapType"] = LAP_TYPE_COOL
                    continue
                laps.at[idx, "LapType"] = LAP_TYPE_PUSH
                previous_push_time = lap_seconds

    laps["LapType"] = laps["LapType"].fillna(LAP_TYPE_UNKNOWN)
    return laps


def _serialize_qualifying_lap(row: pd.Series) -> dict:
    return {
        "lap_number": int(row.get("LapNumber")),
        "lap_type": row.get("LapType", LAP_TYPE_UNKNOWN),
        "lap_time_seconds": row.get("LapTimeSeconds"),
        "is_valid": bool(row.get("IsValid", False)),
        "is_personal_best": bool(row.get("IsPersonalBestLap", False)),
        "track_status": str(row.get("TrackStatus") or ""),
        "compound": row.get("Compound"),
        "is_deleted": bool(row.get("IsDeletedLap", False)),
    }


def build_qualifying_runs_payload(session, driver_code: str, driver_laps: pd.DataFrame, session_type: str) -> dict:
    """Build a structured qualifying-runs payload for one driver."""
    if driver_laps.empty:
        return {
            "session_type": session_type,
            "driver_code": driver_code,
            "segments": [],
        }

    segmented_laps = assign_qualifying_segments(session, driver_laps, driver_code)
    classified_laps = classify_qualifying_laps(segmented_laps)
    segments_payload: list[dict] = []

    for segment_name in QUALIFYING_SEGMENTS:
        segment_df = classified_laps[classified_laps["QualifyingSegment"] == segment_name].copy()
        if segment_df.empty:
            continue

        runs: list[dict] = []
        current_run_rows: list[pd.Series] = []
        for _, row in segment_df.iterrows():
            if current_run_rows and (bool(row.get("HasPitOut")) or bool(current_run_rows[-1].get("HasPitIn"))):
                runs.append(_build_run_payload(len(runs) + 1, current_run_rows))
                current_run_rows = [row]
            else:
                current_run_rows.append(row)
        if current_run_rows:
            runs.append(_build_run_payload(len(runs) + 1, current_run_rows))

        valid_push_times = [
            lap["lap_time_seconds"]
            for run in runs
            for lap in run["laps"]
            if lap["lap_type"] == LAP_TYPE_PUSH and lap["is_valid"] and lap["lap_time_seconds"] is not None
        ]
        segments_payload.append(
            {
                "name": segment_name,
                "runs": runs,
                "best_valid_lap_seconds": min(valid_push_times) if valid_push_times else None,
            }
        )

    return {
        "session_type": session_type,
        "driver_code": driver_code,
        "segments": segments_payload,
    }


def _build_run_payload(run_number: int, run_rows: list[pd.Series]) -> dict:
    laps = [_serialize_qualifying_lap(row) for row in run_rows]
    valid_push_laps = [
        lap for lap in laps if lap["lap_type"] == LAP_TYPE_PUSH and lap["is_valid"] and lap["lap_time_seconds"] is not None
    ]
    first_push = valid_push_laps[0]["lap_time_seconds"] if valid_push_laps else None
    best_push = min((lap["lap_time_seconds"] for lap in valid_push_laps), default=None)
    final_push = valid_push_laps[-1]["lap_time_seconds"] if valid_push_laps else None
    return {
        "run_number": run_number,
        "laps": laps,
        "best_valid_push_lap_seconds": best_push,
        "num_push_laps": len(valid_push_laps),
        "improved_on_final_push": bool(
            first_push is not None
            and final_push is not None
            and best_push is not None
            and final_push == best_push
            and final_push < first_push
        ),
    }


def compare_qualifying_payloads(driver1_payload: dict, driver2_payload: dict) -> dict:
    """Compare two qualifying run payloads without race-style pit stop concepts."""
    driver1_code = driver1_payload.get("driver_code")
    driver2_code = driver2_payload.get("driver_code")
    segments: list[dict] = []

    for segment_name in QUALIFYING_SEGMENTS:
        segment1 = next((segment for segment in driver1_payload.get("segments", []) if segment.get("name") == segment_name), None)
        segment2 = next((segment for segment in driver2_payload.get("segments", []) if segment.get("name") == segment_name), None)
        if not segment1 and not segment2:
            continue
        segments.append(
            {
                "name": segment_name,
                "best_valid_lap_seconds": {
                    driver1_code: segment1.get("best_valid_lap_seconds") if segment1 else None,
                    driver2_code: segment2.get("best_valid_lap_seconds") if segment2 else None,
                },
                "run_push_laps": {
                    driver1_code: _segment_run_push_laps(segment1),
                    driver2_code: _segment_run_push_laps(segment2),
                },
            }
        )

    return {
        "session_type": driver1_payload.get("session_type"),
        "driver_code1": driver1_code,
        "driver_code2": driver2_code,
        "segments": segments,
        "best_overall_qualifying_lap": {
            driver1_code: _best_push_from_payload(driver1_payload),
            driver2_code: _best_push_from_payload(driver2_payload),
        },
        "improvement_from_first_push_to_best": {
            driver1_code: _improvement_from_first_push_to_best(driver1_payload),
            driver2_code: _improvement_from_first_push_to_best(driver2_payload),
        },
        "valid_push_lap_counts": {
            driver1_code: _count_push_laps(driver1_payload, valid_only=True),
            driver2_code: _count_push_laps(driver2_payload, valid_only=True),
        },
        "invalid_deleted_aborted_attempt_counts": {
            driver1_code: _count_compromised_laps(driver1_payload),
            driver2_code: _count_compromised_laps(driver2_payload),
        },
        "drivers": {
            driver1_code: driver1_payload,
            driver2_code: driver2_payload,
        },
    }


def _segment_run_push_laps(segment: dict | None) -> list[dict]:
    if not segment:
        return []
    runs: list[dict] = []
    for run in segment.get("runs", []):
        runs.append(
            {
                "run_number": run.get("run_number"),
                "push_laps": [
                    {
                        "lap_number": lap.get("lap_number"),
                        "lap_time_seconds": lap.get("lap_time_seconds"),
                        "is_valid": lap.get("is_valid"),
                        "is_personal_best": lap.get("is_personal_best"),
                    }
                    for lap in run.get("laps", [])
                    if lap.get("lap_type") == LAP_TYPE_PUSH
                ],
            }
        )
    return runs


def _iter_laps(payload: dict) -> Iterable[dict]:
    for segment in payload.get("segments", []):
        for run in segment.get("runs", []):
            yield from run.get("laps", [])


def _best_push_from_payload(payload: dict) -> float | None:
    push_laps = [
        lap.get("lap_time_seconds")
        for lap in _iter_laps(payload)
        if lap.get("lap_type") == LAP_TYPE_PUSH and lap.get("is_valid") and lap.get("lap_time_seconds") is not None
    ]
    return min(push_laps) if push_laps else None


def _improvement_from_first_push_to_best(payload: dict) -> float | None:
    push_laps = [
        lap.get("lap_time_seconds")
        for lap in _iter_laps(payload)
        if lap.get("lap_type") == LAP_TYPE_PUSH and lap.get("is_valid") and lap.get("lap_time_seconds") is not None
    ]
    if len(push_laps) < 2:
        return None
    return push_laps[0] - min(push_laps)


def _count_push_laps(payload: dict, *, valid_only: bool) -> int:
    return sum(
        1
        for lap in _iter_laps(payload)
        if lap.get("lap_type") == LAP_TYPE_PUSH and (lap.get("is_valid") if valid_only else True)
    )


def _count_compromised_laps(payload: dict) -> dict:
    laps = list(_iter_laps(payload))
    return {
        "invalid_push_laps": sum(
            1 for lap in laps if lap.get("lap_type") == LAP_TYPE_PUSH and not lap.get("is_valid")
        ),
        "aborted_laps": sum(1 for lap in laps if lap.get("lap_type") == LAP_TYPE_ABORTED),
        "deleted_laps": sum(1 for lap in laps if lap.get("is_deleted")),
    }
