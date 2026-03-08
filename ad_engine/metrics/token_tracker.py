"""Token usage and cost tracking for ROI metrics."""

from typing import Any, Dict, Optional

# Rough $ per 1M tokens (input, output) for estimation. Update as needed.
PRICING_PER_1M = {
    "gemini": (0.075, 0.30),
    "openrouter": (0.0, 0.0),  # free tier
    "openai": (0.15, 0.60),     # gpt-4o-mini approx
}


class TokenTracker:
    """Accumulate input/output tokens and compute estimated cost and ROI-style metrics."""

    def __init__(self, backend: str = "gemini"):
        self.backend = backend
        self.input_tokens = 0
        self.output_tokens = 0
        self._by_call: list[dict] = []

    def add(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self._by_call.append({"input": input_tokens, "output": output_tokens})

    def add_from_usage(self, usage: Optional[Dict[str, int]]) -> None:
        if not usage:
            return
        inp = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
        out = usage.get("output_tokens") or usage.get("candidates_token_count") or usage.get("completion_tokens", 0)
        self.add(inp, out)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimated_cost_usd(self) -> float:
        """Estimated cost in USD from list pricing."""
        prices = PRICING_PER_1M.get(self.backend, (0.10, 0.40))
        in_cost = (self.input_tokens / 1_000_000) * prices[0]
        out_cost = (self.output_tokens / 1_000_000) * prices[1]
        return round(in_cost + out_cost, 6)

    def roi_accepted_per_1k_tokens(self, accepted_count: int) -> float:
        """Accepted ads per 1K tokens (higher = better value)."""
        if self.total_tokens <= 0:
            return 0.0
        return round(accepted_count / (self.total_tokens / 1000), 4)

    def roi_score_per_dollar(self, avg_score: float) -> float:
        """Quality score per dollar spent (higher = better)."""
        cost = self.estimated_cost_usd()
        if cost <= 0:
            return avg_score * 1000  # avoid div by zero
        return round(avg_score / cost, 2)

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd(),
            "backend": self.backend,
        }


def usage_from_response(response: Any) -> Optional[Dict[str, int]]:
    """Extract {input_tokens, output_tokens} from Gemini or wrapper response."""
    # Our wrappers (OpenRouter, OpenAI, FallbackLLM)
    u = getattr(response, "usage", None)
    if isinstance(u, dict):
        return u
    # Gemini
    meta = getattr(response, "usage_metadata", None)
    if meta is not None:
        return {
            "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        }
    return None
