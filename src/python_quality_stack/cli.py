from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from python_quality_stack.config import QualityConfig, load_config
from python_quality_stack.guards import guard_failures, print_guard_failures
from python_quality_stack.runner import run, run_all
from python_quality_stack.version_check import check_latest
from python_quality_stack.vertical_spacing import run_vertical_spacing

Command = Callable[[QualityConfig], int]


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config = load_config()

    return _commands()[args.command](config)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the configured Python quality stack.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    for command in _commands():
        subcommands.add_parser(command)

    return parser.parse_args(argv)


def _commands() -> dict[str, Command]:
    return {
        "format": _format,
        "format-check": _format_check,
        "lint": _lint,
        "quality-guards": _quality_guards,
        "vertical-spacing": _vertical_spacing_check,
        "version-check": _version_check,
        "typecheck": _typecheck,
        "complexity": _complexity,
        "cognitive-complexity": _complexity,
        "dead-code": _dead_code,
        "test": _test,
        "check": _check,
    }


def _format(config: QualityConfig) -> int:
    status = run(["ruff", "format", "--no-cache", *_path_args(config.paths)])

    if status != 0:
        return status

    status = run_vertical_spacing(config.vertical_spacing_paths, fix=True)

    if status != 0:
        return status

    return run(["ruff", "format", "--no-cache", *_path_args(config.paths)])


def _format_check(config: QualityConfig) -> int:
    status = run(["ruff", "format", "--check", "--no-cache", *_path_args(config.paths)])

    if status != 0:
        return status

    return run_vertical_spacing(config.vertical_spacing_paths, fix=False)


def _lint(config: QualityConfig) -> int:
    return run(["ruff", "check", "--no-cache", *_path_args(config.paths)]) or _quality_guards(config)


def _quality_guards(config: QualityConfig) -> int:
    failures = guard_failures(Path.cwd().resolve(), config.static_guards, config.enum_reachability)

    if not failures:
        return 0

    print_guard_failures(failures)

    return 1


def _vertical_spacing_check(config: QualityConfig) -> int:
    return run_vertical_spacing(config.vertical_spacing_paths, fix=False)


def _version_check(config: QualityConfig) -> int:
    return check_latest()


def _typecheck(config: QualityConfig) -> int:
    return run_all([["ty", "check"], ["pyright"], ["mypy"]])


def _complexity(config: QualityConfig) -> int:
    return run(["complexipy"])


def _dead_code(config: QualityConfig) -> int:
    return run(
        [
            "vulture",
            *_path_args(config.dead_code_paths),
            "--min-confidence",
            str(config.dead_code_min_confidence),
        ]
    )


def _test(config: QualityConfig) -> int:
    return run(["pytest"])


def _check(config: QualityConfig) -> int:
    return run_all(
        [
            ["python-quality", "version-check"],
            ["python-quality", "format-check"],
            ["python-quality", "lint"],
            ["python-quality", "typecheck"],
            ["python-quality", "complexity"],
            ["python-quality", "dead-code"],
            ["python-quality", "test"],
        ]
    )


def _path_args(paths: tuple[Path, ...]) -> list[str]:
    return [path.as_posix() for path in paths if path.exists()]
