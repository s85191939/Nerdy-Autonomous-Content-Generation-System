"""Tests for ad_engine.utils (retries, failure recovery)."""

import pytest
from ad_engine.utils import with_retry


def test_with_retry_succeeds_first_try():
    calls = [0]
    def fn():
        calls[0] += 1
        return 42
    assert with_retry(fn) == 42
    assert calls[0] == 1


def test_with_retry_succeeds_second_try():
    calls = [0]
    def fn():
        calls[0] += 1
        if calls[0] < 2:
            raise ConnectionError("transient")
        return 43
    assert with_retry(fn, max_retries=2) == 43
    assert calls[0] == 2


def test_with_retry_raises_after_exhausted():
    calls = [0]
    def fn():
        calls[0] += 1
        raise RuntimeError("fail")
    with pytest.raises(RuntimeError):
        with_retry(fn, max_retries=2)
    assert calls[0] == 3
