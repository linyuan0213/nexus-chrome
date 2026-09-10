"""Cloudflare 挑战解析器 — 标准挑战 + Turnstile 盒子 + Managed Challenge。

核心原则：只有真正的 Cloudflare 拦截页（interstitial）才算作“挑战”。
普通业务页面（如签到页）上内嵌的 Turnstile 组件不是挑战，不应被点击或干扰。
"""

import time
from typing import Optional

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.challenge.base import ChallengeResolver
from src.config.settings import (
    CF_CHALLENGE_SELECTORS,
    CHALLENGE_TYPE_CLOUDFLARE,
)
from src.utils.challenge_utils import (
    TurnstileBox,
    locate_turnstile_box,
    page_title_is_challenge,
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
        # 快路径：标题命中 CF 拦截页标题即判定，跳过全量 html（省 ~10s）
        try:
            if page_title_is_challenge(tab):
                return True
            html = tab.html
        except Exception:
            return False
        return _under_cf_challenge(html) or _under_cf_box_challenge(html)

    def resolve(self, tab: ChromiumTab, timeout: int = 30) -> bool:
        """尝试解析 Cloudflare 挑战。"""
        located: Optional[TurnstileBox] = None
        try:
            tab.wait(1)
            # 快路径：标题命中 CF 拦截页则无需读全量 html，直接按可定位组件分流
            if page_title_is_challenge(tab):
                located = locate_turnstile_box(tab, timeout=5)
                if located is not None:
                    return self._solve_box(tab, timeout, located)
                html = tab.html
            else:
                html = tab.html
                # 非拦截页（例如内嵌 Turnstile 的签到页）无需处理，直接放行。
                if not _under_cf_challenge(html):
                    return True
                located = locate_turnstile_box(tab, timeout=5)
                if located is not None:
                    return self._solve_box(tab, timeout, located)
        except Exception:
            html = ""

        if not html:
            return self._wait_challenge_cleared(tab, timeout)

        # Managed Challenge（JS 自动求解）：托管拦截页没有可点的复选框，
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

    def _solve_box(self, tab: ChromiumTab, timeout: int, located: Optional[TurnstileBox] = None) -> bool:
        """Turnstile 盒子挑战：尝试点击盒子内的验证按钮。"""
        logger.debug("Cloudflare Turnstile 盒子挑战，尝试点击...")
        tries = max(1, min(timeout // 10, 2))
        success, _ = sync_cf_box_retry(tab, tries=tries, prelocated=located)
        if success:
            return True
        return self._wait_challenge_cleared(tab, timeout)

    def solve_embedded_widget(self, tab: ChromiumTab, timeout: int = 25) -> bool:
        """尝试解决业务页面内嵌的 Turnstile 组件（如签到页的“请验证您是真人”复选框）。

        非交互组件在可信浏览器下会自动生成 token 并触发 cfCallback 提交表单；
        若渲染出复选框，则点击组件 shadow root 内的复选框。组件消失（表单已
        提交）同样视为成功。

        严格按 deadline 运行：每个耗时步骤（定位 iframe、点击判定、等待 token）
        前都会检查剩余时间，避免因组件无响应（如站点对 IP 限流）无限重试，
        导致请求挂到网关超时才返回。

        Returns:
            是否完成（拿到 token 或表单已提交）。
        """
        deadline = time.monotonic() + max(1, timeout)
        initial_token = turnstile_token(tab)
        # 组件可能异步加载（脚本来自 challenges.cloudflare.com）：
        # 先轮询等待其出现，避免"导航瞬间未渲染→跳过→永不重试"。
        present = self._widget_present(tab)
        while not initial_token and not present and time.monotonic() < deadline and (deadline - time.monotonic()) > 4:
            time.sleep(0.5)
            present = self._widget_present(tab)
        if not initial_token and not present:
            logger.debug("页面无内嵌 Turnstile 组件，跳过")
            return False

        def _remaining() -> float:
            return deadline - time.monotonic()

        def _widget_expired() -> bool:
            """检测 Turnstile expired/error 覆盖层（此时残留旧 token 不可信）。"""
            try:
                body = tab.ele("tag:body", timeout=1)  # type: ignore[union-attr]
                text: str = str(body.text) if body else ""
            except Exception:
                return False
            low = text.lower()
            return (
                "verification expired" in low
                or "验证已过期" in text
                or "验证已失效" in text
                or "verification failed" in low
                or "验证失败，请重试" in text
            )

        def _fresh_token_ok() -> bool:
            """成功判据：token 非空且是进入求解后新生成的，且未处于 expired/error。"""
            if _widget_expired():
                return False
            tok = turnstile_token(tab)
            return bool(tok) and (tok != initial_token or not initial_token)

        # 进入即已有 token 且组件状态正常（如非交互组件自动完成）→ 视为已通过
        if initial_token and not _widget_expired():
            logger.info("内嵌 Turnstile 进入时已有有效 token")
            return True

        expired_streak = 0
        # 主循环：预算充足（>4s）才发起一轮完整的「定位 + 点击 + 判定」。
        # 定位跨域 iframe 本身可能耗时数秒，预算不足时再发起会导致整段
        # 求解显著超过 deadline（历史上曾拖到网关超时才返回）。
        while _remaining() > 4:
            if not self._widget_present(tab):
                logger.info("内嵌 Turnstile 组件已消失，表单可能已提交")
                return True
            if _fresh_token_ok():
                logger.info("内嵌 Turnstile 已生成新 token，等待回调提交")
                return True
            if _widget_expired():
                # expired/error 状态：不再盲目重试点击，连续出现即停止，
                # 避免“一直重复验证但不成功”的死循环
                expired_streak += 1
                logger.warning(f"内嵌 Turnstile 进入 expired/error 态（连续 {expired_streak} 次）")
                if expired_streak >= 2:
                    logger.warning("expired/error 连续出现，停止重试（需人工/新会话重试）")
                    return False
                time.sleep(2)
                continue
            expired_streak = 0
            box = locate_turnstile_box(tab)
            if box is not None and turnstile_click(tab, box):
                # 点击后给组件一段不被打断的等待窗口（实测 token 多在点击后
                # ~7s 内到达，放宽到 15s 避免验证中重点；仍受剩余预算约束）
                wait_until = time.monotonic() + min(15.0, _remaining())
                while time.monotonic() < wait_until:
                    if not self._widget_present(tab):
                        logger.info("内嵌 Turnstile 点击后组件消失，表单已提交")
                        return True
                    if _fresh_token_ok():
                        logger.info("内嵌 Turnstile 点击后生成新 token")
                        return True
                    if _widget_expired():
                        break
                    time.sleep(0.5)
            else:
                time.sleep(0.5)

        # 收尾窗口：剩余预算只够做轻量轮询（不发起新的 iframe 定位/点击）
        while time.monotonic() < deadline:
            if not self._widget_present(tab):
                logger.info("内嵌 Turnstile 组件已消失，表单可能已提交")
                return True
            if _fresh_token_ok():
                logger.info("内嵌 Turnstile 已生成新 token，等待回调提交")
                return True
            time.sleep(0.4)
        logger.warning("内嵌 Turnstile 组件在超时时间内未能完成")
        return False

    def _widget_present(self, tab: ChromiumTab) -> bool:
        """组件存在判定：.cf-turnstile 容器 / turnstile 响应输入 / CF 挑战 iframe."""
        for selector, wait in (
            ("css:.cf-turnstile", 1),
            ('css:input[name="cf-turnstile-response"]', 0.5),
            ('css:iframe[src*="challenges.cloudflare.com"]', 0.5),
        ):
            try:
                if tab.ele(selector, timeout=wait):  # type: ignore[union-attr]
                    return True
            except Exception:
                continue
        return False
