import os
from fasthtml.common import *
import fasthtml.components as fc

daisy_headers = (
    Link(href='https://cdn.jsdelivr.net/npm/daisyui@5', rel='stylesheet', type='text/css'),
    Script(src='https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4')
)

def Button(*c, cls='', **kw):
    return fc.Button(*c, cls=f"btn {cls}", **kw)

app, rt = fast_app(title="carldotcom's playground", hdrs = daisy_headers
    )

@rt
def btn_res(nm:str): return f"Button Clicked, hello {nm}!"

@rt('/')
def get(): 
    return Form(
        H1('Welcome to the playground!', cls='text-3xl'), 
        Input(type='text', id='nm', placeholder='Enter your name'),
        Button('Click me', hx_post="/btn_res", hx_target='#dest'),
        P(id='dest', cls='mt-4')
    )

@rt('/health')
def get():
    """Health check endpoint for Cloud Run"""
    return {"status": "ok", "service": "fasthtml-app"}

# Only run serve() when running locally (not in Cloud Run)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    serve(port=port, host="0.0.0.0")
