from __future__ import annotations

from ..types import JSONValue
from .base import BaseResource


class SystemResource(BaseResource):
    def status(self) -> JSONValue:
        return self._client.call("getStatus")

    def product_info(self) -> JSONValue:
        return self._client.call("getProductInfo")

    def openapi_document(self) -> JSONValue:
        return self._client.call("getOpenApiDocument")
