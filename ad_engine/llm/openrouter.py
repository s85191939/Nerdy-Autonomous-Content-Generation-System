"""OpenRouter API client (OpenAI-compatible). Uses free models when available."""

import os
from typing import Any, List, Optional

import requests

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class _OpenRouterResponse:
    """Mimics Gemini response with .text and .usage for drop-in use."""

    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage = usage or {}


class OpenRouterModel:
    """
    OpenRouter chat-completions client. Use openrouter/free for free-tier models,
    or a specific model id (e.g. meta-llama/llama-3.3-70b-instruct:free).
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "openrouter/free"):
        self._api_key = (api_key or os.environ.get("OPENROUTER_API_KEY") or "").strip()
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouter backend.")
        self._model = model

    def generate_content(
        self,
        contents: List[Any],
        generation_config: Optional[Any] = None,
    ) -> _OpenRouterResponse:
        """
        contents: list of strings, e.g. [system_prompt, user_prompt].
        generation_config: ignored (OpenRouter has its own params if needed).
        """
        messages = []
        for i, part in enumerate(contents):
            text = part if isinstance(part, str) else getattr(part, "text", str(part))
            role = "system" if i == 0 and len(contents) > 1 else "user"
            messages.append({"role": role, "content": text})
        if not messages:
            raise ValueError("contents must not be empty")
        if messages[0]["role"] != "system" and len(messages) == 1:
            messages[0]["role"] = "user"

        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": 2048,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_REFERRER", "https://github.com/s85191939/Nerdy-Autonomous-Content-Generation-System"),
        }
        r = requests.post(
            f"{OPENROUTER_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        usage_raw = data.get("usage") or {}
        usage = {}
        if usage_raw:
            usage = {
                "input_tokens": usage_raw.get("prompt_tokens", 0) or 0,
                "output_tokens": usage_raw.get("completion_tokens", 0) or 0,
            }
        return _OpenRouterResponse(text=content, usage=usage)
