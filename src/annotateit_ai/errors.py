from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class AnnotateItError(Exception):
    """Base class for every SDK-owned failure."""


class ConfigurationError(AnnotateItError, ValueError):
    """The client was configured with an invalid URL, token, or operation argument."""


@dataclass(eq=False)
class PaginationError(AnnotateItError):
    """A paginated response could not make safe forward progress."""

    operation_id: str
    message: str

    def __str__(self) -> str:
        return f"{self.operation_id}: {self.message}"


@dataclass(eq=False)
class TransportError(AnnotateItError):
    """The HTTP exchange failed before an API response was available."""

    method: str
    url: str
    cause: Exception

    def __str__(self) -> str:
        return f"{self.method} {self.url} failed: {self.cause}"


@dataclass(eq=False)
class ApiError(AnnotateItError):
    """A non-success response using AnnotateIt's structured error contract."""

    status_code: int
    message: str
    code: str | None = None
    details: dict[str, Any] | None = None
    method: str | None = None
    url: str | None = None

    def __str__(self) -> str:
        prefix = f"{self.status_code}"
        if self.code:
            prefix += f" {self.code}"
        return f"{prefix}: {self.message}"


@dataclass(eq=False)
class CompatibilityError(AnnotateItError):
    """The desktop app does not advertise the API contract supported by this SDK."""

    message: str
    api_version: str | None = None
    supported_major: int = 1

    def __str__(self) -> str:
        return self.message


@dataclass(eq=False)
class ResponseDecodeError(AnnotateItError):
    """A successful endpoint returned a body that was not valid JSON."""

    method: str
    url: str
    cause: Exception

    def __str__(self) -> str:
        return f"{self.method} {self.url} returned invalid JSON: {self.cause}"


@dataclass(eq=False)
class FileTransferError(AnnotateItError):
    """A local file could not be opened, read, or finalized."""

    path: str
    action: str
    cause: Exception

    def __str__(self) -> str:
        return f"cannot {self.action} {self.path!r}: {self.cause}"
