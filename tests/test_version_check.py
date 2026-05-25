from __future__ import annotations

from python_quality_stack import version_check


def test_version_check_passes_when_current(monkeypatch, capsys) -> None:
    monkeypatch.setattr(version_check, "_installed_commit", lambda: "a" * 40)
    monkeypatch.setattr(version_check, "_latest_commit", lambda: "a" * 40)

    assert version_check.check_latest() == 0
    assert "is current" in capsys.readouterr().out


def test_version_check_fails_when_installed_commit_is_behind(monkeypatch, capsys) -> None:
    monkeypatch.setattr(version_check, "_installed_commit", lambda: "a" * 40)
    monkeypatch.setattr(version_check, "_latest_commit", lambda: "b" * 40)

    assert version_check.check_latest() == 1
    assert "uv lock --upgrade-package python-quality-stack" in capsys.readouterr().out


def test_version_check_continues_without_installed_commit(monkeypatch, capsys) -> None:
    monkeypatch.setattr(version_check, "_installed_commit", lambda: None)

    assert version_check.check_latest() == 0
    assert "warning:" in capsys.readouterr().out


def test_version_check_continues_without_network(monkeypatch, capsys) -> None:
    monkeypatch.setattr(version_check, "_installed_commit", lambda: "a" * 40)
    monkeypatch.setattr(version_check, "_latest_commit", lambda: None)

    assert version_check.check_latest() == 0
    assert "warning:" in capsys.readouterr().out


def test_version_check_can_be_skipped(monkeypatch, capsys) -> None:
    monkeypatch.setenv(version_check.SKIP_ENV, "1")
    monkeypatch.setattr(version_check, "_installed_commit", lambda: "a" * 40)
    monkeypatch.setattr(version_check, "_latest_commit", lambda: "b" * 40)

    assert version_check.check_latest() == 0
    assert "skipped" in capsys.readouterr().out


def test_commit_from_direct_url_reads_git_commit() -> None:
    assert version_check._commit_from_direct_url('{"vcs_info": {"commit_id": "abc123", "vcs": "git"}}') == "abc123"


def test_commit_from_ls_remote_reads_ref_commit() -> None:
    assert version_check._commit_from_ls_remote("abc123\trefs/heads/main\n") == "abc123"
