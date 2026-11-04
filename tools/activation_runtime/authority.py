"""Host-configured authentication, signed review bindings and replay protection."""
from dataclasses import dataclass
from pathlib import Path
import sys

from .common import canonical, fingerprint, identity
P=str(Path(__file__).resolve().parents[1]/"packspec_compiler")
if P not in sys.path: sys.path.insert(0,P)
from signed_bundles import sign, verify, ATTEST_SCHEMA, _validate_period
from signed_gate import SQLiteNonceStore


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    scopes: frozenset


def issue_access(*, subject, tenant, scopes, key, key_id, issued_at, expires_at):
    identity(subject);identity(tenant)
    if not isinstance(scopes,list) or not scopes or len(scopes)>16 or len(set(scopes))!=len(scopes):
        raise ValueError("Unique bounded scopes required")
    for scope in scopes:
        if scope not in {"read","write","review","admin"}: raise ValueError("Unknown access scope")
    _validate_period(issued_at,expires_at,issued_at)
    return sign({"access":{"subject":subject,"tenant":tenant,"scopes":sorted(scopes)},
                 "issued_at":issued_at,"expires_at":expires_at},key,key_id=key_id,schema=ATTEST_SCHEMA)


def authenticate(token,keys, *, as_of, scope):
    payload=verify(token,keys,schema=ATTEST_SCHEMA)
    if set(payload)!={"access","issued_at","expires_at"}: raise PermissionError("Wrong token purpose")
    _validate_period(payload["issued_at"],payload["expires_at"],as_of)
    access=payload["access"]
    if not isinstance(access,dict) or set(access)!={"subject","tenant","scopes"}: raise PermissionError("Invalid principal")
    identity(access["subject"]);identity(access["tenant"])
    scopes=access["scopes"]
    if not isinstance(scopes,list) or any(s not in {"read","write","review","admin"} for s in scopes) or scope not in scopes:
        raise PermissionError("Required scope denied")
    return Principal(access["subject"],access["tenant"],frozenset(scopes))


def review_binding(context, *, decision, reviewer, author_key_id, key, key_id,
                   issued_at, expires_at, nonce):
    """Proposer code can draft, but only a separately configured reviewer can sign."""
    identity(reviewer);identity(author_key_id);identity(nonce)
    if key_id==author_key_id or decision not in {"APPROVE","REJECT"}: raise ValueError("Independent review required")
    _validate_period(issued_at,expires_at,issued_at)
    return sign({"review":{"context":context,"decision":decision,"reviewer":reviewer,
                           "author_key_id":author_key_id,"nonce":nonce},
                 "issued_at":issued_at,"expires_at":expires_at},key,key_id=key_id,schema=ATTEST_SCHEMA)


def check_review(envelope,keys, *, context, author_public_key, as_of):
    """Check authority and exact scope; the caller must atomically record the nonce."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    payload=verify(envelope,keys,schema=ATTEST_SCHEMA)
    if set(payload)!={"review","issued_at","expires_at"}: raise ValueError("Wrong attestation purpose")
    _validate_period(payload["issued_at"],payload["expires_at"],as_of)
    review=payload["review"]
    if not isinstance(review,dict) or set(review)!={"context","decision","reviewer","author_key_id","nonce"}:
        raise ValueError("Invalid review")
    identity(review["reviewer"]);identity(review["nonce"])
    if canonical(review["context"])!=canonical(context) or review["decision"]!="APPROVE":
        raise PermissionError("Review rejected or stale context")
    actual=keys[envelope["key_id"]].public_bytes(Encoding.Raw,PublicFormat.Raw)
    if actual==author_public_key.public_bytes(Encoding.Raw,PublicFormat.Raw):
        raise PermissionError("Same signing key under different identity cannot self-review")
    return {"reviewer":review["reviewer"],"review_key_id":envelope["key_id"],
            "nonce":review["nonce"],
            "context_sha256":fingerprint(context),"review":"HOST_AUTHORIZED_APPROVAL",
            "boundary":"Signature authenticates the configured reviewer, not universal semantic truth"}


def verify_review(envelope,keys, *, context, author_public_key, as_of, nonce_store, tenant):
    identity(tenant)
    checked=check_review(envelope,keys,context=context,author_public_key=author_public_key,as_of=as_of)
    if not isinstance(nonce_store,SQLiteNonceStore) or not nonce_store("activation-review",tenant,checked["nonce"]):
        raise PermissionError("Review replay or nondurable replay guard")
    return {key:value for key,value in checked.items() if key!="nonce"}
