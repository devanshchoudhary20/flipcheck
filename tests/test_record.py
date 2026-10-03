import json
import os

import pytest

from flipcheck import record


def test_request_hash_is_order_independent():
    # the wire body is a dict; canonical_bytes sorts keys so field order never changes the hash
    assert record.request_hash({"a": 1, "b": 2}) == record.request_hash({"b": 2, "a": 1})


def test_request_hash_changes_with_content():
    assert record.request_hash({"a": 1}) != record.request_hash({"a": 2})


def test_write_meta_then_read_meta_roundtrips(tmp_path):
    record.write_meta(
        tmp_path, flipcheck_version="0.1.0", model="laya:en", backend_label="local",
        ollaya_version="0.7.3", recorded_at="2026-09-27", request_hash_hex="abc123",
    )
    meta = record.read_meta(tmp_path)
    assert meta == {
        "flipcheck_version": "0.1.0", "model": "laya:en", "backend": "local",
        "recorded_at": "2026-09-27", "request_hash": "abc123", "ollaya_version": "0.7.3",
    }


def test_write_meta_omits_ollaya_version_when_unknown(tmp_path):
    record.write_meta(
        tmp_path, flipcheck_version="0.1.0", model="kev:0.8b", backend_label="local",
        ollaya_version=None, recorded_at="2026-09-27", request_hash_hex="abc123",
    )
    meta = record.read_meta(tmp_path)
    assert "ollaya_version" not in meta


def test_read_meta_missing_directory_returns_empty_dict(tmp_path):
    assert record.read_meta(tmp_path / "does-not-exist") == {}


def test_read_meta_corrupt_json_returns_empty_dict(tmp_path):
    (tmp_path / "meta.json").write_text("{not json")
    assert record.read_meta(tmp_path) == {}


def test_read_meta_non_utf8_file_returns_empty_dict_not_a_traceback(tmp_path):
    (tmp_path / "meta.json").write_bytes(b"\xff\xfe{bad")
    assert record.read_meta(tmp_path) == {}


def test_replay_sentence_falls_back_on_missing_fields():
    sentence = record.replay_sentence({}, "laya:en")
    assert "on an earlier run" in sentence
    assert "(version unknown)" in sentence


def test_replay_sentence_strips_esc_from_meta_fields():
    meta = {"recorded_at": "\x1b[2K2026-09-27", "ollaya_version": "0.7.3\x1b]52;c;x\x07"}
    sentence = record.replay_sentence(meta, "laya:en")
    assert "\x1b" not in sentence
    assert "\x07" not in sentence


def test_ensure_fixture_dir_creates_with_mode_0700(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "kev-0.8b"
    record.ensure_fixture_dir(fixture_dir)
    assert fixture_dir.is_dir()
    assert (os.stat(fixture_dir).st_mode & 0o777) == 0o700


def test_ensure_fixture_dir_fixes_mode_on_a_pre_existing_directory(tmp_path):
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir(mode=0o755)
    record.ensure_fixture_dir(fixture_dir)
    assert (os.stat(fixture_dir).st_mode & 0o777) == 0o700


def test_recording_post_writes_fixture_files_with_mode_0600(tmp_path):
    def fake_post(url, headers, body):
        return {"answers": {"decision": {"noul": 0.7}}}

    recording_post = record.make_recording_post(tmp_path, fake_post)
    body = {"state": {"a": 1}}
    recording_post("http://x", {}, body)
    digest = record.request_hash(body)
    mode = os.stat(tmp_path / f"{digest}.json").st_mode & 0o777
    assert mode == 0o600


def test_recording_post_refuses_a_symlink_at_the_fixture_path_rather_than_following_it(tmp_path):
    def fake_post(url, headers, body):
        return {"answers": {"decision": {"noul": 0.7}}}

    body = {"state": {"a": 1}}
    digest = record.request_hash(body)
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    (tmp_path / f"{digest}.json").symlink_to(target)

    recording_post = record.make_recording_post(tmp_path, fake_post)
    with pytest.raises(record.RecordError) as exc:
        recording_post("http://x", {}, body)
    assert "refusing to write fixture" in exc.value.message
    assert target.read_text() == "{}"


def test_recording_post_writes_a_file_named_by_the_request_hash(tmp_path):
    def fake_post(url, headers, body):
        return {"answers": {"decision": {"noul": 0.7}}}

    recording_post = record.make_recording_post(tmp_path, fake_post)
    body = {"state": {"a": 1}}
    response = recording_post("http://x", {}, body)
    assert response == {"answers": {"decision": {"noul": 0.7}}}
    digest = record.request_hash(body)
    saved = json.loads((tmp_path / f"{digest}.json").read_text())
    assert saved == response


def test_replaying_post_returns_the_recorded_response(tmp_path):
    body = {"state": {"a": 1}}
    digest = record.request_hash(body)
    (tmp_path / f"{digest}.json").write_text(json.dumps({"answers": {"decision": {"noul": 0.3}}}))
    replaying_post = record.make_replaying_post(tmp_path)
    assert replaying_post("http://x", {}, body) == {"answers": {"decision": {"noul": 0.3}}}


def test_replaying_post_misses_name_the_hash_and_never_falls_back(tmp_path):
    replaying_post = record.make_replaying_post(tmp_path)
    with pytest.raises(record.ReplayMissError) as exc:
        replaying_post("http://x", {}, {"state": {"a": 1}})
    assert "not recorded in" in exc.value.message
    assert "--record" in exc.value.message


def test_replaying_post_on_a_corrupt_fixture_file_gives_a_clear_error(tmp_path):
    body = {"state": {"a": 1}}
    digest = record.request_hash(body)
    (tmp_path / f"{digest}.json").write_text("{not valid json")
    replaying_post = record.make_replaying_post(tmp_path)
    with pytest.raises(record.ReplayMissError) as exc:
        replaying_post("http://x", {}, body)
    assert "corrupt or unreadable" in exc.value.message
    assert "--record" in exc.value.message


def test_replaying_post_on_a_non_utf8_fixture_file_gives_a_clear_error_not_a_traceback(tmp_path):
    body = {"state": {"a": 1}}
    digest = record.request_hash(body)
    (tmp_path / f"{digest}.json").write_bytes(b"\xff\xfe{bad")
    replaying_post = record.make_replaying_post(tmp_path)
    with pytest.raises(record.ReplayMissError) as exc:
        replaying_post("http://x", {}, body)
    assert "corrupt or unreadable" in exc.value.message
    assert "--record" in exc.value.message
