"""Tests for the worker action extraction."""

from src.worker import extract_actions


def test_extract_single_action():
    text = '''Here's what I'll do:
```action
{"type": "shell", "command": "git status"}
```
'''
    actions = extract_actions(text)
    assert len(actions) == 1
    assert actions[0]["type"] == "shell"
    assert actions[0]["command"] == "git status"


def test_extract_multiple_actions():
    text = '''Let me check both:
```action
{"type": "shell", "command": "git status"}
```
And also:
```action
{"type": "container_status"}
```
'''
    actions = extract_actions(text)
    assert len(actions) == 2


def test_no_actions():
    text = "Just a normal response with no actions."
    actions = extract_actions(text)
    assert len(actions) == 0


def test_invalid_json_skipped():
    text = '''
```action
{not valid json}
```
'''
    actions = extract_actions(text)
    assert len(actions) == 0
