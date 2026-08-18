from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .errors import ConfigurationError

DEFAULT_PORT = 8420
DEFAULT_BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}/api/v1"
ANNOTATEIT_URL_ENV = "ANNOTATEIT_URL"
ANNOTATEIT_TOKEN_ENV = "ANNOTATEIT_TOKEN"
# Short aliases remain convenient for callers constructing an explicit environment mapping.
URL_ENV = ANNOTATEIT_URL_ENV
TOKEN_ENV = ANNOTATEIT_TOKEN_ENV
_VERSIONED_API_PATH = re.compile(r"/api/v\d+$", re.IGNORECASE)


def normalize_base_url(raw: str) -> str:
    """Normalize a port, host, or HTTP URL to an AnnotateIt API v1 base URL."""

    value = raw.strip().rstrip("/")
    if not value:
        raise ConfigurationError("AnnotateIt URL cannot be empty")

    if value.isdigit():
        port = int(value)
        if not 1 <= port <= 65_535:
            raise ConfigurationError("AnnotateIt URL port must be between 1 and 65535")
        return f"http://127.0.0.1:{port}/api/v1"

    if re.match(r"^[a-z][a-z\d+.-]*://", value, re.IGNORECASE) and not re.match(r"^https?://", value, re.IGNORECASE):
        raise ConfigurationError("AnnotateIt URL must use http or https")

    candidate = value if re.match(r"^https?://", value, re.IGNORECASE) else f"http://{value}"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError(f"invalid AnnotateIt HTTP URL: {raw!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError("AnnotateIt URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ConfigurationError("AnnotateIt URL must not contain a query or fragment")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ConfigurationError(f"invalid AnnotateIt HTTP URL: {raw!r}") from error

    path = parsed.path.rstrip("/")
    if _VERSIONED_API_PATH.search(path) and not path.endswith("/api/v1"):
        raise ConfigurationError("this SDK supports /api/v1 only")
    if not path.endswith("/api/v1"):
        path = f"{path}/api/v1"

    normalized = SplitResult(parsed.scheme.lower(), parsed.netloc, path, "", "")
    return urlunsplit(normalized)


@dataclass(frozen=True, slots=True)
class ClientConfig:
    base_url: str
    token: str | None
    check_compatibility: bool = True

    @classmethod
    def resolve(
        cls,
        base_url: str | None = None,
        token: str | None = None,
        *,
        check_compatibility: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> ClientConfig:
        source = os.environ if env is None else env
        resolved_url = normalize_base_url(base_url if base_url is not None else source.get(URL_ENV, str(DEFAULT_PORT)))
        raw_token = token if token is not None else source.get(TOKEN_ENV)
        resolved_token = raw_token.strip() if raw_token is not None else None
        return cls(
            base_url=resolved_url,
            token=resolved_token or None,
            check_compatibility=check_compatibility,
        )
