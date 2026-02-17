"""Tests for config.py — ContextVar priority, env-var fallback, and security guard."""

import os
from unittest.mock import patch

import pytest

from mcp_daktela.auth import _request_config
from mcp_daktela.config import get_config


class TestContextVarPriority:
    async def test_contextvar_takes_priority_over_env(self):
        """When ContextVar is set, env vars are ignored."""
        ctx_config = {"url": "https://ctx.daktela.com", "token": "ctx-token"}
        token = _request_config.set(ctx_config)
        try:
            with patch.dict(os.environ, {"DAKTELA_URL": "https://env.daktela.com",
                                         "DAKTELA_ACCESS_TOKEN": "env-token"}):
                result = get_config()
            assert result == ctx_config
        finally:
            _request_config.reset(token)


class TestEnvVarFallback:
    async def test_falls_back_to_env_vars_in_stdio(self):
        """Without ContextVar and not in HTTP mode, env vars are used."""
        env = {
            "DAKTELA_URL": "https://env.daktela.com/",
            "DAKTELA_ACCESS_TOKEN": "env-tok",
        }
        with patch.dict(os.environ, env, clear=False):
            # Ensure MCP_TRANSPORT is not set to streamable-http
            os.environ.pop("MCP_TRANSPORT", None)
            result = get_config()

        assert result == {"url": "https://env.daktela.com", "token": "env-tok"}

    async def test_env_username_password(self):
        """Env-var fallback with username/password."""
        env = {
            "DAKTELA_URL": "https://env.daktela.com",
            "DAKTELA_USERNAME": "user",
            "DAKTELA_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("MCP_TRANSPORT", None)
            os.environ.pop("DAKTELA_ACCESS_TOKEN", None)
            result = get_config()

        assert result == {"url": "https://env.daktela.com", "username": "user", "password": "pass"}


class TestHttpSecurityGuard:
    async def test_raises_in_http_mode_without_contextvar(self):
        """In streamable-http mode, missing ContextVar raises ValueError (no env fallback)."""
        with patch.dict(os.environ, {"MCP_TRANSPORT": "streamable-http",
                                     "DAKTELA_URL": "https://should-not-use.com",
                                     "DAKTELA_ACCESS_TOKEN": "should-not-use"}):
            with pytest.raises(ValueError, match="credentials must be provided via HTTP headers"):
                get_config()
