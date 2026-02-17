import time
from unittest.mock import patch

import httpx
import pytest
import respx

from mcp_daktela import cache
from mcp_daktela.client import DaktelaClient

BASE = "https://test.daktela.com"
TOKEN = "test-token"
IDENTITY = (BASE, TOKEN)


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def mock_api():
    with respx.mock(base_url=BASE) as rsps:
        yield rsps


@pytest.fixture
async def client(mock_api):
    async with DaktelaClient(BASE, token=TOKEN) as c:
        yield c


def _users_response():
    return {
        "result": {
            "data": {
                "john.doe": {"name": "john.doe", "title": "John Doe"},
                "jane.doe": {"name": "jane.doe", "title": "Jane Doe"},
            },
            "total": 2,
        }
    }


class TestCacheModule:
    def test_get_returns_none_on_empty_cache(self):
        assert cache.get(IDENTITY, "users", 0, 200, None, "desc") is None

    def test_put_and_get_cacheable_endpoint(self):
        data = {"data": [{"name": "a"}], "total": 1}
        cache.put(IDENTITY, "users", 0, 200, None, "desc", data)
        assert cache.get(IDENTITY, "users", 0, 200, None, "desc") is data

    def test_non_cacheable_endpoint_ignored(self):
        data = {"data": [], "total": 0}
        cache.put(IDENTITY, "tickets", 0, 50, None, "desc", data)
        assert cache.get(IDENTITY, "tickets", 0, 50, None, "desc") is None

    def test_different_identity_isolated(self):
        data_a = {"data": [{"name": "a"}], "total": 1}
        data_b = {"data": [{"name": "b"}], "total": 1}
        id_a = ("https://a.daktela.com", "token-a")
        id_b = ("https://b.daktela.com", "token-b")

        cache.put(id_a, "users", 0, 200, None, "desc", data_a)
        cache.put(id_b, "users", 0, 200, None, "desc", data_b)

        assert cache.get(id_a, "users", 0, 200, None, "desc") is data_a
        assert cache.get(id_b, "users", 0, 200, None, "desc") is data_b

    def test_same_url_different_user_isolated(self):
        data_admin = {"data": [{"name": "a"}, {"name": "b"}], "total": 2}
        data_lead = {"data": [{"name": "a"}], "total": 1}
        id_admin = (BASE, "admin")
        id_lead = (BASE, "lead")

        cache.put(id_admin, "users", 0, 200, None, "desc", data_admin)
        cache.put(id_lead, "users", 0, 200, None, "desc", data_lead)

        assert cache.get(id_admin, "users", 0, 200, None, "desc") is data_admin
        assert cache.get(id_lead, "users", 0, 200, None, "desc") is data_lead

    def test_expired_entry_returns_none(self):
        data = {"data": [], "total": 0}
        cache.put(IDENTITY, "users", 0, 200, None, "desc", data)

        # Simulate time passing beyond TTL
        key = (IDENTITY, "users", 0, 200, None, "desc")
        expires_at, stored = cache._store[key]
        cache._store[key] = (time.monotonic() - 1, stored)

        assert cache.get(IDENTITY, "users", 0, 200, None, "desc") is None

    def test_different_pagination_different_entries(self):
        data_page1 = {"data": [{"name": "a"}], "total": 2}
        data_page2 = {"data": [{"name": "b"}], "total": 2}

        cache.put(IDENTITY, "users", 0, 1, None, "desc", data_page1)
        cache.put(IDENTITY, "users", 1, 1, None, "desc", data_page2)

        assert cache.get(IDENTITY, "users", 0, 1, None, "desc") is data_page1
        assert cache.get(IDENTITY, "users", 1, 1, None, "desc") is data_page2

    def test_put_prunes_expired_entries(self):
        cache.put(IDENTITY, "users", 0, 200, None, "desc", {"data": [], "total": 0})

        # Expire the entry
        for key in list(cache._store):
            expires_at, data = cache._store[key]
            cache._store[key] = (time.monotonic() - 1, data)

        # This put should prune the expired entry
        cache.put(IDENTITY, "queues", 0, 200, None, "desc", {"data": [], "total": 0})

        assert len(cache._store) == 1  # only queues, users was pruned

    def test_clear(self):
        cache.put(IDENTITY, "users", 0, 200, None, "desc", {"data": [], "total": 0})
        assert len(cache._store) == 1
        cache.clear()
        assert len(cache._store) == 0

    @patch.dict("os.environ", {"CACHE_TTL_SECONDS": "10"})
    def test_ttl_from_env(self):
        assert cache._ttl() == 10.0

    @patch.dict("os.environ", {"CACHE_ENABLED": "false"})
    def test_disabled_via_env(self):
        data = {"data": [{"name": "a"}], "total": 1}
        cache.put(IDENTITY, "users", 0, 200, None, "desc", data)
        assert cache.get(IDENTITY, "users", 0, 200, None, "desc") is None
        assert len(cache._store) == 0

    def test_enabled_by_default(self):
        assert cache._enabled() is True


class TestClientCacheIntegration:
    async def test_cacheable_endpoint_hits_api_once(self, client, mock_api):
        route = mock_api.get("/api/v6/users.json").respond(json=_users_response())

        r1 = await client.list("users", take=200)
        r2 = await client.list("users", take=200)

        assert route.call_count == 1
        assert r1["total"] == 2
        assert r2["total"] == 2

    async def test_non_cacheable_endpoint_always_hits_api(self, client, mock_api):
        route = mock_api.get("/api/v6/tickets.json").respond(json={
            "result": {"data": {}, "total": 0}
        })

        await client.list("tickets")
        await client.list("tickets")

        assert route.call_count == 2

    async def test_filtered_request_bypasses_cache(self, client, mock_api):
        route = mock_api.get("/api/v6/users.json").respond(json=_users_response())

        # Unfiltered — should be cached
        await client.list("users", take=200)
        # Filtered — should bypass cache and hit API
        await client.list("users", take=200, field_filters=[("title", "like", "John")])

        assert route.call_count == 2

    async def test_fields_request_bypasses_cache(self, client, mock_api):
        route = mock_api.get("/api/v6/users.json").respond(json=_users_response())

        await client.list("users", take=200)
        await client.list("users", take=200, fields=["name"])

        assert route.call_count == 2

    async def test_cache_identity_uses_username_for_password_flow(self):
        with respx.mock(base_url=BASE) as rsps:
            rsps.post("/api/v6/login.json").respond(json={
                "result": {"accessToken": "jwt-1", "refreshToken": "rt-1"}
            })

            async with DaktelaClient(BASE, username="admin", password="pw") as c:
                identity = c._cache_identity()
                assert identity == (BASE, "admin")

    async def test_cache_identity_uses_token_for_token_flow(self, client):
        identity = client._cache_identity()
        assert identity == (BASE, TOKEN)
