from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import Client


class BaseResource:
    __slots__ = ("_client",)

    def __init__(self, client: Client) -> None:
        self._client = client


def dataset_path(project_id: str, dataset_id: str) -> dict[str, object]:
    return {"projectId": project_id, "datasetId": dataset_id}


def media_path(project_id: str, dataset_id: str, media_id: str) -> dict[str, object]:
    return {**dataset_path(project_id, dataset_id), "mediaId": media_id}


def track_path(project_id: str, dataset_id: str, media_id: str, track_id: str) -> dict[str, object]:
    return {**media_path(project_id, dataset_id, media_id), "trackId": track_id}


def version_path(project_id: str, dataset_id: str, version_id: str) -> dict[str, object]:
    return {**dataset_path(project_id, dataset_id), "versionId": version_id}
