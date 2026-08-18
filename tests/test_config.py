from __future__ import annotations

import pytest

from annotateit_ai import ClientConfig, ConfigurationError, normalize_base_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8420", "http://127.0.0.1:8420/api/v1"),
        ("localhost:9000", "http://localhost:9000/api/v1"),
        ("http://127.0.0.1:8420/", "http://127.0.0.1:8420/api/v1"),
        ("https://desktop.example/prefix", "https://desktop.example/prefix/api/v1"),
        ("https://desktop.example/api/v1/", "https://desktop.example/api/v1"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    assert normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "0",
        "65536",
        "ftp://localhost:8420",
        "http://user:secret@localhost:8420",
        "http://localhost:8420/api/v2",
        "http://localhost:8420?debug=true",
        "http://localhost:8420/#fragment",
    ],
)
def test_normalize_base_url_rejects_unsafe_or_incompatible_values(raw: str) -> None:
    with pytest.raises(ConfigurationError):
        normalize_base_url(raw)


def test_config_precedence_and_environment() -> None:
    config = ClientConfig.resolve(
        None,
        None,
        env={"ANNOTATEIT_URL": "9001", "ANNOTATEIT_TOKEN": " env-token "},
    )
    assert config.base_url == "http://127.0.0.1:9001/api/v1"
    assert config.token == "env-token"

    explicit = ClientConfig.resolve(
        "https://app.example",
        " explicit-token ",
        env={"ANNOTATEIT_URL": "9001", "ANNOTATEIT_TOKEN": "env-token"},
    )
    assert explicit.base_url == "https://app.example/api/v1"
    assert explicit.token == "explicit-token"
