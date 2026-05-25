from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, (Path(__file__).resolve().parents[1] / "src").as_posix())

from python_quality_stack.codeql import (  # noqa: E402
    CODEQL_BUNDLE_DIGESTS,
    CODEQL_VERSION,
    _archive_name,
    _archive_url,
    _bundle_binary_path,
    _download_file,
    _extract_archive,
    _verify_digest,
)

VENDOR_ROOT = Path("src/python_quality_stack/_vendor/codeql")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    platform_id = args.platform

    with tempfile.TemporaryDirectory(prefix="python-quality-codeql-vendor-") as temp:
        archive_path = Path(temp) / _archive_name(platform_id)

        _download_file(_archive_url(platform_id), archive_path)

        _verify_digest(archive_path, CODEQL_BUNDLE_DIGESTS[platform_id])

        _replace_vendor_bundle(archive_path, platform_id)

    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Download and vendor CodeQL {CODEQL_VERSION}.")
    parser.add_argument("platform", choices=sorted(CODEQL_BUNDLE_DIGESTS))

    return parser.parse_args(argv)


def _replace_vendor_bundle(archive_path: Path, platform_id: str) -> None:
    destination = VENDOR_ROOT / platform_id

    if destination.exists():
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)

    destination.mkdir()

    _extract_archive(archive_path, destination)

    binary = _bundle_binary_path(destination, platform_id)

    if not binary.exists():
        raise RuntimeError(f"extracted archive does not contain expected CodeQL binary: {binary}")

    print(f"Vendored CodeQL bundle at {destination}")


if __name__ == "__main__":
    raise SystemExit(main())
