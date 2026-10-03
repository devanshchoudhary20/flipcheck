import argparse
import sys

from flipcheck import __version__
from flipcheck.backend import BACKEND_CHOICES
from flipcheck.example_cmd import cmd_example
from flipcheck.runner import run_command


def _repeat_count(value: str) -> int:
    # argparse exits 2 on ArgumentTypeError; no silent clamp to 1 left in the runner
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: '{value}'") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError("--repeat must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flipcheck",
        description="Test which fields in an agent decision request an attacker can move.",
    )
    parser.add_argument("--version", action="version", version=f"flipcheck {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("example", help="write a sample request (the Octomind case)")

    run_parser = subparsers.add_parser("run", help="run a request against a backend")
    run_parser.add_argument("request_path")
    run_parser.add_argument(
        "--untrusted", action="append", help="dotted path to an untrusted field, repeatable"
    )
    run_parser.add_argument(
        "--repeat",
        type=_repeat_count,
        default=None,
        help="baseline repeats for the noise floor (default: 2, 3 on a hosted backend)",
    )
    run_parser.add_argument("--model", help="model to test (default: laya:en)")
    run_parser.add_argument("--base-url", help="backend base URL, overrides auto-detection")
    run_parser.add_argument(
        "--backend",
        choices=BACKEND_CHOICES,
        help="force a backend by name instead of auto-detecting (vercel needs "
        "AI_GATEWAY_API_KEY, typesafe needs TYPESAFE_API_KEY)",
    )
    run_parser.add_argument(
        "--confidence-min",
        type=float,
        default=None,
        help="treat crossing this confidence as a flip",
    )
    run_parser.add_argument(
        "--payloads", help="path to a custom payload corpus JSON file (default: the bundled one)"
    )
    run_parser.add_argument(
        "--json", action="store_true", help="print the verdict report as JSON on stdout"
    )
    fixture_group = run_parser.add_mutually_exclusive_group()
    fixture_group.add_argument(
        "--record", metavar="DIR", help="record every backend response into this directory"
    )
    fixture_group.add_argument(
        "--replay", metavar="DIR", help="replay backend responses from this directory, no network"
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "example":
        return cmd_example()
    if args.command == "run":
        return run_command(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
