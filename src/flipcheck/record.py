import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from flipcheck.errors import FlipcheckError
from flipcheck.render.color import sanitize

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")
_FIXTURE_WRITE_FLAGS = os.O_CREAT | os.O_TRUNC | os.O_WRONLY | os.O_NOFOLLOW
_FIXTURE_WRITE_MODE = 0o600


class ReplayMissError(FlipcheckError):
    pass


class RecordError(FlipcheckError):
    pass


def ensure_fixture_dir(fixture_dir: Path) -> None:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    # a pre-existing directory keeps its old mode unless chmod'd regardless of mkdir's own mode=
    os.chmod(fixture_dir, 0o700)


def _write_fixture_file(path: Path, text: str) -> None:
    # k: refuse a symlink at a fixture path rather than writing through it
    try:
        fd = os.open(path, _FIXTURE_WRITE_FLAGS, _FIXTURE_WRITE_MODE)
    except OSError as e:
        raise RecordError(
            f"flipcheck: refusing to write fixture {path}: {e.strerror or e}"
        ) from e
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def request_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _fixture_file(fixture_dir: Path, digest: str) -> Path:
    return fixture_dir / f"{digest}.json"


def _meta_file(fixture_dir: Path) -> Path:
    return fixture_dir / "meta.json"


def read_meta(fixture_dir: Path) -> dict:
    try:
        return json.loads(_meta_file(fixture_dir).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def write_meta(
    fixture_dir: Path, flipcheck_version: str, model: str, backend_label: str,
    ollaya_version: str | None, recorded_at: str, request_hash_hex: str,
) -> None:
    meta = {
        "flipcheck_version": flipcheck_version,
        "model": model,
        "backend": backend_label,
        "recorded_at": recorded_at,
        "request_hash": request_hash_hex,
    }
    if ollaya_version:
        meta["ollaya_version"] = ollaya_version
    _write_fixture_file(_meta_file(fixture_dir), json.dumps(meta, indent=2) + "\n")


def ollaya_version() -> str | None:
    try:
        result = subprocess.run(
            ["ollaya", "--version"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _VERSION_RE.search(result.stdout + result.stderr)
    return match.group(1) if match else None


def request_mismatch_message(fixture_dir: Path, recorded_hash: str, actual_hash: str) -> str:
    # catch a whole-fixture mismatch once, up front, instead of one miss per call
    return (
        f"flipcheck: {fixture_dir} was recorded for a different request "
        f"(hash {recorded_hash[:8]}..., this request hashes to {actual_hash[:8]}...).\n"
        "Record a fixture for this request:\n"
        f"  flipcheck run request.json --record {fixture_dir}"
    )


def replay_miss_message(fixture_dir: Path, digest: str) -> str:
    # screen 12: name the missing call and how to re-record, never fall back to a live backend
    return (
        f"flipcheck: this request is not recorded in {fixture_dir} (hash {digest[:8]}...).\n"
        "Run it live and record it:\n"
        f"  flipcheck run request.json --record {fixture_dir}"
    )


def make_recording_post(fixture_dir: Path, post_fn):
    def recording_post(url, headers, body):
        response = post_fn(url, headers, body)
        _write_fixture_file(
            _fixture_file(fixture_dir, request_hash(body)), json.dumps(response, indent=2) + "\n"
        )
        return response

    return recording_post


def _corrupt_fixture_message(fixture_dir: Path, path: Path, error: Exception) -> str:
    # a recorded call that is unreadable must read as clearly as a replay miss, never fall back
    return (
        f"flipcheck: fixture {path} is corrupt or unreadable ({error}).\n"
        "Re-record it:\n"
        f"  flipcheck run request.json --record {fixture_dir}"
    )


def make_replaying_post(fixture_dir: Path):
    def replaying_post(url, headers, body):
        digest = request_hash(body)
        path = _fixture_file(fixture_dir, digest)
        if not path.exists():
            raise ReplayMissError(replay_miss_message(fixture_dir, digest))
        try:
            return json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ReplayMissError(_corrupt_fixture_message(fixture_dir, path, e)) from e

    return replaying_post


def replay_sentence(meta: dict, model: str) -> str:
    when = sanitize(meta.get("recorded_at")) or "on an earlier run"
    version = sanitize(meta.get("ollaya_version")) or "(version unknown)"
    return (
        f"replayed from a fixture recorded {when} on {model} via ollaya {version}; "
        f"no model called. Run it live: ollaya pull {model} && flipcheck run request.json"
    )
