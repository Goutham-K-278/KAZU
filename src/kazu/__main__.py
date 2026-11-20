"""Module entry point for `python -m kazu` and the `kazu` console script."""

from __future__ import annotations

from kazu.app import run_app


def main() -> int:
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
