from __future__ import annotations

import json
from importlib.resources import files
from inspect import Parameter, signature
from pathlib import Path
from typing import Any, cast

from annotateit_ai import OPERATIONS, Client


def _openapi_operations() -> dict[str, tuple[str, str, tuple[int, ...], bool, bool]]:
    resource = files("annotateit_ai").joinpath("openapi/annotateit-v1.openapi.json")
    document = cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))
    found: dict[str, tuple[str, str, tuple[int, ...], bool, bool]] = {}
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            operation_id = operation["operationId"]
            success = tuple(
                sorted(int(code) for code in operation["responses"] if code.isdigit() and code.startswith("2"))
            )
            request_content = operation.get("requestBody", {}).get("content", {})
            upload = "multipart/form-data" in request_content
            success_content = {
                media_type
                for code, response in operation["responses"].items()
                if code.isdigit() and code.startswith("2")
                for media_type in response.get("content", {})
            }
            download = any(
                media_type in {"application/zip", "application/octet-stream"}
                or media_type.startswith(("image/", "video/"))
                for media_type in success_content
            )
            found[operation_id] = (method.upper(), path, success, download, upload)
    return found


def test_registry_has_exact_openapi_operation_parity() -> None:
    expected = _openapi_operations()
    actual = {
        operation_id: (
            operation.method,
            operation.path,
            operation.success_statuses,
            operation.download,
            operation.upload,
        )
        for operation_id, operation in OPERATIONS.items()
    }
    assert len(expected) == 59
    assert actual == expected


def test_every_operation_has_an_explicit_resource_method() -> None:
    with Client(check_compatibility=False) as client:
        for operation in OPERATIONS.values():
            resource = getattr(client, operation.resource)
            wrapper = getattr(resource, operation.python_name)
            assert callable(wrapper), operation.operation_id


def test_every_resource_wrapper_dispatches_its_registered_operation_id() -> None:
    class SpyClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def call(self, operation_id: str, *args: object, **kwargs: object) -> dict[str, object]:
            self.calls.append((operation_id, "call"))
            return {}

        def upload(self, operation_id: str, *args: object, **kwargs: object) -> dict[str, object]:
            self.calls.append((operation_id, "upload"))
            return {}

        def download(self, operation_id: str, *args: object, **kwargs: object) -> Path:
            self.calls.append((operation_id, "download"))
            return Path("download.bin")

    required_values: dict[str, object] = {
        "project_id": "project",
        "dataset_id": "dataset",
        "media_id": "media",
        "version_id": "version",
        "track_id": "track",
        "name": "name",
        "task_type": "Detection",
        "file": "upload.bin",
        "destination": "download.bin",
        "format": "coco",
        "train_bps": 8000,
        "validation_bps": 1000,
        "test_bps": 1000,
        "plan": {},
        "media_ids": ["media"],
        "subset": "train",
        "locked": True,
        "annotations": [],
        "frame_number": 0,
        "track": {},
        "frame": 0,
        "keyframe": {"shape": {}},
    }

    spy = SpyClient()
    with Client(check_compatibility=False) as client:
        for operation in OPERATIONS.values():
            resource = getattr(client, operation.resource)
            resource._client = spy
            wrapper = getattr(resource, operation.python_name)
            arguments = {
                parameter.name: required_values[parameter.name]
                for parameter in signature(wrapper).parameters.values()
                if parameter.default is Parameter.empty
            }
            wrapper(**arguments)

    assert spy.calls == [
        (
            operation.operation_id,
            "download" if operation.download else "upload" if operation.upload else "call",
        )
        for operation in OPERATIONS.values()
    ]
