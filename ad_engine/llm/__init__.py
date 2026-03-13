"""LLM backends: race multiple backends in parallel for speed, fallback on error."""

import os
from typing import Any, List, Optional

from ad_engine.llm.fallback import FallbackLLM
from ad_engine.llm.openrouter import OpenRouterModel

# Default fast paid model on OpenRouter (Gemini 2.0 Flash — ~$0.10/1M input tokens, very fast)
DEFAULT_OPENROUTER_MODEL = "google/gemini-2.0-flash-001"


class _GeminiWithTimeout:
    """Wraps a Gemini GenerativeModel with a per-call timeout (default 30s)."""

    def __init__(self, model, timeout: int = 30):
        self._model = model
        self._timeout = timeout

    def generate_content(self, contents, generation_config=None):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(self._model.generate_content, contents, generation_config=generation_config)
            return future.result(timeout=self._timeout)


def _gemini_backend(api_key_override: Optional[str] = None):
    """Build Gemini GenerativeModel or None if no key."""
    key = api_key_override or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not (key or "").strip():
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        return None
    genai.configure(api_key=key.strip())
    model = genai.GenerativeModel("gemini-2.0-flash")
    return _GeminiWithTimeout(model, timeout=30)


def _openrouter_backend(
    openrouter_key_override: Optional[str] = None,
    model_override: Optional[str] = None,
):
    """Build OpenRouter model or None if no key."""
    key = (openrouter_key_override or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return None
    model = model_override or os.environ.get("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    return OpenRouterModel(api_key=key, model=model)


def _openai_backend(api_key_override: Optional[str] = None):
    """Build OpenAI model or None if no key or openai not installed."""
    key = (api_key_override or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from ad_engine.llm.openai_client import OpenAIModel
        return OpenAIModel(api_key=key)
    except ImportError:
        return None


def get_llm(
    api_key_override: Optional[str] = None,
    openrouter_key_override: Optional[str] = None,
    model_override: Optional[str] = None,
    openai_key_override: Optional[str] = None,
) -> Any:
    """
    Return an LLM with fallback chain: Gemini (first) -> OpenRouter -> OpenAI.
    Only backends with configured keys are included. At least one must be set.
    The returned object has .generate_content(contents, generation_config=None) -> response with .text.
    """
    backends: List[Any] = []
    names: List[str] = []

    gemini = _gemini_backend(api_key_override)
    if gemini is not None:
        backends.append(gemini)
        names.append("Gemini")

    openrouter = _openrouter_backend(openrouter_key_override, model_override)
    if openrouter is not None:
        backends.append(openrouter)
        names.append("OpenRouter")

    openai = _openai_backend(openai_key_override)
    if openai is not None:
        backends.append(openai)
        names.append("OpenAI")

    if not backends:
        raise ValueError(
            "Set at least one of: GEMINI_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY "
            "(or pass overrides to get_llm)."
        )

    if len(backends) == 1:
        return backends[0]
    # Gemini first, then fallback to OpenRouter/OpenAI on error
    return FallbackLLM(backends, backend_names=names)
