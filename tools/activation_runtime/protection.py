"""Contract-governed sensitive information flow with capability-isolated detokenization (ADR-0002).

Prompt injection is treated as a confused-deputy problem and answered the way IAM answers it:
authority never travels inside the payload. The model receives the minimum information its task
needs, and nothing it is persuaded to do can widen what it saw or what leaves.

Read     Documents are signed by the resource that owns them; origin is derived from the verified
         key, never from a string in the document. The owner's signed data contract classifies every
         field. Declared sensitive fields become opaque reference tokens; only approved derived
         attributes (e.g. card brand, last four) stay visible. Undeclared fields and unclassified
         free text are quarantined, not admitted.
Reason   ``admit_for_model`` runs the existing deterministic gate only over signed, sealed, dated,
         same-tenant evidence, and returns the model context marked as untrusted data plus a label
         of exactly what the model saw.
Release  ``release`` is the single exit. It binds the decision to principal, tenant, purpose,
         operation, destination and data class; needs the source's release rule, the destination's
         acceptance contract and the user's entitlement; normalizes hidden channels; blocks plaintext
         card numbers; refuses tokens the model was never given; can require a signed independent
         review; and records a receipt that holds hashes, never protected plaintext.
Reveal   Only ``Detokenizer`` can turn a token back into a value. It is a separate component that
         re-evaluates the owner's detokenization rule itself; the model, the gate and the gateway's
         decision logic never hold it or its keys.

Boundaries (see ADR-0002): ``TokenVault`` is a reference stand-in for an HSM or a tokenization
service such as Vault Transform; production should use established tokenization, not this class.
Model-visible tokens are references, never credentials or payment authorizations: QualityRag issues
no transaction-capable tokens. The detection backstop covers card numbers (Luhn) only. Signed text
can still contain injected instructions; it is evidence, never an instruction. Nothing here reduces
PCI DSS scope by itself; that requires a documented scoping assessment of the deployed boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
from urllib.parse import urlparse

from .authority import Principal
from .common import canonical, fingerprint, identity

P = str(Path(__file__).resolve().parents[1] / "packspec_compiler")
if P not in sys.path:
    sys.path.insert(0, P)
from signed_bundles import sign, verify, ATTEST_SCHEMA, _validate_period  # noqa: E402

CONTRACT_SCHEMA = "qualityrag.data-contract/v1"
SEALED_SCHEMA = "qualityrag.sealed-document/v1"
RECEIPT_SCHEMA = "qualityrag.release-receipt/v1"
CLASS = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
TOKEN = re.compile(r"\[([A-Z][A-Z0-9_]{1,31}):tok_([0-9a-f]{16})\]")
DERIVED = {"PAN": {"brand", "last4"}}
_PAN_CANDIDATE = re.compile(r"(?<![\d])(?:\d[ -]?){12,18}\d(?![\d])")
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)[^)]*\)")
_URL = re.compile(r"\b(?:https?|ftp|data|javascript):[^\s<>\]\)]+", re.IGNORECASE)


# ---------- Detection backstop (never the primary control) ----------
def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def find_pans(text: str) -> list[tuple[int, int, str]]:
    """Card-number-shaped digit runs (13-19 digits, spaces or dashes allowed) that pass Luhn."""
    hits = []
    for m in _PAN_CANDIDATE.finditer(text):
        digits = re.sub(r"[ -]", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            hits.append((m.start(), m.end(), digits))
    return hits


def _brand(pan: str) -> str:
    if pan[0] == "4":
        return "VISA"
    if pan[:2] in {"34", "37"}:
        return "AMEX"
    if 51 <= int(pan[:2]) <= 55 or 2221 <= int(pan[:4]) <= 2720:
        return "MASTERCARD"
    if pan[:4] == "6011" or pan[:2] == "65":
        return "DISCOVER"
    return "OTHER"


# ---------- Signed data contracts: each resource's own declaration, published through the registry ----------
def _ids(value, what):
    if not isinstance(value, list) or len(value) > 256 or len(set(value)) != len(value):
        raise ValueError(what + " must be a unique list")
    for item in value:
        identity(item)
    return value


def _classes(value, what):
    if not isinstance(value, list) or len(set(value)) != len(value) or any(
            not isinstance(c, str) or not CLASS.fullmatch(c) for c in value):
        raise ValueError(what + " must be unique upper-case class names")
    return value


def _rule(rule, keys, what):
    if not isinstance(rule, dict) or set(rule) != keys:
        raise ValueError(what + " fields differ from the schema")
    identity(rule["destination"])
    _ids(rule["purposes"], what + " purposes")
    _ids(rule["operations"], what + " operations")
    if not rule["purposes"] or not rule["operations"]:
        raise ValueError(what + " must name at least one purpose and operation")
    return rule


def validate_contract(c: dict) -> dict:
    if not isinstance(c, dict) or c.get("schema") != CONTRACT_SCHEMA or c.get("kind") not in {"source", "destination"}:
        raise ValueError("Unknown data contract")
    identity(c.get("id"))
    identity(c.get("tenant"))
    if c["kind"] == "source":
        if set(c) != {"schema", "kind", "id", "tenant", "publisher_key_id", "fields", "text", "scan",
                      "derive", "release", "detokenize"}:
            raise ValueError("Source contract fields differ from the schema")
        identity(c["publisher_key_id"])
        f = c["fields"]
        if not isinstance(f, dict) or set(f) != {"public", "sensitive"}:
            raise ValueError("fields must classify public and sensitive fields")
        _ids(f["public"], "public fields")
        names = set(f["public"])
        for s in f["sensitive"] if isinstance(f["sensitive"], list) else [None]:
            if (not isinstance(s, dict) or set(s) != {"field", "class", "token"} or s["token"] not in {"deterministic", "random"}
                    or not isinstance(s["class"], str) or not CLASS.fullmatch(s["class"]) or s["field"] in names):
                raise ValueError("Invalid or duplicate sensitive field declaration")
            identity(s["field"])
            names.add(s["field"])
        if c["text"] not in {"OWNER_CLASSIFIED", "UNCLASSIFIED"}:
            raise ValueError("text must be OWNER_CLASSIFIED or UNCLASSIFIED")
        _classes(c["scan"], "scan")
        if set(c["scan"]) - {"PAN"}:
            raise ValueError("Only PAN has a detection backstop; declare other classes as fields")
        if not isinstance(c["derive"], dict) or any(cls not in DERIVED or not isinstance(a, list) or set(a) - DERIVED[cls]
                                                    for cls, a in c["derive"].items()):
            raise ValueError("derive may only name approved attributes (PAN: brand, last4)")
        if not isinstance(c["release"], list) or not isinstance(c["detokenize"], list):
            raise ValueError("release and detokenize must be rule lists")
        released = {}
        for r in c["release"]:
            _rule(r, {"destination", "purposes", "operations"}, "release rule")
            released[r["destination"]] = r
        for r in c["detokenize"]:
            _rule(r, {"class", "destination", "purposes", "operations"}, "detokenize rule")
            _classes([r["class"]], "detokenize class")
            base = released.get(r["destination"])
            if base is None or set(r["purposes"]) - set(base["purposes"]) or set(r["operations"]) - set(base["operations"]):
                raise ValueError("Detokenization can never be broader than release")
    else:
        if set(c) != {"schema", "kind", "id", "tenant", "channel", "accepts", "link_hosts", "max_bytes",
                      "requires_review", "review_classes"}:
            raise ValueError("Destination contract fields differ from the schema")
        identity(c["channel"])
        if not isinstance(c["accepts"], dict) or set(c["accepts"]) != {"sources", "classes", "operations"}:
            raise ValueError("accepts must name sources, classes and operations")
        _ids(c["accepts"]["sources"], "accepts.sources")
        _classes(c["accepts"]["classes"], "accepts.classes")
        _ids(c["accepts"]["operations"], "accepts.operations")
        if not isinstance(c["link_hosts"], list) or any(not isinstance(h, str) or not re.fullmatch(r"[a-z0-9.-]{1,253}", h)
                                                        for h in c["link_hosts"]):
            raise ValueError("link_hosts must be lower-case host names")
        if type(c["max_bytes"]) is not int or not 1 <= c["max_bytes"] <= 1_000_000 or type(c["requires_review"]) is not bool:
            raise ValueError("Invalid destination limits")
        _classes(c["review_classes"], "review_classes")
    return c


def sign_contract(contract, key, *, key_id, issued_at, expires_at):
    """The registry signs each resource's contract; an unsigned contract has no authority."""
    validate_contract(contract)
    _validate_period(issued_at, expires_at, issued_at)
    return sign({"data_contract": contract, "issued_at": issued_at, "expires_at": expires_at},
                key, key_id=key_id, schema=ATTEST_SCHEMA)


def load_contracts(envelopes, registry_keys, *, as_of) -> dict:
    out = {}
    for env in envelopes:
        payload = verify(env, registry_keys, schema=ATTEST_SCHEMA)
        if set(payload) != {"data_contract", "issued_at", "expires_at"}:
            raise PermissionError("Wrong attestation purpose")
        _validate_period(payload["issued_at"], payload["expires_at"], as_of)
        c = validate_contract(payload["data_contract"])
        if c["id"] in out:
            raise ValueError("Duplicate contract id")
        out[c["id"]] = c
    return out


# ---------- Token vault (reference stand-in for an HSM or Vault Transform) ----------
class TokenVault:
    """Opaque reference tokens ``[CLASS:tok_<16 hex>]``. Values are sealed with AES-GCM and bound to
    their source and tenant. This class can seal and describe; only a ``Detokenizer`` can open."""

    def __init__(self, master_key: bytes):
        if not isinstance(master_key, bytes) or len(master_key) < 32:
            raise ValueError("A 32-byte master key is required")
        self._mac = hmac.new(master_key, b"qualityrag/token-mac/v1", hashlib.sha256).digest()
        self._enc = hmac.new(master_key, b"qualityrag/token-enc/v1", hashlib.sha256).digest()
        self._store = {}

    def tokenize(self, cls: str, value: str, *, source: str, tenant: str, mode: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        if not CLASS.fullmatch(cls) or not isinstance(value, str) or not value or mode not in {"deterministic", "random"}:
            raise ValueError("Invalid tokenization request")
        identity(source);identity(tenant)
        tid = (hmac.new(self._mac, canonical([tenant, source, cls, value]), hashlib.sha256).hexdigest()[:16]
               if mode == "deterministic" else secrets.token_hex(8))
        token = "[" + cls + ":tok_" + tid + "]"
        if token not in self._store:
            nonce = secrets.token_bytes(12)
            aad = canonical([token, tenant, source])
            digits = re.sub(r"\D", "", value)
            self._store[token] = {"class": cls, "source": source, "tenant": tenant, "nonce": nonce,
                                  "sealed": AESGCM(self._enc).encrypt(nonce, value.encode(), aad),
                                  "last4": digits[-4:] if cls == "PAN" and len(digits) >= 4 else None}
        return token

    def meta(self, token: str) -> dict | None:
        row = self._store.get(token)
        return None if row is None else {k: row[k] for k in ("class", "source", "tenant", "last4")}


class Detokenizer:
    """The only component that can open a token. It re-evaluates the owner's detokenization rule
    itself instead of trusting the caller's decision. Run it as an isolated privileged service."""

    def __init__(self, vault: TokenVault, contracts: dict):
        self._vault = vault
        self._contracts = contracts

    def reveal(self, token, *, tenant, destination, purpose, operation) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        row = self._vault._store.get(token)
        if row is None or row["tenant"] != tenant:
            raise PermissionError("Unknown token for this tenant")
        source = self._contracts.get(row["source"])
        dest = self._contracts.get(destination)
        if (source is None or dest is None or dest["kind"] != "destination" or dest["tenant"] != tenant
                or source["tenant"] != tenant or row["class"] not in dest["accepts"]["classes"]
                or not any(r["class"] == row["class"] and r["destination"] == destination and purpose in r["purposes"]
                           and operation in r["operations"] for r in source["detokenize"])):
            raise PermissionError("Detokenization not authorized by the owner's contract")
        return AESGCM(self._vault._enc).decrypt(row["nonce"], row["sealed"],
                                                canonical([token, row["tenant"], row["source"]])).decode()


# ---------- Read: signed, classified, sealed ingestion ----------
def _instant(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp required")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp needs a timezone")
    return dt.astimezone(timezone.utc)


def sign_document(document, key, *, key_id):
    """The owning resource signs what it publishes. A signature proves integrity and who published,
    not that the text is safe to obey."""
    if not isinstance(document, dict):
        raise ValueError("Document must be an object")
    return sign({"document": document}, key, key_id=key_id, schema=ATTEST_SCHEMA)


def ingest(envelope, *, contracts, publisher_keys, vault: TokenVault) -> dict:
    """Verify the owner's signature, derive origin from the key, protect every declared field,
    quarantine anything the owner did not classify."""
    payload = verify(envelope, publisher_keys, schema=ATTEST_SCHEMA)
    if set(payload) != {"document"} or not isinstance(payload["document"], dict):
        raise PermissionError("Not a signed document")
    doc = payload["document"]
    if not set(doc) <= {"id", "source", "observed_at", "fields", "chunks", "origin", "format", "revision"}:
        raise ValueError("Unsupported document fields")
    identity(doc.get("id"))
    contract = contracts.get(doc.get("source"))
    if contract is None or contract["kind"] != "source":
        raise PermissionError("Document names no registered source contract")
    if envelope["key_id"] != contract["publisher_key_id"]:
        raise PermissionError("Signed by a key that does not own this source")
    _instant(doc.get("observed_at"))
    fields, chunks = doc.get("fields", {}), doc.get("chunks")
    if not isinstance(fields, dict) or not isinstance(chunks, list) or not chunks:
        raise ValueError("Document needs fields (object) and nonempty chunks")
    tenant, src = contract["tenant"], contract["id"]
    declared = {s["field"]: s for s in contract["fields"]["sensitive"]}
    public = set(contract["fields"]["public"])
    quarantine, tokens, safe, sealed_fields = [], {}, {}, {}
    for name, value in fields.items():
        identity(name)
        if name in declared:
            if not isinstance(value, str) or not value:
                raise ValueError("Sensitive field values must be nonempty strings")
            s = declared[name]
            token = vault.tokenize(s["class"], value, source=src, tenant=tenant, mode=s["token"])
            tokens[value] = token
            sealed_fields[name] = token
            wanted = contract["derive"].get(s["class"], [])
            if s["class"] == "PAN" and wanted:
                digits = re.sub(r"\D", "", value)
                attrs = {"brand": _brand(digits) if len(digits) >= 4 else "OTHER", "last4": digits[-4:]}
                safe[name] = {k: attrs[k] for k in wanted}
        elif name in public:
            sealed_fields[name] = value
        else:
            quarantine.append({"field": name, "reason": "UNCLASSIFIED_FIELD"})
    out_chunks = []
    for ch in chunks:
        if not isinstance(ch, dict) or not isinstance(ch.get("text"), str):
            raise ValueError("Each chunk needs text")
        identity(ch.get("id"))
        if ch.get("observed_at") is not None:
            _instant(ch["observed_at"])
        text = ch["text"]
        for value in sorted(tokens, key=len, reverse=True):
            text = text.replace(value, tokens[value])
        if "PAN" in contract["scan"]:
            for start, end, digits in reversed(find_pans(text)):
                text = text[:start] + vault.tokenize("PAN", digits, source=src, tenant=tenant, mode="deterministic") + text[end:]
        out_chunks.append({**{k: v for k, v in ch.items() if k != "text"}, "text": text})
    if contract["text"] != "OWNER_CLASSIFIED":
        quarantine.append({"field": "chunks", "reason": "UNCLASSIFIED_TEXT"})
    return {"schema": SEALED_SCHEMA, "id": doc["id"], "source": src, "tenant": tenant,
            "origin": "signed:" + envelope["key_id"], "observed_at": doc["observed_at"],
            "fields": sealed_fields, "safe_attributes": safe, "chunks": out_chunks,
            "quarantine": quarantine, **({k: doc[k] for k in ("format", "revision") if k in doc}),
            "provenance": {"key_id": envelope["key_id"], "document_sha256": fingerprint(doc),
                           "contract_sha256": fingerprint(contract), "declared_origin_ignored": doc.get("origin")}}


# ---------- Reason: admission over sealed evidence ----------
def admit_for_model(pack, sealed_documents, retrieved, *, as_of, contracts, principal: Principal) -> dict:
    """Gate only signed, sealed, classified, same-tenant evidence; return the model context and its label."""
    from .governance import policy_test
    if not isinstance(principal, Principal) or "read" not in principal.scopes:
        raise PermissionError("A principal with read scope is required")
    admitted, refused = [], []
    for doc in sealed_documents:
        ok = isinstance(doc, dict)
        prov = doc.get("provenance") if ok else None
        contract = contracts.get(doc.get("source")) if ok else None
        reason = None
        if not ok or doc.get("schema") != SEALED_SCHEMA or not isinstance(prov, dict) or contract is None:
            reason = "NOT_SEALED_BY_INGESTION"
        elif contract["tenant"] != principal.tenant or doc.get("tenant") != principal.tenant:
            reason = "CROSS_TENANT"
        elif prov.get("contract_sha256") != fingerprint(contract) or doc.get("origin") != "signed:" + str(prov.get("key_id")):
            reason = "CONTRACT_OR_ORIGIN_CHANGED_SINCE_INGESTION"
        elif doc.get("quarantine"):
            reason = "QUARANTINED:" + ",".join(sorted({q["reason"] for q in doc["quarantine"]}))
        elif any(find_pans(c.get("text", "")) for c in doc.get("chunks", [])):
            reason = "PLAINTEXT_SENSITIVE_DATA"
        if reason:
            refused.append({"document": doc.get("id") if ok else None, "reason": reason})
            continue
        admitted.append({**doc, "chunks": [{**c, "observed_at": c.get("observed_at") or doc["observed_at"]}
                                           for c in doc["chunks"]]})
    known = {c["id"] for d in admitted for c in d["chunks"]}
    kept = [cid for cid in retrieved if cid in known]
    refused += [{"chunk": cid, "reason": "CHUNK_NOT_FROM_ADMITTED_DOCUMENT"} for cid in retrieved if cid not in known]
    if not kept:
        return {"verdict": "INCONCLUSIVE", "can_generate": False, "refused": refused, "context": [],
                "label": None, "test": None}
    test = policy_test(pack, admitted, kept, as_of=as_of)
    context, seen = [], set()
    if test["verdict"] == "ADMIT":
        owner = {c["id"]: d for d in admitted for c in d["chunks"]}
        for req in test["requirements"]:
            for span in req["spans"]:
                if span["status"] == "SUPPORTS" and span["chunk_id"] not in seen:
                    seen.add(span["chunk_id"])
                    context.append({"chunk_id": span["chunk_id"], "source": owner[span["chunk_id"]]["source"],
                                    "text": span["text"], "trust": "UNTRUSTED_SOURCE_TEXT"})
    label = None
    if context:
        label = {"tenant": principal.tenant, "principal": principal.subject,
                 "sources": sorted({c["source"] for c in context}),
                 "tokens": sorted({m.group() for c in context for m in TOKEN.finditer(c["text"])}),
                 "pack_id": test["pack_id"], "pack_version": test["pack_version"], "as_of": as_of}
        label["label_sha256"] = fingerprint(label)
    return {"verdict": test["verdict"], "can_generate": test["verdict"] == "ADMIT", "refused": refused,
            "context": context, "label": label, "test": test,
            "note": "Context text is untrusted evidence, never instructions. The label bounds where anything derived from it may go."}


# ---------- Release: outbound governance ----------
class ReleaseLedger:
    """Append-only, hash-chained release receipts, holding hashes and classes, never protected plaintext.
    Detects ordinary corruption; a database administrator can still rewrite local state."""

    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=5)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS release_receipts(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL, receipt_hash TEXT NOT NULL UNIQUE);
        CREATE TRIGGER IF NOT EXISTS release_no_update BEFORE UPDATE ON release_receipts
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        CREATE TRIGGER IF NOT EXISTS release_no_delete BEFORE DELETE ON release_receipts
          BEGIN SELECT RAISE(ABORT,'append-only'); END;""")

    def append(self, receipt):
        row = self.db.execute("SELECT receipt_hash FROM release_receipts ORDER BY sequence DESC LIMIT 1").fetchone()
        body = {**receipt, "previous": row[0] if row else None}
        digest = fingerprint(body)
        with self.db:
            self.db.execute("INSERT INTO release_receipts(body,receipt_hash) VALUES(?,?)",
                            (json.dumps(body, sort_keys=True), digest))
        return {**body, "receipt_hash": digest}

    def receipts(self):
        out, previous = [], None
        for body_raw, digest in self.db.execute("SELECT body,receipt_hash FROM release_receipts ORDER BY sequence"):
            body = json.loads(body_raw)
            if body.get("previous") != previous or fingerprint(body) != digest:
                raise ValueError("Release ledger chain corruption")
            out.append({**body, "receipt_hash": digest})
            previous = digest
        return out

    def released_from(self, source_id):
        """Recall: every release that carried data from a source later withdrawn or found compromised."""
        return [r for r in self.receipts() if r["decision"] == "RELEASE" and source_id in r["sources"]]

    def close(self):
        self.db.close()


def normalize(text: str, link_hosts) -> tuple[str, list[str]]:
    """Close hidden exfiltration channels: images, off-list links and URLs, invisible characters."""
    changes, allowed = [], set(link_hosts)

    def host_ok(url):
        u = urlparse(url)
        return u.scheme == "https" and (u.hostname or "") in allowed

    if _INVISIBLE.search(text):
        changes.append("INVISIBLE_CHARACTERS_REMOVED")
        text = _INVISIBLE.sub("", text)
    if _MD_IMAGE.search(text):
        changes.append("IMAGE_REMOVED")
        text = _MD_IMAGE.sub("[image removed]", text)

    def link(m):
        if host_ok(m.group(2)):
            return m.group()
        changes.append("LINK_REMOVED")
        return m.group(1)

    def url(m):
        if host_ok(m.group()):
            return m.group()
        changes.append("URL_REMOVED")
        return "[link removed]"
    text = _URL.sub(url, _MD_LINK.sub(link, text))
    return text, changes


def sign_release_review(*, output_sha256, destination, purpose, operation, reviewer, decision, key, key_id,
                        issued_at, expires_at):
    identity(reviewer);identity(destination);identity(purpose);identity(operation)
    if decision not in {"APPROVE", "REJECT"} or not re.fullmatch(r"[0-9a-f]{64}", output_sha256 or ""):
        raise ValueError("Invalid release review")
    _validate_period(issued_at, expires_at, issued_at)
    return sign({"release_review": {"output_sha256": output_sha256, "destination": destination, "purpose": purpose,
                                    "operation": operation, "reviewer": reviewer, "decision": decision},
                 "issued_at": issued_at, "expires_at": expires_at}, key, key_id=key_id, schema=ATTEST_SCHEMA)


@dataclass(frozen=True)
class Outbound:
    contracts: dict
    vault: TokenVault
    detokenizer: Detokenizer
    entitlements: dict   # subject -> [{"destination", "purposes", "operations"}] (host configuration)
    ledger: ReleaseLedger
    reviewer_keys: dict | None = None


def release(gateway: Outbound, output: str, *, destination: str, purpose: str, operation: str,
            principal: Principal, label: dict | None, as_of: str, review: dict | None = None) -> dict:
    """The single exit. DENY unless the source, the destination and the user all say yes, for this
    purpose and this operation, within one tenant."""
    if not isinstance(output, str):
        raise ValueError("Output must be text")
    identity(destination);identity(purpose);identity(operation)
    reasons, detok, changes = [], [], []
    dest = gateway.contracts.get(destination)
    dest = dest if dest is not None and dest["kind"] == "destination" else None
    subject, tenant = getattr(principal, "subject", None), getattr(principal, "tenant", None)
    lab = label if isinstance(label, dict) else {}
    sources, given = sorted(lab.get("sources", [])), set(lab.get("tokens", []))
    if dest is None:
        reasons.append("UNREGISTERED_DESTINATION")
    if not isinstance(principal, Principal) or "write" not in principal.scopes or not any(
            e["destination"] == destination and purpose in e["purposes"] and operation in e["operations"]
            for e in gateway.entitlements.get(subject, [])):
        reasons.append("USER_NOT_ENTITLED")
    if lab and lab.get("label_sha256") != fingerprint({k: v for k, v in lab.items() if k != "label_sha256"}):
        reasons.append("LABEL_TAMPERED")
    if lab and (lab.get("tenant") != tenant or lab.get("principal") != subject):
        reasons.append("LABEL_FROM_ANOTHER_PRINCIPAL")
    text = output
    if dest is not None:
        if dest["tenant"] != tenant:
            reasons.append("CROSS_TENANT")
        if operation not in dest["accepts"]["operations"]:
            reasons.append("DESTINATION_DOES_NOT_ACCEPT_OPERATION")
        for src in sources:
            sc = gateway.contracts.get(src)
            if sc is None or sc["tenant"] != tenant or not any(
                    r["destination"] == destination and purpose in r["purposes"] and operation in r["operations"]
                    for r in sc["release"]):
                reasons.append("SOURCE_RELEASE_REFUSED:" + src)
            if src not in dest["accepts"]["sources"]:
                reasons.append("DESTINATION_DOES_NOT_ACCEPT:" + src)
        text, changes = normalize(output, dest["link_hosts"])
        if len(text.encode()) > dest["max_bytes"]:
            reasons.append("OUTPUT_TOO_LARGE")
    if find_pans(text):
        reasons.append("PLAINTEXT_SENSITIVE_DATA")
    tokenized_sha = hashlib.sha256(text.encode()).hexdigest()
    found = sorted({m.group() for m in TOKEN.finditer(text)})
    for token in found:
        meta = gateway.vault.meta(token)
        if token not in given or meta is None or meta["tenant"] != tenant:
            reasons.append("TOKEN_NOT_IN_MODEL_CONTEXT")
            continue
        sc = gateway.contracts.get(meta["source"])
        if dest is not None and sc is not None and meta["class"] in dest["accepts"]["classes"] and any(
                r["class"] == meta["class"] and r["destination"] == destination and purpose in r["purposes"]
                and operation in r["operations"] for r in sc["detokenize"]):
            detok.append({"token": token, "class": meta["class"], "source": meta["source"]})
    needs_review = dest is not None and (dest["requires_review"] or bool({d["class"] for d in detok} & set(dest["review_classes"])))
    if needs_review:
        try:
            payload = verify(review, gateway.reviewer_keys or {}, schema=ATTEST_SCHEMA)
            r = payload["release_review"]
            _validate_period(payload["issued_at"], payload["expires_at"], as_of)
            if (r["decision"] != "APPROVE" or r["destination"] != destination or r["purpose"] != purpose
                    or r["operation"] != operation or r["output_sha256"] != tokenized_sha or r["reviewer"] == subject):
                reasons.append("REVIEW_REJECTED_OR_STALE")
        except Exception:
            reasons.append("INDEPENDENT_REVIEW_REQUIRED")
    decision = "DENY" if reasons else "RELEASE"
    released = None
    if decision == "RELEASE":
        released, opened = text, {d["token"] for d in detok}
        for token in found:
            if token in opened:  # the isolated service re-checks the owner's rule before opening
                value = gateway.detokenizer.reveal(token, tenant=tenant, destination=destination,
                                                   purpose=purpose, operation=operation)
            else:
                meta = gateway.vault.meta(token)
                value = "[card ending " + meta["last4"] + "]" if meta["last4"] else "[" + meta["class"] + " withheld]"
            released = released.replace(token, value)
    receipt = gateway.ledger.append({
        "schema": RECEIPT_SCHEMA, "at": as_of, "decision": decision, "reasons": sorted(set(reasons)),
        "destination": destination, "purpose": purpose, "operation": operation, "principal": subject,
        "tenant": tenant, "sources": sources, "label_sha256": lab.get("label_sha256"),
        "output_sha256": tokenized_sha, "detokenized": [{"class": d["class"], "source": d["source"]} for d in detok],
        "normalized": sorted(set(changes)), "reviewed": bool(needs_review and decision == "RELEASE")})
    return {"decision": decision, "reasons": sorted(set(reasons)), "text": released, "receipt": receipt}
