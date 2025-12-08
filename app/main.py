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
import sys
import os
from datetime import datetime
from collections import deque

# Add app directory to path for imports
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from f1_mcp_server import get_f1_results, get_f1_schedule, get_driver_lap_times, plot_driver_lap_times, compare_driver_lap_times

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

@rt
def f1_mcp_res(query: str):
    """Process F1 queries using MCP tools with Gemini for natural language understanding"""
    try:
        if not query or not query.strip():
            return "<p>Please enter a question.</p>"
        
        api_key = get_api_key(use_secret_manager=True)
        if not api_key:
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
        
        log_api_call("F1 MCP", "gemini-2.0-flash-lite", prompt)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt
        )
        
        # Parse Gemini's response
        response_text = response.text.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        decision = json.loads(response_text)
        tool_name = decision.get("tool")
        year = decision.get("year", 2024)
        race = decision.get("race")
        driver_code = decision.get("driver_code")
        driver_code1 = decision.get("driver_code1")
        driver_code2 = decision.get("driver_code2")
        
        # Call the appropriate tool
        if tool_name == "get_f1_schedule":
            result = get_f1_schedule(year)
            if "schedule" in result:
                html = f"<h2>F1 Schedule {year}</h2><ul>"
                for r in result["schedule"][:10]:
                    html += f"<li><strong>Round {r.get('RoundNumber')}:</strong> {r.get('EventName')} - {r.get('Location')}, {r.get('Country')} ({r.get('EventDate')})</li>"
                html += "</ul>"
                return html
            else:
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "get_f1_results":
            if not race:
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            result = get_f1_results(year, race)
            if "results" in result:
                html = f"<h2>{result.get('race')} {year} Results</h2><table class='table'><thead><tr><th>Pos</th><th>Driver</th><th>Team</th></tr></thead><tbody>"
                for r in result["results"][:10]:
                    html += f"<tr><td>{int(r.get('Position', 0))}</td><td>{r.get('BroadcastName')}</td><td>{r.get('TeamName')}</td></tr>"
                html += "</tbody></table>"
                return html
            else:
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "get_driver_lap_times":
            if not race:
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code:
                return "<p>Error: Driver code required. Please specify which driver (e.g., VER, NOR, HAM).</p>"
            result = get_driver_lap_times(year, race, driver_code.upper())
            if "lap_data" in result:
                # Create table HTML from lap data
                table_html = "<div class='mt-4'><h3 class='text-2xl mb-4'>Lap Times</h3><table class='table table-zebra w-full'><thead><tr><th>Lap</th><th>Lap Time</th><th>Lap Time (s)</th><th>Compound</th></tr></thead><tbody>"
                for lap in result["lap_data"]:
                    lap_num = lap.get('LapNumber', '')
                    lap_time = lap.get('LapTime', '')
                    lap_time_seconds = lap.get('LapTimeSeconds', '')
                    compound = lap.get('Compound', '')
                    table_html += f"<tr><td>{lap_num}</td><td>{lap_time}</td><td>{lap_time_seconds:.3f}</td><td>{compound}</td></tr>"
                table_html += "</tbody></table></div>"
                return table_html
            else:
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "plot_driver_lap_times":
            if not race:
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code:
                return "<p>Error: Driver code required. Please specify which driver (e.g., VER, NOR, HAM).</p>"
            result = plot_driver_lap_times(year, race, driver_code.upper())
            if "plot_html" in result:
                # Return HTML with plot and table
                plot_html = result["plot_html"]
                
                # Create table HTML from lap data
                if "lap_data" in result and result["lap_data"]:
                    table_html = "<div class='mt-8'><h3 class='text-2xl mb-4'>Lap Times</h3><table class='table table-zebra w-full'><thead><tr><th>Lap</th><th>Lap Time</th><th>Compound</th></tr></thead><tbody>"
                    for lap in result["lap_data"]:
                        lap_num = lap.get('LapNumber', '')
                        lap_time = lap.get('LapTime', '')
                        compound = lap.get('Compound', '')
                        table_html += f"<tr><td>{lap_num}</td><td>{lap_time}</td><td>{compound}</td></tr>"
                    table_html += "</tbody></table></div>"
                    return plot_html + table_html
                else:
                    return plot_html
            else:
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
        elif tool_name == "compare_driver_lap_times":
            if not race:
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code1 or not driver_code2:
                return "<p>Error: Two driver codes required. Please specify both drivers (e.g., HAM and VER).</p>"
            
            # Get comparison data and plot
            result = compare_driver_lap_times(year, race, driver_code1.upper(), driver_code2.upper())
            
            if "error" in result:
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
            
            if "plot_html" not in result:
                return f"<p>Error: Failed to generate comparison plot.</p>"
            
            plot_html = result["plot_html"]
            driver1_data = result.get("driver1_lap_data", [])
            driver2_data = result.get("driver2_lap_data", [])
            
            # Prepare data summary for LLM analysis
            # Calculate statistics for analysis
            driver1_times = [lap["LapTimeSeconds"] for lap in driver1_data]
            driver2_times = [lap["LapTimeSeconds"] for lap in driver2_data]
            
            driver1_avg = sum(driver1_times) / len(driver1_times) if driver1_times else 0
            driver2_avg = sum(driver2_times) / len(driver2_times) if driver2_times else 0
            driver1_min = min(driver1_times) if driver1_times else 0
            driver2_min = min(driver2_times) if driver2_times else 0
            driver1_max = max(driver1_times) if driver1_times else 0
            driver2_max = max(driver2_times) if driver2_times else 0
            
            # Find slower laps (where one driver was significantly slower)
            slower_laps_info = []
            for i, lap1 in enumerate(driver1_data):
                lap_num = lap1["LapNumber"]
                time1 = lap1["LapTimeSeconds"]
                # Find corresponding lap for driver 2
                lap2_match = next((lap for lap in driver2_data if lap["LapNumber"] == lap_num), None)
                if lap2_match:
                    time2 = lap2_match["LapTimeSeconds"]
                    diff = abs(time1 - time2)
                    if diff > 0.5:  # Significant difference (>0.5 seconds)
                        slower_driver = driver_code1 if time1 > time2 else driver_code2
                        slower_laps_info.append({
                            "lap": lap_num,
                            f"{driver_code1}_time": time1,
                            f"{driver_code2}_time": time2,
                            "difference": diff,
                            "slower_driver": slower_driver
                        })
            
            # Extract pit stop information for both drivers
            def extract_pit_stops(lap_data, driver_code):
                pit_stops = []
                for lap in lap_data:
                    pit_in = lap.get("PitInTime", "")
                    pit_out = lap.get("PitOutTime", "")
                    # Check if pit stop occurred (not NaT or empty)
                    if pit_in and pit_in != "NaT" and pit_in != "nat" and str(pit_in) != "nan":
                        pit_stops.append({
                            "lap": lap.get("LapNumber"),
                            "pit_in": pit_in,
                            "pit_out": pit_out if pit_out and pit_out != "NaT" and pit_out != "nat" and str(pit_out) != "nan" else None
                        })
                    elif pit_out and pit_out != "NaT" and pit_out != "nat" and str(pit_out) != "nan":
                        # Sometimes only pit out is recorded
                        pit_stops.append({
                            "lap": lap.get("LapNumber"),
                            "pit_in": None,
                            "pit_out": pit_out
                        })
                return pit_stops
            
            driver1_pit_stops = extract_pit_stops(driver1_data, driver_code1)
            driver2_pit_stops = extract_pit_stops(driver2_data, driver_code2)
            
            # Create analysis prompt for LLM
            analysis_prompt = f"""Analyze the lap time comparison between {driver_code1} and {driver_code2} in the {race} {year} race.

                Statistics:
                - {driver_code1}: Average {driver1_avg:.3f}s, Fastest {driver1_min:.3f}s, Slowest {driver1_max:.3f}s
                - {driver_code2}: Average {driver2_avg:.3f}s, Fastest {driver2_min:.3f}s, Slowest {driver2_max:.3f}s

                Pit Stops:
                - {driver_code1} pit stops: {json.dumps(driver1_pit_stops, indent=2) if driver1_pit_stops else "No pit stops recorded"}
                - {driver_code2} pit stops: {json.dumps(driver2_pit_stops, indent=2) if driver2_pit_stops else "No pit stops recorded"}

                Laps with significant differences (>0.5s):
                {json.dumps(slower_laps_info[:20], indent=2)}

                User query: {query}

                Provide a detailed analysis focusing on:
                1. Overall performance comparison
                2. When and why one driver had slower laps
                3. Pit stop strategies and their impact on lap times
                4. Patterns in the lap time differences, especially around pit stops
                5. Any notable events or strategies visible in the data

                Write in a clear, informative style suitable for F1 fans. Pay special attention to how pit stops affected lap times and race strategy."""
            
            log_api_call("F1 MCP Analysis", "gemini-2.5-flash-lite", analysis_prompt[:200])
            
            # Get LLM analysis
            try:
                analysis_response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=analysis_prompt
                )
                analysis_text = analysis_response.text
                
                # Convert markdown to HTML
                analysis_html = markdown.markdown(analysis_text, extensions=['nl2br', 'fenced_code'])
                analysis_section = f"<div class='mt-8 prose prose-invert max-w-none'><h3 class='text-2xl mb-4'>Analysis</h3>{analysis_html}</div>"
            except Exception as e:
                analysis_section = f"<div class='mt-8'><p class='text-red-400'>Error generating analysis: {str(e)}</p></div>"
            
            # Combine plot and analysis
            return plot_html + analysis_section
        else:
            return f"<p>Error: Unknown tool '{tool_name}'</p>"
    except json.JSONDecodeError as e:
        return f"<p>Error parsing Gemini response: {str(e)}<br>Response was: {response.text[:200]}</p>"
    except Exception as e:
        import traceback
        return f"<p>Error: {str(e)}<br><pre>{traceback.format_exc()}</pre></p>"

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
    return layout(Div(
        H1('Welcome to the F1 MCP section!', cls='text-3xl'), 
        Form(
            Input(type='text', id='query', name='query', placeholder='Ask a F1 related question'),
            Button('Send', hx_post="/f1_mcp_res", hx_target='#dest'),
            Div(id='dest', cls='mt-4 prose prose-invert max-w-none')
        ),
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
