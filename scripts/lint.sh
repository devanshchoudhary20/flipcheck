#!/usr/bin/env bash
set -euo pipefail
uv run ruff check .
uv run python scripts/check_comments.py
