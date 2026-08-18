from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from annotateit_ai import Client, FileTransferError, TransportError


class ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes], *, fail_after: bool = False) -> None:
        self.chunks = chunks
        self.fail_after = fail_after
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks
        if self.fail_after:
            raise httpx.ReadError("stream interrupted")

    def close(self) -> None:
        self.closed = True


def test_download_streams_and_creates_parent_directories(tmp_path: Path) -> None:
    stream = ChunkStream([b"first", b"-", b"second"])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    destination = tmp_path / "nested" / "media.bin"
    with Client(check_compatibility=False, transport=httpx.MockTransport(handler)) as client:
        returned = client.media.download("p", "d", "m", destination)

    assert returned == destination
    assert destination.read_bytes() == b"first-second"
    assert stream.closed
    assert not list(destination.parent.glob("*.part"))


def test_failed_download_preserves_existing_file_and_removes_temp(tmp_path: Path) -> None:
    destination = tmp_path / "archive.zip"
    destination.write_bytes(b"original")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream([b"partial"], fail_after=True))

    with Client(check_compatibility=False, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TransportError):
            client.projects.export_archive("p", destination, overwrite=True)

    assert destination.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.part"))


def test_download_no_clobber_is_atomic_under_a_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "archive.zip"
    real_link = os.link

    def racing_link(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        Path(target).write_bytes(b"concurrent winner")
        real_link(source, target)

    monkeypatch.setattr(os, "link", racing_link)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkStream([b"downloaded data"]))

    with Client(check_compatibility=False, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FileTransferError) as caught:
            client.projects.export_archive("p", destination)

    assert isinstance(caught.value.cause, FileExistsError)
    assert destination.read_bytes() == b"concurrent winner"
    assert not list(tmp_path.glob("*.part"))


def test_upload_uses_httpx_multipart_stream(tmp_path: Path) -> None:
    source = tmp_path / "archive.zip"
    source.write_bytes(b"a" * 262_144)
    observed: dict[str, object] = {}

    class InspectingTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            observed["stream_type"] = type(request.stream).__name__
            observed["content_type"] = request.headers["content-type"]
            observed["body"] = b"".join(request.stream)
            return httpx.Response(201, json={"id": "project"})

    with Client(check_compatibility=False, transport=InspectingTransport()) as client:
        result = client.projects.import_archive(source, project_name="Imported", keep_original_dates=True)

    assert result == {"id": "project"}
    assert observed["stream_type"] == "MultipartStream"
    assert str(observed["content_type"]).startswith("multipart/form-data; boundary=")
    body = bytes(observed["body"])
    assert b'filename="archive.zip"' in body
    assert b"a" * 1024 in body
