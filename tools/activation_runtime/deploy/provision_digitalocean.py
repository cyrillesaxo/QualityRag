"""Operator-approved DigitalOcean bootstrap: private-by-default, no secrets on VM.

Run --plan with no cloud API credential, or --provision only after a
workflow_dispatch approval and GitHub Actions secret configuration.

The created host deliberately has NO QualityRAG runtime credentials, and
does not start the governance API. Do not advertise it as operational.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from urllib import request, error

API = "https://api.digitalocean.com/v2"
DROPLET_NAME = "qualityrag-governance-isolated"
FIREWALL_NAME = "qualityrag-governance-locked"
TAG = "qualityrag-governance"
REGION = "nyc3"
SIZE = "s-1vcpu-2gb"
IMAGE = "ubuntu-24-04-x64"
EXPECTED_MONTHLY_USD = 12

def validate_ip_range(value: str) -> str:
    parsed = ipaddress.ip_network(value, strict=True)
    if parsed.version != 4 or parsed.prefixlen != 32:
        raise ValueError("ADMIN_IPV4_CIDR must be a single public IPv4 /32")
    if not parsed.network_address.is_global:
        raise ValueError("ADMIN_IPV4_CIDR must be a public IPv4 address")
    return str(parsed)

def validate_fingerprint(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("An existing authorized SSH key fingerprint is required")
    import re
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){15}[0-9a-fA-F]{2}", value):
        raise ValueError("SSH key fingerprint must be an existing 16-byte hex fingerprint")
    return value.lower()

def cloud_init(admin: str) -> str:
    # No cloud-init secrets, no app tokens, and no private signing keys.
    return f"""#cloud-config
package_update: true
package_upgrade: true
packages:
  - ca-certificates
  - git
  - python3-venv
  - python3-pip
  - ufw
runcmd:
  - [ "ufw", "default", "deny", "incoming" ]
  - [ "ufw", "default", "allow", "outgoing" ]
  - [ "ufw", "allow", "from", "{admin}", "to", "any", "port", "22", "proto", "tcp" ]
  - [ "ufw", "--force", "enable" ]
  - [ "useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", "qualityrag-governance" ]
  - [ "mkdir", "-p", "/etc/qualityrag-governance", "/var/lib/qualityrag-governance", "/opt/qualityrag" ]
  - [ "chown", "qualityrag-governance:qualityrag-governance", "/var/lib/qualityrag-governance" ]
  - [ "chmod", "0700", "/var/lib/qualityrag-governance" ]
  - [ "chmod", "0750", "/etc/qualityrag-governance" ]
final_message: "Hardened base host only; QualityRAG API remains unconfigured and stopped."
"""

def firewall_payload(admin: str):
    # No HTTP/TLS ports open until app, hostname and certificates are ready.
    inbound = [
        {"protocol":"tcp","ports":"22","sources":{"addresses":[admin]}},
    ]
    outgoing = [
        {"protocol":"tcp","ports":"all","destinations":{"addresses":["0.0.0.0/0","::/0"]}},
        {"protocol":"udp","ports":"all","destinations":{"addresses":["0.0.0.0/0","::/0"]}},
        {"protocol":"icmp","destinations":{"addresses":["0.0.0.0/0","::/0"]}},
    ]
    return {"name":FIREWALL_NAME, "tags":[TAG],
            "inbound_rules":inbound,"outbound_rules":outgoing}

def droplet_payload(admin: str, key: str):
    return {
        "name":DROPLET_NAME, "region":REGION, "size":SIZE,
        "image":IMAGE, "ssh_keys":[key], "backups":False,
        "monitoring":True,"tags":[TAG],"user_data":cloud_init(admin),
    }

def api(method: str, path: str, token: str, body=None):
    payload=None if body is None else json.dumps(body).encode("utf-8")
    req=request.Request(
        API+path, data=payload, method=method,
        headers={"Authorization":"Bearer "+token,
                 "Accept":"application/json",
                 "Content-Type":"application/json"},
    )
    try:
        with request.urlopen(req,timeout=25) as response:
            return json.load(response)
    except error.HTTPError as exc:
        # Do NOT leak provider response bodies; never print auth headers.
        raise RuntimeError("DigitalOcean API returned HTTP "+str(exc.code)) from None

def provision(admin, fingerprint, token):
    # Prevent accidental double provisioning; resolve any previous partial
    # state before another operator attempt.
    existing=api("GET","/droplets?per_page=200",token).get("droplets",[])
    if any(d.get("name")==DROPLET_NAME for d in existing):
        raise RuntimeError("Named governance Droplet already exists; refusing duplicate")
    ssh=api("GET","/account/keys?per_page=200",token).get("ssh_keys",[])
    if not any(k.get("fingerprint","").lower()==fingerprint for k in ssh):
        raise RuntimeError("SSH key fingerprint is not in the DigitalOcean account")
    tag_path="/tags/"+TAG
    try:
        api("GET",tag_path,token)
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        api("POST","/tags",token,{"name":TAG})
    fw=firewall_payload(admin)
    current=api("GET","/firewalls?per_page=200",token).get("firewalls",[])
    same=[x for x in current if x.get("name")==FIREWALL_NAME]
    if same:
        candidate=same[0]
        if candidate.get("tags")!=fw["tags"] or candidate.get("inbound_rules")!=fw["inbound_rules"]:
            raise RuntimeError("Existing named firewall rules differ; operator reconciliation required")
    else:
        api("POST","/firewalls",token,fw)
    created=api("POST","/droplets",token,droplet_payload(admin,fingerprint))
    droplet=created.get("droplet") or {}
    if not droplet.get("id"):
        raise RuntimeError("Provisioning response did not confirm droplet ID")
    return {"state":"PROVISIONED_UNCONFIGURED","droplet_id":droplet["id"],
            "name":DROPLET_NAME,"monthly_base_price_usd":EXPECTED_MONTHLY_USD,
            "runtime_started":False,"mcp_connected":False,
            "next":"Operator must install trust keys, persistent service and HTTPS host before connecting Netlify"}

def main(argv=None):
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan",action="store_true")
    mode.add_argument("--provision",action="store_true")
    args=parser.parse_args(argv)
    admin=validate_ip_range(os.environ.get("ADMIN_IPV4_CIDR",""))
    fingerprint=validate_fingerprint(os.environ.get("QUALITYRAG_SSH_FINGERPRINT",""))
    if args.plan:
        print(json.dumps({
            "mode":"PLAN_ONLY", "droplet_name":DROPLET_NAME, "region":REGION,
            "size":SIZE,"expected_monthly_base_cost_usd":EXPECTED_MONTHLY_USD,
            "ssh_admin_ip":admin,"ssh_key_fingerprint":fingerprint,
            "monitoring":True,"backups":False,
            "cloud_init":cloud_init(admin),
            "ingress_firewall":firewall_payload(admin)["inbound_rules"],
            "runtime_started":False,
            "warning":"No server created; requires credentials and explicit workflow run",
        },sort_keys=True))
        return
    token=os.environ.get("DIGITALOCEAN_API_TOKEN","")
    if not token:
        raise ValueError("DIGITALOCEAN_API_TOKEN secret not configured")
    print(json.dumps(provision(admin,fingerprint,token),sort_keys=True))

if __name__=="__main__":
    try:
        main()
    except (ValueError,RuntimeError) as exc:
        print("PROVISIONING_BLOCKED: "+str(exc),file=sys.stderr)
        sys.exit(1)
