"""Tests for mcp_daktela.scorer — server-side LLM scoring."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_daktela.scorer import (
    MAX_SCAN_RECORDS,
    SCORING_TOOL,
    _build_batch_prompt,
    _call_anthropic,
    _call_openrouter,
    _get_api_key,
    _get_model,
    _get_provider,
    _make_error_scores,
    _scoring_tool_openai_format,
    score_conversations,
    smart_truncate,
)


class TestSmartTruncate:
    def test_short_text_unchanged(self):
        assert smart_truncate("hello world") == "hello world"

    def test_none_returns_empty(self):
        assert smart_truncate(None) == ""

    def test_empty_returns_empty(self):
        assert smart_truncate("") == ""

    def test_exact_limit_unchanged(self):
        text = "x" * 4000
        assert smart_truncate(text, max_len=4000) == text

    def test_truncates_with_head_and_tail(self):
        # 5000 chars, limit 100 → head=40, tail=60
        text = "A" * 2500 + "B" * 2500
        result = smart_truncate(text, max_len=100)
        assert result.startswith("A" * 40)
        assert result.endswith("B" * 60)
        assert "[... middle truncated ...]" in result

    def test_preserves_start_and_end(self):
        text = "START " + "x" * 5000 + " END_HERE"
        result = smart_truncate(text, max_len=200)
        assert result.startswith("START")
        assert result.endswith("END_HERE")

    def test_head_tail_ratio(self):
        # 40% head, 60% tail
        text = "x" * 10000
        result = smart_truncate(text, max_len=1000)
        parts = result.split("[... middle truncated ...]")
        assert len(parts) == 2
        head = parts[0].rstrip("\n")
        tail = parts[1].lstrip("\n")
        assert len(head) == 400  # 40% of 1000
        assert len(tail) == 600  # 60% of 1000


class TestBuildBatchPrompt:
    def test_single_record(self):
        records = [{"id": "CALL001", "time": "10:00", "agent": "John", "duration": "120",
                     "transcript": "Customer: Hi\nOperator: Hello"}]
        result = _build_batch_prompt(records, "Find angry customers")
        assert "Analysis criteria: Find angry customers" in result
        assert "CALL CALL001" in result
        assert "Agent: John" in result
        assert "Duration: 120s" in result
        assert "Customer: Hi" in result

    def test_empty_transcript(self):
        records = [{"id": "CALL001", "time": "10:00", "agent": "John", "duration": "30",
                     "transcript": ""}]
        result = _build_batch_prompt(records, "test")
        assert "no content available" in result

    def test_multiple_records(self):
        records = [
            {"id": "C1", "time": "10:00", "agent": "A1", "duration": "60", "transcript": "T1"},
            {"id": "C2", "time": "11:00", "agent": "A2", "duration": "90", "transcript": "T2"},
        ]
        result = _build_batch_prompt(records, "test")
        assert "CALL C1" in result
        assert "CALL C2" in result

    def test_email_content_type(self):
        records = [{"id": "E1", "time": "10:00", "agent": "A1",
                     "subject": "Invoice issue", "body": "Please help"}]
        result = _build_batch_prompt(records, "test", content_type="EMAIL")
        assert "EMAIL E1" in result
        assert "Subject: Invoice issue" in result
        assert "Please help" in result

    def test_custom_content_type(self):
        records = [{"id": "CH1", "time": "10:00", "agent": "A1", "transcript": "Hi"}]
        result = _build_batch_prompt(records, "test", content_type="CHAT")
        assert "CHAT CH1" in result


class TestMakeErrorScores:
    def test_returns_error_for_each_record(self):
        records = [{"id": "C1"}, {"id": "C2"}]
        result = _make_error_scores(records, "timeout")
        assert len(result) == 2
        assert result[0]["id"] == "C1"
        assert result[0]["score"] == 0
        assert "scoring_error" in result[0]["flags"]
        assert "timeout" in result[0]["summary"]


# ---------------------------------------------------------------------------
# Provider config tests
# ---------------------------------------------------------------------------

class TestScorerConfig:
    def test_default_provider_is_openrouter(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _get_provider() == "openrouter"

    def test_provider_anthropic(self):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic"}):
            assert _get_provider() == "anthropic"

    def test_provider_openrouter_explicit(self):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "openrouter"}):
            assert _get_provider() == "openrouter"

    def test_provider_case_insensitive(self):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "OpenRouter"}):
            assert _get_provider() == "openrouter"

    def test_invalid_provider_raises(self):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "gemini"}):
            with pytest.raises(ValueError, match="must be 'openrouter' or 'anthropic'"):
                _get_provider()

    def test_default_model_openrouter(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _get_model() == "google/gemini-2.0-flash-lite-001"

    def test_default_model_anthropic(self):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic"}):
            assert _get_model() == "claude-haiku-4-5-20251001"

    def test_explicit_model_override(self):
        with patch.dict("os.environ", {"SCORER_MODEL": "google/gemma-3"}):
            assert _get_model() == "google/gemma-3"

    def test_api_key_openrouter(self):
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-key"}, clear=True):
            assert _get_api_key() == "or-key"

    def test_api_key_anthropic(self):
        with patch.dict("os.environ", {
            "SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "ant-key",
        }):
            assert _get_api_key() == "ant-key"

    def test_missing_openrouter_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                _get_api_key()

    def test_missing_anthropic_key_raises(self):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic"}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                _get_api_key()


# ---------------------------------------------------------------------------
# Tool format conversion
# ---------------------------------------------------------------------------

class TestScoringToolOpenAIFormat:
    def test_structure(self):
        result = _scoring_tool_openai_format()
        assert result["type"] == "function"
        assert result["function"]["name"] == "score_conversations"
        assert result["function"]["description"] == SCORING_TOOL["description"]
        assert result["function"]["parameters"] == SCORING_TOOL["input_schema"]

    def test_preserves_required_fields(self):
        result = _scoring_tool_openai_format()
        params = result["function"]["parameters"]
        assert "scores" in params["required"]
        items_props = params["properties"]["scores"]["items"]["properties"]
        assert "id" in items_props
        assert "score" in items_props
        assert "flags" in items_props
        assert "summary" in items_props


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------

class TestScoreConversationsAnthropic:
    """Tests for the Anthropic scoring path (existing behavior)."""

    @pytest.fixture
    def mock_haiku_response(self):
        """Create a mock Anthropic response with tool_use."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "score_conversations"
        tool_block.input = {
            "scores": [
                {"id": "C1", "score": 1, "flags": [], "summary": "Routine call"},
                {"id": "C2", "score": 4, "flags": ["angry_customer"],
                 "summary": "Customer upset about billing"},
            ]
        }
        response = MagicMock()
        response.content = [tool_block]
        return response

    @pytest.fixture
    def sample_records(self):
        return [
            {"id": "C1", "time": "10:00", "agent": "A", "duration": "60",
             "transcript": "Normal conversation"},
            {"id": "C2", "time": "11:00", "agent": "B", "duration": "120",
             "transcript": "Angry conversation"},
        ]

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_returns_scores(self, sample_records, mock_haiku_response):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_haiku_response)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test question", batch_size=10)

        assert len(results) == 2
        assert results[0]["id"] == "C1"
        assert results[0]["score"] == 1
        assert results[1]["id"] == "C2"
        assert results[1]["score"] == 4
        assert "angry_customer" in results[1]["flags"]

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_batching(self, mock_haiku_response):
        # 5 records with batch_size=2 → 3 batches
        records = [
            {"id": f"C{i}", "time": "10:00", "agent": "A", "duration": "60",
             "transcript": f"Transcript {i}"}
            for i in range(5)
        ]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            # Each batch returns scores for its records
            mock_client.messages.create = AsyncMock(return_value=mock_haiku_response)
            mock_cls.return_value = mock_client

            await score_conversations(records, "test", batch_size=2)

        # 3 batches: [C0,C1], [C2,C3], [C4]
        assert mock_client.messages.create.call_count == 3

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_handles_api_error(self, sample_records):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(side_effect=Exception("API timeout"))
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test", batch_size=10)

        assert len(results) == 2
        assert all(r["score"] == 0 for r in results)
        assert all("scoring_error" in r["flags"] for r in results)

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_caps_at_max_records(self):
        records = [
            {"id": f"C{i}", "time": "10:00", "agent": "A", "duration": "60", "transcript": "t"}
            for i in range(MAX_SCAN_RECORDS + 50)
        ]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.name = "score_conversations"
            tool_block.input = {"scores": [
                {"id": f"C{i}", "score": 1, "flags": [], "summary": "ok"}
                for i in range(10)
            ]}
            response = MagicMock()
            response.content = [tool_block]
            mock_client.messages.create = AsyncMock(return_value=response)
            mock_cls.return_value = mock_client

            results = await score_conversations(records, "test", batch_size=10)

        # Should have a _meta entry about capping
        meta = [r for r in results if r.get("id") == "_meta"]
        assert len(meta) == 1
        assert "capped" in meta[0]["summary"].lower()

    async def test_missing_api_key_anthropic(self, sample_records):
        with patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic"}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                await score_conversations(sample_records, "test")

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_empty_records(self):
        results = await score_conversations([], "test")
        assert results == []

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_progress_callback(self, sample_records, mock_haiku_response):
        progress_calls = []

        async def on_progress(completed, total, message):
            progress_calls.append((completed, total, message))

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_haiku_response)
            mock_cls.return_value = mock_client

            await score_conversations(
                sample_records, "test", on_progress=on_progress, batch_size=10
            )

        assert len(progress_calls) == 1  # 1 batch
        assert progress_calls[0][0] == 2  # completed
        assert progress_calls[0][1] == 2  # total

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_uses_tool_use(self, sample_records, mock_haiku_response):
        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_haiku_response)
            mock_cls.return_value = mock_client

            await score_conversations(sample_records, "test", batch_size=10)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["tool_choice"] == {"type": "tool", "name": "score_conversations"}
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "score_conversations"

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_no_tool_use_block_returns_error(self, sample_records):
        """When Anthropic returns no tool_use block, batch gets error scores."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I cannot score these."
        response = MagicMock()
        response.content = [text_block]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=response)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test", batch_size=10)

        assert len(results) == 2
        assert all(r["score"] == 0 for r in results)
        assert all("scoring_error" in r["flags"] for r in results)


# ---------------------------------------------------------------------------
# OpenRouter provider tests
# ---------------------------------------------------------------------------

class TestOpenRouterProvider:
    """Tests for the OpenRouter scoring path."""

    @pytest.fixture
    def sample_records(self):
        return [
            {"id": "C1", "time": "10:00", "agent": "A", "duration": "60",
             "transcript": "Normal conversation"},
            {"id": "C2", "time": "11:00", "agent": "B", "duration": "120",
             "transcript": "Angry conversation"},
        ]

    def _openrouter_response(self, scores: list[dict]) -> dict:
        """Build an OpenRouter-style response dict."""
        return {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "score_conversations",
                            "arguments": json.dumps({"scores": scores}),
                        },
                    }],
                },
            }],
        }

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-test-key"}, clear=True)
    async def test_returns_scores(self, sample_records):
        scores = [
            {"id": "C1", "score": 1, "flags": [], "summary": "Routine"},
            {"id": "C2", "score": 4, "flags": ["angry_customer"], "summary": "Upset customer"},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = self._openrouter_response(scores)

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test question", batch_size=10)

        assert len(results) == 2
        assert results[0]["id"] == "C1"
        assert results[1]["score"] == 4

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-test-key"}, clear=True)
    async def test_sends_correct_request(self, sample_records):
        scores = [{"id": "C1", "score": 1, "flags": [], "summary": "ok"}]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = self._openrouter_response(scores)

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await score_conversations(sample_records, "test", batch_size=10)

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert "openrouter.ai" in url
        payload = call_args[1]["json"]
        assert payload["model"] == "google/gemini-2.0-flash-lite-001"
        assert payload["tools"][0]["type"] == "function"
        assert payload["tool_choice"]["function"]["name"] == "score_conversations"
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer or-test-key"

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-test-key"}, clear=True)
    async def test_http_error_returns_error_scores(self, sample_records):
        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "429 Too Many Requests",
                    request=MagicMock(),
                    response=MagicMock(status_code=429),
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test", batch_size=10)

        assert len(results) == 2
        assert all(r["score"] == 0 for r in results)
        assert all("scoring_error" in r["flags"] for r in results)

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-test-key"}, clear=True)
    async def test_empty_choices_returns_error_scores(self, sample_records):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"choices": []}

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test", batch_size=10)

        assert len(results) == 2
        assert all(r["score"] == 0 for r in results)

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-test-key"}, clear=True)
    async def test_no_tool_calls_returns_error_scores(self, sample_records):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "I can't do this", "tool_calls": []}}],
        }

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test", batch_size=10)

        assert len(results) == 2
        assert all(r["score"] == 0 for r in results)

    async def test_missing_openrouter_key_raises(self, sample_records):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                await score_conversations(sample_records, "test")

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-test-key"}, clear=True)
    async def test_malformed_arguments_returns_error_scores(self, sample_records):
        """When arguments JSON is malformed, batch gets error scores."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "score_conversations",
                            "arguments": "not valid json{{{",
                        },
                    }],
                },
            }],
        }

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            results = await score_conversations(sample_records, "test", batch_size=10)

        assert len(results) == 2
        assert all(r["score"] == 0 for r in results)

    @patch.dict("os.environ", {
        "OPENROUTER_API_KEY": "or-test-key",
        "SCORER_MODEL": "anthropic/claude-haiku",
    }, clear=True)
    async def test_custom_model_override(self, sample_records):
        scores = [{"id": "C1", "score": 1, "flags": [], "summary": "ok"}]
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = self._openrouter_response(scores)

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await score_conversations(sample_records, "test", batch_size=10)

        payload = mock_client.post.call_args[1]["json"]
        assert payload["model"] == "anthropic/claude-haiku"


# ---------------------------------------------------------------------------
# Direct _call_anthropic / _call_openrouter unit tests
# ---------------------------------------------------------------------------

class TestCallAnthropic:
    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_returns_scores(self):
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "score_conversations"
        tool_block.input = {"scores": [{"id": "X", "score": 3, "flags": [], "summary": "test"}]}
        response = MagicMock()
        response.content = [tool_block]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=response)
            mock_cls.return_value = mock_client

            result = await _call_anthropic("test prompt")

        assert result == [{"id": "X", "score": 3, "flags": [], "summary": "test"}]

    @patch.dict("os.environ", {"SCORER_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "test-key"})
    async def test_empty_when_no_tool_use(self):
        text_block = MagicMock()
        text_block.type = "text"
        response = MagicMock()
        response.content = [text_block]

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=response)
            mock_cls.return_value = mock_client

            result = await _call_anthropic("test prompt")

        assert result == []


class TestCallOpenRouter:
    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-key"}, clear=True)
    async def test_returns_scores(self):
        scores = [{"id": "Y", "score": 2, "flags": [], "summary": "ok"}]
        response_data = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "score_conversations",
                            "arguments": json.dumps({"scores": scores}),
                        },
                    }],
                },
            }],
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = response_data

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await _call_openrouter("test prompt")

        assert result == scores

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-key"}, clear=True)
    async def test_empty_when_no_choices(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"choices": []}

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await _call_openrouter("test prompt")

        assert result == []

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "or-key"}, clear=True)
    async def test_arguments_as_dict(self):
        """Some providers return arguments already parsed as dict."""
        scores = [{"id": "Z", "score": 1, "flags": [], "summary": "ok"}]
        response_data = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "score_conversations",
                            "arguments": {"scores": scores},  # dict, not string
                        },
                    }],
                },
            }],
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = response_data

        with patch("mcp_daktela.scorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await _call_openrouter("test prompt")

        assert result == scores
