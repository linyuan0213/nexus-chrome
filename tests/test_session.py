"""Session 模块单元测试 — 使用 mock 浏览器，无需真实 Chrome。"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.fingerprint import FingerprintManager
from src.core.session import Session, SessionManager


@pytest.fixture
def mock_browser():
    return MagicMock()


@pytest.fixture
def mock_tab():
    tab = MagicMock()
    tab.html = "<html><body>hello</body></html>"
    tab.url = "https://example.com/"
    tab.title = "Example"
    tab.cookies.return_value = [
        {"name": "session_id", "value": "abc123", "domain": ".example.com", "path": "/"},
    ]
    # 设置 ele 返回的 mock 元素，支持 click / clear / input
    ele_mock = MagicMock()
    tab.ele.return_value = ele_mock
    return tab


class TestSessionManager:
    def test_create_and_get(self, mock_browser):
        sm = SessionManager(mock_browser)
        session = sm.create("test-session", "stealth", None, None, mock_browser)
        assert sm.get("test-session") is session
        assert session.fingerprint.profile_name == "stealth"

    def test_create_duplicate_raises(self, mock_browser):
        sm = SessionManager(mock_browser)
        sm.create("test-session", "stealth", None, None, mock_browser)
        with pytest.raises(ValueError):
            sm.create("test-session", "stealth", None, None, mock_browser)

    def test_get_missing_raises(self, mock_browser):
        sm = SessionManager(mock_browser)
        with pytest.raises(ValueError):
            sm.get("missing")

    def test_list_and_delete(self, mock_browser):
        sm = SessionManager(mock_browser)
        sm.create("a", "stealth", None, None, mock_browser)
        sm.create("b", "stealth", None, None, mock_browser)
        assert len(sm.list_all()) == 2
        sm.delete("a")
        assert len(sm.list_all()) == 1
        with pytest.raises(ValueError):
            sm.get("a")


class TestSessionNavigate:
    def test_navigate_creates_tab_and_stores_cookies(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            result = session.navigate("https://example.com/")

        mock_browser.new_tab.assert_called_once()
        assert result["url"] == "https://example.com/"
        assert result["cookies"]["session_id"] == "abc123"
        assert session.cookie_store.as_dict("example.com")["session_id"] == "abc123"

    def test_navigate_init_js_before_load(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")

        assert mock_tab.get.called


class TestSessionProxy:
    def test_proxy_applied_to_tab(self, mock_browser, mock_tab):
        """配置代理时标签页应创建于带代理的浏览器上下文（DrissionPage 5.0 行为）。"""
        mock_context = MagicMock()
        mock_context.new_tab.return_value = mock_tab
        mock_browser.new_context.return_value = mock_context
        session = Session("s1", mock_browser, FingerprintManager("stealth"), proxy="http://proxy:8080")

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")

        mock_browser.new_context.assert_called_once_with(proxy="http://proxy:8080")
        mock_context.new_tab.assert_called_once()

    def test_proxy_set_failure_warns(self, mock_browser, mock_tab, caplog):
        """代理上下文创建失败时 navigate 不应抛异常。"""
        mock_browser.new_context.side_effect = RuntimeError("not supported")
        session = Session("s1", mock_browser, FingerprintManager("stealth"), proxy="http://proxy:8080")

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")  # 不应抛异常


class TestSessionInteraction:
    def test_click(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")
        session.click("#btn", humanize=False)
        mock_tab.ele.assert_called_once_with("#btn")
        mock_tab.ele.return_value.click.assert_called_once_with(by_js=None)

    def test_drag_uses_humanized(self, mock_browser, mock_tab):
        """drag 走人性化轨迹驱动，不直接调用 DrissionPage 原生拖拽。"""
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")
        with patch("src.core.session.session.human_drag_selector") as mock_drag:
            session.drag("#slider", 200)
            mock_drag.assert_called_once_with(mock_tab, "#slider", 200, 0, 1.0)

    def test_input_text(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")
        session.input_text("#search", "keyword")
        mock_tab.ele.assert_called_once_with("#search")
        mock_tab.ele.return_value.clear.assert_called_once()
        mock_tab.ele.return_value.input.assert_called_once_with("keyword")

    def test_execute(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")
        session.execute("return document.title")
        mock_tab.run_js.assert_called_once_with("return document.title")


class TestSessionClose:
    def test_close_tab(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")
        session.close_tab("tab_1")
        mock_tab.close.assert_called_once()
        assert session._active_tab_name is None


class TestSessionManagerLimits:
    def test_create_evicts_oldest_when_max_sessions_reached(self, mock_browser):
        sm = SessionManager(mock_browser, max_sessions=2, session_ttl=3600)
        sm.create("a", "stealth", None, None, mock_browser)
        sm.create("b", "stealth", None, None, mock_browser)
        assert len(sm.list_all()) == 2
        sm.create("c", "stealth", None, None, mock_browser)
        assert len(sm.list_all()) == 2
        assert "a" not in sm._sessions
        assert "c" in sm._sessions

    def test_delete_expired(self, mock_browser):
        sm = SessionManager(mock_browser, max_sessions=10, session_ttl=0)
        sm.create("a", "stealth", None, None, mock_browser)
        sm.create("b", "stealth", None, None, mock_browser)
        assert len(sm.list_all()) == 2
        deleted = sm.delete_expired()
        assert deleted == 2
        assert len(sm.list_all()) == 0


class TestSessionTabLifecycle:
    def test_navigate_closes_previous_active_tab(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/")
            session.navigate("https://example.org/")

        assert mock_tab.close.call_count == 1
        assert len(session._tabs) == 1

    def test_navigate_replaces_named_tab(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/", tab_name="work")
            session.navigate("https://example.org/", tab_name="work")

        assert mock_tab.close.call_count == 1
        assert "work" in session._tabs
        assert len(session._tabs) == 1

    def test_browser_fetch_closes_temp_tab(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        tab_any: Any = mock_tab
        tab_any.run_async_js.return_value = {
            "status": 200,
            "headers": {},
            "body": "ok",
            "url": "https://example.org/api",
        }
        session = Session("s1", mock_browser, FingerprintManager("stealth"))

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            result = session.browser_fetch("https://example.org/api", method="POST", data={"k": "v"})

        assert result["status_code"] == 200
        assert result["body"] == "ok"
        assert mock_tab.close.call_count == 1
        assert len(session._tabs) == 0


class TestNewCapabilities:
    """P1 媒体场景 + P2 会话/网络 新增能力测试。"""

    def _make_session(self, mock_browser):
        sm = SessionManager(mock_browser)
        return sm.create("cap-session", "stealth", None, None, mock_browser)

    def test_list_tabs(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        s = self._make_session(mock_browser)
        s._tabs["tab_1"] = mock_tab
        s._active_tab_name = "tab_1"
        result = s.list_tabs()
        assert result["active"] == "tab_1"
        assert result["tabs"][0]["name"] == "tab_1"
        assert result["tabs"][0]["url"] == "https://example.com/"

    def test_create_tab(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        s = self._make_session(mock_browser)
        result = s.create_tab("t2", "https://a.com/")
        assert result["name"] == "t2"
        mock_tab.get.assert_called_once_with("https://a.com/")

    def test_switch_tab(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        s = self._make_session(mock_browser)
        s.create_tab("t1")
        s.create_tab("t2")
        result = s.switch_tab("t1")
        assert result["active"] == "t1"

    def test_close_tab_missing_raises(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        s = self._make_session(mock_browser)
        with pytest.raises(ValueError):
            s.close_tab("nope")

    def test_screenshot(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        mock_tab.get_screenshot.return_value = "BASE64PNG=="
        s = self._make_session(mock_browser)
        s._tabs["tab_1"] = mock_tab
        s._active_tab_name = "tab_1"
        result = s.screenshot()
        assert result["png_base64"] == "BASE64PNG=="
        mock_tab.get_screenshot.assert_called_once_with(full_page=False, as_base64=True)

    def test_set_proxy(self, mock_browser, mock_tab):
        mock_browser.new_tab.return_value = mock_tab
        mock_context = MagicMock()
        mock_context.new_tab.return_value = mock_tab
        mock_browser.new_context.return_value = mock_context
        s = self._make_session(mock_browser)
        s._tabs["tab_1"] = mock_tab
        s._active_tab_name = "tab_1"
        result = s.set_proxy("http://127.0.0.1:8080")
        assert result["proxy"] == "http://127.0.0.1:8080"
        mock_browser.new_context.assert_called_with(proxy="http://127.0.0.1:8080")

    def test_download_fallback_js_fetch(self, mock_browser, mock_tab):
        """浏览器原生下载失败时应回退 JS fetch 二进制。"""
        mock_browser.new_tab.return_value = mock_tab
        mock_tab._download_by_browser.side_effect = RuntimeError("fail")
        mock_tab.run_async_js.return_value = {
            "status": 200,
            "content_type": "application/octet-stream",
            "size": 4,
            "base64": "YmluZQ==",
        }
        s = self._make_session(mock_browser)
        s._tabs["tab_1"] = mock_tab
        s._active_tab_name = "tab_1"
        result = s.download("https://example.com/file.bin")
        assert result.get("base64") == "YmluZQ=="
        assert result.get("size") == 4

    def test_detect_m3u8_master(self, mock_browser, mock_tab):
        """主播放列表解析（EXT-X-STREAM-INF 变体）。"""
        master = (
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=1920x1080\n"
            "https://cdn.example.com/video-1080.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=640000\n"
            "video-720.m3u8\n"
        )
        mock_browser.new_tab.return_value = mock_tab
        s = self._make_session(mock_browser)
        s._tabs["tab_1"] = mock_tab
        s._active_tab_name = "tab_1"
        # 直接测静态解析
        result = s._parse_m3u8("https://cdn.example.com/playlist.m3u8", master)
        assert result["type"] == "master"
        assert len(result["streams"]) == 2
        assert result["streams"][0]["resolution"] == "1920x1080"
        assert result["streams"][1]["url"] == "https://cdn.example.com/video-720.m3u8"

    def test_detect_m3u8_media(self, mock_browser, mock_tab):
        """媒体播放列表解析（EXTINF 分片）。"""
        media = "#EXTM3U\n#EXTINF:9.009,\nseg-1.ts\n#EXTINF:9.009,\nhttps://cdn.example.com/seg-2.ts\n"
        s = SessionManager(mock_browser)
        assert s._pool is mock_browser  # noqa: SLF001  (仅确认创建不抛)
        ss = s.create("m3", "stealth", None, None, mock_browser)
        parsed = ss._parse_m3u8("https://cdn.example.com/playlist.m3u8", media)
        assert parsed["type"] == "media"
        assert len(parsed["segments"]) == 2
        assert parsed["segments"][0]["url"] == "https://cdn.example.com/seg-1.ts"
        assert parsed["segment_count"] == 2


class TestSessionPersistence:
    def test_persist_and_recover(self, mock_browser, tmp_path):
        persist = tmp_path / "sessions.json"
        sm = SessionManager(mock_browser, persist_file=str(persist))
        sm.create("persist-1", "stealth", None, None, mock_browser)
        assert persist.exists()

        # 新建一个 manager（模拟重启），应恢复注册表
        sm2 = SessionManager(mock_browser, persist_file=str(persist))
        recovered = sm2.recovered_sessions()
        assert any(r["id"] == "persist-1" for r in recovered)

    def test_delete_removes_from_persist(self, mock_browser, tmp_path):
        persist = tmp_path / "sessions.json"
        sm = SessionManager(mock_browser, persist_file=str(persist))
        sm.create("persist-2", "stealth", None, None, mock_browser)
        sm.delete("persist-2")
        sm2 = SessionManager(mock_browser, persist_file=str(persist))
        assert not any(r["id"] == "persist-2" for r in sm2.recovered_sessions())


class TestInstanceRecycling:
    """浏览器实例引用计数 + 空闲回收测试。"""

    def _mk_inst(self, key, is_default=False):
        from src.core.browser_manager import ChromeInstance

        return ChromeInstance(
            key=key,
            fp_env=None,
            user_data_dir="/tmp/test-inst",
            port=9300,
            is_default=is_default,
        )

    def test_retain_release(self):
        from src.core.browser_manager import BrowserPool

        pool = BrowserPool(max_browsers=5)
        inst = self._mk_inst("p1")
        pool._instances["p1"] = inst
        pool.retain("p1")
        assert inst.ref_count == 1
        pool.release("p1")
        assert inst.ref_count == 0

    def test_session_delete_releases_instance(self, mock_browser):
        """删除会话后释放实例引用（引用归零触发关闭）。"""
        from src.core.browser_manager import BrowserPool
        from src.core.session import SessionManager

        pool = BrowserPool(max_browsers=5)
        inst = self._mk_inst("p1")
        pool._instances["p1"] = inst
        pool.retain("p1")
        sm = SessionManager(pool)
        sm.create("s1", "stealth", None, None, mock_browser, instance_key="p1")
        sm.delete("s1")
        assert "p1" not in pool._instances  # 引用归零后实例被关闭移除

    def test_evict_only_idle(self):
        """实例超限时只回收空闲（无引用）实例。"""
        from unittest.mock import MagicMock

        from src.core.browser_manager import BrowserPool

        pool = BrowserPool(max_browsers=2)
        inst_a = self._mk_inst("a")
        inst_a.retain()  # 被引用（in use）
        inst_b = self._mk_inst("b")
        # 两个实例都"存活"，避免走死亡回收分支
        for inst in (inst_a, inst_b):
            mb = MagicMock()
            mb.states.is_alive = True
            inst._browser = mb
        pool._instances = {"a": inst_a, "b": inst_b}
        pool._evict_if_needed()
        assert "b" not in pool._instances  # 回收空闲的 b
        assert "a" in pool._instances  # 保留使用中的 a


class TestNavigateAutoCookie:
    def test_auto_carry_stored_cookies(self, mock_browser, mock_tab):
        """未显式传 cookie 时，自动携带会话内已存储的同域名 Cookie。"""
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        # 预置：会话已存有 example.com 的 Cookie
        session.cookie_store.store("example.com", [{"name": "token", "value": "t-abc", "domain": "example.com"}])

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/page")

        # tab.set.cookies 应被调用且包含预置的 token
        set_mock = mock_tab.set.cookies
        assert set_mock.called, "未注入 Cookie"
        injected = set_mock.call_args[0][0]
        names = [c["name"] for c in injected]
        assert "token" in names

    def test_explicit_cookie_overrides_stored(self, mock_browser, mock_tab):
        """显式传入 cookie 时不混入存储（调用方完全控制）。"""
        mock_browser.new_tab.return_value = mock_tab
        session = Session("s1", mock_browser, FingerprintManager("stealth"))
        session.cookie_store.store("example.com", [{"name": "token", "value": "stored-val", "domain": "example.com"}])

        with patch("src.core.session.session.ChallengeOrchestrator") as MockOrchestrator:
            MockOrchestrator.return_value.resolve.return_value = {
                "detected": False,
                "type": "none",
                "solved": True,
                "duration_ms": 0,
            }
            session.navigate("https://example.com/page", cookie="token=explicit-val")

        injected = mock_tab.set.cookies.call_args[0][0]
        token = next(c for c in injected if c["name"] == "token")
        assert token["value"] == "explicit-val"
