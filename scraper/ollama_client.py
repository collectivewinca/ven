"""Tiny client for Ollama Cloud OpenAI-compatible chat completions.

Used by scraper scripts that previously called Gemini — swapped because the
Gemini key got exposed in git history and we wanted to retire that dependency.

Direct HTTP path (not via a local daemon). Works from any egress because
ollama.com's OpenAI-compat endpoint accepts Bearer auth without ASN tricks.
Reads OLLAMA_API_KEY from env.

Default model is minimax-m2.7 (non-reasoning, good for structured JSON and
short-form generation). Override per call with the `model` kwarg.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

OLLAMA_CHAT_URL = os.environ.get(
    "OLLAMA_CHAT_URL", "https://ollama.com/v1/chat/completions"
)
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()
DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "minimax-m2.7")
DEFAULT_TIMEOUT = 45


class OllamaError(RuntimeError):
    pass


def chat(
    prompt: str,
    system: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a single-turn prompt and return the assistant text content.

    Raises OllamaError for auth/network/API failures or empty replies so
    callers don't silently fall through on a broken key.
    """
    if not OLLAMA_API_KEY:
        raise OllamaError("OLLAMA_API_KEY not set in environment")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = requests.post(
        OLLAMA_CHAT_URL,
        headers={
            "Authorization": f"Bearer {OLLAMA_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise OllamaError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise OllamaError(f"unexpected response shape: {e}; raw={data}") from e

    content = (content or "").strip()
    if not content:
        raise OllamaError(
            f"empty content; usage={data.get('usage')} — check max_tokens "
            f"(reasoning models need ≥200 to clear thinking-token budget)"
        )
    return content
