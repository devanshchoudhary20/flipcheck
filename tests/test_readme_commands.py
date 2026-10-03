import re
import shlex
from pathlib import Path

import pytest

from flipcheck.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
# a real invocation, not an output line that happens to start with "flipcheck" (e.g. the
# "flipcheck 0.1.0 · laya:en ..." header in a verdict-table example block)
_KNOWN_FIRST_ARGS = {"run", "example", "--version", "--help"}


# F1: `uvx` and `pipx run` both run the installed console script by name, same subcommand
# after it; the launcher prefix is stripped so the parser sees "flipcheck <subcommand> ..."
_RUNNER_PREFIXES = ((), ("uvx",), ("pipx", "run"))


def _flipcheck_start(tokens: list[str]) -> int | None:
    for prefix in _RUNNER_PREFIXES:
        n = len(prefix)
        if tuple(tokens[:n]) != prefix:
            continue
        rest = tokens[n:]
        if len(rest) >= 2 and rest[0] == "flipcheck" and rest[1] in _KNOWN_FIRST_ARGS:
            return n
    return None


def _flipcheck_commands(markdown: str) -> list[str]:
    commands = []
    for block in _FENCE_RE.findall(markdown):
        for line in block.splitlines():
            for segment in line.strip().lstrip("$").split("&&"):
                segment = segment.strip()
                tokens = segment.split()
                start = _flipcheck_start(tokens)
                if start is not None:
                    commands.append(" ".join(tokens[start:]))
    return commands


def _readme_commands() -> list[str]:
    markdown = (REPO_ROOT / "README.md").read_text()
    return _flipcheck_commands(markdown)


def test_readme_has_at_least_one_flipcheck_command():
    assert len(_readme_commands()) >= 2


def test_uvx_prefixed_command_is_recognized_and_normalized():
    markdown = "```\nuvx flipcheck example\n```"
    assert _flipcheck_commands(markdown) == ["flipcheck example"]


def test_pipx_run_prefixed_command_is_recognized_and_normalized():
    markdown = "```\npipx run flipcheck run request.json\n```"
    assert _flipcheck_commands(markdown) == ["flipcheck run request.json"]


def test_readme_leads_with_uvx():
    markdown = (REPO_ROOT / "README.md").read_text()
    first_fence = _FENCE_RE.findall(markdown)[0]
    assert "uvx flipcheck example" in first_fence


@pytest.mark.parametrize("command", _readme_commands())
def test_readme_command_parses_with_the_real_argparse_parser(command):
    tokens = shlex.split(command)[1:]
    parser = build_parser()
    args = parser.parse_args(tokens)
    if tokens and tokens[0] not in ("--version", "--help"):
        assert args.command == tokens[0]
