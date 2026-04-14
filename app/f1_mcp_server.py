"""FastMCP entrypoint that registers the F1 tools backed by the layered package."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from f1_mcp.tools.analysis_tools import (
    compare_driver_lap_times as _compare_driver_lap_times_impl,
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
def get_f1_results(year: int, race: str) -> dict:
    """Get F1 race results for a given year and race."""
    return _get_f1_results_impl(year, race, session_type="R")


@mcp.tool()
def get_f1_schedule(year: int) -> dict:
    """Get the F1 schedule for a given year."""
    return _get_f1_schedule_impl(year)


@mcp.tool()
def get_driver_lap_times(year: int, race: str, driver_code: str) -> dict:
    """Get lap times data for a given driver in a particular race and year."""
    return _get_driver_lap_times_impl(year, race, driver_code, session_type="R")


@mcp.tool()
def plot_driver_lap_times(year: int, race: str, driver_code: str) -> dict:
    """Plot lap times for a given driver in a particular race and year."""
    return _plot_driver_lap_times_impl(year, race, driver_code, session_type="R")


@mcp.tool()
def compare_driver_lap_times(year: int, race: str, driver_code1: str, driver_code2: str) -> dict:
    """Compare lap times between two drivers in a particular race and year."""
    return _compare_driver_lap_times_impl(year, race, driver_code1, driver_code2, session_type="R")


if __name__ == "__main__":
    mcp.run()
