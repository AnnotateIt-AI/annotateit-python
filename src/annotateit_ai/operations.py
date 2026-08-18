from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal
from urllib.parse import quote

from .errors import ConfigurationError

HTTPMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
_PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True, slots=True)
class Operation:
    operation_id: str
    method: HTTPMethod
    path: str
    success_statuses: tuple[int, ...]
    resource: str
    python_name: str
    download: bool = False
    upload: bool = False

    def render_path(self, parameters: Mapping[str, object] | None = None) -> str:
        supplied = {} if parameters is None else parameters
        required = set(_PATH_PARAMETER.findall(self.path))
        missing = sorted(required.difference(supplied))
        extra = sorted(set(supplied).difference(required))
        if missing:
            raise ConfigurationError(f"{self.operation_id} is missing path parameters: {', '.join(missing)}")
        if extra:
            raise ConfigurationError(f"{self.operation_id} got unknown path parameters: {', '.join(extra)}")

        return _PATH_PARAMETER.sub(lambda match: quote(str(supplied[match.group(1)]), safe=""), self.path)


def _op(
    operation_id: str,
    method: HTTPMethod,
    path: str,
    status: int,
    resource: str,
    python_name: str,
    *,
    download: bool = False,
    upload: bool = False,
) -> Operation:
    return Operation(operation_id, method, path, (status,), resource, python_name, download, upload)


_OPERATIONS = (
    _op("listProjects", "GET", "/projects", 200, "projects", "list"),
    _op("createProject", "POST", "/projects", 201, "projects", "create"),
    _op("importProjectArchive", "POST", "/projects:import", 201, "projects", "import_archive", upload=True),
    _op("getProject", "GET", "/projects/{projectId}", 200, "projects", "get"),
    _op("updateProject", "PATCH", "/projects/{projectId}", 200, "projects", "update"),
    _op("deleteProject", "DELETE", "/projects/{projectId}", 204, "projects", "delete"),
    _op("getProjectStatus", "GET", "/projects/{projectId}/status", 200, "projects", "status"),
    _op("duplicateProject", "POST", "/projects/{projectId}:duplicate", 201, "projects", "duplicate"),
    _op(
        "exportProjectArchive",
        "GET",
        "/projects/{projectId}/export",
        200,
        "projects",
        "export_archive",
        download=True,
    ),
    _op("listProjectActivity", "GET", "/projects/{projectId}/activity-events", 200, "projects", "activity"),
    _op("listDatasets", "GET", "/projects/{projectId}/datasets", 200, "datasets", "list"),
    _op("createDataset", "POST", "/projects/{projectId}/datasets", 201, "datasets", "create"),
    _op("updateDataset", "PATCH", "/projects/{projectId}/datasets/{datasetId}", 200, "datasets", "update"),
    _op("deleteDataset", "DELETE", "/projects/{projectId}/datasets/{datasetId}", 204, "datasets", "delete"),
    _op("copyDataset", "POST", "/projects/{projectId}/datasets/{datasetId}:copy", 201, "datasets", "copy"),
    _op(
        "getDatasetStatistics",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/statistics",
        200,
        "datasets",
        "statistics",
    ),
    _op(
        "exportDataset",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/export",
        200,
        "datasets",
        "export",
        download=True,
    ),
    _op(
        "importDataset",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}:import",
        200,
        "datasets",
        "import_archive",
        upload=True,
    ),
    _op("listVersions", "GET", "/projects/{projectId}/datasets/{datasetId}/versions", 200, "versions", "list"),
    _op("createVersion", "POST", "/projects/{projectId}/datasets/{datasetId}/versions", 201, "versions", "create"),
    _op(
        "getVersion",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}",
        200,
        "versions",
        "get",
    ),
    _op(
        "deleteVersion",
        "DELETE",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}",
        204,
        "versions",
        "delete",
    ),
    _op(
        "getVersionDiff",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}/diff",
        200,
        "versions",
        "diff",
    ),
    _op(
        "getRestorePreflight",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}/restore-preflight",
        200,
        "versions",
        "restore_preflight",
    ),
    _op(
        "restoreVersion",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}:restore",
        200,
        "versions",
        "restore",
    ),
    _op(
        "getVersionExportPlan",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}/export-plan",
        200,
        "versions",
        "export_plan",
    ),
    _op(
        "downloadVersionArchive",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/versions/{versionId}/archive",
        200,
        "versions",
        "download_archive",
        download=True,
    ),
    _op("getSplitState", "GET", "/projects/{projectId}/datasets/{datasetId}/split", 200, "splits", "get"),
    _op("resetSplit", "DELETE", "/projects/{projectId}/datasets/{datasetId}/split", 204, "splits", "reset"),
    _op(
        "validateSplit",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/split/validation",
        200,
        "splits",
        "validate",
    ),
    _op(
        "getSplitManifest",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/split/manifest",
        200,
        "splits",
        "manifest",
    ),
    _op("planSplit", "POST", "/projects/{projectId}/datasets/{datasetId}/split/plan", 200, "splits", "plan"),
    _op("applySplit", "POST", "/projects/{projectId}/datasets/{datasetId}/split:apply", 200, "splits", "apply"),
    _op(
        "assignSplitMedia",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/split/assignments",
        200,
        "splits",
        "assign",
    ),
    _op(
        "setSplitLocked",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/split/assignments:lock",
        200,
        "splits",
        "set_locked",
    ),
    _op(
        "rebalanceSplit",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/split:rebalance",
        200,
        "splits",
        "rebalance",
    ),
    _op(
        "getDatasetQualityReport",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/quality",
        200,
        "quality",
        "report",
    ),
    _op(
        "scanDatasetQuality",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/quality:scan",
        200,
        "quality",
        "scan",
    ),
    _op(
        "cancelDatasetQualityScan",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/quality:cancel",
        200,
        "quality",
        "cancel",
    ),
    _op(
        "getDatasetQualityFingerprint",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/quality/fingerprint",
        200,
        "quality",
        "fingerprint",
    ),
    _op("listMedia", "GET", "/projects/{projectId}/datasets/{datasetId}/media", 200, "media", "list"),
    _op("uploadMedia", "POST", "/projects/{projectId}/datasets/{datasetId}/media", 201, "media", "upload", upload=True),
    _op("getMedia", "GET", "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}", 200, "media", "get"),
    _op(
        "deleteMedia",
        "DELETE",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}",
        204,
        "media",
        "delete",
    ),
    _op(
        "downloadMedia",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/content",
        200,
        "media",
        "download",
        download=True,
    ),
    _op(
        "getAnnotations",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/annotations",
        200,
        "annotations",
        "get",
    ),
    _op(
        "saveAnnotations",
        "PUT",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/annotations",
        200,
        "annotations",
        "save",
    ),
    _op(
        "getFrameAnnotations",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/frames/{frameNumber}/annotations",
        200,
        "annotations",
        "get_frame",
    ),
    _op(
        "saveFrameAnnotations",
        "PUT",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/frames/{frameNumber}/annotations",
        200,
        "annotations",
        "save_frame",
    ),
    _op(
        "listTracks",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks",
        200,
        "tracks",
        "list",
    ),
    _op(
        "createTrack",
        "POST",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks",
        201,
        "tracks",
        "create",
    ),
    _op(
        "getTrack",
        "GET",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks/{trackId}",
        200,
        "tracks",
        "get",
    ),
    _op(
        "updateTrack",
        "PUT",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks/{trackId}",
        200,
        "tracks",
        "update",
    ),
    _op(
        "deleteTrack",
        "DELETE",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks/{trackId}",
        204,
        "tracks",
        "delete",
    ),
    _op(
        "upsertTrackKeyframe",
        "PUT",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks/{trackId}/keyframes/{frame}",
        200,
        "tracks",
        "upsert_keyframe",
    ),
    _op(
        "deleteTrackKeyframe",
        "DELETE",
        "/projects/{projectId}/datasets/{datasetId}/media/{mediaId}/tracks/{trackId}/keyframes/{frame}",
        200,
        "tracks",
        "delete_keyframe",
    ),
    _op("getStatus", "GET", "/status", 200, "system", "status"),
    _op("getProductInfo", "GET", "/product-info", 200, "system", "product_info"),
    _op("getOpenApiDocument", "GET", "/openapi.json", 200, "system", "openapi_document"),
)

OPERATIONS = MappingProxyType({entry.operation_id: entry for entry in _OPERATIONS})

if len(OPERATIONS) != len(_OPERATIONS):  # pragma: no cover - import-time invariant
    raise RuntimeError("duplicate AnnotateIt operationId in SDK registry")


def get_operation(operation_id: str) -> Operation:
    try:
        return OPERATIONS[operation_id]
    except KeyError as error:
        raise ConfigurationError(f"unknown AnnotateIt operationId: {operation_id!r}") from error
