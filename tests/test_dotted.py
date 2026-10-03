import pytest

from flipcheck.dotted import append_text, get_path, inject_by_type, path_exists, remove_path


def test_get_path_nested():
    data = {"state": {"arguments": {"query": "hi"}}}
    assert get_path(data, "state.arguments.query") == "hi"


def test_get_path_missing_raises():
    with pytest.raises(KeyError):
        get_path({"state": {}}, "state.missing")


def test_path_exists():
    data = {"state": {"result": "ok"}}
    assert path_exists(data, "state.result") is True
    assert path_exists(data, "state.nope") is False


def test_remove_path_deletes_and_copies():
    data = {"state": {"a": 1, "b": 2}}
    result = remove_path(data, "state.a")
    assert result["state"] == {"b": 2}
    assert data["state"] == {"a": 1, "b": 2}


def test_append_text_appends_with_newline():
    data = {"state": {"note": "hello"}}
    result = append_text(data, "state.note", "world")
    assert result["state"]["note"] == "hello\nworld"
    assert data["state"]["note"] == "hello"


def test_inject_by_type_appends_to_string():
    data = {"state": {"note": "hello"}}
    result = inject_by_type(data, "state.note", "world")
    assert result["state"]["note"] == "hello\nworld"
    assert data["state"]["note"] == "hello"


def test_inject_by_type_adds_note_key_to_object():
    data = {"state": {"result": {"status": "ok"}}}
    result = inject_by_type(data, "state.result", "attacker text")
    assert result["state"]["result"] == {"status": "ok", "note": "attacker text"}
    assert "note" not in data["state"]["result"]


def test_inject_by_type_appends_element_to_array():
    data = {"state": {"documents": ["a", "b"]}}
    result = inject_by_type(data, "state.documents", "attacker text")
    assert result["state"]["documents"] == ["a", "b", "attacker text"]
    assert data["state"]["documents"] == ["a", "b"]
