# vertical-spacing

Dependency-free Python formatter for readable vertical spacing inside functions.

It is designed to run alongside Ruff or Black. Those tools handle canonical Python formatting; this tool adds repo-enforced logical spacing between statement groups.

## Usage

```bash
vertical-spacing --check src tests scripts
vertical-spacing --fix src tests scripts
```

Rules:

- Insert one blank line after completed compound blocks before same-indent code.
- Insert one blank line before a final `return` or `raise`.
- Insert one blank line before control-flow blocks when they follow setup statements.
- Insert one blank line after multiline setup statements before the next statement.
- Keep attached `elif`, `else`, `except`, and `finally` clauses tight.
- Collapse multiple blank lines inside functions to one.
- Preserve comment boundaries and multiline string contents.
