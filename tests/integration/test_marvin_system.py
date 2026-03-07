import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cache.cache import CacheLayer
from cache.key_generator import CacheKeyGenerator
from lobby.classifier import LobbyClassifier
from marvin.system import MarvinSystem


def make_system(tmp_path):
    db_path = tmp_path / "cache.db"
    return MarvinSystem(
        classifier=LobbyClassifier(),
        cache=CacheLayer(str(db_path)),
        keygen=CacheKeyGenerator(),
    )


def test_status_check_is_cached(tmp_path):
    system = make_system(tmp_path)

    first = system.handle("What's the status?", project=".")
    second = system.handle("What's the status?", project=".")

    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    assert second["cache"]["hit_count"] == 1
    system.close()


def test_debugging_not_cached(tmp_path):
    system = make_system(tmp_path)

    first = system.handle("App crashed with an exception", project=".")
    second = system.handle("App crashed with an exception", project=".")

    assert first["classification"]["intent"] == "debugging"
    assert second["cache"]["hit"] is False
    system.close()


def test_routing_department_selection(tmp_path):
    system = make_system(tmp_path)

    result = system.handle("Please review this pull request", project=".")

    assert result["envelope"]["department"] == "tess"
    assert result["classification"]["intent"] == "code_review"
    system.close()
