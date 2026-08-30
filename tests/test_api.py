"""API 路由单元测试 — mock SessionManager，无需真实浏览器。"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_session_manager():
    sm = MagicMock()
    session = MagicMock()
    session.to_dict.return_value = {
        "id": "work",
        "fingerprint": "stealth",
        "tabs": [],
        "active_tab": None,
        "cookie_domains": [],
    }
    session.cookie_store = MagicMock()
    session.cookie_store.as_dict.return_value = {"session_id": "abc123"}
    session.cookie_store.as_header.return_value = "session_id=abc123"
    session.cookie_store.as_full_dict.return_value = {"example.com": {"session_id": "abc123"}}
    session.cookie_store.store = MagicMock()
    session.get_cookies.return_value = {"example.com": {"session_id": "abc123"}}
    session.get_html.return_value = {"url": "https://example.com/", "html": "<html>"}
    session.execute.return_value = "title"
    sm.create.return_value = session
    sm.get.return_value = session
    sm.list_all.return_value = [session.to_dict()]
    sm.delete = MagicMock()
    return sm, session


class TestCreateSession:
    def test_create_session(self, client, mock_session_manager):
        sm, session = mock_session_manager
        # 注意：routes 模块顶部已 `from session_service import create_session`，
        # 必须 patch 路由命名空间里的引用，patch 源模块属性不生效。
        with patch("src.api.routes.create_session", return_value=session):
            response = client.post(
                "/sessions",
                json={
                    "session_id": "work",
                    "fingerprint_profile": "stealth",
                    "user_agent": "Mozilla/5.0",
                    "proxy": "http://proxy:8080",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == "work"

    def test_create_duplicate(self, client, mock_session_manager):
        session = mock_session_manager[1]
        session.to_dict.return_value = {"id": "work", "tabs": []}
        with (
            patch("src.api.routes.create_session", side_effect=ValueError("会话已存在")),
            patch("src.api.routes._get_sm", return_value=mock_session_manager[0]),
        ):
            response = client.post("/sessions", json={"session_id": "work"})
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["message"] == "会话已存在"


class TestListAndDeleteSession:
    def test_list_sessions(self, client, mock_session_manager):
        sm, _ = mock_session_manager
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.get("/sessions")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]["sessions"]) == 1

    def test_delete_session(self, client, mock_session_manager):
        sm, _ = mock_session_manager
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.delete("/sessions/work")
        assert response.status_code == 200
        assert response.json()["code"] == 0

    def test_delete_missing_session(self, client, mock_session_manager):
        sm, _ = mock_session_manager
        sm.delete.side_effect = ValueError("未找到")
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.delete("/sessions/missing")
        assert response.status_code == 404


class TestNavigate:
    def test_navigate(self, client, mock_session_manager):
        sm, session = mock_session_manager
        session.navigate.return_value = {
            "url": "https://example.com/",
            "title": "Example",
            "html": "<html>",
            "cookies": {"session_id": "abc123"},
            "cookie_header": "session_id=abc123",
            "challenge": {"detected": False, "type": "none", "solved": True, "duration_ms": 0},
        }
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.post("/sessions/work/navigate", json={"url": "https://example.com/", "timeout": 30})
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["html"] == "<html>"


class TestFetch:
    def test_fetch_injects_cookie(self, client, mock_session_manager):
        sm, session = mock_session_manager
        with patch("src.api.routes.HttpClient") as MockClient:
            instance = MockClient.return_value
            instance.fetch.return_value = {
                "url": "https://example.com/api",
                "status_code": 200,
                "headers": {},
                "body": "{}",
                "cookies_used": ["session_id"],
            }
            with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
                response = client.post(
                    "/sessions/work/fetch",
                    json={
                        "url": "https://example.com/api",
                        "method": "GET",
                        "headers": {},
                        "data": None,
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status_code"] == 200
        instance.fetch.assert_called_once()
        call_kwargs = instance.fetch.call_args.kwargs
        assert call_kwargs["cookie_store"] is session.cookie_store


class TestRequest:
    def test_request_uses_browser_fetch_on_challenge(self, client, mock_session_manager):
        sm, session = mock_session_manager
        with patch("src.services.request_service.HttpClient") as MockClient:
            instance = MockClient.return_value
            instance.fetch.return_value = {
                "url": "https://example.com/",
                "status_code": 403,
                "headers": {},
                "body": "Just a moment...",
            }
            session.browser_fetch.return_value = {
                "url": "https://example.com/",
                "status_code": 200,
                "headers": {},
                "body": "<html>ok</html>",
                "challenge": {"detected": True, "type": "cloudflare", "solved": True},
            }
            with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
                response = client.post(
                    "/sessions/work/request",
                    json={
                        "url": "https://example.com/",
                        "method": "GET",
                        "navigate_if_challenge": True,
                        "browser_fetch_on_challenge": True,
                        "return_html": False,
                        "timeout": 30,
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status_code"] == 200
        assert data["data"]["body"] == "<html>ok</html>"
        session.browser_fetch.assert_called_once()

    def test_request_returns_challenge_when_no_fallback(self, client, mock_session_manager):
        sm, session = mock_session_manager
        with patch("src.services.request_service.HttpClient") as MockClient:
            instance = MockClient.return_value
            instance.fetch.return_value = {
                "url": "https://example.com/",
                "status_code": 403,
                "headers": {},
                "body": "Just a moment...",
            }
            with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
                response = client.post(
                    "/sessions/work/request",
                    json={
                        "url": "https://example.com/",
                        "method": "GET",
                        "navigate_if_challenge": False,
                        "browser_fetch_on_challenge": False,
                        "return_html": False,
                        "timeout": 30,
                    },
                )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["status_code"] == 403
        session.browser_fetch.assert_not_called()

    def test_get_html(self, client, mock_session_manager):
        sm, session = mock_session_manager
        session.get_html.return_value = {"url": "https://example.com/", "html": "<html>"}
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.get("/sessions/work/html")
        assert response.status_code == 200
        assert response.json()["data"]["html"] == "<html>"

    def test_get_cookies(self, client, mock_session_manager):
        sm, session = mock_session_manager
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.get("/sessions/work/cookies")
        assert response.status_code == 200
        assert response.json()["data"]["example.com"]["session_id"] == "abc123"


class TestExecute:
    def test_execute_js(self, client, mock_session_manager):
        sm, session = mock_session_manager
        session.execute.return_value = "title"
        with patch("src.api.routes.session_manager", sm), patch("src.api.routes._get_sm", return_value=sm):
            response = client.post("/sessions/work/execute", json={"script": "return document.title"})
        assert response.status_code == 200
        assert response.json()["data"]["result"] == "title"


class TestStatus:
    def test_status_no_vnc_fields(self, client):
        """/status 不再下发 VNC 敏感字段（已迁至 /api/auth/me）。"""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "vnc_password" not in data

    def test_me_contains_vnc_fields(self, client):
        """认证关闭时 /api/auth/me 直接可见（本地模式），返回 VNC 配置。"""
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "vnc_enabled" in data
        assert "vnc_password" in data


class TestInstanceRestart:
    def test_restart_existing_instance(self, client):
        """POST /instances/{key}/restart 拉起已停止实例。"""
        inst = MagicMock()
        inst.ensure.return_value = MagicMock()
        with patch("src.main.browser_manager") as pool:
            pool.get_existing.return_value = inst
            response = client.post("/instances/user_1/restart")
        assert response.status_code == 200
        assert response.json()["code"] == 0
        inst.ensure.assert_called_once()

    def test_restart_missing_instance(self, client):
        with patch("src.main.browser_manager") as pool:
            pool.get_existing.return_value = None
            response = client.post("/instances/ghost/restart")
        assert response.status_code == 200
        assert response.json()["code"] == 1


class TestDeleteCookie:
    def test_delete_cookie(self, client, mock_session_manager):
        """DELETE /sessions/{id}/cookies 按域名+名称删除。"""
        session = mock_session_manager[1]
        session.delete_cookie.return_value = True
        with patch("src.api.routes._get_sm", return_value=mock_session_manager[0]):
            response = client.delete("/sessions/work/cookies", params={"domain": "pterclub.net", "name": "PHPSESSID"})
        assert response.status_code == 200
        assert response.json()["code"] == 0
        session.delete_cookie.assert_called_once_with("pterclub.net", "PHPSESSID")


class TestClearRecovered:
    def test_clear_recovered_route(self, client, mock_session_manager):
        """DELETE /sessions/recovered 清空遗留记录。"""
        sm = mock_session_manager[0]
        sm.clear_recovered.return_value = 3
        with patch("src.api.routes._get_sm", return_value=sm):
            response = client.delete("/sessions/recovered")
        assert response.status_code == 200
        assert response.json()["code"] == 0
        assert "3" in response.json()["message"]
