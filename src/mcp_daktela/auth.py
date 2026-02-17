"""Per-request credential passthrough via ContextVar + FastMCP middleware."""

import os
from contextvars import ContextVar
from urllib.parse import urlparse

import jwt
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams

_request_config: ContextVar[dict[str, str] | None] = ContextVar(
    "_request_config", default=None
)

# Default: only *.daktela.com domains allowed.
# Override with ALLOWED_DAKTELA_DOMAINS env var (comma-separated) for custom domains.
_DEFAULT_ALLOWED_DOMAINS = ["daktela.com"]


def _get_allowed_domains() -> list[str]:
    """Return the list of allowed domain suffixes for Daktela URLs."""
    env = os.environ.get("ALLOWED_DAKTELA_DOMAINS", "")
    if env.strip():
        return [d.strip().lower() for d in env.split(",") if d.strip()]
    return _DEFAULT_ALLOWED_DOMAINS


def _validate_url(url: str) -> str:
    """Validate and normalize the Daktela URL. Prevents SSRF attacks.

    Enforces:
    - HTTPS scheme only (blocks http, file, ftp, etc.)
    - Hostname must end with an allowed domain suffix (blocks internal IPs, metadata endpoints)
    - No IP addresses in hostname (blocks 169.254.169.254, 10.x.x.x, etc.)

    Returns the normalized URL (trailing slashes stripped).
    Raises ValueError on invalid URLs.
    """
    url = url.strip().rstrip("/")

    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError(
            f"X-Daktela-Url must use HTTPS (got '{parsed.scheme or 'empty'}')"
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("X-Daktela-Url has no hostname")

    # Block IP addresses (IPv4 and IPv6)
    # IPv6 in URLs appears as [::1], hostname would be "::1"
    if hostname.replace(".", "").isdigit() or ":" in hostname:
        raise ValueError("X-Daktela-Url must use a domain name, not an IP address")

    allowed = _get_allowed_domains()
    if not any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed):
        allowed_str = ", ".join(f"*.{d}" for d in allowed)
        raise ValueError(
            f"X-Daktela-Url hostname '{hostname}' is not allowed. "
            f"Allowed domains: {allowed_str}"
        )

    return url


def _decode_bearer_token(auth_header: str) -> dict[str, str] | None:
    """Decode a Bearer JWT access token into a Daktela config dict.

    Returns None if the header is not a Bearer token or decoding fails.
    Raises ValueError for expired or invalid tokens (so the error propagates to the client).
    """
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if not jwt_secret:
        return None

    payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access_token":
        raise ValueError("Invalid token type")

    daktela_url = payload.get("daktela_url", "")
    daktela_access_token = payload.get("daktela_access_token", "")
    if not daktela_url or not daktela_access_token:
        raise ValueError("Token missing required claims")

    return {"url": daktela_url, "token": daktela_access_token}


class DaktelaAuthMiddleware(Middleware):
    """Extract Daktela credentials from HTTP headers and store in ContextVar.

    Supports three auth modes:
    1. Authorization: Bearer <jwt> (OAuth access token from Claude Desktop connector)
    2. X-Daktela-Username + X-Daktela-Password (mcp-remote with headers)
    3. X-Daktela-Access-Token (mcp-remote with static token)

    Modes 2 and 3 require X-Daktela-Url.

    Security:
    - URL must be HTTPS and match an allowed domain (default: *.daktela.com)
    - Prevents SSRF attacks via URL validation
    - ContextVar is always cleaned up, even on errors

    In stdio mode (no HTTP headers), this is a no-op — falls through to env vars.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        headers = get_http_headers()

        # Path 1: Bearer JWT token (OAuth flow)
        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            config = _decode_bearer_token(auth_header)
            if config is not None:
                reset_token = _request_config.set(config)
                try:
                    return await call_next(context)
                finally:
                    _request_config.reset(reset_token)

        # Path 2: X-Daktela-* headers (mcp-remote flow)
        url = headers.get("x-daktela-url", "")
        username = headers.get("x-daktela-username", "")
        password = headers.get("x-daktela-password", "")
        token = headers.get("x-daktela-access-token", "")

        # No Daktela headers at all — pass through (stdio mode uses env vars)
        if not url and not username and not password and not token:
            return await call_next(context)

        if not url:
            raise ValueError("X-Daktela-Url header is required")

        url = _validate_url(url)

        if username and password:
            config = {"url": url, "username": username, "password": password}
        elif token:
            config = {"url": url, "token": token}
        else:
            raise ValueError(
                "Either X-Daktela-Username + X-Daktela-Password or "
                "X-Daktela-Access-Token header is required"
            )

        reset_token = _request_config.set(config)
        try:
            return await call_next(context)
        finally:
            _request_config.reset(reset_token)
