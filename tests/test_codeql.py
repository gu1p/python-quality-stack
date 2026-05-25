from __future__ import annotations

import json
from pathlib import Path

import pytest

from python_quality_stack import codeql


@pytest.fixture(autouse=True)
def clear_codeql_skip_env(monkeypatch) -> None:
    monkeypatch.delenv(codeql.SKIP_ENV, raising=False)


def test_codeql_check_can_be_skipped(monkeypatch, capsys) -> None:
    monkeypatch.setenv(codeql.SKIP_ENV, "1")

    assert codeql.run_codeql_check((Path("src"),)) == 0
    assert "skipped" in capsys.readouterr().out


def test_codeql_check_fails_when_bundle_is_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(codeql, "_bundled_binary", lambda: None)

    (tmp_path / "src").mkdir()

    assert codeql.run_codeql_check((Path("src"),)) == 1
    assert "bundled CodeQL is unavailable" in capsys.readouterr().out


def test_codeql_check_reports_sarif_findings(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(codeql, "_bundled_binary", lambda: tmp_path / "codeql")
    monkeypatch.setattr(codeql, "_ensure_executable", lambda binary: True)

    (tmp_path / "codeql").write_text("", encoding="utf-8")

    _write(tmp_path / "src" / "pkg" / "models.py", "CORE_EVENT_SLOTS = frozenset()\n")

    def fake_run(command: list[str]) -> int:
        if "analyze" in command:
            output_path = Path(command[command.index("--output") + 1])
            _write_sarif(output_path, "src/pkg/models.py", 1, "Unused global variable 'CORE_EVENT_SLOTS'")

        return 0

    monkeypatch.setattr(codeql, "_run_command", fake_run)

    assert codeql.run_codeql_check((Path("src"),)) == 1
    output = capsys.readouterr().out
    assert "src/pkg/models.py:1: py/unused-global-variable: Unused global variable 'CORE_EVENT_SLOTS'" in output


def test_codeql_check_ignores_findings_outside_configured_paths(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(codeql, "_bundled_binary", lambda: tmp_path / "codeql")
    monkeypatch.setattr(codeql, "_ensure_executable", lambda binary: True)

    (tmp_path / "codeql").write_text("", encoding="utf-8")

    (tmp_path / "src").mkdir()

    _write(tmp_path / "ignored" / "models.py", "UNUSED = 1\n")

    def fake_run(command: list[str]) -> int:
        if "analyze" in command:
            output_path = Path(command[command.index("--output") + 1])
            _write_sarif(output_path, "ignored/models.py", 1, "Unused global variable 'UNUSED'")

        return 0

    monkeypatch.setattr(codeql, "_run_command", fake_run)

    assert codeql.run_codeql_check((Path("src"),)) == 0
    assert "CodeQL dead-code check passed" in capsys.readouterr().out


def test_codeql_command_uses_database_create_and_analyze(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(codeql, "_bundled_binary", lambda: tmp_path / "codeql")
    monkeypatch.setattr(codeql, "_ensure_executable", lambda binary: True)

    (tmp_path / "codeql").write_text("", encoding="utf-8")

    (tmp_path / "src").mkdir()
    commands: list[list[str]] = []

    def fake_run(command: list[str]) -> int:
        commands.append(command)

        if "analyze" in command:
            output_path = Path(command[command.index("--output") + 1])
            _write_sarif(output_path, "src/pkg/models.py", 1, "Unused global variable")

        return 0

    monkeypatch.setattr(codeql, "_run_command", fake_run)

    assert codeql.run_codeql_check((Path("src"),)) == 1
    assert commands[0][1:4] == ["database", "create", commands[0][3]]
    assert "--build-mode=none" in commands[0]
    assert commands[1][1:3] == ["database", "analyze"]
    assert codeql.CODEQL_QUERY_SUITE in commands[1]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(content, encoding="utf-8")


def _write_sarif(path: Path, uri: str, line: int, message: str) -> None:
    path.write_text(
        json.dumps(
            {
                "runs": [
                    {
                        "results": [
                            {
                                "ruleId": "py/unused-global-variable",
                                "message": {"text": message},
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {"uri": uri},
                                            "region": {"startLine": line},
                                        }
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
