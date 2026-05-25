from __future__ import annotations

from pathlib import Path

from python_quality_stack.config import EnumReachabilityConfig, StaticGuardConfig
from python_quality_stack.guards import guard_failures


DISABLED_ENUMS = EnumReachabilityConfig(
    enabled=False,
    models_path=Path(),
    model_module="",
    reference_roots=(),
    excluded_paths=frozenset(),
    allow_marker="allow-unused-enum:",
)


def test_static_guards_reject_dynamic_typing_outside_allowlist(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "pkg" / "module.py",
        """
        from typing import Any

        value: Any = 1
        """,
    )

    failures = guard_failures(
        tmp_path.resolve(),
        StaticGuardConfig(
            enabled=True,
            python_roots=(Path("src"),),
            text_roots=(Path("src"),),
            dynamic_typing_allowlist=frozenset(),
            strict_no_get_files=frozenset(),
        ),
        DISABLED_ENUMS,
    )

    assert any("dynamic typing is only allowed" in failure for failure in failures)


def test_static_guards_allow_dynamic_typing_at_configured_edges(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "pkg" / "module.py",
        """
        from typing import Any

        value: Any = 1
        """,
    )

    failures = guard_failures(
        tmp_path.resolve(),
        StaticGuardConfig(
            enabled=True,
            python_roots=(Path("src"),),
            text_roots=(Path("src"),),
            dynamic_typing_allowlist=frozenset({"src/pkg/module.py"}),
            strict_no_get_files=frozenset(),
        ),
        DISABLED_ENUMS,
    )

    assert failures == []


def test_enum_reachability_rejects_unreferenced_members(tmp_path: Path) -> None:
    models_path = tmp_path / "src" / "pkg" / "models.py"
    _write(
        models_path,
        """
        from enum import StrEnum


        class Example(StrEnum):
            USED = "used"
            UNUSED = "unused"
        """,
    )

    _write(tmp_path / "src" / "pkg" / "usage.py", "from pkg.models import Example\n\nvalue = Example.USED\n")

    failures = guard_failures(
        tmp_path.resolve(),
        StaticGuardConfig(False, (), (), frozenset(), frozenset()),
        EnumReachabilityConfig(
            enabled=True,
            models_path=Path("src/pkg/models.py"),
            model_module="pkg.models",
            reference_roots=(Path("src/pkg"),),
            excluded_paths=frozenset(),
            allow_marker="allow-unused-enum:",
        ),
    )

    assert any("Example.UNUSED has no production reference" in failure for failure in failures)


def test_enum_reachability_accepts_unused_member_with_reason(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "pkg" / "models.py",
        """
        from enum import StrEnum


        class Example(StrEnum):
            USED = "used"
            UNUSED = "unused"  # allow-unused-enum: accepted API value
        """,
    )

    _write(tmp_path / "src" / "pkg" / "usage.py", "from pkg.models import Example\n\nvalue = Example.USED\n")

    failures = guard_failures(
        tmp_path.resolve(),
        StaticGuardConfig(False, (), (), frozenset(), frozenset()),
        EnumReachabilityConfig(
            enabled=True,
            models_path=Path("src/pkg/models.py"),
            model_module="pkg.models",
            reference_roots=(Path("src/pkg"),),
            excluded_paths=frozenset(),
            allow_marker="allow-unused-enum:",
        ),
    )

    assert failures == []


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(_dedent(content), encoding="utf-8")


def _dedent(content: str) -> str:
    lines = content.strip("\n").splitlines()
    indentation = min(len(line) - len(line.lstrip()) for line in lines if line.strip())

    return "\n".join(line[indentation:] for line in lines) + "\n"
