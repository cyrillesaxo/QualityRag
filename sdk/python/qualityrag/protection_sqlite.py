"""Durable SQLite policy and nonce stores for a single deployment boundary.

Experimental persistence layer. Atomic across processes sharing a SQLite file
on a filesystem with correct SQLite locking; NOT a distributed policy service.
Do not use on unreliable network filesystems or with real cardholder data.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .protection import ProtectionDenied


class _SQLiteBase:
    def __init__(self, path: str | Path) -> None:
        if not isinstance(path, (str, Path)) or not str(path):
            raise ProtectionDenied("INVALID_STORE_PATH")
        # All processes must use the *same* database file. Do not accept this
        # path from an untrusted request; configuration is service-owned.
        self._path = str(path)
        try:
            with self._connect() as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA busy_timeout=5000")
                self._initialize(db)
        except sqlite3.Error as exc:
            raise ProtectionDenied("STORE_UNAVAILABLE") from exc

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def _initialize(self, db: sqlite3.Connection) -> None:
        raise NotImplementedError


class SQLitePolicyAuthority(_SQLiteBase):
    """Durable policy version high-water mark and active/revoked state."""

    def _initialize(self, db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE IF NOT EXISTS protection_policy (
                tenant TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                highest_version INTEGER NOT NULL CHECK(highest_version > 0),
                active_version INTEGER,
                PRIMARY KEY (tenant, policy_id)
            )
        """)

    def publish(self, *, tenant: str, policy_id: str, version: int) -> None:
        if (not isinstance(tenant, str) or not tenant
            or not isinstance(policy_id, str) or not policy_id
            or type(version) is not int or version < 1):
            raise ProtectionDenied("INVALID_POLICY_VERSION")
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT highest_version FROM protection_policy "
                    "WHERE tenant=? AND policy_id=?", (tenant, policy_id)).fetchone()
                if row is not None and version <= row[0]:
                    raise ProtectionDenied("NON_MONOTONIC_POLICY_VERSION")
                db.execute(
                    "INSERT INTO protection_policy "
                    "(tenant, policy_id, highest_version, active_version) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(tenant, policy_id) DO UPDATE SET "
                    "highest_version=excluded.highest_version, "
                    "active_version=excluded.active_version",
                    (tenant, policy_id, version, version))
                db.commit()
        except sqlite3.Error as exc:
            raise ProtectionDenied("STORE_UNAVAILABLE") from exc

    def revoke(self, *, tenant: str, policy_id: str) -> None:
        if not tenant or not policy_id:
            raise ProtectionDenied("INVALID_POLICY_VERSION")
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE protection_policy SET active_version=NULL "
                    "WHERE tenant=? AND policy_id=?", (tenant, policy_id))
                db.commit()
        except sqlite3.Error as exc:
            raise ProtectionDenied("STORE_UNAVAILABLE") from exc

    def require_active(self, *, tenant: str, policy_id: str, version: int) -> None:
        if (not isinstance(tenant, str) or not isinstance(policy_id, str)
            or type(version) is not int):
            raise ProtectionDenied("POLICY_NOT_ACTIVE")
        try:
            with self._connect() as db:
                row = db.execute(
                    "SELECT active_version FROM protection_policy "
                    "WHERE tenant=? AND policy_id=?", (tenant, policy_id)).fetchone()
        except sqlite3.Error as exc:
            raise ProtectionDenied("STORE_UNAVAILABLE") from exc
        if row is None or row[0] != version:
            raise ProtectionDenied("POLICY_NOT_ACTIVE")


class SQLiteReplayStore(_SQLiteBase):
    """Atomic one-use nonce ledger across processes using the same DB file."""

    def _initialize(self, db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE IF NOT EXISTS protection_consumed_nonce (
                nonce TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL
            )
        """)

    def consume(self, nonce: str, expires_at: int, now: int) -> bool:
        if (not isinstance(nonce, str) or not nonce
            or type(expires_at) is not int or type(now) is not int
            or expires_at < now):
            return False
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                # Expired nonces are purged only after expiration; valid
                # receipts cannot be replayed during their validity window.
                db.execute(
                    "DELETE FROM protection_consumed_nonce WHERE expires_at < ?",
                    (now,))
                cursor = db.execute(
                    "INSERT OR IGNORE INTO protection_consumed_nonce "
                    "(nonce, expires_at) VALUES (?, ?)", (nonce, expires_at))
                accepted = cursor.rowcount == 1
                db.commit()
                return accepted
        except sqlite3.Error as exc:
            raise ProtectionDenied("STORE_UNAVAILABLE") from exc
