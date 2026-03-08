"""OpenAI API client (chat completions). Used as fallback when Gemini/OpenRouter fail."""

import os
from typing import Any, List, Optional

OPENAI_DEFAULT_MODEL = "gpt-4o-mini"


class _OpenAIResponse:
    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage = usage or {}


class OpenAIModel:
    """OpenAI chat-completions client. Same interface as Gemini/OpenRouter for fallback chain."""

    def __init__(self, api_key: Optional[str] = None, model: str = OPENAI_DEFAULT_MODEL):
        self._api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI backend.")
        self._model = model

    def generate_content(
        self,
        contents: List[Any],
        generation_config: Optional[Any] = None,
    ) -> _OpenAIResponse:
        messages = []
        for i, part in enumerate(contents):
            text = part if isinstance(part, str) else getattr(part, "text", str(part))
            role = "system" if i == 0 and len(contents) > 1 else "user"
            messages.append({"role": role, "content": text})
        if not messages:
            raise ValueError("contents must not be empty")
        if messages[0]["role"] != "system" and len(messages) == 1:
            messages[0]["role"] = "user"

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Install openai: pip install openai")

        client = OpenAI(api_key=self._api_key)
        r = client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=2048,
        )
        content = ""
        if r.choices and len(r.choices) > 0:
            content = (r.choices[0].message.content or "") or ""
        usage = {}
        if getattr(r, "usage", None):
            usage = {
                "input_tokens": getattr(r.usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(r.usage, "completion_tokens", 0) or 0,
            }
        return _OpenAIResponse(text=content, usage=usage)
