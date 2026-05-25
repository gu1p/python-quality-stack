# python-quality-stack

Opinionated Python quality stack orchestrator.

The tool wraps maintained Python quality tools and a small vertical-spacing formatter behind one CLI:

```bash
python-quality format
python-quality check
python-quality lint
python-quality typecheck
python-quality dead-code
python-quality complexity
python-quality quality-guards
python-quality version-check
```

It delegates to:

- `ruff format`
- `ruff check`
- `ty check`
- `pyright`
- `mypy`
- `complexipy`
- `vulture`
- bundled CodeQL security-and-quality analysis
- `pytest`
- built-in vertical spacing checks
- built-in static quality guards

Configuration lives in `pyproject.toml`.

```toml
[tool.python-quality]
paths = ["src", "tests", "scripts"]

[tool.python-quality.vertical-spacing]
paths = ["src", "tests", "scripts"]

[tool.python-quality.dead-code]
paths = ["src", "tests", "scripts"]
min-confidence = 100

[tool.python-quality.static-guards]
python-roots = ["src", "tests"]
text-roots = ["src", "tests"]
dynamic-typing-allowlist = []
strict-no-get-files = []

[tool.python-quality.enum-reachability]
models-path = "src/package/models.py"
model-module = "package.models"
reference-roots = ["src/package"]
excluded-paths = []
allow-marker = "allow-unused-enum:"
```

`python-quality format` runs Ruff, then the built-in vertical-spacing fixer, then Ruff again.
`python-quality check` runs the full configured Python quality stack.

`python-quality check` starts with a soft freshness check. If the installed Git commit is behind `main`,
the check fails and prints the `uv lock --upgrade-package python-quality-stack` command. If GitHub is
unavailable or the installed commit cannot be determined, it prints a warning and continues. Set
`PYTHON_QUALITY_SKIP_VERSION_CHECK=1` to skip it explicitly.

`python-quality dead-code` runs Vulture first, then the bundled CodeQL Python `security-and-quality`
suite. The CodeQL pass is bundled into platform-specific wheels and does not download anything at
runtime. Set `PYTHON_QUALITY_SKIP_CODEQL=1` only as a temporary local escape hatch.

## Bundled CodeQL wheels

Release wheels are built with the official CodeQL bundle from `github/codeql-action`, pinned in
`scripts/vendor_codeql.py`. The supported bundle platforms are:

- `linux64`
- `osx64`
- `win64`

Build a bundled wheel for one platform with:

```bash
python scripts/vendor_codeql.py linux64
PYTHON_QUALITY_CODEQL_PLATFORM=linux64 python -m build --wheel
```

The custom Hatch build hook marks the wheel as platform-specific and includes the vendored CodeQL
bundle. Source installs or unbundled wheels fail the CodeQL phase with an actionable install message.
