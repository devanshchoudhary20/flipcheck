import http.client
import json
import math
import time
import urllib.error
import urllib.request

RETRY_STATUSES = {429, 503, 529}
MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 1.0
MAX_WAIT_SECONDS = 60.0
TOTAL_BACKOFF_CEILING_SECONDS = 120.0


class HTTPError(Exception):
    def __init__(self, status: int, body, headers: dict):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = _coerce_body(body)
        self.headers = headers


class RetriesExhausted(Exception):
    def __init__(self, statuses: list[int], last_retry_after: str | None, backoff_used: float):
        super().__init__("retries exhausted")
        self.statuses = statuses
        self.last_retry_after = last_retry_after
        self.backoff_used = backoff_used


def _coerce_body(body) -> dict:
    # a proxy or gateway can return a JSON list/string error body; e.body.get must never crash
    if isinstance(body, dict):
        return body
    return {"error": body if isinstance(body, str) else str(body), "code": "UNKNOWN"}


def _parse_body(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # not JSON (proxy error page, truncated body); decide.py's boundary check catches it later
        return {"error": raw.decode("utf-8", "replace"), "code": "UNKNOWN"}
    return _coerce_body(parsed)


# this client never needs a redirect; refuse rather than risk Authorization crossing hosts
class _RedirectRefused(Exception):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _RedirectRefused(f"refusing to follow redirect ({code}) to {newurl}")


_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def _do_request(method: str, url: str, headers: dict, body_bytes: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body_bytes, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, _parse_body(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, _parse_body(e.read()), dict(e.headers)
    except urllib.error.URLError as e:
        raise ConnectionError(str(e)) from e
    except _RedirectRefused as e:
        raise ConnectionError(str(e)) from e
    except (OSError, http.client.HTTPException) as e:
        # socket timeouts/resets during resp.read() and incomplete reads land here, not above
        raise ConnectionError(str(e)) from e


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, MAX_WAIT_SECONDS)


def request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: dict | None = None,
    timeout: float = 30,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    statuses: list[int] = []
    last_retry_after: str | None = None
    backoff = BASE_BACKOFF_SECONDS
    total_waited = 0.0
    for attempt in range(1, max_attempts + 1):
        status, payload, resp_headers = _do_request(method, url, req_headers, body_bytes, timeout)
        if status not in RETRY_STATUSES:
            if status >= 400:
                raise HTTPError(status, payload, resp_headers)
            return payload
        statuses.append(status)
        last_retry_after = resp_headers.get("Retry-After")
        if attempt == max_attempts:
            raise RetriesExhausted(statuses, last_retry_after, backoff)
        parsed_retry_after = _parse_retry_after(last_retry_after)
        default_wait = min(backoff, MAX_WAIT_SECONDS)
        wait = parsed_retry_after if parsed_retry_after is not None else default_wait
        wait = min(wait, max(TOTAL_BACKOFF_CEILING_SECONDS - total_waited, 0.0))
        time.sleep(wait)
        total_waited += wait
        backoff *= 2
    raise RetriesExhausted(statuses, last_retry_after, backoff)


def post(url: str, headers: dict | None, body: dict, timeout: float = 30) -> dict:
    return request("POST", url, headers=headers, body=body, timeout=timeout)


def get(url: str, headers: dict | None = None, timeout: float = 10) -> dict:
    return request("GET", url, headers=headers, timeout=timeout)
