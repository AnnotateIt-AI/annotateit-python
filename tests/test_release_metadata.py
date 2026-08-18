from __future__ import annotations

from importlib.metadata import metadata, version
from pathlib import Path

from annotateit_ai import __version__


def test_installed_release_metadata() -> None:
    package_metadata = metadata("annotateit-ai")

    assert version("annotateit-ai") == __version__
    assert package_metadata["License-Expression"] == "Apache-2.0"
    assert "LICENSE" in package_metadata.get_all("License-File", [])
    assert set(package_metadata.get_all("Project-URL", [])) == {
        "Homepage, https://annotateit.ai",
        "Issues, https://github.com/AnnotateIt-AI/annotateit-python/issues",
        "Repository, https://github.com/AnnotateIt-AI/annotateit-python",
    }


def test_repository_contains_the_apache_2_license() -> None:
    license_text = (Path(__file__).resolve().parent.parent / "LICENSE").read_text(encoding="utf-8")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
