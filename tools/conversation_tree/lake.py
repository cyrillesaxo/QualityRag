"""Tenant-scoped conversation lake (US-080, local reference).

Raw zone: one append-only conversation database per tenant and conversation. Derived zone:
the span index, rebuildable from the raw zone. Deletion writes a tombstone, removes the raw
file and cannot be undone or reused.

This is a local SQLite reference, not the PostgreSQL tenant ledger. The ``principal`` is
supplied by the caller: the host must authenticate it. Encryption at rest and retention
policy are NOT implemented here.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from tools.activation_runtime.common import identity

from .tree import ConversationTree, _at


class ConversationLake:
    def __init__(self, root):
        self.root = Path(root)
        (self.root / "tenants").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.root / "lake.sqlite"), timeout=5)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS lake_conversations(
            tenant TEXT NOT NULL, conversation_id TEXT NOT NULL, created_at TEXT NOT NULL,
            created_by TEXT NOT NULL, tombstoned_at TEXT, tombstoned_by TEXT,
            PRIMARY KEY(tenant, conversation_id));
        CREATE TRIGGER IF NOT EXISTS lake_no_delete BEFORE DELETE ON lake_conversations
          BEGIN SELECT RAISE(ABORT,'append-only'); END;
        """)

    def close(self):
        self.db.close()

    @staticmethod
    def _principal(principal):
        try:
            return identity(principal["tenant"]), identity(principal["subject"])
        except (TypeError, KeyError, ValueError):
            raise PermissionError("Authenticated principal with tenant and subject required") from None

    def _path(self, tenant, conversation_id):
        return self.root / "tenants" / tenant / (identity(conversation_id) + ".sqlite")

    def _row(self, tenant, conversation_id):
        # A conversation in another tenant looks exactly like one that does not exist.
        row = self.db.execute(
            "SELECT tombstoned_at FROM lake_conversations WHERE tenant=? AND conversation_id=?",
            (tenant, identity(conversation_id))).fetchone()
        if row is None:
            raise LookupError("Unknown conversation")
        if row[0] is not None:
            raise LookupError("Conversation deleted")

    def create(self, *, principal, conversation_id, at):
        tenant, subject = self._principal(principal)
        path = self._path(tenant, conversation_id)
        with self.db:
            try:
                self.db.execute("INSERT INTO lake_conversations(tenant,conversation_id,created_at,created_by)"
                                " VALUES(?,?,?,?)", (tenant, conversation_id, _at(at), subject))
            except sqlite3.IntegrityError:
                raise ValueError("Conversation ID already used in this tenant") from None
        path.parent.mkdir(parents=True, exist_ok=True)
        return ConversationTree(str(path))

    def open(self, *, principal, conversation_id):
        tenant, _ = self._principal(principal)
        self._row(tenant, conversation_id)
        return ConversationTree(str(self._path(tenant, conversation_id)))

    def list(self, *, principal):
        tenant, _ = self._principal(principal)
        return [r[0] for r in self.db.execute(
            "SELECT conversation_id FROM lake_conversations WHERE tenant=? AND tombstoned_at IS NULL"
            " ORDER BY conversation_id", (tenant,))]

    def delete(self, *, principal, conversation_id, at):
        """Tombstone a conversation and remove its raw and derived data."""
        tenant, subject = self._principal(principal)
        self._row(tenant, conversation_id)
        with self.db:
            self.db.execute("UPDATE lake_conversations SET tombstoned_at=?, tombstoned_by=?"
                            " WHERE tenant=? AND conversation_id=?", (_at(at), subject, tenant, conversation_id))
        path = self._path(tenant, conversation_id)
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        return {"tenant": tenant, "conversation_id": conversation_id, "status": "TOMBSTONED",
                "receipts": "INVALIDATED"}

    def receipt_usable(self, *, principal, conversation_id, receipt):
        """A receipt for a deleted or foreign conversation is never usable."""
        from .receipts import receipt_status
        try:
            tree = self.open(principal=principal, conversation_id=conversation_id)
        except LookupError as exc:
            return {"status": "STALE", "reasons": [str(exc).upper().replace(" ", "_")]}
        try:
            return receipt_status(tree, receipt)
        finally:
            tree.close()
