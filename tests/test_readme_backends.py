from pathlib import Path

from flipcheck.backend import BACKEND_TABLE

REPO_ROOT = Path(__file__).resolve().parent.parent


def _table_rows(markdown: str) -> list[list[str]]:
    # the "## Backends" section's own table only; stop at the next heading so later
    # sections' tables (control rate, etc.) don't leak into this one, then skip the
    # header and the --- separator row
    section = markdown.split("## Backends", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    data_lines = lines[2:]
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in data_lines]


def test_readme_backend_table_matches_the_registry_in_code():
    markdown = (REPO_ROOT / "README.md").read_text()
    rows = _table_rows(markdown)
    assert len(rows) == len(BACKEND_TABLE)
    for row, spec in zip(rows, BACKEND_TABLE):
        name, how_chosen, env_or_flag, default_model, cost, repeats = row
        assert name == spec.name
        assert how_chosen == spec.how_chosen
        assert env_or_flag == spec.env_or_flag
        assert default_model == spec.default_model
        assert cost == spec.cost
        assert repeats == spec.repeats


def test_readme_lists_local_ollaya_first():
    markdown = (REPO_ROOT / "README.md").read_text()
    rows = _table_rows(markdown)
    assert rows[0][0] == "local ollaya (default)"
