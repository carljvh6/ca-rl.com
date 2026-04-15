Task: Add stint analysis tools to the restructured F1 MCP and expose them end-to-end in the web app

Branch:
- develop

Goal:
- Add first-class stint analysis for race and sprint sessions.
- Make the existing “Analyze stints” prompts real.
- Build the foundation for later strategy and result-explainer workflows.

Files to inspect first:
- app/f1_mcp_server.py
- app/main.py
- app/f1_mcp/tools/analysis_tools.py
- any shared FastF1 session/lap utilities
- rendering helpers under app/f1_mcp/rendering/

Implement these MCP tools:

1) analyze_driver_stints(
    year: int,
    race: str,
    driver_code: str,
    session_type: str = "R"
) -> dict

2) compare_driver_stints(
    year: int,
    race: str,
    driver_code1: str,
    driver_code2: str,
    session_type: str = "R"
) -> dict

Session support:
- default to "R"
- also support "S" if sprint data is available
- fail cleanly for sessions where stint analysis is not meaningful, e.g. qualifying:
  {
    "error": "Stint analysis is only supported for race-like sessions (R, S)."
  }

Definition of a stint:
- contiguous laps on the same tyre compound between pit exits and next pit entry/end of session
- include start_lap and end_lap
- keep explicit flags for out-lap and in-lap
- compute clean metrics both including and excluding in/out laps

For analyze_driver_stints, return:
{
  "year": 2025,
  "race": "Bahrain",
  "session_type": "R",
  "driver_code": "VER",
  "stints": [
    {
      "stint_number": 1,
      "compound": "SOFT",
      "start_lap": 1,
      "end_lap": 14,
      "num_laps": 14,
      "laps": [...],
      "avg_lap_seconds_all": ...,
      "avg_lap_seconds_clean": ...,
      "median_lap_seconds_clean": ...,
      "best_lap_seconds": ...,
      "degradation_slope_seconds_per_lap": ...,
      "includes_out_lap": true,
      "includes_in_lap": true
    }
  ],
  "summary": {
    "num_stints": ...,
    "best_stint_by_avg_clean": ...,
    "longest_stint": ...,
    "shortest_stint": ...
  }
}

For compare_driver_stints, return:
{
  "year": 2025,
  "race": "Bahrain",
  "session_type": "R",
  "driver_code1": "VER",
  "driver_code2": "NOR",
  "driver1_stints": [...],
  "driver2_stints": [...],
  "comparison": {
    "stint_matchups": [
      {
        "driver1_stint_number": 1,
        "driver2_stint_number": 1,
        "driver1_compound": "SOFT",
        "driver2_compound": "SOFT",
        "avg_clean_delta_seconds": ...,
        "median_clean_delta_seconds": ...,
        "best_lap_delta_seconds": ...,
        "degradation_delta_seconds_per_lap": ...,
        "faster_driver": "VER"
      }
    ]
  }
}

Implementation notes:
- Exclude obvious non-representative laps from clean metrics where possible:
  - pit in laps
  - pit out laps
  - laps without valid lap time
  - optionally laps under SC/VSC if track-status metadata is available
- Keep both “all laps” and “clean laps” stats to avoid hiding data
- Reuse existing session loading and session_type normalization helpers
- Do not duplicate loading logic

Update app/f1_mcp_server.py:
- register the two new tools

Update app/main.py:
- import the two new tools
- update the Gemini routing prompt to support:
  - "analyze X's stints"
  - "compare the stints of X and Y"
  - "tyre degradation"
  - "race pace by stint"
- pass session_type through
- render the results in structured sections:
  - stint table(s)
  - stint summary
  - comparison summary
- add a dedicated LLM analysis pass for compare_driver_stints similar to the existing compare_driver_lap_times flow

Rendering:
- create HTML renderers for:
  - single-driver stint table
  - two-driver stint comparison
  - summary cards for best/longest/lowest-deg stint
- headings should show session type

Acceptance criteria:
1. "Analyze Verstappen's stints in Bahrain 2025" works end-to-end
2. "Compare the stints of Norris and Piastri in Miami 2025" works end-to-end
3. "Compare Verstappen and Norris in Bahrain 2025" still works unchanged
4. qualifying requests do not route to stint analysis
5. if someone asks for qualifying stint analysis, they get a clean user-friendly error

Suggested commit order:
1. stint segmentation helper
2. single-driver stint analysis tool
3. two-driver stint comparison tool
4. MCP registration
5. app routing
6. HTML rendering
7. LLM commentary layer
8. tests

Please implement, run tests if available, and summarize:
- files changed
- assumptions
- follow-up recommendations