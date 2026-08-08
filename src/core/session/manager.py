"""SessionManager — 会话生命周期管理与持久化注册表。"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from DrissionPage import Chromium
from loguru import logger

from src.config.settings import MAX_SESSIONS, SESSION_TTL
from src.core.fingerprint import FingerprintManager
from src.core.session.events import publish_event
from src.core.session.session import Session


class SessionManager:
    def __init__(
        self,
        pool: Any,
        max_sessions: int = MAX_SESSIONS,
        session_ttl: int = SESSION_TTL,
        persist_file: Optional[str] = None,
    ):
        self._pool = pool
        self._sessions: Dict[str, Session] = {}
        self._max_sessions = max_sessions
        self._session_ttl = session_ttl
        self._persist_file = persist_file
        self._recovered: Dict[str, Dict[str, Any]] = {}
        self._load_persisted()

    @property
    def pool(self) -> Any:
        """浏览器实例池（供 services 层做实例路由）。"""
        return self._pool

    # ---------- P2-9 会话持久化 ----------

    def _load_persisted(self) -> None:
        """启动时加载持久化的会话注册表（供恢复/列出）。"""
        if not self._persist_file or not os.path.exists(self._persist_file):
            return
        try:
            with open(self._persist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for rec in data.get("sessions", []):
                self._recovered[rec["id"]] = rec
            logger.info(f"[SessionManager] 加载持久化会话注册表: {len(self._recovered)} 条")
        except Exception as e:
            logger.warning(f"[SessionManager] 加载持久化注册表失败: {e}")

    def _save_persisted(self) -> None:
        """将当前会话配置（含 Cookie 域）写入持久化文件。"""
        if not self._persist_file:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_file), exist_ok=True)
            recs: List[Dict[str, Any]] = []
            for rec in self._recovered.values():
                recs.append(rec)
            for s in self._sessions.values():
                recs.append(s.to_dict())
            # 去重（以 id 为准）
            by_id: Dict[str, Dict[str, Any]] = {r["id"]: r for r in recs}
            tmp = f"{self._persist_file}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"sessions": list(by_id.values())}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._persist_file)
        except Exception as e:
            logger.debug(f"[SessionManager] 持久化失败: {e}")

    def recovered_sessions(self) -> List[Dict[str, Any]]:
        """上次进程遗留、尚未重新创建的会话记录。"""
        return list(self._recovered.values())

    def forget_recovered(self, session_id: str) -> None:
        self._recovered.pop(session_id, None)
        self._save_persisted()

    # ---------- 会话生命周期 ----------

    def create(
        self,
        session_id: str,
        fingerprint_profile: Optional[str],
        user_agent: Optional[str],
        proxy: Optional[str],
        browser: Chromium,
        fp_profile_id: Optional[str] = None,
        fp_env: Optional[Dict[str, str]] = None,
        instance_key: Optional[str] = None,
    ) -> Session:
        """创建会话。

        browser 已由服务层绑定到对应指纹实例（core 不感知 fp 层）。
        fp_env 为解析后的指纹环境变量（用于网络层 UA 头一致性）。
        instance_key 为该会话使用的浏览器实例 key（用于释放时回收）。
        """
        if session_id in self._sessions:
            raise ValueError(f"会话 '{session_id}' 已存在")
        if len(self._sessions) >= self._max_sessions:
            oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].last_used_at)
            logger.warning(f"会话数量达到上限 {self._max_sessions}，移除最旧会话 {oldest_id}")
            self.delete(oldest_id)
        fingerprint = FingerprintManager(fingerprint_profile)
        session = Session(
            session_id=session_id,
            browser=browser,
            fingerprint=fingerprint,
            user_agent=user_agent,
            proxy=proxy,
            fp_profile_id=fp_profile_id,
            fp_env=fp_env,
        )
        session.instance_key = instance_key
        self._sessions[session_id] = session
        self._recovered.pop(session_id, None)
        self._save_persisted()
        publish_event("session_created", {"id": session_id, "fp_profile_id": fp_profile_id})
        return session

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise ValueError(f"会话 '{session_id}' 未找到")
        session = self._sessions[session_id]
        session.touch()
        return session

    def list_all(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._sessions.values()]

    def delete(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise ValueError(f"会话 '{session_id}' 未找到")
        session = self._sessions.pop(session_id)
        session.close()
        # 释放浏览器实例引用（无其他会话使用时回收实例，释放内存）
        if session.instance_key and self._pool is not None:
            try:
                self._pool.release(session.instance_key)
            except Exception as e:
                logger.debug(f"[SessionManager] 释放实例引用失败: {e}")
        self._save_persisted()
        publish_event("session_deleted", {"id": session_id})

    def delete_all(self) -> None:
        for sid in list(self._sessions.keys()):
            self.delete(sid)

    def delete_expired(self, max_idle_seconds: Optional[int] = None) -> int:
        """清理超过空闲时间的会话，返回清理数量。"""
        threshold = max_idle_seconds if max_idle_seconds is not None else self._session_ttl
        now = time.monotonic()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_used_at > threshold]
        for sid in expired:
            self.delete(sid)
        return len(expired)
