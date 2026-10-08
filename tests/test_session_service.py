"""测试会话服务 — 会话 UA 与指纹画像的身份自洽编排。"""

from src.services import session_service as svc

WIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
LINUX_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"

_ENVS = {
    "linux_155": {"FP_UAD_PLATFORM": "Linux", "FP_UA_BRAND": "155"},
    "windows_151": {"FP_UAD_PLATFORM": "Windows", "FP_UA_BRAND": "151"},
    "windows_155": {"FP_UAD_PLATFORM": "Windows", "FP_UA_BRAND": "155"},
}


def _fake_resolve(pid):
    return _ENVS.get(pid)


class _FakeStore:
    def __init__(self, ids):
        self._ids = [{"profile_id": i, "enabled": True} for i in ids]

    def list_profiles(self):
        return self._ids


class TestChooseProfileForUa:
    def _patch(self, monkeypatch, ids):
        monkeypatch.setattr(svc, "store", _FakeStore(ids))
        monkeypatch.setattr(svc, "resolve_profile_env", _fake_resolve)

    def test_picks_matching_platform_and_major(self, monkeypatch):
        self._patch(monkeypatch, ["linux_155", "windows_155"])
        assert svc._choose_profile_for_ua(WIN_UA) == "windows_155"

    def test_no_match_returns_none(self, monkeypatch):
        self._patch(monkeypatch, ["windows_151"])
        assert svc._choose_profile_for_ua(WIN_UA) is None


class TestReconcileUaProfile:
    def test_no_ua_keeps_everything(self):
        pid, env, ua = svc._reconcile_ua_profile(None, "windows_151", _ENVS["windows_151"])
        assert (pid, env, ua) == ("windows_151", _ENVS["windows_151"], None)

    def test_consistent_ua_kept(self):
        pid, env, ua = svc._reconcile_ua_profile(WIN_UA, "windows_155", _ENVS["windows_155"])
        assert (pid, ua) == ("windows_155", WIN_UA)

    def test_conflict_rebinds_matching_profile(self, monkeypatch):
        monkeypatch.setattr(svc, "_choose_profile_for_ua", lambda _ua: "windows_155")
        monkeypatch.setattr(svc, "resolve_profile_env", _fake_resolve)
        pid, env, ua = svc._reconcile_ua_profile(WIN_UA, "windows_151", _ENVS["windows_151"])
        assert pid == "windows_155"
        assert env == _ENVS["windows_155"]
        assert ua == WIN_UA

    def test_conflict_without_match_drops_ua(self, monkeypatch):
        monkeypatch.setattr(svc, "_choose_profile_for_ua", lambda _ua: None)
        pid, env, ua = svc._reconcile_ua_profile(WIN_UA, "windows_151", _ENVS["windows_151"])
        assert pid == "windows_151"
        assert ua is None

    def test_ua_without_profile_binds_match(self, monkeypatch):
        monkeypatch.setattr(svc, "_choose_profile_for_ua", lambda _ua: "windows_155")
        monkeypatch.setattr(svc, "resolve_profile_env", _fake_resolve)
        pid, env, ua = svc._reconcile_ua_profile(WIN_UA, None, None)
        assert (pid, ua) == ("windows_155", WIN_UA)

    def test_ua_without_profile_and_no_match_drops_ua(self, monkeypatch):
        monkeypatch.setattr(svc, "_choose_profile_for_ua", lambda _ua: None)
        pid, env, ua = svc._reconcile_ua_profile(WIN_UA, None, None)
        assert (pid, env, ua) == (None, None, None)

    def test_unresolved_env_with_ua_drops_when_no_match(self, monkeypatch):
        monkeypatch.setattr(svc, "_choose_profile_for_ua", lambda _ua: None)
        pid, env, ua = svc._reconcile_ua_profile(WIN_UA, "windows_155", None)
        assert ua is None
