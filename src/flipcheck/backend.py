import os
import urllib.parse
from dataclasses import dataclass, field

from flipcheck import http
from flipcheck.errors import FlipcheckError

DEFAULT_MODEL = "laya:en"
DEFAULT_OLLAYA_URL = "http://127.0.0.1:11435"
BACKEND_LOCAL = "local"
BACKEND_VERCEL = "vercel"
BACKEND_TYPESAFE = "typesafe"
BACKEND_CHOICES = (BACKEND_LOCAL, BACKEND_VERCEL, BACKEND_TYPESAFE)
VERCEL_GATEWAY_URL = "https://ai-gateway.vercel.sh/typesafe"
VERCEL_GATEWAY_MODEL = "typesafe-ai/jev"
TYPESAFE_DIRECT_URL = "https://api.typesafe.ai"
# docs.typesafe.ai/introduction/quickstart.md: TypeSafe's own API model id (pinned: "jev-1.13.0")
TYPESAFE_DIRECT_MODEL = "jev-latest"
# a hosted model needs more baseline repeats than a deterministic local one (bigger network jitter)
LOCAL_REPEATS = 2
HOSTED_REPEATS = 3


class BackendError(FlipcheckError):
    pass


@dataclass
class Backend:
    base_url: str
    model: str
    label: str
    is_local: bool
    headers: dict = field(default_factory=dict)

    @property
    def default_repeats(self) -> int:
        return LOCAL_REPEATS if self.is_local else HOSTED_REPEATS


@dataclass(frozen=True)
class BackendSpec:
    name: str
    how_chosen: str
    env_or_flag: str
    default_model: str
    cost: str
    repeats: str


# single source for the README's Backends table and its own parity test; local first and default
BACKEND_TABLE = [
    BackendSpec(
        name="local ollaya (default)",
        how_chosen="reachable at the loopback URL, checked first",
        env_or_flag=(
            f"`--base-url`, `--backend local`, `OLLAYA_HOST` (default `{DEFAULT_OLLAYA_URL}`)"
        ),
        default_model=f"`{DEFAULT_MODEL}`",
        cost="$0",
        repeats=str(LOCAL_REPEATS),
    ),
    BackendSpec(
        name="custom TypeSafe-compatible endpoint",
        how_chosen="no local ollaya, `TYPESAFE_BASE_URL` set",
        env_or_flag="`TYPESAFE_BASE_URL` (sends no key)",
        default_model=f"`{DEFAULT_MODEL}`",
        cost="depends on the endpoint",
        repeats=str(HOSTED_REPEATS),
    ),
    BackendSpec(
        name="Vercel AI Gateway",
        how_chosen="no local ollaya, `AI_GATEWAY_API_KEY` set",
        env_or_flag="`--backend vercel`, `AI_GATEWAY_API_KEY`",
        default_model=f"`{VERCEL_GATEWAY_MODEL}`",
        cost="~$0.001/run",
        repeats=str(HOSTED_REPEATS),
    ),
    BackendSpec(
        name="TypeSafe direct",
        how_chosen="no local ollaya, no `AI_GATEWAY_API_KEY`, `TYPESAFE_API_KEY` set",
        env_or_flag="`--backend typesafe`, `TYPESAFE_API_KEY`",
        default_model=f"`{TYPESAFE_DIRECT_MODEL}`",
        cost="$0.042/M input tokens",
        repeats=str(HOSTED_REPEATS),
    ),
]


def _host_label(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return "remote"
    if not host:
        return "remote"
    return "local" if host in ("127.0.0.1", "localhost", "::1") else host


def loopback_url() -> str:
    # D19: honour ollaya's own OLLAYA_HOST for the loopback URL
    return os.environ.get("OLLAYA_HOST") or DEFAULT_OLLAYA_URL


def _auth_headers() -> dict:
    key = os.environ.get("OLLAYA_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}


def model_names(models_response: dict) -> list[str]:
    return [m["name"] for m in models_response.get("models", [])]


def _ollaya_reachable(base_url: str, get_fn=http.get) -> bool:
    try:
        get_fn(f"{base_url}/v1/models", _auth_headers())
        return True
    except Exception:
        return False


def no_backend_message(loopback_url: str) -> str:
    return (
        f"flipcheck: no backend reachable at {loopback_url} (local ollaya) and no\n"
        "TYPESAFE_BASE_URL, AI_GATEWAY_API_KEY or TYPESAFE_API_KEY set.\n\n"
        "Get a backend, $0, no key:\n"
        "  curl -fsSL https://ollaya.dev/install.sh | sh && ollaya pull laya:en\n\n"
        "Or point at a different ollaya host or a hosted TypeSafe-compatible endpoint:\n"
        "  flipcheck run request.json --base-url http://127.0.0.1:11435\n"
        "  export AI_GATEWAY_API_KEY=...   (Vercel AI Gateway, model typesafe-ai/jev,\n"
        "    about $0.001/run)\n"
        "  export TYPESAFE_API_KEY=...     (TypeSafe direct, waitlisted)\n\n"
        "Or see a full result with nothing installed:\n"
        "  flipcheck example"
    )


def missing_key_message(backend_name: str, env_var: str) -> str:
    # not a screen-13 401: --backend named a hosted target explicitly, but nothing was sent yet
    return (
        f"flipcheck: --backend {backend_name} needs {env_var} set; nothing was sent.\n"
        f"  export {env_var}=...\n"
        f"Or drop --backend {backend_name} to use the free local ollaya default."
    )


def hosted_notice(backend: Backend) -> str | None:
    # D3: name the host first; three short lines (TEST round 2) keep the force-local command whole
    if backend.is_local:
        return None
    return (
        f"flipcheck: using hosted backend at {backend.label}\n"
        "(not the free local ollaya default).\n"
        f"Force local: flipcheck run <request> --base-url {DEFAULT_OLLAYA_URL}"
    )


def _resolve_forced_backend(
    backend_flag: str, model: str, model_flag: str | None, get_fn
) -> Backend:
    if backend_flag == BACKEND_LOCAL:
        loopback = loopback_url()
        if _ollaya_reachable(loopback, get_fn):
            return Backend(loopback, model, "local", True, _auth_headers())
        raise BackendError(no_backend_message(loopback))

    if backend_flag == BACKEND_VERCEL:
        ai_gateway_key = os.environ.get("AI_GATEWAY_API_KEY")
        if not ai_gateway_key:
            raise BackendError(missing_key_message("vercel", "AI_GATEWAY_API_KEY"))
        url = VERCEL_GATEWAY_URL
        headers = {"Authorization": f"Bearer {ai_gateway_key}"}
        return Backend(url, VERCEL_GATEWAY_MODEL, _host_label(url), False, headers)

    typesafe_api_key = os.environ.get("TYPESAFE_API_KEY")
    if not typesafe_api_key:
        raise BackendError(missing_key_message("typesafe", "TYPESAFE_API_KEY"))
    url = TYPESAFE_DIRECT_URL
    headers = {"Authorization": f"Bearer {typesafe_api_key}"}
    return Backend(url, model_flag or TYPESAFE_DIRECT_MODEL, _host_label(url), False, headers)


def resolve_backend(
    base_url_flag: str | None,
    model_flag: str | None,
    backend_flag: str | None = None,
    get_fn=http.get,
) -> Backend:
    model = model_flag or DEFAULT_MODEL

    if base_url_flag:
        url = base_url_flag.rstrip("/")
        label = _host_label(url)
        return Backend(url, model, label, label == "local", _auth_headers())

    # --backend names a target explicitly, since --base-url only ever carries OLLAYA_API_KEY
    if backend_flag:
        return _resolve_forced_backend(backend_flag, model, model_flag, get_fn)

    loopback = loopback_url()
    # D3: loopback ollaya first, then env-configured hosted backends
    if _ollaya_reachable(loopback, get_fn):
        return Backend(loopback, model, "local", True, _auth_headers())

    typesafe_base_url = os.environ.get("TYPESAFE_BASE_URL")
    if typesafe_base_url:
        url = typesafe_base_url.rstrip("/")
        return Backend(url, model, _host_label(url), False, {})

    ai_gateway_key = os.environ.get("AI_GATEWAY_API_KEY")
    if ai_gateway_key:
        url = VERCEL_GATEWAY_URL
        headers = {"Authorization": f"Bearer {ai_gateway_key}"}
        return Backend(url, VERCEL_GATEWAY_MODEL, _host_label(url), False, headers)

    typesafe_api_key = os.environ.get("TYPESAFE_API_KEY")
    if typesafe_api_key:
        # TypeSafe's own API takes "jev-latest", not the Vercel gateway's provider/model id
        url = TYPESAFE_DIRECT_URL
        headers = {"Authorization": f"Bearer {typesafe_api_key}"}
        return Backend(url, model_flag or TYPESAFE_DIRECT_MODEL, _host_label(url), False, headers)

    raise BackendError(no_backend_message(loopback))
