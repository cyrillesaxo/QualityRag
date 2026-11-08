"""Read-only Streamable HTTP MCP staging boundary.

Single-operator bearer authentication, explicit Origin/Host controls and
a narrowly scoped evidence tool registry. No mutating tools or inference jobs.
NOT a production multi-tenant OAuth server or publicly deployed service.
"""
from __future__ import annotations

import hmac
import os
import re
from contextvars import ContextVar
from video_auth import TokenVerifier, TokenAccessError

REQUEST_SOURCES = ContextVar('qualityrag_video_request_sources', default=None)

from video_catalog import _root, read_evidence, search_evidence
from video_research import research_video_evidence


class RemoteConfigurationError(ValueError):
    pass


def _config(environ):
    mode = environ.get("QUALITYRAG_VIDEO_MCP_AUTH_MODE", "static")
    if mode not in ("static","jwt"):
        raise RemoteConfigurationError("Choose static or jwt authentication")
    secret = environ.get("QUALITYRAG_VIDEO_MCP_TOKEN", "")
    if mode == "static" and (len(secret) < 32 or secret.strip() != secret):
        raise RemoteConfigurationError("Configure a random 32+ character bearer token")
    root = environ.get("QUALITYRAG_VIDEO_ROOT")
    if not root:
        raise RemoteConfigurationError("Set an explicit authorized video root")
    _root(root)
    host = environ.get("QUALITYRAG_VIDEO_MCP_HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise RemoteConfigurationError("Remote bind forbidden: use a protected local reverse proxy")
    allowed_hosts = [x.strip() for x in
                     environ.get("QUALITYRAG_VIDEO_MCP_ALLOWED_HOSTS","127.0.0.1:*,localhost:*").split(",")]
    if not allowed_hosts or any(not re.fullmatch(r"[A-Za-z0-9.*:,_-]{1,128}",x) for x in allowed_hosts):
        raise RemoteConfigurationError("Invalid explicit allowed hosts")
    origins = [x.strip() for x in environ.get("QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGINS","").split(",") if x.strip()]
    if any(not x.startswith("https://") or "/" in x[8:] or "*" in x for x in origins):
        raise RemoteConfigurationError("Origin allowlist must contain exact HTTPS origins")
    scope_text=environ.get("QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS", "")
    ids=[x.strip() for x in scope_text.split(",") if x.strip()]
    if not ids or len(ids)>1000 or len(ids)!=len(set(ids)) or any(
            not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",value) for value in ids):
        raise RemoteConfigurationError("Configure an explicit nonempty source allowlist")
    verifier = None
    if mode == "jwt":
        try:
            verifier = TokenVerifier(
                issuer=environ.get("QUALITYRAG_VIDEO_MCP_ISSUER"),
                audience=environ.get("QUALITYRAG_VIDEO_MCP_AUDIENCE"),
                jwks_file=environ.get("QUALITYRAG_VIDEO_MCP_JWKS_FILE"),
                acl_file=environ.get("QUALITYRAG_VIDEO_MCP_ACL_FILE"),
                operator_source_ids=frozenset(ids))
        except (TokenAccessError, OSError) as exc:
            raise RemoteConfigurationError("Invalid JWT configuration") from exc
    return {"secret":secret,"auth_mode":mode,"verifier":verifier,"root":root,"host":host,"source_ids":frozenset(ids),
            "allowed_hosts":allowed_hosts,"origins":origins}


class BearerGate:
    """ASGI gate: checks authentication *before* MCP session initialization.

    Non-MCP requests are also gated; no unauthenticated diagnostic endpoint.
    All credentials and request headers remain out of response bodies.
    """
    def __init__(self, app, *, secret="", origins=(), verifier=None):
        self.app=app
        self.secret=secret.encode("utf-8")
        self.origins=set(origins)
        self.verifier=verifier

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope,receive,send)
        if scope["type"] not in ("http","websocket"):
            return await self.app(scope,receive,send)
        headers={k.lower():v for k,v in scope.get("headers",[])}
        auth=headers.get(b"authorization",b"")
        sources=None
        if self.verifier is None:
            valid=hmac.compare_digest(auth,b"Bearer "+self.secret)
        else:
            valid=False
            if auth.startswith(b"Bearer "):
                try:
                    grant=self.verifier.authorize(auth[7:].decode("ascii"))
                    sources=grant["source_ids"]
                    valid=True
                except (TokenAccessError,UnicodeError):
                    pass
        origin=headers.get(b"origin",b"").decode("utf-8",errors="replace")
        # No browser cross-origin access by default, even with a token.
        valid=valid and (not origin or origin in self.origins)
        if not valid:
            if scope["type"]=="websocket":
                await send({"type":"websocket.close","code":1008})
                return
            await send({"type":"http.response.start","status":401,
                        "headers":[(b"content-type",b"application/json"),
                                   (b"cache-control",b"no-store")]})
            await send({"type":"http.response.body",
                        "body":b'{"error":"unauthorized"}'})
            return
        scoped=REQUEST_SOURCES.set(sources)
        try:
            return await self.app(scope,receive,send)
        finally:
            REQUEST_SOURCES.reset(scoped)


def create_remote_app(environ=None):
    """Build a protected ASGI application on loopback for reverse-proxy staging."""
    settings=_config(os.environ if environ is None else environ)
    try:
        from mcp.server import MCPServer
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as exc:
        raise RemoteConfigurationError("Install the MCP Python v2 SDK") from exc

    server=MCPServer("QualityRAG Video Evidence Read-Only")
    base=settings["root"]
    permitted=settings["source_ids"]
    def authorized_sources():
        if settings["auth_mode"] == "static":
            return permitted
        request_sources=REQUEST_SOURCES.get()
        if request_sources is None:
            raise ValueError("Missing request identity")
        return request_sources

    @server.tool()
    def search_video_evidence(query: str, modality: str="all", limit: int=10) -> dict:
        """Find candidate audio/visual witness excerpts with local timestamps."""
        return search_evidence(base,query,modality=modality,limit=limit,
                               source_ids=authorized_sources())

    @server.tool()
    def research_video_question(query: str, intent: str="cross_modal",
                                limit: int=8, window_ms: int=3000) -> dict:
        """Find timestamped co-observations; not proof of agreement."""
        return research_video_evidence(base,query,intent=intent,
                                       limit=limit,window_ms=window_ms,source_ids=permitted)

    @server.tool()
    def inspect_video_evidence(source_id: str) -> dict:
        """Return reviewed-format evidence candidates; source integrity checked."""
        if source_id not in authorized_sources():
            # Do not disclose whether this source exists for a different user.
            raise ValueError("Source unavailable")
        return read_evidence(base,source_id)

    transport=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=settings["allowed_hosts"],
        allowed_origins=settings["origins"],
    )
    mcp_app=server.streamable_http_app(transport_security=transport, json_response=True, stateless_http=True)
    return BearerGate(mcp_app,secret=settings["secret"],
                      origins=settings["origins"],verifier=settings["verifier"])


def main():
    settings=_config(os.environ)
    import uvicorn
    port=int(os.environ.get("QUALITYRAG_VIDEO_MCP_PORT","8039"))
    if not 1<=port<=65535:
        raise RemoteConfigurationError("Invalid port")
    uvicorn.run(create_remote_app(),host=settings["host"],port=port,
                proxy_headers=False,server_header=False,access_log=False)


if __name__=="__main__":
    main()
