from __future__ import annotations

from pathlib import Path

from ..client import UNSET
from ..types import DatasetFormat, JSONInput, JSONValue, Pathish
from .base import BaseResource, dataset_path, version_path


class VersionsResource(BaseResource):
    def list(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("listVersions", path_params=dataset_path(project_id, dataset_id))

    def create(
        self,
        project_id: str,
        dataset_id: str,
        *,
        name: str | None = None,
        note: str | None = None,
    ) -> JSONValue:
        body: dict[str, JSONInput] = {}
        if name is not None:
            body["name"] = name
        if note is not None:
            body["note"] = note
        return self._client.call(
            "createVersion",
            path_params=dataset_path(project_id, dataset_id),
            json_body=body if body else UNSET,
        )

    def get(self, project_id: str, dataset_id: str, version_id: str) -> JSONValue:
        return self._client.call("getVersion", path_params=version_path(project_id, dataset_id, version_id))

    def delete(self, project_id: str, dataset_id: str, version_id: str) -> JSONValue:
        return self._client.call("deleteVersion", path_params=version_path(project_id, dataset_id, version_id))

    def diff(
        self,
        project_id: str,
        dataset_id: str,
        version_id: str,
        *,
        target: str | None = None,
    ) -> JSONValue:
        return self._client.call(
            "getVersionDiff",
            path_params=version_path(project_id, dataset_id, version_id),
            query={"target": target},
        )

    def restore_preflight(self, project_id: str, dataset_id: str, version_id: str) -> JSONValue:
        return self._client.call(
            "getRestorePreflight",
            path_params=version_path(project_id, dataset_id, version_id),
        )

    def restore(self, project_id: str, dataset_id: str, version_id: str) -> JSONValue:
        return self._client.call("restoreVersion", path_params=version_path(project_id, dataset_id, version_id))

    def export_plan(self, project_id: str, dataset_id: str, version_id: str, *, format: DatasetFormat) -> JSONValue:
        return self._client.call(
            "getVersionExportPlan",
            path_params=version_path(project_id, dataset_id, version_id),
            query={"format": format},
        )

    def download_archive(
        self,
        project_id: str,
        dataset_id: str,
        version_id: str,
        destination: Pathish,
        *,
        format: DatasetFormat,
        accept_exclusions: bool = False,
        overwrite: bool = False,
    ) -> Path:
        return self._client.download(
            "downloadVersionArchive",
            destination,
            path_params=version_path(project_id, dataset_id, version_id),
            query={"format": format, "acceptExclusions": accept_exclusions},
            overwrite=overwrite,
        )
