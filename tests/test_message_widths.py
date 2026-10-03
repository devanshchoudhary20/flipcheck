import json
from pathlib import Path

import pytest
from conftest import assert_max_line_width

from flipcheck.backend import Backend, missing_key_message, no_backend_message
from flipcheck.decide import _hosted_model_not_found_message
from flipcheck.record import replay_miss_message
from flipcheck.request_file import RequestError, load_request
from flipcheck.untrusted import UntrustedError, resolve_untrusted

# every error screen's message must fit a plain 80-column terminal (TEST fix 3); this file
# is the one place that sweeps all of them, on top of the width asserts next to each screen's
# own test in test_decide.py, test_backend.py and test_untrusted.py


def test_screen_6_no_backend_reachable_fits_80_columns():
    assert_max_line_width(no_backend_message("http://127.0.0.1:11435"))


def test_missing_key_message_fits_80_columns():
    assert_max_line_width(missing_key_message("vercel", "AI_GATEWAY_API_KEY"))
    assert_max_line_width(missing_key_message("typesafe", "TYPESAFE_API_KEY"))


def test_screen_8_bad_json_fits_80_columns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("bad.json").write_text('{"state": {}, "questions": {')
    with pytest.raises(RequestError) as exc:
        load_request("bad.json")
    assert "not valid JSON" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_screen_8_bad_json_with_a_longer_filename_still_fits_80_columns(tmp_path, monkeypatch):
    # TEST round 2: a longer, realistic filename plus the parser's own message used to print
    # as one unwrapped 146-char line; the path never truncates, the parser text now wraps
    monkeypatch.chdir(tmp_path)
    name = "a-request-with-a-somewhat-longer-filename.json"
    Path(name).write_text('{"state": {}, "questions": {"q": {"type": tru}}}')
    with pytest.raises(RequestError) as exc:
        load_request(name)
    assert name in exc.value.message
    assert_max_line_width(exc.value.message)


def test_screen_8_missing_state_fits_80_columns(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("request.json").write_text(json.dumps({"questions": {"q": {"type": "choice"}}}))
    with pytest.raises(RequestError) as exc:
        load_request("request.json")
    assert_max_line_width(exc.value.message)


def test_screen_8_untrusted_path_not_found_fits_80_columns():
    request = {"state": {"tool_name": "shell"}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, ["state.nope"], "request.json")
    assert_max_line_width(exc.value.message)


def test_screen_9_no_untrusted_fields_fits_80_columns():
    request = {"state": {"tool_name": "shell"}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, None, "request.json")
    assert_max_line_width(exc.value.message)


def test_screen_12_replay_miss_fits_80_columns():
    assert_max_line_width(replay_miss_message(Path("/tmp/fixtures"), "abc123def456"))


def test_screen_7_hosted_model_not_found_fits_80_columns_except_the_base_url_command():
    vercel = Backend(
        "https://ai-gateway.vercel.sh/typesafe", "typesafe-ai/jev", "ai-gateway.vercel.sh",
        False, {},
    )
    message = _hosted_model_not_found_message(
        'model "typesafe-ai/jev-pro" not found', vercel, "typesafe-ai/jev-pro"
    )
    lines = message.splitlines()
    # the only allowed exception: a copy-pasteable --base-url command carrying the account's
    # own (long) hosted URL, which splitting would break; every other line still fits 80
    assert_max_line_width("\n".join(lines[:-1]))
    assert len(lines[-1]) == 93
