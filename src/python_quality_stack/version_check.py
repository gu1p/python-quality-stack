from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from importlib import metadata

PACKAGE_NAME = "python-quality-stack"
REMOTE_URL = "https://github.com/gu1p/python-quality-stack.git"
MAIN_REF = "refs/heads/main"
SKIP_ENV = "PYTHON_QUALITY_SKIP_VERSION_CHECK"


def check_latest() -> int:
    if _should_skip():
        print(f"python-quality-stack version check skipped via {SKIP_ENV}=1")

        return 0

    installed = _installed_commit()

    if installed is None:
        _warn("could not determine installed python-quality-stack commit; continuing")

        return 0

    latest = _latest_commit()

    if latest is None:
        _warn("could not verify latest python-quality-stack version; continuing")

        return 0

    if _same_commit(installed, latest):
        print(f"python-quality-stack is current: {_short(installed)}")

        return 0

    _print_behind(installed, latest)

    return 1


def _should_skip() -> bool:
    return os.environ.get(SKIP_ENV) == "1"


def _installed_commit() -> str | None:
    try:
        direct_url = metadata.distribution(PACKAGE_NAME).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None

    if not direct_url:
        return None

    return _commit_from_direct_url(direct_url)


def _commit_from_direct_url(text: str) -> str | None:
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError:
        return None

    values = _object_mapping(data)

    if values is None:
        return None

    vcs_info = _object_mapping(values.get("vcs_info"))

    if vcs_info is None:
        return None

    commit = vcs_info.get("commit_id")

    return commit if isinstance(commit, str) and commit else None


def _object_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None

    return {key: item for key, item in value.items() if isinstance(key, str)}


def _latest_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "ls-remote", REMOTE_URL, MAIN_REF],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    return _commit_from_ls_remote(result.stdout)


def _commit_from_ls_remote(output: str) -> str | None:
    first_line = output.splitlines()[0] if output.splitlines() else ""
    commit = first_line.split()[0] if first_line.split() else ""

    return commit or None


def _same_commit(installed: str, latest: str) -> bool:
    return installed == latest or installed.startswith(latest) or latest.startswith(installed)


def _short(commit: str) -> str:
    return commit[:8]


def _warn(message: str) -> None:
    print(f"warning: {message}")


def _print_behind(installed: str, latest: str) -> None:
    print("python-quality-stack is behind:")

    print(f"  installed: {_short(installed)}")

    print(f"  latest:    {_short(latest)}")

    print("Run: uv lock --upgrade-package python-quality-stack")
