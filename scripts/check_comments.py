#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src"
EXCLUDED_DIRS = {"__pycache__"}


def walk(directory: Path) -> list[Path]:
    files = []
    for entry in sorted(directory.iterdir()):
        if entry.name in EXCLUDED_DIRS:
            continue
        if entry.is_dir():
            files.extend(walk(entry))
        elif entry.suffix == ".py":
            files.append(entry)
    return files


def find_hash_comment_runs(lines: list[str]) -> list[tuple[int, int]]:
    violations = []
    run_start = None
    for index, line in enumerate(lines):
        is_comment = line.strip().startswith("#")
        if is_comment and run_start is None:
            run_start = index
        elif not is_comment and run_start is not None:
            if index - run_start >= 2:
                violations.append((run_start + 1, index))
            run_start = None
    if run_start is not None and len(lines) - run_start >= 2:
        violations.append((run_start + 1, len(lines)))
    return violations


def find_docstrings(path: Path, source: str) -> list[tuple[int, int]]:
    tree = ast.parse(source, filename=str(path))
    violations = []
    nodes = [tree, *ast.walk(tree)]
    seen = set()
    for node in nodes:
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        docstring_node = ast.get_docstring(node, clean=False)
        if docstring_node is None:
            continue
        body = node.body if hasattr(node, "body") else []
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            first = body[0]
            violations.append((first.lineno, getattr(first, "end_lineno", first.lineno)))
    return violations


def check_file(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")
    violations = [("comment", *run) for run in find_hash_comment_runs(lines)]
    violations += [("docstring", *run) for run in find_docstrings(path, content)]
    return [f"{path}:{start}-{end} ({kind})" for kind, start, end in violations]


def main() -> int:
    files = walk(ROOT)
    violations = [line for f in files for line in check_file(f)]
    if violations:
        print(f"{len(violations)} violation(s) found:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print("No multi-line comments or docstrings found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
