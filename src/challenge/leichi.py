"""雷池（SafeLine）WAF 挑战解析器。"""

import time

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.challenge.base import ChallengeResolver
from src.config.settings import CHALLENGE_TYPE_LEICHI, LEICHI_SELECTORS


class LeichiResolver(ChallengeResolver):
    @property
    def challenge_type(self) -> str:
        return CHALLENGE_TYPE_LEICHI

    def detect(self, tab: ChromiumTab) -> bool:
        try:
            html = tab.html
        except Exception:
            return False
        if not html:
            return False
        doc = pq(html)
        for selector in LEICHI_SELECTORS:
            if doc(selector):
                return True
        title = str(doc("title").text()).lower()  # type: ignore
        return any(kw in title for kw in ("雷池", "安全拦截", "访问验证"))

    def resolve(self, tab: ChromiumTab, timeout: int = 30) -> bool:
        logger.debug("检测到雷池 WAF 挑战，等待验证...")
        deadline = time.monotonic() + timeout
        tab.wait(5)
        while time.monotonic() < deadline:
            if not self.detect(tab):
                logger.debug("雷池挑战已通过")
                return True
            tab.wait(1)
        return False
