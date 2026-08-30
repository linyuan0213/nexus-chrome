"""挑战检测单元测试 — 纯 HTML 解析，不需要浏览器。"""

from unittest.mock import MagicMock, patch

from src.config.settings import (
    CHALLENGE_TYPE_CLOUDFLARE,
    CHALLENGE_TYPE_FIVE_SECOND,
    CHALLENGE_TYPE_GENERIC,
    CHALLENGE_TYPE_LEICHI,
)

# HTML 片段
CF_PAGE = "<html><head><title>Just a moment...</title></head><body><div id='cf-challenge-running'></div></body></html>"
CF_BOX_PAGE = "<html><head><title>Just a moment...</title></head><body><form id='challenge-form'><input name='cf-turnstile-response'></form></body></html>"
EMBEDDED_TURNSTILE_PAGE = (
    "<html><head><title>签到</title></head><body><div class='cf-turnstile' data-sitekey='0x4AAAAAABfcR5-BOyur3FT4'>"
    "<input type='hidden' name='cf-turnstile-response'></div></body></html>"
)
FIVE_SEC_PAGE = "<html><head><title>安全检查中...</title></head><body><div id='sec'>5</div></body></html>"
LEICHI_PAGE = "<html><head><title>雷池</title></head><body><div id='safeline-block'></div></body></html>"
NORMAL_PAGE = "<html><head><title>Normal Page</title></head><body><p>Hello</p></body></html>"


class TestCloudflareDetect:
    def test_detect_standard(self):
        from src.challenge.cloudflare import _under_cf_challenge

        assert _under_cf_challenge(CF_PAGE) is True

    def test_detect_japanese(self):
        from src.challenge.cloudflare import _under_cf_challenge

        html = "<html><head><title>请稍候…</title></head><body></body></html>"
        assert _under_cf_challenge(html) is True

    def test_detect_box(self):
        from src.challenge.cloudflare import _under_cf_box_challenge

        assert _under_cf_box_challenge(CF_BOX_PAGE) is True

    def test_embedded_turnstile_not_challenge(self):
        """页面内嵌 Turnstile 组件（如签到页）不应被误判为 Cloudflare 挑战。"""
        from src.challenge.cloudflare import _under_cf_box_challenge, _under_cf_challenge

        assert _under_cf_challenge(EMBEDDED_TURNSTILE_PAGE) is False
        assert _under_cf_box_challenge(EMBEDDED_TURNSTILE_PAGE) is False

    def test_no_detect_on_normal(self):
        from src.challenge.cloudflare import _under_cf_box_challenge, _under_cf_challenge

        assert _under_cf_challenge(NORMAL_PAGE) is False
        assert _under_cf_box_challenge(NORMAL_PAGE) is False
        assert _under_cf_box_challenge(EMBEDDED_TURNSTILE_PAGE) is False

    def test_precursor_script_not_interstitial(self):
        """CF 前端正常页面加载 /cdn-cgi/challenge-platform/ 脚本不应被误判为拦截页。"""
        from src.challenge.cloudflare import _under_cf_challenge

        html = (
            "<html><head><title>插画、漫画</title></head><body>"
            "<script src='/cdn-cgi/challenge-platform/scripts/precursor/main.js'></script>"
            "<p>正常内容</p></body></html>"
        )
        assert _under_cf_challenge(html) is False

    def test_challenge_type(self):
        from src.challenge.cloudflare import CloudflareResolver

        resolver = CloudflareResolver()
        assert resolver.challenge_type == CHALLENGE_TYPE_CLOUDFLARE


class TestFiveSecondDetect:
    def test_detect_by_selector(self):
        from pyquery import PyQuery

        from src.config.settings import FIVE_SECOND_SELECTORS

        doc = PyQuery(FIVE_SEC_PAGE)
        found = any(doc(s) for s in FIVE_SECOND_SELECTORS)
        assert found is True

    def test_no_detect_on_normal(self):
        from pyquery import PyQuery

        from src.config.settings import FIVE_SECOND_SELECTORS

        doc = PyQuery(NORMAL_PAGE)
        found = any(doc(s) for s in FIVE_SECOND_SELECTORS)
        assert found is False

    def test_challenge_type(self):
        from src.challenge.five_second_shield import FiveSecondShieldResolver

        resolver = FiveSecondShieldResolver()
        assert resolver.challenge_type == CHALLENGE_TYPE_FIVE_SECOND


class TestLeichiDetect:
    def test_detect_by_selector(self):
        from pyquery import PyQuery

        from src.config.settings import LEICHI_SELECTORS

        doc = PyQuery(LEICHI_PAGE)
        found = any(doc(s) for s in LEICHI_SELECTORS)
        assert found is True

    def test_challenge_type(self):
        from src.challenge.leichi import LeichiResolver

        resolver = LeichiResolver()
        assert resolver.challenge_type == CHALLENGE_TYPE_LEICHI


class TestGenericDetect:
    def test_detect_by_selector(self):
        from pyquery import PyQuery

        from src.config.settings import CHALLENGE_SELECTORS, GENERIC_CHALLENGE_SELECTORS

        html = (
            "<html><head><title>Access denied</title></head><body><div class='challenge-container'></div></body></html>"
        )
        doc = PyQuery(html)
        all_selectors = CHALLENGE_SELECTORS + GENERIC_CHALLENGE_SELECTORS
        found = any(doc(s) for s in all_selectors)
        assert found is True

    def test_challenge_type(self):
        from src.challenge.generic import GenericResolver

        resolver = GenericResolver()
        assert resolver.challenge_type == CHALLENGE_TYPE_GENERIC


class TestChallengeOrchestratorInit:
    def test_creates_resolvers(self):
        from src.challenge.resolver import ChallengeOrchestrator

        orchestrator = ChallengeOrchestrator(timeout=30)
        assert len(orchestrator._resolvers) == 4

    def test_resolve_no_challenge(self):
        from unittest.mock import MagicMock

        from src.challenge.resolver import ChallengeOrchestrator

        orchestrator = ChallengeOrchestrator(timeout=5)
        tab = MagicMock()
        tab.html = NORMAL_PAGE
        result = orchestrator.resolve(tab)
        assert result["detected"] is False
        assert result["solved"] is True

    def test_resolve_no_challenge_reports_embedded_turnstile(self):
        from unittest.mock import MagicMock

        from src.challenge.resolver import ChallengeOrchestrator

        orchestrator = ChallengeOrchestrator(timeout=5)
        tab = MagicMock()
        tab.html = NORMAL_PAGE
        result = orchestrator.resolve(tab)
        assert "embedded_turnstile" in result


class TestCloudflareResolveBranch:
    """resolve 分支选择：盒子优先于托管（防脚本标记误判导致复选框不点击）。"""

    def _resolver(self):
        from src.challenge.cloudflare import CloudflareResolver

        return CloudflareResolver()

    def _tab(self, html: str):
        tab = MagicMock()
        tab.html = html
        return tab

    _BOX_HTML = (
        "<html><head><title>Just a moment...</title></head><body>"
        '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
        '<input name="cf-turnstile-response">'
        "</body></html>"
    )

    def test_box_locatable_goes_to_solve_box_even_with_managed_script(self):
        """同时带 managed 脚本标记 + 可定位盒子 → 走 _solve_box（点击复选框）。"""
        resolver = self._resolver()
        with (
            patch("src.challenge.cloudflare.locate_turnstile_box", return_value=MagicMock()),
            patch.object(resolver, "_solve_box", return_value=True) as box,
            patch.object(resolver, "_wait_managed", return_value=True) as managed,
        ):
            assert resolver.resolve(self._tab(self._BOX_HTML)) is True
        box.assert_called_once()
        managed.assert_not_called()

    def test_managed_without_box_waits(self):
        """托管标记且无 Turnstile 输入/盒子 → 走 _wait_managed（不点击）。"""
        resolver = self._resolver()
        managed_html = (
            "<html><head><title>Just a moment...</title></head><body>"
            '<script src="https://challenges.cloudflare.com/managed/v1/challenge.js"></script>'
            "</body></html>"
        )
        with (
            patch("src.challenge.cloudflare.locate_turnstile_box", return_value=None),
            patch.object(resolver, "_solve_box", return_value=True) as box,
            patch.object(resolver, "_wait_managed", return_value=True) as managed,
        ):
            assert resolver.resolve(self._tab(managed_html)) is True
        box.assert_not_called()
        managed.assert_called_once()

    def test_non_interstitial_passes_through(self):
        """普通页面（内嵌 Turnstile 组件）不算挑战，直接放行。"""
        resolver = self._resolver()
        html = (
            "<html><head><title>签到</title></head><body>"
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>'
            "</body></html>"
        )
        with patch.object(resolver, "_solve_box") as box, patch.object(resolver, "_wait_managed") as managed:
            assert resolver.resolve(self._tab(html)) is True
        box.assert_not_called()
        managed.assert_not_called()
