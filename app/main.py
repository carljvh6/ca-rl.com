import os
from fasthtml.common import *
import fasthtml.components as fc
from google import genai
from dotenv import load_dotenv
from google.cloud import secretmanager

daisy_headers = (
    Link(href='https://cdn.jsdelivr.net/npm/daisyui@5', rel='stylesheet', type='text/css'),
    Script(src='https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4'),
    Script("document.documentElement.setAttribute('data-theme', 'dark');")
)

def Button(*c, cls='', **kw):
    return fc.Button(*c, cls=f"btn {cls}", **kw)

def get_api_key():
    """
    Get Google API key from Secret Manager (Cloud Run) or environment/.env (local).
    Priority: Environment Variable > Secret Manager > .env file
    
    For Cloud Run: Set GOOGLE_CLOUD_PROJECT env var and create secret named 'GOOGLE_API_KEY' in Secret Manager
    For local: Use .env file with GOOGLE_API_KEY=your_key
    """
    # First, try environment variable (works in both local and Cloud Run)
    # This allows overriding Secret Manager if needed
    api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GEMINI_API_KEY')
    if api_key:
        return api_key
    
    # Check if we're running in Cloud Run (K_SERVICE is set by Cloud Run)
    is_cloud_run = os.getenv('K_SERVICE') is not None
    
    if is_cloud_run:
        # Try Secret Manager
        try:
            # Cloud Run sets GOOGLE_CLOUD_PROJECT automatically
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
            
            if project_id:
                secret_name = "GOOGLE_API_KEY"  # Secret name in Secret Manager
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                api_key = response.payload.data.decode("UTF-8")
                if api_key:
                    return api_key
            else:
                print("Warning: GOOGLE_CLOUD_PROJECT not set, skipping Secret Manager")
        except Exception as e:
            # If Secret Manager fails, log but continue to try .env
            print(f"Warning: Could not fetch from Secret Manager: {e}")
    
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
        api_key = get_api_key()
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=message
        )

        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

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
        H1('Welcom to the blog!', cls='text-3xl'), 
    ))

@rt('/chatbot')
def get():
    return layout(Div(
        H1('Welcome to the chatbot!', cls='text-3xl'), 
        Form(
            Input(type='text', id='message', placeholder='Ask you question to the chatbot'),
            Button('Send', hx_post="/chatbot_res", hx_target='#dest'),
            P(id='dest', cls='mt-4')
        ),
        cls='flex flex-col gap-2 p-4'
    ))

@rt('/about')
def get():
    return layout(Div(
        H1('Welcome to the about section!', cls='text-3xl'), 
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
