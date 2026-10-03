import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from flipcheck.errors import FlipcheckError, read_utf8_text


class PayloadsError(FlipcheckError):
    pass


@dataclass
class Payload:
    id: str
    cls: str
    source: str
    text: str
    control_id: str
    control_text: str


def _parse_entries(raw, source_label: str) -> list[Payload]:
    if not isinstance(raw, list) or not raw:
        raise PayloadsError(f"flipcheck: {source_label} has no payload entries.")
    entries = []
    for item in raw:
        try:
            entries.append(
                Payload(
                    id=item["id"],
                    cls=item.get("class") or "uncategorized",
                    source=item.get("source") or "unknown",
                    text=item["text"],
                    control_id=item.get("control_id") or f"{item['id']}-control",
                    control_text=item["control_text"],
                )
            )
        except KeyError as e:
            raise PayloadsError(f"flipcheck: {source_label} entry is missing key {e}.") from e
    return entries


def load_default_payloads() -> list[Payload]:
    raw = resources.files("flipcheck").joinpath("payloads.json").read_text()
    return _parse_entries(json.loads(raw), "the bundled payload corpus")


def load_payloads(path: str | None) -> list[Payload]:
    if not path:
        return load_default_payloads()
    raw = read_utf8_text(Path(path), PayloadsError, path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise PayloadsError(f"flipcheck: {path} is not valid JSON: {e.msg}") from e
    return _parse_entries(data, path)
