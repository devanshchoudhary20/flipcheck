import pytest
from conftest import assert_max_line_width

from flipcheck.untrusted import UntrustedError, default_detect, resolve_untrusted


def test_default_detect_matches_pattern_list():
    state = {"tool_name": "shell", "previous_tool_output": "note", "arguments": {}}
    assert default_detect(state) == ["state.previous_tool_output"]


def test_default_detect_no_match_returns_empty():
    state = {"tool_name": "shell", "arguments": {}, "status": "pending"}
    assert default_detect(state) == []


def test_resolve_untrusted_prefers_cli_flag():
    request = {"state": {"a": {"b": 1}}, "_untrusted": ["state.a"]}
    assert resolve_untrusted(request, ["state.a.b"], "request.json") == ["state.a.b"]


def test_resolve_untrusted_falls_back_to_file_list():
    request = {"state": {"a": 1}, "_untrusted": ["state.a"]}
    assert resolve_untrusted(request, None, "request.json") == ["state.a"]


def test_resolve_untrusted_falls_back_to_default_regex():
    request = {"state": {"tool_result": "x"}}
    assert resolve_untrusted(request, None, "request.json") == ["state.tool_result"]


def test_resolve_untrusted_raises_when_nothing_matches():
    request = {"state": {"tool_name": "shell"}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, None, "request.json")
    assert "no untrusted fields detected" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_resolve_untrusted_raises_on_missing_cli_path():
    request = {"state": {"tool_name": "shell"}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, ["state.nope"], "request.json")
    assert "--untrusted" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_resolve_untrusted_rejects_state_itself_rather_than_crashing():
    # c: --untrusted state would delete "state" then crash looking it back up; refuse it instead
    request = {"state": {"tool_name": "shell", "previous_tool_output": "x"}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, ["state"], "request.json")
    assert '"state" not found' in exc.value.message
    assert exc.value.exit_code == 2


def test_resolve_untrusted_rejects_a_path_outside_state():
    request = {"state": {"tool_name": "shell"}, "other": {"tool_result": "x"}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, ["other.tool_result"], "request.json")
    assert '"other.tool_result" not found' in exc.value.message


def test_resolve_untrusted_reports_none_for_an_empty_state_rather_than_a_blank():
    # screen 9's own fallback: an empty "state" object must read "(none)", not a blank line
    request = {"state": {}}
    with pytest.raises(UntrustedError) as exc:
        resolve_untrusted(request, None, "request.json")
    assert 'Top-level keys in "state": (none)' in exc.value.message
