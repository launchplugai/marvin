"""Tests for the dispatcher safety and execution."""

import os
import tempfile
import pytest

from src.dispatcher.dispatcher import Dispatcher


@pytest.fixture
def disp():
    return Dispatcher(work_dir=tempfile.mkdtemp())


def test_allowed_command(disp):
    result = disp.run_shell("echo hello")
    assert result.success
    assert "hello" in result.output


def test_blocked_command_prefix(disp):
    result = disp.run_shell("wget http://example.com")
    assert not result.success
    assert "BLOCKED" in result.output


def test_blocked_dangerous_pattern(disp):
    result = disp.run_shell("rm -rf /tmp/something")
    assert not result.success
    assert "BLOCKED" in result.output


def test_blocked_force_push(disp):
    result = disp.run_shell("git push origin main --force")
    assert not result.success
    assert "BLOCKED" in result.output


def test_git_status_allowed(disp):
    result = disp.run_shell("git status", cwd="/home/user/marvin")
    assert result.success


def test_file_read(disp):
    path = os.path.join(disp.work_dir, "test.txt")
    with open(path, "w") as f:
        f.write("hello world")

    result = disp.read_file(path)
    assert result.success
    assert result.output == "hello world"


def test_file_write(disp):
    path = os.path.join(disp.work_dir, "out.txt")
    result = disp.write_file(path, "written by dispatcher")
    assert result.success
    assert os.path.exists(path)
    with open(path) as f:
        assert f.read() == "written by dispatcher"


def test_audit_log(disp):
    disp.run_shell("echo test1")
    disp.run_shell("echo test2")

    log = disp.get_audit_log()
    assert len(log) == 2
    assert log[0]["ok"]
    assert log[1]["ok"]
