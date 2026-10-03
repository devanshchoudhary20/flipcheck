import pytest
from conftest import assert_max_line_width

from flipcheck.backend import BACKEND_TABLE, Backend, BackendError, hosted_notice, resolve_backend


def _ok(url, headers=None):
    return {"models": []}


def _unreachable(url, headers=None):
    raise ConnectionError("refused")


def test_base_url_flag_wins_outright(monkeypatch):
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    backend = resolve_backend("http://127.0.0.1:9999", None, get_fn=_unreachable)
    assert backend.base_url == "http://127.0.0.1:9999"
    assert backend.is_local is True


def test_loopback_wins_over_env_keys(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")
    backend = resolve_backend(None, None, get_fn=_ok)
    assert backend.is_local is True
    assert backend.label == "local"


def test_falls_back_to_typesafe_base_url(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://stub.example.com")
    backend = resolve_backend(None, None, get_fn=_unreachable)
    assert backend.base_url == "https://stub.example.com"
    assert backend.is_local is False


def test_falls_back_to_ai_gateway_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-key")
    backend = resolve_backend(None, None, get_fn=_unreachable)
    assert backend.model == "typesafe-ai/jev"
    assert backend.headers["Authorization"] == "Bearer gw-key"


def test_falls_back_to_typesafe_api_key_defaults_to_jev_latest(monkeypatch):
    # bug fix: TypeSafe's own API takes "jev-latest", not the local ollaya id or the
    # Vercel gateway's provider/model id (docs.typesafe.ai/introduction/quickstart.md)
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    backend = resolve_backend(None, None, get_fn=_unreachable)
    assert backend.base_url == "https://api.typesafe.ai"
    assert backend.model == "jev-latest"
    assert backend.headers["Authorization"] == "Bearer ts-key"


def test_raises_when_nothing_resolves(monkeypatch):
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(BackendError) as exc:
        resolve_backend(None, None, get_fn=_unreachable)
    assert_max_line_width(exc.value.message)


def test_loopback_wins_over_ai_gateway_key_too(monkeypatch):
    # D3's own case: AI_GATEWAY_API_KEY is routinely set for Vercel AI SDK users, so a
    # reachable local server, not the key, must decide the backend
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-key")
    backend = resolve_backend(None, None, get_fn=_ok)
    assert backend.is_local is True
    assert backend.label == "local"


def test_hosted_notice_names_the_host_and_how_to_force_local():
    backend = Backend(
        "https://ai-gateway.vercel.sh/typesafe", "typesafe-ai/jev", "ai-gateway.vercel.sh",
        False, {},
    )
    notice = hosted_notice(backend)
    assert "ai-gateway.vercel.sh" in notice
    assert "--base-url http://127.0.0.1:11435" in notice
    assert_max_line_width(notice)


def test_hosted_notice_is_none_for_local_backend():
    backend = Backend("http://127.0.0.1:11435", "laya:en", "local", True, {})
    assert hosted_notice(backend) is None


def test_default_repeats_is_two_local_three_hosted():
    local = Backend("http://127.0.0.1:11435", "laya:en", "local", True, {})
    hosted = Backend("https://api.typesafe.ai", "laya:en", "api.typesafe.ai", False, {})
    assert local.default_repeats == 2
    assert hosted.default_repeats == 3


def test_backend_table_lists_local_first_and_marked_default():
    assert BACKEND_TABLE[0].name == "local ollaya (default)"
    assert {spec.name for spec in BACKEND_TABLE} == {
        "local ollaya (default)", "custom TypeSafe-compatible endpoint",
        "Vercel AI Gateway", "TypeSafe direct",
    }


def test_backend_flag_local_reaches_loopback_even_with_a_hosted_key_set(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-key")
    backend = resolve_backend(None, None, backend_flag="local", get_fn=_ok)
    assert backend.is_local is True
    assert backend.label == "local"


def test_backend_flag_local_fails_like_screen_6_when_unreachable(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    with pytest.raises(BackendError) as excinfo:
        resolve_backend(None, None, backend_flag="local", get_fn=_unreachable)
    assert "no backend reachable" in excinfo.value.message


def test_backend_flag_vercel_reaches_the_gateway_even_with_ollaya_running(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-key")
    # get_fn=_ok would normally mean loopback is reachable; --backend vercel skips that check
    backend = resolve_backend(None, None, backend_flag="vercel", get_fn=_ok)
    assert backend.base_url == "https://ai-gateway.vercel.sh/typesafe"
    assert backend.model == "typesafe-ai/jev"
    assert backend.headers["Authorization"] == "Bearer gw-key"
    assert backend.is_local is False


def test_backend_flag_vercel_without_the_key_names_the_env_var(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    with pytest.raises(BackendError) as excinfo:
        resolve_backend(None, None, backend_flag="vercel", get_fn=_ok)
    assert "AI_GATEWAY_API_KEY" in excinfo.value.message
    assert "nothing was sent" in excinfo.value.message


def test_backend_flag_typesafe_reaches_typesafe_even_with_ollaya_running(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    backend = resolve_backend(None, None, backend_flag="typesafe", get_fn=_ok)
    assert backend.base_url == "https://api.typesafe.ai"
    assert backend.model == "jev-latest"
    assert backend.headers["Authorization"] == "Bearer ts-key"
    assert backend.is_local is False


def test_backend_flag_typesafe_without_the_key_names_the_env_var(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(BackendError) as excinfo:
        resolve_backend(None, None, backend_flag="typesafe", get_fn=_ok)
    assert "TYPESAFE_API_KEY" in excinfo.value.message
    assert "nothing was sent" in excinfo.value.message


def test_base_url_still_wins_over_backend_flag(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-key")
    backend = resolve_backend(
        "http://127.0.0.1:9999", None, backend_flag="vercel", get_fn=_unreachable
    )
    assert backend.base_url == "http://127.0.0.1:9999"
