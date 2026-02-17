import os

from mcp_daktela.auth import _request_config


def get_config() -> dict[str, str]:
    """Load Daktela configuration from ContextVar (HTTP mode) or environment variables.

    Priority:
    1. ContextVar set by DaktelaAuthMiddleware (per-request HTTP headers)
    2. Environment variables (stdio mode only)

    Security: In streamable-http transport mode, env-var fallback is blocked
    to prevent accidental credential exposure on shared infrastructure.
    """
    # Check ContextVar first (set by middleware from HTTP headers)
    ctx_config = _request_config.get()
    if ctx_config is not None:
        return ctx_config

    # Security guard: block env-var fallback in HTTP mode
    transport = os.environ.get("MCP_TRANSPORT", "")
    if transport == "streamable-http":
        raise ValueError(
            "Daktela credentials must be provided via HTTP headers "
            "(X-Daktela-Url, X-Daktela-Username/Password or X-Daktela-Access-Token)"
        )

    # Env-var fallback (stdio/local mode only)
    url = os.environ.get("DAKTELA_URL", "")
    if not url:
        raise ValueError("DAKTELA_URL environment variable is required")

    # Normalize: strip trailing slash
    url = url.rstrip("/")

    username = os.environ.get("DAKTELA_USERNAME", "")
    password = os.environ.get("DAKTELA_PASSWORD", "")
    token = os.environ.get("DAKTELA_ACCESS_TOKEN", "")

    if username and password:
        return {"url": url, "username": username, "password": password}
    elif token:
        return {"url": url, "token": token}
    else:
        raise ValueError(
            "Either DAKTELA_USERNAME + DAKTELA_PASSWORD or DAKTELA_ACCESS_TOKEN "
            "environment variables are required"
        )
