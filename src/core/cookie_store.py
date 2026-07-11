"""Cookie 共享存储 — 线程安全，按域名隔离。每个 Session 持有独立实例。"""

from threading import RLock
from typing import Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger


class CookieStore:
    def __init__(self):
        self._lock = RLock()
        self._store: Dict[str, List[Dict[str, str]]] = {}

    def store(self, domain: str, cookies: List[Dict[str, str]]) -> None:
        if not domain or not cookies:
            return
        with self._lock:
            existing = {c.get("name"): c for c in self._store.get(domain, [])}
            for c in cookies:
                name = c.get("name")
                if name:
                    existing[name] = c
            self._store[domain] = list(existing.values())
            logger.debug(f"CookieStore: 存储 {len(cookies)} 个 Cookie → {domain}")

    def store_from_url(self, url: str, cookies: List[Dict[str, str]]) -> None:
        domain = urlparse(url).netloc
        self.store(domain, cookies)

    def get(self, domain: str) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._store.get(domain, []))

    def get_for_url(self, url: str) -> List[Dict[str, str]]:
        domain = urlparse(url).netloc
        return self.get(domain)

    def as_header(self, domain: str) -> str:
        cookies = self.get(domain)
        return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name"))

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
