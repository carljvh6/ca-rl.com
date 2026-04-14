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


def render_qualifying_runs_plot(
    year: int,
    race: str,
    driver_code: str,
    qualifying_result: dict,
) -> str:
    """Render a qualifying run chart showing push laps by segment and run."""
    push_laps: list[dict] = []
    for segment in qualifying_result.get("segments", []):
        segment_name = segment.get("name")
        segment_order = {"Q1": 0, "Q2": 1, "Q3": 2}.get(str(segment_name), 0)
        for run in segment.get("runs", []):
            for lap in run.get("laps", []):
                if lap.get("lap_type") != "PUSH" or lap.get("lap_time_seconds") is None:
                    continue
                push_laps.append(
                    {
                        "x": len(push_laps) + 1,
                        "lap_time_seconds": float(lap["lap_time_seconds"]),
                        "segment": str(segment_name),
                        "segment_order": segment_order,
                        "run_number": int(run.get("run_number", 0)),
                        "is_valid": bool(lap.get("is_valid")),
                    }
                )

    if not push_laps:
        return ""

    colors = {"Q1": "#f59e0b", "Q2": "#3b82f6", "Q3": "#10b981"}
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(13, 6), facecolor="#181818")
    ax.set_facecolor("#181818")

    for segment_name in ("Q1", "Q2", "Q3"):
        segment_points = [lap for lap in push_laps if lap["segment"] == segment_name]
        if not segment_points:
            continue
        xs = [lap["x"] for lap in segment_points]
        ys = [lap["lap_time_seconds"] for lap in segment_points]
        ax.plot(
            xs,
            ys,
            marker="o",
            linewidth=2.5,
            markersize=7,
            color=colors[segment_name],
            markerfacecolor=colors[segment_name],
            markeredgecolor=colors[segment_name],
            label=segment_name,
            alpha=0.95,
        )
        for lap in segment_points:
            ax.annotate(
                f"R{lap['run_number']}",
                (lap["x"], lap["lap_time_seconds"]),
                textcoords="offset points",
                xytext=(0, -14),
                ha="center",
                color="#d1d5db",
                fontsize=9,
            )

    invalid_pushes = [lap for lap in push_laps if not lap["is_valid"]]
    if invalid_pushes:
        ax.scatter(
            [lap["x"] for lap in invalid_pushes],
            [lap["lap_time_seconds"] for lap in invalid_pushes],
            s=100,
            facecolors="none",
            edgecolors="#f8fafc",
            linewidths=1.8,
            label="Invalid push",
        )

    for idx in range(1, len(push_laps)):
        if push_laps[idx]["segment"] != push_laps[idx - 1]["segment"]:
            ax.axvline(idx + 0.5, color="#6b7280", linestyle="--", alpha=0.4, linewidth=1.5)

    lap_labels = [
        f"{lap['segment']} R{lap['run_number']}"
        for lap in push_laps
    ]
    ax.set_xticks([lap["x"] for lap in push_laps])
    ax.set_xticklabels(lap_labels, rotation=35, ha="right", color="#f1f1f1", fontsize=10)
    ax.set_xlabel("Push laps by segment and run", color="#f1f1f1", fontsize=13)
    ax.set_ylabel("Lap Time (s)", color="#f1f1f1", fontsize=14)
    ax.set_title(
        f"{driver_code} Qualifying Push Laps ({year} {race})",
        color="#f1f1f1",
        fontsize=19,
        fontweight="bold",
        pad=18,
    )
    all_times = [lap["lap_time_seconds"] for lap in push_laps]
    min_time = min(all_times)
    max_time = max(all_times)
    time_range = max(max_time - min_time, 0.5)
    ax.set_ylim(max(0, min_time - time_range * 0.12), max_time + time_range * 0.18)
    ax.legend(loc="best", fontsize=11, framealpha=0.3)
    _apply_axes_style(ax)
    plt.tight_layout()
    return _figure_to_html(fig, "Qualifying Push Laps Plot")


def render_qualifying_comparison_plot(
    year: int,
    race: str,
    comparison_result: dict,
) -> str:
    """Render qualifying comparison as best push lap progression by segment."""
    driver1 = str(comparison_result.get("driver_code1") or "")
    driver2 = str(comparison_result.get("driver_code2") or "")
    drivers = comparison_result.get("drivers", {})
    payload1 = drivers.get(driver1, {})
    payload2 = drivers.get(driver2, {})

    def collect_points(payload: dict) -> list[dict]:
        points: list[dict] = []
        for segment in payload.get("segments", []):
            segment_name = str(segment.get("name") or "")
            segment_index = {"Q1": 1, "Q2": 2, "Q3": 3}.get(segment_name)
            best = segment.get("best_valid_lap_seconds")
            if segment_index is None or best is None:
                continue
            points.append({"x": segment_index, "segment": segment_name, "y": float(best)})
        return points

    points1 = collect_points(payload1)
    points2 = collect_points(payload2)
    if not points1 and not points2:
        return ""

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#181818")
    ax.set_facecolor("#181818")

    for driver_code, points, color, marker in (
        (driver1, points1, "#ff3b3f", "o"),
        (driver2, points2, "#3b82f6", "s"),
    ):
        if not points:
            continue
        ax.plot(
            [point["x"] for point in points],
            [point["y"] for point in points],
            marker=marker,
            linewidth=3,
            markersize=8,
            color=color,
            markerfacecolor=color,
            markeredgecolor=color,
            label=driver_code,
            alpha=0.95,
        )

    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["Q1", "Q2", "Q3"], color="#f1f1f1", fontsize=12)
    ax.set_xlabel("Qualifying segment", color="#f1f1f1", fontsize=13)
    ax.set_ylabel("Best valid push lap (s)", color="#f1f1f1", fontsize=14)
    ax.set_title(
        f"{driver1} vs {driver2} Qualifying Progression ({year} {race})",
        color="#f1f1f1",
        fontsize=19,
        fontweight="bold",
        pad=18,
    )
    all_times = [point["y"] for point in (points1 + points2)]
    min_time = min(all_times)
    max_time = max(all_times)
    time_range = max(max_time - min_time, 0.5)
    ax.set_ylim(max(0, min_time - time_range * 0.18), max_time + time_range * 0.18)
    ax.legend(loc="best", fontsize=11, framealpha=0.3)
    _apply_axes_style(ax)
    plt.tight_layout()
    return _figure_to_html(fig, "Qualifying Comparison Plot")
