from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
from collections.abc import Sequence
from pathlib import Path

CODEQL_VERSION = "2.25.5"
CODEQL_BUNDLE_DIGESTS = {
    "linux64": "24717f939f1bef659f893ff4a9c99ba8c056fbaca9640f877c4dc74cf96486d7",
    "osx64": "c365f6c41145b97150c32026f72df1d02060b15c560588785e764eec10be945e",
    "win64": "6bef9bd2e61a7b3bca91c19637e5607a5fc887b2cf8b73e7c202516f4df773e1",
}
RELEASE_BASE_URL = "https://github.com/github/codeql-action/releases/download"
VENDOR_ROOT = Path("src/python_quality_stack/_vendor/codeql")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    platform_id = args.platform
    archive_name = f"codeql-bundle-{platform_id}.tar.gz"
    url = f"{RELEASE_BASE_URL}/codeql-bundle-v{CODEQL_VERSION}/{archive_name}"

    with tempfile.TemporaryDirectory(prefix="python-quality-codeql-vendor-") as temp:
        archive_path = Path(temp) / archive_name

        _download(url, archive_path)

        _verify_digest(archive_path, CODEQL_BUNDLE_DIGESTS[platform_id])

        _replace_vendor_bundle(archive_path, VENDOR_ROOT / platform_id)

    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and vendor the pinned CodeQL bundle.")
    parser.add_argument("platform", choices=sorted(CODEQL_BUNDLE_DIGESTS))

    return parser.parse_args(argv)


def _download(url: str, destination: Path) -> None:
    print(f"Downloading {url}")

    with urllib.request.urlopen(url, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _verify_digest(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()

    if actual != expected:
        raise RuntimeError(f"checksum mismatch for {path.name}: expected {expected}, got {actual}")


def _replace_vendor_bundle(archive_path: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)

    destination.mkdir()

    with tarfile.open(archive_path, "r:gz") as archive:
        _safe_extract(archive, destination)

    binary = destination / "codeql" / ("codeql.exe" if destination.name == "win64" else "codeql")

    if not binary.exists():
        raise RuntimeError(f"extracted archive does not contain expected CodeQL binary: {binary}")

    print(f"Vendored CodeQL bundle at {destination}")


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    destination_root = destination.resolve()

    for member in archive.getmembers():
        member_path = (destination / member.name).resolve()

        if not _is_relative_to(member_path, destination_root):
            raise RuntimeError(f"archive member escapes destination: {member.name}")

    archive.extractall(destination)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False

    return True


if __name__ == "__main__":
    raise SystemExit(main())
