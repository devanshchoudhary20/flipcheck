# Changelog

## 0.1.0 - 2026-10-03

- First build. `flipcheck example` and `flipcheck run <request.json>` against a local ollaya model (default `laya:en`) or a hosted TypeSafe-compatible backend (Vercel AI Gateway or TypeSafe direct, both optional).
- Per untrusted field: remove, inject (eight sourced payloads with paired length-matched controls), and a verdict of DON'T SEND, HARDEN, OK, INERT, or BRITTLE, with exit codes 0/1/2/3/130.
- `--record`/`--replay` fixtures; the wheel ships a fixture recorded on `laya:en` so `flipcheck example` works with no backend and no network.
- `--json`, `--untrusted`, `--payloads`, `--repeat`, `--model`, `--base-url`, `--confidence-min`.
- Not yet published to PyPI; that is the launch gate, held for the human's sign-off.
