"""五秒盾挑战解析器 — 等待 JS 倒计时完成后页面自动跳转。"""

import time

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.challenge.base import ChallengeResolver
from src.config.settings import CHALLENGE_TYPE_FIVE_SECOND, FIVE_SECOND_SELECTORS


class FiveSecondShieldResolver(ChallengeResolver):
    @property
    def challenge_type(self) -> str:
        return CHALLENGE_TYPE_FIVE_SECOND

    def detect(self, tab: ChromiumTab) -> bool:
        try:
            html = tab.html
        except Exception:
            return False
        if not html:
            return False
        doc = pq(html)
        for selector in FIVE_SECOND_SELECTORS:
            if doc(selector):
                return True
        title = str(doc("title").text()).lower()  # type: ignore
        return any(kw in title for kw in ("安全检查", "安全验证", "请等待", "loading"))

    def resolve(self, tab: ChromiumTab, timeout: int = 30) -> bool:
        logger.debug("检测到五秒盾，等待 JS 倒计时完成...")
        deadline = time.monotonic() + timeout
        tab.wait(5)
        while time.monotonic() < deadline:
            if not self.detect(tab):
                logger.debug("五秒盾挑战已通过")
                return True
            tab.wait(1)
        return False
