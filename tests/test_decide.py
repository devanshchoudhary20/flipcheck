import pytest
from conftest import assert_max_line_width

from flipcheck import http
from flipcheck.backend import Backend
from flipcheck.decide import DecisionError, call_systemone, extract_cost


def _backend() -> Backend:
    return Backend("http://127.0.0.1:11435", "kev:0.8b", "local", True, {})


def _vercel_backend() -> Backend:
    return Backend(
        "https://ai-gateway.vercel.sh/typesafe", "typesafe-ai/jev", "ai-gateway.vercel.sh",
        False, {},
    )


def _typesafe_backend() -> Backend:
    return Backend("https://api.typesafe.ai", "laya:en", "api.typesafe.ai", False, {})


def _payload() -> dict:
    return {
        "model": "kev:0.8b",
        "state": {"a": 1},
        "questions": {"decision": {"type": "choice", "criteria": {"block": "b", "allow": "a"}}},
    }


def test_call_systemone_raises_on_missing_answers_key():
    def fake_post(url, headers, body):
        return {"model": "kev:0.8b", "usage": {"input_tokens": 1, "output_tokens": 0}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert '"answers" object' in exc.value.message


def test_call_systemone_raises_on_missing_question_entry():
    def fake_post(url, headers, body):
        return {"model": "kev:0.8b", "answers": {"some_other_id": {"noul": 0.5}}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert '"decision" entry' in exc.value.message


def test_call_systemone_returns_response_on_valid_answers():
    def fake_post(url, headers, body):
        return {
            "model": "kev:0.8b",
            "answers": {"decision": {"probabilities": {"block": 0.7, "allow": 0.3}}},
        }

    response = call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert response["answers"]["decision"]["probabilities"]["block"] == 0.7


def test_model_not_found_on_local_backend_suggests_ollaya_pull():
    def fake_post(url, headers, body):
        raise http.HTTPError(
            404, {"error": 'model "does-not-exist" not found, try pulling it first',
                  "code": "MODEL_NOT_FOUND"}, {},
        )

    def fake_get(url, headers=None):
        return {"models": [{"name": "laya:en"}]}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post, get_fn=fake_get)
    assert "ollaya pull does-not-exist" in exc.value.message
    assert "Installed models on" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_model_not_found_sanitizes_installed_model_names_from_v1_models():
    def fake_post(url, headers, body):
        raise http.HTTPError(
            404, {"error": 'model "does-not-exist" not found, try pulling it first',
                  "code": "MODEL_NOT_FOUND"}, {},
        )

    def fake_get(url, headers=None):
        return {"models": [{"name": "laya:en\x1b[1;32m"}]}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post, get_fn=fake_get)
    assert "\x1b" not in exc.value.message
    assert "laya:en" in exc.value.message


def test_model_not_found_falls_back_when_v1_models_itself_fails():
    # decide.py's "(none installed...)" fallback: GET /v1/models raising must not crash the
    # MODEL_NOT_FOUND message, and must read as a hint rather than an empty list
    def fake_post(url, headers, body):
        raise http.HTTPError(
            404, {"error": 'model "does-not-exist" not found, try pulling it first',
                  "code": "MODEL_NOT_FOUND"}, {},
        )

    def fake_get(url, headers=None):
        raise ConnectionError("ollaya's own /v1/models is down too")

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post, get_fn=fake_get)
    assert "(none installed; ollaya pull laya:en to pull one)" in exc.value.message


def test_model_not_found_falls_back_when_v1_models_returns_an_empty_list():
    def fake_post(url, headers, body):
        raise http.HTTPError(
            404, {"error": 'model "does-not-exist" not found, try pulling it first',
                  "code": "MODEL_NOT_FOUND"}, {},
        )

    def fake_get(url, headers=None):
        return {"models": []}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post, get_fn=fake_get)
    assert "(none installed; ollaya pull laya:en to pull one)" in exc.value.message


def test_an_unparsable_base_url_reads_as_the_configured_backend_not_remote():
    # decide.py's screen-13 fallback: a backend.label of "remote" (an unparsable base URL)
    # must not leak the literal word "remote" into the 401 message
    unparsable = Backend("https://[::not-a-host", "laya:en", "remote", False, {})

    def fake_post(url, headers, body):
        raise http.HTTPError(401, {"error": "invalid api key"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(unparsable, _payload(), post_fn=fake_post)
    assert "key rejected by the configured backend (401)" in exc.value.message
    assert "remote" not in exc.value.message


def test_model_not_found_on_a_hosted_backend_never_suggests_ollaya_pull():
    def fake_post(url, headers, body):
        raise http.HTTPError(
            404, {"error": 'model "typesafe-ai/jev-pro" not found',
                  "code": "MODEL_NOT_FOUND"}, {},
        )

    with pytest.raises(DecisionError) as exc:
        call_systemone(_vercel_backend(), _payload(), post_fn=fake_post)
    assert "ollaya pull" not in exc.value.message
    assert "Installed models on" not in exc.value.message
    assert "typesafe-ai/jev-pro" in exc.value.message
    assert "--model <model>" in exc.value.message
    assert "ai-gateway.vercel.sh" in exc.value.message
    # the 93-col command line is the one documented exception; see test_message_widths.py


def test_screen_13_key_rejected_names_the_host_and_both_key_sources():
    def fake_post(url, headers, body):
        raise http.HTTPError(401, {"error": "invalid api key"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_vercel_backend(), _payload(), post_fn=fake_post)
    assert "key rejected by ai-gateway.vercel.sh (401)" in exc.value.message
    assert "waitlisted" in exc.value.message
    assert "flipcheck run request.json --base-url http://127.0.0.1:11435" in exc.value.message
    assert exc.value.exit_code == 2
    assert_max_line_width(exc.value.message)


def test_screen_14_vercel_free_tier_refusal_echoes_the_gateways_own_text():
    def fake_post(url, headers, body):
        raise http.HTTPError(402, {"error": "typesafe-ai/jev is not included in the Free tier"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_vercel_backend(), _payload(), post_fn=fake_post)
    assert "not included in the Free tier" in exc.value.message
    assert "not in Vercel's free tier" in exc.value.message
    assert "ollaya pull laya:en" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_an_unrelated_402_gets_a_payment_message_not_the_free_tier_claim():
    # fix: a 402 for some other billing reason must not say "Jev is not in Vercel's free tier"
    def fake_post(url, headers, body):
        raise http.HTTPError(402, {"error": "organization spend limit reached"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_vercel_backend(), _payload(), post_fn=fake_post)
    assert "organization spend limit reached" in exc.value.message
    assert "not in Vercel's free tier" not in exc.value.message
    assert "Check your account's credits or billing" in exc.value.message
    assert "ollaya pull laya:en" in exc.value.message


def test_a_402_with_no_body_gets_the_generic_payment_message():
    def fake_post(url, headers, body):
        raise http.HTTPError(402, {}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_vercel_backend(), _payload(), post_fn=fake_post)
    assert "not in Vercel's free tier" not in exc.value.message
    assert "(no message from the backend)" in exc.value.message


def test_screen_15_retries_exhausted_on_a_hosted_backend_points_back_to_local():
    def fake_post(url, headers, body):
        raise http.RetriesExhausted([429, 503, 429], "30", 8.0)

    with pytest.raises(DecisionError) as exc:
        call_systemone(_typesafe_backend(), _payload(), post_fn=fake_post)
    assert "giving up after 3 attempts (429, 503, 429)" in exc.value.message
    assert "Last Retry-After: 30s" in exc.value.message
    assert "flipcheck run request.json --base-url http://127.0.0.1:11435" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_screen_15_retries_exhausted_on_the_local_backend_has_no_dead_end():
    # D3: a local backend that is itself overloaded must not be told to "switch to local"
    def fake_post(url, headers, body):
        raise http.RetriesExhausted([503, 503], None, 4.0)

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert "Last Retry-After: not given (backed off 4s)" in exc.value.message
    assert "switch to the local model" not in exc.value.message
    assert "ollaya pull laya:en" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_screen_15_fallback_line_fits_80_columns_with_a_real_backoff_value(monkeypatch):
    # TEST fix 3: the no-Retry-After fallback line overflowed 80 cols by 18 chars
    def fake_post(url, headers, body):
        raise http.RetriesExhausted([429, 429, 429, 429, 429], None, 16.0)

    with pytest.raises(DecisionError) as exc:
        call_systemone(_typesafe_backend(), _payload(), post_fn=fake_post)
    assert "Last Retry-After: not given (backed off 16s)" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_a_choice_answer_with_no_probabilities_key_is_rejected_not_rendered_as_none():
    # the worst bug this round fixed: a response with no "probabilities" must not render
    # "baseline None 0.00" and exit 0 as if the field were safe
    def fake_post(url, headers, body):
        return {"answers": {"decision": {"confidence": 0.5}}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert '"decision" answer has no non-empty "probabilities" object' in exc.value.message
    assert exc.value.exit_code == 2


def test_a_choice_answer_with_empty_probabilities_is_rejected():
    def fake_post(url, headers, body):
        return {"answers": {"decision": {"probabilities": {}, "confidence": 0.5}}}

    with pytest.raises(DecisionError):
        call_systemone(_backend(), _payload(), post_fn=fake_post)


def test_a_choice_answer_with_non_numeric_probability_values_is_rejected():
    def fake_post(url, headers, body):
        return {"answers": {"decision": {"probabilities": {"block": "0.7", "allow": "0.3"}}}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert '"probabilities" has a non-numeric value' in exc.value.message


def _noul_payload() -> dict:
    return {
        "model": "kev:0.8b",
        "state": {"a": 1},
        "questions": {"q": {"type": "noul", "instructions": "ok?"}},
    }


def test_a_noul_answer_with_no_noul_key_is_rejected():
    def fake_post(url, headers, body):
        return {"answers": {"q": {"confidence": 0.9}}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _noul_payload(), post_fn=fake_post)
    assert '"q" answer has no numeric "noul" value' in exc.value.message


def test_a_noul_answer_with_no_noul_and_no_confidence_is_still_rejected_on_the_noul_check():
    def fake_post(url, headers, body):
        return {"answers": {"q": {}}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _noul_payload(), post_fn=fake_post)
    assert '"q" answer has no numeric "noul" value' in exc.value.message


def test_a_present_but_non_numeric_confidence_is_rejected():
    def fake_post(url, headers, body):
        return {"answers": {"q": {"noul": 0.7, "confidence": "high"}}}

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _noul_payload(), post_fn=fake_post)
    assert '"confidence" is not numeric' in exc.value.message


def test_an_absent_confidence_is_fine_on_an_otherwise_valid_noul_answer():
    def fake_post(url, headers, body):
        return {"answers": {"q": {"noul": 0.7}}}

    response = call_systemone(_backend(), _noul_payload(), post_fn=fake_post)
    assert response["answers"]["q"]["noul"] == 0.7


def test_a_500_with_a_json_list_error_body_never_crashes_e_body_get():
    def fake_post(url, headers, body):
        raise http.HTTPError(500, [], {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert "ollaya returned UNKNOWN (500)" in exc.value.message


def test_a_500_with_a_json_string_error_body_never_crashes_e_body_get():
    def fake_post(url, headers, body):
        raise http.HTTPError(500, "oops", {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert "oops" in exc.value.message


def test_a_generic_hosted_error_names_the_host_and_never_says_ollaya():
    def fake_post(url, headers, body):
        raise http.HTTPError(500, {"error": "upstream boom"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_vercel_backend(), _payload(), post_fn=fake_post)
    assert "ollaya" not in exc.value.message
    assert "ai-gateway.vercel.sh returned UNKNOWN (500)" in exc.value.message
    assert "--model" in exc.value.message
    assert "--backend local" in exc.value.message
    assert_max_line_width(exc.value.message)


def test_a_generic_local_error_keeps_the_ollaya_wording():
    def fake_post(url, headers, body):
        raise http.HTTPError(400, {"error": "bad request", "code": "INVALID_REQUEST"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert "flipcheck: ollaya returned INVALID_REQUEST (400)" in exc.value.message


def test_a_backend_error_carrying_esc_bytes_never_reaches_the_message():
    def fake_post(url, headers, body):
        raise http.HTTPError(500, {"error": "\x1b[2K\x1b[1;32mOK\x1b]52;c;x\x07boom"}, {})

    with pytest.raises(DecisionError) as exc:
        call_systemone(_backend(), _payload(), post_fn=fake_post)
    assert "\x1b" not in exc.value.message
    assert "\x07" not in exc.value.message


def test_extract_cost_reads_provider_metadata_gateway_cost():
    response = {"provider_metadata": {"gateway": {"cost": 0.0012}}}
    assert extract_cost(response) == 0.0012


def test_extract_cost_is_none_when_absent_never_a_placeholder():
    assert extract_cost({}) is None
    assert extract_cost({"provider_metadata": {}}) is None
    assert extract_cost({"provider_metadata": {"gateway": {}}}) is None
