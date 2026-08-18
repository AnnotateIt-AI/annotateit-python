from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, Protocol, TextIO, cast
from urllib.parse import urlsplit

from .client import Client
from .config import DEFAULT_BASE_URL, normalize_base_url
from .errors import AnnotateItError, CompatibilityError, FileTransferError
from .operations import OPERATIONS

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
SUPPORTED_API_MAJOR = 1

FORMATS = ("coco", "yolo", "voc", "datumaro", "supervisely-video", "mot", "kitti", "mots", "zip")
TASK_TYPES = ("Detection", "Instance segmentation", "Keypoint detection", "Classification")
MEDIA_SCOPES = ("all", "annotated", "unannotated")
MEDIA_TYPES = ("all", "images", "videos")
SPLIT_SUBSETS = ("train", "validation", "test", "unassigned")
ANNOTATION_STATUSES = ("none", "annotated", "partially_annotated", "to_revisit")
QUALITY_MODES = ("quick", "deep")
MOTS_CLASSES = ("car", "pedestrian", "ignore", "exclude")

# This is intentionally explicit: tests compare it to the bundled OpenAPI document so a
# newly-live endpoint cannot silently ship without a discoverable CLI command.
API_OPERATION_COMMANDS: dict[str, str] = {
    "listProjects": "projects list",
    "createProject": "projects create",
    "importProjectArchive": "projects import",
    "getProject": "projects show",
    "updateProject": "projects update",
    "deleteProject": "projects delete",
    "getProjectStatus": "projects status",
    "duplicateProject": "projects duplicate",
    "exportProjectArchive": "projects export",
    "listProjectActivity": "projects activity",
    "listDatasets": "datasets list",
    "createDataset": "datasets create",
    "updateDataset": "datasets update",
    "deleteDataset": "datasets delete",
    "copyDataset": "datasets copy",
    "getDatasetStatistics": "datasets statistics",
    "exportDataset": "export",
    "importDataset": "import",
    "listVersions": "versions list",
    "createVersion": "versions create",
    "getVersion": "versions show",
    "deleteVersion": "versions delete",
    "getVersionDiff": "versions diff",
    "getRestorePreflight": "versions preflight",
    "restoreVersion": "versions restore",
    "getVersionExportPlan": "versions export-plan",
    "downloadVersionArchive": "versions archive",
    "getSplitState": "split show",
    "resetSplit": "split reset",
    "validateSplit": "split validate",
    "getSplitManifest": "split manifest",
    "planSplit": "split plan",
    "applySplit": "split apply",
    "assignSplitMedia": "split assign",
    "setSplitLocked": "split lock",
    "rebalanceSplit": "split rebalance",
    "getDatasetQualityReport": "quality show",
    "scanDatasetQuality": "quality scan",
    "cancelDatasetQualityScan": "quality cancel",
    "getDatasetQualityFingerprint": "quality fingerprint",
    "listMedia": "media list",
    "uploadMedia": "media upload",
    "getMedia": "media show",
    "downloadMedia": "media download",
    "deleteMedia": "media delete",
    "getAnnotations": "annotations get",
    "saveAnnotations": "annotations replace",
    "getFrameAnnotations": "frames annotations get",
    "saveFrameAnnotations": "frames annotations replace",
    "listTracks": "tracks list",
    "createTrack": "tracks create",
    "getTrack": "tracks show",
    "updateTrack": "tracks replace",
    "deleteTrack": "tracks delete",
    "upsertTrackKeyframe": "tracks keyframes put",
    "deleteTrackKeyframe": "tracks keyframes delete",
    "getStatus": "status",
    "getProductInfo": "product info",
    "getOpenApiDocument": "openapi show",
}

COMMAND_TO_OPERATION = {command: operation_id for operation_id, command in API_OPERATION_COMMANDS.items()}
if len(COMMAND_TO_OPERATION) != len(API_OPERATION_COMMANDS):  # pragma: no cover - import invariant
    raise RuntimeError("two API operations have the same CLI command")

HELP = f"""annotateit - CLI for the local AnnotateIt REST API v1

Usage
  annotateit <group> <command> [arguments] [--flags]

Connection
  --url <port|host|url>   Default: {DEFAULT_BASE_URL}
  --token <token>         Prefer ANNOTATEIT_TOKEN to avoid shell history
  --no-version-check      Skip the /product-info compatibility preflight
  annotateit doctor       Verify authentication and API compatibility
  annotateit openapi show [--out openapi.json]

Core resources
  projects  list | create | show | update | delete | duplicate | export | import | status | activity
  datasets  list | create | update | delete | copy | statistics
  media     list | show | download | upload | delete
  annotations get | replace
  frames annotations get | replace
  tracks    list | create | show | replace | delete
  tracks keyframes put | delete

Dataset workflows
  versions  list | create | show | delete | diff | preflight | restore | export-plan | archive
  split     show | validate | manifest | plan | apply | assign | lock | rebalance | reset
  quality   scan | show | fingerprint | cancel
  import <projectId> <datasetId> <archive.zip>
  export <projectId> <datasetId> --format {"|".join(FORMATS)}

Data input and safety
  --from <file|->        Read a JSON request body from a UTF-8 file or stdin
  --yes                  Required for destructive delete/replace/restore/apply/reset/rebalance operations
  --force                Explicitly replace an existing output file
  --json                 Stable JSON output; diagnostics remain on stderr

Global flags may appear before or after the command. Abbreviated and unknown flags are rejected.
See the package README for setup, safety, and usage examples.
"""


class UsageError(ValueError):
    """Invalid command syntax or local JSON input."""


class OperationExecutor(Protocol):
    def call(
        self,
        operation_id: str,
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Any = ...,
    ) -> Any: ...

    def upload(
        self,
        operation_id: str,
        file: str | os.PathLike[str],
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        content_type: str | None = None,
        field_name: str = "file",
    ) -> Any: ...

    def download(
        self,
        operation_id: str,
        destination: str | os.PathLike[str],
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> Path: ...

    def close(self) -> None: ...


ExecutorFactory = Callable[[str, str | None, Mapping[str, str]], OperationExecutor]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


class _Missing:
    pass


MISSING = _Missing()
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")
_PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _non_negative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return number


def _positive(value: str) -> int:
    number = _non_negative(value)
    if number == 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _page_size(value: str) -> int:
    number = _positive(value)
    if number > 200:
        raise argparse.ArgumentTypeError("must be between 1 and 200")
    return number


def _basis_points(value: str) -> int:
    number = _non_negative(value)
    if number > 10_000:
        raise argparse.ArgumentTypeError("must be between 0 and 10000")
    return number


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _optional_bool(parser: argparse.ArgumentParser, name: str, *, dest: str | None = None) -> None:
    parser.add_argument(name, dest=dest, nargs="?", const=True, type=_parse_bool, default=None)


def _path_names(operation_id: str) -> list[str]:
    return _PATH_PARAMETER.findall(OPERATIONS[operation_id].path)


def _command_parser(command: str) -> _Parser:
    if command == "doctor":
        return _Parser(prog="annotateit doctor", allow_abbrev=False)
    operation_id = COMMAND_TO_OPERATION[command]
    parser = _Parser(prog=f"annotateit {command}", allow_abbrev=False)
    for name in _path_names(operation_id):
        if name in {"frame", "frameNumber"}:
            parser.add_argument(name, type=_non_negative)
        else:
            parser.add_argument(name)

    if command == "projects create":
        parser.add_argument("--name", required=True)
        parser.add_argument("--task-type", choices=TASK_TYPES, required=True)
        parser.add_argument("--labels")
    elif command == "projects update":
        parser.add_argument("--name")
        parser.add_argument("--labels")
        parser.add_argument("--yes", action="store_true")
    elif command == "projects duplicate":
        parser.add_argument("--name", required=True)
    elif command == "projects export":
        parser.add_argument("--out", required=True)
        parser.add_argument("--force", action="store_true")
    elif command == "projects import":
        parser.add_argument("archive")
        parser.add_argument("--name")
        _optional_bool(parser, "--keep-original-dates", dest="keep_original_dates")
    elif command == "projects activity":
        parser.add_argument("--dataset")
        parser.add_argument("--event-type")
        parser.add_argument("--actor")
        parser.add_argument("--from", dest="from_time")
        parser.add_argument("--to", dest="to_time")
        parser.add_argument("--page-size", type=_page_size, default=200)
        parser.add_argument("--max-items", type=_positive)
    elif command in {"projects delete", "datasets delete", "media delete", "versions delete", "tracks delete"}:
        parser.add_argument("--yes", action="store_true")
    elif command in {"datasets create", "datasets update"}:
        parser.add_argument("--name", required=True)
    elif command == "datasets copy":
        parser.add_argument("--name")
        parser.add_argument("--media-scope", choices=MEDIA_SCOPES, default="all")
        parser.add_argument("--media-types", choices=MEDIA_TYPES, default="all")
        _optional_bool(parser, "--annotations")
    elif command == "media list":
        parser.add_argument("--page-size", type=_page_size, default=200)
        parser.add_argument("--max-items", type=_positive)
        parser.add_argument("--skip", type=_non_negative, default=0)
        parser.add_argument("--status")
    elif command == "media upload":
        parser.add_argument("files", nargs="+")
    elif command == "media download":
        parser.add_argument("--out", required=True)
        parser.add_argument("--force", action="store_true")
    elif command in {"annotations replace", "frames annotations replace", "tracks replace"}:
        parser.add_argument("--from", dest="source", required=True)
        parser.add_argument("--yes", action="store_true")
    elif command in {"tracks create", "tracks keyframes put"}:
        parser.add_argument("--from", dest="source", required=True)
    elif command == "tracks keyframes delete":
        parser.add_argument("--yes", action="store_true")
    elif command == "versions create":
        parser.add_argument("--name")
        parser.add_argument("--note")
    elif command == "versions diff":
        parser.add_argument("--target", default="current")
    elif command == "versions restore":
        parser.add_argument("--yes", action="store_true")
    elif command == "versions export-plan":
        parser.add_argument("--format", choices=FORMATS, required=True)
    elif command == "versions archive":
        parser.add_argument("--format", choices=FORMATS, required=True)
        _optional_bool(parser, "--accept-exclusions", dest="accept_exclusions")
        parser.add_argument("--out", required=True)
        parser.add_argument("--force", action="store_true")
    elif command == "split plan":
        parser.add_argument("--train", type=_basis_points)
        parser.add_argument("--validation", type=_basis_points)
        parser.add_argument("--test", type=_basis_points)
        parser.add_argument("--seed", type=_non_negative)
        _optional_bool(parser, "--stratify")
        parser.add_argument("--from", dest="source")
        parser.add_argument("--out")
        parser.add_argument("--force", action="store_true")
    elif command == "split apply":
        parser.add_argument("--from", dest="source", required=True)
        parser.add_argument("--yes", action="store_true")
    elif command == "split assign":
        parser.add_argument("mediaIds", nargs="+")
        parser.add_argument("--subset", choices=SPLIT_SUBSETS, required=True)
        _optional_bool(parser, "--locked")
        _optional_bool(parser, "--dry-run", dest="dry_run")
    elif command == "split lock":
        parser.add_argument("mediaIds", nargs="+")
        parser.add_argument("--locked", required=True, type=_parse_bool)
    elif command in {"split rebalance", "split reset"}:
        parser.add_argument("--yes", action="store_true")
    elif command == "quality scan":
        parser.add_argument("--mode", choices=QUALITY_MODES, default="quick")
    elif command == "import":
        parser.add_argument("archive")
    elif command == "export":
        parser.add_argument("--format", choices=FORMATS, required=True)
        parser.add_argument("--out")
        parser.add_argument("--force", action="store_true")
        _optional_bool(parser, "--split")
        _optional_bool(parser, "--accept-unassigned", dest="accept_unassigned")
        parser.add_argument("--polyline-width", type=_positive_float)
        parser.add_argument("--mots-classes")
    elif command == "openapi show":
        parser.add_argument("--out")
        parser.add_argument("--force", action="store_true")

    return parser


def _extract_globals(argv: Sequence[str]) -> tuple[list[str], dict[str, object]]:
    remaining: list[str] = []
    values: dict[str, object] = {"json": False, "no_version_check": False}
    seen: set[str] = set()
    index = 0
    while index < len(argv):
        token = argv[index]
        matched = False
        for option, destination in (("--url", "url"), ("--token", "token")):
            if token == option or token.startswith(f"{option}="):
                if option in seen:
                    raise UsageError(f"{option} may only be passed once")
                seen.add(option)
                if token == option:
                    index += 1
                    if index >= len(argv) or argv[index].startswith("--"):
                        raise UsageError(f"{option} needs a value")
                    value = argv[index]
                else:
                    value = token[len(option) + 1 :]
                if value == "":
                    raise UsageError(f"{option} cannot be empty")
                values[destination] = value
                matched = True
                break
        if not matched:
            for option, destination in (("--json", "json"), ("--no-version-check", "no_version_check")):
                if token == option or token.startswith(f"{option}="):
                    if option in seen:
                        raise UsageError(f"{option} may only be passed once")
                    seen.add(option)
                    raw: str | bool = True if token == option else token[len(option) + 1 :]
                    try:
                        values[destination] = _parse_bool(raw)
                    except argparse.ArgumentTypeError as error:
                        raise UsageError(f"{option} expects true or false") from error
                    matched = True
                    break
        if not matched:
            remaining.append(token)
        index += 1
    return remaining, values


def _route(argv: Sequence[str]) -> tuple[str, list[str]]:
    if not argv:
        return "help", []
    if argv[0] in {"help", "--help", "-h"}:
        if len(argv) != 1:
            raise UsageError("help takes no arguments")
        return "help", []
    if argv[0] == "doctor":
        return "doctor", list(argv[1:])
    for command in sorted(COMMAND_TO_OPERATION, key=lambda value: len(value.split()), reverse=True):
        words = command.split()
        if list(argv[: len(words)]) == words:
            return command, list(argv[len(words) :])
    raise UsageError(f"unknown command {' '.join(argv)!r}")


def _read_json(source: str, stdin: TextIO, expected: str = "value") -> Any:
    try:
        text = stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot read JSON from {source!r}: {error}") from error
    try:
        value: Any = json.loads(text)
    except json.JSONDecodeError as error:
        raise UsageError(
            f"invalid JSON in {source!r}: {error.msg} at line {error.lineno}, column {error.colno}"
        ) from error
    if expected == "object" and (not isinstance(value, dict)):
        raise UsageError(f"{source!r} must contain a JSON object")
    if expected == "array" and not isinstance(value, list):
        raise UsageError(f"{source!r} must contain a JSON array")
    return value


def _write_json_atomic(destination: str, value: Any, force: bool) -> Path:
    target = Path(destination)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as sink:
                json.dump(value, sink, ensure_ascii=False, indent=2)
                sink.write("\n")
                sink.flush()
                os.fsync(sink.fileno())
            if force:
                os.replace(temporary, target)
            else:
                os.link(temporary, target)
                temporary.unlink()
        finally:
            temporary.unlink(missing_ok=True)
    except FileExistsError as error:
        raise FileTransferError(str(target), "replace existing output; pass --force to overwrite", error) from error
    except OSError as error:
        raise FileTransferError(str(target), "write output", error) from error
    return target


def _json_line(stream: TextIO, value: Any) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    stream.write("\n")


def _table(stream: TextIO, items: list[dict[str, Any]], extra: Sequence[str] = ()) -> None:
    if not items:
        return
    columns = ("id", "name", *extra)
    rows = [[str(item.get(column, "")) for column in columns] for item in items]
    widths = [max(len(row[index]) for row in rows) for index in range(len(columns))]
    for row in rows:
        stream.write("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip() + "\n")


def _require_yes(namespace: argparse.Namespace, message: str) -> None:
    if not bool(getattr(namespace, "yes", False)):
        raise UsageError(f"{message}; pass --yes to confirm")


def _path_params(operation_id: str, namespace: argparse.Namespace) -> dict[str, object] | None:
    result = {name: cast(object, getattr(namespace, name)) for name in _path_names(operation_id)}
    return result or None


def _call(
    executor: OperationExecutor,
    operation_id: str,
    namespace: argparse.Namespace,
    *,
    query: Mapping[str, Any] | None = None,
    body: Any = MISSING,
) -> Any:
    kwargs: dict[str, Any] = {"path_params": _path_params(operation_id, namespace), "query": query}
    if isinstance(body, _Missing):
        return executor.call(operation_id, **kwargs)
    return executor.call(operation_id, json_body=body, **kwargs)


def _statuses(raw: str | None) -> list[str]:
    if raw is None:
        return []
    values = list(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    invalid = sorted(set(values).difference(ANNOTATION_STATUSES))
    if not values or invalid:
        raise UsageError(f"--status must contain one or more of: {', '.join(ANNOTATION_STATUSES)}")
    return values


def _mots_mapping(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in raw.split(","):
        label_id, separator, class_name = entry.strip().partition("=")
        if not separator or not label_id or class_name not in MOTS_CLASSES:
            raise UsageError("--mots-classes must be labelId=car|pedestrian|ignore|exclude entries")
        if label_id in result:
            raise UsageError(f"--mots-classes contains duplicate label id {label_id!r}")
        result[label_id] = class_name
    if not result:
        raise UsageError("--mots-classes cannot be empty")
    return result


def _default_factory(base_url: str, token: str | None, environ: Mapping[str, str]) -> OperationExecutor:
    return Client(base_url, token, check_compatibility=False, env=environ)


def _check_compatibility(executor: OperationExecutor, stderr: TextIO, base_url: str) -> dict[str, Any]:
    raw = executor.call("getProductInfo")
    if not isinstance(raw, dict):
        raise CompatibilityError("AnnotateIt product-info response is not a JSON object")
    result = cast(dict[str, Any], raw)
    version = result.get("apiVersion")
    if version is None:
        stderr.write("warning: app does not advertise apiVersion; assuming compatible REST API v1\n")
        return result
    if not isinstance(version, str) or (match := _SEMVER.fullmatch(version)) is None:
        raise CompatibilityError(f"AnnotateIt reported an invalid apiVersion: {version!r}")
    if int(match.group(1)) != SUPPORTED_API_MAJOR:
        raise CompatibilityError(
            f"incompatible API version {version}: this CLI supports major version {SUPPORTED_API_MAJOR}.x",
            api_version=version,
        )
    reported_path = result.get("apiBasePath")
    configured_path = urlsplit(base_url).path.rstrip("/")
    if reported_path is not None and (
        not isinstance(reported_path, str) or reported_path.rstrip("/") != configured_path
    ):
        raise CompatibilityError(
            f"AnnotateIt reports API base path {reported_path!r}, but the CLI uses {configured_path!r}",
            api_version=version,
        )
    return result


class _CompatibilityExecutor:
    """Delay compatibility I/O until local validation has succeeded."""

    def __init__(self, executor: OperationExecutor, stderr: TextIO, base_url: str) -> None:
        self._executor = executor
        self._stderr = stderr
        self._base_url = base_url
        self._checked = False

    def _ensure(self) -> None:
        if not self._checked:
            _check_compatibility(self._executor, self._stderr, self._base_url)
            self._checked = True

    def call(
        self,
        operation_id: str,
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        json_body: Any = MISSING,
    ) -> Any:
        if operation_id not in {"getProductInfo", "getOpenApiDocument"}:
            self._ensure()
        if isinstance(json_body, _Missing):
            return self._executor.call(operation_id, path_params=path_params, query=query)
        return self._executor.call(operation_id, path_params=path_params, query=query, json_body=json_body)

    def upload(
        self,
        operation_id: str,
        file: str | os.PathLike[str],
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        content_type: str | None = None,
        field_name: str = "file",
    ) -> Any:
        self._ensure()
        return self._executor.upload(
            operation_id,
            file,
            path_params=path_params,
            query=query,
            content_type=content_type,
            field_name=field_name,
        )

    def download(
        self,
        operation_id: str,
        destination: str | os.PathLike[str],
        *,
        path_params: dict[str, object] | None = None,
        query: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> Path:
        self._ensure()
        return self._executor.download(
            operation_id,
            destination,
            path_params=path_params,
            query=query,
            overwrite=overwrite,
        )

    def close(self) -> None:
        self._executor.close()


def _list_output(
    stdout: TextIO, value: Any, json_mode: bool, *, key: str | None = None, extra: Sequence[str] = ()
) -> None:
    if json_mode:
        _json_line(stdout, value)
        return
    candidate = value.get(key, []) if key is not None and isinstance(value, dict) else value
    if not isinstance(candidate, list):
        raise RuntimeError("list response is not a JSON array")
    items = [cast(dict[str, Any], item) for item in candidate if isinstance(item, dict)]
    if len(items) != len(candidate):
        raise RuntimeError("list response contains a non-object item")
    _table(stdout, items, extra)


def _download_output(
    executor: OperationExecutor,
    operation_id: str,
    namespace: argparse.Namespace,
    stdout: TextIO,
    json_mode: bool,
    *,
    query: Mapping[str, Any] | None = None,
    format_name: str | None = None,
) -> None:
    destination = str(namespace.out)
    result = executor.download(
        operation_id,
        destination,
        path_params=_path_params(operation_id, namespace),
        query=query,
        overwrite=bool(namespace.force),
    )
    try:
        byte_count = result.stat().st_size
    except OSError as error:
        raise FileTransferError(str(result), "inspect completed download", error) from error
    payload: dict[str, Any] = {"path": str(result), "bytes": byte_count}
    if format_name is not None:
        payload["format"] = format_name
    if json_mode:
        _json_line(stdout, payload)
    else:
        stdout.write(f"{result} ({byte_count / 1024 / 1024:.1f} MB)\n")


def _paginate_media(executor: OperationExecutor, namespace: argparse.Namespace) -> dict[str, Any]:
    statuses = _statuses(cast(str | None, namespace.status))
    page_size = int(namespace.page_size)
    max_items = cast(int | None, namespace.max_items)
    skip = int(namespace.skip)
    media: list[dict[str, Any]] = []
    total_matched_count = 0
    next_skip: int | None = skip

    while next_skip is not None:
        remaining = page_size if max_items is None else min(page_size, max_items - len(media))
        if remaining <= 0:
            break
        query: dict[str, Any] = {"limit": remaining, "skip": skip}
        if statuses:
            query["status"] = statuses
        raw = _call(executor, "listMedia", namespace, query=query)
        if isinstance(raw, list):
            page: dict[str, Any] = {"media": raw, "totalMatchedCount": len(raw), "nextSkip": None}
        elif isinstance(raw, dict):
            page = cast(dict[str, Any], raw)
        else:
            raise RuntimeError("media response is not a JSON object")
        page_items = page.get("media")
        if not isinstance(page_items, list):
            raise RuntimeError("media response has no media array")
        if len(page_items) > remaining:
            raise RuntimeError("media response exceeded the requested page size")
        if not all(isinstance(item, dict) for item in page_items):
            raise RuntimeError("media response contains a non-object item")
        media.extend(cast(list[dict[str, Any]], page_items))
        raw_total = page.get("totalMatchedCount")
        total_matched_count = int(raw_total) if isinstance(raw_total, int) else total_matched_count + len(page_items)
        raw_next = page.get("nextSkip")
        if raw_next is None:
            next_skip = None
        elif isinstance(raw_next, int):
            next_skip = raw_next
        else:
            raise RuntimeError("media response nextSkip is not an integer or null")
        if not page_items and next_skip is not None:
            raise RuntimeError("media pagination returned an empty page with a continuation")
        if max_items is not None and len(media) >= max_items:
            break
        if next_skip is not None and next_skip <= skip:
            raise RuntimeError("media pagination did not advance nextSkip")
        if next_skip is not None:
            skip = next_skip
    return {"media": media, "totalMatchedCount": total_matched_count, "nextSkip": next_skip}


def _paginate_activity(executor: OperationExecutor, namespace: argparse.Namespace) -> dict[str, Any]:
    base: dict[str, Any] = {}
    for attribute, query_name in (
        ("dataset", "datasetId"),
        ("event_type", "eventType"),
        ("actor", "actorId"),
        ("from_time", "from"),
        ("to_time", "to"),
    ):
        value = getattr(namespace, attribute)
        if value is not None:
            base[query_name] = value
    page_size = int(namespace.page_size)
    max_items = cast(int | None, namespace.max_items)
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    has_more = False
    seen: set[str] = set()
    while True:
        remaining = page_size if max_items is None else min(page_size, max_items - len(items))
        if remaining <= 0:
            break
        query = {**base, "limit": remaining}
        if cursor is not None:
            query["cursor"] = cursor
        raw = _call(executor, "listProjectActivity", namespace, query=query)
        if not isinstance(raw, dict):
            raise RuntimeError("activity response is not a JSON object")
        page_items = raw.get("items")
        if not isinstance(page_items, list):
            raise RuntimeError("activity response has no items array")
        if len(page_items) > remaining:
            raise RuntimeError("activity response exceeded the requested page size")
        if not all(isinstance(item, dict) for item in page_items):
            raise RuntimeError("activity response contains a non-object item")
        items.extend(cast(list[dict[str, Any]], page_items))
        has_more = raw.get("hasMore") is True
        raw_cursor = raw.get("nextCursor")
        if raw_cursor is not None and not isinstance(raw_cursor, str):
            raise RuntimeError("activity nextCursor is not a string or null")
        cursor = raw_cursor
        if max_items is not None and len(items) >= max_items:
            break
        if has_more and cursor is None:
            raise RuntimeError("activity response says hasMore without nextCursor")
        if has_more and not page_items:
            raise RuntimeError("activity pagination returned an empty page with a continuation")
        if not has_more:
            break
        assert cursor is not None
        if cursor in seen:
            raise RuntimeError("activity pagination returned the same cursor twice")
        seen.add(cursor)
    return {"items": items, "nextCursor": cursor, "hasMore": has_more}


def _dispatch(
    command: str,
    namespace: argparse.Namespace,
    executor: OperationExecutor,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    json_mode: bool,
) -> None:
    operation_id = COMMAND_TO_OPERATION[command]
    result: Any

    if command == "projects activity":
        result = _paginate_activity(executor, namespace)
        _list_output(stdout, result, json_mode, key="items", extra=("eventType", "occurredAt"))
        return
    if command == "media list":
        result = _paginate_media(executor, namespace)
        _list_output(stdout, result, json_mode, key="media", extra=("type",))
        return

    if command == "projects create":
        labels = [] if namespace.labels is None else _read_json(namespace.labels, stdin, "array")
        result = _call(
            executor,
            operation_id,
            namespace,
            body={"name": namespace.name, "taskType": namespace.task_type, "labels": labels},
        )
    elif command == "projects update":
        if namespace.name is None and namespace.labels is None:
            raise UsageError("projects update needs --name or --labels")
        body: dict[str, Any] = {}
        if namespace.name is not None:
            body["name"] = namespace.name
        if namespace.labels is not None:
            _require_yes(namespace, "replacing the project label schema can invalidate annotations")
            body["labels"] = _read_json(namespace.labels, stdin, "array")
        result = _call(executor, operation_id, namespace, body=body)
    elif command == "projects duplicate":
        result = _call(executor, operation_id, namespace, body={"name": namespace.name})
    elif command == "projects import":
        query: dict[str, Any] = {}
        if namespace.name is not None:
            query["projectName"] = namespace.name
        if namespace.keep_original_dates is not None:
            query["keepOriginalDates"] = namespace.keep_original_dates
        stderr.write(f"importing project {namespace.archive}...\n")
        result = executor.upload(operation_id, namespace.archive, query=query or None, content_type="application/zip")
    elif command == "projects export":
        stderr.write(f"exporting project {namespace.projectId}...\n")
        _download_output(executor, operation_id, namespace, stdout, json_mode)
        return
    elif command == "datasets create":
        result = _call(executor, operation_id, namespace, body={"name": namespace.name})
    elif command == "datasets update":
        result = _call(executor, operation_id, namespace, body={"name": namespace.name})
    elif command == "datasets copy":
        result = _call(
            executor,
            operation_id,
            namespace,
            body={
                **({} if namespace.name is None else {"name": namespace.name}),
                "mediaScope": namespace.media_scope,
                "mediaTypes": namespace.media_types,
                "includeAnnotations": True if namespace.annotations is None else namespace.annotations,
            },
        )
    elif command == "media upload":
        uploaded: list[Any] = []
        for source in namespace.files:
            stderr.write(f"uploading {source}...\n")
            uploaded.append(executor.upload(operation_id, source, path_params=_path_params(operation_id, namespace)))
        result = uploaded[0] if len(uploaded) == 1 else uploaded
        if json_mode:
            _json_line(stdout, result)
        elif isinstance(result, list):
            _list_output(stdout, result, False, extra=("type",))
        elif isinstance(result, dict):
            _list_output(stdout, [result], False, extra=("type",))
        else:
            _json_line(stdout, result)
        return
    elif command == "media download":
        _download_output(executor, operation_id, namespace, stdout, json_mode)
        return
    elif command in {"annotations replace", "frames annotations replace"}:
        _require_yes(namespace, "PUT replaces every loose annotation in this scope")
        result = _call(executor, operation_id, namespace, body=_read_json(namespace.source, stdin, "array"))
    elif command == "tracks create":
        result = _call(executor, operation_id, namespace, body=_read_json(namespace.source, stdin, "object"))
    elif command == "tracks replace":
        _require_yes(namespace, "PUT replaces the complete track and all keyframes")
        result = _call(executor, operation_id, namespace, body=_read_json(namespace.source, stdin, "object"))
    elif command == "tracks keyframes put":
        result = _call(executor, operation_id, namespace, body=_read_json(namespace.source, stdin, "object"))
    elif command == "versions create":
        body = {
            **({} if namespace.name is None else {"name": namespace.name}),
            **({} if namespace.note is None else {"note": namespace.note}),
        }
        result = _call(executor, operation_id, namespace, body=body)
    elif command == "versions diff":
        result = _call(executor, operation_id, namespace, query={"target": namespace.target})
    elif command == "versions export-plan":
        result = _call(executor, operation_id, namespace, query={"format": namespace.format})
    elif command == "versions archive":
        query = {
            "format": namespace.format,
            "acceptExclusions": False if namespace.accept_exclusions is None else namespace.accept_exclusions,
        }
        _download_output(
            executor,
            operation_id,
            namespace,
            stdout,
            json_mode,
            query=query,
            format_name=namespace.format,
        )
        return
    elif command == "split plan":
        ratio_flags = (namespace.train, namespace.validation, namespace.test)
        if namespace.source is not None:
            if any(value is not None for value in (*ratio_flags, namespace.seed, namespace.stratify)):
                raise UsageError("--from cannot be combined with ratio, seed or stratify flags")
            body = _read_json(namespace.source, stdin, "object")
        else:
            if any(value is None for value in ratio_flags):
                raise UsageError("--train, --validation and --test are required unless --from is used")
            train, validation, test = cast(tuple[int, int, int], ratio_flags)
            if train + validation + test != 10_000:
                raise UsageError("split ratios must add up to 10000 basis points")
            if namespace.seed is not None and namespace.seed > 0xFFFF_FFFF:
                raise UsageError("--seed must be at most 4294967295")
            body = {
                "ratios": {"trainBps": train, "validationBps": validation, "testBps": test},
                **({} if namespace.seed is None else {"seed": namespace.seed}),
                "stratifyByLabels": True if namespace.stratify is None else namespace.stratify,
            }
        if namespace.out is None and namespace.force:
            raise UsageError("--force requires --out")
        result = _call(executor, operation_id, namespace, body=body)
        if namespace.out is not None:
            _write_json_atomic(namespace.out, result, namespace.force)
            stderr.write(f"wrote {namespace.out}\n")
            if not json_mode:
                return
    elif command == "split apply":
        _require_yes(namespace, "applying a split replaces all automatic assignments")
        source = cast(dict[str, Any], _read_json(namespace.source, stdin, "object"))
        result = _call(executor, operation_id, namespace, body={"plan": source.get("plan", source)})
    elif command == "split assign":
        body = {
            "mediaIds": namespace.mediaIds,
            "subset": namespace.subset,
            **({} if namespace.locked is None else {"locked": namespace.locked}),
        }
        result = _call(
            executor,
            operation_id,
            namespace,
            query={"dryRun": False if namespace.dry_run is None else namespace.dry_run},
            body=body,
        )
    elif command == "split lock":
        result = _call(
            executor,
            operation_id,
            namespace,
            body={"mediaIds": namespace.mediaIds, "locked": namespace.locked},
        )
    elif command == "quality scan":
        result = _call(executor, operation_id, namespace, query={"mode": namespace.mode})
    elif command == "import":
        stderr.write(f"importing {namespace.archive}...\n")
        result = executor.upload(
            operation_id,
            namespace.archive,
            path_params=_path_params(operation_id, namespace),
            content_type="application/zip",
        )
    elif command == "export":
        split = False if namespace.split is None else namespace.split
        accept_unassigned = False if namespace.accept_unassigned is None else namespace.accept_unassigned
        if accept_unassigned and not split:
            raise UsageError("--accept-unassigned requires --split")
        if namespace.polyline_width is not None and namespace.format not in {"coco", "yolo", "voc"}:
            raise UsageError("--polyline-width is only valid for coco, yolo or voc")
        if namespace.mots_classes is not None and namespace.format != "mots":
            raise UsageError("--mots-classes is only valid with --format mots")
        namespace.out = namespace.out or f"{namespace.datasetId}-{namespace.format}.zip"
        query = {
            "format": namespace.format,
            "split": split,
            "acceptUnassignedExcluded": accept_unassigned,
            **({} if namespace.polyline_width is None else {"polylineWidth": namespace.polyline_width}),
            **(
                {}
                if namespace.mots_classes is None
                else {
                    "motsClassMapping": json.dumps(
                        _mots_mapping(namespace.mots_classes), separators=(",", ":"), sort_keys=True
                    )
                }
            ),
        }
        stderr.write(f"exporting {namespace.datasetId} as {namespace.format}...\n")
        _download_output(
            executor,
            operation_id,
            namespace,
            stdout,
            json_mode,
            query=query,
            format_name=namespace.format,
        )
        return
    elif command == "openapi show":
        if namespace.out is None and namespace.force:
            raise UsageError("--force requires --out")
        result = _call(executor, operation_id, namespace)
        if namespace.out is not None:
            _write_json_atomic(namespace.out, result, namespace.force)
            stderr.write(f"wrote {namespace.out}\n")
            if not json_mode:
                return
    elif command in {
        "projects delete",
        "datasets delete",
        "media delete",
        "tracks delete",
        "tracks keyframes delete",
        "versions delete",
        "versions restore",
        "split reset",
        "split rebalance",
    }:
        messages = {
            "projects delete": "deleting a project removes all of its datasets and annotations",
            "datasets delete": "deleting a dataset removes its media, annotations, splits and versions",
            "media delete": "deleting media also deletes its annotations and tracks",
            "tracks delete": "deleting a track removes all of its keyframes",
            "tracks keyframes delete": "deleting the last keyframe can also delete the track",
            "versions delete": "deleting a dataset version cannot be undone",
            "versions restore": "restoring replaces the current dataset state",
            "split reset": "resetting removes all split assignments",
            "split rebalance": "rebalancing changes every unlocked assignment",
        }
        _require_yes(namespace, messages[command])
        result = _call(executor, operation_id, namespace)
    else:
        result = _call(executor, operation_id, namespace)

    if command in {"projects list", "datasets list"}:
        _list_output(stdout, result, json_mode)
    elif command == "tracks list" and not json_mode and isinstance(result, list):
        _list_output(stdout, result, False)
    elif command in {
        "projects delete",
        "datasets delete",
        "media delete",
        "tracks delete",
        "versions delete",
        "split reset",
    }:
        identifier = getattr(
            namespace,
            {
                "projects delete": "projectId",
                "datasets delete": "datasetId",
                "media delete": "mediaId",
                "tracks delete": "trackId",
                "versions delete": "versionId",
                "split reset": "datasetId",
            }[command],
        )
        if json_mode:
            _json_line(stdout, {"deleted": True, "id": identifier})
        else:
            stdout.write(f"deleted {identifier}\n")
    elif command == "status" and not json_mode:
        stdout.write("ok\n")
    else:
        _json_line(stdout, result)


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    executor_factory: ExecutorFactory | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    environment = os.environ if environ is None else environ
    input_stream = sys.stdin if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    factory = _default_factory if executor_factory is None else executor_factory
    executor: OperationExecutor | None = None
    try:
        remaining, global_options = _extract_globals(arguments)
        command, command_arguments = _route(remaining)
        if command == "help":
            output_stream.write(HELP)
            return EXIT_OK

        command_parser = _command_parser(command)
        if "--help" in command_arguments or "-h" in command_arguments:
            output_stream.write(command_parser.format_help())
            return EXIT_OK
        namespace = command_parser.parse_args(command_arguments)
        raw_url = cast(str | None, global_options.get("url")) or environment.get("ANNOTATEIT_URL") or str(8420)
        try:
            base_url = normalize_base_url(raw_url)
        except AnnotateItError as error:
            raise UsageError(str(error)) from error
        raw_token = cast(str | None, global_options.get("token"))
        token = raw_token if raw_token is not None else environment.get("ANNOTATEIT_TOKEN")
        token = token.strip() if token is not None else None
        if command not in {"product info", "openapi show"} and not token:
            raise UsageError(
                "no token - pass --token, or set ANNOTATEIT_TOKEN. "
                "Create one in the app under Settings > REST API > Access tokens."
            )

        executor = factory(base_url, token, environment)
        json_mode = bool(global_options["json"])
        no_version_check = bool(global_options["no_version_check"])
        if command == "doctor":
            product = _check_compatibility(executor, error_stream, base_url)
            status = executor.call("getStatus")
            result = {"compatible": True, "apiMajor": SUPPORTED_API_MAJOR, "product": product, "status": status}
            if json_mode:
                _json_line(output_stream, result)
            else:
                product_version = product.get("productVersion", "unknown app version")
                api_version = product.get("apiVersion", "v1 (assumed)")
                output_stream.write(f"compatible - {product_version}, API {api_version}\n")
            return EXIT_OK

        if command not in {"product info", "openapi show"} and not no_version_check:
            executor = _CompatibilityExecutor(executor, error_stream, base_url)
        _dispatch(
            command,
            namespace,
            executor,
            stdin=input_stream,
            stdout=output_stream,
            stderr=error_stream,
            json_mode=json_mode,
        )
        return EXIT_OK
    except UsageError as error:
        error_stream.write(f"{error}\n\nRun 'annotateit help' for usage.\n")
        return EXIT_USAGE
    except (AnnotateItError, OSError) as error:
        error_stream.write(f"{error}\n")
        return EXIT_FAILURE
    except KeyboardInterrupt:
        error_stream.write("interrupted\n")
        return 130
    except Exception as error:  # defensive CLI boundary: never expose a traceback by default
        error_stream.write(f"unexpected error: {error}\n")
        return EXIT_FAILURE
    finally:
        if executor is not None:
            executor.close()


def main() -> int:
    return run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
