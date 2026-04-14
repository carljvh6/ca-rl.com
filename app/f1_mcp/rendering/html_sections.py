"""Reusable HTML snippets for F1 MCP web responses."""

from __future__ import annotations

import json
import re
from html import escape

import markdown

from f1_mcp.providers.session_provider import describe_session_type, normalize_session_type


def format_session_suffix(session_type: str | None) -> str:
    """Return a short heading suffix for non-default sessions."""
    normalized = normalize_session_type(session_type)
    return "" if normalized == "R" else f" ({normalized})"


def format_session_heading(prefix: str, *, year: int, race: str, session_type: str | None) -> str:
    """Build a standard heading with session awareness."""
    normalized = normalize_session_type(session_type)
    if normalized == "R":
        return f"{prefix} — {escape(str(race))} {year}"
    return f"{prefix} — {escape(str(race))} {year} ({normalized})"


def format_session_context(session_type: str | None) -> str:
    """Return a human-readable session label for prose copy."""
    normalized = normalize_session_type(session_type)
    return "race" if normalized == "R" else describe_session_type(normalized)


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


def render_results_summary(
    query: str,
    year: int,
    race: str,
    results: list[dict],
    session_type: str = "R",
) -> str:
    """Render a concise, query-aware summary for session results responses."""
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
        f"<p class='text-sm opacity-80 mb-2'>{escape(str(race))} {year} {escape(format_session_context(session_type))} quick answer</p>"
        f"{''.join(parts)}</div>"
    )


def render_results_table(year: int, race: str, results: list[dict], session_type: str = "R") -> str:
    """Render session results with an extra timing/status column when available."""
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
        f"<h2>{format_session_heading('F1 Results', year=year, race=race, session_type=session_type)}</h2>"
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
    session_type = comparison_summary.get("session_type", "R")
    session_context = format_session_context(session_type)
    if normalize_session_type(session_type) in {"Q", "SQ"}:
        return f"""Analyze the qualifying comparison between {driver_code1} and {driver_code2} in the {race} {year} {session_context}.

Use only PUSH laps for pace conclusions. Treat OUT, COOL, and IN laps as run-structure context.

Qualifying summary:
{json.dumps(comparison_summary, indent=2)}

User query: {user_query}

Provide a concise analysis covering:
1. Best lap by qualifying segment (Q1/Q2/Q3)
2. Run structure and when each driver improved
3. Improvements from early push laps to peak pace
4. Invalidated, deleted, or compromised attempts
5. No references to pit stops or average-of-all-laps pace metrics

Write in a clear, informative style for F1 fans."""
    return f"""Analyze the lap time comparison between {driver_code1} and {driver_code2} in the {race} {year} {session_context}.

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


def _format_seconds(value: object) -> str:
    if value is None:
        return "—"
    try:
        total = float(value)
    except (TypeError, ValueError):
        return "—"
    mins = int(total // 60)
    secs = total - mins * 60
    return f"{mins}:{secs:06.3f}"


def _render_key_value_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "<p class='opacity-70'>No data available.</p>"
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        "<table class='table table-zebra w-full'>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _render_section(title: str, inner_html: str) -> str:
    return (
        "<section class='mt-6 rounded-lg border border-base-300 bg-base-200/30 p-4'>"
        f"<h3 class='text-xl mb-3'>{escape(title)}</h3>"
        f"{inner_html}</section>"
    )


def render_qualifying_runs_sections(result: dict) -> str:
    """Render the qualifying run analysis UI sections for one driver."""
    segments = result.get("segments", [])
    if not segments:
        return "<p class='opacity-70'>No qualifying segments available.</p>"

    best_rows: list[list[str]] = []
    structure_rows: list[list[str]] = []
    improvement_rows: list[list[str]] = []
    invalid_rows: list[list[str]] = []

    for segment in segments:
        segment_name = str(segment.get("name") or "")
        best_rows.append([escape(segment_name), escape(_format_seconds(segment.get("best_valid_lap_seconds")))])
        for run in segment.get("runs", []):
            lap_summary = ", ".join(
                f"L{lap.get('lap_number')} {lap.get('lap_type')}"
                + (f" {_format_seconds(lap.get('lap_time_seconds'))}" if lap.get("lap_time_seconds") is not None else "")
                for lap in run.get("laps", [])
            )
            structure_rows.append(
                [
                    escape(segment_name),
                    escape(str(run.get("run_number"))),
                    escape(lap_summary),
                ]
            )
            improvement_rows.append(
                [
                    escape(segment_name),
                    escape(str(run.get("run_number"))),
                    escape(_format_seconds(run.get("best_valid_push_lap_seconds"))),
                    "Yes" if run.get("improved_on_final_push") else "No",
                ]
            )
            compromised = [
                f"L{lap.get('lap_number')} {lap.get('lap_type')}"
                for lap in run.get("laps", [])
                if (not lap.get("is_valid")) or lap.get("lap_type") == "ABORTED" or lap.get("is_deleted")
            ]
            if compromised:
                invalid_rows.append(
                    [
                        escape(segment_name),
                        escape(str(run.get("run_number"))),
                        escape(", ".join(compromised)),
                    ]
                )

    push_rows = [
        [
            escape(str(segment.get("name") or "")),
            escape(str(run.get("run_number"))),
            escape(", ".join(
                _format_seconds(lap.get("lap_time_seconds"))
                for lap in run.get("laps", [])
                if lap.get("lap_type") == "PUSH" and lap.get("lap_time_seconds") is not None
            ) or "—"),
        ]
        for segment in segments
        for run in segment.get("runs", [])
    ]

    return "".join(
        [
            _render_section(
                "Best laps by segment",
                _render_key_value_table(["Segment", "Best valid push lap"], best_rows),
            ),
            _render_section(
                "Run structure",
                _render_key_value_table(["Segment", "Run", "Lap sequence"], structure_rows),
            ),
            _render_section(
                "Push-lap comparison",
                _render_key_value_table(["Segment", "Run", "Push laps"], push_rows),
            ),
            _render_section(
                "Improvements across attempts",
                _render_key_value_table(
                    ["Segment", "Run", "Best push", "Improved on final push"],
                    improvement_rows,
                ),
            ),
            _render_section(
                "Invalid / compromised laps",
                _render_key_value_table(["Segment", "Run", "Laps"], invalid_rows),
            ),
        ]
    )


def render_qualifying_comparison_sections(result: dict) -> str:
    """Render qualifying comparison sections for two drivers."""
    driver1 = str(result.get("driver_code1") or "")
    driver2 = str(result.get("driver_code2") or "")
    segments = result.get("segments", [])

    best_rows = [
        [
            escape(segment.get("name") or ""),
            escape(_format_seconds(segment.get("best_valid_lap_seconds", {}).get(driver1))),
            escape(_format_seconds(segment.get("best_valid_lap_seconds", {}).get(driver2))),
        ]
        for segment in segments
    ]

    structure_rows: list[list[str]] = []
    push_rows: list[list[str]] = []
    for segment in segments:
        for driver_code in (driver1, driver2):
            for run in segment.get("run_push_laps", {}).get(driver_code, []):
                push_laps = ", ".join(
                    _format_seconds(lap.get("lap_time_seconds"))
                    for lap in run.get("push_laps", [])
                    if lap.get("lap_time_seconds") is not None
                )
                push_rows.append(
                    [
                        escape(segment.get("name") or ""),
                        escape(driver_code),
                        escape(str(run.get("run_number"))),
                        escape(push_laps or "—"),
                    ]
                )
                structure_rows.append(
                    [
                        escape(segment.get("name") or ""),
                        escape(driver_code),
                        escape(str(run.get("run_number"))),
                        escape(str(len(run.get("push_laps", [])))),
                    ]
                )

    improvements = result.get("improvement_from_first_push_to_best", {})
    invalid_counts = result.get("invalid_deleted_aborted_attempt_counts", {})
    improvement_rows = [
        [escape(driver1), escape(_format_seconds(improvements.get(driver1))), escape(_format_seconds(result.get("best_overall_qualifying_lap", {}).get(driver1)))],
        [escape(driver2), escape(_format_seconds(improvements.get(driver2))), escape(_format_seconds(result.get("best_overall_qualifying_lap", {}).get(driver2)))],
    ]
    invalid_rows = [
        [
            escape(driver_code),
            escape(str(counts.get("invalid_push_laps", 0))),
            escape(str(counts.get("aborted_laps", 0))),
            escape(str(counts.get("deleted_laps", 0))),
        ]
        for driver_code, counts in invalid_counts.items()
    ]

    return "".join(
        [
            _render_section(
                "Best laps by segment",
                _render_key_value_table(["Segment", driver1, driver2], best_rows),
            ),
            _render_section(
                "Run structure",
                _render_key_value_table(["Segment", "Driver", "Run", "Push laps"], structure_rows),
            ),
            _render_section(
                "Push-lap comparison",
                _render_key_value_table(["Segment", "Driver", "Run", "Push lap times"], push_rows),
            ),
            _render_section(
                "Improvements across attempts",
                _render_key_value_table(["Driver", "First push to best", "Best overall"], improvement_rows),
            ),
            _render_section(
                "Invalid / compromised laps",
                _render_key_value_table(["Driver", "Invalid push", "Aborted", "Deleted"], invalid_rows),
            ),
        ]
    )


def render_qualifying_runs_prose(result: dict) -> str:
    """Render deterministic prose for a single-driver qualifying analysis."""
    driver_code = str(result.get("driver_code") or "")
    segments = result.get("segments", [])
    if not segments:
        return ""

    segment_bits: list[str] = []
    total_runs = 0
    compromised_bits: list[str] = []
    for segment in segments:
        runs = segment.get("runs", [])
        total_runs += len(runs)
        best = segment.get("best_valid_lap_seconds")
        if best is not None:
            segment_bits.append(f"{segment.get('name')} best was {_format_seconds(best)}")
        compromised = []
        for run in runs:
            for lap in run.get("laps", []):
                if lap.get("lap_type") == "ABORTED" or lap.get("is_deleted") or not lap.get("is_valid"):
                    compromised.append(f"L{lap.get('lap_number')} {lap.get('lap_type')}")
        if compromised:
            compromised_bits.append(f"{segment.get('name')}: {', '.join(compromised)}")

    summary = (
        f"<p>{escape(driver_code)}'s qualifying is split into {total_runs} run"
        f"{'' if total_runs == 1 else 's'} across {len(segments)} segment"
        f"{'' if len(segments) == 1 else 's'}. "
        f"{escape('; '.join(segment_bits))}.</p>"
    )
    detail = (
        "<p>Headline pace is based only on push laps. "
        "Out laps, cooldown laps, and in laps are shown as run structure so you can see how each attempt was built.</p>"
    )
    compromised_html = (
        f"<p>Compromised laps: {escape(' | '.join(compromised_bits))}.</p>"
        if compromised_bits
        else "<p>No invalid or obviously compromised laps were flagged in this run summary.</p>"
    )
    return (
        "<div class='mt-6 prose prose-invert max-w-none'>"
        "<h3 class='text-2xl mb-4'>Analysis</h3>"
        f"{summary}{detail}{compromised_html}</div>"
    )


def render_qualifying_comparison_prose(result: dict) -> str:
    """Render deterministic prose for a two-driver qualifying comparison."""
    driver1 = str(result.get("driver_code1") or "")
    driver2 = str(result.get("driver_code2") or "")
    bests = result.get("best_overall_qualifying_lap", {})
    improvements = result.get("improvement_from_first_push_to_best", {})
    invalid = result.get("invalid_deleted_aborted_attempt_counts", {})

    faster_driver = None
    best1 = bests.get(driver1)
    best2 = bests.get(driver2)
    if best1 is not None and best2 is not None:
        faster_driver = driver1 if best1 < best2 else driver2 if best2 < best1 else "Neither"

    segment_bits = []
    for segment in result.get("segments", []):
        times = segment.get("best_valid_lap_seconds", {})
        t1 = times.get(driver1)
        t2 = times.get(driver2)
        if t1 is None or t2 is None:
            continue
        leader = driver1 if t1 < t2 else driver2 if t2 < t1 else "Tied"
        if leader == "Tied":
            segment_bits.append(f"{segment.get('name')} was tied on {_format_seconds(t1)}")
        else:
            gap = abs(float(t1) - float(t2))
            segment_bits.append(f"{segment.get('name')} went to {leader} by {gap:.3f}s")

    headline = (
        f"<p>Best outright push-lap pace favored {escape(faster_driver)}: "
        f"{escape(driver1)} {_format_seconds(best1)} versus {escape(driver2)} {_format_seconds(best2)}.</p>"
        if faster_driver and faster_driver != "Neither"
        else f"<p>Both drivers finished with the same best push-lap benchmark at {_format_seconds(best1)}.</p>"
        if best1 is not None and best2 is not None
        else "<p>Best overall push-lap pace could not be determined for both drivers.</p>"
    )
    progression = (
        f"<p>Segment progression: {escape('; '.join(segment_bits))}.</p>"
        if segment_bits
        else "<p>Segment-by-segment progression is limited because one or both drivers are missing valid push laps in some phases.</p>"
    )
    improvement = (
        f"<p>Improvement from first valid push to best lap: {escape(driver1)} {_format_seconds(improvements.get(driver1))}, "
        f"{escape(driver2)} {_format_seconds(improvements.get(driver2))}. "
        "Only push laps are used for this comparison.</p>"
    )
    invalid_text = ", ".join(
        f"{driver}: {counts.get('invalid_push_laps', 0)} invalid push, {counts.get('aborted_laps', 0)} aborted, {counts.get('deleted_laps', 0)} deleted"
        for driver, counts in invalid.items()
    )
    invalid_html = (
        f"<p>Compromised attempts: {escape(invalid_text)}.</p>"
        if invalid_text
        else "<p>No compromised attempts were flagged.</p>"
    )
    return (
        "<div class='mt-6 prose prose-invert max-w-none'>"
        "<h3 class='text-2xl mb-4'>Analysis</h3>"
        f"{headline}{progression}{improvement}{invalid_html}</div>"
    )
