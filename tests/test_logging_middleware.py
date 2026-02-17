"""Tests for ToolLoggingMiddleware."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_daktela.logging_middleware import ToolLoggingMiddleware, _sanitize_params


class TestSanitizeParams:
    def test_short_values_preserved(self):
        assert _sanitize_params({"a": "short", "b": 42}) == {"a": "short", "b": 42}

    def test_long_strings_truncated(self):
        long_val = "x" * 300
        result = _sanitize_params({"key": long_val})
        assert len(result["key"]) == 203  # 200 + "..."
        assert result["key"].endswith("...")

    def test_non_string_values_unchanged(self):
        assert _sanitize_params({"n": 100, "b": True, "x": None}) == {
            "n": 100, "b": True, "x": None,
        }


class TestToolLoggingMiddleware:
    @pytest.fixture
    def middleware(self):
        return ToolLoggingMiddleware()

    @pytest.fixture
    def context(self):
        ctx = MagicMock()
        ctx.message.name = "list_tickets"
        ctx.message.arguments = {"stage": "OPEN", "take": 50}
        return ctx

    async def test_logs_successful_call(self, middleware, context):
        mock_result = MagicMock()
        mock_result.content = []

        call_next = AsyncMock(return_value=mock_result)

        with patch("mcp_daktela.logging_middleware.logger") as mock_logger:
            result = await middleware.on_call_tool(context, call_next)

        assert result is mock_result
        call_next.assert_awaited_once_with(context=context)

        log_call = mock_logger.info.call_args[0][0]
        log_data = json.loads(log_call)
        assert log_data["event"] == "tool_call"
        assert log_data["tool"] == "list_tickets"
        assert log_data["params"] == {"stage": "OPEN", "take": 50}
        assert log_data["status"] == "ok"
        assert "duration_ms" in log_data
        assert "response_bytes" in log_data

    async def test_logs_error_and_reraises(self, middleware, context):
        call_next = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("mcp_daktela.logging_middleware.logger") as mock_logger:
            with pytest.raises(RuntimeError, match="boom"):
                await middleware.on_call_tool(context, call_next)

        log_call = mock_logger.error.call_args[0][0]
        log_data = json.loads(log_call)
        assert log_data["event"] == "tool_call"
        assert log_data["tool"] == "list_tickets"
        assert log_data["status"] == "error"
        assert "boom" in log_data["error"]
        assert "duration_ms" in log_data

    async def test_handles_missing_arguments(self, middleware):
        ctx = MagicMock()
        ctx.message.name = "get_ticket"
        ctx.message.arguments = None

        mock_result = MagicMock()
        mock_result.content = []
        call_next = AsyncMock(return_value=mock_result)

        with patch("mcp_daktela.logging_middleware.logger") as mock_logger:
            await middleware.on_call_tool(ctx, call_next)

        log_data = json.loads(mock_logger.info.call_args[0][0])
        assert log_data["params"] == {}
