import time

from lobby.circuit_breaker import CircuitBreakerStore


def test_breaker_trips_after_threshold(monkeypatch):
    store = CircuitBreakerStore()

    store.record_failure("ollama", ttl_sec=1, max_failures=2, error="boom")
    assert store.can_attempt("ollama")

    store.record_failure("ollama", ttl_sec=1, max_failures=2, error="boom")
    assert not store.can_attempt("ollama")

    # advance time
    future = time.time() + 2
    monkeypatch.setattr("time.time", lambda: future)
    assert store.can_attempt("ollama")
