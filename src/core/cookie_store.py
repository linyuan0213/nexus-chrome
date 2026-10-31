"""Cookie 共享存储 — 线程安全，按域名隔离。每个 Session 持有独立实例。"""

from threading import RLock
from time import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger


class CookieStore:
    def __init__(self):
        self._lock = RLock()
        self._store: Dict[str, List[Dict[str, Any]]] = {}

    def store(self, domain: str, cookies: List[Dict[str, Any]]) -> None:
        if not domain or not cookies:
            return
        with self._lock:
            self._prune_expired(domain)
            existing = {c.get("name"): c for c in self._store.get(domain, [])}
            for cookie in cookies:
                name = cookie.get("name")
                if name:
                    existing[name] = dict(cookie)
            self._store[domain] = list(existing.values())
            logger.debug(f"CookieStore: 存储 {len(cookies)} 个 Cookie → {domain}")

    def store_from_url(self, url: str, cookies: List[Dict[str, Any]]) -> None:
        domain = urlparse(url).netloc
        self.store(domain, cookies)

    def _prune_expired(self, domain: str | None = None) -> None:
        now = time()
        domains = [domain] if domain else list(self._store)
        for current in domains:
            remaining = [
                cookie
                for cookie in self._store.get(current, [])
                if not cookie.get("expires") or float(cookie["expires"]) > now
            ]
            if remaining:
                self._store[current] = remaining
            else:
                self._store.pop(current, None)

    def get(self, domain: str) -> List[Dict[str, Any]]:
        with self._lock:
            self._prune_expired(domain)
            return list(self._store.get(domain, []))

    def get_for_url(self, url: str) -> List[Dict[str, Any]]:
        domain = urlparse(url).netloc
        return self.get(domain)

    def as_header(self, domain: str) -> str:
        cookies = self.get(domain)
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))

    def as_header_for_url(self, url: str) -> str:
        return self.as_header(urlparse(url).netloc)

    def as_dict(self, domain: str) -> Dict[str, str]:
        cookies = self.get(domain)
        return {c["name"]: c["value"] for c in cookies if c.get("name")}

    def as_full_dict(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return {d: self.as_dict(d) for d in self._store}

    def list_domains(self) -> List[str]:
        with self._lock:
            return list(self._store.keys())

    def clear(self, domain: Optional[str] = None) -> None:
        with self._lock:
            if domain:
                self._store.pop(domain, None)
            else:
                self._store.clear()

    def delete_cookie(self, domain: str, name: str) -> bool:
        """按域名+名称删除单个 Cookie（镜像存储级）。返回是否实际删除。"""
        with self._lock:
            cookies = self._store.get(domain, [])
            remaining = [c for c in cookies if c.get("name") != name]
            if len(remaining) == len(cookies):
                return False
            if remaining:
                self._store[domain] = remaining
            else:
                self._store.pop(domain, None)
            logger.debug(f"CookieStore: 删除 Cookie → {domain}/{name}")
            return True
