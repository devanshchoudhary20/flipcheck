import os
import re
import sys

# ESC gets its own visible marker so a tampered label still reads as tampered, not vanished
_ESC = "\x1b"
_ESC_MARKER = "␛"
# the rest of C0/C1 (BEL and friends, plus \n/\t) become a space, never deleted, so words don't fuse
_OTHER_CONTROL_RE = re.compile(r"[\x00-\x1a\x1c-\x1f\x80-\x9f]")
_WHITESPACE_RUN_RE = re.compile(r" {2,}")

_ROLES = {
    "muted": "\x1b[2m",
    "header": "\x1b[1m",
}
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
# D7 (TEST): hue alone fails AA on a real light theme; weight carries the word, a marker the hue
_MARKER = "■"
_MARKER_HUE = {
    "danger": "\x1b[31m",
    "warning": "\x1b[33m",
    "success": "\x1b[32m",
}


def _tty() -> bool:
    return sys.stdout.isatty()


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return _tty()


def sanitize(text):
    # non-str falls through untouched so callers' `x or default` fallback checks still work
    if not isinstance(text, str):
        return text
    replaced = _OTHER_CONTROL_RE.sub(" ", text.replace(_ESC, _ESC_MARKER))
    return _WHITESPACE_RUN_RE.sub(" ", replaced)


def colorize(text: str, role: str) -> str:
    if not _color_enabled():
        return text
    code = _ROLES.get(role)
    if not code:
        return text
    return f"{code}{text}{_RESET}"


def verdict_word(text: str, role: str) -> str:
    # screens.md: NO_COLOR or a non-TTY means no escape codes at all, not even bold
    if not _color_enabled():
        return text
    hue = _MARKER_HUE.get(role)
    marker = f"{hue}{_MARKER}{_RESET} " if hue else "  "
    return f"{marker}{_BOLD}{text}{_RESET}"
