"""Reusable HTML snippets for F1 MCP web responses."""

from __future__ import annotations

import json

import markdown


def render_lap_times_table(lap_data: list[dict], include_seconds: bool = True) -> str:
    """Render a lap-times table for the web UI."""
    if include_seconds:
        header = (
            "<thead><tr><th>Lap</th><th>Lap Time</th><th>Lap Time (s)</th><th>Compound</th></tr></thead>"
        )
        rows = "".join(
            f"<tr><td>{lap.get('LapNumber', '')}</td><td>{lap.get('LapTime', '')}</td>"
            f"<td>{float(lap.get('LapTimeSeconds', 0)):.3f}</td><td>{lap.get('Compound', '')}</td></tr>"
            for lap in lap_data
        )
    else:
        header = "<thead><tr><th>Lap</th><th>Lap Time</th><th>Compound</th></tr></thead>"
        rows = "".join(
            f"<tr><td>{lap.get('LapNumber', '')}</td><td>{lap.get('LapTime', '')}</td>"
            f"<td>{lap.get('Compound', '')}</td></tr>"
            for lap in lap_data
        )
    return (
        "<div class='mt-4'><h3 class='text-2xl mb-4'>Lap Times</h3>"
        f"<table class='table table-zebra w-full'>{header}<tbody>{rows}</tbody></table></div>"
    )


def render_comparison_analysis_section(analysis_text: str) -> str:
    """Render comparison narration markdown as an HTML section."""
    analysis_html = markdown.markdown(analysis_text, extensions=["nl2br", "fenced_code"])
    return (
        "<div class='mt-8 prose prose-invert max-w-none'>"
        "<h3 class='text-2xl mb-4'>Analysis</h3>"
        f"{analysis_html}</div>"
    )


def build_comparison_analysis_prompt(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    comparison_summary: dict,
    user_query: str,
) -> str:
    """Build the reusable LLM prompt for two-driver comparison narration."""
    return f"""Analyze the lap time comparison between {driver_code1} and {driver_code2} in the {race} {year} race.

Statistics:
- {driver_code1}: Average {comparison_summary.get('driver1_avg', 0) or 0:.3f}s, Fastest {comparison_summary.get('driver1_best', 0) or 0:.3f}s, Slowest {comparison_summary.get('driver1_slowest', 0) or 0:.3f}s
- {driver_code2}: Average {comparison_summary.get('driver2_avg', 0) or 0:.3f}s, Fastest {comparison_summary.get('driver2_best', 0) or 0:.3f}s, Slowest {comparison_summary.get('driver2_slowest', 0) or 0:.3f}s

Pit Stops:
- {driver_code1} pit stops: {json.dumps(comparison_summary.get('driver1_pit_stops', []), indent=2) if comparison_summary.get('driver1_pit_stops') else "No pit stops recorded"}
- {driver_code2} pit stops: {json.dumps(comparison_summary.get('driver2_pit_stops', []), indent=2) if comparison_summary.get('driver2_pit_stops') else "No pit stops recorded"}

Laps with significant differences (>0.5s):
{json.dumps(comparison_summary.get('significant_delta_laps', [])[:20], indent=2)}

User query: {user_query}

Provide a detailed analysis focusing on:
1. Overall performance comparison
2. When and why one driver had slower laps
3. Pit stop strategies and their impact on lap times
4. Patterns in the lap time differences, especially around pit stops
5. Any notable events or strategies visible in the data

Write in a clear, informative style suitable for F1 fans. Pay special attention to how pit stops affected lap times and race strategy."""

