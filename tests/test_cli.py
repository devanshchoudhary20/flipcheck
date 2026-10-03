import pytest

from flipcheck.cli import build_parser


def test_help_exits_clean():
    parser = build_parser()
    assert parser.prog == "flipcheck"


def test_repeat_zero_rejected_with_exit_code_2(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["run", "request.json", "--repeat", "0"])
    assert exc.value.code == 2
    assert "--repeat must be at least 1" in capsys.readouterr().err


def test_repeat_negative_rejected_with_exit_code_2(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["run", "request.json", "--repeat", "-3"])
    assert exc.value.code == 2
    assert "--repeat must be at least 1" in capsys.readouterr().err


def test_repeat_one_is_accepted():
    parser = build_parser()
    args = parser.parse_args(["run", "request.json", "--repeat", "1"])
    assert args.repeat == 1
