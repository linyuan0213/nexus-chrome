"""BrowserPool 实例上限与画像隔离测试."""

from unittest.mock import patch

from src.core.browser_manager.pool import BrowserPool


class _FakeInst:
    def __init__(self, key=None, **kwargs):
        self.key = key or "default"
        self.ref_count = 0
        self.is_default = self.key == "default"
        self.last_used = 0
        self.is_alive = True
        self.display_index = None
        self.port = 9222
        self.display = ":1"
        self.vnc_port = 5900
        self.web_port = 6080

    def ensure(self):
        return self

    def retain(self):
        self.ref_count += 1

    def release(self):
        self.ref_count = max(0, self.ref_count - 1)

    @property
    def is_idle(self):
        return self.ref_count <= 0

    @property
    def idle_seconds(self):
        return 0

    def reap_dead_browser(self):
        return False

    def shutdown(self):
        self.is_alive = False


def test_pool_does_not_reuse_across_profiles_at_cap():
    """达上限也不跨画像复用（否则串指纹会被 CF 拦截）."""
    with patch("src.core.browser_manager.pool.ChromeInstance", _FakeInst):
        pool = BrowserPool(max_browsers=2)
        first = pool.get("user_1")
        pool.retain(first.key)
        second = pool.get("default")
        assert second is not first
        assert second.key == "default"
        assert len(pool.list_instances()) == 2


def test_pool_evicts_idle_instance_to_make_room():
    """达上限时优先回收空闲实例，再为所需画像新建，实例数不超上限."""
    with patch("src.core.browser_manager.pool.ChromeInstance", _FakeInst):
        pool = BrowserPool(max_browsers=1)
        pool.get("user_1")  # ref_count=0 → 空闲
        created = pool.get("other")
        assert created.key == "other"
        assert len(pool.list_instances()) == 1


def test_ensure_browser_with_profile_returns_actual_key():
    with patch("src.core.browser_manager.pool.ChromeInstance", _FakeInst):
        pool = BrowserPool(max_browsers=2)
        _browser, key = pool.ensure_browser_with_profile("user_1")
        assert key == "user_1"
