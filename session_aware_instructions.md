Task: Add session-aware F1 MCP support, then expose it end-to-end in the web app

Branch:
- develop

Goal:
- Make the existing F1 tools session-aware instead of race-only.
- Support at least: R, Q, SQ, S, FP1, FP2, FP3
- Keep current race behavior as the default.
- Update the Gemini routing layer and UI rendering so queries like:
  - "Compare Norris and Leclerc in qualifying at Monza 2025"
  - "Show Verstappen's FP2 lap times in Bahrain 2025"
  actually work.

Why this change:
- app/f1_mcp_server.py currently wraps the refactored tools cleanly, but all wrappers hardcode session_type="R".
- app/main.py example prompts already imply session-aware support, but the routing prompt still only knows about the older race-only tools.

Files to inspect first:
- app/f1_mcp_server.py
- app/main.py
- app/f1_mcp/tools/reference_tools.py
- app/f1_mcp/tools/analysis_tools.py
- any shared FastF1/session loading helpers in the new package

Implementation requirements:

1) MCP tool signatures
Update these exported MCP tools in app/f1_mcp_server.py:
- get_f1_results(year: int, race: str, session_type: str = "R") -> dict
- get_driver_lap_times(year: int, race: str, driver_code: str, session_type: str = "R") -> dict
- plot_driver_lap_times(year: int, race: str, driver_code: str, session_type: str = "R") -> dict
- compare_driver_lap_times(year: int, race: str, driver_code1: str, driver_code2: str, session_type: str = "R") -> dict

Leave get_f1_schedule unchanged.

2) Underlying tool implementations
In the layered package, thread session_type through to the actual FastF1 calls.
Wherever a session is loaded, replace hardcoded race loading with the passed session_type.
Normalize aliases before loading:
- "R", "race" -> "R"
- "Q", "quali", "qualifying", "q3" -> "Q"
- "S", "sprint" -> "S"
- "SQ", "sprint qualifying", "sprint shootout" -> "SQ"
- "FP1", "practice 1" -> "FP1"
- "FP2", "practice 2" -> "FP2"
- "FP3", "practice 3" -> "FP3"

Create one shared normalizer/helper instead of duplicating logic.

3) Validation
Add a helper like:
- normalize_session_type(session_type: str | None) -> str
Raise a clean error payload for unsupported values, e.g.
{
  "error": "Unsupported session_type 'XYZ'. Use one of: R, Q, SQ, S, FP1, FP2, FP3."
}

4) Routing prompt in app/main.py
Update the Gemini routing prompt so it can extract:
- tool
- year
- race
- driver_code
- driver_code1
- driver_code2
- session_type

Rules:
- default session_type to "R" if omitted
- infer "Q" for qualifying language
- infer "S" or "SQ" for sprint language where obvious
- infer "FP1"/"FP2"/"FP3" for practice mentions
- comparison requests with two drivers should still route to compare_driver_lap_times
- "lap times" without "plot" should go to get_driver_lap_times
- "plot" or "graph" should go to plot_driver_lap_times

Update the JSON schema example in the prompt to include session_type.

5) Tool invocation layer in app/main.py
Pass session_type through when calling the tools.
Add session_type into logs/traces so the agent log panel shows it.
Where results/lap-time/comparison sections are rendered, show the selected session in headings/subheadings.

Examples:
- "## F1 Results — 2025 Monza (Q)"
- "## Lap times — Verstappen, Bahrain 2025 (FP2)"
- "## Driver comparison — Norris vs Leclerc, Monza 2025 (Q)"

6) Rendering / copy updates
Wherever the UI currently says "race", make wording session-aware when appropriate.
Do not break current race wording when session_type == "R".

7) Backward compatibility
Existing race-only calls must continue to work unchanged.
If session_type is not provided anywhere, behavior should remain the same as today.

8) Tests
Add or update lightweight tests for:
- session normalization
- wrapper functions forwarding session_type
- invalid session_type handling
- routing prompt parser expectations if there are parser tests
- at least one happy-path call each for:
  - qualifying results
  - FP2 lap times
  - qualifying driver comparison

If there is no current test structure, add a small focused test module rather than a huge suite.

9) Nice-to-have but do if easy
Return normalized session_type in successful payloads so the UI can rely on it:
{
  "session_type": "Q",
  ...
}

Acceptance criteria:
- These work end-to-end from the web app:
  1. "Who won qualifying at Monza 2025?"
  2. "Show Verstappen's FP2 lap times in Bahrain 2025"
  3. "Compare Norris and Leclerc in qualifying at Monza 2025"
- Existing race queries still work:
  4. "What were the results of the 2025 Bahrain Grand Prix?"
  5. "Compare Verstappen and Norris in Bahrain 2025"
- Unsupported session strings fail cleanly with a user-friendly error.

Suggested commit sequence:
1. session normalization helper
2. tool-layer session_type plumbing
3. MCP wrapper signature updates
4. app/main.py routing + rendering updates
5. tests

Please implement the code, run tests if available, and summarize:
- files changed
- any assumptions made
- any follow-up work needed