from __future__ import annotations

import subprocess
from collections.abc import Sequence


def run(command: Sequence[str]) -> int:
    print(f"$ {' '.join(command)}", flush=True)

    return subprocess.run(command, check=False).returncode


def run_all(commands: Sequence[Sequence[str]]) -> int:
    for command in commands:
        status = run(command)

        if status != 0:
            return status

    return 0
