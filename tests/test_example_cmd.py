import json
from pathlib import Path

from flipcheck.example_cmd import cmd_example
from flipcheck.octomind import OCTOMIND_REQUEST

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_dev_fixture_matches_the_shipped_constant():
    on_disk = json.loads((REPO_ROOT / "examples" / "octomind.json").read_text())
    assert on_disk == OCTOMIND_REQUEST


def test_cmd_example_writes_request_json(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    exit_code = cmd_example()
    assert exit_code == 0
    written = json.loads((tmp_path / "request.json").read_text())
    assert written == OCTOMIND_REQUEST
    assert "wrote request.json" in capsys.readouterr().out


def test_cmd_example_never_overwrites(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "request.json").write_text('{"state": {}, "questions": {}}')
    exit_code = cmd_example()
    assert exit_code == 0
    kept = json.loads((tmp_path / "request.json").read_text())
    assert kept == {"state": {}, "questions": {}}
    assert "already exists" in capsys.readouterr().err


def test_cmd_example_ends_with_the_bridge_to_the_readers_own_agent(tmp_path, monkeypatch, capsys):
    # D13 (pm-gate-2): screen 11 must point at running the reader's own request, not a rerun
    monkeypatch.chdir(tmp_path)
    exit_code = cmd_example()
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Test your own agent: save its /v1/systemone body as JSON, then" in out
    assert "flipcheck run <file> (README: getting request.json)" in out
