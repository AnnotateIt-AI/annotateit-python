from __future__ import annotations

import json

import httpx
import pytest

from annotateit_ai import Client, PaginationError


def test_ergonomic_wrappers_map_python_names_to_wire_contract() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    with Client(check_compatibility=False, transport=httpx.MockTransport(handler)) as client:
        client.splits.plan(
            "project",
            "dataset",
            train_bps=8000,
            validation_bps=1000,
            test_bps=1000,
            seed=42,
            stratify_by_labels=False,
        )
        client.splits.assign(
            "project",
            "dataset",
            ["m1", "m2"],
            "validation",
            locked=True,
            dry_run=True,
        )

    plan = seen[0]
    assert plan.method == "POST"
    assert plan.url.path.endswith("/split/plan")
    assert json.loads(plan.content) == {
        "ratios": {"trainBps": 8000, "validationBps": 1000, "testBps": 1000},
        "seed": 42,
        "stratifyByLabels": False,
    }

    assignment = seen[1]
    assert assignment.url.params["dryRun"] == "true"
    assert json.loads(assignment.content) == {
        "mediaIds": ["m1", "m2"],
        "subset": "validation",
        "locked": True,
    }


def test_media_auto_pagination_honors_max_items_and_repeated_query_values() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        skip = int(request.url.params["skip"])
        pages = {
            0: {"media": [{"id": "m1"}, {"id": "m2"}], "nextSkip": 2},
            2: {"media": [{"id": "m3"}, {"id": "m4"}], "nextSkip": 4},
        }
        return httpx.Response(200, json=pages[skip])

    with Client(check_compatibility=False, transport=httpx.MockTransport(handler)) as client:
        media = client.media.list_all(
            "p",
            "d",
            statuses=["annotated", "to_revisit"],
            page_size=2,
            max_items=3,
        )

    assert [item["id"] for item in media] == ["m1", "m2", "m3"]
    assert seen[1].url.params["limit"] == "1"
    assert seen[1].url.params.get_list("status") == ["annotated", "to_revisit"]


def test_activity_auto_pagination_and_cursor_loop_guard() -> None:
    def successful(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(200, json={"items": [{"id": "e1"}], "nextCursor": "next", "hasMore": True})
        return httpx.Response(200, json={"items": [{"id": "e2"}], "nextCursor": None, "hasMore": False})

    with Client(check_compatibility=False, transport=httpx.MockTransport(successful)) as client:
        assert [item["id"] for item in client.projects.list_all_activity("p")] == ["e1", "e2"]

    def looping(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [{"id": "event"}], "nextCursor": "same", "hasMore": True})

    with Client(check_compatibility=False, transport=httpx.MockTransport(looping)) as client:
        with pytest.raises(PaginationError, match="did not advance"):
            client.projects.list_all_activity("p", cursor="same")


def test_media_non_advancing_skip_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"media": [{"id": "m1"}], "nextSkip": 0})

    with Client(check_compatibility=False, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PaginationError, match="did not advance"):
            client.media.list_all("p", "d")
