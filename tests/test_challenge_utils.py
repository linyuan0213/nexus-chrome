"""测试 Cloudflare 挑战解决工具。"""

from src.utils.challenge_utils import (
    TurnstileBox,
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
    """turnstile_click：人性化轨迹点击 + 最多 3 次重试。"""

    class _Rect:
        viewport_location = (100, 50)
        size = (20, 20)

    class _Btn:
        tag = "input"
        rect = None  # 无坐标 → 回退 btn.click()

        def __init__(self, clicked):
            self._clicked = clicked

        def click(self):
            self._clicked.append(True)

    class _Box:
        def __init__(self, btn=None):
            self._btn = btn

        def ele(self, selector, timeout=None):
            if self._btn and "checkbox" in selector:
                return self._btn
            return None

    class _Page:
        def ele(self, locator, timeout=None):
            return None

    def _patch_judgement(self, monkeypatch, success: bool):
        """统一 mock 判定信号与等待，避免测试走真实 8s 轮询。"""
        monkeypatch.setattr("src.utils.challenge_utils.time.sleep", lambda *_: None)
        monkeypatch.setattr("src.utils.challenge_utils._turnstile_success", lambda box: success)
        monkeypatch.setattr("src.utils.challenge_utils.turnstile_token", lambda page: "")

    def test_fallback_to_btn_click_and_success(self, monkeypatch):
        """无坐标时回退元素点击；success 标记出现即通过。"""
        self._patch_judgement(monkeypatch, success=True)
        clicked = []
        btn = self._Btn(clicked)
        box = self._Box(btn=btn)
        assert turnstile_click(self._Page(), TurnstileBox(box=box, origin=None)) is True  # type: ignore[arg-type]
        assert clicked == [True]

    def test_humanized_click_used_when_rect_available(self, monkeypatch):
        """有视口坐标时走人性化贝塞尔轨迹点击，且坐标带随机偏移。"""
        self._patch_judgement(monkeypatch, success=True)
        calls = []

        class Btn:
            tag = "input"
            rect = TestTurnstileClick._Rect()

            def click(self):
                raise AssertionError("不应走 btn.click 路径")

        monkeypatch.setattr("src.utils.challenge_utils.human_click", lambda page, target: calls.append(target))
        box = self._Box(btn=Btn())
        # origin (200, 100)：目标 = origin + iframe 相对位置 (100, 50) + 半边 (10, 10) + ±3 抖动
        assert turnstile_click(self._Page(), TurnstileBox(box=box, origin=(200, 100))) is True  # type: ignore[arg-type]
        assert len(calls) == 1
        # 绝对中心 (310, 160) ± 3px 偏移
        assert abs(calls[0][0] - 310) <= 3 and abs(calls[0][1] - 160) <= 3

    def test_click_not_passed_retries_three_times(self, monkeypatch):
        """点击后判定未通过 → 最多重试 3 次。"""
        self._patch_judgement(monkeypatch, success=False)
        # 压缩判定等待窗口为 0，避免真实 8s 轮询
        monkeypatch.setattr("src.utils.challenge_utils._CLICK_JUDGE_TIMEOUT_S", 0)
        clicked = []
        btn = self._Btn(clicked)
        box = self._Box(btn=btn)
        assert turnstile_click(self._Page(), TurnstileBox(box=box, origin=None), max_attempts=3) is False  # type: ignore[arg-type]
        assert clicked == [True, True, True]

    def test_no_checkbox_returns_false_after_retries(self, monkeypatch):
        """始终无复选框：重试 3 次后返回 False。"""
        sleeps = []
        monkeypatch.setattr("src.utils.challenge_utils.time.sleep", lambda s: sleeps.append(s))
        box = self._Box(btn=None)
        assert turnstile_click(self._Page(), TurnstileBox(box=box, origin=None), max_attempts=3) is False  # type: ignore[arg-type]
        assert len(sleeps) == 2  # 第 1、2 次失败后各等一次

    def test_fast_exit_when_title_left_challenge(self, monkeypatch):
        """页面标题已非挑战（内嵌组件场景：业务页标题不命中挑战集）→ 点击后立即通过。

        内嵌 Turnstile 的签到/登录页标题不是挑战标题，点击后无需等待 success
        标记，由调用方（solve_embedded_widget）继续轮询 token。
        """
        self._patch_judgement(monkeypatch, success=False)
        monkeypatch.setattr("src.utils.challenge_utils.page_title_is_challenge", lambda page: False)
        clicked = []
        btn = self._Btn(clicked)
        box = self._Box(btn=btn)
        assert turnstile_click(self._Page(), TurnstileBox(box=box, origin=None)) is True  # type: ignore[arg-type]
        assert clicked == [True]

    def test_checkbox_appears_on_retry(self, monkeypatch):
        """第一次未渲染出复选框，第二次出现后点击成功。"""
        self._patch_judgement(monkeypatch, success=True)
        clicked = []
        btn = self._Btn(clicked)
        box = self._Box(btn=None)
        calls = {"n": 0}

        def ele(selector, timeout=None):
            if "checkbox" in selector:
                calls["n"] += 1
                if calls["n"] == 1:
                    return None  # 第一次未就绪
                return btn
            return None

        box.ele = ele  # type: ignore[method-assign]
        assert turnstile_click(self._Page(), TurnstileBox(box=box, origin=None)) is True  # type: ignore[arg-type]
        assert clicked == [True]


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
                assert "iframe" in locator
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

        located = locate_turnstile_box(_Page())  # type: ignore[arg-type]
        assert located is not None
        assert located.box is body_sr
        assert located.origin is None  # fake iframe 无 rect


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
                assert "iframe" in locator
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

        located = locate_turnstile_box(_Page())  # type: ignore[arg-type]
        assert located is not None
        assert located.box is body_sr
        assert located.origin is None  # fake iframe 无 rect
