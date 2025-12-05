import os
from fasthtml.common import *

app, rt = fast_app()

@rt('/')
def get(): 
    return Div(P('Hello World!'), hx_get="/change")

@rt('/health')
def get():
    """Health check endpoint for Cloud Run"""
    return {"status": "ok", "service": "fasthtml-app"}

# Only run serve() when running locally (not in Cloud Run)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    serve(port=port, host="0.0.0.0")
