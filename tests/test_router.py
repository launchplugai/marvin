from dataclasses import replace

import yaml

from lobby.circuit_breaker import CircuitBreakerStore
from lobby.config import LobbyConfig, load_config
from lobby.health import HealthSnapshot
from lobby.keywords import KeywordRegistry
from lobby.router import LobbyRouter, RequestEnvelope

DATA_PATH = "tests/tests_data/golden_routing_cases.yaml"


def build_router(mode: str) -> LobbyRouter:
    cfg = load_config("config/lobby.defaults.yml")
    cfg = replace(cfg, lobby_mode=mode)
    registry = KeywordRegistry(cfg.keyword_commands_path)
    breakers = CircuitBreakerStore()
    return LobbyRouter(cfg, registry, breakers)


def make_snapshot(ollama_ok: bool, openai_ok: bool) -> HealthSnapshot:
    return HealthSnapshot(
        checked_at=0.0,
        ollama_ok=ollama_ok,
        openai_ok=openai_ok,
    )


def test_router_against_golden_cases():
    cases = yaml.safe_load(open(DATA_PATH, encoding="utf-8"))
    for case in cases:
        router = build_router(case["mode"])
        snapshot = make_snapshot(
            case["health"]["ollama_ok"], case["health"]["openai_ok"]
        )
        envelope = RequestEnvelope(
            request_id=f"test-{case['name']}",
            user_id="anon",
            text=case["input"],
        )
        decision = router.route(envelope, snapshot)
        assert (
            decision.record.layer == case["expected_layer"]
        ), f"layer mismatch for {case['name']}"
        assert (
            decision.record.intent == case["expected_intent"]
        ), f"intent mismatch for {case['name']}"
        assert decision.record.reason, "reason should be populated"
