from __future__ import annotations

import builtins
from collections.abc import Iterator, Sequence
from pathlib import Path

from ..errors import ConfigurationError, PaginationError
from ..types import AnnotationStatus, JSONObject, JSONValue, Pathish
from .base import BaseResource, dataset_path, media_path


class MediaResource(BaseResource):
    def list(
        self,
        project_id: str,
        dataset_id: str,
        *,
        limit: int = 50,
        skip: int = 0,
        statuses: Sequence[AnnotationStatus] | None = None,
    ) -> JSONValue:
        return self._client.call(
            "listMedia",
            path_params=dataset_path(project_id, dataset_id),
            query={"limit": limit, "skip": skip, "status": statuses},
        )

    def iter_all(
        self,
        project_id: str,
        dataset_id: str,
        *,
        statuses: Sequence[AnnotationStatus] | None = None,
        page_size: int = 100,
        max_items: int | None = None,
    ) -> Iterator[JSONObject]:
        if page_size < 1:
            raise ConfigurationError("media page_size must be at least 1")
        if max_items is not None and max_items < 0:
            raise ConfigurationError("max_items must be non-negative")

        yielded = 0
        skip = 0
        seen_skips = {skip}
        while max_items is None or yielded < max_items:
            request_limit = page_size if max_items is None else min(page_size, max_items - yielded)
            page = self.list(project_id, dataset_id, limit=request_limit, skip=skip, statuses=statuses)
            if not isinstance(page, dict):
                raise PaginationError("listMedia", "response is missing a media array")
            items = page.get("media")
            if not isinstance(items, list):
                raise PaginationError("listMedia", "response is missing a media array")
            for item in items:
                if not isinstance(item, dict):
                    raise PaginationError("listMedia", "media must contain JSON objects")
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            candidate = page.get("nextSkip")
            if candidate is None:
                return
            if isinstance(candidate, bool) or not isinstance(candidate, int):
                raise PaginationError("listMedia", "nextSkip must be an integer or null")
            if candidate <= skip or candidate in seen_skips:
                raise PaginationError("listMedia", "nextSkip did not advance")
            if not items:
                raise PaginationError("listMedia", "empty page advertised a continuation")
            seen_skips.add(candidate)
            skip = candidate

    def list_all(
        self,
        project_id: str,
        dataset_id: str,
        *,
        statuses: Sequence[AnnotationStatus] | None = None,
        page_size: int = 100,
        max_items: int | None = None,
    ) -> builtins.list[JSONObject]:
        return builtins.list(
            self.iter_all(
                project_id,
                dataset_id,
                statuses=statuses,
                page_size=page_size,
                max_items=max_items,
            )
        )

    def upload(
        self,
        project_id: str,
        dataset_id: str,
        file: Pathish,
        *,
        content_type: str | None = None,
    ) -> JSONValue:
        return self._client.upload(
            "uploadMedia",
            file,
            path_params=dataset_path(project_id, dataset_id),
            content_type=content_type,
        )

    def get(self, project_id: str, dataset_id: str, media_id: str) -> JSONValue:
        return self._client.call("getMedia", path_params=media_path(project_id, dataset_id, media_id))

    def delete(self, project_id: str, dataset_id: str, media_id: str) -> JSONValue:
        return self._client.call("deleteMedia", path_params=media_path(project_id, dataset_id, media_id))

    def download(
        self,
        project_id: str,
        dataset_id: str,
        media_id: str,
        destination: Pathish,
        *,
        overwrite: bool = False,
    ) -> Path:
        return self._client.download(
            "downloadMedia",
            destination,
            path_params=media_path(project_id, dataset_id, media_id),
            overwrite=overwrite,
        )
