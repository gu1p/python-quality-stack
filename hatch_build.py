from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PLATFORM_TAGS = {
    "linux64": "py3-none-manylinux_2_17_x86_64",
    "osx64": "py3-none-macosx_10_13_x86_64",
    "win64": "py3-none-win_amd64",
}


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        platform_id = os.environ.get("PYTHON_QUALITY_CODEQL_PLATFORM")

        if self.target_name != "wheel" or not platform_id:
            return

        if platform_id not in PLATFORM_TAGS:
            supported = ", ".join(sorted(PLATFORM_TAGS))
            message = f"unsupported PYTHON_QUALITY_CODEQL_PLATFORM={platform_id!r}; expected one of: {supported}"

            raise ValueError(message)

        vendor_root = Path(self.root) / "src" / "python_quality_stack" / "_vendor" / "codeql" / platform_id

        if not vendor_root.exists():
            raise FileNotFoundError(f"missing vendored CodeQL bundle: {vendor_root}")

        force_include = build_data.setdefault("force_include", {})

        if not isinstance(force_include, dict):
            raise TypeError("hatch build_data['force_include'] must be a dictionary")

        force_include[vendor_root.as_posix()] = f"python_quality_stack/_vendor/codeql/{platform_id}"
        build_data["pure_python"] = False
        build_data["tag"] = PLATFORM_TAGS[platform_id]
