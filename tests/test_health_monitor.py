from lobby.health import HealthMonitor


def test_health_monitor_cache(monkeypatch):
    calls = {"ollama": 0, "openai": 0}

    def fake_requests_get(url, timeout):  # noqa: D401
        calls["ollama"] += 1
        class Resp:
            def raise_for_status(self):
                return None
        return Resp()

    monkeypatch.setattr("requests.get", fake_requests_get)

    def fake_openai_probe():
        calls["openai"] += 1
        return True

    monitor = HealthMonitor("http://ollama:11434", fake_openai_probe, cache_ttl=60)

    snap1 = monitor.get_snapshot()
    snap2 = monitor.get_snapshot()

    assert snap1 is snap2
    assert calls["ollama"] == 1
    assert calls["openai"] == 1
