from __future__ import annotations

import io
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from annotateit_ai.cli import API_OPERATION_COMMANDS, COMMAND_TO_OPERATION, _command_parser, run
from annotateit_ai.operations import OPERATIONS


class FakeExecutor:
    def __init__(self, responses: Mapping[str, list[Any] | Any] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def _response(self, operation_id: str) -> Any:
        if operation_id not in self.responses:
            if operation_id == "getProductInfo":
                return {"apiVersion": "1.0.0", "productVersion": "test"}
            return {"operationId": operation_id}
        value = self.responses[operation_id]
        if isinstance(value, list) and operation_id in {"listMedia", "listProjectActivity"}:
            if not value:
                raise AssertionError(f"no response left for {operation_id}")
            return value.pop(0)
        return value

    def call(
        self,
        operation_id: str,
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        self.calls.append(
            {
                "kind": "call",
                "operation_id": operation_id,
                "path_params": path_params,
                "query": query,
                "json_body": json_body,
            }
        )
        return self._response(operation_id)

    def upload(
        self,
        operation_id: str,
        file: str | Path,
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        content_type: str | None = None,
        field_name: str = "file",
    ) -> Any:
        self.calls.append(
            {
                "kind": "upload",
                "operation_id": operation_id,
                "file": str(file),
                "path_params": path_params,
                "query": query,
                "content_type": content_type,
                "field_name": field_name,
            }
        )
        return self._response(operation_id)

    def download(
        self,
        operation_id: str,
        destination: str | Path,
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> Path:
        target = Path(destination)
        if target.exists() and not overwrite:
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"archive")
        self.calls.append(
            {
                "kind": "download",
                "operation_id": operation_id,
                "destination": str(destination),
                "path_params": path_params,
                "query": query,
                "overwrite": overwrite,
            }
        )
        return target

    def close(self) -> None:
        self.closed = True


class Factory:
    def __init__(self, executor: FakeExecutor) -> None:
        self.executor = executor
        self.calls: list[tuple[str, str | None, Mapping[str, str]]] = []

    def __call__(self, url: str, token: str | None, environ: Mapping[str, str]) -> FakeExecutor:
        self.calls.append((url, token, environ))
        return self.executor


def invoke(
    argv: list[str],
    *,
    responses: Mapping[str, list[Any] | Any] | None = None,
    environ: Mapping[str, str] | None = None,
    stdin: str = "",
) -> tuple[int, str, str, FakeExecutor, Factory]:
    executor = FakeExecutor(responses)
    factory = Factory(executor)
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        argv,
        environ={"ANNOTATEIT_TOKEN": "env-token", **dict(environ or {})},
        stdin=io.StringIO(stdin),
        stdout=stdout,
        stderr=stderr,
        executor_factory=factory,
    )
    return code, stdout.getvalue(), stderr.getvalue(), executor, factory


def test_every_live_openapi_operation_has_one_unique_command() -> None:
    document = json.loads(
        (Path(__file__).parents[1] / "src/annotateit_ai/openapi/annotateit-v1.openapi.json").read_text(encoding="utf-8")
    )
    operation_ids = {
        operation["operationId"]
        for path_item in document["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert len(operation_ids) == 59
    assert set(API_OPERATION_COMMANDS) == operation_ids
    assert len(COMMAND_TO_OPERATION) == len(API_OPERATION_COMMANDS)


@pytest.mark.parametrize("command", sorted(COMMAND_TO_OPERATION))
def test_every_mapped_command_has_a_strict_parser(command: str) -> None:
    parser = _command_parser(command)
    assert parser.allow_abbrev is False
    assert parser.prog == f"annotateit {command}"


@pytest.mark.parametrize("operation_id", sorted(API_OPERATION_COMMANDS))
def test_every_live_operation_is_dispatchable(operation_id: str, tmp_path: Path) -> None:
    command = API_OPERATION_COMMANDS[operation_id]
    path_values = {
        "projectId": "p",
        "datasetId": "d",
        "mediaId": "m",
        "versionId": "v",
        "trackId": "t",
        "frameNumber": "0",
        "frame": "0",
    }
    path_names = []
    for part in OPERATIONS[operation_id].path.split("{")[1:]:
        path_names.append(part.split("}", maxsplit=1)[0])
    argv = [*command.split(), *(path_values[name] for name in path_names)]
    source = "{}"
    additions: dict[str, list[str]] = {
        "createProject": ["--name", "n", "--task-type", "Detection"],
        "importProjectArchive": ["archive.zip"],
        "updateProject": ["--name", "n"],
        "deleteProject": ["--yes"],
        "duplicateProject": ["--name", "copy"],
        "exportProjectArchive": ["--out", str(tmp_path / "project.zip")],
        "createDataset": ["--name", "n"],
        "updateDataset": ["--name", "n"],
        "deleteDataset": ["--yes"],
        "exportDataset": ["--format", "coco", "--out", str(tmp_path / "dataset.zip")],
        "importDataset": ["archive.zip"],
        "deleteVersion": ["--yes"],
        "restoreVersion": ["--yes"],
        "getVersionExportPlan": ["--format", "coco"],
        "downloadVersionArchive": [
            "--format",
            "coco",
            "--out",
            str(tmp_path / "version.zip"),
        ],
        "resetSplit": ["--yes"],
        "planSplit": ["--train", "8000", "--validation", "1000", "--test", "1000"],
        "applySplit": ["--from", "-", "--yes"],
        "assignSplitMedia": ["m", "--subset", "train"],
        "setSplitLocked": ["m", "--locked", "true"],
        "rebalanceSplit": ["--yes"],
        "uploadMedia": ["frame.jpg"],
        "downloadMedia": ["--out", str(tmp_path / "media.bin")],
        "deleteMedia": ["--yes"],
        "saveAnnotations": ["--from", "-", "--yes"],
        "saveFrameAnnotations": ["--from", "-", "--yes"],
        "createTrack": ["--from", "-"],
        "updateTrack": ["--from", "-", "--yes"],
        "deleteTrack": ["--yes"],
        "upsertTrackKeyframe": ["--from", "-"],
        "deleteTrackKeyframe": ["--yes"],
    }
    argv.extend(additions.get(operation_id, []))
    argv.extend(["--json", "--no-version-check"])
    if operation_id in {"saveAnnotations", "saveFrameAnnotations"}:
        source = "[]"
    responses: dict[str, Any] = {}
    if operation_id == "listProjects" or operation_id == "listDatasets":
        responses[operation_id] = []
    elif operation_id == "listMedia":
        responses[operation_id] = [{"media": [], "totalMatchedCount": 0, "nextSkip": None}]
    elif operation_id == "listProjectActivity":
        responses[operation_id] = [{"items": [], "nextCursor": None, "hasMore": False}]

    code, _, stderr, executor, _ = invoke(argv, responses=responses, stdin=source)
    assert code == 0, stderr
    assert operation_id in [call["operation_id"] for call in executor.calls]


def test_help_needs_neither_token_nor_client() -> None:
    executor = FakeExecutor()
    factory = Factory(executor)
    stdout = io.StringIO()
    code = run([], environ={}, stdout=stdout, stderr=io.StringIO(), executor_factory=factory)
    assert code == 0
    assert "59" not in stdout.getvalue()  # help stays user-oriented, not contract-internal
    assert "projects" in stdout.getvalue()
    assert "delete/replace/restore/apply/reset/rebalance" in stdout.getvalue()
    assert factory.calls == []


def test_command_help_is_specific_and_needs_no_token_or_client() -> None:
    executor = FakeExecutor()
    factory = Factory(executor)
    stdout = io.StringIO()
    code = run(
        ["media", "list", "--help"],
        environ={},
        stdout=stdout,
        stderr=io.StringIO(),
        executor_factory=factory,
    )
    assert code == 0
    assert "projectId" in stdout.getvalue()
    assert "--page-size" in stdout.getvalue()
    assert factory.calls == []


def test_doctor_help_is_specific_and_needs_no_token() -> None:
    stdout = io.StringIO()
    factory = Factory(FakeExecutor())
    code = run(["doctor", "--help"], environ={}, stdout=stdout, stderr=io.StringIO(), executor_factory=factory)
    assert code == 0
    assert "usage: annotateit doctor" in stdout.getvalue()
    assert factory.calls == []


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["projects", "list", "--bogus"], "unrecognized arguments"),
        (
            ["projects", "create", "--name", "n", "--na", "x", "--task-type", "Detection"],
            "unrecognized arguments",
        ),
        (["status", "--url", "8420", "--url", "8421"], "may only be passed once"),
        (["status", "--json=maybe"], "expects true or false"),
    ],
)
def test_strict_global_and_command_flags(argv: list[str], message: str) -> None:
    code, _, stderr, executor, _ = invoke(argv)
    assert code == 2
    assert message in stderr
    assert executor.calls == []


def test_flags_may_appear_anywhere_and_override_environment() -> None:
    code, stdout, _, executor, factory = invoke(
        ["--url", "9001", "projects", "list", "--token=flag-token", "--json", "--no-version-check"],
        responses={"listProjects": []},
        environ={"ANNOTATEIT_URL": "9000", "ANNOTATEIT_TOKEN": "env-token"},
    )
    assert code == 0
    assert json.loads(stdout) == []
    assert factory.calls[0][0] == "http://127.0.0.1:9001/api/v1"
    assert factory.calls[0][1] == "flag-token"
    assert [call["operation_id"] for call in executor.calls] == ["listProjects"]
    assert executor.closed


def test_old_app_without_version_warns_but_continues() -> None:
    code, stdout, stderr, executor, _ = invoke(
        ["status", "--json"],
        responses={"getProductInfo": {"productVersion": "old"}, "getStatus": {"status": "ok"}},
    )
    assert code == 0
    assert json.loads(stdout) == {"status": "ok"}
    assert "assuming compatible REST API v1" in stderr
    assert [call["operation_id"] for call in executor.calls] == ["getProductInfo", "getStatus"]


def test_incompatible_major_blocks_operation() -> None:
    code, _, stderr, executor, _ = invoke(
        ["projects", "delete", "p1", "--yes"],
        responses={"getProductInfo": {"apiVersion": "2.0.0"}},
    )
    assert code == 1
    assert "incompatible API version 2.0.0" in stderr
    assert [call["operation_id"] for call in executor.calls] == ["getProductInfo"]


def test_mismatched_api_base_path_blocks_operation() -> None:
    code, _, stderr, executor, _ = invoke(
        ["status"],
        responses={"getProductInfo": {"apiVersion": "1.0.0", "apiBasePath": "/api/v2"}},
    )
    assert code == 1
    assert "API base path" in stderr
    assert [call["operation_id"] for call in executor.calls] == ["getProductInfo"]


def test_doctor_checks_product_and_status() -> None:
    code, stdout, _, executor, _ = invoke(
        ["doctor", "--json"],
        responses={"getProductInfo": {"apiVersion": "1.0.0"}, "getStatus": {"status": "ok"}},
    )
    assert code == 0
    assert json.loads(stdout)["compatible"] is True
    assert [call["operation_id"] for call in executor.calls] == ["getProductInfo", "getStatus"]


def test_destructive_command_requires_yes_before_network() -> None:
    code, _, stderr, executor, _ = invoke(["media", "delete", "p", "d", "m"])
    assert code == 2
    assert "--yes" in stderr
    assert executor.calls == []


def test_project_create_reads_labels_json(tmp_path: Path) -> None:
    labels = tmp_path / "labels.json"
    labels.write_text('[{"id":"l1","name":"Cat"}]', encoding="utf-8")
    code, _, _, executor, _ = invoke(
        [
            "projects",
            "create",
            "--name",
            "Animals",
            "--task-type",
            "Detection",
            "--labels",
            str(labels),
            "--no-version-check",
        ]
    )
    assert code == 0
    assert executor.calls[0]["json_body"] == {
        "name": "Animals",
        "taskType": "Detection",
        "labels": [{"id": "l1", "name": "Cat"}],
    }


def test_annotation_replace_preserves_writable_keypoint_label_id() -> None:
    body = [{"id": "a", "type": "KEYPOINT", "labelId": "left-eye", "x": 1, "y": 2}]
    code, _, _, executor, _ = invoke(
        ["annotations", "replace", "p", "d", "m", "--from", "-", "--yes", "--no-version-check"],
        stdin=json.dumps(body),
    )
    assert code == 0
    assert executor.calls[0]["json_body"] == body


def test_media_auto_pagination_uses_media_not_items_and_repeated_statuses() -> None:
    code, stdout, _, executor, _ = invoke(
        [
            "media",
            "list",
            "p",
            "d",
            "--page-size",
            "2",
            "--max-items",
            "3",
            "--status",
            "annotated,to_revisit,annotated",
            "--json",
            "--no-version-check",
        ],
        responses={
            "listMedia": [
                {"media": [{"id": "1"}, {"id": "2"}], "totalMatchedCount": 5, "nextSkip": 2},
                {"media": [{"id": "3"}], "totalMatchedCount": 5, "nextSkip": 3},
            ]
        },
    )
    assert code == 0
    assert [item["id"] for item in json.loads(stdout)["media"]] == ["1", "2", "3"]
    list_calls = [call for call in executor.calls if call["operation_id"] == "listMedia"]
    assert list_calls[0]["query"] == {"limit": 2, "skip": 0, "status": ["annotated", "to_revisit"]}
    assert list_calls[1]["query"] == {"limit": 1, "skip": 2, "status": ["annotated", "to_revisit"]}


def test_activity_auto_pagination_uses_cursor_and_remaining_limit() -> None:
    code, stdout, _, executor, _ = invoke(
        ["projects", "activity", "p", "--page-size", "2", "--max-items", "3", "--json", "--no-version-check"],
        responses={
            "listProjectActivity": [
                {"items": [{"id": "1"}, {"id": "2"}], "nextCursor": "next", "hasMore": True},
                {"items": [{"id": "3"}], "nextCursor": "last", "hasMore": True},
            ]
        },
    )
    assert code == 0
    assert len(json.loads(stdout)["items"]) == 3
    calls = [call for call in executor.calls if call["operation_id"] == "listProjectActivity"]
    assert calls[0]["query"] == {"limit": 2}
    assert calls[1]["query"] == {"limit": 1, "cursor": "next"}


@pytest.mark.parametrize(
    ("argv", "responses", "message"),
    [
        (
            ["media", "list", "p", "d"],
            {"listMedia": [{"media": [], "nextSkip": 10}]},
            "empty page with a continuation",
        ),
        (
            ["projects", "activity", "p"],
            {"listProjectActivity": [{"items": [], "nextCursor": "again", "hasMore": True}]},
            "empty page with a continuation",
        ),
    ],
)
def test_pagination_rejects_empty_continuation(argv: list[str], responses: Mapping[str, Any], message: str) -> None:
    code, _, stderr, _, _ = invoke([*argv, "--no-version-check"], responses=responses)
    assert code == 1
    assert message in stderr


@pytest.mark.parametrize("command", [["media", "list", "p", "d"], ["projects", "activity", "p"]])
def test_page_size_over_200_is_rejected_without_network(command: list[str]) -> None:
    code, _, stderr, executor, _ = invoke([*command, "--page-size", "201"])
    assert code == 2
    assert "between 1 and 200" in stderr
    assert executor.calls == []


def test_split_plan_write_is_no_clobber_then_force(tmp_path: Path) -> None:
    destination = tmp_path / "plan.json"
    args = [
        "split",
        "plan",
        "p",
        "d",
        "--train",
        "8000",
        "--validation",
        "1000",
        "--test",
        "1000",
        "--out",
        str(destination),
        "--no-version-check",
    ]
    response = {"plan": {"fingerprint": "x"}}
    code, _, _, executor, _ = invoke(args, responses={"planSplit": response})
    assert code == 0
    assert json.loads(destination.read_text(encoding="utf-8")) == response
    assert executor.calls[0]["json_body"]["ratios"]["trainBps"] == 8000

    code, _, stderr, _, _ = invoke(args, responses={"planSplit": response})
    assert code == 1
    assert "--force" in stderr
    code, _, _, _, _ = invoke([*args, "--force"], responses={"planSplit": response})
    assert code == 0


def test_split_apply_accepts_wrapped_plan(tmp_path: Path) -> None:
    source = tmp_path / "plan.json"
    source.write_text('{"plan":{"assignments":[]},"preview":true}', encoding="utf-8")
    code, _, _, executor, _ = invoke(["split", "apply", "p", "d", "--from", str(source), "--yes", "--no-version-check"])
    assert code == 0
    assert executor.calls[0]["json_body"] == {"plan": {"assignments": []}}


def test_downloads_pass_force_path_and_required_version_format(tmp_path: Path) -> None:
    destination = tmp_path / "version.zip"
    code, stdout, _, executor, _ = invoke(
        [
            "versions",
            "archive",
            "p",
            "d",
            "v",
            "--format",
            "coco",
            "--accept-exclusions",
            "--out",
            str(destination),
            "--force",
            "--json",
            "--no-version-check",
        ]
    )
    assert code == 0
    assert json.loads(stdout)["bytes"] == len(b"archive")
    assert executor.calls[0] == {
        "kind": "download",
        "operation_id": "downloadVersionArchive",
        "destination": str(destination),
        "path_params": {"projectId": "p", "datasetId": "d", "versionId": "v"},
        "query": {"format": "coco", "acceptExclusions": True},
        "overwrite": True,
    }


def test_openapi_output_requires_force_to_replace(tmp_path: Path) -> None:
    destination = tmp_path / "openapi.json"
    destination.write_text("old", encoding="utf-8")
    code, _, stderr, _, _ = invoke(
        ["openapi", "show", "--out", str(destination)], responses={"getOpenApiDocument": {"openapi": "3.1.0"}}
    )
    assert code == 1
    assert "--force" in stderr
    assert destination.read_text(encoding="utf-8") == "old"
    code, _, _, _, _ = invoke(
        ["openapi", "show", "--out", str(destination), "--force"],
        responses={"getOpenApiDocument": {"openapi": "3.1.0"}},
    )
    assert code == 0
    assert json.loads(destination.read_text(encoding="utf-8")) == {"openapi": "3.1.0"}


def test_export_validates_dependent_flags_before_download(tmp_path: Path) -> None:
    code, _, stderr, executor, _ = invoke(
        [
            "export",
            "p",
            "d",
            "--format",
            "mots",
            "--accept-unassigned",
            "--out",
            str(tmp_path / "x.zip"),
            "--no-version-check",
        ]
    )
    assert code == 2
    assert "requires --split" in stderr
    assert executor.calls == []


def test_project_dataset_and_media_upload_commands() -> None:
    cases = [
        (["projects", "import", "project.zip"], "importProjectArchive", None),
        (["import", "p", "d", "dataset.zip"], "importDataset", {"projectId": "p", "datasetId": "d"}),
        (["media", "upload", "p", "d", "a.jpg", "b.jpg"], "uploadMedia", {"projectId": "p", "datasetId": "d"}),
    ]
    for arguments, operation_id, path_params in cases:
        code, _, _, executor, _ = invoke([*arguments, "--json", "--no-version-check"])
        assert code == 0
        upload_calls = [call for call in executor.calls if call["kind"] == "upload"]
        assert upload_calls
        assert all(call["operation_id"] == operation_id and call["path_params"] == path_params for call in upload_calls)
