from __future__ import annotations

import json
import os
import platform
import shutil
import shlex
import stat
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from importlib import resources
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple
from urllib.parse import unquote, urlparse

CODEQL_QUERY_SUITE = "codeql/python-queries:codeql-suites/python-security-and-quality.qls"
SKIP_ENV = "PYTHON_QUALITY_SKIP_CODEQL"
SUPPORTED_PLATFORMS = {
    "linux64": "Linux x86_64",
    "osx64": "macOS x86_64",
    "win64": "Windows x86_64",
}
IGNORED_SOURCE_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "dist",
        "node_modules",
    }
)


class CodeqlFinding(NamedTuple):
    path: str
    line: int
    rule_id: str
    message: str


def run_codeql_check(paths: Sequence[Path]) -> int:
    if os.environ.get(SKIP_ENV) == "1":
        print(f"CodeQL dead-code check skipped via {SKIP_ENV}=1")

        return 0

    existing_paths = _existing_paths(paths)

    if not existing_paths:
        return _skip_without_paths()

    binary = _checked_binary()

    if binary is None:
        return 1

    status, findings = _analyze_codeql(binary, Path.cwd().resolve(), existing_paths)

    if status != 0:
        return status

    return _print_findings(findings)


def _existing_paths(paths: Sequence[Path]) -> tuple[Path, ...]:
    return tuple(path for path in paths if path.exists())


def _skip_without_paths() -> int:
    print("CodeQL dead-code check skipped: no configured paths exist")

    return 0


def _checked_binary() -> Path | None:
    binary = _bundled_binary()

    if binary is None:
        print(_missing_binary_message())

        return None

    if not _ensure_executable(binary):
        print(f"error: bundled CodeQL binary is not executable: {binary}")

        return None

    return binary


def _analyze_codeql(binary: Path, root: Path, paths: Sequence[Path]) -> tuple[int, list[CodeqlFinding]]:
    with TemporaryDirectory(prefix="python-quality-codeql-") as temp:
        temp_path = Path(temp)
        database_path = temp_path / "database"

        sarif_path = temp_path / "results.sarif"

        source_root = temp_path / "source"

        if not _prepare_source_root(source_root, root, paths):
            return 1, []

        status = _run_analysis_commands(binary, database_path, source_root, sarif_path)

        if status != 0:
            return status, []

        return _analysis_findings(sarif_path, source_root, paths)


def _prepare_source_root(destination: Path, root: Path, paths: Sequence[Path]) -> bool:
    try:
        for path in sorted(paths, key=lambda item: len(item.parts)):
            _copy_source_path(root, path, destination)
    except OSError as error:
        print(f"error: failed to prepare CodeQL source tree: {error}")

        return False

    return True


def _run_analysis_commands(binary: Path, database_path: Path, source_root: Path, sarif_path: Path) -> int:
    status = _create_database(binary, database_path, source_root)

    if status != 0:
        return status

    return _analyze_database(binary, database_path, sarif_path)


def _analysis_findings(sarif_path: Path, source_root: Path, paths: Sequence[Path]) -> tuple[int, list[CodeqlFinding]]:
    try:
        return 0, _findings_from_sarif(sarif_path, source_root, paths)
    except RuntimeError as error:
        print(f"error: {error}")

        return 1, []


def _copy_source_path(root: Path, path: Path, destination_root: Path) -> None:
    source = _resolve_path(root, path)
    relative = _source_relative_path(root, path, source)
    destination = destination_root / relative

    if destination.exists():
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        shutil.copytree(source, destination, ignore=_copy_ignore)
    else:
        shutil.copy2(source, destination)


def _source_relative_path(root: Path, original: Path, resolved: Path) -> Path:
    if not original.is_absolute():
        return original

    try:
        return resolved.relative_to(root)
    except ValueError:
        return Path(resolved.name)


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_SOURCE_NAMES}


def _create_database(binary: Path, database_path: Path, source_root: Path) -> int:
    return _run_command(
        [
            binary.as_posix(),
            "database",
            "create",
            database_path.as_posix(),
            "--language=python",
            "--build-mode=none",
            "--source-root",
            source_root.as_posix(),
            "--overwrite",
        ]
    )


def _analyze_database(binary: Path, database_path: Path, sarif_path: Path) -> int:
    return _run_command(
        [
            binary.as_posix(),
            "database",
            "analyze",
            database_path.as_posix(),
            CODEQL_QUERY_SUITE,
            "--format=sarif-latest",
            "--output",
            sarif_path.as_posix(),
            "--sarif-category=python",
        ]
    )


def _print_findings(findings: Sequence[CodeqlFinding]) -> int:
    if not findings:
        print("CodeQL dead-code check passed")

        return 0

    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule_id}: {finding.message}")

    return 1


def _bundled_binary() -> Path | None:
    platform_id = _platform_id()

    if platform_id is None:
        return None

    executable = "codeql.exe" if platform_id == "win64" else "codeql"
    resource = resources.files("python_quality_stack").joinpath(
        "_vendor",
        "codeql",
        platform_id,
        "codeql",
        executable,
    )

    if not resource.is_file():
        return None

    return Path(str(resource))


def _platform_id() -> str | None:
    machine = platform.machine().lower()

    if machine not in {"amd64", "x86_64"}:
        return None

    if sys.platform.startswith("linux"):
        return "linux64"

    if sys.platform == "darwin":
        return "osx64"

    if sys.platform == "win32":
        return "win64"

    return None


def _missing_binary_message() -> str:
    detected = f"{sys.platform}/{platform.machine() or 'unknown'}"

    supported = ", ".join(SUPPORTED_PLATFORMS.values())

    return (
        "error: bundled CodeQL is unavailable for this installation. "
        f"Detected {detected}; supported bundled wheels are {supported}. "
        "Install a python-quality-stack wheel built with the CodeQL bundle."
    )


def _ensure_executable(binary: Path) -> bool:
    if sys.platform == "win32" or os.access(binary, os.X_OK):
        return True

    try:
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    except OSError:
        return False

    return os.access(binary, os.X_OK)


def _run_command(command: Sequence[str]) -> int:
    print(f"$ {shlex.join(command)}", flush=True)

    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"error: failed to run CodeQL: {error}")

        return 1


def _findings_from_sarif(sarif_path: Path, root: Path, included_paths: Sequence[Path]) -> list[CodeqlFinding]:
    data = _load_json_object(sarif_path)

    included_roots = tuple(_resolve_path(root, path) for path in included_paths)
    findings = (
        _finding_from_result(result, root, included_roots)
        for run in _object_list(data.get("runs"))
        for result in _object_list(run.get("results"))
    )

    return _present_findings(findings)


def _present_findings(findings: Iterable[CodeqlFinding | None]) -> list[CodeqlFinding]:
    return [finding for finding in findings if finding is not None]


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"failed to read CodeQL SARIF output: {error}") from error

    result = _object_mapping(data)

    if result is None:
        raise RuntimeError("CodeQL SARIF output root is not an object")

    return result


def _finding_from_result(
    result: Mapping[str, object],
    root: Path,
    included_roots: Sequence[Path],
) -> CodeqlFinding | None:
    location = _primary_location(result)

    if location is None:
        return None

    artifact = _object_mapping(location.get("artifactLocation"))
    uri = _string(artifact.get("uri") if artifact is not None else None)

    if uri is None:
        return None

    path = _path_from_uri(uri, root)

    if not _is_included(path, included_roots):
        return None

    return CodeqlFinding(
        path=_display_path(path, root),
        line=_line_number(location),
        rule_id=_rule_id(result),
        message=_message(result),
    )


def _primary_location(result: Mapping[str, object]) -> Mapping[str, object] | None:
    locations = _object_list(result.get("locations"))

    if not locations:
        return None

    physical = _object_mapping(locations[0].get("physicalLocation"))

    return physical


def _path_from_uri(uri: str, root: Path) -> Path:
    parsed = urlparse(uri)

    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).resolve()

    return (root / unquote(uri)).resolve()


def _line_number(location: Mapping[str, object]) -> int:
    region = _object_mapping(location.get("region"))

    if region is None:
        return 1

    line = region.get("startLine")

    return line if isinstance(line, int) and not isinstance(line, bool) and line > 0 else 1


def _message(result: Mapping[str, object]) -> str:
    message = _object_mapping(result.get("message"))
    text = _string(message.get("text") if message is not None else None)

    return text or "CodeQL finding"


def _rule_id(result: Mapping[str, object]) -> str:
    return _string(result.get("ruleId")) or "codeql"


def _resolve_path(root: Path, path: Path) -> Path:
    candidate = path if path.is_absolute() else root / path

    return candidate.resolve()


def _is_included(path: Path, included_roots: Sequence[Path]) -> bool:
    return any(_is_relative_to(path, included_root) for included_root in included_roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False

    return True


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []

    return [mapping for item in value if (mapping := _object_mapping(item)) is not None]


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None

    return {key: item for key, item in value.items() if isinstance(key, str)}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
