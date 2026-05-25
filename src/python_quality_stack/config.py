from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, NamedTuple


class QualityConfig(NamedTuple):
    paths: tuple[Path, ...]
    vertical_spacing_paths: tuple[Path, ...]
    dead_code_paths: tuple[Path, ...]
    dead_code_min_confidence: int
    static_guards: "StaticGuardConfig"
    enum_reachability: "EnumReachabilityConfig"


class StaticGuardConfig(NamedTuple):
    enabled: bool
    python_roots: tuple[Path, ...]
    text_roots: tuple[Path, ...]
    dynamic_typing_allowlist: frozenset[str]
    strict_no_get_files: frozenset[str]


class EnumReachabilityConfig(NamedTuple):
    enabled: bool
    models_path: Path
    model_module: str
    reference_roots: tuple[Path, ...]
    excluded_paths: frozenset[str]
    allow_marker: str


def load_config(root: Path | None = None) -> QualityConfig:
    project_root = (root or Path.cwd()).resolve()
    raw = _tool_config(project_root)
    paths = _paths(raw.get("paths"), default=("src", "tests", "scripts"))

    vertical_raw = _table(raw, "vertical-spacing")

    dead_code_raw = _table(raw, "dead-code")

    return QualityConfig(
        paths=paths,
        vertical_spacing_paths=_paths(vertical_raw.get("paths"), default=tuple(path.as_posix() for path in paths)),
        dead_code_paths=_paths(dead_code_raw.get("paths"), default=tuple(path.as_posix() for path in paths)),
        dead_code_min_confidence=_int(dead_code_raw.get("min-confidence"), default=100),
        static_guards=_static_guard_config(raw, paths),
        enum_reachability=_enum_reachability_config(raw),
    )


def _tool_config(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"

    if not path.exists():
        return {}

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tool = data.get("tool", {})

    if not isinstance(tool, dict):
        return {}

    config = tool.get("python-quality", {})

    return config if isinstance(config, dict) else {}


def _static_guard_config(raw: dict[str, Any], paths: tuple[Path, ...]) -> StaticGuardConfig:
    table = _table(raw, "static-guards")
    enabled = bool(table)

    return StaticGuardConfig(
        enabled=enabled,
        python_roots=_paths(table.get("python-roots"), default=tuple(path.as_posix() for path in paths)),
        text_roots=_paths(table.get("text-roots"), default=tuple(path.as_posix() for path in paths)),
        dynamic_typing_allowlist=frozenset(_strings(table.get("dynamic-typing-allowlist"))),
        strict_no_get_files=frozenset(_strings(table.get("strict-no-get-files"))),
    )


def _enum_reachability_config(raw: dict[str, Any]) -> EnumReachabilityConfig:
    table = _table(raw, "enum-reachability")
    models_path = _path(table.get("models-path"), default="")

    model_module = _string(table.get("model-module"), default="")
    enabled = bool(table) and bool(models_path.as_posix()) and bool(model_module)

    return EnumReachabilityConfig(
        enabled=enabled,
        models_path=models_path,
        model_module=model_module,
        reference_roots=_paths(table.get("reference-roots"), default=()),
        excluded_paths=frozenset(_strings(table.get("excluded-paths"))),
        allow_marker=_string(table.get("allow-marker"), default="allow-unused-enum:"),
    )


def _table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})

    return value if isinstance(value, dict) else {}


def _paths(value: object, *, default: tuple[str, ...]) -> tuple[Path, ...]:
    values = _strings(value) if value is not None else list(default)

    return tuple(Path(item) for item in values)


def _path(value: object, *, default: str) -> Path:
    return Path(value) if isinstance(value, str) else Path(default)


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, str)]


def _string(value: object, *, default: str) -> str:
    return value if isinstance(value, str) else default


def _int(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default
