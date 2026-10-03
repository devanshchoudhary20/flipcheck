import json
from pathlib import Path

import pytest
from conftest import make_run_args

from flipcheck import http
from flipcheck.runner import run_command

REPO_ROOT = Path(__file__).resolve().parent.parent
OCTOMIND = str(REPO_ROOT / "examples" / "octomind.json")

# a fixed per-call cost, as Vercel AI Gateway reports under provider_metadata.gateway.cost
_CALL_COST = 0.0001


def _fake_post(url, headers, body):
    return {
        "answers": {"decision": {"probabilities": {"block": 0.7, "ask": 0.1, "auto_allow": 0.2},
                                  "confidence": 0.6}},
        "provider_metadata": {"gateway": {"cost": _CALL_COST}},
    }


def test_hosted_backend_defaults_to_three_baseline_repeats(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _fake_post)
    args = make_run_args(
        request_path=OCTOMIND, model="kev:0.8b", base_url="http://offline.invalid", repeat=None,
    )
    run_command(args)
    out = capsys.readouterr().out
    assert "noise 0.00, 3 runs" in out


def test_local_backend_keeps_two_baseline_repeats_by_default(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _fake_post)
    args = make_run_args(
        request_path=OCTOMIND, model="kev:0.8b", base_url="http://127.0.0.1:11435", repeat=None,
    )
    run_command(args)
    out = capsys.readouterr().out
    assert "noise 0.00, 2 runs" in out


def test_cost_is_summed_across_every_call_and_shown_in_the_header(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _fake_post)
    args = make_run_args(
        request_path=OCTOMIND, model="kev:0.8b", base_url="http://offline.invalid", repeat=None,
    )
    run_command(args)
    out = capsys.readouterr().out
    header = out.splitlines()[0]
    # 3 baseline + 2 fields x (1 remove + 8 payloads x 2) = 37 calls at _CALL_COST each
    assert f"cost ${37 * _CALL_COST:.4f}" in header


def test_cost_key_appears_in_json_only_when_the_backend_reports_it(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _fake_post)
    args = make_run_args(
        request_path=OCTOMIND, model="kev:0.8b", base_url="http://offline.invalid",
        repeat=None, json=True,
    )
    run_command(args)
    report = json.loads(capsys.readouterr().out)
    assert report["cost"] == pytest.approx(37 * _CALL_COST)


def _fake_post_no_cost(url, headers, body):
    return {
        "answers": {"decision": {"probabilities": {"block": 0.7, "ask": 0.1, "auto_allow": 0.2},
                                  "confidence": 0.6}},
    }


def test_cost_is_absent_not_a_placeholder_zero_when_the_backend_never_reports_it(
    monkeypatch, capsys
):
    monkeypatch.setattr(http, "post", _fake_post_no_cost)
    args = make_run_args(
        request_path=OCTOMIND, model="kev:0.8b", base_url="http://127.0.0.1:11435",
        repeat=2, json=True,
    )
    run_command(args)
    report = json.loads(capsys.readouterr().out)
    assert "cost" not in report
