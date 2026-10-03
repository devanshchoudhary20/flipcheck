class FlipcheckError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def read_utf8_text(path, error_cls, display=None):
    # decode at the boundary: a non-UTF-8 file reads as one clean error, never a traceback
    label = display if display is not None else str(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise error_cls(f"flipcheck: cannot read {label}: {e.strerror or e}") from e
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise error_cls(f"flipcheck: {label} is not UTF-8 text; save it as UTF-8 JSON.") from None
