from __future__ import annotations

from typing import Any, Optional

import httpx


class ApiError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail: Any
    try:
        body = response.json()
        detail = body.get("detail", body)
    except Exception:
        detail = response.text
    raise ApiError(response.status_code, detail)


class HttpTransport:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        with httpx.Client(
            transport=self._transport,
            timeout=self._timeout,
            headers=_auth_headers(self._api_key),
        ) as client:
            response = client.request(method, url, json=json, params=params)
        _raise_for_status(response)
        if response.status_code == 204:
            return None
        return response.json()


class AsyncHttpTransport:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = _normalize_base_url(base_url)
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            headers=_auth_headers(self._api_key),
        ) as client:
            response = await client.request(method, url, json=json, params=params)
        _raise_for_status(response)
        if response.status_code == 204:
            return None
        return response.json()
