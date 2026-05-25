from __future__ import annotations

import argparse
import ast
import io
import tokenize
from collections.abc import Sequence
from pathlib import Path

DEFAULT_PATHS = (Path("src"), Path("tests"), Path("scripts"))
EXCLUDED_PARTS = frozenset({"dist", "node_modules", ".git", ".venv"})

COMPOUND_STATEMENTS = (
    ast.AsyncFor,
    ast.AsyncWith,
    ast.For,
    ast.If,
    ast.Match,
    ast.Try,
    ast.While,
    ast.With,
)
CONTINUATION_PREFIXES = ("elif ", "else:", "except ", "except:", "finally:")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = _python_files(args.paths)
    changed = [path for path in paths if format_file(path, fix=args.fix)]

    if not changed:
        return 0

    _print_changed_files(changed, args.fix)

    return 0 if args.fix else 1


def format_file(path: Path, *, fix: bool) -> bool:
    original = path.read_text(encoding="utf-8")
    formatted = format_text(original)
    changed = formatted != original

    if changed and fix:
        path.write_text(formatted, encoding="utf-8")

    return changed


def format_text(text: str) -> str:
    formatted = text

    for _ in range(4):
        next_text = _format_text_once(formatted)

        if next_text == formatted:
            return formatted

        formatted = next_text

    return formatted


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce vertical spacing inside Python functions.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fix", action="store_true", help="rewrite files in place")
    mode.add_argument("--check", action="store_true", help="only report files that would change")
    parser.add_argument("paths", nargs="*", type=Path, default=DEFAULT_PATHS)

    return parser.parse_args(argv)


def _python_files(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []

    for path in paths:
        files.extend(_python_files_for_path(path))

    return sorted(set(files))


def _python_files_for_path(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if _is_python_file(path) else []

    if not path.exists():
        return []

    return [item for item in path.rglob("*.py") if _is_python_file(item)]


def _is_python_file(path: Path) -> bool:
    return path.suffix == ".py" and path.is_file() and not EXCLUDED_PARTS.intersection(path.parts)


def _format_text_once(text: str) -> str:
    lines = text.splitlines()
    tree = ast.parse(text)
    required_blank_before = _required_blank_lines(tree, lines)
    function_spans = _function_spans(tree)
    protected_inner_lines = _protected_multiline_string_inner_lines(text)
    formatted_lines = _format_lines(lines, required_blank_before, function_spans, protected_inner_lines)

    return _join_lines(formatted_lines, trailing_newline=text.endswith("\n"))


def _required_blank_lines(tree: ast.AST, lines: list[str]) -> set[int]:
    required: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _collect_required_blank_lines(node.body, lines, required)

    return required


def _collect_required_blank_lines(body: list[ast.stmt], lines: list[str], required: set[int]) -> None:
    _add_body_boundaries(body, lines, required)

    for statement in body:
        for child_body in _statement_bodies(statement):
            _collect_required_blank_lines(child_body, lines, required)


def _add_body_boundaries(body: list[ast.stmt], lines: list[str], required: set[int]) -> None:
    for index, current in enumerate(body[1:], start=1):
        previous = body[index - 1]

        if _needs_blank_before(previous, current, index == len(body) - 1, lines):
            required.add(_start_line(current))


def _needs_blank_before(previous: ast.stmt, current: ast.stmt, is_final: bool, lines: list[str]) -> bool:
    if _has_comment_between(lines, _end_line(previous), _start_line(current)):
        return False

    if _is_final_terminal(current, is_final):
        return True

    return _is_spacing_source(previous) or _is_spacing_target(current)


def _is_final_terminal(statement: ast.stmt, is_final: bool) -> bool:
    return is_final and isinstance(statement, ast.Return | ast.Raise)


def _is_spacing_source(statement: ast.stmt) -> bool:
    return isinstance(statement, COMPOUND_STATEMENTS) or _end_line(statement) > statement.lineno


def _is_spacing_target(statement: ast.stmt) -> bool:
    return isinstance(statement, COMPOUND_STATEMENTS)


def _statement_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    bodies = _named_statement_bodies(statement)
    bodies.extend(_except_handler_bodies(statement))
    bodies.extend(_match_case_bodies(statement))

    return bodies


def _named_statement_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    return [
        body for name in ("body", "orelse", "finalbody") if _is_statement_list(body := getattr(statement, name, None))
    ]


def _except_handler_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.Try):
        return [handler.body for handler in statement.handlers]

    return []


def _match_case_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.Match):
        return [case.body for case in statement.cases]

    return []


def _is_statement_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value)


def _function_spans(tree: ast.AST) -> list[tuple[int, int]]:
    return [
        (_start_line(node), _end_line(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]


def _protected_multiline_string_inner_lines(text: str) -> set[int]:
    protected: set[int] = set()

    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.STRING and token.start[0] != token.end[0]:
            protected.update(range(token.start[0] + 1, token.end[0] + 1))

    return protected


def _format_lines(
    lines: list[str],
    required_blank_before: set[int],
    function_spans: list[tuple[int, int]],
    protected_inner_lines: set[int],
) -> list[str]:
    result: list[str] = []
    pending_blank_lines = 0
    previous_line_number = 0

    for line_number, line in enumerate(lines, start=1):
        if line_number in protected_inner_lines:
            result.extend("" for _ in range(pending_blank_lines))
            result.append(line)
            pending_blank_lines = 0
            previous_line_number = _next_previous_line_number(line, line_number, previous_line_number)
            continue

        if _is_blank(line):
            pending_blank_lines += 1
            continue

        blank_count = _blank_count_before(
            line,
            line_number,
            previous_line_number,
            pending_blank_lines,
            required_blank_before,
            function_spans,
            lines,
        )

        result.extend("" for _ in range(blank_count))
        result.append(line)
        pending_blank_lines = 0
        previous_line_number = line_number

    return result


def _next_previous_line_number(line: str, line_number: int, previous_line_number: int) -> int:
    return line_number if line.strip() else previous_line_number


def _blank_count_before(
    line: str,
    line_number: int,
    previous_line_number: int,
    pending_blank_lines: int,
    required_blank_before: set[int],
    function_spans: list[tuple[int, int]],
    lines: list[str],
) -> int:
    if previous_line_number == 0:
        return 0

    if _starts_continuation_clause(line):
        return 0

    if line_number in required_blank_before:
        return 1

    if not _same_function_span(previous_line_number, line_number, function_spans):
        return pending_blank_lines

    return _function_blank_count(lines, previous_line_number, line_number, pending_blank_lines)


def _function_blank_count(
    lines: list[str],
    previous_line_number: int,
    line_number: int,
    pending_blank_lines: int,
) -> int:
    if _line_is_comment(lines[previous_line_number - 1]) or _line_is_comment(lines[line_number - 1]):
        return pending_blank_lines

    return min(pending_blank_lines, 1)


def _same_function_span(left: int, right: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= left <= end and start <= right <= end for start, end in spans)


def _has_comment_between(lines: list[str], start_line: int, end_line: int) -> bool:
    return any(_line_is_comment(line) for line in lines[start_line : end_line - 1])


def _starts_continuation_clause(line: str) -> bool:
    stripped = line.lstrip()

    return stripped.startswith(CONTINUATION_PREFIXES)


def _line_is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def _is_blank(line: str) -> bool:
    return not line.strip()


def _end_line(statement: ast.AST) -> int:
    return statement.end_lineno or statement.lineno


def _start_line(statement: ast.AST) -> int:
    decorators = getattr(statement, "decorator_list", ())

    if decorators:
        return min(decorator.lineno for decorator in decorators)

    return statement.lineno


def _join_lines(lines: list[str], *, trailing_newline: bool) -> str:
    if not lines:
        return "\n" if trailing_newline else ""

    return "\n".join(lines) + ("\n" if trailing_newline else "")


def _print_changed_files(paths: list[Path], fixed: bool) -> None:
    action = "formatted" if fixed else "would reformat"

    for path in paths:
        print(f"{action}: {path.as_posix()}")


if __name__ == "__main__":
    raise SystemExit(main())
