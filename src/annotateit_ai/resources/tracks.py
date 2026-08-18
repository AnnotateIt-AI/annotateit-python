from __future__ import annotations

from collections.abc import Mapping

from ..types import JSONInput, JSONValue
from .base import BaseResource, media_path, track_path


class TracksResource(BaseResource):
    def list(self, project_id: str, dataset_id: str, media_id: str) -> JSONValue:
        return self._client.call("listTracks", path_params=media_path(project_id, dataset_id, media_id))

    def create(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        track: Mapping[str, JSONInput],
    ) -> JSONValue:
        return self._client.call(
            "createTrack",
            path_params=media_path(project_id, dataset_id, media_id),
            json_body=dict(track),
        )

    def get(self, project_id: str, dataset_id: str, media_id: str, track_id: str) -> JSONValue:
        return self._client.call(
            "getTrack",
            path_params=track_path(project_id, dataset_id, media_id, track_id),
        )

    def update(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        track_id: str,
        track: Mapping[str, JSONInput],
    ) -> JSONValue:
        return self._client.call(
            "updateTrack",
            path_params=track_path(project_id, dataset_id, media_id, track_id),
            json_body=dict(track),
        )

    def delete(self, project_id: str, dataset_id: str, media_id: str, track_id: str) -> JSONValue:
        return self._client.call(
            "deleteTrack",
            path_params=track_path(project_id, dataset_id, media_id, track_id),
        )

    def upsert_keyframe(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        track_id: str,
        frame: int,
        keyframe: Mapping[str, JSONInput],
    ) -> JSONValue:
        return self._client.call(
            "upsertTrackKeyframe",
            path_params={**track_path(project_id, dataset_id, media_id, track_id), "frame": frame},
            json_body=dict(keyframe),
        )

    def delete_keyframe(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        track_id: str,
        frame: int,
    ) -> JSONValue:
        return self._client.call(
            "deleteTrackKeyframe",
            path_params={**track_path(project_id, dataset_id, media_id, track_id), "frame": frame},
        )
