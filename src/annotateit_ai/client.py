from __future__ import annotations

import json
import mimetypes
import os
import re
import ssl
import tempfile
import threading
from collections.abc import Collection, Mapping
from pathlib import Path
from types import TracebackType
from typing import Any, Final, cast
from urllib.parse import unquote, urlsplit

import httpx

from ._version import __version__
from .config import ClientConfig
from .errors import (
    ApiError,
    CompatibilityError,
    ConfigurationError,
    FileTransferError,
    ResponseDecodeError,
    TransportError,
)
from .operations import get_operation
from .types import JSONInput, JSONObject, JSONValue, Pathish, Query, QueryScalar

SUPPORTED_API_MAJOR: Final = 1
DEFAULT_TIMEOUT: Final = httpx.Timeout(310.0, connect=5.0)
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


class _Unset:
    __slots__ = ()


UNSET: Final = _Unset()


def _query_scalar(value: QueryScalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def encode_query(query: Query | None) -> list[tuple[str, str]]:
    """Encode booleans lowercase and arrays as repeated OpenAPI form parameters."""

    if query is None:
        return []

    encoded: list[tuple[str, str]] = []
    for name, value in query.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            encoded.append((name, json.dumps(value, separators=(",", ":"), sort_keys=True)))
            continue
        if isinstance(value, (str, int, float, bool)):
            encoded.append((name, _query_scalar(value)))
            continue
        encoded.extend((name, _query_scalar(item)) for item in value)
    return encoded


def _error_from_response(response: httpx.Response) -> ApiError:
    try:
        raw = response.json()
    except ValueError:
        raw = None

    message = response.reason_phrase or "request failed"
    code: str | None = None
    details: dict[str, Any] | None = None
    if isinstance(raw, dict):
        nested = raw.get("error")
        if isinstance(nested, dict):
            if isinstance(nested.get("message"), str):
                message = nested["message"]
            if isinstance(nested.get("code"), str):
                code = nested["code"]
            if isinstance(nested.get("details"), dict):
                details = nested["details"]
        if code is None and isinstance(raw.get("code"), str):
            code = raw["code"]
        if message == (response.reason_phrase or "request failed") and isinstance(raw.get("message"), str):
            message = raw["message"]

    request = response.request
    return ApiError(response.status_code, message, code, details, request.method, str(request.url))


class Client:
    """Synchronous client for the AnnotateIt local REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        check_compatibility: bool = True,
        timeout: httpx.Timeout | float | None = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
        verify: ssl.SSLContext | str | bool = True,
        trust_env: bool = False,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.config = ClientConfig.resolve(
            base_url,
            token,
            check_compatibility=check_compatibility,
            env=env,
        )
        headers = {"accept": "application/json", "user-agent": f"annotateit-ai-python/{__version__}"}
        if self.config.token is not None:
            headers["authorization"] = f"Bearer {self.config.token}"

        self._http = httpx.Client(
            base_url=f"{self.config.base_url}/",
            headers=headers,
            timeout=timeout,
            transport=transport,
            verify=verify,
            trust_env=trust_env,
            follow_redirects=False,
        )
        self._compatibility_lock = threading.Lock()
        self._product_info: JSONObject | None = None

        # Imported here to keep resource modules free to type-check against Client without a cycle.
        from .resources import (
            AnnotationsResource,
            DatasetsResource,
            MediaResource,
            ProjectsResource,
            QualityResource,
            SplitsResource,
            SystemResource,
            TracksResource,
            VersionsResource,
        )

        self.projects = ProjectsResource(self)
        self.datasets = DatasetsResource(self)
        self.media = MediaResource(self)
        self.annotations = AnnotationsResource(self)
        self.tracks = TracksResource(self)
        self.versions = VersionsResource(self)
        self.splits = SplitsResource(self)
        self.quality = QualityResource(self)
        self.system = SystemResource(self)

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def is_closed(self) -> bool:
        return self._http.is_closed

    @property
    def cached_product_info(self) -> JSONObject | None:
        return None if self._product_info is None else dict(self._product_info)

    def close(self) -> None:
        self._http.close()

    def ensure_compatible(self) -> JSONObject:
        """Fetch product-info once and require the advertised API to be compatible with v1."""

        if self._product_info is not None:
            return dict(self._product_info)

        with self._compatibility_lock:
            if self._product_info is not None:
                return dict(self._product_info)

            raw = self.request_json(
                "GET",
                "/product-info",
                expected_status=(200,),
                check_compatibility=False,
            )
            if not isinstance(raw, dict):
                raise CompatibilityError("AnnotateIt product-info response is not a JSON object")

            info: JSONObject = raw
            version = info.get("apiVersion")
            if not isinstance(version, str):
                raise CompatibilityError("AnnotateIt does not advertise apiVersion", api_version=None)
            match = _SEMVER.fullmatch(version)
            if match is None:
                raise CompatibilityError(
                    f"AnnotateIt reported an invalid apiVersion: {version!r}",
                    api_version=version,
                )
            if int(match.group(1)) != SUPPORTED_API_MAJOR:
                raise CompatibilityError(
                    f"incompatible API version {version}: this SDK supports major version {SUPPORTED_API_MAJOR}.x",
                    api_version=version,
                )

            reported_path = info.get("apiBasePath")
            configured_path = urlsplit(self.config.base_url).path.rstrip("/")
            if isinstance(reported_path, str) and reported_path.rstrip("/") != configured_path:
                raise CompatibilityError(
                    f"AnnotateIt reports API base path {reported_path!r}, but the SDK uses {configured_path!r}",
                    api_version=version,
                )

            self._product_info = info
            return dict(info)

    def _ensure_if_enabled(self, enabled: bool) -> None:
        if enabled and self.config.check_compatibility:
            self.ensure_compatible()

    @staticmethod
    def _relative_path(path: str) -> str:
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "://" in path
            or "?" in path
            or "#" in path
            or any(ord(character) < 32 or ord(character) == 127 for character in path)
        ):
            raise ConfigurationError("API path must be an absolute path within the configured API base")

        decoded = path
        for _ in range(4):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                break
            decoded = next_decoded
        else:
            raise ConfigurationError("API path contains excessive percent encoding")
        if decoded.startswith("//") or "\\" in decoded or any(part in {".", ".."} for part in decoded.split("/")):
            raise ConfigurationError("API path must not escape the configured API base")
        return path.lstrip("/")

    def _send(
        self,
        method: str,
        path: str,
        *,
        query: Query | None = None,
        json_body: JSONInput | _Unset | None = UNSET,
        files: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        expected_status: Collection[int] | None = None,
        check_compatibility: bool = True,
        stream: bool = False,
    ) -> httpx.Response:
        self._ensure_if_enabled(check_compatibility)
        kwargs: dict[str, Any] = {
            "params": encode_query(query),
            "headers": headers,
        }
        if not isinstance(json_body, _Unset):
            kwargs["json"] = json_body
        if files is not None:
            kwargs["files"] = files

        request = self._http.build_request(method, self._relative_path(path), **kwargs)
        try:
            response = self._http.send(request, stream=stream)
        except httpx.HTTPError as error:
            raise TransportError(method.upper(), str(request.url), error) from error

        allowed = set(expected_status) if expected_status is not None else set(range(200, 300))
        if response.status_code not in allowed:
            try:
                response.read()
            except httpx.HTTPError as error:
                response.close()
                raise TransportError(method.upper(), str(request.url), error) from error
            api_error = _error_from_response(response)
            response.close()
            raise api_error
        return response

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Query | None = None,
        json_body: JSONInput | _Unset | None = UNSET,
        files: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        expected_status: Collection[int] | None = None,
        check_compatibility: bool = True,
    ) -> httpx.Response:
        """Perform a generic buffered HTTP request within the configured API base."""

        return self._send(
            method,
            path,
            query=query,
            json_body=json_body,
            files=files,
            headers=headers,
            expected_status=expected_status,
            check_compatibility=check_compatibility,
        )

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Query | None = None,
        json_body: JSONInput | _Unset | None = UNSET,
        files: Mapping[str, Any] | None = None,
        expected_status: Collection[int] | None = None,
        check_compatibility: bool = True,
    ) -> JSONValue:
        """Perform a request and decode its JSON body; 204 responses become ``None``."""

        response = self.request(
            method,
            path,
            query=query,
            json_body=json_body,
            files=files,
            expected_status=expected_status,
            check_compatibility=check_compatibility,
        )
        try:
            if response.status_code == 204 or not response.content:
                return None
            try:
                return cast(JSONValue, response.json())
            except ValueError as error:
                raise ResponseDecodeError(method.upper(), str(response.request.url), error) from error
        finally:
            response.close()

    def call(
        self,
        operation_id: str,
        *,
        path_params: Mapping[str, object] | None = None,
        query: Query | None = None,
        json_body: JSONInput | _Unset | None = UNSET,
        files: Mapping[str, Any] | None = None,
        expected_status: Collection[int] | None = None,
    ) -> JSONValue:
        """Invoke a registered JSON operation by its OpenAPI ``operationId``."""

        operation = get_operation(operation_id)
        if operation.download:
            raise ConfigurationError(f"{operation_id} is binary; use Client.download() so it is streamed")
        return self.request_json(
            operation.method,
            operation.render_path(path_params),
            query=query,
            json_body=json_body,
            files=files,
            expected_status=expected_status or operation.success_statuses,
            check_compatibility=operation_id not in {"getProductInfo", "getOpenApiDocument"},
        )

    def upload(
        self,
        operation_id: str,
        file: Pathish,
        *,
        path_params: Mapping[str, object] | None = None,
        query: Query | None = None,
        content_type: str | None = None,
        field_name: str = "file",
    ) -> JSONValue:
        """Stream a file as multipart/form-data without loading it into memory."""

        operation = get_operation(operation_id)
        if not operation.upload:
            raise ConfigurationError(f"{operation_id} is not a multipart upload operation")
        source = Path(file)
        mime = content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        try:
            handle = source.open("rb")
        except OSError as error:
            raise FileTransferError(str(source), "open for upload", error) from error

        with handle:
            return self.request_json(
                operation.method,
                operation.render_path(path_params),
                query=query,
                files={field_name: (source.name, handle, mime)},
                expected_status=operation.success_statuses,
            )

    def download(
        self,
        operation_id: str,
        destination: Pathish,
        *,
        path_params: Mapping[str, object] | None = None,
        query: Query | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Stream into a same-directory temp file and atomically publish the completed download."""

        operation = get_operation(operation_id)
        if not operation.download:
            raise ConfigurationError(f"{operation_id} is not a binary download operation")
        target = Path(destination)
        if target.exists() and not overwrite:
            raise FileTransferError(str(target), "replace existing download", FileExistsError(str(target)))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".part",
                dir=target.parent,
            )
            os.close(descriptor)
        except OSError as error:
            raise FileTransferError(str(target), "create download file", error) from error

        temporary = Path(temporary_name)
        response: httpx.Response | None = None
        try:
            response = self._send(
                operation.method,
                operation.render_path(path_params),
                query=query,
                expected_status=operation.success_statuses,
                stream=True,
            )
            with temporary.open("wb") as sink:
                for chunk in response.iter_bytes():
                    sink.write(chunk)
                sink.flush()
                os.fsync(sink.fileno())
            if overwrite:
                os.replace(temporary, target)
            else:
                # A hard link is an atomic no-clobber publish on both NTFS and POSIX filesystems.
                # The temp file lives beside the destination, so it cannot cross devices.
                os.link(temporary, target)
                temporary.unlink()
        except FileTransferError:
            raise
        except httpx.HTTPError as error:
            failed_url = str(response.request.url) if response else operation.path
            raise TransportError(operation.method, failed_url, error) from error
        except OSError as error:
            raise FileTransferError(str(target), "finalize download", error) from error
        finally:
            if response is not None:
                response.close()
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return target


AnnotateItClient = Client
