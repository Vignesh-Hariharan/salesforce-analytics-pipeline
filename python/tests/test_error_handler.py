import pytest

from utils.error_handler import retry_on_failure


def test_retry_succeeds_on_first_attempt():
    calls = {'n': 0}

    @retry_on_failure(max_attempts=3, delay=0)
    def ok():
        calls['n'] += 1
        return 'fine'

    assert ok() == 'fine'
    assert calls['n'] == 1


def test_retry_succeeds_after_transient_failure():
    calls = {'n': 0}

    @retry_on_failure(max_attempts=3, delay=0, exceptions=(RuntimeError,))
    def flaky():
        calls['n'] += 1
        if calls['n'] < 3:
            raise RuntimeError("transient")
        return 'eventually'

    assert flaky() == 'eventually'
    assert calls['n'] == 3


def test_retry_propagates_after_exhaustion():
    calls = {'n': 0}

    @retry_on_failure(max_attempts=2, delay=0, exceptions=(RuntimeError,))
    def always_fails():
        calls['n'] += 1
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        always_fails()
    assert calls['n'] == 2


def test_retry_does_not_swallow_unhandled_exceptions():
    @retry_on_failure(max_attempts=3, delay=0, exceptions=(KeyError,))
    def wrong_kind():
        raise ValueError("not retriable")

    with pytest.raises(ValueError):
        wrong_kind()
