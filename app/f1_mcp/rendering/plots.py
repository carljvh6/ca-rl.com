"""Matplotlib plot rendering helpers for F1 lap visualizations."""

from __future__ import annotations

import base64
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from f1_mcp.services.compare_analysis import extract_pit_stop_laps


def _figure_to_html(fig, alt_text: str) -> str:
    img_buffer = BytesIO()
    fig.savefig(
        img_buffer,
        format="png",
        facecolor="#181818",
        edgecolor="none",
        dpi=100,
        bbox_inches="tight",
    )
    img_buffer.seek(0)
    img_base64 = base64.b64encode(img_buffer.getvalue()).decode("utf-8")
    plt.close(fig)
    return (
        '<div style="width:100%; text-align:center;">'
        f'<img src="data:image/png;base64,{img_base64}" '
        f'style="max-width:100%; height:auto;" alt="{alt_text}" /></div>'
    )


def _apply_axes_style(ax) -> None:
    ax.tick_params(colors="#f1f1f1", labelsize=12)
    ax.grid(True, alpha=0.3, color="#666666")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#666666")
    ax.spines["left"].set_color("#666666")


def render_single_driver_lap_plot(year: int, race: str, driver_code: str, lap_data: list[dict]) -> str:
    """Render the existing single-driver lap chart to embedded HTML."""
    lap_numbers = [lap["LapNumber"] for lap in lap_data]
    lap_times_seconds = [lap["LapTimeSeconds"] for lap in lap_data]

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 6), facecolor="#181818")
    ax.set_facecolor("#181818")
    ax.plot(
        lap_numbers,
        lap_times_seconds,
        marker="o",
        linewidth=3,
        markersize=7,
        color="#ff3b3f",
        markerfacecolor="#ff3b3f",
        markeredgecolor="#ff3b3f",
    )
    ax.set_xlabel("Lap Number", color="#f1f1f1", fontsize=14)
    ax.set_ylabel("Lap Time (s)", color="#f1f1f1", fontsize=14)
    ax.set_title(
        f"{driver_code} Lap Times ({year} {race})",
        color="#f1f1f1",
        fontsize=20,
        fontweight="bold",
        pad=20,
    )

    min_time = min(lap_times_seconds)
    max_time = max(lap_times_seconds)
    time_range = max_time - min_time
    ax.set_ylim(max(0, min_time - time_range * 0.1), max_time + time_range * 0.1)
    _apply_axes_style(ax)
    plt.tight_layout()
    return _figure_to_html(fig, "Lap Times Plot")


def render_comparison_lap_plot(
    year: int,
    race: str,
    driver_code1: str,
    driver1_lap_data: list[dict],
    driver_code2: str,
    driver2_lap_data: list[dict],
) -> str:
    """Render the existing two-driver comparison chart to embedded HTML."""
    driver1_laps = [lap["LapNumber"] for lap in driver1_lap_data]
    driver1_times = [lap["LapTimeSeconds"] for lap in driver1_lap_data]
    driver2_laps = [lap["LapNumber"] for lap in driver2_lap_data]
    driver2_times = [lap["LapTimeSeconds"] for lap in driver2_lap_data]

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(14, 7), facecolor="#181818")
    ax.set_facecolor("#181818")
    ax.plot(
        driver1_laps,
        driver1_times,
        marker="o",
        linewidth=3,
        markersize=6,
        color="#ff3b3f",
        markerfacecolor="#ff3b3f",
        markeredgecolor="#ff3b3f",
        label=driver_code1,
        alpha=0.9,
    )
    ax.plot(
        driver2_laps,
        driver2_times,
        marker="s",
        linewidth=3,
        markersize=6,
        color="#3b82f6",
        markerfacecolor="#3b82f6",
        markeredgecolor="#3b82f6",
        label=driver_code2,
        alpha=0.9,
    )

    for pit_lap in extract_pit_stop_laps(driver1_lap_data):
        ax.axvline(x=pit_lap, color="#ff3b3f", linestyle="--", alpha=0.5, linewidth=2)
    for pit_lap in extract_pit_stop_laps(driver2_lap_data):
        ax.axvline(x=pit_lap, color="#3b82f6", linestyle="--", alpha=0.5, linewidth=2)

    ax.set_xlabel("Lap Number", color="#f1f1f1", fontsize=14)
    ax.set_ylabel("Lap Time (s)", color="#f1f1f1", fontsize=14)
    ax.set_title(
        f"{driver_code1} vs {driver_code2} Lap Times Comparison ({year} {race})",
        color="#f1f1f1",
        fontsize=20,
        fontweight="bold",
        pad=20,
    )

    all_times = driver1_times + driver2_times
    min_time = min(all_times)
    max_time = max(all_times)
    time_range = max_time - min_time
    ax.set_ylim(max(0, min_time - time_range * 0.1), max_time + time_range * 0.1)

    legend_elements = [
        plt.Line2D([0], [0], color="#ff3b3f", marker="o", linestyle="-", linewidth=3, markersize=6, label=driver_code1),
        plt.Line2D([0], [0], color="#3b82f6", marker="s", linestyle="-", linewidth=3, markersize=6, label=driver_code2),
    ]
    if extract_pit_stop_laps(driver1_lap_data) or extract_pit_stop_laps(driver2_lap_data):
        legend_elements.append(
            plt.Line2D([0], [0], color="gray", linestyle="--", linewidth=2, label="Pit Stops")
        )
    ax.legend(handles=legend_elements, loc="best", fontsize=12, framealpha=0.3)
    _apply_axes_style(ax)
    plt.tight_layout()
    return _figure_to_html(fig, "Lap Times Comparison Plot")
