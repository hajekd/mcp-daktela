import httpx
import pytest
import respx

from mcp_daktela.client import DaktelaClient

BASE = "https://test.daktela.com"
TOKEN = "test-token"


@pytest.fixture
def mock_api():
    with respx.mock(base_url=BASE) as rsps:
        yield rsps


@pytest.fixture
async def client(mock_api):
    async with DaktelaClient(BASE, token=TOKEN) as c:
        yield c


class TestList:
    async def test_list_returns_records_and_total(self, client, mock_api):
        mock_api.get("/api/v6/tickets.json").respond(json={
            "result": {
                "data": {
                    "TK001": {"name": "TK001", "title": "First"},
                    "TK002": {"name": "TK002", "title": "Second"},
                },
                "total": 42,
            }
        })

        result = await client.list("tickets")
        assert len(result["data"]) == 2
        assert result["total"] == 42

    async def test_list_sends_auth_header(self, client, mock_api):
        route = mock_api.get("/api/v6/tickets.json").respond(json={
            "result": {"data": {}, "total": 0}
        })

        await client.list("tickets")
        assert route.called
        request = route.calls[0].request
        assert request.headers["X-AUTH-TOKEN"] == TOKEN

    async def test_list_sends_query_params(self, client, mock_api):
        route = mock_api.get("/api/v6/tickets.json").respond(json={
            "result": {"data": {}, "total": 0}
        })

        await client.list("tickets", skip=10, take=5)
        request = route.calls[0].request
        assert "skip=10" in str(request.url)
        assert "take=5" in str(request.url)

    async def test_list_with_filters(self, client, mock_api):
        route = mock_api.get("/api/v6/tickets.json").respond(json={
            "result": {"data": {}, "total": 0}
        })

        await client.list(
            "tickets",
            field_filters=[("stage", "eq", "OPEN")],
        )
        url_str = str(route.calls[0].request.url)
        assert "filter" in url_str
        assert "stage" in url_str

    async def test_list_handles_empty_list_response(self, client, mock_api):
        mock_api.get("/api/v6/tickets.json").respond(json={
            "result": {"data": [], "total": 0}
        })

        result = await client.list("tickets")
        assert result["data"] == []
        assert result["total"] == 0

    async def test_list_raises_on_http_error(self, client, mock_api):
        mock_api.get("/api/v6/tickets.json").respond(status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            await client.list("tickets")


class TestGet:
    async def test_get_returns_record(self, client, mock_api):
        mock_api.get("/api/v6/tickets/TK001.json").respond(json={
            "result": {"name": "TK001", "title": "Test ticket"},
        })

        result = await client.get("tickets", "TK001")
        assert result["name"] == "TK001"
        assert result["title"] == "Test ticket"

    async def test_get_returns_none_on_404(self, client, mock_api):
        mock_api.get("/api/v6/tickets/NONEXISTENT.json").respond(status_code=404)

        result = await client.get("tickets", "NONEXISTENT")
        assert result is None

    async def test_get_raises_on_other_errors(self, client, mock_api):
        mock_api.get("/api/v6/tickets/TK001.json").respond(status_code=500)

        with pytest.raises(httpx.HTTPStatusError):
            await client.get("tickets", "TK001")
