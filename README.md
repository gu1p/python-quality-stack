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
