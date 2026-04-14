Refactor the F1 MCP architecture on the develop branch of carljvh6/ca-rl.com into clear layers, without changing the external behavior first.

Context from the current codebase:
- `app/f1_mcp_server.py` currently mixes FastF1 data loading, domain logic, MCP tool registration, and chart generation in one file. It currently exposes tools like `get_f1_results`, `get_f1_schedule`, `get_driver_lap_times`, and plotting/comparison helpers, with race session hardcoded as `'R'` in several places.  [oai_citation:0‡GitHub](https://raw.githubusercontent.com/carljvh6/ca-rl.com/develop/app/f1_mcp_server.py)
- `app/main.py` currently contains app routing/orchestration logic and also performs extra inline comparison analysis and LLM-based narration, so some domain analysis lives in the web layer instead of reusable services.  [oai_citation:1‡GitHub](https://raw.githubusercontent.com/carljvh6/ca-rl.com/develop/app/main.py)
- The `app/` directory currently contains only `f1_mcp_server.py`, `main.py`, and `rag_routes.py`, so this refactor should introduce an internal package structure under `app/`.  [oai_citation:2‡GitHub](https://github.com/carljvh6/ca-rl.com/tree/develop/app)

Goals:
1. Create a maintainable layered architecture.
2. Preserve existing endpoints/features during the refactor.
3. Prepare the codebase for new MCP tools like stint analysis, session-type support, position evolution, and higher-level “explain result” workflows.
4. Make the core analysis reusable from both MCP tools and the web UI.

Target architecture:
Create this package structure under `app/`:

app/
  main.py
  rag_routes.py
  f1_mcp_server.py
  f1_mcp/
    __init__.py
    providers/
      __init__.py
      session_provider.py
      schedule_provider.py
      laps_provider.py
    services/
      __init__.py
      lap_analysis.py
      stint_analysis.py
      compare_analysis.py
    schemas/
      __init__.py
      session_models.py
      lap_models.py
      comparison_models.py
    rendering/
      __init__.py
      plots.py
      html_sections.py
    tools/
      __init__.py
      reference_tools.py
      analysis_tools.py

Layer responsibilities:

1) Providers layer
Purpose: raw FastF1 access, loading, normalization, caching helpers, and dataframe extraction only.
No MCP registration, no HTML rendering, no Gemini/LLM logic.

Implement:
- `providers/session_provider.py`
  - `load_session(year: int, race: str, session_type: str)`
  - centralize `fastf1.get_session(...)` and `.load()`
  - validate `session_type`
  - keep session-loading behavior consistent across tools
- `providers/schedule_provider.py`
  - `get_schedule_df(year: int) -> pd.DataFrame`
- `providers/laps_provider.py`
  - `get_driver_laps_df(year: int, race: str, session_type: str, driver_code: str) -> pd.DataFrame`
  - include the same core columns currently used in lap tools
  - handle missing/invalid lap times robustly
  - preserve the current semantics as much as possible

2) Services layer
Purpose: convert raw dataframes/sessions into F1 concepts and structured analysis.
No HTML. No MCP decorators. No web request objects. No Gemini calls.

Implement:
- `services/lap_analysis.py`
  - helper for lap normalization and summary metrics
  - compute avg lap, best lap, lap count, valid lap count
- `services/stint_analysis.py`
  - identify stints from compound changes and pit in/out markers
  - return structured stint summaries:
    - stint_number
    - compound
    - start_lap
    - end_lap
    - lap_count
    - avg_lap_time_seconds
    - best_lap_time_seconds
    - simple degradation slope
- `services/compare_analysis.py`
  - reusable two-driver comparison logic currently done inline in `main.py`
  - same-lap delta table
  - avg pace comparison
  - best lap comparison
  - pit-stop lap extraction
  - “significant delta laps” extraction
  - return structured dict/data objects suitable for UI rendering or LLM summarization

3) Schemas layer
Purpose: define clean typed structures for outputs passed between providers/services/tools/UI.
Use dataclasses, TypedDicts, or pydantic models if already available in the repo, but keep it lightweight.
Create models for:
- schedule entries
- lap records
- stint summaries
- comparison summaries

4) Rendering layer
Purpose: presentation-only logic.
Move plotting/chart creation out of core MCP data-access logic.

Implement:
- `rendering/plots.py`
  - move current matplotlib/base64 plot generation here
  - functions for single-driver lap chart
  - functions for two-driver comparison chart
- `rendering/html_sections.py`
  - any reusable HTML snippets/structured rendering helpers currently built ad hoc in `main.py`

5) Tools layer
Purpose: thin MCP wrappers around providers/services.
Tools should return structured dicts and call the provider/service layers.
Keep MCP registration here or import into `f1_mcp_server.py`.

Implement:
- `tools/reference_tools.py`
  - `get_f1_schedule`
  - `get_f1_results`
- `tools/analysis_tools.py`
  - `get_driver_lap_times`
  - `plot_driver_lap_times`
  - `compare_driver_lap_times`

Refactor instructions:
A. Preserve current public behavior
- Keep the existing MCP tool names working.
- Keep existing route behavior in `main.py` working.
- Do not break current output payload shapes unless absolutely necessary.
- If you need to add fields, do so additively.

B. Introduce `session_type` internally now
- Even if the UI does not expose it yet, thread `session_type` through the provider/service APIs.
- Default it to `'R'` to preserve current behavior.
- Replace hardcoded race-session loading in core logic with the new abstraction.

C. Move inline comparison logic out of `main.py`
- Identify comparison/statistics/pit-stop extraction logic currently embedded in the app layer.
- Move it into `services/compare_analysis.py`.
- `main.py` should orchestrate and render, not compute race-analysis primitives directly.

D. Reduce `f1_mcp_server.py` to an entrypoint/registry
- After refactor, `f1_mcp_server.py` should mostly wire up FastMCP and import/register the tool functions.
- It should not contain most of the business logic.

E. Keep rendering separate
- Any chart HTML/base64 creation should live in `rendering/plots.py`.
- MCP tool functions may call rendering helpers, but raw data retrieval and analysis must not depend on rendering.

F. Add docstrings and clear function boundaries
- Each new module should have a top-level comment/docstring describing its role.
- Each service should describe inputs/outputs clearly.

Desired follow-up structure after this refactor:
- Providers = data access
- Services = F1 analysis
- Tools = MCP API surface
- Rendering = charts/HTML
- Main app = NL routing + orchestration + response composition

Implementation phases:
Phase 1:
- Create new package structure and move raw FastF1/session/laps/schedule access into providers.
- Update existing tools to use providers.

Phase 2:
- Extract comparison/statistics logic from `main.py` into services.
- Update `main.py` to call services.

Phase 3:
- Move plotting to rendering layer.
- Slim down `f1_mcp_server.py` into a registry/entrypoint.

Phase 4:
- Add internal `session_type='R'` plumbed through all relevant functions.
- Do not yet redesign the UI unless needed for compatibility.

Constraints:
- Work only on the develop branch.
- Keep changes incremental and easy to review.
- Prefer small clean commits.
- Do not add speculative features yet beyond architecture prep.
- Do not remove existing functionality.
- Avoid overengineering.

Deliverables:
1. The refactored code.
2. A concise diff summary by module.
3. A short architecture note explaining the new layering.
4. Manual test steps for:
   - schedule lookup
   - results lookup
   - driver lap retrieval
   - single-driver lap plot
   - two-driver lap comparison
5. A short “next features enabled by this refactor” note mentioning:
   - session-type support
   - stint analysis
   - position evolution
   - explain-result workflows

Before finishing, verify imports and basic app startup paths so the refactor is runnable.