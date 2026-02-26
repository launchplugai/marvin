from lobby.observability import DecisionLogRecord


def test_decision_log_schema_roundtrip():
    record = DecisionLogRecord(
        request_id="req-1",
        user_id="anon",
        layer="keyword",
        intent="status",
        confidence=0.99,
        reason="keyword hit",
        keyword_hit="status",
        ollama_ok=True,
        openai_ok=True,
        latency_ms_total=12.3,
        estimated_cost_usd=0.0,
    )

    payload = record.to_dict()

    assert payload["layer"] == "keyword"
    assert payload["keyword_hit"] == "status"
