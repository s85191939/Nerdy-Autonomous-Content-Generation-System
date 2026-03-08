"""Fallback LLM: try backends in order (e.g. Gemini -> OpenRouter -> OpenAI) until one succeeds."""

from typing import Any, List, Optional


class _ResponseWithText:
    """Minimal response object with .text and .usage for compatibility."""

    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage = usage or {}


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
                usage = getattr(out, "usage", None) if hasattr(out, "usage") else None
                return _ResponseWithText(text=text, usage=usage)
            except Exception as e:
                last_exc = e
                # Try next backend (same interface may be used by caller's retry, so we continue)
                continue
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No backends configured")
