"""m3u8 播放列表探测与解析 mixin。"""

import os
from typing import Any, Dict
from urllib.parse import urlparse

from loguru import logger

from src.core.session.download import DownloadMixin


class MediaMixin(DownloadMixin):
    """抓取并解析 m3u8 播放列表（主列表 / 媒体列表）。"""

    def detect_m3u8(self, url: str, timeout: int = 30) -> Dict[str, Any]:
        """抓取并解析 m3u8 播放列表（支持主列表与媒体列表）。

        Returns:
            {"url", "type": "master"|"media"|"unknown", "streams": [{bandwidth, resolution, url}],
             "segments": [{duration, url}], "raw"(截断)}
        """
        self.touch()
        domain = urlparse(url).netloc
        # 先确保已过盾（同域导航），再用浏览器下载管理器取播放列表（跨域可靠）
        try:
            if self._active_tab_name is None or urlparse(self._get_active_tab().url).netloc != domain:  # type: ignore[union-attr]
                self._browser_fetch_get(url, self.cookie_store.as_header(domain), None, timeout=min(timeout, 20))
        except Exception as e:
            logger.debug(f"[Session:{self.id}] m3u8 过盾导航失败(可忽略): {e}")
        tab = self._get_active_tab()
        try:
            tab_any: Any = tab
            mission: Any = tab_any._download_by_browser(url, save_path="/tmp", timeout=timeout)
            if mission is not None:
                mission.wait(timeout)
                path = mission.final_path or getattr(mission, "path", "")
                if path and os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        body = f.read()
                    if "EXTM3U" in body:
                        return self._parse_m3u8(url, body)
        except Exception as e:
            logger.debug(f"[Session:{self.id}] m3u8 浏览器下载失败({e})")
        return {"url": url, "type": "unknown", "streams": [], "segments": [], "raw": ""}

    @staticmethod
    def _parse_m3u8(base_url: str, body: str) -> Dict[str, Any]:
        """解析 m3u8 文本（主列表含 EXT-X-STREAM-INF；媒体列表含 EXTINF 分片）。"""

        base_dir = base_url.rsplit("/", 1)[0] if "/" in base_url else ""
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        streams: list[Dict[str, Any]] = []
        segments: list[Dict[str, Any]] = []
        cur_stream: Dict[str, Any] = {}
        cur_duration = 0.0

        def resolve(u: str) -> str:
            if u.startswith("http"):
                return u
            return f"{base_dir}/{u.lstrip('/')}" if base_dir else u

        for ln in lines:
            if ln.startswith("#EXT-X-STREAM-INF"):
                attrs: Dict[str, Any] = {}
                for kv in ln.replace("#EXT-X-STREAM-INF:", "").split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        attrs[k] = v.strip('"')
                cur_stream = {
                    "bandwidth": attrs.get("BANDWIDTH", ""),
                    "resolution": attrs.get("RESOLUTION", ""),
                    "codecs": attrs.get("CODECS", ""),
                    "url": "",
                }
            elif ln.startswith("#EXTINF"):
                try:
                    cur_duration = float(ln.replace("#EXTINF:", "").split(",")[0])
                except ValueError:
                    cur_duration = 0.0
            elif ln.startswith("#"):
                continue
            else:
                if cur_stream:
                    cur_stream["url"] = resolve(ln)
                    streams.append(cur_stream)
                    cur_stream = {}
                else:
                    segments.append({"duration": round(cur_duration, 3), "url": resolve(ln)})
                    cur_duration = 0.0

        ptype = "master" if streams else ("media" if segments else "unknown")
        return {
            "url": base_url,
            "type": ptype,
            "streams": streams[:50],
            "segments": segments[:500] if ptype == "media" else segments[:50],
            "segment_count": len(segments),
        }
