from __future__ import annotations

import io
from collections.abc import Mapping
from pathlib import Path

import httpx

from annotateit_ai import Client
from annotateit_ai.cli import run


def client_factory(transport: httpx.BaseTransport):
    def create(url: str, token: str | None, environ: Mapping[str, str]) -> Client:
        return Client(url, token, check_compatibility=False, transport=transport, env=environ)

    return create


def test_cli_calls_real_sdk_transport_with_auth_and_version_preflight() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/product-info"):
            return httpx.Response(200, json={"apiVersion": "1.0.0"})
        return httpx.Response(200, json={"status": "ok"})

    stdout = io.StringIO()
    code = run(
        ["status", "--json"],
        environ={"ANNOTATEIT_TOKEN": "secret"},
        stdout=stdout,
        stderr=io.StringIO(),
        executor_factory=client_factory(httpx.MockTransport(handler)),
    )
    assert code == 0
    assert [request.url.path for request in requests] == ["/api/v1/product-info", "/api/v1/status"]
    assert all(request.headers["authorization"] == "Bearer secret" for request in requests)
    assert stdout.getvalue().strip() == '{\n  "status": "ok"\n}'


def test_cli_streams_download_through_real_sdk_transport(tmp_path: Path) -> None:
    content = b"\x00annotateit-archive\xff"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/projects/p/datasets/d/media/m/content"
        return httpx.Response(200, content=content, headers={"content-type": "application/octet-stream"})

    destination = tmp_path / "nested" / "media.bin"
    code = run(
        [
            "media",
            "download",
            "p",
            "d",
            "m",
            "--out",
            str(destination),
            "--json",
            "--no-version-check",
        ],
        environ={"ANNOTATEIT_TOKEN": "secret"},
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        executor_factory=client_factory(httpx.MockTransport(handler)),
    )
    assert code == 0
    assert destination.read_bytes() == content


def test_cli_streams_multipart_upload_through_real_sdk_transport(tmp_path: Path) -> None:
    source = tmp_path / "frame.jpg"
    source.write_bytes(b"jpeg-data")
    seen_body = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_body
        assert request.url.path == "/api/v1/projects/p/datasets/d/media"
        assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
        seen_body = request.read()
        return httpx.Response(201, json={"id": "m", "name": "frame.jpg", "type": "image"})

    code = run(
        ["media", "upload", "p", "d", str(source), "--json", "--no-version-check"],
        environ={"ANNOTATEIT_TOKEN": "secret"},
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        executor_factory=client_factory(httpx.MockTransport(handler)),
    )
    assert code == 0
    assert b'filename="frame.jpg"' in seen_body
    assert b"jpeg-data" in seen_body
