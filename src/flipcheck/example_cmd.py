import argparse
import json
import sys
from importlib import resources
from pathlib import Path

from flipcheck.octomind import OCTOMIND_REQUEST
from flipcheck.runner import run_command

BUNDLED_FIXTURE = "fixtures/example-laya-en"
_DEMO_EXIT_CODES = (0, 1, 3)  # normal verdict outcomes; anything else is a real fixture bug
# D13 (pm-gate-2, carried to TEST): the bridge from the demo to the reader's own agent
BRIDGE_LINE = (
    "Test your own agent: save its /v1/systemone body as JSON, then\n"
    "flipcheck run <file> (README: getting request.json)"
)


def _replay_args(request_path: Path, fixture_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        request_path=str(request_path), untrusted=None, repeat=2, model=None, base_url=None,
        backend=None, confidence_min=None, payloads=None, json=False, record=None,
        replay=str(fixture_dir),
    )


def cmd_example() -> int:
    path = Path("request.json")
    if path.exists():
        # D12: never clobber a request the reader may have captured from their own agent
        print(
            f"flipcheck: {path} already exists; not overwriting it.\n"
            f"See the existing file, or run it: flipcheck run {path}",
            file=sys.stderr,
        )
        return 0
    path.write_text(json.dumps(OCTOMIND_REQUEST, indent=2) + "\n")
    print(f"wrote {path} (the Octomind case: previous_tool_output, arguments.query)")
    print()

    with resources.as_file(resources.files("flipcheck").joinpath(BUNDLED_FIXTURE)) as fixture_dir:
        exit_code = run_command(_replay_args(path, fixture_dir))
    # D23: the demo always exits 0 on success; a genuine error (broken fixture) still surfaces
    if exit_code not in _DEMO_EXIT_CODES:
        return exit_code
    print()
    print(BRIDGE_LINE)
    return 0
