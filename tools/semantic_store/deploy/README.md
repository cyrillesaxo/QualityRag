# Video MCP — private single-host deployment checklist

**Not an automatic deployment.** This runbook uses a pre-existing Ubuntu host,
an approved DNS name, a trusted external OAuth issuer and authorized video files.
Do not reuse a host running another customer workload without reviewing
isolation, port ownership, memory pressure and impact on the existing service.

## Preconditions

- A dedicated Ubuntu 24.04 VM with ssh/sudo access and firewall restricted to
  inbound 22 (admin IP only), 80 (ACME challenge) and 443; **8039 must not be
  publicly accessible**. Pin package versions and run vulnerability checks.
- A DNS A/AAAA record for your domain. A valid external OAuth issuer supporting
  authorization code/PKCE, discovery and JWT access tokens for audience equal
  to `https://YOUR_DOMAIN/mcp`. Configure issuer and client consent separately.
- Consent/rights-cleared video evidence already indexed and registered. This
  server exposes search, not video ingestion or GPU model inference.

## Provision (administrator actions)

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin qualityrag-video
sudo mkdir -p /etc/qualityrag /srv/qualityrag-video/media /opt/qualityrag
sudo chown -R qualityrag-video:qualityrag-video /srv/qualityrag-video/media
# Deploy a reviewed repository checkout into /opt/qualityrag; keep the service
# user's permissions read-only for source and executable code.
sudo python3 -m venv /opt/qualityrag/.venv
sudo /opt/qualityrag/.venv/bin/pip install -r /opt/qualityrag/tools/semantic_store/deploy/requirements-remote.txt
sudo install -m 0640 -o root -g qualityrag-video \
  /opt/qualityrag/tools/semantic_store/deploy/video-mcp.env.example \
  /etc/qualityrag/video-mcp.env
```

Fill every env placeholder with real site-specific configuration, set
`QUALITYRAG_VIDEO_MCP_AUTH_MODE=jwt`, and provide
`QUALITYRAG_VIDEO_MCP_ALLOWED_SOURCE_IDS` with the exact rights-cleared
source IDs. Populate `/etc/qualityrag/trusted-jwks.json` with **public**
keys retrieved securely from the configured issuer, and
`/etc/qualityrag/video-access.json` with subject-to-source ACL mapping.
Protect these files for root and the dedicated service group; never commit
tokens, keys, private source metadata or customer video to GitHub.

```sh
sudo install -m 0644 /opt/qualityrag/tools/semantic_store/deploy/qualityrag-video-mcp.service \
  /etc/systemd/system/qualityrag-video-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now qualityrag-video-mcp.service
sudo systemctl is-active qualityrag-video-mcp.service
# Local server only: use a bearer token to check POST /mcp.
```

Install Caddy from its official packages, replace
`video-mcp.example.com` in `deploy/Caddyfile.example` with the domain you
control, validate the configuration with `caddy validate`, and reload Caddy.
Caddy terminates TLS and proxies to loopback port 8039. The MCP runtime also
validates the public Host header against `QUALITYRAG_VIDEO_MCP_ALLOWED_HOSTS`.
Verify neither the firewall nor the hosting provider exposes port 8039.

**The Caddy template is not a full production security boundary.** Add traffic
rate limits, certificate/patch monitoring, centralized non-sensitive audit logs
and incident response controls in the actual deployment environment.

## End-to-end smoke

After an external identity provider has issued a valid scoped, signed JWT,
supply it only through the operator shell environment. Never paste the token
into chat or source control.

```sh
export QUALITYRAG_VIDEO_MCP_RESOURCE_URL="https://YOUR_DOMAIN/mcp"
export QUALITYRAG_VIDEO_MCP_SMOKE_TOKEN="$(YOUR_SECURE_TOKEN_RETRIEVAL_COMMAND)"
PYTHONPATH=tools/semantic_store python \
  tools/semantic_store/deploy/smoke_https.py
unset QUALITYRAG_VIDEO_MCP_SMOKE_TOKEN
```

The smoke validates public protected-resource discovery, an unauthenticated
401 and WWW-Authenticate challenge, authenticated MCP tools/list and a strict
read-only tool set. It **rejects redirects** so credentials are not forwarded.
To complete acceptance, run per-user checks against two authorized tenant
test accounts and confirm each sees only its own indexed evidence.

## Deployment gate

Do not announce ChatGPT usability or publish the endpoint until all these hold:
1. Dedicated workflow CI and SDK CI green on the deployed commit.
2. Live HTTPS identity-provider authorization-code/PKCE and token validation
   accepted for the precise audience and scope.
3. Cross-account access-control checks against real deployed service pass.
4. Hosting security, quotas, patching, logging, backup/retention and consent
   reviewed, including data deletion and incident-response procedures.
5. ChatGPT-compatible connector installed/connected by the user, and one
   actual timestamp-cited query works against authorized video footage.

These templates do not create infrastructure, modify existing VMs, grant video
rights or connect an app to ChatGPT.
