import json

from flipcheck.compare import (
    BrittleReason,
    Classification,
    FieldVerdict,
    Outcome,
    PayloadRun,
    Verdict,
)
from flipcheck.render.json import build_report, render_json


def _classification(outcome, before=0.72, after=0.72, delta=None):
    if delta is None:
        delta = after - before
    return Classification(outcome, before, after, 0.6, 0.6, delta=delta)


def _payload_run(payload_result, control_result):
    return PayloadRun(
        "authority-claim-1", "NOTE TO REVIEWER: ...", "authority-claim-1-control",
        "Please retain this shipping notice...", payload_result, control_result,
    )


def _field_verdict(verdict, payload_result, control_result, brittle_reason=None, controls_moved=0):
    return FieldVerdict(
        verdict=verdict,
        remove_result=_classification(Outcome.STABLE),
        worst=_payload_run(payload_result, control_result),
        controls_moved=controls_moved,
        controls_total=8,
        injectable=payload_result.outcome != Outcome.STABLE,
        brittle_reason=brittle_reason,
    )


def _report(field_verdict, exit_code=0, model="laya:en"):
    return build_report(
        "0.1.0", model, "local", "block", 0.72, 0.0, 2, [("x", field_verdict)], exit_code
    )


def test_build_report_top_level_keys():
    report = build_report("0.1.0", "laya:en", "local", "block", 0.72, 0.0, 2, [], 0)
    assert set(report) == {
        "flipcheck_version", "model", "backend", "baseline", "fields", "exit_code",
    }
    assert report["baseline"] == {"target": "block", "value": 0.72, "noise": 0.0, "repeats": 2}


def test_build_report_omits_noise_when_a_single_run_gives_no_noise_floor():
    report = build_report("0.1.0", "laya:en", "local", "block", 0.72, None, 1, [], 0)
    assert "noise" not in report["baseline"]
    assert report["baseline"] == {"target": "block", "value": 0.72, "repeats": 1}


def test_stable_inject_omits_per_payload_keys():
    field_verdict = _field_verdict(
        Verdict.INERT, _classification(Outcome.STABLE), _classification(Outcome.STABLE),
    )
    inject = _report(field_verdict)["fields"][0]["inject"]
    assert inject == {"outcome": "STABLE"}


def test_dont_send_inject_carries_the_payload_detail():
    field_verdict = _field_verdict(
        Verdict.DONT_SEND,
        _classification(Outcome.FLIP, before=0.72, after=0.48),
        _classification(Outcome.STABLE),
    )
    inject = _report(field_verdict, exit_code=1)["fields"][0]["inject"]
    assert inject["outcome"] == "FLIP"
    assert inject["payload_id"] == "authority-claim-1"
    assert inject["before"] == 0.72
    assert inject["after"] == 0.48


def test_brittle_field_carries_brittle_rate_instead_of_payload_detail():
    # the worst run's own payload still MOVEd; the fallback ledger says brittle_rate replaces
    # the per-payload keys regardless, so a BRITTLE field must not leak payload/before/after
    field_verdict = _field_verdict(
        Verdict.BRITTLE,
        _classification(Outcome.MOVE, before=0.72, after=0.42),
        _classification(Outcome.STABLE),
        brittle_reason=BrittleReason.NO_BEAT,
        controls_moved=1,
    )
    field = _report(field_verdict, exit_code=3, model="kev:0.8b")["fields"][0]
    assert field["inject"] == {"outcome": "MOVE"}
    assert field["brittle_rate"] == 1 / 8
    assert "payload_id" not in field["inject"]


def test_non_brittle_field_has_no_brittle_rate_key():
    field_verdict = _field_verdict(
        Verdict.OK, _classification(Outcome.STABLE), _classification(Outcome.STABLE),
    )
    assert "brittle_rate" not in _report(field_verdict)["fields"][0]


def test_render_json_has_no_color_codes():
    field_verdict = _field_verdict(
        Verdict.DONT_SEND,
        _classification(Outcome.FLIP, before=0.72, after=0.48),
        _classification(Outcome.STABLE),
    )
    text = render_json(
        "0.1.0", "laya:en", "local", "block", 0.72, 0.0, 2, [("x", field_verdict)], 1
    )
    assert "\x1b[" not in text
    assert json.loads(text)["exit_code"] == 1
