from __future__ import annotations

import builtins
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

from ..errors import ConfigurationError, PaginationError
from ..types import ActivityEventType, CreatableProjectDomain, JSONInput, JSONObject, JSONValue, Pathish
from .base import BaseResource


class ProjectsResource(BaseResource):
    def list(self) -> JSONValue:
        return self._client.call("listProjects")

    def create(
        self,
        name: str,
        task_type: CreatableProjectDomain,
        *,
        labels: Sequence[Mapping[str, JSONInput]] | None = None,
    ) -> JSONValue:
        body: dict[str, JSONInput] = {"name": name, "taskType": task_type}
        if labels is not None:
            body["labels"] = [dict(label) for label in labels]
        return self._client.call("createProject", json_body=body)

    def import_archive(
        self,
        file: Pathish,
        *,
        project_name: str | None = None,
        keep_original_dates: bool = False,
        content_type: str = "application/zip",
    ) -> JSONValue:
        return self._client.upload(
            "importProjectArchive",
            file,
            query={"projectName": project_name, "keepOriginalDates": keep_original_dates},
            content_type=content_type,
        )

    def get(self, project_id: str) -> JSONValue:
        return self._client.call("getProject", path_params={"projectId": project_id})

    def update(
        self,
        project_id: str,
        *,
        name: str | None = None,
        labels: Sequence[Mapping[str, JSONInput]] | None = None,
    ) -> JSONValue:
        body: dict[str, JSONInput] = {}
        if name is not None:
            body["name"] = name
        if labels is not None:
            body["labels"] = [dict(label) for label in labels]
        return self._client.call("updateProject", path_params={"projectId": project_id}, json_body=body)

    def delete(self, project_id: str) -> JSONValue:
        return self._client.call("deleteProject", path_params={"projectId": project_id})

    def status(self, project_id: str) -> JSONValue:
        return self._client.call("getProjectStatus", path_params={"projectId": project_id})

    def duplicate(self, project_id: str, name: str) -> JSONValue:
        return self._client.call(
            "duplicateProject",
            path_params={"projectId": project_id},
            json_body={"name": name},
        )

    def export_archive(self, project_id: str, destination: Pathish, *, overwrite: bool = False) -> Path:
        return self._client.download(
            "exportProjectArchive",
            destination,
            path_params={"projectId": project_id},
            overwrite=overwrite,
        )

    def activity(
        self,
        project_id: str,
        *,
        dataset_id: str | None = None,
        event_types: Sequence[ActivityEventType] | None = None,
        actor_id: str | None = None,
        from_: str | None = None,
        to: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> JSONValue:
        return self._client.call(
            "listProjectActivity",
            path_params={"projectId": project_id},
            query={
                "datasetId": dataset_id,
                "eventType": event_types,
                "actorId": actor_id,
                "from": from_,
                "to": to,
                "cursor": cursor,
                "limit": limit,
            },
        )

    def iter_activity(
        self,
        project_id: str,
        *,
        dataset_id: str | None = None,
        event_types: Sequence[ActivityEventType] | None = None,
        actor_id: str | None = None,
        from_: str | None = None,
        to: str | None = None,
        cursor: str | None = None,
        page_size: int = 200,
        max_items: int | None = None,
    ) -> Iterator[JSONObject]:
        if not 1 <= page_size <= 200:
            raise ConfigurationError("activity page_size must be between 1 and 200")
        if max_items is not None and max_items < 0:
            raise ConfigurationError("max_items must be non-negative")

        yielded = 0
        next_cursor = cursor
        seen_cursors = set() if cursor is None else {cursor}
        while max_items is None or yielded < max_items:
            request_limit = page_size if max_items is None else min(page_size, max_items - yielded)
            page = self.activity(
                project_id,
                dataset_id=dataset_id,
                event_types=event_types,
                actor_id=actor_id,
                from_=from_,
                to=to,
                cursor=next_cursor,
                limit=request_limit,
            )
            if not isinstance(page, dict):
                raise PaginationError("listProjectActivity", "response is missing an items array")
            items = page.get("items")
            if not isinstance(items, list):
                raise PaginationError("listProjectActivity", "response is missing an items array")
            for item in items:
                if not isinstance(item, dict):
                    raise PaginationError("listProjectActivity", "items must contain JSON objects")
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            has_more = page.get("hasMore")
            if has_more is not True:
                return
            candidate = page.get("nextCursor")
            if not isinstance(candidate, str) or not candidate or candidate in seen_cursors:
                raise PaginationError("listProjectActivity", "nextCursor did not advance")
            if not items:
                raise PaginationError("listProjectActivity", "empty page advertised a continuation")
            seen_cursors.add(candidate)
            next_cursor = candidate

    def list_all_activity(
        self,
        project_id: str,
        *,
        dataset_id: str | None = None,
        event_types: Sequence[ActivityEventType] | None = None,
        actor_id: str | None = None,
        from_: str | None = None,
        to: str | None = None,
        cursor: str | None = None,
        page_size: int = 200,
        max_items: int | None = None,
    ) -> builtins.list[JSONObject]:
        return builtins.list(
            self.iter_activity(
                project_id,
                dataset_id=dataset_id,
                event_types=event_types,
                actor_id=actor_id,
                from_=from_,
                to=to,
                cursor=cursor,
                page_size=page_size,
                max_items=max_items,
            )
        )
