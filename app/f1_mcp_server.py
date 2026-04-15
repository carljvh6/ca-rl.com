"""FastMCP entrypoint that registers the F1 tools backed by the layered package."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from f1_mcp.tools.analysis_tools import (
    analyze_driver_stints as _analyze_driver_stints_impl,
    analyze_qualifying_runs as _analyze_qualifying_runs_impl,
    compare_driver_stints as _compare_driver_stints_impl,
    compare_driver_lap_times as _compare_driver_lap_times_impl,
    compare_qualifying_runs as _compare_qualifying_runs_impl,
    get_driver_lap_times as _get_driver_lap_times_impl,
    plot_driver_lap_times as _plot_driver_lap_times_impl,
)
from f1_mcp.tools.reference_tools import (
    get_f1_results as _get_f1_results_impl,
    get_f1_schedule as _get_f1_schedule_impl,
)

logger = logging.getLogger(__name__)
mcp = FastMCP("f1_server")


@mcp.tool()
def get_f1_results(year: int, race: str, session_type: str = "R") -> dict:
    """Get F1 results for a given year, event, and session."""
    return _get_f1_results_impl(year, race, session_type=session_type)


@mcp.tool()
def get_f1_schedule(year: int) -> dict:
    """Get the F1 schedule for a given year."""
    return _get_f1_schedule_impl(year)


@mcp.tool()
def get_driver_lap_times(year: int, race: str, driver_code: str, session_type: str = "R") -> dict:
    """Get lap times data for a given driver in a particular session and year."""
    return _get_driver_lap_times_impl(year, race, driver_code, session_type=session_type)


@mcp.tool()
def plot_driver_lap_times(year: int, race: str, driver_code: str, session_type: str = "R") -> dict:
    """Plot lap times for a given driver in a particular session and year."""
    return _plot_driver_lap_times_impl(year, race, driver_code, session_type=session_type)


@mcp.tool()
def compare_driver_lap_times(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    session_type: str = "R",
) -> dict:
    """Compare lap times between two drivers in a particular session and year."""
    return _compare_driver_lap_times_impl(
        year,
        race,
        driver_code1,
        driver_code2,
        session_type=session_type,
    )


@mcp.tool()
def analyze_qualifying_runs(
    year: int,
    race: str,
    driver_code: str,
    session_type: str = "Q",
) -> dict:
    """Analyze qualifying runs for one driver with Q1/Q2/Q3 awareness."""
    return _analyze_qualifying_runs_impl(year, race, driver_code, session_type=session_type)


@mcp.tool()
def compare_qualifying_runs(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    session_type: str = "Q",
) -> dict:
    """Compare qualifying runs for two drivers using push-lap metrics."""
    return _compare_qualifying_runs_impl(
        year,
        race,
        driver_code1,
        driver_code2,
        session_type=session_type,
    )


@mcp.tool()
def analyze_driver_stints(
    year: int,
    race: str,
    driver_code: str,
    session_type: str = "R",
) -> dict:
    """Analyze a driver's stints in a race-like session."""
    return _analyze_driver_stints_impl(year, race, driver_code, session_type=session_type)


@mcp.tool()
def compare_driver_stints(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    session_type: str = "R",
) -> dict:
    """Compare two drivers' stints in a race-like session."""
    return _compare_driver_stints_impl(
        year,
        race,
        driver_code1,
        driver_code2,
        session_type=session_type,
    )


if __name__ == "__main__":
    mcp.run()
