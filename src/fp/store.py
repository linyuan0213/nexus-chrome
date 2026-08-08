"""SQLite 存储层 — 画像、版本历史、审计日志、节点心跳。

线程安全：sqlite3 连接 + 全局锁；所有写操作串行。
"""

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.fp.profile import RolloutRule


class Store:
    def __init__(self, db_path: str | None = None):
        db_path = db_path or os.getenv("FP_CENTER_DB", "data/fp_config_center.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    version INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    rollout TEXT NOT NULL DEFAULT '{}',
                    fingerprint TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    operator TEXT NOT NULL DEFAULT 'admin'
                );
                CREATE TABLE IF NOT EXISTS profile_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    rollout TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    operator TEXT NOT NULL DEFAULT 'admin'
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operator TEXT NOT NULL,
                    action TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    version INTEGER,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    profile_id TEXT,
                    profile_version INTEGER,
                    browser TEXT,
                    fp_snapshot TEXT,
                    last_seen TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_versions_profile ON profile_versions(profile_id, version);
                """
            )
            self._conn.commit()

    def reset(self) -> None:
        """清空全部数据（测试用）。"""
        with self._lock:
            self._conn.executescript(
                "DELETE FROM profiles; DELETE FROM profile_versions; DELETE FROM audit_log; DELETE FROM nodes;"
            )
            self._conn.commit()

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    # ---- 画像 ----

    def list_profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM profiles ORDER BY profile_id").fetchall()
        return [self._summary(r) for r in rows]

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
        return self._row_to_profile(row) if row else None

    def get_profile_version(self, profile_id: str, version: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM profile_versions WHERE profile_id=? AND version=?",
                (profile_id, version),
            ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row["profile_id"],
            "version": row["version"],
            "rollout": json.loads(row["rollout"]),
            "fingerprint": json.loads(row["fingerprint"]),
        }

    def create_or_update(self, data: dict[str, Any], operator: str = "admin") -> dict[str, Any]:
        """创建新画像或更新为新版本（version+1），并写入历史版本。"""
        profile_id = data["profile_id"]
        now = self._now()
        with self._lock:
            existing = self._conn.execute("SELECT version FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            version = (existing["version"] + 1) if existing else 1
            rollout = json.dumps(data.get("rollout", {}))
            fingerprint = json.dumps(data["fingerprint"])
            self._conn.execute(
                "INSERT INTO profiles (profile_id, name, version, enabled, rollout, fingerprint, updated_at, operator) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(profile_id) DO UPDATE SET name=excluded.name, version=excluded.version, "
                "enabled=excluded.enabled, rollout=excluded.rollout, fingerprint=excluded.fingerprint, "
                "updated_at=excluded.updated_at, operator=excluded.operator",
                (
                    profile_id,
                    data.get("name", ""),
                    version,
                    int(data.get("enabled", True)),
                    rollout,
                    fingerprint,
                    now,
                    operator,
                ),
            )
            self._conn.execute(
                "INSERT INTO profile_versions (profile_id, version, rollout, fingerprint, created_at, operator) "
                "VALUES (?,?,?,?,?,?)",
                (profile_id, version, rollout, fingerprint, now, operator),
            )
            self._audit_locked(operator, "update", profile_id, version, f"create_or_update -> v{version}")
            self._conn.commit()
        return {"profile_id": profile_id, "version": version}

    def rollback(self, profile_id: str, to_version: int, operator: str = "admin") -> dict[str, Any] | None:
        """回滚到指定历史版本。"""
        with self._lock:
            version_row = self._conn.execute(
                "SELECT * FROM profile_versions WHERE profile_id=? AND version=?",
                (profile_id, to_version),
            ).fetchone()
            if not version_row:
                return None
            now = self._now()
            self._conn.execute(
                "UPDATE profiles SET version=?, rollout=?, fingerprint=?, updated_at=?, operator=? WHERE profile_id=?",
                (version_row["version"], version_row["rollout"], version_row["fingerprint"], now, operator, profile_id),
            )
            self._audit_locked(operator, "rollback", profile_id, to_version, f"rollback -> v{to_version}")
            self._conn.commit()
        return {"profile_id": profile_id, "version": to_version}

    def update_rollout(self, profile_id: str, rollout: RolloutRule, operator: str = "admin") -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT profile_id FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            if not row:
                return None
            now = self._now()
            self._conn.execute(
                "UPDATE profiles SET rollout=?, updated_at=?, operator=? WHERE profile_id=?",
                (rollout.model_dump_json(), now, operator, profile_id),
            )
            self._audit_locked(operator, "gray", profile_id, None, f"rollout={rollout.model_dump_json()}")
            self._conn.commit()
        return {"profile_id": profile_id, "rollout": rollout.model_dump()}

    def get_versions(self, profile_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT version, created_at, operator FROM profile_versions WHERE profile_id=? ORDER BY version DESC",
                (profile_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- 节点心跳 ----

    def upsert_node(self, node_id: str, data: dict[str, Any]) -> None:
        now = self._now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO nodes (node_id, profile_id, profile_version, browser, fp_snapshot, last_seen) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(node_id) DO UPDATE SET profile_id=excluded.profile_id, "
                "profile_version=excluded.profile_version, browser=excluded.browser, "
                "fp_snapshot=excluded.fp_snapshot, last_seen=excluded.last_seen",
                (
                    node_id,
                    data.get("profile_id"),
                    data.get("profile_version"),
                    data.get("browser"),
                    data.get("fp_snapshot"),
                    now,
                ),
            )
            self._conn.commit()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    def get_profile_version_number(self, profile_id: str) -> int | None:
        with self._lock:
            row = self._conn.execute("SELECT version FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
        return row["version"] if row else None

    # ---- 内部 ----

    def _audit_locked(self, operator: str, action: str, profile_id: str, version: int | None, detail: str) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (operator, action, profile_id, version, detail, created_at) VALUES (?,?,?,?,?,?)",
            (operator, action, profile_id, version, detail, self._now()),
        )

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "profile_id": row["profile_id"],
            "name": row["name"],
            "version": row["version"],
            "enabled": bool(row["enabled"]),
            "rollout": json.loads(row["rollout"]),
        }

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "profile_id": row["profile_id"],
            "name": row["name"],
            "version": row["version"],
            "enabled": bool(row["enabled"]),
            "rollout": json.loads(row["rollout"]),
            "fingerprint": json.loads(row["fingerprint"]),
            "updated_at": row["updated_at"],
        }


store = Store()
