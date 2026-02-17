FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Dependency layer (cached unless pyproject.toml changes)
COPY pyproject.toml .
COPY src/ src/
RUN uv pip install --system --no-cache .

# No DAKTELA_* env vars in the image — credentials come from headers only
ENV MCP_TRANSPORT=streamable-http
ENV PORT=8080

CMD ["python", "-m", "mcp_daktela"]
