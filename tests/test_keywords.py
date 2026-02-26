from pathlib import Path

from lobby.keywords import KeywordRegistry


def test_exact_match_only(tmp_path):
    sample = tmp_path / "keywords.json"
    sample.write_text(
        """
        [
          {"command": "status", "response": "ok", "allows_args": false, "version": 1}
        ]
        """,
        encoding="utf-8",
    )

    registry = KeywordRegistry(sample)

    assert registry.match("status").response == "ok"
    assert registry.match("Status") is None
    assert registry.match("status please") is None
