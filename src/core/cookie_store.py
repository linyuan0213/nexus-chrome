"""Cookie 共享存储 — 线程安全，按域名隔离。每个 Session 持有独立实例。"""

from threading import RLock
from time import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger


def _cookie_key(cookie: Dict[str, Any], default_domain: str = "") -> tuple[str, str, str]:
    """Cookie 唯一键：domain/path/name；同名不同路径不能互相覆盖。"""
    name = str(cookie.get("name") or "")
    domain = str(cookie.get("domain") or default_domain or "").lstrip(".").lower()
    path = str(cookie.get("path") or "/")
    return domain, path, name


def _path_matches(request_path: str, cookie_path: str) -> bool:
    path = cookie_path or "/"
    if path == "/":
        return True
    return request_path == path or request_path.startswith(path.rstrip("/") + "/")


class CookieStore:
    def __init__(self):
        self._lock = RLock()
        self._store: Dict[str, List[Dict[str, Any]]] = {}

    def store(self, domain: str, cookies: List[Dict[str, Any]]) -> None:
        if not domain or not cookies:
            return
        with self._lock:
            self._prune_expired(domain)
            existing = {_cookie_key(c, domain): c for c in self._store.get(domain, [])}
            for cookie in cookies:
                if not cookie.get("name"):
                    continue
                item = dict(cookie)
                item.setdefault("domain", domain)
                item.setdefault("path", "/")
                existing[_cookie_key(item, domain)] = item
            self._store[domain] = list(existing.values())
            logger.debug(f"CookieStore: 存储 {len(cookies)} 个 Cookie → {domain}")

    def store_from_url(self, url: str, cookies: List[Dict[str, Any]]) -> None:
        domain = urlparse(url).netloc
        self.store(domain, cookies)

    def reconcile(self, domain: str, cookies: List[Dict[str, Any]]) -> None:
        """用浏览器当前完整 Cookie 列表覆盖域内镜像，删除已失效的旧 Cookie."""
        if not domain:
            return
        with self._lock:
            incoming = {
                _cookie_key(c, domain): {**c, "domain": c.get("domain") or domain, "path": c.get("path") or "/"}
                for c in cookies
                if c.get("name")
            }
            self._store[domain] = list(incoming.values())
            self._prune_expired(domain)

    def _prune_expired(self, domain: str | None = None) -> None:
        now = time()
        domains = [domain] if domain else list(self._store)
        for current in domains:
            remaining: List[Dict[str, Any]] = []
            for cookie in self._store.get(current, []):
                expires = cookie.get("expires")
                if expires is None:
                    remaining.append(cookie)
                    continue
                try:
                    if float(expires) > now:
                        remaining.append(cookie)
                except (TypeError, ValueError):
                    remaining.append(cookie)
            if remaining:
                self._store[current] = remaining
            else:
                self._store.pop(current, None)

    def get(self, domain: str) -> List[Dict[str, Any]]:
        with self._lock:
            self._prune_expired(domain)
            return list(self._store.get(domain, []))

    def get_for_url(self, url: str) -> List[Dict[str, Any]]:
        parsed = urlparse(url)
        domain = parsed.netloc
        path = parsed.path or "/"
        return [c for c in self.get(domain) if _path_matches(path, str(c.get("path") or "/"))]

    def as_header(self, domain: str) -> str:
        cookies = self.get(domain)
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))

    def as_header_for_url(self, url: str) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in self.get_for_url(url) if c.get("name"))

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

    def delete_cookie(self, domain: str, name: str, path: str | None = None) -> bool:
        """按域名+名称（可选路径）删除单个 Cookie。返回是否实际删除。"""
        with self._lock:
            cookies = self._store.get(domain, [])
            remaining = [
                c
                for c in cookies
                if not (c.get("name") == name and (path is None or str(c.get("path") or "/") == path))
            ]
            if len(remaining) == len(cookies):
                return False
            if remaining:
                self._store[domain] = remaining
            else:
                self._store.pop(domain, None)
            logger.debug(f"CookieStore: 删除 Cookie → {domain}/{name}")
            return True
