#!/usr/bin/env bash
# Prepare a new isolated Ubuntu 24.04 DigitalOcean host for the real
# QualityRAG governance API. The API is NOT enabled by this script.
# Usage (root): bash prepare_host.sh <reviewed-40-hex-git-commit>
set -Eeuo pipefail
umask 077

fail() { printf 'BLOCKED: %s\n' "$*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root on the dedicated QualityRAG host."
[[ "$#" -eq 1 ]] || fail "Exactly one reviewed Git commit SHA is required."
COMMIT="$1"
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "A full 40-character lowercase commit SHA is required."
[[ "$( . /etc/os-release; echo "$ID:$VERSION_ID" )" == "ubuntu:24.04" ]] ||
  fail "Only Ubuntu 24.04 is supported."
[[ "$(hostname)" == "qualityrag-governance-isolated" ]] ||
  fail "Wrong host: expected qualityrag-governance-isolated."
[[ ! -e /etc/qualityrag-governance/authority.json ]] ||
  fail "Host already has governance authorities; refuse implicit replacement."
if systemctl is-active --quiet qualityrag-governance.service 2>/dev/null; then
  fail "Governance service is already running; refuse implicit replacement."
fi
if [[ -d /opt/qualityrag && -n "$(ls -A /opt/qualityrag)" ]]; then
  fail "A prior source checkout exists; do not overwrite a deployed application."
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y install --no-install-recommends \
  ca-certificates git python3 python3-venv python3-pip

if ! id -u qualityrag-governance >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin qualityrag-governance
fi

install -d -o root -g root -m 0755 /opt/qualityrag
install -d -o root -g qualityrag-governance -m 0750 /etc/qualityrag-governance
install -d -o qualityrag-governance -g qualityrag-governance -m 0700 /var/lib/qualityrag-governance

# Fetch the exact reviewed commit, never an implicitly moving branch.
git -C /opt/qualityrag init -q
git -C /opt/qualityrag remote add origin https://github.com/cyrillesaxo/QualityRag.git
git -C /opt/qualityrag fetch --depth 1 origin "$COMMIT"
[[ "$(git -C /opt/qualityrag rev-parse FETCH_HEAD)" == "$COMMIT" ]] ||
  fail "Fetched commit does not match the approved version."
git -C /opt/qualityrag checkout --detach -q "$COMMIT"
[[ "$(git -C /opt/qualityrag rev-parse HEAD)" == "$COMMIT" ]] ||
  fail "Checkout is not the approved commit."

python3 -m venv /opt/qualityrag/.venv
/opt/qualityrag/.venv/bin/python -m pip install \
  --disable-pip-version-check --no-input \
  -r /opt/qualityrag/tools/activation_runtime/deploy/requirements-governance.txt

# Import the real authenticated runtime and execute the deterministic PackSpec
# reference witness. This is a local smoke test, not independent correctness
# evidence or approval to open the service to the public.
(
  cd /opt/qualityrag
  PYTHONDONTWRITEBYTECODE=1 /opt/qualityrag/.venv/bin/python - <<'PY'
from tools.activation_runtime.service import Application, server
from tools.activation_runtime.governance import example, policy_test

fixture = example()
kwargs = dict(pack=fixture["pack"], documents=fixture["documents"],
              as_of=fixture["as_of"])
full = policy_test(retrieved=fixture["retrieved"], **kwargs)
limited = policy_test(
    retrieved=["ops-7.3", "incident-summary", "runbook-restart", "ops-mirror-7.3"],
    **kwargs)
assert full["verdict"] == "ADMIT", full.get("verdict")
assert limited["verdict"] == "INCONCLUSIVE", limited.get("verdict")
print("QUALITYRAG_LOCAL_EVIDENCE_SMOKE_PASSED ADMIT INCONCLUSIVE")
PY
)

install -o root -g root -m 0644 \
  /opt/qualityrag/tools/activation_runtime/deploy/qualityrag-governance.service \
  /etc/systemd/system/qualityrag-governance.service
systemctl daemon-reload
# Explicitly disabled: start only after trusted public verification keys
# and issuer-managed credentials have been configured by the operator.
systemctl disable --now qualityrag-governance.service >/dev/null 2>&1 || true
test ! -e /etc/qualityrag-governance/authority.json ||
  fail "Unexpected governance authority file present."

printf '%s\n' "QUALITYRAG_HOST_PREPARED_NOT_STARTED"
printf 'commit=%s\n' "$COMMIT"
printf '%s\n' "remaining=operator-owned verification keys, DNS/TLS, upstream bearer, Netlify secrets, live evidence smoke"
