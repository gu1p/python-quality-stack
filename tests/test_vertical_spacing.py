from __future__ import annotations

import textwrap
from pathlib import Path

from vertical_spacing import format_file, format_text


def test_vertical_spacing_separates_repository_style_blocks() -> None:
    assert _format(
        """
        def _repository(app):
            if app.state.repository is None:
                repository_db_path = app.state.repository_db_path
                if not isinstance(repository_db_path, Path):
                    raise TypeError("repository path state has an invalid type")
                app.state.repository = SQLiteAnamnesisRepository(repository_db_path)
            repository = app.state.repository
            if isinstance(repository, SQLiteAnamnesisRepository):
                return repository
            raise TypeError("app repository state has an invalid type")
        """
    ) == _source(
        """
        def _repository(app):
            if app.state.repository is None:
                repository_db_path = app.state.repository_db_path

                if not isinstance(repository_db_path, Path):
                    raise TypeError("repository path state has an invalid type")

                app.state.repository = SQLiteAnamnesisRepository(repository_db_path)

            repository = app.state.repository

            if isinstance(repository, SQLiteAnamnesisRepository):
                return repository

            raise TypeError("app repository state has an invalid type")
        """
    )


def test_vertical_spacing_separates_setup_blocks_and_final_return() -> None:
    assert _format(
        """
        def _build_openrouter_http_client():
            _load_dotenv()
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not set")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            referer = os.environ.get("OPENROUTER_HTTP_REFERER")
            title = os.environ.get("OPENROUTER_APP_TITLE")
            if referer:
                headers["HTTP-Referer"] = referer
            if title:
                headers["X-Title"] = title
            return httpx.Client(base_url=OPENROUTER_BASE_URL, headers=headers, timeout=120)
        """
    ) == _source(
        """
        def _build_openrouter_http_client():
            _load_dotenv()
            api_key = os.environ.get("OPENROUTER_API_KEY")

            if not api_key:
                raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY is not set")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            referer = os.environ.get("OPENROUTER_HTTP_REFERER")
            title = os.environ.get("OPENROUTER_APP_TITLE")

            if referer:
                headers["HTTP-Referer"] = referer

            if title:
                headers["X-Title"] = title

            return httpx.Client(base_url=OPENROUTER_BASE_URL, headers=headers, timeout=120)
        """
    )


def test_vertical_spacing_keeps_attached_continuation_clauses_tight() -> None:
    assert _format(
        """
        def choose(value):
            if value == 1:
                label = "one"
            elif value == 2:
                label = "two"
            else:
                label = "many"

            return label
        """
    ) == _source(
        """
        def choose(value):
            if value == 1:
                label = "one"
            elif value == 2:
                label = "two"
            else:
                label = "many"

            return label
        """
    )


def test_vertical_spacing_collapses_extra_blank_lines_inside_functions() -> None:
    assert _format(
        """
        def calculate():
            first = 1


            second = 2


            return first + second
        """
    ) == _source(
        """
        def calculate():
            first = 1

            second = 2

            return first + second
        """
    )


def test_vertical_spacing_preserves_multiline_string_contents() -> None:
    assert _format(
        """
        def prompt():
            text = \"\"\"
            alpha


            beta
            \"\"\"
            return text
        """
    ) == _source(
        """
        def prompt():
            text = \"\"\"
            alpha


            beta
            \"\"\"

            return text
        """
    )


def test_vertical_spacing_preserves_comment_boundaries() -> None:
    assert _format(
        """
        def calculate():
            value = 1
            # The branch is deliberately next to this explanation.
            if value:
                return value
            return 0
        """
    ) == _source(
        """
        def calculate():
            value = 1
            # The branch is deliberately next to this explanation.
            if value:
                return value

            return 0
        """
    )


def test_vertical_spacing_check_mode_does_not_rewrite(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    original = _source(
        """
        def calculate():
            if ready():
                value = 1
            return value
        """
    )

    path.write_text(original, encoding="utf-8")

    changed = format_file(path, fix=False)

    assert changed is True
    assert path.read_text(encoding="utf-8") == original


def test_vertical_spacing_fix_mode_rewrites(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        _source(
            """
            def calculate():
                if ready():
                    value = 1
                return value
            """
        ),
        encoding="utf-8",
    )

    changed = format_file(path, fix=True)

    assert changed is True
    assert path.read_text(encoding="utf-8") == _source(
        """
        def calculate():
            if ready():
                value = 1

            return value
        """
    )


def _format(source: str) -> str:
    return format_text(_source(source))


def _source(source: str) -> str:
    return textwrap.dedent(source).lstrip()
