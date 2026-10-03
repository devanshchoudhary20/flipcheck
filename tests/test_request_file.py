import json

import pytest
from conftest import make_run_args

from flipcheck import http
from flipcheck.request_file import RequestError, _position_text, load_request, select_question
from flipcheck.runner import run_command


def test_load_request_bad_json_reports_position(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"state": {}, "questions": {')
    with pytest.raises(RequestError) as exc:
        load_request(str(path))
    assert "not valid JSON" in exc.value.message


def test_load_request_missing_state(tmp_path):
    path = tmp_path / "req.json"
    path.write_text(json.dumps({"questions": {"q": {"type": "choice"}}}))
    with pytest.raises(RequestError) as exc:
        load_request(str(path))
    assert 'has no "state" key' in exc.value.message
    assert 'has no "questions" key' not in exc.value.message


def test_load_request_missing_questions(tmp_path):
    path = tmp_path / "req.json"
    path.write_text(json.dumps({"state": {"tool_name": "shell"}}))
    with pytest.raises(RequestError) as exc:
        load_request(str(path))
    assert 'has no "questions" key' in exc.value.message
    assert 'has no "state" key' not in exc.value.message


def test_load_request_non_utf8_file_gives_a_clean_message_not_a_traceback(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff\xfe{bad")
    with pytest.raises(RequestError) as exc:
        load_request(str(path))
    assert "is not UTF-8 text" in exc.value.message
    assert exc.value.exit_code == 2


def test_load_request_ok(tmp_path):
    path = tmp_path / "req.json"
    body = {"state": {"a": 1}, "questions": {"q": {"type": "noul"}}}
    path.write_text(json.dumps(body))
    assert load_request(str(path)) == body


def test_position_text_reads_position_unknown_when_the_parser_has_no_lineno_or_colno():
    # some JSONDecodeError subclasses/positions carry no line/column; must read as a hint,
    # never a blank or crash on the "line None, column None" f-string
    class _Positionless:
        lineno = None
        colno = None

    assert _position_text(_Positionless()) == "position unknown"


def test_select_question_rejects_score_type():
    with pytest.raises(RequestError):
        select_question({"urgency": {"type": "score", "criteria": ["a", "b"]}})


def test_select_question_rejects_a_non_object_question_rather_than_crashing():
    # c: a string (or any non-dict) in place of the question body must not AttributeError
    with pytest.raises(RequestError) as exc:
        select_question({"decision": "not a question object"})
    assert 'question 1 ("decision") is not an object' in exc.value.message
    assert exc.value.exit_code == 2


def test_score_question_skip_is_non_fatal_end_to_end_through_the_runner(
    tmp_path, monkeypatch, capsys
):
    # item 5: the skip note is diagnostic, not an error; the run still prints the full table
    request = {
        "state": {"tool_result": "ok"},
        "questions": {
            "decision": {"type": "choice", "criteria": {"block": "b", "allow": "a"}},
            "urgency": {"type": "score", "criteria": ["a", "b"]},
        },
    }
    path = tmp_path / "req.json"
    path.write_text(json.dumps(request))

    def fake_post(url, headers, body):
        return {
            "answers": {"decision": {"probabilities": {"block": 0.7, "allow": 0.3},
                                      "confidence": 0.6}}
        }

    monkeypatch.setattr(http, "post", fake_post)
    args = make_run_args(request_path=str(path), base_url="http://offline.invalid")
    exit_code = run_command(args)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Skipping question 2." in captured.err
    assert "FIELD" in captured.out and "VERDICT" in captured.out
    assert "state.tool_result" in captured.out


def test_select_question_returns_first_choice(capsys):
    questions = {
        "decision": {"type": "choice", "criteria": {"block": "b", "allow": "a"}},
        "extra": {"type": "score", "criteria": ["a", "b"]},
    }
    qid, question = select_question(questions)
    assert qid == "decision"
    assert question["type"] == "choice"
    err = capsys.readouterr().err
    # screens.md's exact wording for the documented single-skip case, not "skipping questions 2-2"
    assert err == (
        'flipcheck: question 2 is type "score"; v1 only checks the first question and\n'
        'only "noul" or "choice" types. Skipping question 2.\n'
    )
