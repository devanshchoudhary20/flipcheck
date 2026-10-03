import textwrap

from flipcheck.compare import (
    BRITTLE_CONTROL_MOVES,
    BrittleReason,
    Classification,
    FieldVerdict,
    Outcome,
    Verdict,
    gate_range,
)
from flipcheck.record import replay_sentence
from flipcheck.render.color import colorize, sanitize, verdict_word
from flipcheck.render.progress import terminal_width

FIELD_MAX_WIDTH = 40
FIELD_MIN_WIDTH = len("FIELD")
OUTCOME_WIDTH = 7
VERDICT_WIDTH = len("DON'T SEND") + 1
QUOTE_MAX = 72
DETAIL_WRAP_MAX = 76
WRAP_MIN_WIDTH = 40

_VERDICT_ROLE = {
    Verdict.DONT_SEND: "danger",
    Verdict.HARDEN: "warning",
    Verdict.OK: "success",
    Verdict.INERT: "muted",
    Verdict.BRITTLE: "muted",
}

# D2: the plan's own action sentence per verdict, printed on every row, not only in --json
_ACTIONS = {
    Verdict.DONT_SEND: (
        "This field does not inform the decision, yet text in it moves the verdict. "
        "Remove it before calling."
    ),
    Verdict.HARDEN: (
        "The decision needs this field and attacker text in it moves the verdict. "
        "Quote it as data, split it into signals, add a deterministic check."
    ),
    Verdict.INERT: "Neither informs nor moves. Drop it; send only the fields the question needs.",
}

_OK_ACTION_TEMPLATE = (
    "Informs the decision; resisted {n} payloads. Its current text moves the verdict: if "
    "someone outside your system writes it, read it before trusting this row."
)


def field_width(paths: list[str]) -> int:
    longest = max((len(path) for path in paths), default=FIELD_MIN_WIDTH)
    return max(min(longest, FIELD_MAX_WIDTH), FIELD_MIN_WIDTH)


def truncate_field(path: str, width: int) -> str:
    # D5: keep the tail (the most specific part of a dotted path), truncate the head
    path = sanitize(path)
    if len(path) <= width:
        return path
    return "…" + path[-(width - 1) :]


def _repeats_text(repeats: int) -> str:
    return f"{repeats} run" if repeats == 1 else f"{repeats} runs"


def _format_cost(cost: float) -> str:
    return f"${cost:.4f}"


def render_header(
    version: str,
    model: str,
    backend_label: str,
    target: str,
    value: float,
    noise: float | None,
    repeats: int,
    cost: float | None = None,
) -> str:
    noise_text = f"{noise:.2f}" if noise is not None else "n/a"
    # cost only ever appears when the backend's own response carried it; never a $0.00 placeholder
    cost_clause = f" · cost {_format_cost(cost)}" if cost is not None else ""
    repeats_text = _repeats_text(repeats)
    line = (
        f"flipcheck {version} · {sanitize(model)} · {sanitize(backend_label)} · "
        f"baseline {_target_name(target)} {value:.2f} (noise {noise_text}, {repeats_text})"
        f"{cost_clause}"
    )
    return colorize(line, "header")


def _wrap_target_width(padding: int) -> int:
    # a 0x0 pty or COLUMNS=4 must not drive textwrap.wrap's width to <= 0 (TEST fix 2)
    return max(min(terminal_width() - padding, DETAIL_WRAP_MAX), WRAP_MIN_WIDTH)


def render_replay_banner(meta: dict, model: str) -> str:
    # screen 11: bracketed, wrapped, muted; continuation lines get one leading space
    sentence = replay_sentence(meta, model)
    width = _wrap_target_width(2)
    wrapped = textwrap.wrap(sentence, width=width) or [sentence]
    lines = [f"[{wrapped[0]}", *(f" {line}" for line in wrapped[1:])]
    lines[-1] += "]"
    return colorize("\n".join(lines), "muted")


def _quote(text: str) -> str:
    text = sanitize(text)
    if len(text) > QUOTE_MAX:
        return text[: QUOTE_MAX - 3] + "..."
    return text


def _target_name(label: str | None) -> str:
    return sanitize(label) if label else "noul"


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _signed(value: float) -> str:
    return f"+{value:.2f}" if value >= 0 else f"{value:.2f}"


def _control_clause(control_result: Classification) -> str:
    # pm-gate-2 D1 ruling: the detail line prints both deltas, so the reader sees the size
    return f"its same-length control {_signed(control_result.delta)}"


def _flip_detail(label: str | None, result: Classification) -> str:
    # D21: name what the decision flipped to, not just the tracked label's own before/after
    target = _target_name(label)
    if result.after_label is not None:
        return (
            f"flipped {target} ({result.before:.2f}) -> "
            f"{sanitize(result.after_label)} ({_fmt(result.after_label_value)})"
        )
    return f"flipped {target} {result.before:.2f} -> {result.after:.2f}"

def _move_detail(label: str | None, result: Classification, confidence_min: float | None) -> str:
    # D14: state direction and the gate range on the metric the decision actually gates on
    target = _target_name(label)
    use_confidence = (
        confidence_min is not None
        and result.before_confidence is not None
        and result.after_confidence is not None
    )
    if use_confidence:
        lo, hi = gate_range(result.before_confidence, result.after_confidence)
        gate_line = f"an agent gating on confidence >= T flips for any T from {lo:.2f} to {hi:.2f}"
    else:
        lo, hi = gate_range(result.before, result.after)
        gate_line = f"an agent that gates {target} >= T flips for any T from {lo:.2f} to {hi:.2f}"
    return (
        f"moved {target} {result.before:.2f} -> {result.after:.2f} "
        f"(confidence {_fmt(result.before_confidence)} -> {_fmt(result.after_confidence)}); "
        f"{gate_line}"
    )


def _numeric_detail(label: str | None, result: Classification, confidence_min: float | None) -> str:
    if result.outcome == Outcome.FLIP:
        return _flip_detail(label, result)
    return _move_detail(label, result, confidence_min)


def _capitalize_first(text: str) -> str:
    return text[:1].upper() + text[1:]


# the ladder: laya:en (default) -> kev:0.8b (~6 GB RAM) -> kev:4b (16 GB+); `ollaya pull` only
def _brittle_advice(model: str) -> str:
    if model.startswith("laya"):
        return (
            "if you have 6 GB+ RAM, pull the next model up (`ollaya pull kev:0.8b`) and try "
            "`--model kev:0.8b`; otherwise test on the model your agent actually runs"
        )
    if model == "kev:0.8b":
        return (
            "if you have 16 GB+ RAM, pull the next model up (`ollaya pull kev:4b`) and try "
            "`--model kev:4b`; otherwise test on the model your agent actually runs"
        )
    return "test on the model your agent actually runs"


# name which clause fired: a noisy model reads differently from a payload missing its margin
def _brittle_fact(label: str | None, model: str, field_verdict: FieldVerdict) -> str:
    target = _target_name(label)
    worst = field_verdict.worst
    control = worst.control_result
    if field_verdict.brittle_reason == BrittleReason.CONTROLS_MOVED:
        verb = "flipped" if control.outcome == Outcome.FLIP else "moved"
        return (
            f"More than {BRITTLE_CONTROL_MOVES} of {field_verdict.controls_total} harmless "
            f"controls moved this field on {model} ({field_verdict.controls_moved} of "
            f'{field_verdict.controls_total}); for example, control "{_quote(worst.control_text)}" '
            f"also {verb} {target} {control.before:.2f} -> {control.after:.2f} "
            f"({_signed(control.delta)})."
        )
    payload = worst.payload_result
    return (
        f"None of the 8 payloads beat its own paired control: the worst moved {target} "
        f"{payload.before:.2f} -> {payload.after:.2f} ({_signed(payload.delta)}); "
        f"{_control_clause(control)}."
    )


def _wrap_width() -> int:
    return _wrap_target_width(4)


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, width=_wrap_width()) or [text]


# screens.md's all-BRITTLE variant: the recommendation prints once above the table, not per row
def render_brittle_banner(model: str) -> str:
    sentence = (
        f"{sanitize(model)}'s controls moved the verdict on every untrusted field in this "
        "request; injection can't be told from noise on this model. "
        f"{_capitalize_first(_brittle_advice(model))}."
    )
    wrapped = textwrap.wrap(sentence, width=_wrap_target_width(0)) or [sentence]
    return colorize("\n".join(wrapped), "muted")


# shared by the table's detail lines and --json's "action" key, one sentence per verdict
def field_action(model: str, field_verdict: FieldVerdict) -> str:
    verdict = field_verdict.verdict
    if verdict == Verdict.BRITTLE:
        return f"Injection can't be told from noise here; {_brittle_advice(model)}."
    if verdict == Verdict.OK:
        # PM ruling on D1: fold the caveat into the OK action itself, no sixth state
        return _OK_ACTION_TEMPLATE.format(n=field_verdict.controls_total)
    return _ACTIONS[verdict]


def _detail_lines(
    label: str | None,
    field_verdict: FieldVerdict,
    model: str,
    confidence_min: float | None,
    all_brittle: bool = False,
) -> list[str]:
    verdict = field_verdict.verdict
    worst = field_verdict.worst

    if verdict == Verdict.BRITTLE:
        # captain's review, chunk 2: at most two sentences, what happened then what to do
        what_happened = _brittle_fact(label, model, field_verdict)
        if all_brittle:
            # the advice already printed once in render_brittle_banner; rows keep only the fact
            return _wrap(what_happened)
        return [*_wrap(what_happened), *_wrap(field_action(model, field_verdict))]

    if verdict in (Verdict.DONT_SEND, Verdict.HARDEN):
        quote = (
            f'payload "{_quote(worst.payload_text)}" ({worst.payload_id}) · '
            f'control "{_quote(worst.control_text)}"'
        )
        base = _numeric_detail(label, worst.payload_result, confidence_min)
        numeric = f"{base}; {_control_clause(worst.control_result)}"
        return [*_wrap(quote), *_wrap(numeric), *_wrap(field_action(model, field_verdict))]

    return _wrap(field_action(model, field_verdict))


def all_fields_brittle(rows: list[tuple[str, FieldVerdict]]) -> bool:
    return bool(rows) and all(field_verdict.verdict == Verdict.BRITTLE for _, field_verdict in rows)


def render_verdict_table(
    rows: list[tuple[str, FieldVerdict]],
    label: str | None,
    model: str,
    confidence_min: float | None = None,
    all_brittle: bool = False,
) -> str:
    width = field_width([path for path, _ in rows])
    header = (
        f"{'FIELD':<{width}}  {'REMOVE':<{OUTCOME_WIDTH}}  {'INJECT':<{OUTCOME_WIDTH}}  "
        f"{'CONTROL':<{OUTCOME_WIDTH}}  {'VERDICT':<{VERDICT_WIDTH}}"
    )
    lines = [header]
    for path, field_verdict in rows:
        field_text = truncate_field(path, width)
        remove_word = field_verdict.remove_result.outcome.value
        inject_word = field_verdict.worst.payload_result.outcome.value
        control_word = field_verdict.worst.control_result.outcome.value
        verdict_role = _VERDICT_ROLE[field_verdict.verdict]
        padded_verdict = f"{field_verdict.verdict.value:<{VERDICT_WIDTH}}"
        # D7 (TEST): danger/warning/success ride a marker glyph, not hue on the word itself
        verdict_cell = (
            colorize(padded_verdict, verdict_role)
            if verdict_role == "muted"
            else verdict_word(padded_verdict, verdict_role)
        )
        row = (
            f"{field_text:<{width}}  {remove_word:<{OUTCOME_WIDTH}}  "
            f"{inject_word:<{OUTCOME_WIDTH}}  {control_word:<{OUTCOME_WIDTH}}  {verdict_cell}"
        )
        lines.append(row)
        for detail in _detail_lines(label, field_verdict, model, confidence_min, all_brittle):
            lines.append(f"    {detail}")
    return "\n".join(lines)


def render_footer(payload_count: int) -> str:
    return colorize(
        f"{payload_count} payloads and {payload_count} controls per field, not a proof. "
        "Strip untrusted fields anyway.",
        "muted",
    )
