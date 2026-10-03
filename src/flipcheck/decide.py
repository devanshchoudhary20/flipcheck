import re

from flipcheck import http
from flipcheck.backend import model_names
from flipcheck.errors import FlipcheckError
from flipcheck.render.color import sanitize

_MODEL_NAME_RE = re.compile(r'model "([^"]+)" not found')

# D10: one generic backend-error screen for ollaya codes with no screen of their own
_NEXT_STEP = {
    "STATE_TRUNCATED": "Shorten the state, or mark fewer fields untrusted.",
    "INPUT_TOO_LONG": "Shorten the state; it is over the model's token limit.",
    "TOO_MANY_OPTIONS": "This question has more options than the model's option budget.",
    "MODEL_LOAD_FAILED": "Try a smaller model: ollaya pull laya:en",
    "INFERENCE_FAILED": "The model runner failed; retry, or try a smaller model.",
    "UNAUTHORIZED": "Set OLLAYA_API_KEY to a matching value, or unset it on the server.",
}
_DEFAULT_NEXT_STEP = "Retry, or try a smaller model: ollaya pull laya:en"


class DecisionError(FlipcheckError):
    pass


def _next_step(code: str) -> str:
    return _NEXT_STEP.get(code, _DEFAULT_NEXT_STEP)


_FORCE_LOCAL_LINES = (
    "  ollaya pull laya:en\n"
    "  flipcheck run request.json --base-url http://127.0.0.1:11435"
)


def _host_display(backend) -> str:
    # screen 13 fallback: an unparsable base URL (_host_label's "remote") reads as this, not a blank
    return "the configured backend" if backend.label == "remote" else backend.label


def _key_rejected_message(backend) -> str:
    return (
        f"flipcheck: key rejected by {_host_display(backend)} (401).\n"
        "TypeSafe direct keys are waitlisted (opentweet.io/jev/api-access); Vercel AI\n"
        "Gateway needs an AI_GATEWAY_API_KEY with TypeSafe access enabled.\n"
        "Run locally instead:\n"
        f"{_FORCE_LOCAL_LINES}"
    )


def _is_vercel_free_tier_refusal(backend, raw_error: str | None) -> bool:
    # fix: reuse backend.label, the exact parsed hostname, not a base_url substring a path can fake
    if backend.label != "ai-gateway.vercel.sh":
        return False
    return bool(raw_error and "free tier" in raw_error.lower())


def _vercel_free_tier_message(backend, raw_error: str) -> str:
    # raw_error is always truthy here; the unreachable no-message fallback was deleted, not tested
    host = _host_display(backend)
    # the gateway's own text gets its own line: the fixed prefix alone leaves no 80-col room
    first_line = f"flipcheck: {host} refused the call:\n{raw_error}"
    return (
        f"{first_line}\n"
        "Jev is not in Vercel's free tier; buy AI Gateway credits or run locally:\n"
        f"{_FORCE_LOCAL_LINES}"
    )


def _hosted_payment_message(backend, status: int, raw_error: str | None) -> str:
    # some other payment problem (free-tier is checked, and ruled out, before this is called)
    message = raw_error or "(no message from the backend)"
    return (
        f"flipcheck: {_host_display(backend)} returned {status}: {message}\n"
        "Check your account's credits or billing, or run locally:\n"
        f"{_FORCE_LOCAL_LINES}"
    )


def extract_cost(response: dict) -> float | None:
    # parsed at the boundary with the rest of the response; never a placeholder for an absent field
    metadata = response.get("provider_metadata")
    gateway = metadata.get("gateway") if isinstance(metadata, dict) else None
    cost = gateway.get("cost") if isinstance(gateway, dict) else None
    return cost if isinstance(cost, (int, float)) else None


def _hosted_model_not_found_message(frozen_error: str, backend, missing: str) -> str:
    # a hosted account has no "ollaya pull"; the frozen error gets its own line (80-col budget)
    return (
        f'flipcheck: {_host_display(backend)} rejected the model "{missing}":\n'
        f"{frozen_error}\n\n"
        "Pass a model your account offers:\n"
        f"  flipcheck run request.json --model <model> --base-url {backend.base_url}"
    )


def _model_not_found_message(frozen_error: str, backend, get_fn) -> str:
    match = _MODEL_NAME_RE.search(frozen_error)
    missing = match.group(1) if match else "<model>"
    if not backend.is_local:
        return _hosted_model_not_found_message(frozen_error, backend, missing)
    try:
        models_resp = get_fn(f"{backend.base_url}/v1/models", backend.headers)
        names = [sanitize(name) for name in model_names(models_resp)]
    except Exception:
        names = []
    listed = (
        "\n".join(f"  {name}" for name in names)
        if names
        else "  (none installed; ollaya pull laya:en to pull one)"
    )
    return (
        f"flipcheck: {frozen_error}\n\n"
        f"Installed models on {backend.base_url}:\n{listed}\n\n"
        "Pull it:\n"
        f"  ollaya pull {missing}\n"
        "or rerun with --model <one of the installed models>"
    )


def _retries_exhausted_message(exc: http.RetriesExhausted, backend) -> str:
    attempts = ", ".join(str(status) for status in exc.statuses)
    # D3: a backend that is already local gets no "switch to local" dead end
    way_back = (
        "retry, or try a smaller model: ollaya pull laya:en"
        if backend.is_local
        else f"retry, or switch to the local model:\n{_FORCE_LOCAL_LINES}"
    )
    first = f"flipcheck: giving up after {len(exc.statuses)} attempts ({attempts})."
    if exc.last_retry_after:
        return (
            f"{first}\n"
            f"Last Retry-After: {exc.last_retry_after}s. The backend is rate-limiting or "
            f"overloaded; wait and\n{way_back}"
        )
    # TEST fix 3: "not given (backed off Ns)" needs its own line to fit the 80-col budget
    return (
        f"{first}\n"
        f"Last Retry-After: not given (backed off {exc.backoff_used:.0f}s).\n"
        f"The backend is rate-limiting or overloaded; wait and\n{way_back}"
    )


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_answer_shape(answer, question_id: str, question_type: str | None, where: str) -> None:
    # boundary check: a malformed answer must raise here, never render as None/0.00/"safe"
    if not isinstance(answer, dict):
        raise DecisionError(
            f'flipcheck: malformed response from the backend{where}: '
            f'"{question_id}" answer is not an object.'
        )
    if question_type == "choice":
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or not probabilities:
            raise DecisionError(
                f'flipcheck: malformed response from the backend{where}: '
                f'"{question_id}" answer has no non-empty "probabilities" object.'
            )
        if not all(_is_number(v) for v in probabilities.values()):
            raise DecisionError(
                f'flipcheck: malformed response from the backend{where}: '
                f'"{question_id}" "probabilities" has a non-numeric value.'
            )
    elif question_type == "noul":
        if not _is_number(answer.get("noul")):
            raise DecisionError(
                f'flipcheck: malformed response from the backend{where}: '
                f'"{question_id}" answer has no numeric "noul" value.'
            )
    confidence = answer.get("confidence")
    if confidence is not None and not _is_number(confidence):
        raise DecisionError(
            f'flipcheck: malformed response from the backend{where}: '
            f'"{question_id}" "confidence" is not numeric.'
        )


def _validate_response(response, payload: dict, call_label: str) -> dict:
    where = f" on call {call_label}" if call_label else ""
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise DecisionError(
            f'flipcheck: malformed response from the backend{where}: no "answers" object.'
        )
    question_id = next(iter(payload["questions"]))
    if question_id not in response["answers"]:
        raise DecisionError(
            f'flipcheck: malformed response from the backend{where}: '
            f'"answers" has no "{question_id}" entry.'
        )
    question_type = payload["questions"][question_id].get("type")
    _validate_answer_shape(response["answers"][question_id], question_id, question_type, where)
    return response


def _generic_error_message(code: str, status: int, where: str, message: str, backend) -> str:
    # g: a hosted backend has no "ollaya pull"; the message gets its own line (80-col budget)
    if backend.is_local:
        first = f"flipcheck: ollaya returned {code} ({status}){where}:"
        return f"{first}\n{message}\n{_next_step(code)}"
    return (
        f"flipcheck: {_host_display(backend)} returned {code} ({status}){where}:\n"
        f"{message}\n"
        "Try a different model with --model, or run locally:\n"
        "  flipcheck run request.json --backend local"
    )


def call_systemone(
    backend, payload: dict, call_label: str = "", post_fn=http.post, get_fn=http.get
) -> dict:
    try:
        response = post_fn(f"{backend.base_url}/v1/systemone", backend.headers, payload)
        return _validate_response(response, payload, call_label)
    except http.HTTPError as e:
        code = sanitize(e.body.get("code", "UNKNOWN"))
        raw_error = sanitize(e.body.get("error"))
        if code == "MODEL_NOT_FOUND":
            message = raw_error or "(no message from the backend)"
            raise DecisionError(_model_not_found_message(message, backend, get_fn)) from e
        # screens 13, 14: TypeSafe/Vercel errors don't carry ollaya's own "code" field
        if not backend.is_local:
            if e.status == 401:
                raise DecisionError(_key_rejected_message(backend)) from e
            if _is_vercel_free_tier_refusal(backend, raw_error):
                raise DecisionError(_vercel_free_tier_message(backend, raw_error)) from e
            if e.status == 402:
                raise DecisionError(_hosted_payment_message(backend, e.status, raw_error)) from e
        message = raw_error or "(no message from the backend)"
        where = f" on call {call_label}" if call_label else ""
        raise DecisionError(_generic_error_message(code, e.status, where, message, backend)) from e
    except http.RetriesExhausted as e:
        raise DecisionError(_retries_exhausted_message(e, backend)) from e
    except ConnectionError as e:
        raise DecisionError(f"flipcheck: could not reach {backend.base_url}: {e}") from e
