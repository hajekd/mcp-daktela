"""Server-side conversation scoring using LLM providers.

Implements the "map" phase of the map-reduce pattern:
- Fetch all matching records (done by caller)
- Batch records into groups of ~20
- Score each batch with LLM using tool_use for structured output
- Return compact scored results for the outer LLM to analyze

Supports two providers:
- openrouter (default): Minimax M2.5 via OpenRouter — $0.30/$1.10 per MTok
- anthropic: Claude Haiku 4.5 via Anthropic SDK — $1/$5 per MTok
"""

import asyncio
import json
import logging
import os
from typing import Any, Callable, Coroutine

import httpx

logger = logging.getLogger(__name__)

# Safety limits
MAX_SCAN_RECORDS = 1000
MAX_TRANSCRIPT_CHARS = 4000
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_CONCURRENCY = 10

# Provider defaults
_DEFAULT_PROVIDER = "openrouter"
_OPENROUTER_DEFAULT_MODEL = "google/gemini-2.0-flash-lite-001"
_ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SCORING_TOOL = {
    "name": "score_conversations",
    "description": "Score a batch of conversations based on analysis criteria.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "The call/record ID as provided.",
                        },
                        "score": {
                            "type": "integer",
                            "description": (
                                "1=routine, 2=minor note, 3=worth reviewing, "
                                "4=needs attention, 5=urgent/critical"
                            ),
                        },
                        "flags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Applicable flags: angry_customer, escalation_request, "
                                "compliance_risk, lost_deal, missed_commitment, "
                                "communication_issue, exceptional_service, technical_issue, "
                                "billing_dispute, churn_risk"
                            ),
                        },
                        "summary": {
                            "type": "string",
                            "description": (
                                "One sentence: what happened and why it matters. Max 150 chars."
                            ),
                        },
                    },
                    "required": ["id", "score", "flags", "summary"],
                },
            },
        },
        "required": ["scores"],
    },
}

SYSTEM_PROMPT = (
    "You are a contact center quality analyst. You will receive a batch of "
    "contact center records (calls, emails, chats, or other interactions).\n\n"
    "For each record, evaluate it against the analysis criteria and score it "
    "using the score_conversations tool.\n\n"
    "Scoring guide:\n"
    "- 1: Routine, no issues\n"
    "- 2: Minor note but no action needed\n"
    "- 3: Worth reviewing — something slightly unusual\n"
    "- 4: Needs attention — clear issue or risk identified\n"
    "- 5: Urgent — requires immediate management attention\n\n"
    "Be selective with high scores. Most records (70-80%) should score 1-2. "
    "Only flag genuine issues — false positives waste management time.\n\n"
    "Flags must be specific and accurate. Don't flag 'angry_customer' for mild frustration.\n\n"
    "Summaries must be concrete: who, what, why it matters. No generic statements."
)

# Type alias for progress callback: (completed, total, message) -> None
ProgressCallback = Callable[[int, int, str], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

def _get_provider() -> str:
    """Return scoring provider: 'openrouter' or 'anthropic'."""
    provider = os.environ.get("SCORER_PROVIDER", _DEFAULT_PROVIDER).lower()
    if provider not in ("openrouter", "anthropic"):
        raise ValueError(
            f"SCORER_PROVIDER must be 'openrouter' or 'anthropic', got '{provider}'"
        )
    return provider


def _get_model() -> str:
    """Return model ID, defaulting per provider."""
    explicit = os.environ.get("SCORER_MODEL")
    if explicit:
        return explicit
    provider = _get_provider()
    if provider == "anthropic":
        return _ANTHROPIC_DEFAULT_MODEL
    return _OPENROUTER_DEFAULT_MODEL


def _get_api_key() -> str:
    """Return the API key for the active provider."""
    provider = _get_provider()
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required when "
                "SCORER_PROVIDER=anthropic. Set it in your Cloud Run service or .env file."
            )
        return key
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required for scan tools. "
            "Set it in your Cloud Run service or .env file."
        )
    return key


# ---------------------------------------------------------------------------
# Tool format conversion
# ---------------------------------------------------------------------------

def _scoring_tool_openai_format() -> dict:
    """Convert Anthropic tool schema to OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": SCORING_TOOL["name"],
            "description": SCORING_TOOL["description"],
            "parameters": SCORING_TOOL["input_schema"],
        },
    }


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

async def _call_anthropic(prompt: str) -> list[dict]:
    """Call Anthropic API using the SDK. Returns list of score dicts."""
    import anthropic

    api_key = _get_api_key()
    model = _get_model()
    client = anthropic.AsyncAnthropic(api_key=api_key)

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[SCORING_TOOL],
        tool_choice={"type": "tool", "name": "score_conversations"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "score_conversations":
            scores = block.input.get("scores", [])
            if scores:
                return scores

    return []


async def _call_openrouter(prompt: str) -> list[dict]:
    """Call OpenRouter chat/completions API. Returns list of score dicts."""
    api_key = _get_api_key()
    model = _get_model()

    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "tools": [_scoring_tool_openai_format()],
        "tool_choice": {"type": "function", "function": {"name": "score_conversations"}},
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    # Parse OpenAI-style tool_calls response
    choices = data.get("choices", [])
    if not choices:
        return []

    message = choices[0].get("message", {})
    tool_calls = message.get("tool_calls", [])

    for tc in tool_calls:
        func = tc.get("function", {})
        if func.get("name") == "score_conversations":
            args = func.get("arguments", "{}")
            if isinstance(args, str):
                args = json.loads(args)
            scores = args.get("scores", [])
            if scores:
                return scores

    return []


async def _call_llm(prompt: str) -> list[dict]:
    """Dispatch to the configured provider. Returns list of score dicts."""
    provider = _get_provider()
    if provider == "anthropic":
        return await _call_anthropic(prompt)
    return await _call_openrouter(prompt)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def smart_truncate(text: str, max_len: int = MAX_TRANSCRIPT_CHARS) -> str:
    """Truncate keeping first and last portions.

    Takes 40% from start (opening context/greeting) and 60% from end
    (resolution/escalation — where the signal usually lives).
    """
    if not text or len(text) <= max_len:
        return text or ""
    head_len = max_len * 2 // 5  # 40%
    tail_len = max_len * 3 // 5  # 60%
    return text[:head_len] + "\n\n[... middle truncated ...]\n\n" + text[-tail_len:]


def _build_batch_prompt(
    batch: list[dict], question: str, content_type: str = "CALL",
) -> str:
    """Build the user prompt for a batch of records."""
    parts = [f"Analysis criteria: {question}\n\nRecords to analyze:\n"]
    for item in batch:
        record_id = item.get("id", "?")
        time = item.get("time", "")
        agent = item.get("agent", "unknown")
        # Build header fields
        header_parts = [f"{content_type} {record_id}", time, f"Agent: {agent}"]
        for extra_key in ("duration", "subject", "direction", "address"):
            val = item.get(extra_key)
            if val:
                label = extra_key.capitalize()
                suffix = "s" if extra_key == "duration" else ""
                header_parts.append(f"{label}: {val}{suffix}")
        header = " | ".join(p for p in header_parts if p)

        body = smart_truncate(item.get("transcript", "") or item.get("body", ""))
        if not body:
            body = f"(no content available)"
        parts.append(f"=== {header} ===\n{body}\n")
    return "\n".join(parts)


def _make_error_scores(batch: list[dict], reason: str) -> list[dict]:
    """Generate fallback scores when scoring fails."""
    return [
        {
            "id": r.get("id", "?"),
            "score": 0,
            "flags": ["scoring_error"],
            "summary": reason,
        }
        for r in batch
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def score_conversations(
    records: list[dict],
    question: str,
    on_progress: ProgressCallback | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    content_type: str = "CALL",
) -> list[dict]:
    """Score conversations using LLM in batches.

    Args:
        records: List of dicts, each with: id, time, agent, + content fields.
        question: The analysis criteria / user's analytical question.
        on_progress: Optional async callback(completed, total, message).
        batch_size: Records per LLM API call (default: 20).
        max_concurrency: Max parallel LLM calls (default: 10).

    Returns:
        List of scored dicts: id, score, flags, summary.
        Records that failed scoring have score=0 and flags=["scoring_error"].
    """
    # Validate config eagerly (fail fast before processing)
    _get_api_key()

    # Enforce safety cap
    capped = False
    if len(records) > MAX_SCAN_RECORDS:
        records = records[:MAX_SCAN_RECORDS]
        capped = True

    if not records:
        return []

    # Build batches
    batches = [records[i : i + batch_size] for i in range(0, len(records), batch_size)]

    sem = asyncio.Semaphore(max_concurrency)
    completed = 0
    lock = asyncio.Lock()

    async def _score_batch(batch: list[dict]) -> list[dict]:
        nonlocal completed
        async with sem:
            prompt = _build_batch_prompt(batch, question, content_type)
            try:
                scores = await _call_llm(prompt)
                if not scores:
                    logger.warning("LLM returned no scores for batch")
                    return _make_error_scores(batch, "No scoring response")
                return scores
            except Exception as e:
                logger.warning(f"LLM scoring failed: {type(e).__name__}: {e}")
                return _make_error_scores(batch, "Scoring temporarily unavailable")
            finally:
                async with lock:
                    completed += len(batch)
                    if on_progress:
                        await on_progress(
                            completed, len(records),
                            f"Scored {completed}/{len(records)} records",
                        )

    batch_results = await asyncio.gather(*[_score_batch(b) for b in batches])

    results = []
    for batch_scores in batch_results:
        results.extend(batch_scores)

    # Tag if we hit the cap
    if capped:
        results.append({
            "id": "_meta",
            "score": 0,
            "flags": ["results_capped"],
            "summary": f"Analysis capped at {MAX_SCAN_RECORDS} records. More exist.",
        })

    return results
