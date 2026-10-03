import json

from flipcheck.compare import FieldVerdict, Outcome, Verdict
from flipcheck.render.table import field_action


def _remove_dict(field_verdict: FieldVerdict) -> dict:
    return {"outcome": field_verdict.remove_result.outcome.value}


def _inject_dict(field_verdict: FieldVerdict) -> dict:
    worst = field_verdict.worst
    result = worst.payload_result
    # screens.md fallback ledger: BRITTLE carries brittle_rate "instead of the per-payload keys"
    if result.outcome == Outcome.STABLE or field_verdict.verdict == Verdict.BRITTLE:
        return {"outcome": result.outcome.value}
    return {
        "outcome": result.outcome.value,
        "payload_id": worst.payload_id,
        "payload": worst.payload_text,
        "before": result.before,
        "after": result.after,
    }


def _control_dict(field_verdict: FieldVerdict) -> dict:
    worst = field_verdict.worst
    return {"outcome": worst.control_result.outcome.value, "control_id": worst.control_id}


def _field_dict(model: str, path: str, field_verdict: FieldVerdict) -> dict:
    entry = {
        "path": path,
        "remove": _remove_dict(field_verdict),
        "inject": _inject_dict(field_verdict),
        "control": _control_dict(field_verdict),
        "verdict": field_verdict.verdict.value,
        "action": field_action(model, field_verdict),
    }
    if field_verdict.verdict == Verdict.BRITTLE:
        entry["brittle_rate"] = field_verdict.controls_moved / field_verdict.controls_total
    return entry


def build_report(
    version: str, model: str, backend_label: str, target: str, value: float,
    noise: float | None, repeats: int, rows: list[tuple[str, FieldVerdict]], exit_code: int,
    cost: float | None = None,
) -> dict:
    baseline = {"target": target, "value": value, "repeats": repeats}
    if noise is not None:
        baseline["noise"] = noise
    report = {
        "flipcheck_version": version,
        "model": model,
        "backend": backend_label,
        "baseline": baseline,
        "fields": [_field_dict(model, path, field_verdict) for path, field_verdict in rows],
        "exit_code": exit_code,
    }
    if cost is not None:
        report["cost"] = cost
    return report


def render_json(*args, **kwargs) -> str:
    # screen 10: no color codes regardless of NO_COLOR or TTY, so this never goes through colorize
    return json.dumps(build_report(*args, **kwargs), indent=2)
