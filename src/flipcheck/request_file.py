import json
import sys
import textwrap
from pathlib import Path

from flipcheck.errors import FlipcheckError, read_utf8_text


class RequestError(FlipcheckError):
    pass


def _position_text(error: json.JSONDecodeError) -> str:
    if error.lineno and error.colno:
        return f"line {error.lineno}, column {error.colno}"
    return "position unknown"


def _missing_key_message(path_str: str, key: str) -> str:
    return (
        f'flipcheck: {path_str} has no "{key}" key. flipcheck needs a decision request\n'
        'with "state" and "questions", the same body your agent sends to /v1/systemone.'
    )


def load_request(path_str: str) -> dict:
    path = Path(path_str)
    raw = read_utf8_text(path, RequestError, path_str)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # TEST round 2: the path never truncates, so the parser's own text wraps on its own line
        detail = f"({_position_text(e)}): {e.msg}"
        wrapped = "\n".join(textwrap.wrap(detail, width=80) or [detail])
        raise RequestError(f"flipcheck: {path_str} is not valid JSON.\n{wrapped}") from e

    if not isinstance(data, dict) or "state" not in data:
        raise RequestError(_missing_key_message(path_str, "state"))
    if not isinstance(data.get("questions"), dict) or not data["questions"]:
        raise RequestError(_missing_key_message(path_str, "questions"))
    return data


def _skip_kind(question) -> str:
    question_type = question.get("type") if isinstance(question, dict) else None
    return f'type "{question_type}"' if question_type else "no type"


def _skip_note(questions: dict, skipped_ids: list[str]) -> str:
    # screens.md's own wording: a single skipped question names itself and its own type
    if len(skipped_ids) == 1:
        number = 2
        kind = _skip_kind(questions[skipped_ids[0]])
        return (
            f"flipcheck: question {number} is {kind}; v1 only checks the first question and\n"
            f'only "noul" or "choice" types. Skipping question {number}.'
        )
    # D15's gap, generalized beyond one extra question: screens.md only specs the single case
    last = len(skipped_ids) + 1
    return (
        f"flipcheck: request has {last} questions; v1 checks question 1 only, "
        f"skipping questions 2-{last}."
    )


def select_question(questions: dict) -> tuple[str, dict]:
    question_id, question = next(iter(questions.items()))
    if not isinstance(question, dict):
        raise RequestError(
            f'flipcheck: question 1 ("{question_id}") is not an object; v1 only checks '
            'question 1, and only "noul" or "choice" types.'
        )
    question_type = question.get("type")
    if question_type not in ("choice", "noul"):
        kind = f'type "{question_type}"' if question_type else "no type"
        raise RequestError(
            f'flipcheck: question 1 ("{question_id}") has {kind}; v1 only checks question 1, '
            'and only "noul" or "choice" types.'
        )
    skipped_ids = list(questions.keys())[1:]
    if skipped_ids:
        print(_skip_note(questions, skipped_ids), file=sys.stderr)
    return question_id, question
