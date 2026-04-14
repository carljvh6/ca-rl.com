import os
from fasthtml.common import *
import fasthtml.components as fc
from google import genai
from dotenv import load_dotenv
from google.cloud import secretmanager
from urllib.request import Request, urlopen
from urllib.error import URLError
import markdown
import json
import contextvars
import html as html_lib
import logging
import sys
import os
from datetime import datetime
from collections import deque

# Add app directory to path for imports
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from f1_mcp_server import get_f1_results, get_f1_schedule, get_driver_lap_times, plot_driver_lap_times, compare_driver_lap_times
from f1_mcp.rendering.html_sections import (
    build_comparison_analysis_prompt,
    render_comparison_analysis_section,
    render_lap_times_table,
    render_results_summary,
    render_results_table,
)
from f1_mcp.local_llm import get_local_llm_config, ollama_generate

example_prompts = {
    "Schedules": [
        "What is the F1 schedule for 2025?",
        "Show me the 2026 Formula 1 race calendar",
    ],
    "Results": [
        "What were the results of the 2025 Bahrain Grand Prix?",
        "Who finished on the podium in Monza 2025?",
    ],
    "Driver analysis": [
        "Show me Lewis Hamilton's lap times in the 2025 British Grand Prix",
        "Plot Charles Leclerc's lap times for Monza 2025",
    ],
    "Driver comparisons": [
        "Compare Verstappen and Norris in Bahrain 2025",
        "Compare Hamilton and Russell lap times at Silverstone 2025",
    ],
    "Advanced analysis": [
        "Compare Norris and Leclerc in qualifying at Monza 2025",
        "Analyze Verstappen's stints in Bahrain 2025",
        "Compare the stints of Norris and Piastri in Miami 2025",
        "Show Verstappen's FP2 lap times in Bahrain 2025",
        "Who won the 2026 Australian Grand Prix and what was the gap to P2?",
        "Compare qualifying lap times for Verstappen and Leclerc at the 2026 Japanese Grand Prix",
    ],
}

f1_mcp_log_ctx: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "f1_mcp_log_ctx", default=None
)


class _F1MCPContextLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        buf = f1_mcp_log_ctx.get()
        if buf is not None:
            try:
                buf.append(self.format(record))
            except Exception:
                pass


_f1_mcp_ctx_handler = _F1MCPContextLogHandler()
_f1_mcp_ctx_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
)
for _logger_name in ("f1_mcp_server", "f1_mcp"):
    _f1_mcp_py_logger = logging.getLogger(_logger_name)
    if not any(isinstance(h, _F1MCPContextLogHandler) for h in _f1_mcp_py_logger.handlers):
        _f1_mcp_py_logger.addHandler(_f1_mcp_ctx_handler)
        _f1_mcp_py_logger.setLevel(logging.INFO)


def _f1_trace(log: list[str], message: str) -> None:
    log.append(f"{datetime.now().strftime('%H:%M:%S')} {message}")


def _f1_response_with_logs(content_html: str, log_lines: list[str]) -> str:
    body = (
        "(no log entries for this response)"
        if not log_lines
        else html_lib.escape("\n".join(log_lines))
    )
    panel = (
        '<details class="mt-6 border border-base-300 rounded-lg bg-base-200/40">'
        '<summary class="cursor-pointer select-none px-3 py-2 text-sm font-medium hover:bg-base-300/30 rounded-lg">'
        "Agent &amp; tool logs"
        "</summary>"
        '<div class="px-3 pb-3">'
        '<pre class="text-xs whitespace-pre-wrap break-words max-h-96 overflow-y-auto bg-base-300/50 rounded p-3 m-0 font-mono">'
        f"{body}</pre></div></details>"
    )
    return content_html + panel


_SYSTEM_JSON_ONLY = (
    "You are a precise assistant. When the user asks for JSON only, respond with "
    "a single JSON object and nothing else: no markdown, no code fences, no commentary."
)
_SYSTEM_PROSE = (
    "You are a knowledgeable Formula 1 analyst. Write clear, accurate commentary. "
    "Do not invent statistics or lap data."
)


def _f1_strip_json_blob(response_text: str) -> str:
    response_text = (response_text or "").strip()
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()
    stripped = response_text.lstrip()
    if not stripped.startswith("{"):
        start = response_text.find("{")
        end = response_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            response_text = response_text[start : end + 1]
    return response_text.strip()


def _f1_generate_llm_text(
    *,
    use_local: bool,
    client,
    prompt: str,
    log: list[str],
    purpose: str,
    context_label: str,
    json_only: bool,
) -> str:
    if use_local:
        base, model = get_local_llm_config()
        _f1_trace(log, f"Local LLM ({model} @ {base}): {purpose}")
        log_api_call(context_label, f"ollama:{model}", prompt[:400])
        system = _SYSTEM_JSON_ONLY if json_only else _SYSTEM_PROSE
        return ollama_generate(prompt, system=system)
    if client is None:
        raise RuntimeError("Gemini client is not configured")
    _f1_trace(log, f"Gemini (gemini-2.5-flash-lite): {purpose}")
    log_api_call(context_label, "gemini-2.5-flash-lite", prompt[:400])
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )
    return (response.text or "").strip()


# Track API call timestamps for rate limit monitoring
api_call_times = deque(maxlen=100)

def log_api_call(context: str, model: str, request_text: str):
    """Log API call with timestamp and rate limit info"""
    now = datetime.now()
    api_call_times.append(now)
    
    # Count calls in the last minute
    one_minute_ago = datetime.fromtimestamp(now.timestamp() - 60)
    recent_calls = [t for t in api_call_times if t > one_minute_ago]
    
    print(f"\n{'='*60}")
    print(f"[GenAI API Call - {context}]")
    print(f"Timestamp: {now.strftime('%H:%M:%S')}")
    print(f"Model: {model}")
    print(f"Recent calls (last minute): {len(recent_calls)}")
    print(f"Request: {request_text[:300]}..." if len(request_text) > 300 else f"Request: {request_text}")
    print(f"{'='*60}")

daisy_headers = (
    Link(href='https://cdn.jsdelivr.net/npm/daisyui@5', rel='stylesheet', type='text/css'),
    Script(src='https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4'),
    Script("document.documentElement.setAttribute('data-theme', 'dark');"),
    Style("""
        @keyframes hourglass-spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .hourglass-loader {
            display: inline-block;
            animation: hourglass-spin 1s linear infinite;
        }
        .htmx-indicator {
            opacity: 0;
            transition: opacity 200ms ease-in;
            pointer-events: none;
        }
        .htmx-request .htmx-indicator,
        .htmx-request.htmx-indicator {
            opacity: 1;
        }
    """),
    Script("""
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('.menu-toggle').forEach(function(toggle) {
                const arrow = toggle.querySelector('[id$="_arrow"]');
                if (arrow) {
                    arrow.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        const contentId = toggle.getAttribute('data-content-id');
                        const arrowId = toggle.getAttribute('data-arrow-id');
                        const content = document.getElementById(contentId);
                        const arrowEl = document.getElementById(arrowId);
                        if (content) {
                            content.classList.toggle('hidden');
                        }
                        if (arrowEl) {
                            arrowEl.classList.toggle('rotate-180');
                        }
                    });
                }
            });
        });
    """)
)

def Button(*c, cls='', **kw):
    return fc.Button(*c, cls=f"btn {cls}", **kw)

def get_api_key(use_secret_manager=None):
    """
    Get Google API key from Secret Manager (Cloud Run) or environment/.env (local).
    Priority: Environment Variable > Secret Manager > .env file
    
    Args:
        use_secret_manager: If True, force Secret Manager usage. If False, skip Secret Manager.
                           If None (default), auto-detect based on Cloud Run environment.
    
    For Cloud Run: Set GOOGLE_CLOUD_PROJECT env var and create secret named 'GOOGLE_API_KEY' in Secret Manager
    For local: Use .env file with GOOGLE_API_KEY=your_key
    """
    # First, try environment variable (works in both local and Cloud Run)
    # This allows overriding Secret Manager if needed
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if api_key:
        return api_key
    
    # Determine if we should try Secret Manager
    if use_secret_manager is None:
        # Auto-detect: Check if we're running in Cloud Run (K_SERVICE is set by Cloud Run)
        should_use_secret_manager = os.getenv('K_SERVICE') is not None
    else:
        # Use explicit setting
        should_use_secret_manager = use_secret_manager
    
    if should_use_secret_manager:
        # Try Secret Manager
        try:
            # Cloud Run sets GOOGLE_CLOUD_PROJECT automatically, but sometimes it's not set
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
            
            if not project_id:
                # Try alternative env var names
                project_id = os.getenv('GCP_PROJECT') or os.getenv('GCLOUD_PROJECT')
            
            # If still not found, try to get from metadata service (Cloud Run)
            if not project_id:
                try:
                    metadata_url = "http://metadata.google.internal/computeMetadata/v1/project/project-id"
                    req = Request(metadata_url)
                    req.add_header("Metadata-Flavor", "Google")
                    response = urlopen(req, timeout=2)
                    project_id = response.read().decode('utf-8')
                    print(f"Retrieved project ID from metadata service: {project_id}")
                except (URLError, Exception) as meta_error:
                    print(f"Could not get project ID from metadata: {meta_error}")
            
            if project_id:
                secret_name = "GOOGLE_API_KEY"  # Secret name in Secret Manager
                try:
                    client = secretmanager.SecretManagerServiceClient()
                    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
                    print(f"Attempting to fetch secret: {name}")
                    response = client.access_secret_version(request={"name": name})
                    api_key = response.payload.data.decode("UTF-8")
                    if api_key:
                        print("Successfully retrieved API key from Secret Manager")
                        return api_key
                except Exception as sm_error:
                    # Log but don't crash - fall through to .env file
                    print(f"Warning: Secret Manager access failed: {str(sm_error)}")
                    print(f"This is OK if secret doesn't exist or service account lacks permissions")
            else:
                print(f"Warning: Project ID not found. Available env vars: K_SERVICE={os.getenv('K_SERVICE')}, GOOGLE_CLOUD_PROJECT={os.getenv('GOOGLE_CLOUD_PROJECT')}")
        except Exception as e:
            # If Secret Manager fails, log detailed error but don't crash
            import traceback
            error_details = traceback.format_exc()
            print(f"Warning: Error fetching from Secret Manager: {str(e)}")
            print(f"Traceback: {error_details}")
            print("Falling back to .env file or environment variables")
    
    # Fall back to .env file for local development
    load_dotenv()
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if api_key:
        return api_key
    
    # Don't raise error during app startup - return None and let route handlers handle it
    # This prevents app from crashing if API key is missing
    print("Warning: GOOGLE_API_KEY not found in Secret Manager, environment variables, or .env file.")
    print("The app will start but API-dependent routes will fail.")
    return None

def create_menu_item(label, href=None, sub_items=None, menu_id=None):
    """Create a menu item with optional sub-items"""
    if sub_items:
        # Create collapsible menu item with sub-items
        if not menu_id:
            menu_id = f"menu_{label.lower().replace(' ', '_').replace('/', '_')}"
        content_id = f"{menu_id}_content"
        arrow_id = f"{menu_id}_arrow"
        # Get the main page href from the first sub-item
        main_href = sub_items[0][1] if sub_items else href
        
        return Div(
            A(
                Span(label, cls='flex-1 text-left'),
                Span('▼', cls='text-xs transition-transform', id=arrow_id),
                href=main_href,
                cls='btn btn-ghost w-full justify-between cursor-pointer menu-toggle',
                **{'data-content-id': content_id, 'data-arrow-id': arrow_id}
            ),
            Div(
                *[A(sub_label, href=sub_href, cls='btn btn-ghost w-full justify-start pl-8 text-sm py-2 h-auto min-h-0') 
                  for sub_label, sub_href in sub_items],
                cls='flex flex-col gap-1 pl-4 hidden transition-all',
                id=content_id
            ),
            cls='w-full'
        )
    else:
        # Simple menu item without sub-items
        return A(label, href=href, cls='btn btn-ghost w-full justify-start')

def layout(content):
    # Define menu structure with sub-items
    menu_items = [
        create_menu_item('Home', sub_items=[
            ('Main', '/'),
        ]),
        create_menu_item('Blog', sub_items=[
            ('Main', '/blog'),
        ]),
        create_menu_item('Chatbot', sub_items=[
            ('Main', '/chatbot'),
            ('Info', '/chatbot/info'),
        ]),
        create_menu_item('F1 MCP', sub_items=[
            ('Main', '/f1_mcp'),
            ('Info', '/f1_mcp/info'),
        ]),
        create_menu_item('RAG', sub_items=[
            ('Main', '/rag'),
            ('Ingestion', '/rag/ingestion'),
            # ('Retrieval', '/rag/retrieval'),  # COMMENTED OUT - Retrieval functionality temporarily disabled
            ('Info', '/rag/info'),
        ]),
        create_menu_item('About', sub_items=[
            ('Main', '/about'),
        ]),
    ]
    
    sidebar = Div(
        Div(
            *menu_items,
            cls='flex flex-col gap-2 p-4'
        ),
        cls='w-64 min-h-screen bg-base-100'
    )
    main_content = Div(content, cls='flex-1 p-8')
    return Div(sidebar, main_content, cls='flex')

app, rt = fast_app(title="carldotcom's playground", hdrs = daisy_headers)

# Import and register route modules
import rag_routes
rag_routes.register_rag_routes(rt)

# Verify routes are registered (for debugging)
if hasattr(app, 'routes'):
    rag_routes_registered = any('/rag/ingestion' in str(r.path) for r in app.routes)
    if not rag_routes_registered:
        print("WARNING: /rag/ingestion route not found after importing rag_routes")

# Ensure app is available for uvicorn/ASGI
__all__ = ['app']

@rt
def btn_res(nm:str): return f"Button Clicked, hello {nm}!"

@rt
def chatbot_res(message:str): 
    try:
        api_key = get_api_key(use_secret_manager=True)
        if not api_key:
            return "Error: API key not configured. Please set GOOGLE_API_KEY environment variable."
        client = genai.Client(api_key=api_key)

        log_api_call("Chatbot", "gemini-2.5-flash-lite", message)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=message
        )

        # Convert markdown to HTML
        html_content = markdown.markdown(response.text, extensions=['nl2br', 'fenced_code'])
        return html_content
    except Exception as e:
        return f"Error: {str(e)}"

def _f1_mcp_res_run(query: str, log: list[str], *, use_local: bool) -> str:
    """Process F1 queries using MCP tools with Gemini or a local Gemma (Ollama) for routing and narration."""
    routing_response_text = ""
    try:
        if not query or not query.strip():
            _f1_trace(log, "(validation) empty query")
            return "<p>Please enter a question.</p>"

        qdisp = query.strip()
        if len(qdisp) > 240:
            qdisp = qdisp[:240] + "…"
        _f1_trace(log, f"Query: {qdisp}")

        if use_local:
            _f1_trace(log, "LLM backend: local Gemma (Ollama); Gemini API key not required for routing")
            client = None
        else:
            api_key = get_api_key(use_secret_manager=True)
            if not api_key:
                _f1_trace(log, "(validation) missing API key")
                return "<p>Error: API key not configured. Please set GOOGLE_API_KEY environment variable.</p>"
            client = genai.Client(api_key=api_key)

        # Ask Gemini to determine which tool to use
        prompt = f"""Analyze this F1 query and determine which tool to use:
            - get_f1_schedule(year) for schedule questions
            - get_f1_results(year, race) for results questions
            - get_driver_lap_times(year, race, driver_code) for lap time data (without plotting)
            - plot_driver_lap_times(year, race, driver_code) for single driver lap time plots
            - compare_driver_lap_times(year, race, driver_code1, driver_code2) for comparing two drivers' lap times

            Query: {query}

            Respond in JSON: {{"tool": "tool_name", "year": 2024, "race": "race_name", "driver_code": "VER", "driver_code1": "HAM", "driver_code2": "VER"}}
            Extract year (default 2025), race name, and driver code(s) (3-letter code like VER, NOR, HAM) if needed.
            For comparison requests mentioning two drivers, use compare_driver_lap_times with driver_code1 and driver_code2."""

        routing_response_text = _f1_generate_llm_text(
            use_local=use_local,
            client=client,
            prompt=prompt,
            log=log,
            purpose="tool routing",
            context_label="F1 MCP",
            json_only=True,
        )
        response_text = _f1_strip_json_blob(routing_response_text)

        decision = json.loads(response_text)
        tool_name = decision.get("tool")
        year = decision.get("year", 2024)
        race = decision.get("race")
        driver_code = decision.get("driver_code")
        driver_code1 = decision.get("driver_code1")
        driver_code2 = decision.get("driver_code2")

        _f1_trace(
            log,
            f"Routing decision: tool={tool_name!r} year={year} race={race!r} "
            f"driver_code={driver_code!r} driver_code1={driver_code1!r} driver_code2={driver_code2!r}",
        )

        # Call the appropriate tool
        if tool_name == "get_f1_schedule":
            _f1_trace(log, f"Tool call: get_f1_schedule({year})")
            result = get_f1_schedule(year)
            if "schedule" in result:
                html = f"<h2>F1 Schedule {year}</h2><ul>"
                for r in result["schedule"][:10]:
                    html += f"<li><strong>Round {r.get('RoundNumber')}:</strong> {r.get('EventName')} - {r.get('Location')}, {r.get('Country')} ({r.get('EventDate')})</li>"
                html += "</ul>"
                _f1_trace(log, f"get_f1_schedule OK ({len(result['schedule'])} events)")
                return html
            else:
                _f1_trace(log, f"get_f1_schedule error: {result.get('error', 'Unknown error')}")
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "get_f1_results":
            if not race:
                _f1_trace(log, "(validation) get_f1_results missing race")
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            _f1_trace(log, f"Tool call: get_f1_results({year!r}, {race!r})")
            result = get_f1_results(year, race)
            if "results" in result:
                race_name = result.get("race", race)
                summary_html = render_results_summary(query, year, race_name, result["results"])
                table_html = render_results_table(year, race_name, result["results"])
                html = summary_html + table_html
                _f1_trace(log, f"get_f1_results OK ({len(result['results'])} rows)")
                return html
            else:
                _f1_trace(log, f"get_f1_results error: {result.get('error', 'Unknown error')}")
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "get_driver_lap_times":
            if not race:
                _f1_trace(log, "(validation) get_driver_lap_times missing race")
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code:
                _f1_trace(log, "(validation) get_driver_lap_times missing driver_code")
                return "<p>Error: Driver code required. Please specify which driver (e.g., VER, NOR, HAM).</p>"
            _f1_trace(log, f"Tool call: get_driver_lap_times({year!r}, {race!r}, {driver_code.upper()!r})")
            result = get_driver_lap_times(year, race, driver_code.upper())
            if "lap_data" in result:
                table_html = render_lap_times_table(result["lap_data"], include_seconds=True)
                _f1_trace(log, f"get_driver_lap_times OK ({len(result['lap_data'])} laps)")
                return table_html
            else:
                _f1_trace(log, f"get_driver_lap_times error: {result.get('error', 'Unknown error')}")
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "plot_driver_lap_times":
            if not race:
                _f1_trace(log, "(validation) plot_driver_lap_times missing race")
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code:
                _f1_trace(log, "(validation) plot_driver_lap_times missing driver_code")
                return "<p>Error: Driver code required. Please specify which driver (e.g., VER, NOR, HAM).</p>"
            _f1_trace(log, f"Tool call: plot_driver_lap_times({year!r}, {race!r}, {driver_code.upper()!r})")
            result = plot_driver_lap_times(year, race, driver_code.upper())
            if "plot_html" in result:
                # Return HTML with plot and table
                plot_html = result["plot_html"]
                
                # Create table HTML from lap data
                if "lap_data" in result and result["lap_data"]:
                    table_html = render_lap_times_table(result["lap_data"], include_seconds=False)
                    _f1_trace(log, "plot_driver_lap_times OK (plot + table)")
                    return plot_html + table_html
                else:
                    _f1_trace(log, "plot_driver_lap_times OK (plot only)")
                    return plot_html
            else:
                _f1_trace(log, f"plot_driver_lap_times error: {result.get('error', 'Unknown error')}")
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "compare_driver_lap_times":
            if not race:
                _f1_trace(log, "(validation) compare_driver_lap_times missing race")
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code1 or not driver_code2:
                _f1_trace(log, "(validation) compare_driver_lap_times missing driver pair")
                return "<p>Error: Two driver codes required. Please specify both drivers (e.g., HAM and VER).</p>"

            # Get comparison data and plot
            _f1_trace(
                log,
                f"Tool call: compare_driver_lap_times({year!r}, {race!r}, "
                f"{driver_code1.upper()!r}, {driver_code2.upper()!r})",
            )
            result = compare_driver_lap_times(year, race, driver_code1.upper(), driver_code2.upper())
            
            if "error" in result:
                _f1_trace(log, f"compare_driver_lap_times error: {result.get('error', 'Unknown error')}")
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"

            if "plot_html" not in result:
                _f1_trace(log, "compare_driver_lap_times: missing plot_html")
                return f"<p>Error: Failed to generate comparison plot.</p>"
            
            plot_html = result["plot_html"]
            comparison_summary = result.get("comparison_summary", {})
            analysis_prompt = build_comparison_analysis_prompt(
                year,
                race,
                driver_code1.upper(),
                driver_code2.upper(),
                comparison_summary,
                query,
            )
            
            # Get LLM analysis
            try:
                analysis_text = _f1_generate_llm_text(
                    use_local=use_local,
                    client=client,
                    prompt=analysis_prompt,
                    log=log,
                    purpose="comparison analysis",
                    context_label="F1 MCP Analysis",
                    json_only=False,
                )

                analysis_section = render_comparison_analysis_section(analysis_text)
                _f1_trace(log, f"Analysis LLM OK ({len(analysis_text)} chars)")
            except Exception as e:
                analysis_section = f"<div class='mt-8'><p class='text-red-400'>Error generating analysis: {str(e)}</p></div>"
                _f1_trace(log, f"Analysis LLM failed: {e}")

            # Combine plot and analysis
            _f1_trace(log, "compare_driver_lap_times flow complete")
            return plot_html + analysis_section
        else:
            _f1_trace(log, f"Unknown tool name from model: {tool_name!r}")
            return f"<p>Error: Unknown tool '{tool_name}'</p>"
    except json.JSONDecodeError as e:
        _f1_trace(log, f"JSON parse error: {e}")
        preview = html_lib.escape((routing_response_text or "")[:500])
        return f"<p>Error parsing LLM routing response: {str(e)}<br><pre>{preview}</pre></p>"
    except Exception as e:
        import traceback
        _f1_trace(log, f"Unhandled exception: {e}\n{traceback.format_exc()}")
        return f"<p>Error: {str(e)}<br><pre>{traceback.format_exc()}</pre></p>"


@rt
def f1_mcp_res(query: str, use_local_gemma: str = ""):
    use_local = str(use_local_gemma or "").strip().lower() in ("1", "on", "true", "yes")
    log_buf: list[str] = []
    token = f1_mcp_log_ctx.set(log_buf)
    try:
        return _f1_response_with_logs(_f1_mcp_res_run(query, log_buf, use_local=use_local), log_buf)
    finally:
        f1_mcp_log_ctx.reset(token)

@rt('/')
def get(): 
    return layout(Form(
        H1('Welcome to the playground!', cls='text-3xl'), 
        Input(type='text', id='nm', placeholder='Enter your name'),
        Button('Click me', hx_post="/btn_res", hx_target='#dest'),
        P(id='dest', cls='mt-4')
    ))

@rt('/blog')
def get():
    return layout(Div(
        H1('Welcome to the blog!', cls='text-3xl'), 
    ))

@rt('/chatbot')
def get():
    return layout(Div(
        H1('Welcome to the chatbot!', cls='text-3xl'), 
        Form(
            Input(type='text', id='message', placeholder='Ask you question to the chatbot'),
            Button('Send', hx_post="/chatbot_res", hx_target='#dest'),
            Div(id='dest', cls='mt-4 prose prose-invert max-w-none')
        ),
        cls='flex flex-col gap-2 p-4'
    ))

@rt('/f1_mcp')
def get():
    categories = sorted(example_prompts.keys())
    prompts_json = json.dumps(example_prompts)
    return layout(Div(
        H1('Welcome to the F1 MCP section!', cls='text-3xl'), 
        Form(
            Input(
                type='text',
                id='query',
                name='query',
                placeholder='Ask any F1 question...',
                cls='input input-bordered w-full'
            ),
            Div(
                H3('Need ideas?', cls='text-sm font-medium'),
                P(
                    'Pick a category and we will prefill a sample question.',
                    cls='text-xs opacity-70'
                ),
                Div(
                    Div(
                        Label('Category', fr='prompt_category', cls='text-xs uppercase tracking-wide opacity-70'),
                        Select(
                            Option('Choose a category', value=''),
                            *[Option(category, value=category) for category in categories],
                            id='prompt_category',
                            cls='select select-bordered w-full text-base leading-normal min-h-12'
                        ),
                        cls='flex flex-col gap-1'
                    ),
                    Div(
                        Label('Example prompt', fr='example_prompt', cls='text-xs uppercase tracking-wide opacity-70'),
                        Select(
                            Option('Select a category first', value=''),
                            id='example_prompt',
                            cls='select select-bordered w-full text-base leading-normal min-h-12',
                            disabled=True
                        ),
                        cls='flex flex-col gap-1'
                    ),
                    cls='grid gap-3 md:grid-cols-2'
                ),
                cls='rounded-xl border border-base-300 bg-base-200/40 p-4 flex flex-col gap-3'
            ),
            Div(
                Label(
                    Input(
                        type='checkbox',
                        name='use_local_gemma',
                        value='1',
                        cls='checkbox checkbox-primary',
                    ),
                    Span('Use local Gemma (Ollama) instead of Gemini', cls='text-sm'),
                    cls='label cursor-pointer flex flex-row items-center gap-2 justify-start w-fit',
                ),
                P(
                    'Ollama defaults: F1_OLLAMA_URL=http://127.0.0.1:11434, F1_LOCAL_GEMMA_MODEL=gemma3:4b-it-qat',
                    cls='text-xs opacity-60 max-w-2xl',
                ),
                cls='flex flex-col gap-1',
            ),
            Div(
                Button(
                    'Send',
                    cls='btn-primary w-fit',
                    hx_post="/f1_mcp_res",
                    hx_target='#dest',
                    hx_indicator='#loading-f1'
                ),
                Span('⏳', id='loading-f1', cls='hourglass-loader htmx-indicator text-xl'),
                cls='flex items-center gap-2'
            ),
            Div(id='dest', cls='mt-4 prose prose-invert max-w-none'),
            Script(f"""
                (() => {{
                    const promptMap = {prompts_json};
                    const categorySelect = document.getElementById('prompt_category');
                    const promptSelect = document.getElementById('example_prompt');
                    const queryInput = document.getElementById('query');
                    if (!categorySelect || !promptSelect || !queryInput) return;

                    function resetPrompts(placeholderText) {{
                        promptSelect.innerHTML = '';
                        const placeholder = document.createElement('option');
                        placeholder.value = '';
                        placeholder.textContent = placeholderText;
                        promptSelect.appendChild(placeholder);
                    }}

                    categorySelect.addEventListener('change', () => {{
                        const selectedCategory = categorySelect.value;
                        if (!selectedCategory || !promptMap[selectedCategory]) {{
                            promptSelect.disabled = true;
                            resetPrompts('Select a category first');
                            return;
                        }}

                        promptSelect.disabled = false;
                        resetPrompts('Choose an example prompt');
                        promptMap[selectedCategory].forEach((prompt) => {{
                            const option = document.createElement('option');
                            option.value = prompt;
                            option.textContent = prompt;
                            promptSelect.appendChild(option);
                        }});
                        if (promptMap[selectedCategory].length > 0) {{
                            promptSelect.selectedIndex = 1;
                            queryInput.value = promptMap[selectedCategory][0];
                        }}
                    }});

                    promptSelect.addEventListener('change', () => {{
                        const selectedPrompt = promptSelect.value;
                        if (!selectedPrompt) return;
                        queryInput.value = selectedPrompt;
                        queryInput.focus();
                        queryInput.setSelectionRange(queryInput.value.length, queryInput.value.length);
                    }});
                }})();
            """)
        , cls='flex flex-col gap-4 mt-4'),
        cls='flex flex-col gap-2 p-4'
    ))

@rt('/health')
def get():
    """Health check endpoint for Cloud Run"""
    return {"status": "ok", "service": "fasthtml-app"}

@rt('/about')
def get():
    return layout(Div(
        H1('Under Construction', cls='text-3xl'), 
    ))

@rt('/info')
def get():
    return layout(Div(
        H1('Under Construction', cls='text-3xl'), 
    ))

@rt('/blog/info')
def get():
    return layout(Div(
        H1('Under Construction', cls='text-3xl'), 
    ))

@rt('/chatbot/info')
def get():
    return layout(Div(
        H1('Under Construction', cls='text-3xl'), 
    ))

@rt('/f1_mcp/info')
def get():
    return layout(Div(
        H1('F1 MCP Info', cls='text-3xl'), 
        P('This is a page where I worked on implementing an MCP server that can answer F1 related questions.'),
    ))


# Only run serve() when running locally (not in Cloud Run)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    serve(port=port, host="0.0.0.0")
