"""Async HTTP client for the Daktela REST API v6."""

import time

import httpx

from mcp_daktela import cache
from mcp_daktela.filters import build_filters


class DaktelaClient:
    """Read-only async client for Daktela API v6.

    Supports two auth modes:
    - Static token: pass token directly
    - Username/password: logs in to get JWT, auto-refreshes before expiry

    Usage:
        async with DaktelaClient("https://instance.daktela.com", token="...") as client:
            tickets = await client.list("tickets")

        async with DaktelaClient("https://instance.daktela.com",
                                  username="user", password="pass") as client:
            tickets = await client.list("tickets")
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token = token
        self._refresh_token: str | None = None
        self._token_expires_at: float = 0  # epoch timestamp
        self._external_client = http_client is not None
        self._http = http_client or httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        if self._username and self._password and not self._token:
            await self._login()
        return self

    async def __aexit__(self, *exc):
        if not self._external_client:
            await self._http.aclose()

    def _url(self, endpoint: str) -> str:
        return f"{self._base_url}/api/v6/{endpoint}.json"

    async def _login(self):
        """Authenticate with username/password to get JWT tokens."""
        resp = await self._http.post(
            self._url("login"),
            json={"username": self._username, "password": self._password},
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})
        self._token = result["accessToken"]
        self._refresh_token = result.get("refreshToken")
        # Refresh 60 seconds before actual expiry
        expires_in = 3600  # default 1h
        self._token_expires_at = time.monotonic() + expires_in - 60

    async def _refresh(self):
        """Refresh the JWT using the refresh token."""
        resp = await self._http.put(
            self._url("login"),
            json={"refreshToken": self._refresh_token},
        )
        if resp.status_code != 200:
            # Refresh failed, fall back to full login
            await self._login()
            return
        result = resp.json().get("result", {})
        self._token = result["accessToken"]
        self._refresh_token = result.get("refreshToken", self._refresh_token)
        self._token_expires_at = time.monotonic() + 3600 - 60

    async def _ensure_token(self):
        """Ensure we have a valid token, refreshing if needed."""
        if self._username and self._token_expires_at and time.monotonic() >= self._token_expires_at:
            if self._refresh_token:
                await self._refresh()
            else:
                await self._login()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an authenticated request with automatic token refresh."""
        await self._ensure_token()
        kwargs.setdefault("headers", {})["X-AUTH-TOKEN"] = self._token
        return await self._http.request(method, url, **kwargs)

    def _cache_identity(self) -> tuple:
        """Derive a cache identity scoped to this user and Daktela instance."""
        return (self._base_url, self._username or self._token)

    async def list(
        self,
        endpoint: str,
        *,
        field_filters: list[tuple[str, str, str | list[str]]] | None = None,
        skip: int = 0,
        take: int = 50,
        sort: str | None = None,
        sort_dir: str = "desc",
        fields: list[str] | None = None,
    ) -> dict:
        """Fetch a paginated list from a Daktela endpoint.

        Returns:
            dict with keys: "data" (list of records), "total" (int total count)
        """
        cacheable = field_filters is None and fields is None
        if cacheable:
            cached = cache.get(
                self._cache_identity(), endpoint, skip, take, sort, sort_dir,
            )
            if cached is not None:
                return cached

        params = build_filters(
            field_filters=field_filters,
            skip=skip,
            take=take,
            sort=sort,
            sort_dir=sort_dir,
            fields=fields,
        )
        resp = await self._request("GET", self._url(endpoint), params=params)
        resp.raise_for_status()
        body = resp.json()

        raw_data = body.get("result", {}).get("data", {})
        # Daktela returns data as a dict keyed by record name; normalize to list
        if isinstance(raw_data, dict):
            records = list(raw_data.values())
        elif isinstance(raw_data, list):
            records = raw_data
        else:
            records = []

        total = body.get("result", {}).get("total", len(records))
        result = {"data": records, "total": total}

        if cacheable:
            cache.put(
                self._cache_identity(), endpoint, skip, take, sort, sort_dir, result,
            )

        return result

    async def get(self, endpoint: str, name: str) -> dict | None:
        """Fetch a single record by name/ID.

        Returns:
            The record dict, or None if not found.
        """
        resp = await self._request("GET", self._url(f"{endpoint}/{name}"))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.json()
        # Single-record endpoints return the record directly under "result"
        # (unlike list endpoints which use "result.data")
        return body.get("result")
