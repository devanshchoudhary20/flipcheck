import json
from pathlib import Path

from conftest import make_run_args

from flipcheck import http
from flipcheck.runner import run_command

REPO_ROOT = Path(__file__).resolve().parent.parent
OCTOMIND = str(REPO_ROOT / "examples" / "octomind.json")
BASELINE_STATE = json.loads(Path(OCTOMIND).read_text())["state"]


def _fake_post(url, headers, body):
    # a model that reacts to any added text, not to what it says: every payload and its
    # length-matched control land on the same shifted answer, so neither beats the other
    # and every control moves too, same as laya:en's real control-rate failure
    probabilities = (
        {"block": 0.70, "ask": 0.10, "auto_allow": 0.20}
        if body["state"] == BASELINE_STATE
        else {"block": 0.30, "ask": 0.10, "auto_allow": 0.60}
    )
    return {"answers": {"decision": {"probabilities": probabilities, "confidence": 0.6}}}


def test_every_field_brittle_prints_the_recommendation_once_above_the_table(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _fake_post)
    args = make_run_args(
        request_path=OCTOMIND, model="laya:en", base_url="http://offline.invalid",
    )
    exit_code = run_command(args)
    out = capsys.readouterr().out

    assert exit_code == 3
    # the banner, once, above the FIELD header
    banner_count = out.count("controls moved the verdict on every untrusted field in this")
    assert banner_count == 1
    assert out.index("controls moved the verdict on every untrusted field") < out.index("FIELD")
    # both rows keep their own fact line, but drop the now-redundant per-row advice
    assert out.count("More than 4 of 8 harmless controls moved") == 2
    assert out.count("Injection can't be told from noise here") == 0
    assert out.count("BRITTLE") >= 2
