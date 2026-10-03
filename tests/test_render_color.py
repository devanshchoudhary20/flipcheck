from flipcheck.render.color import sanitize, verdict_word


def test_sanitize_strips_esc_and_csi_sequence():
    text = sanitize("\x1b[2K\x1b[1;32mOK")
    assert "\x1b" not in text
    assert "OK" in text


def test_sanitize_strips_osc_52_sequence():
    text = sanitize("label\x1b]52;c;Zm9v\x07done")
    assert "\x1b" not in text
    assert "\x07" not in text


def test_sanitize_strips_c1_control_characters():
    assert sanitize("a\x9bb") == "a b"


def test_sanitize_replaces_newline_and_tab_with_space_not_deletion():
    assert sanitize("line one\nline two") == "line one line two"
    assert sanitize("a\tb") == "a b"


def test_sanitize_collapses_whitespace_runs_created_by_control_chars():
    assert sanitize("a\n\n\nb") == "a b"


def test_sanitize_replaces_esc_with_visible_marker_not_removal():
    text = sanitize("\x1b[1;32mSAFE\x1b[0m")
    assert "\x1b" not in text
    assert "␛" in text
    assert "SAFE" in text


def test_sanitize_passes_through_plain_text():
    assert sanitize("state.previous_tool_output") == "state.previous_tool_output"


def test_sanitize_non_str_is_untouched_so_falsy_checks_still_work():
    assert sanitize(None) is None
    assert sanitize(0) == 0


def test_verdict_word_is_plain_outside_a_tty(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert verdict_word("DON'T SEND", "danger") == "DON'T SEND"


def test_verdict_word_is_bold_with_a_colored_marker_on_a_tty(monkeypatch):
    # D7 (TEST): the word is bold in the default foreground; only the marker carries hue
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert verdict_word("DON'T SEND", "danger") == "\x1b[31m■\x1b[0m \x1b[1mDON'T SEND\x1b[0m"


def test_verdict_word_emits_no_escape_codes_at_all_under_no_color_on_a_real_tty(monkeypatch):
    # TEST round 2: screens.md wins; NO_COLOR means zero escape codes, not "bold survives"
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    result = verdict_word("HARDEN", "warning")
    assert result == "HARDEN"
    assert "\x1b" not in result
    assert "■" not in result


def test_verdict_word_treats_an_empty_no_color_as_unset(monkeypatch):
    # no-color.org: NO_COLOR must be present AND non-empty to count as set
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "")
    result = verdict_word("HARDEN", "warning")
    assert result == "\x1b[33m■\x1b[0m \x1b[1mHARDEN\x1b[0m"
