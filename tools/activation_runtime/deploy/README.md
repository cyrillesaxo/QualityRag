# Private QualityRAG governance API host — operator rollout

**Status: not deployed by this repository package.** The only observed DigitalOcean
VM belongs to the APX customer-discovery workflow; do not modify or reuse it
without workload isolation and resource-ownership review.

This package runs the **existing** QualityRAG Python
`tools.activation_runtime.cli serve` application, using a fixed
loopback-only port and a dedicated non-login account. Caddy forwards only
`/api/*` from a separate HTTPS hostname. No public Studio UI and no direct
port 8769 access.

## Dependencies

A dedicated Ubuntu 24.04 host with persistent disk, restricted admin access,
DNS and a properly monitored Caddy installation. This workflow requires
durable `/var/lib/qualityrag-governance` storage because the Semantic Garden
uses SQLite and tenant-derived artifact folders. It is **not** an appropriate
implementation for ephemeral Netlify Functions.

### Provisioning checklist

1. Create the dedicated VM/container host and configure its firewall. Inbound
   22 from operator IP only, 80/443 for Caddy; **deny public 8769**. Do not
   grant outbound access to arbitrary video sources or identity endpoints.
2. Create a non-login account and directories:
   ```sh
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin qualityrag-governance
   sudo mkdir -p /opt/qualityrag /etc/qualityrag-governance /var/lib/qualityrag-governance
   sudo chown qualityrag-governance:qualityrag-governance /var/lib/qualityrag-governance
   sudo chmod 0700 /var/lib/qualityrag-governance
   sudo chown root:qualityrag-governance /etc/qualityrag-governance
   sudo chmod 0750 /etc/qualityrag-governance
   ```
3. Deploy a reviewed and commit-pinned QualityRAG checkout under
   `/opt/qualityrag`; do **not** grant the service user write access to code.
   Create a Python 3.12 virtualenv there and install audited packages from
   `requirements-governance.txt` (plus required transitive dependencies).
4. Provision `/etc/qualityrag-governance/authority.json` with **public**
   Ed25519 access and release verification keys, an explicit
   `minimum_sequence`, and approved proposal-principal allowlist. Example
   skeleton (not valid until keys are replaced):
   ```json
   {
     "access": {"production-access-1": "BASE64_RAW_ED25519_PUBLIC_KEY"},
     "release": {"production-release-1": "BASE64_RAW_ED25519_PUBLIC_KEY"},
     "minimum_sequence": 1,
     "proposal_principals": []
   }
   ```
   Own the trust file as root:qualityrag-governance with mode 0640. Never
   place an access **private** signing key on the backend or in Netlify.
5. Provision a separately signed, **read-scope-only**, short-lived access
   envelope issued by the authorized signer. Set it as Netlify's secret runtime
   variable `QUALITYRAG_API_TOKEN_JSON`. The signing private key remains
   offline; implement rotation/revocation and minimum sequence policy. A
   short-lived token **will expire**, so renew it before expiry rather than
   disabling time checks. The local `bootstrap.py` creates research-only
   credentials and is **not** a production identity-provider enrollment flow.
6. Install `qualityrag-governance.service` into systemd and enable it.
   Set Caddy's hostname and load the restricted `Caddyfile.example` reverse
   proxy; verify automatic HTTPS, patches, logging, TLS and egress policy.
7. Configure **the separate Netlify project `qualityrag-mcp`** with
   `QUALITYRAG_API_ENDPOINT=https://YOUR_GOVERNANCE_HOST`, the signed
   `QUALITYRAG_API_TOKEN_JSON`, and `QUALITYRAG_MCP_ACCESS_TOKEN` (a
   strong, independently generated client-side bearer secret). All three must
   be secret where applicable and scoped to Functions/production. Do not
   commit or paste their values into chat/CI.
8. Rebuild and deploy Netlify; use a live test token to invoke
   `policy_test` through the **actual** public MCP and check that a missing
   requirement yields `INCONCLUSIVE`. Verify garden tenant scoping and
   signatures. Rotate all staging tokens before connecting users.

## Boundaries / go-no-go

- **No deploy without authenticated HTTPS backend and least-privilege keys.**
  The adapter currently accepts a shared static client bearer; that is not
  end-user OAuth, not per-ChatGPT-user identity, and not safe to advertise as
  a multi-tenant user-facing app.
- The Python backend authenticates the **Netlify service identity**. To
  represent multiple customers with individual source access, the adapter
  must independently validate user-bound OAuth tokens and issue/delegate
  corresponding signed tenant credentials; do not reuse a shared operator
  tenant across arbitrary external clients.
- Key material and authorization policy must be managed independently of
  the repository and reviewed before production use.
- Monitoring should include HTTP statuses, bounded latency, token-expiry
  alerts, SQLite backups and tested restoration, disk usage, security updates,
  non-sensitive audit telemetry and isolation checks.
- The local CI bridge in PR #90 verifies real PackSpec calls with test keys.
  It does NOT demonstrate a live deployed Python backend, external OAuth or
  authorized production evidence.

## Netlify endpoint

When all gates pass, the Netlify public MCP is
`https://qualityrag-mcp.netlify.app/mcp` and the Python HTTPS API
origin is passed via `QUALITYRAG_API_ENDPOINT`. Caddy must make only
`/api/*` available on the backend. The Python server stays on loopback.

This package leaves the `quality-rag` (PackSpec website) and separate video
MCP integration untouched.
