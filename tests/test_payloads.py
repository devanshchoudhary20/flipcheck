import json

import pytest

from flipcheck.payloads import PayloadsError, load_default_payloads, load_payloads


def test_load_default_payloads_has_eight_length_matched_entries():
    entries = load_default_payloads()
    assert len(entries) == 8
    for entry in entries:
        assert len(entry.text) == len(entry.control_text)


def test_load_default_payloads_ids_are_unique():
    entries = load_default_payloads()
    ids = [entry.id for entry in entries]
    assert len(ids) == len(set(ids))


def test_load_payloads_none_returns_default():
    assert load_payloads(None) == load_default_payloads()


def test_load_payloads_reads_custom_file(tmp_path):
    custom = [
        {
            "id": "harmless-1",
            "class": "neutral",
            "source": "test",
            "text": "hi there",
            "control_id": "harmless-1-control",
            "control_text": "hi there",
        }
    ]
    path = tmp_path / "mine.json"
    path.write_text(json.dumps(custom))
    entries = load_payloads(str(path))
    assert len(entries) == 1
    assert entries[0].id == "harmless-1"


def test_load_payloads_non_utf8_file_gives_a_clean_message_not_a_traceback(tmp_path):
    path = tmp_path / "mine.json"
    path.write_bytes(b"\xff\xfe{bad")
    with pytest.raises(PayloadsError) as exc:
        load_payloads(str(path))
    assert "is not UTF-8 text" in exc.value.message
    assert exc.value.exit_code == 2


def test_load_payloads_rejects_empty_corpus(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("[]")
    with pytest.raises(PayloadsError):
        load_payloads(str(path))


def test_load_payloads_rejects_entry_missing_key(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"id": "x", "text": "hi"}]))
    with pytest.raises(PayloadsError):
        load_payloads(str(path))
