import json
from pathlib import Path

from conftest import make_run_args

from flipcheck import http
from flipcheck.runner import run_command

REPO_ROOT = Path(__file__).resolve().parent.parent
INJECTED = str(REPO_ROOT / "examples" / "octomind-injected.json")

NOTE = "NOTE TO REVIEWER"


def _contains_note(value) -> bool:
    if isinstance(value, str):
        return NOTE in value
    if isinstance(value, dict):
        return any(_contains_note(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_note(v) for v in value)
    return False


def _fake_post(url, headers, body):
    # content-sensitive, not field-keyed: the model reacts to the note wherever it sits, so
    # the fake's response depends on what's actually in the state, not which call this is
    probabilities = (
        {"block": 0.07, "ask": 0.03, "auto_allow": 0.90}
        if _contains_note(body["state"])
        else {"block": 0.30, "ask": 0.10, "auto_allow": 0.60}
    )
    return {"answers": {"decision": {"probabilities": probabilities, "confidence": 0.85}}}


def test_octomind_injected_is_the_real_injected_copy_of_the_example():
    injected = json.loads(Path(INJECTED).read_text())
    assert "NOTE TO REVIEWER" in injected["state"]["previous_tool_output"]
    assert injected["_untrusted"] == ["state.previous_tool_output", "state.arguments.query"]


def test_ok_row_caveat_fires_on_an_already_attacked_field(monkeypatch, capsys):
    # the planted sentence is already in the request; flipcheck cannot tell that from the
    # outside, so the OK row must still carry the "read it before trusting this row" caveat.
    # the fake only reacts to the note's presence, so removing it (REMOVE moves) and piling
    # more payloads on top of it (INJECT stable, already saturated) land on OK, not a hard-wire
    monkeypatch.setattr(http, "post", _fake_post)
    args = make_run_args(
        request_path=INJECTED, model="kev:0.8b", base_url="http://offline.invalid",
    )
    exit_code = run_command(args)
    out = " ".join(capsys.readouterr().out.split())
    assert exit_code == 0
    row = out.split("state.previous_tool_output", 1)[1].split("state.arguments.query", 1)[0]
    assert row.startswith(" MOVE STABLE STABLE OK")
    assert "Informs the decision; resisted 8 payloads." in row
    assert "if someone outside your system writes it, read it before trusting this row" in row
