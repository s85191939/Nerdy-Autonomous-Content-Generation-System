"""Race multiple LLM backends in parallel — use whichever responds first."""

import logging
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class _ResponseWithText:
    """Minimal response object with .text and .usage."""

    def __init__(self, text: str, usage: Optional[dict] = None):
        self.text = text
        self.usage = usage or {}


class RacingLLM:
    """
    Sends the same request to multiple backends concurrently.
    Returns the first successful response, cancels the rest.
    Much faster than sequential fallback when multiple keys are configured.
    """

    def __init__(self, backends: List[Any], backend_names: Optional[List[str]] = None):
        self._backends = backends
        self._names = backend_names or [f"backend_{i}" for i in range(len(backends))]

    def generate_content(
        self,
        contents: List[Any],
        generation_config: Optional[Any] = None,
    ) -> _ResponseWithText:
        if len(self._backends) == 1:
            out = self._backends[0].generate_content(contents, generation_config)
            text = out.text if hasattr(out, "text") else str(out)
            usage = getattr(out, "usage", None) if hasattr(out, "usage") else None
            return _ResponseWithText(text=text, usage=usage)

        # Race all backends in parallel
        def _call_backend(idx):
            backend = self._backends[idx]
            out = backend.generate_content(contents, generation_config)
            text = out.text if hasattr(out, "text") else str(out)
            usage = getattr(out, "usage", None) if hasattr(out, "usage") else None
            return idx, text, usage

        with ThreadPoolExecutor(max_workers=len(self._backends)) as executor:
            futures = {executor.submit(_call_backend, i): i for i in range(len(self._backends))}
            done, not_done = wait(futures, return_when=FIRST_COMPLETED)

            # Get first successful result
            last_exc = None
            for future in done:
                try:
                    idx, text, usage = future.result()
                    logger.debug("Race won by %s", self._names[idx])
                    # Cancel remaining futures
                    for f in not_done:
                        f.cancel()
                    return _ResponseWithText(text=text, usage=usage)
                except Exception as e:
                    last_exc = e
                    continue

            # If first batch all failed, wait for remaining
            if not_done:
                done2, _ = wait(not_done)
                for future in done2:
                    try:
                        idx, text, usage = future.result()
                        logger.debug("Race won (late) by %s", self._names[idx])
                        return _ResponseWithText(text=text, usage=usage)
                    except Exception as e:
                        last_exc = e
                        continue

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No backends configured")
