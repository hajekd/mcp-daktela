"""Tests for OAuth 2.0 endpoints and JWT token flow."""

import hashlib
import json
import os
import time
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from starlette.testclient import TestClient

from mcp_daktela.oauth import (
    _AUTH_CODE_LIFETIME,
    _REFRESH_TOKEN_LIFETIME,
    _decode_jwt,
    _get_jwt_secret,
    _parse_daktela_datetime,
    _sign_jwt,
    handle_authorization_server_metadata,
    handle_authorize,
    handle_protected_resource_metadata,
    handle_register,
    handle_token,
)

JWT_SECRET = "test-secret-key-for-oauth-tests!"  # 33 bytes, meets HS256 minimum


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)


def _make_pkce_pair():
    """Generate a PKCE code_verifier + code_challenge pair."""
    verifier = "test_verifier_with_enough_entropy_1234567890"
    challenge = (
        urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


class TestJwtHelpers:
    def test_get_jwt_secret(self):
        assert _get_jwt_secret() == JWT_SECRET

    def test_get_jwt_secret_missing(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET")
        with pytest.raises(ValueError, match="JWT_SECRET"):
            _get_jwt_secret()

    def test_sign_and_decode(self):
        payload = {"type": "access_token", "foo": "bar", "exp": int(time.time()) + 3600}
        token = _sign_jwt(payload)
        decoded = _decode_jwt(token, expected_type="access_token")
        assert decoded["foo"] == "bar"

    def test_decode_wrong_type(self):
        payload = {"type": "refresh_token", "exp": int(time.time()) + 3600}
        token = _sign_jwt(payload)
        with pytest.raises(jwt.InvalidTokenError, match="Expected token type"):
            _decode_jwt(token, expected_type="access_token")

    def test_decode_expired(self):
        payload = {"type": "access_token", "exp": int(time.time()) - 10}
        token = _sign_jwt(payload)
        with pytest.raises(jwt.ExpiredSignatureError):
            _decode_jwt(token, expected_type="access_token")

    def test_parse_daktela_datetime(self):
        ts = _parse_daktela_datetime("2026-02-14 23:34:17")
        assert ts > 0
        # Europe/Prague is CET (UTC+1) in February → 3600s less than UTC
        assert ts == 1771108457


# ---------------------------------------------------------------------------
# OAuth metadata endpoints
# ---------------------------------------------------------------------------


class TestMetadataEndpoints:
    async def test_protected_resource_metadata(self):
        request = _mock_request("https", "mcp.example.com")
        resp = await handle_protected_resource_metadata(request)
        body = json.loads(resp.body)
        assert body["resource"] == "https://mcp.example.com/"
        assert body["authorization_servers"] == ["https://mcp.example.com"]

    async def test_authorization_server_metadata(self):
        request = _mock_request("https", "mcp.example.com")
        resp = await handle_authorization_server_metadata(request)
        body = json.loads(resp.body)
        assert body["issuer"] == "https://mcp.example.com"
        assert body["authorization_endpoint"] == "https://mcp.example.com/oauth/authorize"
        assert body["token_endpoint"] == "https://mcp.example.com/oauth/token"
        assert body["registration_endpoint"] == "https://mcp.example.com/oauth/register"
        assert "S256" in body["code_challenge_methods_supported"]
        assert "authorization_code" in body["grant_types_supported"]
        assert "refresh_token" in body["grant_types_supported"]


# ---------------------------------------------------------------------------
# Dynamic client registration
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_register_success(self):
        request = _mock_request("https", "mcp.example.com")
        request.json = AsyncMock(return_value={
            "redirect_uris": ["http://localhost:12345/callback"],
            "client_name": "Claude Desktop",
        })
        resp = await handle_register(request)
        assert resp.status_code == 201
        body = json.loads(resp.body)
        assert "client_id" in body
        assert body["redirect_uris"] == ["http://localhost:12345/callback"]
        assert body["grant_types"] == ["authorization_code", "refresh_token"]

    async def test_register_missing_redirect_uris(self):
        request = _mock_request("https", "mcp.example.com")
        request.json = AsyncMock(return_value={})
        resp = await handle_register(request)
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert body["error"] == "invalid_client_metadata"

    async def test_register_invalid_json(self):
        request = _mock_request("https", "mcp.example.com")
        request.json = AsyncMock(side_effect=json.JSONDecodeError("", "", 0))
        resp = await handle_register(request)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Token endpoint — auth code exchange
# ---------------------------------------------------------------------------


def _make_auth_code(challenge, **overrides):
    """Create a valid auth code JWT for testing."""
    payload = {
        "type": "auth_code",
        "daktela_url": "https://test.daktela.com",
        "daktela_access_token": "dak_access_123",
        "daktela_access_exp": int(time.time()) + 3600,
        "daktela_username": "testuser",
        "daktela_password": "testpass",
        "code_challenge": challenge,
        "client_id": "test_client",
        "redirect_uri": "http://localhost:12345/callback",
        "exp": int(time.time()) + 300,
    }
    payload.update(overrides)
    return _sign_jwt(payload)


class TestAuthCodeExchange:
    async def test_exchange_success(self):
        verifier, challenge = _make_pkce_pair()
        auth_code = _make_auth_code(challenge)

        request = _mock_form_request({
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": verifier,
            "redirect_uri": "http://localhost:12345/callback",
        })
        resp = await handle_token(request)
        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] > 0

        # Verify the access token contains the right data
        decoded = jwt.decode(body["access_token"], JWT_SECRET, algorithms=["HS256"])
        assert decoded["type"] == "access_token"
        assert decoded["daktela_url"] == "https://test.daktela.com"
        assert decoded["daktela_access_token"] == "dak_access_123"

        # Verify the refresh token contains credentials (not Daktela tokens)
        decoded_r = jwt.decode(body["refresh_token"], JWT_SECRET, algorithms=["HS256"])
        assert decoded_r["type"] == "refresh_token"
        assert decoded_r["daktela_username"] == "testuser"
        assert decoded_r["daktela_password"] == "testpass"
        assert decoded_r["daktela_url"] == "https://test.daktela.com"
        # Refresh token should have ~30 day expiry
        assert decoded_r["exp"] > int(time.time()) + _REFRESH_TOKEN_LIFETIME - 60

    async def test_exchange_bad_pkce(self):
        _, challenge = _make_pkce_pair()
        auth_code = _make_auth_code(challenge)

        request = _mock_form_request({
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": "wrong_verifier",
            "redirect_uri": "http://localhost:12345/callback",
        })
        resp = await handle_token(request)
        assert resp.status_code == 400
        body = json.loads(resp.body)
        assert body["error"] == "invalid_grant"
        assert "PKCE" in body["error_description"]

    async def test_exchange_expired_code(self):
        verifier, challenge = _make_pkce_pair()
        auth_code = _make_auth_code(challenge, exp=int(time.time()) - 10)

        request = _mock_form_request({
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": verifier,
            "redirect_uri": "http://localhost:12345/callback",
        })
        resp = await handle_token(request)
        assert resp.status_code == 400
        assert json.loads(resp.body)["error"] == "invalid_grant"

    async def test_exchange_redirect_uri_mismatch(self):
        verifier, challenge = _make_pkce_pair()
        auth_code = _make_auth_code(challenge)

        request = _mock_form_request({
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": verifier,
            "redirect_uri": "http://DIFFERENT/cb",
        })
        resp = await handle_token(request)
        assert resp.status_code == 400
        assert "redirect_uri" in json.loads(resp.body)["error_description"]

    async def test_exchange_missing_code(self):
        request = _mock_form_request({
            "grant_type": "authorization_code",
            "code_verifier": "something",
        })
        resp = await handle_token(request)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Token endpoint — refresh
# ---------------------------------------------------------------------------


class TestRefreshToken:
    async def test_refresh_success(self):
        refresh_jwt = _sign_jwt({
            "type": "refresh_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_username": "testuser",
            "daktela_password": "testpass",
            "exp": int(time.time()) + _REFRESH_TOKEN_LIFETIME,
        })

        daktela_response = {
            "result": {
                "accessToken": "new_dak_access",
                "accessTokenExpirationDate": "2099-12-31 23:59:59",
            }
        }

        request = _mock_form_request({
            "grant_type": "refresh_token",
            "refresh_token": refresh_jwt,
        })

        with patch("mcp_daktela.oauth._daktela_login") as mock_login:
            mock_login.return_value = daktela_response["result"]
            resp = await handle_token(request)

        assert resp.status_code == 200
        body = json.loads(resp.body)
        assert "access_token" in body
        assert "refresh_token" in body

        decoded = jwt.decode(body["access_token"], JWT_SECRET, algorithms=["HS256"])
        assert decoded["daktela_access_token"] == "new_dak_access"

        # Verify refresh token is reissued with same credentials
        decoded_r = jwt.decode(body["refresh_token"], JWT_SECRET, algorithms=["HS256"])
        assert decoded_r["daktela_username"] == "testuser"
        assert decoded_r["daktela_password"] == "testpass"

        # Verify _daktela_login was called with correct args
        mock_login.assert_called_once_with("https://test.daktela.com", "testuser", "testpass")

    async def test_refresh_expired_jwt(self):
        refresh_jwt = _sign_jwt({
            "type": "refresh_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_username": "u",
            "daktela_password": "p",
            "exp": int(time.time()) - 10,
        })

        request = _mock_form_request({
            "grant_type": "refresh_token",
            "refresh_token": refresh_jwt,
        })
        resp = await handle_token(request)
        assert resp.status_code == 400
        assert json.loads(resp.body)["error"] == "invalid_grant"

    async def test_refresh_daktela_rejects(self):
        refresh_jwt = _sign_jwt({
            "type": "refresh_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_username": "baduser",
            "daktela_password": "badpass",
            "exp": int(time.time()) + 86400,
        })

        request = _mock_form_request({
            "grant_type": "refresh_token",
            "refresh_token": refresh_jwt,
        })

        with patch("mcp_daktela.oauth._daktela_login") as mock_login:
            mock_login.return_value = "Invalid username or password"
            resp = await handle_token(request)

        assert resp.status_code == 400
        assert "Invalid" in json.loads(resp.body)["error_description"]

    async def test_unsupported_grant_type(self):
        request = _mock_form_request({"grant_type": "client_credentials"})
        resp = await handle_token(request)
        assert resp.status_code == 400
        assert json.loads(resp.body)["error"] == "unsupported_grant_type"


# ---------------------------------------------------------------------------
# Bearer token in auth middleware
# ---------------------------------------------------------------------------


class TestOAuthGateMiddleware:
    """Test that OAuthGateMiddleware validates Bearer JWTs at the HTTP level."""

    def _make_scope(self, headers: dict[str, str]) -> dict:
        raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return {
            "type": "http",
            "path": "/mcp",
            "headers": raw,
        }

    async def test_expired_bearer_returns_401(self):
        from mcp_daktela.oauth import OAuthGateMiddleware

        expired_jwt = _sign_jwt({
            "type": "access_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_access_token": "old",
            "exp": int(time.time()) - 10,
        })

        app = AsyncMock()
        mw = OAuthGateMiddleware(app)
        scope = self._make_scope({
            "Authorization": f"Bearer {expired_jwt}",
            "Host": "mcp.example.com",
        })

        sent = []

        async def capture_send(message):
            sent.append(message)

        await mw(scope, AsyncMock(), capture_send)

        # Should NOT have called the inner app
        app.assert_not_called()
        # Should have sent a 401 response
        start = [m for m in sent if m.get("type") == "http.response.start"]
        assert start[0]["status"] == 401
        resp_headers = dict(start[0]["headers"])
        assert b"www-authenticate" in resp_headers

    async def test_valid_bearer_passes_through(self):
        from mcp_daktela.oauth import OAuthGateMiddleware

        valid_jwt = _sign_jwt({
            "type": "access_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_access_token": "tok",
            "exp": int(time.time()) + 3600,
        })

        app = AsyncMock()
        mw = OAuthGateMiddleware(app)
        scope = self._make_scope({"Authorization": f"Bearer {valid_jwt}"})

        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    async def test_daktela_headers_pass_through_without_jwt_check(self):
        from mcp_daktela.oauth import OAuthGateMiddleware

        app = AsyncMock()
        mw = OAuthGateMiddleware(app)
        scope = self._make_scope({
            "X-Daktela-Url": "https://test.daktela.com",
            "X-Daktela-Access-Token": "tok",
        })

        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    async def test_no_auth_returns_401(self):
        from mcp_daktela.oauth import OAuthGateMiddleware

        app = AsyncMock()
        mw = OAuthGateMiddleware(app)
        scope = self._make_scope({"Host": "mcp.example.com"})

        sent = []

        async def capture_send(message):
            sent.append(message)

        await mw(scope, AsyncMock(), capture_send)

        app.assert_not_called()
        start = [m for m in sent if m.get("type") == "http.response.start"]
        assert start[0]["status"] == 401


class TestExpiresInBuffer:
    """Verify that expires_in is reported conservatively (10 min early)."""

    async def test_expires_in_has_buffer(self):
        verifier, challenge = _make_pkce_pair()
        access_exp = int(time.time()) + 7200  # 2 hours from now
        auth_code = _make_auth_code(challenge, daktela_access_exp=access_exp)

        request = _mock_form_request({
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": verifier,
            "redirect_uri": "http://localhost:12345/callback",
        })
        resp = await handle_token(request)
        body = json.loads(resp.body)

        # expires_in should be ~2h minus 10min buffer (6600), not the full 7200
        assert body["expires_in"] <= 7200 - 600 + 5  # +5s tolerance for test runtime
        assert body["expires_in"] >= 7200 - 600 - 5


class TestBearerTokenMiddleware:
    async def test_bearer_token_sets_contextvar(self):
        from mcp_daktela.auth import DaktelaAuthMiddleware, _request_config

        access_jwt = _sign_jwt({
            "type": "access_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_access_token": "dak_tok_123",
            "exp": int(time.time()) + 3600,
        })

        captured = {}

        async def capturing_call_next(context):
            captured["config"] = _request_config.get()
            return "ok"

        middleware = DaktelaAuthMiddleware()
        headers = {"authorization": f"Bearer {access_jwt}"}

        with patch("mcp_daktela.auth.get_http_headers", return_value=headers):
            await middleware.on_call_tool(AsyncMock(), capturing_call_next)

        assert captured["config"] == {
            "url": "https://test.daktela.com",
            "token": "dak_tok_123",
        }
        assert _request_config.get() is None  # cleaned up

    async def test_bearer_token_expired_raises(self):
        from mcp_daktela.auth import DaktelaAuthMiddleware

        expired_jwt = _sign_jwt({
            "type": "access_token",
            "daktela_url": "https://test.daktela.com",
            "daktela_access_token": "old",
            "exp": int(time.time()) - 10,
        })

        middleware = DaktelaAuthMiddleware()
        headers = {"authorization": f"Bearer {expired_jwt}"}

        with patch("mcp_daktela.auth.get_http_headers", return_value=headers):
            # Expired JWT should raise, which propagates as an error to the client
            with pytest.raises(jwt.ExpiredSignatureError):
                await middleware.on_call_tool(AsyncMock(), AsyncMock())

    async def test_bearer_takes_priority_over_x_headers(self):
        """If both Bearer and X-Daktela-* headers present, Bearer wins."""
        from mcp_daktela.auth import DaktelaAuthMiddleware, _request_config

        access_jwt = _sign_jwt({
            "type": "access_token",
            "daktela_url": "https://bearer.daktela.com",
            "daktela_access_token": "bearer_tok",
            "exp": int(time.time()) + 3600,
        })

        captured = {}

        async def capturing_call_next(context):
            captured["config"] = _request_config.get()
            return "ok"

        middleware = DaktelaAuthMiddleware()
        headers = {
            "authorization": f"Bearer {access_jwt}",
            "x-daktela-url": "https://header.daktela.com",
            "x-daktela-access-token": "header_tok",
        }

        with patch("mcp_daktela.auth.get_http_headers", return_value=headers):
            await middleware.on_call_tool(AsyncMock(), capturing_call_next)

        assert captured["config"]["url"] == "https://bearer.daktela.com"
        assert captured["config"]["token"] == "bearer_tok"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_request(scheme: str, host: str, query_string: str = ""):
    """Create a mock Starlette Request."""
    request = AsyncMock()
    request.url = AsyncMock()
    request.url.scheme = scheme
    request.headers = {"host": host}
    request.method = "GET"

    # Parse query params
    from starlette.datastructures import QueryParams
    request.query_params = QueryParams(query_string)
    return request


def _mock_form_request(form_data: dict):
    """Create a mock request with form data."""
    request = AsyncMock()
    request.form = AsyncMock(return_value=form_data)
    return request
