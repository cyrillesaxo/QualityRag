# Connect QualityRAG Video MCP to ChatGPT

**Connection state:** NOT CONNECTED. This document is an operator runbook; the
existing local and remote MCP servers are repository implementations, not an
installed ChatGPT plugin.

The existing remote read-only server lives at
`tools/semantic_store/video_mcp_remote.py`. It exposes:

| MCP tool | Capability |
| --- | --- |
| `search_video_evidence` | Source-scoped retrieval of timestamped audio/video witnesses |
| `research_video_question` | Group source-scoped nearby cross-modal witnesses; no truth inference |
| `inspect_video_evidence` | Inspect evidence for an authorized indexed source |

The local stdio server (`video_mcp.py`) also offers operator-only ingestion
and local hybrid search; these tools are **not** exposed on the remote server.
Do not present the remote connection as enabling social-platform crawling,
automatic video ingestion, or production-grade visual verification.

## Readiness gate

- [ ] A **real** HTTPS hostname and `/mcp` route have been provisioned; do
  not substitute the `example.com` placeholders from the runbook.
- [ ] The service has passed the external deployment smoke and cross-identity
  isolation checks. No known public endpoint is provisioned by this PR.
- [ ] OAuth authorization server with compatible discovery, authorization-code
  + PKCE, consent and refresh-token support is deployed by an external IdP.
  It issues RS256 access JWTs with `video:read` scope and an audience exactly
  equal to `https://YOUR_DOMAIN/mcp`. Validate token rotation/revocation.
- [ ] JWKS public keys and subject-to-source ACLs are managed securely, and
  the source allowlist contains only rights-cleared authorized media.
- [ ] Initial corpus has at least one actual indexed video and hash-verified
  timestamped witnesses; no synthetic fixtures are presented as real footage.
- [ ] A ChatGPT account/workspace authorized to add custom MCP servers is
  available in the **web** client.

## ChatGPT connection

Follow the most recent official OpenAI instructions (features/plan eligibility
change): https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

On supported accounts/workspaces:

1. Open **Plugins**, choose **+ → Add custom MCP server**.
2. Name it **QualityRAG Video Evidence**; description: **Read-only,
   source-cited audio/visual evidence search with uncertainty controls**.
3. Choose HTTPS URL `https://YOUR_DOMAIN/mcp`, or the supported Secure MCP
   Tunnel configuration for a private server if your account offers it.
4. Choose OAuth with the trusted external provider configured in the server;
   complete authentication and consent. Do not paste access tokens into chat
   or hardcode bearer tokens into the server registration.
5. Review the permission warning and create the plugin. Verify the discovered
   tools match the three read-only operations above.
6. Install/enable the plugin as prompted. Start a new conversation, type
   `@` and select **QualityRAG Video Evidence**.
7. Try: “Search authorized video evidence for wheelchair safety checks,
   cite exact timestamps, distinguish visual from spoken evidence, and
   explicitly label unresolved constraints.”
8. Confirm different test principals cannot inspect each other's source IDs.

If the **Add custom MCP server** menu is absent, verify the current plan and
workspace administrator permissions using OpenAI's documentation. Do not infer
that the MCP is connected just because the repo contains server code.

## Suggested acceptance payload

A response is ready for a live pilot only when it includes a recognized
source ID, indexed modality, start/end timestamps, source SHA-256, candidate
observation, and uncertainty statement. Where rights permit public citations,
include a valid source page link; otherwise no public URL should be emitted.
A transcript-only observation must never be described as visually confirmed.

## In case of failure

- Discovery/authorization errors: verify DNS/TLS, OAuth protected-resource
  metadata, issuer discovery, matching audience and issued scopes.
- HTTP 401: check actual resource audience, token expiration, issuer and
  `video:read`; do not disable checks to force connection.
- Empty evidence: verify authorized IDs, catalog fingerprints and actual
  ingestion rather than modifying ACLs blindly.
- Tool scan mismatch: review the remote tool registry; do not expose local
  media ingestion or model execution to chat users as a shortcut.

**Boundary:** Connecting the ChatGPT app requires an explicit user/admin
installation and authorization step. This repository cannot complete it on
the user's behalf. No direct ChatGPT connection has been confirmed.
