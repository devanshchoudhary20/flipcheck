import re
import textwrap

from flipcheck.dotted import path_exists
from flipcheck.errors import FlipcheckError
from flipcheck.render.color import sanitize

DEFAULT_PATTERNS = [
    "tool_output",
    "tool_result",
    "previous_tool_output",
    "observation",
    "retrieved",
    "documents",
    "context",
    "email",
    "body",
    "page",
    "result",
]
_DEFAULT_REGEX = re.compile("|".join(re.escape(p) for p in DEFAULT_PATTERNS), re.IGNORECASE)


class UntrustedError(FlipcheckError):
    pass


def default_detect(state) -> list[str]:
    if not isinstance(state, dict):
        return []
    return [f"state.{key}" for key in state if _DEFAULT_REGEX.search(key)]


def _format_keys(state) -> str:
    if not isinstance(state, dict) or not state:
        return "(none)"
    return ", ".join(sanitize(key) for key in state.keys())


def _points_inside_state(path: str) -> bool:
    # c: "state" itself and anything outside it isn't an untrusted field, it's injectable
    return path.startswith("state.") and len(path) > len("state.")


def _no_untrusted_message(request_path: str, state) -> str:
    example_key = next(iter(state), "field") if isinstance(state, dict) and state else "field"
    patterns_line = "None matched the default patterns ({}).".format(", ".join(DEFAULT_PATTERNS))
    wrapped = textwrap.fill(patterns_line, width=78)
    return (
        f"flipcheck: no untrusted fields detected in {request_path}\n\n"
        f'Top-level keys in "state": {_format_keys(state)}\n'
        f"{wrapped}\n\n"
        "Mark fields explicitly:\n"
        f"  flipcheck run {request_path} --untrusted state.{example_key}\n"
        f'  or add "_untrusted": ["state.{example_key}"] to the request file.'
    )


def resolve_untrusted(
    request: dict, cli_untrusted: list[str] | None, request_path: str
) -> list[str]:
    state = request.get("state")

    if cli_untrusted:
        paths, source = list(cli_untrusted), "--untrusted"
    else:
        file_list = request.get("_untrusted")
        if file_list:
            paths, source = list(file_list), "_untrusted"
        else:
            paths, source = default_detect(state), "default"

    for path in paths:
        if not _points_inside_state(path) or not path_exists(request, path):
            raise UntrustedError(
                f'flipcheck: {source} "{path}" not found. Top-level keys in "state":\n'
                f"{_format_keys(state)}"
            )

    if not paths:
        raise UntrustedError(_no_untrusted_message(request_path, state))

    return paths
