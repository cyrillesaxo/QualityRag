"""Operator-run HTTPS staging smoke. Never prints bearer tokens.

Requires a real deployed HTTPS endpoint, issuer-issued video:read JWT, and a
server-side source allowlist. This test is intentionally NOT executed by CI.
"""
from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("HTTPS smoke rejects redirects to avoid credential forwarding")


def smoke(url, token):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.path != "/mcp" or
            parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("Set a canonical HTTPS URL ending in /mcp")
    if not isinstance(token,str) or not token or "\r" in token or "\n" in token:
        raise ValueError("An externally issued scoped access token is required")
    open_url=build_opener(NoRedirect()).open
    base = url.removesuffix("/mcp")
    metadata_url = base+"/.well-known/oauth-protected-resource/mcp"
    with open_url(Request(metadata_url,headers={"Accept":"application/json"}),timeout=20) as response:
        metadata=json.loads(response.read(100000))
    if metadata.get("resource") != url or not metadata.get("authorization_servers"):
        raise RuntimeError("Protected-resource metadata is invalid")
    payload={"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
    body=json.dumps(payload).encode()
    headers={"Accept":"application/json, text/event-stream",
             "Content-Type":"application/json"}
    try:
        open_url(Request(url,data=body,headers=headers,method="POST"),timeout=20)
    except HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError("Unauthenticated call must yield HTTP 401") from None
        challenge=exc.headers.get("WWW-Authenticate","")
        if metadata_url not in challenge:
            raise RuntimeError("Missing protected-resource discovery challenge")
    else:
        raise RuntimeError("Unauthenticated call unexpectedly succeeded")
    headers["Authorization"]="Bearer "+token
    with open_url(Request(url,data=body,headers=headers,method="POST"),timeout=20) as response:
        if response.status != 200 or "application/json" not in response.headers.get("Content-Type",""):
            raise RuntimeError("Authenticated MCP tools/list returned unexpected response")
        result=json.loads(response.read(200000))
    names={entry["name"] for entry in result["result"]["tools"]}
    expected={"search_video_evidence","research_video_question","inspect_video_evidence"}
    if names != expected:
        raise RuntimeError("Unexpected remotely exposed MCP tools")
    return {"status":"STAGING_PROTOCOL_PASS","authenticated":True,
            "resource_url":url,"tools":sorted(names),
            "access_control":"Bearer validation only; inspect source-scoping separately"}


if __name__=="__main__":
    endpoint=os.environ.get("QUALITYRAG_VIDEO_MCP_RESOURCE_URL","")
    token=os.environ.get("QUALITYRAG_VIDEO_MCP_SMOKE_TOKEN","")
    try:
        print(json.dumps(smoke(endpoint,token),indent=2))
    except Exception as exc:
        # Do not include token or Authorization headers in error messages.
        print("STAGING_PROTOCOL_FAIL: "+type(exc).__name__,file=sys.stderr)
        sys.exit(1)
