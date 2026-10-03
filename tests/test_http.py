from http.client import IncompleteRead

import pytest

from flipcheck import http


def test_parse_body_coerces_a_json_list_error_body():
    assert http._parse_body(b"[1, 2]") == {"error": "[1, 2]", "code": "UNKNOWN"}


def test_parse_body_coerces_a_json_string_error_body():
    assert http._parse_body(b'"oops"') == {"error": "oops", "code": "UNKNOWN"}


def test_http_error_coerces_a_non_dict_body_so_e_body_get_never_crashes():
    assert http.HTTPError(500, [], {}).body == {"error": "[]", "code": "UNKNOWN"}
    assert http.HTTPError(500, "oops", {}).body == {"error": "oops", "code": "UNKNOWN"}


def test_do_request_maps_a_socket_timeout_to_connection_error(monkeypatch):
    def raising_open(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(http._OPENER, "open", raising_open)
    with pytest.raises(ConnectionError):
        http._do_request("POST", "http://x", {}, b"{}", 1)


def test_do_request_maps_an_incomplete_read_to_connection_error(monkeypatch):
    def raising_open(req, timeout):
        raise IncompleteRead(b"")

    monkeypatch.setattr(http._OPENER, "open", raising_open)
    with pytest.raises(ConnectionError):
        http._do_request("POST", "http://x", {}, b"{}", 1)


@pytest.mark.parametrize(
    "value",
    ["999999999", "²", "-5", "nan", "inf", "junk"],
)
def test_parse_retry_after_rejects_unsafe_values_but_never_crashes(value):
    parsed = http._parse_retry_after(value)
    assert parsed is None or (0 <= parsed <= http.MAX_WAIT_SECONDS)


def test_parse_retry_after_caps_a_huge_value_at_max_wait():
    assert http._parse_retry_after("999999999") == http.MAX_WAIT_SECONDS


def test_parse_retry_after_rejects_negative_and_nan():
    assert http._parse_retry_after("-5") is None
    assert http._parse_retry_after("nan") is None
    assert http._parse_retry_after("inf") is None


def test_parse_retry_after_rejects_unicode_digits_and_junk():
    assert http._parse_retry_after("²") is None
    assert http._parse_retry_after("junk") is None


def test_request_falls_back_to_backoff_when_retry_after_is_unparseable(monkeypatch):
    waits = []
    monkeypatch.setattr(http.time, "sleep", lambda seconds: waits.append(seconds))

    def fake_do_request(method, url, headers, body_bytes, timeout):
        return 429, {}, {"Retry-After": "²"}

    monkeypatch.setattr(http, "_do_request", fake_do_request)
    with pytest.raises(http.RetriesExhausted):
        http.request("POST", "http://x", body={}, max_attempts=2)
    assert waits == [http.BASE_BACKOFF_SECONDS]


def test_request_never_sleeps_past_the_total_backoff_ceiling(monkeypatch):
    waits = []
    monkeypatch.setattr(http.time, "sleep", lambda seconds: waits.append(seconds))

    def fake_do_request(method, url, headers, body_bytes, timeout):
        return 429, {}, {"Retry-After": "999999999"}

    monkeypatch.setattr(http, "_do_request", fake_do_request)
    with pytest.raises(http.RetriesExhausted):
        http.request("POST", "http://x", body={}, max_attempts=5)
    assert sum(waits) <= http.TOTAL_BACKOFF_CEILING_SECONDS


def test_no_redirect_handler_refuses_a_redirect_request():
    handler = http._NoRedirectHandler()
    with pytest.raises(http._RedirectRefused):
        handler.redirect_request(None, None, 302, "Found", {}, "http://evil.invalid")


def test_do_request_maps_a_refused_redirect_to_connection_error(monkeypatch):
    def redirecting_open(req, timeout):
        raise http._RedirectRefused("refusing to follow redirect (302) to http://evil.invalid")

    monkeypatch.setattr(http._OPENER, "open", redirecting_open)
    with pytest.raises(ConnectionError):
        http._do_request("GET", "http://x", {}, None, 1)


def test_post_returns_json_on_success(monkeypatch):
    def fake_do_request(method, url, headers, body_bytes, timeout):
        return 200, {"ok": True}, {}

    monkeypatch.setattr(http, "_do_request", fake_do_request)
    assert http.post("http://x", {}, {"a": 1}) == {"ok": True}


def test_parse_body_handles_invalid_json_same_on_success_and_error():
    assert http._parse_body(b"not json") == {"error": "not json", "code": "UNKNOWN"}
    assert http._parse_body(b"") == {}


def test_post_raises_http_error_on_4xx(monkeypatch):
    def fake_do_request(method, url, headers, body_bytes, timeout):
        return 404, {"error": "not found", "code": "MODEL_NOT_FOUND"}, {}

    monkeypatch.setattr(http, "_do_request", fake_do_request)
    with pytest.raises(http.HTTPError) as exc:
        http.post("http://x", {}, {})
    assert exc.value.status == 404


def test_post_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda _seconds: None)
    calls = {"n": 0}

    def fake_do_request(method, url, headers, body_bytes, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return 503, {"error": "overloaded", "code": "QUEUE_FULL"}, {"Retry-After": "1"}
        return 200, {"ok": True}, {}

    monkeypatch.setattr(http, "_do_request", fake_do_request)
    assert http.post("http://x", {}, {}) == {"ok": True}
    assert calls["n"] == 3


def test_retries_exhausted_carries_statuses(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda _seconds: None)

    def fake_do_request(method, url, headers, body_bytes, timeout):
        return 429, {"error": "rate limited", "code": "QUEUE_FULL"}, {}

    monkeypatch.setattr(http, "_do_request", fake_do_request)
    with pytest.raises(http.RetriesExhausted) as exc:
        http.request("POST", "http://x", body={}, max_attempts=2)
    assert exc.value.statuses == [429, 429]
