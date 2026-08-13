"""Cloudflare 挑战解析器 — 标准挑战 + Turnstile 盒子 + Managed Challenge。

核心原则：只有真正的 Cloudflare 拦截页（interstitial）才算作“挑战”。
普通业务页面（如签到页）上内嵌的 Turnstile 组件不是挑战，不应被点击或干扰。
"""

import time

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.challenge.base import ChallengeResolver
from src.config.settings import (
    CF_CHALLENGE_SELECTORS,
    CHALLENGE_TYPE_CLOUDFLARE,
)
from src.utils.challenge_utils import (
    locate_turnstile_box,
    sync_cf_box_retry,
    sync_cf_retry,
    turnstile_click,
    turnstile_token,
)

CF_TITLES = {"just a moment...", "请稍候…"}

# 现代 Cloudflare 拦截页独有的字符串标记（普通页面即使加载了
# /cdn-cgi/challenge-platform/... 脚本也不算拦截页，因此不包含
# “challenge-platform” 字样）。
_CF_INTERSTITIAL_MARKERS = (
    "_cf_chl_opt",
    'id="challenge-form"',
    'class="challenge-form"',
    'id="challenge-stage"',
    "cf-im-under-attack",
)


def _page_title(html_text: str) -> str:
    if not html_text:
        return ""
    return str(pq(html_text)("title").text()).lower()  # type: ignore


def _is_interstitial(html_text: str) -> bool:
    """是否为真正的 Cloudflare 拦截页，而非页面内嵌的 Turnstile 组件。"""
    if not html_text:
        return False
    if _page_title(html_text) in CF_TITLES:
        return True
    if any(marker in html_text for marker in _CF_INTERSTITIAL_MARKERS):
        return True
    doc = pq(html_text)
    for selector in CF_CHALLENGE_SELECTORS:
        if doc(selector):
            return True
    return False


def _under_cf_challenge(html_text: str) -> bool:
    return _is_interstitial(html_text)


def _under_cf_box_challenge(html_text: str) -> bool:
    """拦截页上的 Turnstile 盒子挑战（需点击）。普通页面内嵌组件不视为挑战。"""
    return _is_interstitial(html_text) and _is_turnstile_challenge(html_text)


def _is_managed_challenge(html_text: str) -> bool:
    """是否为 Cloudflare Managed Challenge（JS 自动求解）。仅在拦截页上才算。"""
    if not html_text or not _is_interstitial(html_text):
        return False
    if "challenges.cloudflare.com" in html_text:
        return True
    return bool(pq(html_text)('script[src*="challenges.cloudflare.com"]'))


def _is_turnstile_challenge(html_text: str) -> bool:
    """页面是否包含 Turnstile 响应输入（拦截页与内嵌组件均可能出现）。"""
    if not html_text:
        return False
    if "cf-turnstile-response" in html_text:
        return True
    return bool(pq(html_text)('input[name="cf-turnstile-response"]'))


class CloudflareResolver(ChallengeResolver):
    @property
    def challenge_type(self) -> str:
        return CHALLENGE_TYPE_CLOUDFLARE

    def detect(self, tab: ChromiumTab) -> bool:
        try:
            html = tab.html
        except Exception:
            return False
        return _under_cf_challenge(html) or _under_cf_box_challenge(html)

    def resolve(self, tab: ChromiumTab, timeout: int = 30) -> bool:
        """尝试解析 Cloudflare 挑战。"""
        try:
            tab.wait(1)
            html = tab.html
        except Exception:
            html = ""

        if not html:
            return self._wait_challenge_cleared(tab, timeout)

        # 非拦截页（例如内嵌 Turnstile 的签到页）无需处理，直接放行。
        if not _under_cf_challenge(html):
            return True

        # Managed Challenge（JS 自动求解）优先：托管拦截页也常内嵌
        # cf-turnstile-response，会误判为盒挑战，但托管页没有可点的复选框，
        # 只需等待 JS 自动完成，点击反而超时。
        if _is_managed_challenge(html):
            return self._wait_managed(tab, timeout)

        # Turnstile 盒子挑战：需点击盒子内复选框（非托管拦截页）。
        if _under_cf_box_challenge(html):
            return self._solve_box(tab, timeout)

        return self._solve_standard(tab, timeout)

    def _wait_challenge_cleared(self, tab: ChromiumTab, timeout: int) -> bool:
        """通用轮询：等待页面不再处于 Cloudflare 拦截状态。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                html = tab.html
            except Exception:
                html = ""
            if not _under_cf_challenge(html):
                return True
            time.sleep(1)
        return False

    def _wait_managed(self, tab: ChromiumTab, timeout: int) -> bool:
        """Managed Challenge：Cloudflare JS 自动求解，只需等待并轮询。"""
        logger.debug("Cloudflare Managed Challenge，等待 JS 自动求解...")
        return self._wait_challenge_cleared(tab, timeout)

    def _solve_standard(self, tab: ChromiumTab, timeout: int) -> bool:
        """标准 Cloudflare 挑战：尝试点击 Turnstile 复选框。"""
        logger.debug("Cloudflare 标准挑战，尝试点击验证按钮...")
        tries = max(1, min(timeout // 10, 2))
        success, _ = sync_cf_retry(tab, tries=tries)
        if success:
            return True
        # 兜底：再等待挑战自动清除
        return self._wait_challenge_cleared(tab, timeout)

    def _solve_box(self, tab: ChromiumTab, timeout: int) -> bool:
        """Turnstile 盒子挑战：尝试点击盒子内的验证按钮。"""
        logger.debug("Cloudflare Turnstile 盒子挑战，尝试点击...")
        tries = max(1, min(timeout // 10, 2))
        success, _ = sync_cf_box_retry(tab, tries=tries)
        if success:
            return True
        return self._wait_challenge_cleared(tab, timeout)

    def solve_embedded_widget(self, tab: ChromiumTab, timeout: int = 25) -> bool:
        """尝试解决业务页面内嵌的 Turnstile 组件（如签到页的“请验证您是真人”复选框）。

        非交互组件在可信浏览器下会自动生成 token 并触发 cfCallback 提交表单；
        若渲染出复选框，则点击组件 shadow root 内的复选框。组件消失（表单已
        提交）同样视为成功。

        Returns:
            是否完成（拿到 token 或表单已提交）。
        """
        deadline = time.monotonic() + timeout
        # 页面根本没有 Turnstile 组件也没有 token → 无需处理。
        if not turnstile_token(tab) and not self._widget_present(tab):
            logger.debug("页面无内嵌 Turnstile 组件，跳过")
            return False
        while time.monotonic() < deadline:
            if turnstile_token(tab):
                logger.info("内嵌 Turnstile 已生成 token，等待回调提交")
                return True
            if not self._widget_present(tab):
                logger.info("内嵌 Turnstile 组件已消失，表单可能已提交")
                return True
            box = locate_turnstile_box(tab)
            if box is not None and turnstile_click(tab, box):
                for _ in range(8):
                    if turnstile_token(tab):
                        logger.info("内嵌 Turnstile 点击后生成 token")
                        return True
                    if not self._widget_present(tab):
                        logger.info("内嵌 Turnstile 点击后组件消失，表单已提交")
                        return True
                    time.sleep(1)
            time.sleep(2)
        logger.warning("内嵌 Turnstile 组件在超时时间内未能完成")
        return False

    def _widget_present(self, tab: ChromiumTab) -> bool:
        try:
            return bool(tab.ele("css:.cf-turnstile", timeout=1))  # type: ignore[union-attr]
        except Exception:
            return False
