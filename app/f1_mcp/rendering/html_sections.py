"""Reusable HTML snippets for F1 MCP web responses."""

from __future__ import annotations

import json
import re
from html import escape

import markdown


def _format_lap_time(lap: dict) -> str:
    """Render lap time as M:SS.mmm for readability."""
    raw = lap.get("LapTime")
    if isinstance(raw, str):
        match = re.search(r"(?:(\d+)\s+days?\s+)?(\d+):(\d+):(\d+(?:\.\d+)?)", raw)
        if match:
            days = int(match.group(1) or 0)
            hours = int(match.group(2))
            minutes = int(match.group(3))
            seconds = float(match.group(4))
            total_minutes = days * 24 * 60 + hours * 60 + minutes
            return f"{total_minutes}:{seconds:06.3f}"

    try:
        sec = float(lap.get("LapTimeSeconds", 0))
        mins = int(sec // 60)
        rem = sec - (mins * 60)
        return f"{mins}:{rem:06.3f}"
    except (TypeError, ValueError):
        return str(raw or "")


def render_lap_times_table(lap_data: list[dict], include_seconds: bool = True) -> str:
    """Render a lap-times table for the web UI."""
    if include_seconds:
        header = (
            "<thead><tr><th>Lap</th><th>Lap Time</th><th>Compound</th></tr></thead>"
        )
        rows = "".join(
            f"<tr><td>{lap.get('LapNumber', '')}</td><td>{_format_lap_time(lap)}</td>"
            f"<td>{lap.get('Compound', '')}</td></tr>"
            for lap in lap_data
        )
    else:
        header = "<thead><tr><th>Lap</th><th>Lap Time</th><th>Compound</th></tr></thead>"
        rows = "".join(
            f"<tr><td>{lap.get('LapNumber', '')}</td><td>{_format_lap_time(lap)}</td>"
            f"<td>{lap.get('Compound', '')}</td></tr>"
            for lap in lap_data
        )
    return (
        "<div class='mt-4'><h3 class='text-2xl mb-4'>Lap Times</h3>"
        f"<table class='table table-zebra w-full'>{header}<tbody>{rows}</tbody></table></div>"
    )


def _clean_result_value(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "nan", "nat"}:
        return ""
    return text


def _extract_gap_to_winner(row: dict) -> str:
    """Return a readable gap/status string for race result rows."""
    time_val = _clean_result_value(row.get("Time"))
    if time_val and time_val != "0 days 00:00:00":
        return time_val
    status_val = _clean_result_value(row.get("Status"))
    return status_val


def render_results_summary(query: str, year: int, race: str, results: list[dict]) -> str:
    """Render a concise, query-aware summary for race-results responses."""
    if not results:
        return ""

    sorted_results = sorted(results, key=lambda row: int(row.get("Position", 9999)))
    winner = sorted_results[0]
    p2 = next((row for row in sorted_results if int(row.get("Position", 9999)) == 2), None)
    podium = [row for row in sorted_results if int(row.get("Position", 9999)) in {1, 2, 3}]

    winner_name = escape(_clean_result_value(winner.get("BroadcastName")) or "Unknown")
    winner_team = escape(_clean_result_value(winner.get("TeamName")) or "Unknown team")
    parts = [
        f"<p><strong>Winner:</strong> {winner_name} ({winner_team})</p>",
    ]

    q = (query or "").lower()
    if "gap" in q or "p2" in q or "second" in q:
        if p2:
            p2_name = escape(_clean_result_value(p2.get("BroadcastName")) or "Unknown")
            gap = escape(_extract_gap_to_winner(p2))
            if gap:
                parts.append(f"<p><strong>Gap to P2 ({p2_name}):</strong> {gap}</p>")
            else:
                parts.append(
                    f"<p><strong>P2:</strong> {p2_name} (gap not available in timing payload)</p>"
                )
        else:
            parts.append("<p><strong>Gap to P2:</strong> not available</p>")

    if "podium" in q:
        podium_text = ", ".join(
            f"P{int(r.get('Position', 0))} {escape(_clean_result_value(r.get('BroadcastName')))}"
            for r in podium
        )
        if podium_text:
            parts.append(f"<p><strong>Podium:</strong> {podium_text}</p>")

    return (
        "<div class='rounded-lg border border-base-300 bg-base-200/40 p-4 mb-4'>"
        f"<p class='text-sm opacity-80 mb-2'>{escape(str(race))} {year} quick answer</p>"
        f"{''.join(parts)}</div>"
    )


def render_results_table(year: int, race: str, results: list[dict]) -> str:
    """Render race results with an extra timing/status column when available."""
    rows = "".join(
        "<tr>"
        f"<td>{int(r.get('Position', 0))}</td>"
        f"<td>{escape(_clean_result_value(r.get('BroadcastName')))}</td>"
        f"<td>{escape(_clean_result_value(r.get('TeamName')))}</td>"
        f"<td>{escape(_extract_gap_to_winner(r)) or '—'}</td>"
        "</tr>"
        for r in sorted(results, key=lambda row: int(row.get("Position", 9999)))[:10]
    )
    return (
        f"<h2>{escape(str(race))} {year} Results</h2>"
        "<table class='table table-zebra w-full'>"
        "<thead><tr><th>Pos</th><th>Driver</th><th>Team</th><th>Gap / Status</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
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

