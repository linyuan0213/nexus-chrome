"""测试指纹画像模型、环境变量渲染与本地画像读取。"""

import json

from src.fp.profile import FpProfile, RolloutRule
from src.fp.render import render_env
from src.fp.store import store
from src.fp.sync_client import get_profile, get_profile_local

DEFAULT_PROFILE_JSON = json.dumps(
    {
        "profile_id": "site-audiences",
        "name": "Audiences 站点画像",
        "version": 1,
        "fingerprint": {
            "ua": "Mozilla/5.0 (X11; Linux x86_64) Chrome/151.0.0.0",
            "cores": 8,
            "memory": 8,
            "canvas_seed": 42,
        },
    }
)


def _reset() -> None:
    store.reset()


def _seed_profile() -> None:

    data = json.loads(DEFAULT_PROFILE_JSON)
    fp = {k: v for k, v in data.pop("fingerprint").items()}
    store.create_or_update({**data, "fingerprint": fp})


class TestFpProfile:
    def test_defaults(self):
        profile = FpProfile(profile_id="site-audiences")
        assert profile.fingerprint.languages == ["zh-CN", "zh"]
        assert profile.fingerprint.webgl_vendor == "Intel Inc."
        assert profile.version == 1

    def test_parse_from_dict(self):
        data = json.loads(DEFAULT_PROFILE_JSON)
        profile = FpProfile(**data)
        assert profile.fingerprint.cores == 8
        assert profile.fingerprint.canvas_seed == 42

    def test_rollout(self):
        profile = FpProfile(profile_id="x", rollout=RolloutRule(percent=100))
        assert profile.is_rolled_out_to("any-node") is True
        profile = FpProfile(profile_id="x", rollout=RolloutRule(percent=0))
        assert profile.is_rolled_out_to("any-node") is False
        profile = FpProfile(profile_id="x", rollout=RolloutRule(percent=0, nodes=["node-a"]))
        assert profile.is_rolled_out_to("node-a") is True
        assert profile.is_rolled_out_to("node-b") is False


class TestRenderEnv:
    def test_basic_mapping(self):
        data = json.loads(DEFAULT_PROFILE_JSON)
        profile = FpProfile(**data)
        env = render_env(profile.fingerprint)
        assert env["FP_UA"] == "Mozilla/5.0 (X11; Linux x86_64) Chrome/151.0.0.0"
        assert env["FP_CORES"] == "8"
        assert env["FP_CANVAS_SEED"] == "42"
        assert env["FP_WEBGL_VENDOR"] == "Intel Inc."

    def test_list_fields_joined(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        env = render_env(profile.fingerprint)
        assert env["FP_LANGS"] == "zh-CN,zh"

    def test_bool_rendered_as_01(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        env = render_env(profile.fingerprint)
        assert env["FP_CANVAS_NOISE"] == "1"

    def test_empty_fields_skipped(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.rtc_ip = ""
        env = render_env(profile.fingerprint)
        assert "FP_RTC_IP" not in env


class TestProfileStore:
    def setup_method(self):
        _reset()

    def test_get_profile_local(self):
        _seed_profile()
        profile = get_profile_local("site-audiences")
        assert profile is not None
        assert profile.fingerprint.cores == 8

    def test_get_profile(self):
        _seed_profile()
        profile = get_profile("site-audiences", use_cache=False)
        assert profile is not None
        assert profile.fingerprint.memory == 8

    def test_missing_profile(self):
        assert get_profile("no-such-profile", use_cache=False) is None
