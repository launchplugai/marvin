import yaml
from pathlib import Path

DATA_PATH = Path(__file__).parent / "tests_data" / "golden_routing_cases.yaml"


REQUIRED_FIELDS = {
    "name",
    "input",
    "mode",
    "health",
    "expected_layer",
    "expected_intent",
    "reason",
}


LAYERS = {"keyword", "ollama", "openai", "fallback"}


INTENTS = {
    "status",
    "howto",
    "trivial",
    "unknown",
    "code_debug",
    "code_review",
    "feature_design",
    "architecture",
    "security",
}


def test_golden_cases_cover_layers_and_fields():
    cases = yaml.safe_load(DATA_PATH.read_text(encoding="utf-8"))

    seen_layers = set()
    for case in cases:
        assert REQUIRED_FIELDS.issubset(case.keys()), case["name"]
        assert case["expected_layer"] in LAYERS
        assert case["expected_intent"] in INTENTS
        health = case["health"]
        assert isinstance(health.get("ollama_ok"), bool)
        assert isinstance(health.get("openai_ok"), bool)
        seen_layers.add(case["expected_layer"])

    assert LAYERS.issubset(seen_layers), "Golden cases must cover every layer"
