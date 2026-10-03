import json
from pathlib import Path

from conftest import make_run_args

from flipcheck import http
from flipcheck.runner import _resolve_backend_and_post, run_command

REPO_ROOT = Path(__file__).resolve().parent.parent
OCTOMIND = str(REPO_ROOT / "examples" / "octomind.json")
LAYA_FIXTURE = REPO_ROOT / "src" / "flipcheck" / "fixtures" / "example-laya-en"
KEV_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "kev-0.8b"


def _strip_replay_banner(output: str) -> str:
    # replay prints one extra bracketed banner block after the header; the live run that
    # produced the evidence file never printed it, so remove it before the byte comparison
    start = output.find("\n[")
    if start == -1:
        return output
    end = output.find("]\n", start)
    return output[:start] + output[end + 1 :]


def _refuse_network(*_args, **_kwargs):
    raise AssertionError("replay must never call a live backend")


def test_replay_laya_en_matches_live_evidence(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _refuse_network)
    monkeypatch.setattr(http, "get", _refuse_network)
    monkeypatch.setenv("NO_COLOR", "1")
    args = make_run_args(request_path=OCTOMIND, model="laya:en", replay=str(LAYA_FIXTURE))
    exit_code = run_command(args)
    assert exit_code == 1
    live_evidence_path = REPO_ROOT / "tests" / "fixtures" / "live" / "verdict-table-laya-en.txt"
    live_evidence = live_evidence_path.read_text()
    assert _strip_replay_banner(capsys.readouterr().out) == live_evidence


def test_replay_kev_matches_live_evidence_and_drives_brittle_from_real_output(
    monkeypatch, capsys
):
    monkeypatch.setattr(http, "post", _refuse_network)
    monkeypatch.setattr(http, "get", _refuse_network)
    monkeypatch.setenv("NO_COLOR", "1")
    args = make_run_args(request_path=OCTOMIND, model="kev:0.8b", replay=str(KEV_FIXTURE))
    exit_code = run_command(args)
    assert exit_code == 1
    out = capsys.readouterr().out
    live_evidence_path = REPO_ROOT / "tests" / "fixtures" / "live" / "verdict-table-kev-0.8b.txt"
    live_evidence = live_evidence_path.read_text()
    assert _strip_replay_banner(out) == live_evidence
    # the BRITTLE row here comes from kev:0.8b's own recorded controls, not a synthetic fixture
    assert "More than 4 of 8 harmless controls moved this field on kev:0.8b (5 of 8)" in out


def test_replay_miss_names_the_hash_and_how_to_rerecord(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _refuse_network)
    monkeypatch.setattr(http, "get", _refuse_network)
    empty_fixture = tmp_path / "fixtures"
    empty_fixture.mkdir()
    args = make_run_args(request_path=OCTOMIND, model="kev:0.8b", replay=str(empty_fixture))
    exit_code = run_command(args)
    assert exit_code == 2
    err = capsys.readouterr().err
    assert f"not recorded in {empty_fixture}" in err
    assert "--record" in err


def test_replay_prints_no_progress_lines(monkeypatch, capsys):
    # screens.md's lifecycle step 2 and screen 11 show no loading state for a replay
    monkeypatch.setattr(http, "post", _refuse_network)
    monkeypatch.setattr(http, "get", _refuse_network)
    args = make_run_args(request_path=OCTOMIND, model="laya:en", replay=str(LAYA_FIXTURE))
    run_command(args)
    err = capsys.readouterr().err
    assert "running" not in err
    assert "done in" not in err


def test_replay_backend_label_and_model_come_from_the_fixtures_meta(tmp_path):
    (tmp_path / "meta.json").write_text(
        json.dumps({"model": "kev:0.8b", "backend": "ai-gateway.vercel.sh"})
    )
    request = json.loads(Path(OCTOMIND).read_text())
    args = make_run_args(replay=str(tmp_path))
    backend, _post_fn, meta = _resolve_backend_and_post(
        args, request, "decision", request["questions"]["decision"]
    )
    assert backend.label == "ai-gateway.vercel.sh"
    assert backend.model == "kev:0.8b"
    assert backend.is_local is False
    assert meta["backend"] == "ai-gateway.vercel.sh"


def test_replay_mismatch_is_caught_before_any_per_call_miss(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _refuse_network)
    monkeypatch.setattr(http, "get", _refuse_network)
    mismatched_fixture = tmp_path / "fixtures"
    mismatched_fixture.mkdir()
    (mismatched_fixture / "meta.json").write_text(
        json.dumps({"model": "kev:0.8b", "backend": "local", "request_hash": "0" * 64})
    )
    args = make_run_args(request_path=OCTOMIND, model="kev:0.8b", replay=str(mismatched_fixture))
    exit_code = run_command(args)
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "was recorded for a different request" in err
    assert "--record" in err
    assert "not recorded in" not in err  # the per-call miss message must not also fire


def test_replay_json_shape(monkeypatch, capsys):
    monkeypatch.setattr(http, "post", _refuse_network)
    monkeypatch.setattr(http, "get", _refuse_network)
    args = make_run_args(
        request_path=OCTOMIND, model="laya:en", replay=str(LAYA_FIXTURE), json=True,
    )
    exit_code = run_command(args)
    report = json.loads(capsys.readouterr().out)
    assert report["exit_code"] == exit_code
    assert set(report) == {
        "flipcheck_version", "model", "backend", "baseline", "fields", "exit_code",
    }
    assert report["model"] == "laya:en"
    assert report["backend"] == "local"
    assert {"target", "value", "noise", "repeats"} <= set(report["baseline"])
    for field in report["fields"]:
        assert {"path", "remove", "inject", "control", "verdict", "action"} <= set(field)
