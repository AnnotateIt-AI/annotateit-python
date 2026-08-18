from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..types import JSONInput, JSONValue
from .base import BaseResource, media_path


class AnnotationsResource(BaseResource):
    def get(self, project_id: str, dataset_id: str, media_id: str) -> JSONValue:
        return self._client.call("getAnnotations", path_params=media_path(project_id, dataset_id, media_id))

    def save(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        annotations: Sequence[Mapping[str, JSONInput]],
    ) -> JSONValue:
        return self._client.call(
            "saveAnnotations",
            path_params=media_path(project_id, dataset_id, media_id),
            json_body=[dict(annotation) for annotation in annotations],
        )

    def get_frame(self, project_id: str, dataset_id: str, media_id: str, frame_number: int) -> JSONValue:
        return self._client.call(
            "getFrameAnnotations",
            path_params={**media_path(project_id, dataset_id, media_id), "frameNumber": frame_number},
        )

    def save_frame(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        frame_number: int,
        annotations: Sequence[Mapping[str, JSONInput]],
    ) -> JSONValue:
        return self._client.call(
            "saveFrameAnnotations",
            path_params={**media_path(project_id, dataset_id, media_id), "frameNumber": frame_number},
            json_body=[dict(annotation) for annotation in annotations],
        )
