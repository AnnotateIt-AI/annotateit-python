from __future__ import annotations

from ..types import JSONValue, QualityScanMode
from .base import BaseResource, dataset_path


class QualityResource(BaseResource):
    def report(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("getDatasetQualityReport", path_params=dataset_path(project_id, dataset_id))

    def scan(self, project_id: str, dataset_id: str, *, mode: QualityScanMode = "quick") -> JSONValue:
        return self._client.call(
            "scanDatasetQuality",
            path_params=dataset_path(project_id, dataset_id),
            query={"mode": mode},
        )

    def cancel(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call("cancelDatasetQualityScan", path_params=dataset_path(project_id, dataset_id))

    def fingerprint(self, project_id: str, dataset_id: str) -> JSONValue:
        return self._client.call(
            "getDatasetQualityFingerprint",
            path_params=dataset_path(project_id, dataset_id),
        )
