from __future__ import annotations

import argparse
import ast
import io
import tokenize
from collections.abc import Sequence
from pathlib import Path
from typing import TypeGuard

DEFAULT_PATHS = (Path("src"), Path("tests"), Path("scripts"))
EXCLUDED_PARTS = frozenset({"dist", "node_modules", ".git", ".venv", "_vendor"})
SMALL_UNRELATED_CLUSTER_LIMIT = 3
SMALL_UNRELATED_STATEMENT_CHARS = 40

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

    return run_vertical_spacing(args.paths, fix=args.fix)


def run_vertical_spacing(paths: Sequence[Path], *, fix: bool) -> int:
    print(f"$ vertical-spacing {'--fix' if fix else '--check'} {' '.join(_path_args(paths))}", flush=True)

    changed = [path for path in _python_files(paths) if format_file(path, fix=fix)]

    if not changed:
        return 0

    _print_changed_files(changed, fix)

    return 0 if fix else 1


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
    tree: ast.Module = ast.parse(text)
    required_blank_before = _required_blank_lines(tree, lines)

    function_spans = _function_spans(tree)

    protected_inner_lines = _protected_multiline_string_inner_lines(text)
    formatted_lines = _format_lines(lines, required_blank_before, function_spans, protected_inner_lines)

    return _join_lines(formatted_lines, trailing_newline=text.endswith("\n"))


def _required_blank_lines(tree: ast.Module, lines: list[str]) -> set[int]:
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
        if _needs_blank_before(body, index, lines):
            required.add(_start_line(current))


def _needs_blank_before(body: list[ast.stmt], index: int, lines: list[str]) -> bool:
    previous = body[index - 1]
    current = body[index]
    is_final = index == len(body) - 1

    if _has_comment_between(lines, _end_line(previous), _start_line(current)):
        return False

    if _is_final_terminal(current, is_final):
        return True

    if _is_spacing_source(previous) or _is_spacing_target(current):
        return True

    return _needs_cohesion_blank(body, index, lines)


def _needs_cohesion_blank(body: list[ast.stmt], index: int, lines: list[str]) -> bool:
    previous = body[index - 1]
    current = body[index]

    if not _is_simple_cohesion_statement(previous) or not _is_simple_cohesion_statement(current):
        return False

    if _statements_are_cohesive(previous, current):
        return False

    return not _small_unrelated_cluster_allows_tight_pair(body, index, lines)


def _statements_are_cohesive(previous: ast.stmt, current: ast.stmt) -> bool:
    return _assignment_is_used_by_next_statement(previous, current) or _same_call_receiver(previous, current)


def _assignment_is_used_by_next_statement(previous: ast.stmt, current: ast.stmt) -> bool:
    return bool(_assigned_references(previous) & _loaded_references(current))


def _same_call_receiver(previous: ast.stmt, current: ast.stmt) -> bool:
    previous_receiver = _call_receiver(previous)

    current_receiver = _call_receiver(current)

    return previous_receiver is not None and previous_receiver == current_receiver


def _small_unrelated_cluster_allows_tight_pair(body: list[ast.stmt], index: int, lines: list[str]) -> bool:
    if not _is_small_unrelated_pair(body[index - 1], body[index], lines):
        return False

    cluster_start = _small_unrelated_cluster_start(body, index, lines)

    return (index - cluster_start) % SMALL_UNRELATED_CLUSTER_LIMIT != 0


def _small_unrelated_cluster_start(body: list[ast.stmt], index: int, lines: list[str]) -> int:
    start = index

    while start > 0 and _is_small_unrelated_pair(body[start - 1], body[start], lines):
        start -= 1

    return start


def _is_small_unrelated_pair(previous: ast.stmt, current: ast.stmt, lines: list[str]) -> bool:
    if _has_comment_between(lines, _end_line(previous), _start_line(current)):
        return False

    if _statements_are_cohesive(previous, current):
        return False

    return _is_small_cluster_statement(previous, lines) and _is_small_cluster_statement(current, lines)


def _is_small_cluster_statement(statement: ast.stmt, lines: list[str]) -> bool:
    if not _is_simple_cohesion_statement(statement) or _start_line(statement) != _end_line(statement):
        return False

    return len(lines[_start_line(statement) - 1].strip()) < SMALL_UNRELATED_STATEMENT_CHARS


def _is_simple_cohesion_statement(statement: ast.stmt) -> bool:
    return _is_assignment_statement(statement) or _is_call_expression(statement)


def _is_assignment_statement(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign)


def _is_call_expression(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)


def _assigned_references(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Assign):
        return _target_references(statement.targets)

    if isinstance(statement, ast.AnnAssign | ast.AugAssign):
        return _target_references([statement.target])

    return set()


def _target_references(targets: Sequence[ast.expr]) -> set[str]:
    references: set[str] = set()

    for target in targets:
        references.update(_target_reference(target))

    return references


def _target_reference(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {_name_reference(target.id)}

    if isinstance(target, ast.Attribute):
        return {_attribute_reference(target)}

    if isinstance(target, ast.Tuple | ast.List):
        return _target_references(target.elts)

    return set()


def _loaded_references(statement: ast.stmt) -> set[str]:
    references: set[str] = set()

    for node in ast.walk(statement):
        references.update(_loaded_reference(node))

    return references


def _loaded_reference(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        return {_name_reference(node.id)}

    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        return {_attribute_reference(node)}

    return set()


def _call_receiver(statement: ast.stmt) -> str | None:
    if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
        return None

    call = statement.value

    if isinstance(call.func, ast.Attribute):
        return _reference_key(call.func.value)

    return None


def _name_reference(name: str) -> str:
    return f"name:{name}"


def _attribute_reference(node: ast.Attribute) -> str:
    return f"attr:{_reference_key(node)}"


def _reference_key(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return _name_reference(node.id)

    if isinstance(node, ast.Attribute):
        return f"{_reference_key(node.value)}.{node.attr}"

    return ast.dump(node, include_attributes=False)


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
    bodies: list[list[ast.stmt]] = []

    for name in ("body", "orelse", "finalbody"):
        body = getattr(statement, name, None)

        if _is_statement_list(body):
            bodies.append(body)

    return bodies


def _except_handler_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.Try):
        return [handler.body for handler in statement.handlers]

    return []


def _match_case_bodies(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.Match):
        return [case.body for case in statement.cases]

    return []


def _is_statement_list(value: object) -> TypeGuard[list[ast.stmt]]:
    return isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value)


def _function_spans(tree: ast.Module) -> list[tuple[int, int]]:
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


def _end_line(statement: ast.stmt) -> int:
    return statement.end_lineno or statement.lineno


def _start_line(statement: ast.stmt) -> int:
    decorators = _decorators(statement)

    if decorators:
        return min(decorator.lineno for decorator in decorators)

    return statement.lineno


def _decorators(statement: ast.stmt) -> list[ast.expr]:
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return statement.decorator_list

    return []


def _join_lines(lines: list[str], *, trailing_newline: bool) -> str:
    if not lines:
        return "\n" if trailing_newline else ""

    return "\n".join(lines) + ("\n" if trailing_newline else "")


def _print_changed_files(paths: list[Path], fixed: bool) -> None:
    action = "formatted" if fixed else "would reformat"

    for path in paths:
        print(f"{action}: {path.as_posix()}")


def _path_args(paths: Sequence[Path]) -> list[str]:
    return [path.as_posix() for path in paths]


if __name__ == "__main__":
    raise SystemExit(main())
