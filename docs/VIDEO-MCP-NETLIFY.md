# Netlify as the public QualityRAG MCP endpoint

The existing Netlify project **quality-rag** can host a narrowly scoped
stateless HTTP gateway. This lets us use an HTTPS public Netlify URL without
moving the Python multimodal inference engine or its indexed video corpus
into serverless functions.

## Endpoints after a successful deploy

- `https://quality-rag.netlify.app/mcp` — Streamable HTTP POST gateway.
- `https://quality-rag.netlify.app/.well-known/oauth-protected-resource/mcp`
  — public OAuth protected-resource metadata (GET).
- `https://quality-rag.netlify.app/.well-known/oauth-protected-resource`
  — alternative discovery route (GET).

**These routes are not live merely because their code is committed.** Netlify
must build/deploy the branch with the functions, then an actual upstream MCP
must be reachable. Without `QUALITYRAG_VIDEO_MCP_UPSTREAM_URL`, requests
fail closed with HTTP 503 rather than returning synthetic evidence.

## Architecture

```
ChatGPT custom MCP connection (explicit user/admin approval)
        |
        | HTTPS /mcp, externally issued audience-bound OAuth token
        v
Netlify quality-rag project: stateless HTTP gateway
        |
        | HTTPS, bearer token forwarded only to fixed operator-configured host
        v
Dedicated QualityRAG Python HTTP MCP resource server
        |
        | JWT signature/issuer/audience/scope + user-to-source ACL validation
        v
Rights-cleared local video evidence catalog / governed retrieval
```

Netlify only forwards MCP JSON requests and resource discovery.
Authentication, source-level authorization, frame evidence, ASR and storage
remain at the dedicated upstream Python service. No video uploads, model
workers, original media, secrets or user data are bundled into the Netlify
functions. No subdomain DNS change or paid VM is performed by this commit.

## Netlify environment

For the existing Netlify project `quality-rag`, after the independently
secured Python server is deployed, set:

```
QUALITYRAG_VIDEO_MCP_UPSTREAM_URL=https://private-qualityrag-host.example/mcp
```

Replace the placeholder with a **real, trusted, publicly TLS-reachable,
operator-controlled upstream**. The endpoint must be configured to advertise
the actual public Netlify URL in its protected resource metadata:

```
QUALITYRAG_VIDEO_MCP_RESOURCE_URL=https://quality-rag.netlify.app/mcp
QUALITYRAG_VIDEO_MCP_AUDIENCE=https://quality-rag.netlify.app/mcp
QUALITYRAG_VIDEO_MCP_ALLOWED_HOSTS=private-qualityrag-host.example
```

These three configuration values belong **on the Python upstream**, not
on the Netlify site. The external IdP must issue JWT access tokens for the
public Netlify audience URI, and the upstream must continue enforcing
principal-to-video ACLs. Configure its Host allowlist to the **upstream**
hostname because the gateway uses normal upstream TLS and Host handling.

Optional Netlify variable:
`QUALITYRAG_VIDEO_MCP_ALLOWED_ORIGIN=https://your-web-app.example`.
With no configured origin, browser-origin requests are denied while native
server-to-server MCP clients can connect. This does not replace CSRF/identity
checks in upstream or grant browser CORS permission.

The gateway does not send credentials to third-party redirects and rejects
non-HTTPS or private-IP literal upstream configurations. Do not configure
a redirecting backend or any untrusted DNS-controlled domain; a production
private tunnel is safer than an internet-exposed Python worker.

## Deploy and verify

The operator can deploy this branch to a **Netlify deploy preview** and verify
function routing before promoting to production. Do not risk the existing
published website to test without a preview.

```sh
node --test netlify/tests/video-mcp-gateway.test.mjs
```

After the upstream is ready, test:

- Without `Authorization`: POST `/mcp` responds HTTP 401.
- With a valid JWT: MCP initialization, `tools/list`, and a source-scoped
  search return evidence from the permitted indexed media.
- With an expired or wrong-audience JWT: HTTP 401.
- The public `.well-known` metadata advertises the **Netlify public**
  HTTPS URI and trusted external IdP.
- A source ID belonging to another principal must not be inspectable.
- No video source URLs are emitted without declared citation permission.
- A missing upstream produces HTTP 503 instead of a false successful answer.
- The only remote tool names remain `search_video_evidence`,
  `research_video_question`, and `inspect_video_evidence`.

**ChatGPT connection:** once the HTTPS endpoint is working, go to
ChatGPT Plugins → Add custom MCP server (if available to your account),
enter `https://quality-rag.netlify.app/mcp`, complete OAuth, then approve
the custom connector. The user/admin must explicitly connect the app.

### Netlify limitations

Netlify Functions are stateless and time-limited. The gateway caps request
and response payloads and enforces a timeout. This works with the Python
server's stateless JSON MCP transport. It does **not** support continuous
SSE subscriptions or long-running video analysis; those remain separate,
asynchronous ingestion tasks on the Python host.

The existing QualityRAG Netlify site is public; deploying a function must
not imply that previously published content is private. Authentication and
authorization are mandatory for video evidence.
