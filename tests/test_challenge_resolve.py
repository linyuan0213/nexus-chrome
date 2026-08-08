"""挑战解析器 resolve 逻辑单元测试 — 使用 mock tab。"""

import time
from unittest.mock import MagicMock

import pytest

from src.challenge.cloudflare import CloudflareResolver
from src.challenge.five_second_shield import FiveSecondShieldResolver
from src.challenge.generic import GenericResolver
from src.challenge.leichi import LeichiResolver

CF_PAGE = "<html><head><title>Just a moment...</title></head><body><div id='cf-challenge-running'></div></body></html>"
CF_BOX_PAGE = "<html><head><title>Just a moment...</title></head><body><form id='challenge-form'><input name='cf-turnstile-response'></form></body></html>"
EMBEDDED_TURNSTILE_PAGE = (
    "<html><head><title>签到</title></head><body><div class='cf-turnstile' data-sitekey='0x4AAAAAABfcR5-BOyur3FT4'>"
    "<input type='hidden' name='cf-turnstile-response'></div></body></html>"
)
FIVE_SEC_PAGE = "<html><head><title>安全检查中...</title></head><body><div id='sec'>5</div></body></html>"
LEICHI_PAGE = "<html><head><title>雷池</title></head><body><div id='safeline-block'></div></body></html>"
NORMAL_PAGE = "<html><head><title>Normal Page</title></head><body><p>Hello</p></body></html>"


def make_tab(html_sequence=None):
    tab = MagicMock()
    if html_sequence is None:
        html_sequence = [NORMAL_PAGE]
    iter_html = iter(html_sequence)
    tab.html = property(lambda self: next(iter_html, NORMAL_PAGE))
    type(tab).html = tab.html
    return tab


class TestResolverTimeout:
    def test_five_second_respects_timeout(self):
        tab = MagicMock()
        tab.html = FIVE_SEC_PAGE
        resolver = FiveSecondShieldResolver()
        start = time.monotonic()
        result = resolver.resolve(tab, timeout=2)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed < 5  # 不应硬编码等待 7 秒

    def test_leichi_respects_timeout(self):
        tab = MagicMock()
        tab.html = LEICHI_PAGE
        resolver = LeichiResolver()
        start = time.monotonic()
        result = resolver.resolve(tab, timeout=2)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed < 5

    def test_generic_respects_timeout(self):
        tab = MagicMock()
        tab.html = (
            "<html><head><title>Access denied</title></head><body><div class='challenge-container'></div></body></html>"
        )
        resolver = GenericResolver()
        start = time.monotonic()
        result = resolver.resolve(tab, timeout=2)
        elapsed = time.monotonic() - start
        assert result is False
        assert elapsed < 5


class TestCloudflareResolve:
    def test_no_challenge_returns_true(self):
        tab = MagicMock()
        tab.html = NORMAL_PAGE
        resolver = CloudflareResolver()
        assert resolver.resolve(tab, timeout=2) is True
        tab.wait.assert_called()

    def test_embedded_turnstile_not_treated_as_challenge(self):
        """内嵌 Turnstile 的签到页不应被当作挑战去点击。"""
        tab = MagicMock()
        tab.html = EMBEDDED_TURNSTILE_PAGE
        resolver = CloudflareResolver()
        assert resolver.resolve(tab, timeout=2) is True

    def test_managed_challenge_polling(self):
        tab = MagicMock()
        tab.html = CF_PAGE
        resolver = CloudflareResolver()
        # 由于 _solve_standard 会调用 sync_cf_retry，mock 它
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.challenge.cloudflare._is_managed_challenge", lambda x: True)
            result = resolver.resolve(tab, timeout=1)
        # Managed Challenge 会轮询，超时返回 False
        assert result is False

    def test_challenge_cleared_returns_true(self):
        tab = MagicMock()
        # 第一页是 challenge，之后变成正常页面
        htmls = [CF_PAGE, CF_PAGE, NORMAL_PAGE]
        tab.html = property(lambda self: htmls.pop(0) if htmls else NORMAL_PAGE)
        type(tab).html = tab.html
        resolver = CloudflareResolver()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.challenge.cloudflare._is_managed_challenge", lambda x: True)
            result = resolver.resolve(tab, timeout=5)
        assert result is True


class TestSolveEmbeddedWidget:
    def test_token_present_returns_true(self):
        tab = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.challenge.cloudflare.turnstile_token", lambda t: "token-abc")
            result = CloudflareResolver().solve_embedded_widget(tab, timeout=5)
        assert result is True

    def test_widget_disappears_returns_true(self):
        """表单提交后组件消失同样视为完成（组件需先存在）。"""
        tab = MagicMock()
        state = {"present": True}

        class _FakeResolver(CloudflareResolver):
            def _widget_present(self, tab):  # noqa: ARG002
                result = state["present"]
                state["present"] = False
                return result

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.challenge.cloudflare.turnstile_token", lambda t: "")
            mp.setattr("src.challenge.cloudflare.locate_turnstile_box", lambda t, timeout=5: None)
            result = _FakeResolver().solve_embedded_widget(tab, timeout=5)
        assert result is True

    def test_no_widget_at_all_returns_false(self):
        """页面从未出现 Turnstile 组件时无需处理，直接跳过。"""
        from src.challenge.cloudflare import CloudflareResolver

        tab = MagicMock()

        class _FakeResolver(CloudflareResolver):
            def _widget_present(self, tab):  # noqa: ARG002
                return False

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.challenge.cloudflare.turnstile_token", lambda t: "")
            result = _FakeResolver().solve_embedded_widget(tab, timeout=2)
        assert result is False

    def test_timeout_returns_false(self):
        tab = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("src.challenge.cloudflare.turnstile_token", lambda t: "")
            mp.setattr("src.challenge.cloudflare.locate_turnstile_box", lambda t, timeout=5: None)
            result = CloudflareResolver().solve_embedded_widget(tab, timeout=2)
        assert result is False


class TestCloudflareResolveOrder:
    def test_box_challenge_preferred_over_managed(self):
        """拦截页同时是盒子挑战与托管挑战时，优先走盒子点击。"""
        from src.challenge.cloudflare import CloudflareResolver

        tab = MagicMock()
        # 同时含 _cf_chl_opt（拦截页）、cf-turnstile-response（盒子）、challenges.cloudflare.com（托管）
        tab.html = (
            "<html><head><title>请稍候…</title></head><body>"
            "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>"
            "<input name='cf-turnstile-response'>"
            "</body></html>"
        )
        resolver = CloudflareResolver()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(CloudflareResolver, "_solve_box", lambda self, t, timeout: True)
            called = []
            mp.setattr(
                CloudflareResolver,
                "_wait_managed",
                lambda self, t, timeout: called.append(True) or True,
            )
            assert resolver.resolve(tab, timeout=3) is True
        assert called == [], "盒子挑战存在时不应先走托管等待"

    def test_multi_layer_cf_then_leichi(self):
        """两层 WAF：先 CF 拦截页，解决后跳转到雷池拦截页，应逐层解决。"""
        from src.challenge.cloudflare import CloudflareResolver
        from src.challenge.leichi import LeichiResolver
        from src.challenge.resolver import ChallengeOrchestrator

        # 页面随解决进度变化：CF 拦截页 → 雷池拦截页 → 正常页
        pages = [CF_PAGE, LEICHI_PAGE, NORMAL_PAGE]
        state = {"i": 0}

        class _Tab(MagicMock):
            @property
            def html(self):
                return pages[state["i"]]

        def cf_resolve(self, t, timeout):
            state["i"] = 1
            return True

        def leichi_resolve(self, t, timeout):
            state["i"] = 2
            return True

        tab = _Tab()
        orchestrator = ChallengeOrchestrator(timeout=10)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(CloudflareResolver, "resolve", cf_resolve)
            mp.setattr(LeichiResolver, "resolve", leichi_resolve)
            mp.setattr(
                "src.challenge.resolver.ChallengeOrchestrator._solve_embedded_turnstile",
                lambda self, t, timeout: False,
            )
            result = orchestrator.resolve(tab)
        assert result["detected"] is True
        assert result["solved"] is True
        assert result["layers"] == ["cloudflare", "leichi"]
