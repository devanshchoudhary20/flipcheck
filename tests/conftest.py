import argparse

# the one place every runner-level test builds a run_command Namespace, so a new flag
# only needs a default added here instead of in every test file
_DEFAULTS = dict(
    request_path=None, untrusted=None, repeat=2, model=None, base_url=None, backend=None,
    confidence_min=None, payloads=None, json=False, record=None, replay=None,
)


def make_run_args(**overrides) -> argparse.Namespace:
    return argparse.Namespace(**{**_DEFAULTS, **overrides})


def assert_max_line_width(text: str, limit: int = 80) -> None:
    # TEST fix 3: every error screen's message must fit a plain 80-column terminal
    for line in text.splitlines():
        assert len(line) <= limit, f"line is {len(line)} cols (> {limit}): {line!r}"
