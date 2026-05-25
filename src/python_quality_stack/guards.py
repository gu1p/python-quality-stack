from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from python_quality_stack.config import EnumReachabilityConfig, StaticGuardConfig

CAST_RE = re.compile(r"\bcast\b")
DYNAMIC_RE = re.compile(r"\bAny\b|dict\[str,\s*Any\]|dict\[str,\s*object\]")
UNTYPED_GET_RE = re.compile(r"\.get\(")


class EnumMember(NamedTuple):
    enum_name: str
    member_name: str
    line_number: int
    has_allow_marker: bool
    allow_reason: str


def guard_failures(
    root: Path,
    static_config: StaticGuardConfig,
    enum_config: EnumReachabilityConfig,
) -> list[str]:
    failures: list[str] = []

    if static_config.enabled:
        failures.extend(_cast_failures(root, static_config))
        failures.extend(_dynamic_typing_failures(root, static_config))

    if enum_config.enabled:
        failures.extend(_enum_member_reachability_failures(root, enum_config))

    return failures


def print_guard_failures(failures: Sequence[str]) -> None:
    print("Python quality guard failures:")

    for failure in failures:
        print(f"  {failure}")


def _cast_failures(root: Path, config: StaticGuardConfig) -> list[str]:
    failures: list[str] = []

    for path in _files(root, config.text_roots, suffixes=(".py", ".ts", ".tsx")):
        failures.extend(_cast_file_failures(root, path))

    return failures


def _cast_file_failures(root: Path, path: Path) -> list[str]:
    relative = _relative(root, path)

    return [
        f"{relative}:{line_number}: avoid cast; use typed validation/narrowing"
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if CAST_RE.search(line)
    ]


def _dynamic_typing_failures(root: Path, config: StaticGuardConfig) -> list[str]:
    failures: list[str] = []

    for path in _files(root, config.python_roots, suffixes=(".py",)):
        failures.extend(_dynamic_typing_file_failures(root, path, config))

    return failures


def _dynamic_typing_file_failures(root: Path, path: Path, config: StaticGuardConfig) -> list[str]:
    relative = _relative(root, path)
    allowed_dynamic = relative in config.dynamic_typing_allowlist or relative.startswith("tests/")

    strict_no_get = relative in config.strict_no_get_files

    return [
        failure
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for failure in _dynamic_typing_line_failures(relative, line_number, line, allowed_dynamic, strict_no_get)
    ]


def _dynamic_typing_line_failures(
    relative: str,
    line_number: int,
    line: str,
    allowed_dynamic: bool,
    strict_no_get: bool,
) -> list[str]:
    failures: list[str] = []

    if not allowed_dynamic and DYNAMIC_RE.search(line):
        failures.append(f"{relative}:{line_number}: dynamic typing is only allowed at explicit edges")

    if strict_no_get and UNTYPED_GET_RE.search(line):
        failures.append(f"{relative}:{line_number}: use typed fields/helpers instead of untyped .get")

    return failures


def _enum_member_reachability_failures(root: Path, config: EnumReachabilityConfig) -> list[str]:
    models_path = root / config.models_path
    members = _enum_members(models_path, config.allow_marker)
    references = _referenced_enum_members(members, _production_enum_reference_files(root, config), config.model_module)

    return _unused_enum_member_failures(root, members, references, models_path, config.allow_marker)


def _enum_members(path: Path, allow_marker: str) -> list[EnumMember]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    tree: ast.Module = ast.parse(text, filename=str(path))

    members: list[EnumMember] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _inherits_from_str_enum(node):
            members.extend(_enum_class_members(node, lines, allow_marker))

    return members


def _enum_class_members(node: ast.ClassDef, lines: list[str], allow_marker: str) -> list[EnumMember]:
    members: list[EnumMember] = []

    for statement in node.body:
        member_name = _enum_member_name(statement)

        if member_name is None:
            continue

        line = lines[statement.lineno - 1]
        marker_index = line.find(allow_marker)
        has_marker = marker_index >= 0
        reason = line[marker_index + len(allow_marker) :].strip() if has_marker else ""
        members.append(EnumMember(node.name, member_name, statement.lineno, has_marker, reason))

    return members


def _enum_member_name(statement: ast.stmt) -> str | None:
    if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
        return None

    target = statement.targets[0]

    if not isinstance(target, ast.Name):
        return None

    if not isinstance(statement.value, ast.Constant) or not isinstance(statement.value.value, str):
        return None

    return target.id


def _inherits_from_str_enum(node: ast.ClassDef) -> bool:
    return any(
        (name := _dotted_name(base)) == "StrEnum" or (name is not None and name.endswith(".StrEnum"))
        for base in node.bases
    )


def _production_enum_reference_files(root: Path, config: EnumReachabilityConfig) -> list[Path]:
    return [
        path
        for path in _files(root, config.reference_roots, suffixes=(".py",))
        if _relative(root, path) not in config.excluded_paths
    ]


def _referenced_enum_members(
    members: list[EnumMember],
    reference_paths: Sequence[Path],
    model_module: str,
) -> set[tuple[str, str]]:
    member_names_by_enum = _member_names_by_enum(members)
    enum_names = set(member_names_by_enum)

    references: set[tuple[str, str]] = set()

    for path in reference_paths:
        references.update(_referenced_enum_members_in_file(path, enum_names, member_names_by_enum, model_module))

    return references


def _referenced_enum_members_in_file(
    path: Path,
    enum_names: set[str],
    member_names_by_enum: dict[str, set[str]],
    model_module: str,
) -> set[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(text, filename=str(path))
    direct_aliases, module_aliases = _enum_import_aliases(tree, enum_names, model_module)

    return {
        (enum_name, node.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        if (enum_name := _referenced_enum_name(node.value, enum_names, direct_aliases, module_aliases)) is not None
        if node.attr in member_names_by_enum[enum_name]
    }


def _member_names_by_enum(members: list[EnumMember]) -> dict[str, set[str]]:
    member_names_by_enum: dict[str, set[str]] = {}

    for member in members:
        member_names_by_enum.setdefault(member.enum_name, set()).add(member.member_name)

    return member_names_by_enum


def _enum_import_aliases(tree: ast.Module, enum_names: set[str], model_module: str) -> tuple[dict[str, str], set[str]]:
    direct_aliases: dict[str, str] = {}
    module_aliases = {model_module}

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            _add_module_import_aliases(statement, module_aliases, model_module)
        elif isinstance(statement, ast.ImportFrom):
            _add_import_from_aliases(statement, enum_names, direct_aliases, module_aliases, model_module)

    return direct_aliases, module_aliases


def _add_module_import_aliases(statement: ast.Import, module_aliases: set[str], model_module: str) -> None:
    for alias in statement.names:
        if alias.name == model_module:
            module_aliases.add(alias.asname or model_module)


def _add_import_from_aliases(
    statement: ast.ImportFrom,
    enum_names: set[str],
    direct_aliases: dict[str, str],
    module_aliases: set[str],
    model_module: str,
) -> None:
    if statement.module == model_module:
        _add_model_symbol_aliases(statement, enum_names, direct_aliases)
    elif statement.module == model_module.rpartition(".")[0]:
        _add_package_module_aliases(statement, module_aliases, model_module)


def _add_model_symbol_aliases(
    statement: ast.ImportFrom,
    enum_names: set[str],
    direct_aliases: dict[str, str],
) -> None:
    for alias in statement.names:
        if alias.name == "*":
            direct_aliases.update({enum_name: enum_name for enum_name in enum_names})
        elif alias.name in enum_names:
            direct_aliases[alias.asname or alias.name] = alias.name


def _add_package_module_aliases(statement: ast.ImportFrom, module_aliases: set[str], model_module: str) -> None:
    module_name = model_module.rpartition(".")[2]

    for alias in statement.names:
        if alias.name == module_name:
            module_aliases.add(alias.asname or module_name)


def _referenced_enum_name(
    value: ast.expr,
    enum_names: set[str],
    direct_aliases: dict[str, str],
    module_aliases: set[str],
) -> str | None:
    dotted_name = _dotted_name(value)

    if dotted_name is None:
        return None

    if (direct_name := _direct_enum_name(dotted_name, enum_names, direct_aliases)) is not None:
        return direct_name

    return _module_enum_name(dotted_name, enum_names, module_aliases)


def _direct_enum_name(dotted_name: str, enum_names: set[str], direct_aliases: dict[str, str]) -> str | None:
    direct_name = direct_aliases.get(dotted_name, dotted_name)

    return direct_name if direct_name in enum_names else None


def _module_enum_name(dotted_name: str, enum_names: set[str], module_aliases: set[str]) -> str | None:
    for module_alias in module_aliases:
        prefix = f"{module_alias}."

        if dotted_name.startswith(prefix) and (enum_name := dotted_name.removeprefix(prefix)) in enum_names:
            return enum_name

    return None


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute) and (parent := _dotted_name(node.value)) is not None:
        return f"{parent}.{node.attr}"

    return None


def _unused_enum_member_failures(
    root: Path,
    members: list[EnumMember],
    references: set[tuple[str, str]],
    models_path: Path,
    allow_marker: str,
) -> list[str]:
    failures: list[str] = []
    relative = _relative(root, models_path)

    for member in members:
        failures.extend(_unused_enum_member_failure(member, references, relative, allow_marker))

    return failures


def _unused_enum_member_failure(
    member: EnumMember,
    references: set[tuple[str, str]],
    relative: str,
    allow_marker: str,
) -> list[str]:
    key = (member.enum_name, member.member_name)

    prefix = f"{relative}:{member.line_number}: {member.enum_name}.{member.member_name}"
    message = _unused_enum_member_message(member, key in references, prefix, allow_marker)

    return [message] if message else []


def _unused_enum_member_message(member: EnumMember, is_referenced: bool, prefix: str, allow_marker: str) -> str:
    if member.has_allow_marker:
        return _unused_enum_marker_message(member, is_referenced, prefix)

    return "" if is_referenced else _unused_enum_message(prefix, allow_marker)


def _unused_enum_marker_message(member: EnumMember, is_referenced: bool, prefix: str) -> str:
    if not member.allow_reason:
        return f"{prefix} allow marker needs a reason"

    return f"{prefix} has a stale unused-enum marker" if is_referenced else ""


def _unused_enum_message(prefix: str, allow_marker: str) -> str:
    return f"{prefix} has no production reference; add behavior or annotate with # {allow_marker} <reason>"


def _files(root: Path, roots: tuple[Path, ...], *, suffixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []

    for source_root in roots:
        resolved = root / source_root

        if not resolved.exists():
            continue

        files.extend(
            path
            for path in resolved.rglob("*")
            if path.is_file()
            and path.suffix in suffixes
            and "node_modules" not in path.parts
            and "dist" not in path.parts
        )

    return sorted(files)


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()
