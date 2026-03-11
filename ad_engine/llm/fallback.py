"""Fallback LLM: try backends in order (e.g. Gemini -> OpenRouter -> OpenAI) until one succeeds."""

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class _ResponseWithText:
    """Minimal response object with .text and .usage for compatibility."""

    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage = usage or {}


def _extract_usage(response: Any) -> Optional[dict]:
    """Extract usage dict from any backend response (Gemini, OpenRouter, OpenAI)."""
    # Our wrappers store usage as a dict
    u = getattr(response, "usage", None)
    if isinstance(u, dict) and u:
        return u
    # Gemini stores it as usage_metadata object
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        return {
            "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        }
    return None


class FallbackLLM:
    """
    Wraps multiple LLM backends. Each must implement:
      generate_content(contents: List, generation_config=None) -> object with .text
    Tries them in order; on exception (quota, auth, network) tries the next.
    """

    def __init__(self, backends: List[Any], backend_names: Optional[List[str]] = None):
        self._backends = backends
        self._names = backend_names or [f"backend_{i}" for i in range(len(backends))]

    def generate_content(
        self,
        contents: List[Any],
        generation_config: Optional[Any] = None,
    ) -> _ResponseWithText:
        last_exc = None
        for i, backend in enumerate(self._backends):
            try:
                out = backend.generate_content(contents, generation_config)
                text = out.text if hasattr(out, "text") else str(out)
                if not text or not text.strip():
                    logger.warning("Backend %s returned empty response, trying next", self._names[i])
                    continue
                usage = _extract_usage(out)
                return _ResponseWithText(text=text, usage=usage)
            except Exception as e:
                logger.warning("Backend %s failed: %s", self._names[i], e)
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No backends configured")
