"""Tests for DaktelaAuthMiddleware and ContextVar lifecycle."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from mcp_daktela.auth import (
    DaktelaAuthMiddleware,
    _request_config,
    _validate_url,
)

HEADERS_PATH = "mcp_daktela.auth.get_http_headers"


def _make_context():
    """Create a minimal mock MiddlewareContext."""
    return AsyncMock()


def _make_call_next(result="tool result"):
    """Create a mock call_next that returns a fixed result."""
    return AsyncMock(return_value=result)


class TestContextVarLifecycle:
    async def test_set_and_reset(self):
        """ContextVar is set during tool execution and cleaned up after."""
        middleware = DaktelaAuthMiddleware()
        captured = {}

        async def capturing_call_next(context):
            captured["config"] = _request_config.get()
            return "ok"

        headers = {
            "x-daktela-url": "https://test.daktela.com",
            "x-daktela-access-token": "tok123",
        }
        with patch(HEADERS_PATH, return_value=headers):
            await middleware.on_call_tool(_make_context(), capturing_call_next)

        assert captured["config"] == {"url": "https://test.daktela.com", "token": "tok123"}
        assert _request_config.get() is None  # cleaned up

    async def test_cleanup_on_tool_error(self):
        """ContextVar is cleaned up even when the tool raises."""
        middleware = DaktelaAuthMiddleware()

        async def failing_call_next(context):
            raise RuntimeError("tool boom")

        headers = {
            "x-daktela-url": "https://test.daktela.com",
            "x-daktela-access-token": "tok123",
        }
        with patch(HEADERS_PATH, return_value=headers):
            with pytest.raises(RuntimeError, match="tool boom"):
                await middleware.on_call_tool(_make_context(), failing_call_next)

        assert _request_config.get() is None  # still cleaned up


class TestUsernamePasswordAuth:
    async def test_username_password_headers(self):
        """Middleware extracts username/password from headers."""
        middleware = DaktelaAuthMiddleware()
        captured = {}

        async def capturing_call_next(context):
            captured["config"] = _request_config.get()
            return "ok"

        headers = {
            "x-daktela-url": "https://test.daktela.com",
            "x-daktela-username": "admin",
            "x-daktela-password": "secret",
        }
        with patch(HEADERS_PATH, return_value=headers):
            await middleware.on_call_tool(_make_context(), capturing_call_next)

        assert captured["config"] == {
            "url": "https://test.daktela.com",
            "username": "admin",
            "password": "secret",
        }


class TestAccessTokenAuth:
    async def test_access_token_header(self):
        """Middleware extracts access token from headers."""
        middleware = DaktelaAuthMiddleware()
        captured = {}

        async def capturing_call_next(context):
            captured["config"] = _request_config.get()
            return "ok"

        headers = {
            "x-daktela-url": "https://test.daktela.com/",
            "x-daktela-access-token": "mytoken",
        }
        with patch(HEADERS_PATH, return_value=headers):
            await middleware.on_call_tool(_make_context(), capturing_call_next)

        assert captured["config"] == {
            "url": "https://test.daktela.com",
            "token": "mytoken",
        }


class TestUrlTrailingSlash:
    async def test_trailing_slash_stripped(self):
        """URL trailing slash is normalized away."""
        middleware = DaktelaAuthMiddleware()
        captured = {}

        async def capturing_call_next(context):
            captured["config"] = _request_config.get()
            return "ok"

        headers = {
            "x-daktela-url": "https://test.daktela.com///",
            "x-daktela-access-token": "tok",
        }
        with patch(HEADERS_PATH, return_value=headers):
            await middleware.on_call_tool(_make_context(), capturing_call_next)

        assert captured["config"]["url"] == "https://test.daktela.com"


class TestValidationErrors:
    async def test_missing_url_raises(self):
        """Missing X-Daktela-Url raises ValueError."""
        middleware = DaktelaAuthMiddleware()
        headers = {"x-daktela-access-token": "tok123"}
        with patch(HEADERS_PATH, return_value=headers):
            with pytest.raises(ValueError, match="X-Daktela-Url header is required"):
                await middleware.on_call_tool(_make_context(), _make_call_next())

    async def test_missing_credentials_raises(self):
        """URL present but no credentials raises ValueError."""
        middleware = DaktelaAuthMiddleware()
        headers = {"x-daktela-url": "https://test.daktela.com"}
        with patch(HEADERS_PATH, return_value=headers):
            with pytest.raises(ValueError, match="X-Daktela-Username.*X-Daktela-Access-Token"):
                await middleware.on_call_tool(_make_context(), _make_call_next())


class TestStdioPassthrough:
    async def test_no_headers_passes_through(self):
        """No Daktela headers → middleware is a no-op (stdio mode)."""
        middleware = DaktelaAuthMiddleware()
        call_next = _make_call_next("passthrough result")

        with patch(HEADERS_PATH, return_value={}):
            result = await middleware.on_call_tool(_make_context(), call_next)

        assert result == "passthrough result"
        assert _request_config.get() is None  # never set


class TestUrlValidation:
    """SSRF protection: validate X-Daktela-Url against allowed domains and schemes."""

    def test_valid_daktela_url(self):
        assert _validate_url("https://test.daktela.com") == "https://test.daktela.com"

    def test_valid_subdomain(self):
        assert _validate_url("https://customer.daktela.com/") == "https://customer.daktela.com"

    def test_rejects_http(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            _validate_url("http://test.daktela.com")

    def test_rejects_no_scheme(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            _validate_url("test.daktela.com")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            _validate_url("file:///etc/passwd")

    def test_rejects_non_daktela_domain(self):
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("https://evil.com")

    def test_rejects_metadata_ip(self):
        """Block GCP metadata endpoint (SSRF vector)."""
        with pytest.raises(ValueError, match="not an IP address"):
            _validate_url("https://169.254.169.254")

    def test_rejects_localhost_ip(self):
        with pytest.raises(ValueError, match="not an IP address"):
            _validate_url("https://127.0.0.1")

    def test_rejects_private_ip(self):
        with pytest.raises(ValueError, match="not an IP address"):
            _validate_url("https://10.0.0.1")

    def test_rejects_ipv6(self):
        with pytest.raises(ValueError, match="not an IP address"):
            _validate_url("https://[::1]")

    def test_rejects_empty_hostname(self):
        with pytest.raises(ValueError, match="no hostname"):
            _validate_url("https://")

    def test_rejects_daktela_com_prefix_attack(self):
        """Ensure 'notdaktela.com' does not match '.daktela.com'."""
        with pytest.raises(ValueError, match="not allowed"):
            _validate_url("https://notdaktela.com")

    def test_bare_daktela_com_allowed(self):
        """The bare domain 'daktela.com' itself should be allowed."""
        assert _validate_url("https://daktela.com") == "https://daktela.com"

    def test_custom_allowed_domains(self):
        """ALLOWED_DAKTELA_DOMAINS env var overrides the default."""
        with patch.dict(os.environ, {"ALLOWED_DAKTELA_DOMAINS": "custom.io, other.net"}):
            assert _validate_url("https://app.custom.io") == "https://app.custom.io"
            assert _validate_url("https://other.net") == "https://other.net"
            with pytest.raises(ValueError, match="not allowed"):
                _validate_url("https://test.daktela.com")
