from __future__ import annotations

from pathlib import Path

from ..client import UNSET
from ..types import DatasetFormat, JSONInput, JSONValue, MediaScope, MediaTypeSelection, Pathish
from .base import BaseResource, dataset_path


class DatasetsResource(BaseResource):
    def list(self, project_id: str) -> JSONValue:
        return self._client.call("listDatasets", path_params={"projectId": project_id})

    def create(self, project_id: str, name: str) -> JSONValue:
        return self._client.call(
            "createDataset",
            path_params={"projectId": project_id},
            json_body={"name": name},
        )

    def update(self, project_id: str, dataset_id: str, name: str) -> JSONValue:
        return self._client.call(
            "updateDataset",
            path_params=dataset_path(project_id, dataset_id),
            json_body={"name": name},
        )

    def delete(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("deleteDataset", path_params=dataset_path(project_id, dataset_id))

    def copy(
        self,
        project_id: str,
        dataset_id: str,
        *,
        name: str | None = None,
        media_scope: MediaScope | None = None,
        media_types: MediaTypeSelection | None = None,
        include_annotations: bool | None = None,
    ) -> JSONValue:
        body: dict[str, JSONInput] = {}
        if name is not None:
            body["name"] = name
        if media_scope is not None:
            body["mediaScope"] = media_scope
        if media_types is not None:
            body["mediaTypes"] = media_types
        if include_annotations is not None:
            body["includeAnnotations"] = include_annotations
        return self._client.call(
            "copyDataset",
            path_params=dataset_path(project_id, dataset_id),
            json_body=body if body else UNSET,
        )

    def statistics(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("getDatasetStatistics", path_params=dataset_path(project_id, dataset_id))

    def export(
        self,
        project_id: str,
        dataset_id: str,
        destination: Pathish,
        *,
        format: DatasetFormat,
        split: bool = False,
        accept_unassigned_excluded: bool = False,
        polyline_width: float | None = None,
        mots_class_mapping: str | None = None,
        overwrite: bool = False,
    ) -> Path:
        return self._client.download(
            "exportDataset",
            destination,
            path_params=dataset_path(project_id, dataset_id),
            query={
                "format": format,
                "split": split,
                "acceptUnassignedExcluded": accept_unassigned_excluded,
                "polylineWidth": polyline_width,
                "motsClassMapping": mots_class_mapping,
            },
            overwrite=overwrite,
        )

    def import_archive(
        self,
        project_id: str,
        dataset_id: str,
        file: Pathish,
        *,
        content_type: str = "application/zip",
    ) -> JSONValue:
        return self._client.upload(
            "importDataset",
            file,
            path_params=dataset_path(project_id, dataset_id),
            content_type=content_type,
        )
