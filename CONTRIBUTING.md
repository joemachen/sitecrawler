# Contributing

Everything about how this project is developed lives in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): toolchain, setup, branching,
commit style, definition of done, and testing strategy.

Short version:

1. Open or pick an issue.
2. Branch from `main` (`feat/...`, `fix/...`, `docs/...`, `chore/...`).
3. Add a failing test, make it pass.
4. `uv run pre-commit run --all-files` must be clean.
5. Open a PR; CI must be green; squash-merge.
6. Add a line to `CHANGELOG.md` under Unreleased.
