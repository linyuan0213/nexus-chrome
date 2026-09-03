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
        """解析当前页面的挑战（支持多层 WAF：如 CF 后接雷池，逐层解决）。

        每次检测到拦截页挑战就解决，然后等待页面跳转并重新检测，直到没有
        拦截页挑战（此时若页面内嵌 Turnstile 组件则一并处理）或超时。
        """
        start = time.monotonic()
        deadline = start + self.timeout
        layers: List[str] = []

        while time.monotonic() < deadline:
            # 预算即将耗尽时不再发起新一轮检测/求解（避免卡在超时临界点）
            if deadline - time.monotonic() < 3:
                break
            resolver = self.detect(tab)
            if resolver is None:
                # 无拦截页挑战：尝试解决业务页面内嵌的 Turnstile 组件（如签到页）。
                remaining = max(1, int(deadline - time.monotonic()))
                embedded_ok = self._solve_embedded_turnstile(tab, remaining)
                duration_ms = int((time.monotonic() - start) * 1000)
                return {
                    "detected": bool(layers),
                    "type": ",".join(layers) if layers else CHALLENGE_TYPE_NONE,
                    "solved": True,
                    "duration_ms": duration_ms,
                    "layers": layers,
                    "embedded_turnstile": embedded_ok,
                }

            layers.append(resolver.challenge_type)
            remaining = max(1, deadline - time.monotonic())
            success = resolver.resolve(tab, timeout=int(remaining))
            if not success:
                duration_ms = int((time.monotonic() - start) * 1000)
                result = {
                    "detected": True,
                    "type": ",".join(layers),
                    "solved": False,
                    "duration_ms": duration_ms,
                    "layers": layers,
                }
                logger.info(f"挑战处理结果: {result}")
                return result

            # 当前层已解决：等待页面跳转，可能进入下一层（如 CF 后接雷池）。
            try:
                tab.wait(2)
            except BaseException:
                logger.debug("tab.wait 被中断，继续下一层检测")

        duration_ms = int((time.monotonic() - start) * 1000)
        result = {
            "detected": True,
            "type": ",".join(layers),
            "solved": False,
            "duration_ms": duration_ms,
            "layers": layers,
        }
        logger.info(f"挑战处理结果(超时): {result}")
        return result

    def _solve_embedded_turnstile(self, tab: ChromiumTab, timeout: int) -> bool:
        """尽力解决页面内嵌的 Turnstile 组件，不影响主流程。"""
        try:
            return CloudflareResolver().solve_embedded_widget(tab, timeout=timeout)
        except Exception as e:
            logger.warning(f"内嵌 Turnstile 组件处理失败: {e}")
            return False
