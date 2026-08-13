from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import Config


@dataclass
class ApiResult:
    status: int
    body: Any
    raw: str = ""


class FarmAIClient:
    def __init__(self, config: Config):
        self.config = config

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        query: dict | None = None,
    ) -> ApiResult:
        url = self.config.base_url + path

        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)

        data = None
        headers = {
            "X-API-Key": self.config.api_key,
            "Accept": "application/json",
        }

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8")
                return ApiResult(
                    status=response.status,
                    body=self._parse(raw),
                    raw=raw,
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return ApiResult(
                status=exc.code,
                body=self._parse(raw),
                raw=raw,
            )
        except urllib.error.URLError as exc:
            return ApiResult(
                status=0,
                body={"transport_error": str(exc)},
                raw=str(exc),
            )

    @staticmethod
    def _parse(raw: str):
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    @staticmethod
    def data(body: Any):
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    def get(self, path: str, query: dict | None = None) -> ApiResult:
        return self._request("GET", path, query=query)

    def post(self, path: str, payload: dict) -> ApiResult:
        return self._request("POST", path, payload=payload)
