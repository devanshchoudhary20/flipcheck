import shutil
import sys
import time

from flipcheck.render.color import sanitize


def terminal_width() -> int:
    # 0, negative or missing all read as "unknown" (seen on 0x0 ptys and many CI runners)
    columns = shutil.get_terminal_size(fallback=(80, 24)).columns
    return columns if columns > 0 else 80


def render_loading_line(
    done: int, total: int, model: str, backend_label: str, avg_seconds: float | None
) -> str:
    if avg_seconds is None:
        rate, remaining = "estimating…", ""
    else:
        rate = f"~{avg_seconds:.1f}s/call"
        left = avg_seconds * max(total - done, 0)
        remaining = f", ~{left:.0f}s left"
    base = (
        f"Running {done}/{total} calls against {sanitize(model)} "
        f"({sanitize(backend_label)}), {rate}{remaining}"
    )
    with_suffix = f"{base}  (Ctrl-C to stop)"
    # D4: fits 80 columns so the \r rewrite works; drop the suffix first, then clip the line itself
    width = terminal_width() - 1
    if len(with_suffix) <= width:
        return with_suffix
    if len(base) <= width:
        return base
    return base[: max(width - 1, 0)] + "…"


def start_line(total: int, model: str, backend_label: str) -> str:
    return (
        f"flipcheck: running {total} calls against "
        f"{sanitize(model)} ({sanitize(backend_label)})..."
    )


def done_line(elapsed_seconds: float) -> str:
    return f"flipcheck: done in {elapsed_seconds:.1f}s"


def interrupted_message(done: int, total: int) -> str:
    return f"flipcheck: interrupted, {done}/{total} calls made, nothing recorded"


class ProgressReporter:
    def __init__(self, total: int, model: str, backend_label: str, stream=None):
        self.total = total
        self.model = model
        self.backend_label = backend_label
        self.stream = stream or sys.stderr
        self.done = 0
        self.durations: list[float] = []
        # D4: the TTY test is stderr's own isatty, since this line writes to stderr
        self.is_tty = self.stream.isatty()
        self._started_at = time.monotonic()

    def start(self) -> None:
        if not self.is_tty:
            self.stream.write(start_line(self.total, self.model, self.backend_label) + "\n")
            self.stream.flush()

    def tick(self, duration: float) -> None:
        self.done += 1
        self.durations.append(duration)
        if self.is_tty:
            avg = sum(self.durations) / len(self.durations) if len(self.durations) >= 2 else None
            line = render_loading_line(self.done, self.total, self.model, self.backend_label, avg)
            self.stream.write("\r" + line + " " * 4)
            self.stream.flush()

    def finish(self) -> None:
        if self.is_tty:
            self.stream.write("\r" + " " * terminal_width() + "\r")
        else:
            elapsed = time.monotonic() - self._started_at
            self.stream.write(done_line(elapsed) + "\n")
        self.stream.flush()

    def interrupted_message(self) -> str:
        return interrupted_message(self.done, self.total)
