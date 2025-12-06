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

# Add app directory to path for imports
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from f1_mcp_server import get_f1_results, get_f1_schedule, plot_driver_lap_times

daisy_headers = (
    Link(href='https://cdn.jsdelivr.net/npm/daisyui@5', rel='stylesheet', type='text/css'),
    Script(src='https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4'),
    Script("document.documentElement.setAttribute('data-theme', 'dark');")
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
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
                print(f"Attempting to fetch secret: {name}")
                response = client.access_secret_version(request={"name": name})
                api_key = response.payload.data.decode("UTF-8")
                if api_key:
                    print("Successfully retrieved API key from Secret Manager")
                    return api_key
            else:
                print(f"Warning: Project ID not found. Available env vars: K_SERVICE={os.getenv('K_SERVICE')}, GOOGLE_CLOUD_PROJECT={os.getenv('GOOGLE_CLOUD_PROJECT')}")
        except Exception as e:
            # If Secret Manager fails, log detailed error
            import traceback
            error_details = traceback.format_exc()
            print(f"Error fetching from Secret Manager: {str(e)}")
            print(f"Traceback: {error_details}")
    
    # Fall back to .env file for local development
    load_dotenv()
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if api_key:
        return api_key
    
    raise ValueError("GOOGLE_API_KEY not found in Secret Manager, environment variables, or .env file.")

def layout(content):
    sidebar = Div(
        Div(
            A('Home', href='/', cls='btn btn-ghost w-full justify-start'),
            A('Blog', href='/blog', cls='btn btn-ghost w-full justify-start'),
            A('Chatbot', href='/chatbot', cls='btn btn-ghost w-full justify-start'),
            A('F1 MCP', href='/f1_mcp', cls='btn btn-ghost w-full justify-start'),
            A('About', href='/about', cls='btn btn-ghost w-full justify-start'),
            A('Python Interpreter', href='/python_intepreter', cls='btn btn-ghost w-full justify-start'),
            cls='flex flex-col gap-2 p-4'
        ),
        cls='w-64 min-h-screen bg-base-100'
    )
    main_content = Div(content, cls='flex-1 p-8')
    return Div(sidebar, main_content, cls='flex')

app, rt = fast_app(title="carldotcom's playground", hdrs = daisy_headers
    )

@rt
def btn_res(nm:str): return f"Button Clicked, hello {nm}!"

@rt
def chatbot_res(message:str): 
    try:
        api_key = get_api_key(use_secret_manager=True)
        client = genai.Client(api_key=api_key)

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
        client = genai.Client(api_key=api_key)
        
        # Ask Gemini to determine which tool to use
        prompt = f"""Analyze this F1 query and determine which tool to use:
- get_f1_schedule(year) for schedule questions
- get_f1_results(year, race) for results questions
- plot_driver_lap_times(year, race, driver_code) for lap time plots

Query: {query}

Respond in JSON: {{"tool": "tool_name", "year": 2024, "race": "race_name", "driver_code": "VER"}}
Extract year (default 2024), race name, and driver code (3-letter code like VER, NOR, HAM) if needed.
For plot requests, look for driver names or codes in the query."""
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
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
        elif tool_name == "plot_driver_lap_times":
            if not race:
                return "<p>Error: Race name required. Please specify which race you're asking about.</p>"
            if not driver_code:
                return "<p>Error: Driver code required. Please specify which driver (e.g., VER, NOR, HAM).</p>"
            result = plot_driver_lap_times(year, race, driver_code.upper())
            if "plot_html" in result:
                # Return HTML directly - FastHTML will render it
                return result["plot_html"]
            else:
                return f"<p>Error: {result.get('error', 'Unknown error')}</p>"
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

@rt('/python_intepreter')
def get():
    return layout(Div(
        H1('Welcom to the python intepreter!', cls='text-3xl'), 
    ))

# Only run serve() when running locally (not in Cloud Run)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    serve(port=port, host="0.0.0.0")
