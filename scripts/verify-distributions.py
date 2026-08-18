from __future__ import annotations

import argparse
import tarfile
import zipfile
from email.message import Message
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath

from annotateit_ai import __version__

PACKAGE_NAME = "annotateit-ai"
IMPORT_PACKAGE = "annotateit_ai"
EXPECTED_PROJECT_URLS = {
    "Homepage": "https://annotateit.ai",
    "Issues": "https://github.com/AnnotateIt-AI/annotateit-python/issues",
    "Repository": "https://github.com/AnnotateIt-AI/annotateit-python",
}
REQUIRED_PACKAGE_FILES = {
    f"{IMPORT_PACKAGE}/py.typed",
    f"{IMPORT_PACKAGE}/openapi/annotateit-v1.openapi.json",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _single(paths: list[Path], description: str) -> Path:
    _require(len(paths) == 1, f"Expected exactly one {description}, found {len(paths)}.")
    return paths[0]


def _metadata_from_wheel(archive: zipfile.ZipFile, names: set[str]) -> tuple[Message, str]:
    metadata_name = _single(
        [Path(name) for name in names if name.endswith(".dist-info/METADATA")],
        "wheel METADATA file",
    ).as_posix()
    return BytesParser(policy=default).parsebytes(archive.read(metadata_name)), metadata_name.removesuffix("METADATA")


def _project_urls(metadata: Message) -> dict[str, str]:
    values = metadata.get_all("Project-URL", [])
    _require(len(values) == len(EXPECTED_PROJECT_URLS), "Unexpected number of Project-URL metadata entries.")
    urls: dict[str, str] = {}
    for value in values:
        label, separator, url = value.partition(",")
        _require(bool(separator), f"Malformed Project-URL metadata: {value!r}.")
        urls[label.strip()] = url.strip()
    return urls


def _verify_metadata(metadata: Message) -> None:
    _require(metadata["Name"] == PACKAGE_NAME, f"Unexpected package name: {metadata['Name']!r}.")
    _require(metadata["Version"] == __version__, f"Unexpected package version: {metadata['Version']!r}.")
    _require(metadata["Metadata-Version"] == "2.4", "The distributions must use Metadata-Version 2.4.")
    _require(metadata["License-Expression"] == "Apache-2.0", "Missing Apache-2.0 license expression.")
    _require("LICENSE" in metadata.get_all("License-File", []), "Missing LICENSE metadata entry.")
    _require(metadata["Requires-Python"] == ">=3.10", "Unexpected Requires-Python metadata.")
    _require(_project_urls(metadata) == EXPECTED_PROJECT_URLS, "Project URLs do not match the release contract.")


def _verify_wheel(wheel: Path, license_bytes: bytes) -> None:
    expected_suffix = f"-{__version__}-py3-none-any.whl"
    _require(wheel.name.endswith(expected_suffix), f"Wheel is not the expected universal wheel: {wheel.name}.")

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata, dist_info_prefix = _metadata_from_wheel(archive, names)
        _verify_metadata(metadata)

        wheel_metadata = archive.read(f"{dist_info_prefix}WHEEL").decode("utf-8")
        _require("Root-Is-Purelib: true" in wheel_metadata, "Wheel is not marked as pure Python.")
        _require("Tag: py3-none-any" in wheel_metadata, "Wheel does not carry the py3-none-any tag.")

        entry_points = archive.read(f"{dist_info_prefix}entry_points.txt").decode("utf-8")
        _require(
            "annotateit = annotateit_ai.cli:main" in entry_points,
            "Wheel is missing the annotateit console entry point.",
        )
        _require(REQUIRED_PACKAGE_FILES <= names, "Wheel is missing py.typed or the OpenAPI contract.")

        license_name = f"{dist_info_prefix}licenses/LICENSE"
        _require(license_name in names, "Wheel is missing its bundled LICENSE file.")
        _require(archive.read(license_name) == license_bytes, "Bundled wheel license differs from repository LICENSE.")


def _verify_sdist(sdist: Path, license_bytes: bytes) -> None:
    expected_suffix = f"-{__version__}.tar.gz"
    _require(sdist.name.endswith(expected_suffix), f"Unexpected source distribution name: {sdist.name}.")

    with tarfile.open(sdist, mode="r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        roots = {PurePosixPath(name).parts[0] for name in members}
        _require(len(roots) == 1, "Source distribution must have exactly one archive root.")
        root = roots.pop()
        _require(root == f"{IMPORT_PACKAGE}-{__version__}", f"Unexpected source distribution root: {root}.")
        required = {
            f"{root}/LICENSE",
            f"{root}/PKG-INFO",
            f"{root}/README.md",
            f"{root}/pyproject.toml",
            f"{root}/src/{IMPORT_PACKAGE}/py.typed",
            f"{root}/src/{IMPORT_PACKAGE}/openapi/annotateit-v1.openapi.json",
        }
        _require(required <= members.keys(), "Source distribution is missing required release files.")

        license_file = archive.extractfile(members[f"{root}/LICENSE"])
        _require(license_file is not None, "Could not read LICENSE from the source distribution.")
        _require(license_file.read() == license_bytes, "Bundled source license differs from repository LICENSE.")

        package_metadata_file = archive.extractfile(members[f"{root}/PKG-INFO"])
        _require(package_metadata_file is not None, "Could not read PKG-INFO from the source distribution.")
        _verify_metadata(BytesParser(policy=default).parsebytes(package_metadata_file.read()))


def verify_distributions(distribution_directory: Path) -> None:
    repository_root = Path(__file__).resolve().parent.parent
    license_bytes = (repository_root / "LICENSE").read_bytes()
    _require(b"Apache License" in license_bytes, "Repository LICENSE is not the Apache License.")

    files = sorted(path for path in distribution_directory.iterdir() if path.is_file())
    wheel = _single([path for path in files if path.suffix == ".whl"], "wheel")
    sdist = _single([path for path in files if path.name.endswith(".tar.gz")], "source distribution")
    _require(len(files) == 2, f"Distribution directory contains unexpected files: {[path.name for path in files]}.")

    _verify_wheel(wheel, license_bytes)
    _verify_sdist(sdist, license_bytes)
    print(f"Verified {wheel.name} and {sdist.name} for PyPI publication.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify built AnnotateIt Python distributions.")
    parser.add_argument("distribution_directory", type=Path)
    arguments = parser.parse_args()
    verify_distributions(arguments.distribution_directory.resolve())


if __name__ == "__main__":
    main()
