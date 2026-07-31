"""测试 Cloudflare 挑战解决工具。"""

from src.utils.challenge_utils import (
    _turnstile_error,
    sync_cf_box_retry,
    sync_cf_retry,
)


class _FakePage:
    """最小桩：仅暴露挑战检测所需属性。"""

    def __init__(self, html):
        self.html = html


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
