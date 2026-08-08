"""测试 Cloudflare 挑战解决工具。"""

from src.utils.challenge_utils import (
    _turnstile_error,
    locate_turnstile_box,
    sync_cf_box_retry,
    sync_cf_retry,
    turnstile_click,
    turnstile_token,
)


class _FakePage:
    """最小桩：仅暴露挑战检测所需属性。"""

    def __init__(self, html):
        self.html = html

    def ele(self, locator, timeout=None):
        return None


class _FakeErrorBox:
    """模拟报“验证失败”的 Turnstile shadow root。"""

    def ele(self, locator, timeout=None):
        if "challenge-error-text" in locator:
            return type("_E", (), {"text": "验证失败 故障排除"})()
        return None


class _FakeErrorPage:
    def __init__(self):
        self.html = "<html><body>Verification failed</body></html>"

    def ele(self, locator, timeout=None):
        return type("_B", (), {"text": "Verification failed. Troubleshooting."})()


class TestSyncCfShortCircuit:
    def test_sync_cf_retry_no_challenge(self):
        page = _FakePage("<html><title>normal page</title></html>")
        assert sync_cf_retry(page, tries=2) == (True, False)  # type: ignore[arg-type]

    def test_sync_cf_box_retry_no_challenge(self):
        page = _FakePage("<html><body>ok</body></html>")
        assert sync_cf_box_retry(page, tries=2) == (True, False)  # type: ignore[arg-type]


class TestTurnstileError:
    def test_detects_error_from_box(self):
        assert _turnstile_error(_FakeErrorPage(), _FakeErrorBox()) is True  # type: ignore[arg-type]


class TestTurnstileToken:
    def test_no_input_returns_empty(self):
        assert turnstile_token(_FakePage("<html></html>")) == ""  # type: ignore[arg-type]

    def test_returns_token_value(self):
        class _Inp:
            def attr(self, name):
                return "token123"

        class _Page:
            def ele(self, locator, timeout=None):
                return _Inp()

        assert turnstile_token(_Page()) == "token123"  # type: ignore[arg-type]

    def test_empty_value_returns_empty(self):
        class _Inp:
            def attr(self, name):
                return ""

        class _Page:
            def ele(self, locator, timeout=None):
                return _Inp()

        assert turnstile_token(_Page()) == ""  # type: ignore[arg-type]


class TestTurnstileClick:
    def test_click_input_checkbox(self):
        clicked = []

        class _Btn:
            tag = "input"

            def click(self):
                clicked.append(True)

        class _Box:
            def ele(self, selector, timeout=None):
                assert "input[type=checkbox]" in selector
                return _Btn()

        class _Page:
            class actions:  # noqa: N801
                @staticmethod
                def move_to(*args, **kwargs):
                    raise AssertionError("不应走 actions 路径")

        assert turnstile_click(_Page(), _Box()) is True  # type: ignore[arg-type]
        assert clicked == [True]

    def test_no_checkbox_returns_false(self):
        class _Box:
            def ele(self, selector, timeout=None):
                return None

        class _Page:
            pass

        assert turnstile_click(_Page(), _Box()) is False  # type: ignore[arg-type]


class TestLocateTurnstileBox:
    def test_returns_none_when_no_widget(self):
        page = _FakePage("<html></html>")
        assert locate_turnstile_box(page) is None  # type: ignore[arg-type]

    def test_shadow_root_path_returns_body_shadow_root(self):
        """验证 closed shadow root 穿透路径：输入框父级 shadow root → iframe → body.shadow_root。"""
        body_sr = object()

        class _Frame:
            def ele(self, locator, timeout=None):
                assert "tag:body" in locator
                return type("_Body", (), {"shadow_root": body_sr})()

        class _Shadow:
            def ele(self, locator, timeout=None):
                assert "tag:iframe" in locator
                return _Frame()

        class _Wrapper:
            shadow_root = _Shadow()

        class _Inp:
            def parent(self):
                return _Wrapper()

        class _Widget:
            pass

        class _Page:
            def ele(self, locator, timeout=None):
                if ".cf-turnstile" in locator:
                    return _Widget()
                if "cf-turnstile-response" in locator:
                    return _Inp()
                return None

        assert locate_turnstile_box(_Page()) is body_sr  # type: ignore[arg-type]


class TestLocateTurnstileBoxInterstitial:
    def test_works_without_cf_turnstile_class(self):
        """CF 拦截页的 Turnstile 组件没有 .cf-turnstile 类，也应能定位。"""
        body_sr = object()

        class _Frame:
            def ele(self, locator, timeout=None):
                assert "tag:body" in locator
                return type("_Body", (), {"shadow_root": body_sr})()

        class _Shadow:
            def ele(self, locator, timeout=None):
                assert "tag:iframe" in locator
                return _Frame()

        class _Wrapper:
            shadow_root = _Shadow()

        class _Inp:
            def parent(self):
                return _Wrapper()

        class _Page:
            def ele(self, locator, timeout=None):
                if "cf-turnstile-response" in locator:
                    return _Inp()
                return None

        assert locate_turnstile_box(_Page()) is body_sr  # type: ignore[arg-type]
