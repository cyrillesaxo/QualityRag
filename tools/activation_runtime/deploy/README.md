# Private QualityRAG governance API host — operator rollout

**Status (2026-11-08):** DigitalOcean Droplet `617283147` named
`qualityrag-governance-isolated` exists, active, IP `159.65.251.50`.
The API has **not** been installed/started or connected to Netlify.
The older APX customer-discovery host is a distinct VM and must not be touched.

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


## Unified deployment path (main branch)

The canonical provisioning and installation artifacts now live together under
`tools/activation_runtime/deploy/` in the default branch.

**Order matters:** review and approve a dedicated SSH key and a public
administrator IPv4 /32, then run the plan-only
`.github/workflows/governance-provision.yml`. A paid VM may only be created
through the explicit, cost-confirmed workflow action. It is *not* created
by checking out this branch, merging a PR, or running the tests.

After the VM is created, an authorized operator must validate cloud-init
completion, patching, firewall rules, SSH access, locked service-user
permissions, and local application verification before separately
installing the signed API, binding the Caddy hostname, and enabling the
Netlify upstream secret. The Python signer private key stays off the VM.

**Do not replace the read-only governance token with the broad
`bootstrap.py` research token.** Use the offline
`issue_service_access.py` utility only after establishing host-managed
Ed25519 issuance keys, tenant scope, key lifecycle and an approved secure
secret transfer. An issued token expires within one hour and has only
the `read` scope. Application client OAuth requires its own trusted
identity provider and does not come from this script.

No startup-time SSH step, user-data provisioner, or GitHub workflow may
silently mark this app as externally connected. The acceptance gate is
a real HTTPS `/api/policy/test` and a Netlify `tools/call` with signed
tenant identity and observed verdicts, plus cross-tenant denial checks.


## Stage the already-created isolated server (operator action)

The DigitalOcean connector cannot execute commands through SSH. Use PuTTY
with your locally held `.ppk` private key or the provider's Droplet Console.
Never paste the PuTTY private key or its passphrase into chat, GitHub, or CI.

- Target server: `159.65.251.50` (`qualityrag-governance-isolated`).
- SSH port: 22. The provider/host firewall is configured for the administrator
  public IP recorded during provisioning; reconnect/update the approved IP
  using provider console if your mobile connection changes.
- In PuTTY: Host Name `root@159.65.251.50`, port `22`, connection SSH;
  set **Connection > SSH > Auth > Credentials > Private key file** to the
  QualityRAG `.ppk` saved on your computer.
- After login, run the following, and check the repository commit before
  installation:
  ```sh
  sudo apt-get update
  sudo apt-get install -y git
  git clone --depth=1 https://github.com/cyrillesaxo/QualityRag.git /tmp/qualityrag-stage
  cd /tmp/qualityrag-stage
  git rev-parse HEAD
  sudo bash tools/activation_runtime/deploy/prepare_host.sh "$(git rev-parse HEAD)"
  ```
  An operator who has reviewed a specific release should check out its
  **40-character commit** rather than relying on a moving default branch.
- Successful output ends with `QUALITYRAG_HOST_PREPARED_NOT_STARTED` and
  `QUALITYRAG_LOCAL_EVIDENCE_SMOKE_PASSED ADMIT INCONCLUSIVE`. Both
  are **local, fixture-based** checks. They do not authorize production use.
- The installer rejects non-Ubuntu 24.04 systems, wrong host names, existing
  authority keys, an existing running service, and nonempty checkouts.
  It fetches precisely the approved commit, runs a real Python governance
  fixture, installs the locked-down systemd unit, and leaves it disabled.
- Next: provision root-managed **public** verifier keys and the offline
  issuer-managed short-lived *read-only* signed gateway token. Then configure
  an operator-owned domain's DNS A record to `159.65.251.50`, install
  Caddy, enable inbound ports 80/443 at **both** UFW and DigitalOcean cloud
  firewall, verify TLS, and enable the service only after trust validation.
  `/api/policy/test` must return real verdicts before Netlify is connected.
  Never open port 8769 to the public internet.

### Access and configuration caveats

The provisioned SSH key is an RSA 2048 key generated with PuTTY, not the
Ed25519 **governance attestation key**. SSH access is distinct from runtime
authorization. The private SSH key stays on the operator's machine.
The service issuer signing key stays off the server and Netlify.

Production operator work is not finished merely because the Droplet is active:
verify persistent storage, root and sudo access, firewall attachment, patch
level, service isolation, signed tenant scoping, expiry/rotation, external TLS,
backups, monitoring and denial of unsigned requests.

