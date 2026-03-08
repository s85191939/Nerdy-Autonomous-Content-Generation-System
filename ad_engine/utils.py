"""Shared utilities: retries, failure recovery."""

import time
from typing import Callable, TypeVar

T = TypeVar("T")

# Default: 3 attempts, exponential backoff 1s, 2s, 4s
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_BACKOFF_MULTIPLIER = 2.0


def with_retry(
    fn: Callable[[], T],
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
    retryable_exceptions: tuple = (Exception,),
) -> T:
    """
    Call fn(); on retryable exception, wait and retry up to max_retries.
    Raises the last exception if all retries fail.
    """
    last_exc = None
    delay = initial_backoff
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retryable_exceptions as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(delay)
                delay *= backoff_multiplier
    raise last_exc
