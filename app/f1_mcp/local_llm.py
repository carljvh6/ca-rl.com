"""Local LLM (Ollama) for F1 MCP when Gemini API is not used."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3:4b-it-qat"


def get_local_llm_config() -> tuple[str, str]:
    base = os.environ.get("F1_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    model = os.environ.get("F1_LOCAL_GEMMA_MODEL", DEFAULT_MODEL)
    return base, model


def ollama_generate(
    prompt: str,
    *,
    system: str | None = None,
    timeout_s: int = 600,
) -> str:
    """Call Ollama /api/generate and return the model response text."""
    base, model = get_local_llm_config()
    url = f"{base}/api/generate"
    body: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if system:
        body["system"] = system
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {e.code}: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {url}. Start Ollama and ensure the model is "
            f"pulled (e.g. `ollama pull {model}`). Original error: {e}"
        ) from e
    return (data.get("response") or "").strip()
