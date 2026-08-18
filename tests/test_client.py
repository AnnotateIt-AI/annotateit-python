from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from annotateit_ai import (
    ApiError,
    Client,
    CompatibilityError,
    ConfigurationError,
    ResponseDecodeError,
    TransportError,
)


def _product_info() -> dict[str, object]:
    return {"name": "AnnotateIt", "apiVersion": "1.0.0", "apiBasePath": "/api/v1"}


def _transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_preflight_is_cached_and_bearer_auth_is_applied() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/product-info":
            return httpx.Response(200, json=_product_info())
        return httpx.Response(200, json=[])

    with Client("8420", token="secret", transport=_transport(handler)) as client:
        assert client.projects.list() == []
        assert client.projects.list() == []
        assert client.cached_product_info == _product_info()

    assert [request.url.path for request in requests].count("/api/v1/product-info") == 1
    assert all(request.headers["authorization"] == "Bearer secret" for request in requests)


def test_product_info_itself_does_not_recursively_preflight() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_product_info())

    with Client(transport=_transport(handler)) as client:
        assert client.system.product_info() == _product_info()

    assert len(requests) == 1


@pytest.mark.parametrize("api_version", ["2.0.0", "v1", "", None])
def test_preflight_rejects_incompatible_or_invalid_versions(api_version: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"apiVersion": api_version, "apiBasePath": "/api/v1"},
            request=request,
        )

    with Client(transport=_transport(handler)) as client, pytest.raises(CompatibilityError):
        client.projects.list()


def test_preflight_rejects_a_different_base_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"apiVersion": "1.0.0", "apiBasePath": "/api/v2"})

    with Client(transport=_transport(handler)) as client, pytest.raises(CompatibilityError):
        client.projects.list()


def test_query_encoding_repeats_arrays_and_lowercases_booleans() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    with Client(check_compatibility=False, transport=_transport(handler)) as client:
        client.media.list("project / one", "dataset", statuses=["annotated", "to_revisit"])

    request = seen[0]
    assert request.url.raw_path.split(b"?", 1)[0] == b"/api/v1/projects/project%20%2F%20one/datasets/dataset/media"
    assert request.url.params.get_list("status") == ["annotated", "to_revisit"]
    assert request.url.params["limit"] == "50"
    assert request.url.params["skip"] == "0"


def test_structured_api_error_is_preserved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"error": {"code": "PROJECT_BUSY", "message": "project is busy", "details": {"retry": True}}},
        )

    with Client(check_compatibility=False, transport=_transport(handler)) as client, pytest.raises(ApiError) as caught:
        client.projects.get("project")

    assert caught.value.status_code == 409
    assert caught.value.code == "PROJECT_BUSY"
    assert caught.value.message == "project is busy"
    assert caught.value.details == {"retry": True}
    assert caught.value.method == "GET"


def test_transport_and_decode_errors_are_sdk_owned() -> None:
    def transport_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with Client(check_compatibility=False, transport=_transport(transport_failure)) as client:
        with pytest.raises(TransportError) as caught:
            client.projects.list()
        assert isinstance(caught.value.cause, httpx.ConnectError)

    def invalid_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})

    with Client(check_compatibility=False, transport=_transport(invalid_json)) as client:
        with pytest.raises(ResponseDecodeError):
            client.projects.list()


@pytest.mark.parametrize(
    "path",
    [
        "https://attacker.example/",
        "//attacker.example/",
        "/../status",
        "/%2e%2e/status",
        "/%252e%252e/status",
        "/projects?redirect=https://attacker.example",
        "/projects\\..\\status",
    ],
)
def test_generic_request_cannot_escape_the_api_base(path: str) -> None:
    with Client(check_compatibility=False, transport=_transport(lambda request: httpx.Response(200))) as client:
        with pytest.raises(ConfigurationError):
            client.request("GET", path)


def test_context_manager_closes_client() -> None:
    client = Client(check_compatibility=False, transport=_transport(lambda request: httpx.Response(200)))
    with client as entered:
        assert entered is client
        assert not client.is_closed
    assert client.is_closed


def test_default_timeout_covers_the_servers_five_minute_request_window() -> None:
    seen_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_timeout.update(request.extensions["timeout"])
        return httpx.Response(200, json=[])

    with Client(check_compatibility=False, transport=_transport(handler)) as client:
        client.projects.list()

    assert seen_timeout == {"connect": 5.0, "read": 310.0, "write": 310.0, "pool": 310.0}
