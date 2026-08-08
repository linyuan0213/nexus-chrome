"""指纹配置 API 集成测试（内建于 nexus-chrome）。"""

from fastapi.testclient import TestClient

from src.fp.store import store
from src.main import app

client = TestClient(app)


def _reset():
    store.reset()


class TestFpApi:
    def setup_method(self):
        _reset()

    def test_create_and_get(self):
        r = client.post(
            "/api/profiles",
            json={
                "profile_id": "site-audiences",
                "name": "测试画像",
                "fingerprint": {"ua": "Mozilla/5.0 Test/1.0", "cores": 8},
            },
        )
        assert r.status_code == 200
        assert r.json()["data"]["version"] == 1

        r = client.get("/api/profiles/site-audiences")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["version"] == 1
        assert data["data"]["ua"] == "Mozilla/5.0 Test/1.0"
        assert data["signature"]

    def test_update_bumps_version(self):
        for _ in range(2):
            client.post("/api/profiles", json={"profile_id": "x", "fingerprint": {"cores": 8}})
        r = client.get("/api/profiles/x")
        assert r.json()["data"]["version"] == 2

    def test_rollback(self):
        client.post("/api/profiles", json={"profile_id": "x", "fingerprint": {"cores": 8}})
        client.post("/api/profiles", json={"profile_id": "x", "fingerprint": {"cores": 16}})
        r = client.post("/api/profiles/x/rollback?to_version=1")
        assert r.status_code == 200
        assert r.json()["data"]["version"] == 1
        assert client.get("/api/profiles/x").json()["data"]["data"]["cores"] == 8

    def test_gray(self):
        client.post("/api/profiles", json={"profile_id": "x"})
        r = client.post("/api/profiles/x/gray", json={"percent": 20})
        assert r.status_code == 200
        assert r.json()["data"]["rollout"]["percent"] == 20

    def test_heartbeat(self):
        client.post("/api/profiles", json={"profile_id": "x"})
        client.post("/api/profiles", json={"profile_id": "x"})
        r = client.get("/api/nodes/n1/heartbeat", params={"profile_id": "x", "profile_version": 1})
        assert r.status_code == 200
        assert r.json()["data"]["should_reload"] is True

    def test_not_found(self):
        r = client.get("/api/profiles/nope")
        assert r.status_code == 404
