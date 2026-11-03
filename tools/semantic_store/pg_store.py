"""Tenant-bound PostgreSQL persistence for the experimental semantic ledger.

The login-role-to-tenant binding is owned by database administrators; no
caller-supplied tenant_id or session GUC is trusted. Requires an autocommit
psycopg connection using an unprivileged LOGIN role granted qr_runtime.
Cannot emit an authenticated semantic ADMIT.
"""
from __future__ import annotations

import re
from typing import Any

from store import Admission, canonical_bytes, digest

_SHA = re.compile(r"^[0-9a-f]{64}$")


class TenantPostgresStore:
    def __init__(self, connection):
        if not getattr(connection, "autocommit", False):
            raise ValueError("PostgreSQL connection must use autocommit for atomic operations")
        self.db=connection
        with self.db.cursor() as cursor:
            cursor.execute("SELECT qr_private.authenticated_tenant()")
            tenant=cursor.fetchone()[0]
            if tenant is None:
                raise PermissionError("Database login role is not bound to a tenant")
            self.tenant_id=tenant

    def add_source(self, source_id: str, revision: str,
                   source_sha256: str, metadata: dict[str, Any]) -> None:
        if not isinstance(source_sha256,str) or not _SHA.fullmatch(source_sha256):
            raise ValueError("Source digest must be lowercase SHA-256")
        if not isinstance(metadata,dict):
            raise ValueError("Source metadata object required")
        payload=canonical_bytes(metadata).decode("utf-8")
        with self.db.transaction():
            self.db.execute("""
              INSERT INTO qr_store.source_versions
              (tenant_id,source_id,revision,source_sha256,metadata_json)
              VALUES (qr_private.authenticated_tenant(),%s,%s,%s,%s::jsonb)
            """,(source_id,revision,source_sha256,payload))

    def add_object(self, object_id: str, revision: str,
                   source_id: str, source_revision: str,
                   kind: str, payload: dict[str, Any]) -> str:
        if not isinstance(kind,str) or not kind or not isinstance(payload,dict):
            raise ValueError("Nonempty kind and object payload required")
        h=digest(payload)
        with self.db.transaction():
            self.db.execute("""
              INSERT INTO qr_store.semantic_versions
              (tenant_id,object_id,revision,source_id,source_revision,
               kind,payload_json,payload_sha256)
              VALUES (qr_private.authenticated_tenant(),%s,%s,%s,%s,%s,%s::jsonb,%s)
            """,(object_id,revision,source_id,source_revision,kind,
                 canonical_bytes(payload).decode("utf-8"),h))
        return h

    def add_edge(self, edge_id: str, layer: str,
                 from_id: str, from_revision: str,
                 to_id: str, to_revision: str, relation: str,
                 properties: dict[str, Any] | None = None) -> None:
        if not isinstance(properties,dict) and properties is not None:
            raise ValueError("Edge properties must be JSON object")
        with self.db.transaction():
            self.db.execute("""
              INSERT INTO qr_store.semantic_edges
              (tenant_id,edge_id,layer,from_id,from_revision,
               to_id,to_revision,relation,properties_json)
              VALUES (qr_private.authenticated_tenant(),%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,(edge_id,layer,from_id,from_revision,to_id,to_revision,relation,
                 canonical_bytes(properties or {}).decode("utf-8")))

    def object_version(self, object_id: str, revision: str) -> dict | None:
        row=self.db.execute("""
          SELECT payload_json FROM qr_store.semantic_versions
          WHERE tenant_id=qr_private.authenticated_tenant()
          AND object_id=%s AND revision=%s
        """,(object_id,revision)).fetchone()
        return row[0] if row else None

    def record_admission(self, object_id: str, revision: str,
                         packspec_digest: str, checks: list[dict]) -> Admission:
        if (not isinstance(packspec_digest,str) or not packspec_digest
                or not isinstance(checks,list)
                or any(not isinstance(check,dict) for check in checks)):
            raise ValueError("PackSpec digest and structured checks required")
        failed=any(c.get("status") in ("FAIL","UNSAT") for c in checks)
        status="REFUSE" if failed else "INCONCLUSIVE"
        reason=("Supplied checks include an explicit failure" if failed else
                "Trusted verifier binding not implemented")
        receipt={
            "object_id":object_id,"revision":revision,
            "packspec_digest":packspec_digest,"checks":checks,
            "verdict":status,"reason":reason,
        }
        h=digest(receipt)
        with self.db.transaction():
            self.db.execute("""
              INSERT INTO qr_store.admission_receipts
              (tenant_id,receipt_hash,object_id,revision,packspec_digest,
               verdict,reason,checks_json)
              VALUES (qr_private.authenticated_tenant(),%s,%s,%s,%s,%s,%s,%s::jsonb)
              ON CONFLICT (tenant_id,receipt_hash) DO NOTHING
            """,(h,object_id,revision,packspec_digest,status,reason,
                 canonical_bytes(checks).decode("utf-8")))
        return Admission(status,reason,h)


    def record_apx_receipt(self, *, object_id: str, revision: str,
                           engine: str, receipt: dict) -> dict:
        """Preserve canonical HCR/RCOC receipts without trusting the source."""
        from apx_receipts import validate_receipt
        classification=validate_receipt(engine,receipt)
        h=digest({"engine":engine,"object_id":object_id,"revision":revision,
                  "receipt":receipt})
        with self.db.transaction():
            self.db.execute("""
                INSERT INTO qr_store.apx_receipts
                (tenant_id,receipt_sha256,object_id,revision,
                 engine,schema_id,source_digests_json,receipt_json,verification)
                VALUES (qr_private.authenticated_tenant(),%s,%s,%s,
                        %s,%s,%s::jsonb,%s::jsonb,'UNVERIFIED_EXTERNAL_RESULT')
                ON CONFLICT (tenant_id,receipt_sha256) DO NOTHING
            """,(h,object_id,revision,engine,classification["schema"],
                 canonical_bytes(classification["source_digests"]).decode("utf-8"),
                 canonical_bytes(receipt).decode("utf-8")))
        return {**classification,"receipt_sha256":h}

    def read_edges(self, source_id: str, revision: str,
                   *, limit: int = 100) -> list[dict]:
        """Tenant RLS + bounded outgoing graph edges; not a public read API."""
        if type(limit) is not int or not 1 <= limit <= 1001:
            raise ValueError("Bounded edge lookup required")
        rows=self.db.execute("""
          SELECT edge_id,layer,from_id,from_revision,to_id,to_revision,
                 relation,properties_json
          FROM qr_store.semantic_edges
          WHERE tenant_id=qr_private.authenticated_tenant()
                AND from_id=%s AND from_revision=%s
          ORDER BY edge_id LIMIT %s
        """,(source_id,revision,limit)).fetchall()
        return [{
            "edge_id":row[0],"layer":row[1],
            "from_id":row[2],"from_revision":row[3],
            "to_id":row[4],"to_revision":row[5],
            "relation":row[6],"properties":row[7],
        } for row in rows]
