"""通用 WAF 挑战解析器 — 兜底方案，等待页面自动完成验证。"""

import time

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.challenge.base import ChallengeResolver
from src.config.settings import (
    CHALLENGE_SELECTORS,
    CHALLENGE_TITLES,
    CHALLENGE_TYPE_GENERIC,
    GENERIC_CHALLENGE_SELECTORS,
)


class GenericResolver(ChallengeResolver):
    @property
    def challenge_type(self) -> str:
        return CHALLENGE_TYPE_GENERIC

    def detect(self, tab: ChromiumTab) -> bool:
        try:
            html = tab.html
        except Exception:
            return False
        if not html:
            return False
        doc = pq(html)
        title = str(doc("title").text()).lower()  # type: ignore
        for t in CHALLENGE_TITLES:
            if t.lower() == title:
                return True
        for selector in CHALLENGE_SELECTORS + GENERIC_CHALLENGE_SELECTORS:
            if doc(selector):
                return True
        return False

    def resolve(self, tab: ChromiumTab, timeout: int = 30) -> bool:
        logger.debug("检测到通用 WAF 挑战，等待页面处理...")
        deadline = time.monotonic() + timeout
        tab.wait(5)
        while time.monotonic() < deadline:
            if not self.detect(tab):
                logger.debug("通用挑战已通过")
                return True
            tab.wait(1)
        return False
