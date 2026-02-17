"""Enable `python -m mcp_daktela` invocation (used by Dockerfile)."""

import logging
import os

from mcp_daktela.server import mcp, oauth_gate_middleware

# Configure tool-call logger to emit to stdout (picked up by Cloud Logging)
logging.getLogger("mcp_daktela.tools").setLevel(logging.INFO)
logging.getLogger("mcp_daktela.tools").addHandler(logging.StreamHandler())

transport = os.environ.get("MCP_TRANSPORT", "stdio")
host = os.environ.get("HOST", "0.0.0.0")
port = int(os.environ.get("PORT", "8080"))

kwargs = {}
if transport == "streamable-http":
    kwargs["middleware"] = [oauth_gate_middleware]
    kwargs["path"] = "/"

mcp.run(transport=transport, host=host, port=port, **kwargs)
