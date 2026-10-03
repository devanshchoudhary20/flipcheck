import sys
import time
from datetime import date
from pathlib import Path

from flipcheck import __version__, http, record
from flipcheck.backend import DEFAULT_MODEL, Backend, hosted_notice, resolve_backend
from flipcheck.compare import (
    PayloadRun,
    Verdict,
    classify,
    compute_noise,
    evaluate_field,
    target_label,
    target_value,
)
from flipcheck.decide import DecisionError, call_systemone, extract_cost
from flipcheck.dotted import inject_by_type, remove_path
from flipcheck.errors import FlipcheckError
from flipcheck.payloads import load_payloads
from flipcheck.render.json import render_json
from flipcheck.render.progress import ProgressReporter, interrupted_message
from flipcheck.render.table import (
    all_fields_brittle,
    render_brittle_banner,
    render_footer,
    render_header,
    render_replay_banner,
    render_verdict_table,
)
from flipcheck.request_file import load_request, select_question
from flipcheck.untrusted import resolve_untrusted

CALLS_PER_PAYLOAD = 2  # one inject call, one paired-control call


def _build_payload(model: str, state: dict, question_id: str, question: dict) -> dict:
    return {"model": model, "state": state, "questions": {question_id: question}}


def _exit_code(field_verdicts) -> int:
    verdicts = [fv.verdict for fv in field_verdicts]
    if any(v in (Verdict.DONT_SEND, Verdict.HARDEN) for v in verdicts):
        return 1
    if any(v == Verdict.BRITTLE for v in verdicts):
        return 3
    return 0


def _check_replay_matches(
    fixture_dir: Path, meta: dict, model: str, request: dict, question_id: str, question: dict
):
    recorded_hash = meta.get("request_hash")
    if not recorded_hash:
        return
    actual_hash = record.request_hash(
        _build_payload(model, request["state"], question_id, question)
    )
    if actual_hash != recorded_hash:
        raise record.ReplayMissError(
            record.request_mismatch_message(fixture_dir, recorded_hash, actual_hash)
        )


def _resolve_backend_and_post(args, request: dict, question_id: str, question: dict):
    # chunk 3: record/replay are a backend the runner calls through, not a parallel pipeline
    if args.replay:
        fixture_dir = Path(args.replay)
        meta = record.read_meta(fixture_dir)
        model = args.model or meta.get("model") or DEFAULT_MODEL
        # the fixture's own meta names what actually produced the recording, not "local"
        label = meta.get("backend") or "local"
        backend = Backend(f"replay:{fixture_dir}", model, label, label == "local", {})
        _check_replay_matches(fixture_dir, meta, model, request, question_id, question)
        return backend, record.make_replaying_post(fixture_dir), meta

    backend = resolve_backend(args.base_url, args.model, getattr(args, "backend", None))
    post_fn = http.post
    if args.record:
        fixture_dir = Path(args.record)
        record.ensure_fixture_dir(fixture_dir)
        post_fn = record.make_recording_post(fixture_dir, post_fn)
    return backend, post_fn, None


def run_command(args) -> int:
    try:
        request = load_request(args.request_path)
        untrusted_paths = resolve_untrusted(request, args.untrusted, args.request_path)
        question_id, question = select_question(request["questions"])
        backend, post_fn, replay_meta = _resolve_backend_and_post(
            args, request, question_id, question
        )
        corpus = load_payloads(args.payloads)
    except FlipcheckError as e:
        print(e.message, file=sys.stderr)
        return e.exit_code

    notice = hosted_notice(backend)
    if notice:
        print(notice, file=sys.stderr)

    # chunk 4 default; cli.py's --repeat type= validator already rejects < 1, no clamp needed
    repeats = args.repeat if args.repeat is not None else backend.default_repeats
    total_calls = repeats + len(untrusted_paths) * (1 + CALLS_PER_PAYLOAD * len(corpus))
    # screens.md's lifecycle and screen 11 show no loading state for a replay: nothing is called
    progress = None if args.replay else ProgressReporter(total_calls, backend.model, backend.label)
    if progress:
        progress.start()
    calls_made = 0
    total_cost = 0.0
    cost_seen = False

    def call(state: dict, call_note: str) -> dict:
        nonlocal calls_made, total_cost, cost_seen
        payload = _build_payload(backend.model, state, question_id, question)
        calls_made += 1
        call_label = f"{calls_made}/{total_calls}[{call_note}]"
        started = time.monotonic()
        response = call_systemone(backend, payload, call_label=call_label, post_fn=post_fn)
        if progress:
            progress.tick(time.monotonic() - started)
        cost = extract_cost(response)
        if cost is not None:
            cost_seen = True
            total_cost += cost
        return response["answers"][question_id]

    try:
        baseline_answers = [call(request["state"], "baseline") for _ in range(repeats)]

        question_type = question.get("type")
        label = target_label(baseline_answers[0], question_type)
        baseline_values = [target_value(a, question_type, label) for a in baseline_answers]
        noise = compute_noise(baseline_values)
        baseline_answer = baseline_answers[0]

        def classify_after(state: dict, call_note: str):
            after_answer = call(state, call_note)
            return classify(
                question_type, label, baseline_answer, after_answer, noise, args.confidence_min
            )

        rows = []
        for path in untrusted_paths:
            remove_result = classify_after(remove_path(request, path)["state"], f"remove {path}")

            runs = []
            for entry in corpus:
                payload_state = inject_by_type(request, path, entry.text)["state"]
                payload_result = classify_after(payload_state, f"inject {path} {entry.id}")
                control_state = inject_by_type(request, path, entry.control_text)["state"]
                control_result = classify_after(control_state, f"control {path} {entry.control_id}")
                runs.append(
                    PayloadRun(
                        entry.id, entry.text, entry.control_id, entry.control_text,
                        payload_result, control_result,
                    )
                )

            rows.append((path, evaluate_field(remove_result, runs, noise)))
    except (DecisionError, record.ReplayMissError, record.RecordError) as e:
        if progress:
            progress.finish()
        print(e.message, file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        message = (
            progress.interrupted_message()
            if progress
            else interrupted_message(calls_made, total_calls)
        )
        print(f"\n{message}", file=sys.stderr)
        return 130

    if progress:
        progress.finish()

    if args.record:
        try:
            record.write_meta(
                Path(args.record),
                flipcheck_version=__version__,
                model=backend.model,
                backend_label=backend.label,
                ollaya_version=record.ollaya_version(),
                recorded_at=date.today().isoformat(),
                request_hash_hex=record.request_hash(
                    _build_payload(backend.model, request["state"], question_id, question)
                ),
            )
        except record.RecordError as e:
            print(e.message, file=sys.stderr)
            return e.exit_code

    target_display = label if question_type == "choice" else "noul"
    exit_code = _exit_code(fv for _, fv in rows)
    cost = total_cost if cost_seen else None

    if args.json:
        print(render_json(
            __version__, backend.model, backend.label, target_display, baseline_values[0],
            noise, repeats, rows, exit_code, cost,
        ))
        return exit_code

    header = render_header(
        __version__,
        backend.model,
        backend.label,
        target_display,
        baseline_values[0],
        noise,
        repeats,
        cost,
    )
    all_brittle = all_fields_brittle(rows)
    print(header)
    if replay_meta is not None:
        print(render_replay_banner(replay_meta, backend.model))
    print()
    if all_brittle:
        print(render_brittle_banner(backend.model))
        print()
    print(render_verdict_table(rows, label, backend.model, args.confidence_min, all_brittle))
    print()
    print(render_footer(len(corpus)))
    return exit_code
