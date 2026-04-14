"""Analysis-style MCP tool implementations for lap retrieval and plotting."""

from __future__ import annotations

import logging

from f1_mcp.providers.laps_provider import get_driver_laps_df
from f1_mcp.providers.session_provider import is_qualifying_session_type, load_session, normalize_session_type
from f1_mcp.rendering.plots import render_comparison_lap_plot, render_single_driver_lap_plot
from f1_mcp.services.compare_analysis import compare_two_drivers
from f1_mcp.services.lap_analysis import build_lap_records, summarize_laps
from f1_mcp.services.qualifying_analysis import (
    build_qualifying_runs_payload,
    compare_qualifying_payloads,
)
from f1_mcp.services.stint_analysis import summarize_stints

logger = logging.getLogger("f1_mcp_server")


def get_driver_lap_times(
    year: int,
    race: str,
    driver_code: str,
    session_type: str = "R",
) -> dict:
    """Return serialized lap data for one driver while preserving the existing payload shape."""
    logger.info("Getting lap times for %s in %s - %s (%s)", driver_code, year, race, session_type)
    try:
        driver_code = driver_code.upper()
        normalized_session_type = normalize_session_type(session_type)
        driver_laps = get_driver_laps_df(year, race, normalized_session_type, driver_code)
        if driver_laps.empty:
            return {"error": f"No valid lap time data found for driver {driver_code} in {year} - {race}"}

        lap_records = build_lap_records(driver_laps)
        return {
            "year": year,
            "race": race,
            "driver_code": driver_code,
            "session_type": normalized_session_type,
            "lap_data": lap_records,
            "summary": summarize_laps(driver_laps),
            "stints": summarize_stints(driver_laps),
        }
    except Exception as exc:
        logger.error("Error getting lap times: %s", exc)
        return {"error": str(exc)}


def plot_driver_lap_times(
    year: int,
    race: str,
    driver_code: str,
    session_type: str = "R",
) -> dict:
    """Render the existing single-driver lap plot using the layered internals."""
    logger.info("Plotting lap times for %s in %s - %s (%s)", driver_code, year, race, session_type)
    try:
        normalized_session_type = normalize_session_type(session_type)
        result = get_driver_lap_times(year, race, driver_code, session_type=normalized_session_type)
        if "error" in result:
            return result

        lap_data = result.get("lap_data", [])
        if not lap_data:
            return {"error": f"No lap data available for plotting driver {driver_code} in {year} - {race}"}

        return {
            "year": year,
            "race": race,
            "driver_code": driver_code.upper(),
            "session_type": normalized_session_type,
            "plot_html": render_single_driver_lap_plot(year, race, driver_code.upper(), lap_data),
            "lap_data": lap_data,
            "summary": result.get("summary"),
            "stints": result.get("stints"),
        }
    except Exception as exc:
        logger.error("Error plotting lap times: %s", exc)
        return {"error": str(exc)}


def compare_driver_lap_times(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    session_type: str = "R",
) -> dict:
    """Compare two drivers while preserving the existing MCP tool response fields."""
    logger.info(
        "Comparing lap times for %s vs %s in %s - %s (%s)",
        driver_code1,
        driver_code2,
        year,
        race,
        session_type,
    )
    try:
        normalized_session_type = normalize_session_type(session_type)
        driver1_result = get_driver_lap_times(year, race, driver_code1, session_type=normalized_session_type)
        driver2_result = get_driver_lap_times(year, race, driver_code2, session_type=normalized_session_type)

        if "error" in driver1_result:
            return {"error": f"Error getting data for {driver_code1.upper()}: {driver1_result['error']}"}
        if "error" in driver2_result:
            return {"error": f"Error getting data for {driver_code2.upper()}: {driver2_result['error']}"}

        driver1_data = driver1_result.get("lap_data", [])
        driver2_data = driver2_result.get("lap_data", [])
        if not driver1_data:
            return {"error": f"No lap data available for driver {driver_code1.upper()} in {year} - {race}"}
        if not driver2_data:
            return {"error": f"No lap data available for driver {driver_code2.upper()} in {year} - {race}"}

        comparison_summary = compare_two_drivers(
            driver_code1.upper(),
            driver1_data,
            driver_code2.upper(),
            driver2_data,
        )
        comparison_summary["session_type"] = normalized_session_type
        return {
            "year": year,
            "race": race,
            "driver_code1": driver_code1.upper(),
            "driver_code2": driver_code2.upper(),
            "session_type": normalized_session_type,
            "plot_html": render_comparison_lap_plot(
                year,
                race,
                driver_code1.upper(),
                driver1_data,
                driver_code2.upper(),
                driver2_data,
            ),
            "driver1_lap_data": driver1_data,
            "driver2_lap_data": driver2_data,
            "comparison_summary": comparison_summary,
        }
    except Exception as exc:
        logger.error("Error comparing lap times: %s", exc)
        return {"error": str(exc)}


def analyze_qualifying_runs(
    year: int,
    race: str,
    driver_code: str,
    session_type: str = "Q",
) -> dict:
    """Return qualifying runs grouped by Q1/Q2/Q3 with lap classifications."""
    logger.info(
        "Analyzing qualifying runs for %s in %s - %s (%s)",
        driver_code,
        year,
        race,
        session_type,
    )
    try:
        normalized_session_type = normalize_session_type(session_type)
        if not is_qualifying_session_type(normalized_session_type):
            return {"error": "Qualifying run analysis only supports Q or SQ sessions."}

        driver_code = driver_code.upper()
        session = load_session(year, race, normalized_session_type)
        if not hasattr(session, "laps") or session.laps is None:
            return {"error": f"No lap data available for {year} - {race} ({normalized_session_type})"}

        driver_laps = session.laps[session.laps["Driver"] == driver_code].copy()
        if driver_laps.empty:
            return {"error": f"No qualifying lap data found for driver {driver_code} in {year} - {race}"}

        result = build_qualifying_runs_payload(
            session,
            driver_code,
            driver_laps,
            normalized_session_type,
        )
        result["year"] = year
        result["race"] = race
        return result
    except Exception as exc:
        logger.error("Error analyzing qualifying runs: %s", exc)
        return {"error": str(exc)}


def compare_qualifying_runs(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    session_type: str = "Q",
) -> dict:
    """Compare two drivers' qualifying runs using push-lap-only pace metrics."""
    logger.info(
        "Comparing qualifying runs for %s vs %s in %s - %s (%s)",
        driver_code1,
        driver_code2,
        year,
        race,
        session_type,
    )
    try:
        normalized_session_type = normalize_session_type(session_type)
        if not is_qualifying_session_type(normalized_session_type):
            return {"error": "Qualifying run comparison only supports Q or SQ sessions."}

        driver1_result = analyze_qualifying_runs(
            year,
            race,
            driver_code1.upper(),
            session_type=normalized_session_type,
        )
        driver2_result = analyze_qualifying_runs(
            year,
            race,
            driver_code2.upper(),
            session_type=normalized_session_type,
        )
        if "error" in driver1_result:
            return {"error": f"Error getting qualifying data for {driver_code1.upper()}: {driver1_result['error']}"}
        if "error" in driver2_result:
            return {"error": f"Error getting qualifying data for {driver_code2.upper()}: {driver2_result['error']}"}

        result = compare_qualifying_payloads(driver1_result, driver2_result)
        result.update(
            {
                "year": year,
                "race": race,
                "session_type": normalized_session_type,
                "driver_code1": driver_code1.upper(),
                "driver_code2": driver_code2.upper(),
            }
        )
        return result
    except Exception as exc:
        logger.error("Error comparing qualifying runs: %s", exc)
        return {"error": str(exc)}
