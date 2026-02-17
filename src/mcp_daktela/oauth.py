"""OAuth 2.0 authorization server for Claude Desktop "Add custom connector" flow.

Implements stateless OAuth 2.0 with:
- RFC 9728: OAuth Protected Resource Metadata
- RFC 8414: OAuth Authorization Server Metadata
- RFC 7591: Dynamic Client Registration
- PKCE (RFC 7636): Proof Key for Code Exchange

All tokens (auth codes, access tokens, refresh tokens) are stateless JWTs signed
with JWT_SECRET. No database needed.

Token design:
- Access token: contains daktela_url + daktela_access_token, expires when
  Daktela access token expires (~2h). Used directly for API calls.
- Refresh token: contains daktela_url + username + password (server-signed,
  opaque to client), 30-day expiry. On refresh, re-logins to Daktela to get
  a fresh access token. Credentials never leave the server — the JWT is signed
  and can only be decoded with JWT_SECRET.
- Auth code: signed JWT, 5-minute expiry, PKCE-protected.
"""

import hashlib
import json
import os
import secrets
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timezone

import httpx
import jwt
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp_daktela.auth import _validate_url

# JWT signing secret — must be set in Cloud Run env vars
_JWT_ALGORITHM = "HS256"
_AUTH_CODE_LIFETIME = 300  # 5 minutes
_REFRESH_TOKEN_LIFETIME = 30 * 86400  # 30 days


class OAuthGateMiddleware:
    """ASGI middleware that returns 401 + WWW-Authenticate for unauthenticated /mcp requests.

    Per the MCP spec (RFC 9728), when a client accesses the MCP endpoint without
    a valid Bearer token, the server MUST return 401 with a WWW-Authenticate header
    pointing to the protected resource metadata. This triggers the OAuth discovery flow.

    Requests to non-/mcp paths (OAuth endpoints, well-known, etc.) pass through.
    Requests with Authorization: Bearer or X-Daktela-* headers pass through.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path not in ("/", "/mcp"):
            await self.app(scope, receive, send)
            return

        # Check if any auth is present
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        has_bearer = auth.startswith("Bearer ")
        has_daktela = any(
            key.startswith(b"x-daktela-") for key in headers
        )

        if has_bearer or has_daktela:
            await self.app(scope, receive, send)
            return

        # No auth — return 401 with WWW-Authenticate
        scheme = "https"
        host = ""
        for key, value in scope.get("headers", []):
            if key == b"x-forwarded-proto":
                scheme = value.decode()
            elif key == b"x-forwarded-host":
                host = value.decode()
            elif key == b"host" and not host:
                host = value.decode()

        resource_metadata_url = f"{scheme}://{host}/.well-known/oauth-protected-resource"
        www_auth = f'Bearer resource_metadata="{resource_metadata_url}"'

        response = Response(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": www_auth},
        )
        await response(scope, receive, send)


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise ValueError("JWT_SECRET environment variable is required")
    return secret


def _parse_daktela_datetime(dt_str: str) -> int:
    """Parse Daktela datetime string to unix timestamp."""
    # Daktela returns "2026-02-14 23:34:17" (naive, assumed UTC)
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _sign_jwt(payload: dict) -> str:
    return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)


def _decode_jwt(token: str, expected_type: str) -> dict:
    """Decode and verify a JWT, checking the type claim."""
    payload = jwt.decode(token, _get_jwt_secret(), algorithms=[_JWT_ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")
    return payload


def _get_server_url(request: Request) -> str:
    """Derive the public server URL from the request."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{scheme}://{host}"


async def _daktela_login(daktela_url: str, username: str, password: str) -> dict | str:
    """Login to Daktela API. Returns result dict on success, error string on failure."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                f"{daktela_url}/api/v6/login.json",
                json={"username": username, "password": password},
            )
    except httpx.HTTPError:
        return "Could not connect to Daktela instance"

    if resp.status_code != 200:
        return "Invalid username or password"

    result = resp.json().get("result", {})
    if not result.get("accessToken"):
        return "Unexpected response from Daktela API"

    return result


# ---------------------------------------------------------------------------
# OAuth endpoint handlers
# ---------------------------------------------------------------------------


async def handle_protected_resource_metadata(request: Request) -> Response:
    """RFC 9728: OAuth Protected Resource Metadata."""
    server_url = _get_server_url(request)
    return JSONResponse({
        "resource": f"{server_url}/",
        "authorization_servers": [server_url],
    })


async def handle_authorization_server_metadata(request: Request) -> Response:
    """RFC 8414: OAuth Authorization Server Metadata."""
    server_url = _get_server_url(request)
    return JSONResponse({
        "issuer": server_url,
        "authorization_endpoint": f"{server_url}/oauth/authorize",
        "token_endpoint": f"{server_url}/oauth/token",
        "registration_endpoint": f"{server_url}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    })


async def handle_register(request: Request) -> Response:
    """RFC 7591: Dynamic Client Registration.

    Claude Desktop registers itself as a public client. We accept any
    registration and return the same client_id back (stateless — we don't
    store registrations, we just need the redirect_uris for validation).
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    redirect_uris = body.get("redirect_uris", [])
    if not redirect_uris:
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "redirect_uris required"},
            status_code=400,
        )

    client_id = secrets.token_urlsafe(32)

    return JSONResponse(
        {
            "client_id": client_id,
            "client_name": body.get("client_name", "MCP Client"),
            "redirect_uris": redirect_uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
        status_code=201,
    )


_LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect Daktela to Claude</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f5f5f5; display: flex; justify-content: center; align-items: center;
         min-height: 100vh; padding: 20px; }
  .card { background: white; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1);
          padding: 40px; max-width: 420px; width: 100%; }
  h1 { font-size: 1.4em; margin-bottom: 8px; color: #1a1a1a; }
  .subtitle { color: #666; margin-bottom: 24px; font-size: 0.9em; }
  label { display: block; font-weight: 500; margin-bottom: 4px; color: #333; font-size: 0.9em; }
  input { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px;
          font-size: 1em; margin-bottom: 16px; }
  input:focus { outline: none; border-color: #7c3aed; box-shadow: 0 0 0 3px rgba(124,58,237,0.1); }
  button { width: 100%; padding: 12px; background: #7c3aed; color: white; border: none;
           border-radius: 8px; font-size: 1em; font-weight: 500; cursor: pointer; }
  button:hover { background: #6d28d9; }
  .error { background: #fef2f2; border: 1px solid #fecaca; color: #dc2626; padding: 10px 12px;
           border-radius: 8px; margin-bottom: 16px; font-size: 0.9em; }
  .hint { color: #888; font-size: 0.8em; margin-top: -12px; margin-bottom: 16px; }
  .logo { display: block; max-width: 180px; height: auto; margin: 0 auto 24px; }
</style>
</head>
<body>
<div class="card">
  <img src="/logo.png" alt="Daktela" class="logo">
  <h1>Connect Daktela to Claude</h1>
  <p class="subtitle">Enter your Daktela instance credentials</p>
  {{ERROR}}
  <form method="POST">
    <input type="hidden" name="client_id" value="{{CLIENT_ID}}">
    <input type="hidden" name="redirect_uri" value="{{REDIRECT_URI}}">
    <input type="hidden" name="code_challenge" value="{{CODE_CHALLENGE}}">
    <input type="hidden" name="code_challenge_method" value="{{CODE_CHALLENGE_METHOD}}">
    <input type="hidden" name="state" value="{{STATE}}">
    <label for="daktela_url">Daktela Instance URL</label>
    <input type="url" id="daktela_url" name="daktela_url"
           placeholder="https://yourcompany.daktela.com" required
           value="{{DAKTELA_URL}}">
    <p class="hint">e.g. https://yourcompany.daktela.com</p>
    <label for="username">Username</label>
    <input type="text" id="username" name="username" required
           value="{{USERNAME}}" autocomplete="username">
    <label for="password">Password</label>
    <input type="password" id="password" name="password" required
           autocomplete="current-password">
    <button type="submit">Connect</button>
  </form>
</div>
</body>
</html>
"""


def _render_login(
    request: Request,
    error: str = "",
    daktela_url: str = "",
    username: str = "",
) -> HTMLResponse:
    """Render the login form, preserving query params as hidden fields."""
    params = request.query_params
    html = _LOGIN_HTML
    html = html.replace("{{CLIENT_ID}}", params.get("client_id", ""))
    html = html.replace("{{REDIRECT_URI}}", params.get("redirect_uri", ""))
    html = html.replace("{{CODE_CHALLENGE}}", params.get("code_challenge", ""))
    html = html.replace("{{CODE_CHALLENGE_METHOD}}", params.get("code_challenge_method", "S256"))
    html = html.replace("{{STATE}}", params.get("state", ""))
    html = html.replace("{{DAKTELA_URL}}", daktela_url)
    html = html.replace("{{USERNAME}}", username)
    if error:
        html = html.replace("{{ERROR}}", f'<div class="error">{error}</div>')
    else:
        html = html.replace("{{ERROR}}", "")
    return HTMLResponse(html)


async def handle_authorize(request: Request) -> Response:
    """OAuth authorize endpoint — shows login form (GET) or processes it (POST)."""
    if request.method == "GET":
        return _render_login(request)

    # POST — process the login form
    form = await request.form()
    daktela_url = str(form.get("daktela_url", "")).strip()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    redirect_uri = str(form.get("redirect_uri", ""))
    client_id = str(form.get("client_id", ""))
    code_challenge = str(form.get("code_challenge", ""))
    code_challenge_method = str(form.get("code_challenge_method", "S256"))
    state = str(form.get("state", ""))

    if not redirect_uri:
        return _render_login(request, error="Missing redirect_uri", daktela_url=daktela_url,
                             username=username)

    if code_challenge_method != "S256":
        return _render_login(request, error="Only S256 code challenge method is supported",
                             daktela_url=daktela_url, username=username)

    # Validate Daktela URL (SSRF protection)
    try:
        daktela_url = _validate_url(daktela_url)
    except ValueError as e:
        return _render_login(request, error=str(e), daktela_url=daktela_url, username=username)

    # Authenticate against Daktela API
    result = await _daktela_login(daktela_url, username, password)
    if isinstance(result, str):
        return _render_login(request, error=result, daktela_url=daktela_url, username=username)

    daktela_access_token = result["accessToken"]
    access_exp_str = result.get("accessTokenExpirationDate", "")

    # Parse access token expiry
    try:
        access_exp = _parse_daktela_datetime(access_exp_str)
    except (ValueError, TypeError):
        access_exp = int(time.time()) + 3600

    # Issue a signed auth code JWT (short-lived, contains everything needed)
    auth_code_payload = {
        "type": "auth_code",
        "daktela_url": daktela_url,
        "daktela_access_token": daktela_access_token,
        "daktela_access_exp": access_exp,
        "daktela_username": username,
        "daktela_password": password,
        "code_challenge": code_challenge,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "exp": int(time.time()) + _AUTH_CODE_LIFETIME,
    }
    auth_code = _sign_jwt(auth_code_payload)

    # Redirect back to Claude Desktop with the auth code
    sep = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{sep}code={auth_code}"
    if state:
        location += f"&state={state}"

    return Response(status_code=302, headers={"Location": location})


async def handle_token(request: Request) -> Response:
    """OAuth token endpoint — handles auth code exchange and refresh."""
    try:
        form = await request.form()
        grant_type = str(form.get("grant_type", ""))
    except Exception:
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    if grant_type == "authorization_code":
        return await _handle_auth_code_exchange(form)
    elif grant_type == "refresh_token":
        return await _handle_refresh(form)
    else:
        return JSONResponse(
            {"error": "unsupported_grant_type", "error_description": f"Unsupported: {grant_type}"},
            status_code=400,
        )


def _issue_token_response(
    daktela_url: str,
    daktela_access_token: str,
    access_exp: int,
    username: str,
    password: str,
) -> JSONResponse:
    """Build and return the OAuth token response with access + refresh tokens."""
    access_token = _sign_jwt({
        "type": "access_token",
        "daktela_url": daktela_url,
        "daktela_access_token": daktela_access_token,
        "exp": access_exp,
    })
    refresh_token = _sign_jwt({
        "type": "refresh_token",
        "daktela_url": daktela_url,
        "daktela_username": username,
        "daktela_password": password,
        "exp": int(time.time()) + _REFRESH_TOKEN_LIFETIME,
    })
    expires_in = max(0, access_exp - int(time.time()))
    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "refresh_token": refresh_token,
    })


async def _handle_auth_code_exchange(form) -> Response:
    """Exchange auth code for access + refresh tokens."""
    code = str(form.get("code", ""))
    code_verifier = str(form.get("code_verifier", ""))
    redirect_uri = str(form.get("redirect_uri", ""))

    if not code or not code_verifier:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "code and code_verifier required"},
            status_code=400,
        )

    # Decode the auth code JWT
    try:
        payload = _decode_jwt(code, expected_type="auth_code")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": str(e)},
            status_code=400,
        )

    # Verify PKCE: SHA256(code_verifier) must match code_challenge
    expected_challenge = (
        urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    if expected_challenge != payload.get("code_challenge"):
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "PKCE verification failed"},
            status_code=400,
        )

    # Verify redirect_uri matches
    if redirect_uri and redirect_uri != payload.get("redirect_uri"):
        return JSONResponse(
            {"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
            status_code=400,
        )

    return _issue_token_response(
        daktela_url=payload["daktela_url"],
        daktela_access_token=payload["daktela_access_token"],
        access_exp=payload["daktela_access_exp"],
        username=payload["daktela_username"],
        password=payload["daktela_password"],
    )


async def _handle_refresh(form) -> Response:
    """Use refresh token to re-login to Daktela and get a fresh access token."""
    refresh_token_str = str(form.get("refresh_token", ""))

    if not refresh_token_str:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "refresh_token required"},
            status_code=400,
        )

    # Decode our refresh token JWT
    try:
        payload = _decode_jwt(refresh_token_str, expected_type="refresh_token")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
        return JSONResponse(
            {"error": "invalid_grant", "error_description": str(e)},
            status_code=400,
        )

    daktela_url = payload["daktela_url"]
    username = payload["daktela_username"]
    password = payload["daktela_password"]

    # Re-login to Daktela to get a fresh access token
    result = await _daktela_login(daktela_url, username, password)
    if isinstance(result, str):
        return JSONResponse(
            {"error": "invalid_grant", "error_description": result},
            status_code=400,
        )

    new_access_token = result["accessToken"]
    access_exp_str = result.get("accessTokenExpirationDate", "")

    try:
        access_exp = _parse_daktela_datetime(access_exp_str)
    except (ValueError, TypeError):
        access_exp = int(time.time()) + 3600

    return _issue_token_response(
        daktela_url=daktela_url,
        daktela_access_token=new_access_token,
        access_exp=access_exp,
        username=username,
        password=password,
    )
