"""认证服务与中间件测试。"""

import pytest

from src.core.auth.service import API_KEY_PREFIX, AuthService


@pytest.fixture
def svc(tmp_path):
    """独立实例（临时 key 文件），避免污染全局单例。"""
    return AuthService(key_file=str(tmp_path / "api_keys.json"))


@pytest.fixture
def enabled_svc(svc, monkeypatch):
    monkeypatch.setattr("src.core.auth.service.AUTH_PASSWORD", "test-secret")
    return svc


class TestLogin:
    def test_disabled_when_no_password(self, svc):
        assert svc.enabled is False
        assert svc.login("anything") is None

    def test_login_success_and_verify(self, enabled_svc):
        token = enabled_svc.login("test-secret")
        assert token is not None
        assert enabled_svc.verify(token, "/sessions") is True

    def test_login_wrong_password(self, enabled_svc):
        assert enabled_svc.login("wrong") is None

    def test_logout_invalidates(self, enabled_svc):
        token = enabled_svc.login("test-secret")
        enabled_svc.logout(token)
        assert enabled_svc.verify(token, "/sessions") is False

    def test_expired_session_rejected(self, enabled_svc):
        token = enabled_svc.login("test-secret")
        enabled_svc._sessions[token] = 0  # 强制过期
        assert enabled_svc.verify(token, "/sessions") is False


class TestApiKeys:
    def test_create_and_verify(self, svc):
        rec = svc.create_key("tester", ["sessions"])
        assert rec["key"].startswith(API_KEY_PREFIX)
        assert rec["prefix"] != rec["key"]  # 只存前缀
        assert svc.verify(rec["key"], "/sessions") is True

    def test_scope_restriction(self, svc):
        rec = svc.create_key("sessions-only", ["sessions"])
        assert svc.verify(rec["key"], "/sessions/abc") is True
        assert svc.verify(rec["key"], "/instances") is False

    def test_wildcard_scope(self, svc):
        rec = svc.create_key("admin-bot", ["*"])
        assert svc.verify(rec["key"], "/instances") is True

    def test_revoke(self, svc):
        rec = svc.create_key("temp", ["*"])
        assert svc.revoke_key(rec["id"]) is True
        assert svc.verify(rec["key"], "/sessions") is False
        assert svc.revoke_key(rec["id"]) is False  # 重复吊销

    def test_persistence(self, svc, tmp_path):
        rec = svc.create_key("persist", ["sessions"])
        svc2 = AuthService(key_file=str(tmp_path / "api_keys.json"))
        assert svc2.verify(rec["key"], "/sessions") is True
        assert svc2.list_keys()[0]["name"] == "persist"
        assert "key_hash" not in svc2.list_keys()[0]  # 摘要不外泄

    def test_wrong_key_rejected(self, svc):
        svc.create_key("x", ["*"])
        assert svc.verify("ncmk_wrong-key", "/sessions") is False


class TestAuthMiddleware:
    """中间件：AUTH_PASSWORD 启用后保护非白名单路径。"""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.core.auth.service.AUTH_PASSWORD", "test-secret")
        svc = AuthService(key_file=str(tmp_path / "keys.json"))
        # 路由与中间件分别持有引用，需要同时替换
        monkeypatch.setattr("src.main.auth_service", svc)
        monkeypatch.setattr("src.api.auth.auth_service", svc)
        from fastapi.testclient import TestClient

        from src.main import app

        with TestClient(app) as c:
            yield c, svc

    def test_unauthenticated_401(self, client):
        c, _ = client
        assert c.get("/sessions").status_code == 401

    def test_exempt_paths(self, client):
        c, _ = client
        assert c.get("/").status_code == 200
        assert c.get("/status").status_code == 200
        assert c.get("/api/auth/config").status_code == 200

    def test_login_then_access(self, client):
        c, svc = client
        r = c.post("/api/auth/login", json={"password": "test-secret"})
        assert r.status_code == 200
        token = r.json()["data"]["token"]
        r2 = c.get("/sessions", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200

    def test_api_key_scope(self, client):
        c, svc = client
        key = svc.create_key("bot", ["instances"])["key"]
        assert c.get("/instances", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert c.get("/sessions", headers={"Authorization": f"Bearer {key}"}).status_code == 401

    def test_fp_token_still_works(self, client, monkeypatch):
        """FP_ADMIN_TOKEN 兼容：画像接口不受全局中间件拦截。"""
        monkeypatch.setattr("src.api.fp_profiles._FP_ADMIN_TOKEN", "fp-secret")
        # 重新构造中间件可见的 is_fp_credential
        from src.api import fp_profiles

        monkeypatch.setattr("src.main.is_fp_credential", fp_profiles.is_fp_credential)
        c, _ = client
        r = c.get("/api/profiles", params={"Authorization": "Bearer fp-secret"})
        assert r.status_code == 200

    def test_me_requires_auth(self, client):
        c, svc = client
        assert c.get("/api/auth/me").status_code == 401
        token = svc.login("test-secret")
        r = c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert "vnc_password" in r.json()["data"]

    def test_keys_management(self, client):
        c, svc = client
        token = svc.login("test-secret")
        headers = {"Authorization": f"Bearer {token}"}
        r = c.post("/api/auth/keys", json={"name": "ci", "scopes": ["sessions"]}, headers=headers)
        assert r.status_code == 200
        key_id = r.json()["data"]["id"]
        assert c.get("/api/auth/keys", headers=headers).status_code == 200
        assert c.delete(f"/api/auth/keys/{key_id}", headers=headers).status_code == 200
