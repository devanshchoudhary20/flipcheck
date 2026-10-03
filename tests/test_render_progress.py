import os

from flipcheck.render.progress import terminal_width


def _stub_terminal_size(columns):
    return lambda fallback=(80, 24): os.terminal_size((columns, 24))


def test_terminal_width_treats_zero_as_unknown_and_falls_back_to_80(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", _stub_terminal_size(0))
    assert terminal_width() == 80


def test_terminal_width_treats_negative_as_unknown_and_falls_back_to_80(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", _stub_terminal_size(-5))
    assert terminal_width() == 80


def test_terminal_width_keeps_a_narrow_but_positive_value(monkeypatch):
    # COLUMNS=4: real, not "unknown"; the crash this caused lived downstream (TEST fix 2)
    monkeypatch.setattr("shutil.get_terminal_size", _stub_terminal_size(4))
    assert terminal_width() == 4


def test_terminal_width_keeps_a_normal_value(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", _stub_terminal_size(60))
    assert terminal_width() == 60
