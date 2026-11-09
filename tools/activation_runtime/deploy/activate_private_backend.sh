#!/usr/bin/env bash
# Install only PUBLIC verifier keys and start the loopback-only API.
# Keep public Caddy /api/* response at 503 until separately tested.
# Usage as root: bash activate_private_backend.sh /root/authority.json
set -Eeuo pipefail
umask 077

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" -eq 0 ]] || fail "root required"
[[ "$(hostname)" == "qualityrag-governance-isolated" ]] || fail "wrong hostname"
[[ "$(. /etc/os-release; echo "$ID:$VERSION_ID")" == "ubuntu:24.04" ]] || fail "Ubuntu 24.04 required"
[[ "$#" -eq 1 ]] || fail "provide public authority.json file path"
[[ -f "$1" && ! -L "$1" ]] || fail "public authority JSON must be a regular file"
[[ ! -e /etc/qualityrag-governance/authority.json ]] || fail "authority already installed; refuse overwrite"
! systemctl is-active --quiet qualityrag-governance.service || fail "service already running"
[[ -x /opt/qualityrag/.venv/bin/python ]] || fail "runtime not installed"
[[ -f /etc/systemd/system/qualityrag-governance.service ]] || fail "service unit missing"
[[ "$(systemctl is-active caddy.service)" == "active" ]] || fail "HTTPS Caddy must be active"
[[ -f /etc/caddy/Caddyfile ]] || fail "Caddyfile missing"
grep -Fq 'respond @api "QualityRAG backend not configured" 503' /etc/caddy/Caddyfile ||
    fail "public API must still be blocked by Caddy"

AUTH="$1"
/opt/qualityrag/.venv/bin/python - "$AUTH" <<'PY'
import base64,json,sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
f=Path(sys.argv[1]);data=f.read_bytes()
if len(data)>8192:raise ValueError("Authority file too large")
obj=json.loads(data)
if set(obj)!={"access","release","minimum_sequence","proposal_principals"}:raise ValueError("Unexpected authority keys")
if obj["minimum_sequence"]!=1 or obj["proposal_principals"]!=[]:raise ValueError("Unexpected authority policy")
seen=set()
for purpose in ("access","release"):
    group=obj[purpose]
    if type(group)!=dict or len(group)!=1:raise ValueError("One verification key per purpose required")
    for kid,raw in group.items():
        if not isinstance(kid,str) or not isinstance(raw,str):raise ValueError("Bad public key entry")
        key=base64.b64decode(raw,validate=True)
        if len(key)!=32 or key in seen:raise ValueError("Invalid or reused Ed25519 key")
        Ed25519PublicKey.from_public_bytes(key)
        seen.add(key)
print("QUALITYRAG_PUBLIC_AUTHORITY_VALIDATED")
PY

install -o root -g qualityrag-governance -m 0640 "$AUTH" /etc/qualityrag-governance/authority.json
systemctl daemon-reload
systemctl enable --now qualityrag-governance.service

# Test no anonymous access (403). Valid signed requests must be tested
# independently with the OFFLINE signing key before opening the Caddy proxy.
for _ in $(seq 1 15); do
    if ss -ltn | grep -Eq '127\.0\.0\.1:8769[[:space:]]'; then break; fi
    sleep 1
done
if ! ss -ltn | grep -Eq '127\.0\.0\.1:8769[[:space:]]'; then
    systemctl disable --now qualityrag-governance.service
    fail "No 127.0.0.1:8769 listener; check systemctl status/journal"
fi
if ss -ltn | grep -Eq '(^|[[:space:]])(0\.0\.0\.0|\*|\[::\]):8769[[:space:]]'; then
    systemctl disable --now qualityrag-governance.service
    fail "Unexpected public Python listener"
fi

status=$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
  -X POST -H 'Content-Type: application/json' --data '{}' \
  http://127.0.0.1:8769/api/status) || {
    systemctl disable --now qualityrag-governance.service
    fail "Local unauthenticated request failed unexpectedly"
  }
if [[ "$status" != "403" ]]; then
    systemctl disable --now qualityrag-governance.service
    fail "Expected 403 for unsigned request; got $status"
fi
printf '%s\n' "QUALITYRAG_PRIVATE_SERVICE_STARTED_UNSIGNED_DENIED"
printf '%s\n' "CADDY_PUBLIC_API_REMAINS_BLOCKED"
printf '%s\n' "NEXT=verify signed token via private SSH tunnel, then publish reverse proxy"
