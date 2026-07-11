"""挑战编排器 — 检测 → 识别 → 解析 → 验证 流水线。"""

import time
from typing import Any, Dict, List, Optional

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.challenge.base import ChallengeResolver
from src.challenge.cloudflare import CloudflareResolver
from src.challenge.five_second_shield import FiveSecondShieldResolver
from src.challenge.generic import GenericResolver
from src.challenge.leichi import LeichiResolver
from src.config.settings import CHALLENGE_TYPE_NONE


class ChallengeOrchestrator:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._resolvers: List[ChallengeResolver] = [
            CloudflareResolver(),
            FiveSecondShieldResolver(),
            LeichiResolver(),
            GenericResolver(),
        ]

    def detect(self, tab: ChromiumTab) -> Optional[ChallengeResolver]:
        """检测当前页面面临的挑战类型。"""
        for resolver in self._resolvers:
            if resolver.detect(tab):
                logger.info(f"检测到挑战类型: {resolver.challenge_type}")
                return resolver
        return None

    def resolve(self, tab: ChromiumTab) -> Dict[str, Any]:
        """尝试解析当前页面的挑战。返回挑战结果字典。"""
        start = time.monotonic()
        deadline = start + self.timeout

        resolver = self.detect(tab)
        if resolver is None:
            return {
                "detected": False,
                "type": CHALLENGE_TYPE_NONE,
                "solved": True,
                "duration_ms": 0,
            }

        remaining = max(1, deadline - time.monotonic())
        success = resolver.resolve(tab, timeout=int(remaining))
        if success:
            try:
                tab.wait(2)
            except BaseException:
                logger.debug("tab.wait 被中断，继续后续验证")

        duration_ms = int((time.monotonic() - start) * 1000)
        result = {
            "detected": True,
            "type": resolver.challenge_type,
            "solved": success,
            "duration_ms": duration_ms,
        }
        logger.info(f"挑战处理结果: {result}")
        return result
