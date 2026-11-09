#!/usr/bin/env bash
# Stage public HTTPS with Caddy, but DO NOT expose the QualityRAG application.
# Run on the isolated Droplet as root, after allowing TCP 80/443 in
# DigitalOcean's cloud firewall for the qualityrag-governance tag.
set -Eeuo pipefail
umask 077
fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || fail "Run as root"
[[ "$(hostname)" == "qualityrag-governance-isolated" ]] || fail "Wrong host"
[[ "$(. /etc/os-release; echo "$ID:$VERSION_ID")" == "ubuntu:24.04" ]] || fail "Expected Ubuntu 24.04"
[[ -f /etc/systemd/system/qualityrag-governance.service ]] || fail "Install governance runtime before HTTPS"
! systemctl is-active --quiet qualityrag-governance.service ||
  fail "Governance engine must be inactive until signed access is installed"
[[ ! -f /etc/qualityrag-governance/authority.json ]] ||
  fail "Existing authority is present; review live service before changing HTTPS"
[[ ! -e /etc/caddy/Caddyfile ]] ||
  fail "Caddyfile already exists; refuse to overwrite other sites"

DOMAIN=governance.dodollc.net
EXPECTED_IP=159.65.251.50
ACTUAL_IPS="$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | sort -u)"
[[ "$ACTUAL_IPS" == "$EXPECTED_IP" ]] ||
  fail "DNS not resolved solely to approved DigitalOcean address: $ACTUAL_IPS"
# Refuse on systems with existing public web listeners; do not displace services.
if ss -ltn '( sport = :80 or sport = :443 )' | grep -Eq 'LISTEN'; then
  fail "HTTP/HTTPS listener already present; review before enabling Caddy"
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends caddy ufw
install -d -o root -g root -m 0755 /etc/caddy
cat > /etc/caddy/Caddyfile <<'CADDY'
{
    email cyrille.eloundou@dodollc.net
}
governance.dodollc.net {
    # TLS certificate via automatic ACME, with normal public certificate.
    # There is intentionally NO reverse proxy while authority is unconfigured.
    @api path /api/*
    respond @api "QualityRAG backend not configured" 503
    respond "Not Found" 404
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy no-referrer
        Cache-Control no-store
        Strict-Transport-Security "max-age=31536000"
    }
}
CADDY
chown root:root /etc/caddy/Caddyfile
chmod 0644 /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
ufw allow 80/tcp
ufw allow 443/tcp
systemctl enable --now caddy
systemctl reload caddy

printf '%s\n' "QUALITYRAG_HTTPS_STAGE_STARTED_APPLICATION_BLOCKED"
printf '%s\n' "Verify from outside: curl -fsSI https://governance.dodollc.net/ should return HTTP 404"
printf '%s\n' "Verify /api/* returns 503 before connecting real signed runtime"
printf '%s\n' "Never open Python port 8769 to the internet"
