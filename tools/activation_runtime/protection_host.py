"""Service host for ADR-0002 protection: the ``protect/*`` API behind the console and the MCP tools.

Contracts come from the registry (``GET /v1/contracts/published``) or a file holding that response,
and every envelope is re-verified here with the contract governor's public keys. Sealed documents
and the release ledger are kept per tenant under the workspace root. The tenant is always the
authenticated principal's; no request can name another tenant.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import quote, urlparse
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import protection as p
from .common import identity

ROUTES = {"protect/status": "read", "protect/documents": "read", "protect/admit": "read", "protect/receipts": "read",
          "protect/ingest": "write", "protect/release": "write"}


def _keys(values):
    return {kid: Ed25519PublicKey.from_public_bytes(base64.b64decode(v, validate=True)) for kid, v in (values or {}).items()}


def fetch_published(url, token, tenant, *, timeout=5):
    """Read published contracts from the registry. HTTPS, or plain HTTP on loopback only."""
    u = urlparse(url)
    if not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost"))) or u.username or u.query:
        raise ValueError("Registry URL must be HTTPS (or loopback HTTP) without credentials or query")
    identity(tenant)
    req = urllib.request.Request(url.rstrip("/") + "/v1/contracts/published?tenant=" + quote(tenant),
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read(2_000_001)[:2_000_000])
    if body.get("tenant") != tenant or not isinstance(body.get("contracts"), list):
        raise ValueError("Unexpected registry response")
    return body["contracts"]


class ProtectionHost:
    def __init__(self, root, config, *, clock):
        self.root = Path(root) / "protection"
        self.clock = clock
        self.contract_keys = _keys(config.get("contract_keys"))
        self.publisher_keys = _keys(config.get("publisher_keys"))
        self.reviewer_keys = _keys(config.get("reviewer_keys"))
        self.entitlements = config.get("entitlements", {})
        key = Path(config["vault_key_file"]).read_bytes()
        self.vault = p.TokenVault(key)
        envelopes = list(config.get("contracts", []))
        if config.get("contracts_file"):
            envelopes += json.loads(Path(config["contracts_file"]).read_text())["contracts"]
        registry = config.get("registry")
        if registry:
            for tenant in registry["tenants"]:
                envelopes += fetch_published(registry["url"], Path(registry["token_file"]).read_text().strip(), tenant)
        self.contracts = p.load_contracts(envelopes, self.contract_keys, as_of=self._now())
        self.detokenizer = p.Detokenizer(self.vault, self.contracts)

    def _now(self):
        from datetime import datetime, timezone
        t = datetime.fromisoformat(self.clock().replace("Z", "+00:00")).astimezone(timezone.utc)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _dir(self, tenant):
        d = self.root / identity(tenant)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _ledger(self, tenant):
        # One connection per request: the HTTP server is threaded and SQLite connections are per-thread.
        return p.ReleaseLedger(str(self._dir(tenant) / "releases.sqlite"))

    def _documents(self, tenant):
        f = self._dir(tenant) / "sealed.json"
        return json.loads(f.read_text()) if f.exists() else []

    def _save(self, tenant, docs):
        f = self._dir(tenant) / "sealed.json"
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(docs, sort_keys=True))
        tmp.replace(f)

    def _mine(self, principal):
        return {k: v for k, v in self.contracts.items() if v["tenant"] == principal.tenant}

    def dispatch(self, route, body, principal):
        tenant = principal.tenant
        if route == "protect/status":
            if body:
                raise ValueError("Unsupported status options")
            docs = self._documents(tenant)
            return {"configured": True, "tenant": tenant, "contracts": sorted(self._mine(principal).values(), key=lambda c: (c["kind"], c["id"])),
                    "documents": len(docs), "quarantined": sum(bool(d["quarantine"]) for d in docs),
                    "entitled": self.entitlements.get(principal.subject, []),
                    "boundary": "Reference vault and in-process detokenizer; no PCI scope reduction claimed (ADR-0002)."}
        if route == "protect/ingest":
            if set(body) != {"envelope"}:
                raise ValueError("Unsupported ingest options")
            sealed = p.ingest(body["envelope"], contracts=self._mine(principal), publisher_keys=self.publisher_keys, vault=self.vault)
            docs = [d for d in self._documents(tenant) if d["id"] != sealed["id"]] + [sealed]
            self._save(tenant, docs)
            return {"id": sealed["id"], "source": sealed["source"], "origin": sealed["origin"], "quarantine": sealed["quarantine"],
                    "chunks": [c["id"] for c in sealed["chunks"]], "safe_attributes": sealed["safe_attributes"],
                    "tokens": sorted({m.group() for c in sealed["chunks"] for m in p.TOKEN.finditer(c["text"])} |
                                     {v for v in sealed["fields"].values() if isinstance(v, str) and p.TOKEN.fullmatch(v)})}
        if route == "protect/documents":
            if body:
                raise ValueError("Unsupported documents options")
            return {"documents": [{"id": d["id"], "source": d["source"], "origin": d["origin"], "observed_at": d["observed_at"],
                                   "quarantine": d["quarantine"], "fields": d["fields"], "safe_attributes": d["safe_attributes"],
                                   "chunks": [{k: c.get(k) for k in ("id", "text", "requirement_id", "status")} for c in d["chunks"]]}
                                  for d in self._documents(tenant)]}
        if route == "protect/admit":
            if not {"pack", "retrieved"} <= set(body) <= {"pack", "retrieved", "as_of"}:
                raise ValueError("Unsupported admission options")
            return p.admit_for_model(body["pack"], self._documents(tenant), body["retrieved"],
                                     as_of=body.get("as_of") or self._now(), contracts=self.contracts, principal=principal)
        if route == "protect/release":
            if not {"output", "destination", "purpose", "operation", "label"} <= set(body) <= \
                    {"output", "destination", "purpose", "operation", "label", "review"}:
                raise ValueError("Unsupported release options")
            ledger = self._ledger(tenant)
            try:
                gateway = p.Outbound(contracts=self.contracts, vault=self.vault, detokenizer=self.detokenizer,
                                     entitlements=self.entitlements, ledger=ledger, reviewer_keys=self.reviewer_keys)
                return p.release(gateway, body["output"], destination=body["destination"], purpose=body["purpose"],
                                 operation=body["operation"], principal=principal, label=body["label"],
                                 as_of=self._now(), review=body.get("review"))
            finally:
                ledger.close()
        if route == "protect/receipts":
            if body:
                raise ValueError("Unsupported receipts options")
            ledger = self._ledger(tenant)
            try:
                return {"receipts": list(reversed(ledger.receipts()))[:200]}
            finally:
                ledger.close()
        raise ValueError("Unknown protection route")
