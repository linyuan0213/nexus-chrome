"""测试指纹画像模型、环境变量渲染与本地画像读取。"""

import json

from src.fp.profile import FpProfile, RolloutRule
from src.fp.render import render_env
from src.fp.store import store
from src.fp.sync_client import get_profile, get_profile_local, invalidate_cache

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

    def test_webgl_params_rendered_as_enum_pairs(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_params = {"MAX_TEXTURE_SIZE": 16384, "MAX_SAMPLES": 8}
        env = render_env(profile.fingerprint)
        pairs = dict(p.split(":") for p in env["FP_WEBGL_PARAMS"].split(","))
        assert pairs == {"3379": "16384", "36183": "8"}

    def test_webgl_params_unknown_name_skipped(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_params = {"NOT_A_PARAM": 1, "MAX_SAMPLES": 4}
        env = render_env(profile.fingerprint)
        assert env["FP_WEBGL_PARAMS"] == "36183:4"

    def test_webgl_viewport_dims(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_viewport_dims = [32767, 32767]
        env = render_env(profile.fingerprint)
        assert env["FP_WEBGL_VIEWPORT_DIMS"] == "32767,32767"
        # 长度不为 2（显式无效）时回退到按平台自动生成
        profile.fingerprint.webgl_viewport_dims = [1]
        env2 = render_env(profile.fingerprint)
        assert env2["FP_WEBGL_VIEWPORT_DIMS"] == "16384,16384"  # Linux/Mesa 平台

    def test_webgl_extensions_remove(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_extensions_remove = ["WEBGL_compressed_texture_astc"]
        env = render_env(profile.fingerprint)
        assert env["FP_WEBGL_EXTENSIONS_REMOVE"] == "WEBGL_compressed_texture_astc"

    def test_auto_webgl_params_when_not_set(self):
        """画像未设 webgl_params 时自动按平台生成自洽参数。"""
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_params = {}
        profile.fingerprint.webgl_viewport_dims = []
        profile.fingerprint.platform = "MacIntel"
        env = render_env(profile.fingerprint)
        pairs = dict(p.split(":") for p in env["FP_WEBGL_PARAMS"].split(","))
        assert pairs["34921"] == "16"  # MAX_VERTEX_ATTRIBS
        assert pairs["36203"] == "4294967294"  # MAX_ELEMENT_INDEX
        assert env["FP_WEBGL_VIEWPORT_DIMS"] == "16384,16384"  # macOS

    def test_auto_webgl_params_windows_viewport(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_params = {}
        profile.fingerprint.webgl_viewport_dims = []
        profile.fingerprint.platform = "Win32"
        env = render_env(profile.fingerprint)
        pairs = dict(p.split(":") for p in env["FP_WEBGL_PARAMS"].split(","))
        assert pairs["36349"] == "1024"  # D3D11 MAX_FRAGMENT_UNIFORM_VECTORS
        assert env["FP_WEBGL_VIEWPORT_DIMS"] == "32767,32767"  # D3D11

    def test_explicit_webgl_params_takes_precedence(self):
        profile = FpProfile(**json.loads(DEFAULT_PROFILE_JSON))
        profile.fingerprint.webgl_params = {"MAX_SAMPLES": 4}
        profile.fingerprint.platform = "MacIntel"
        env = render_env(profile.fingerprint)
        assert env["FP_WEBGL_PARAMS"] == "36183:4"
        assert "34921" not in env["FP_WEBGL_PARAMS"]


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

    def test_cache_invalidation(self):
        """画像更新后 invalidate_cache 使新读取立即拿到新版本（否则 TTL 内返回旧值）。"""
        invalidate_cache()
        _seed_profile()
        assert get_profile("site-audiences").fingerprint.cores == 8  # type: ignore[union-attr]

        # 更新画像但不失效缓存：TTL 内返回旧值
        data = json.loads(DEFAULT_PROFILE_JSON)
        fp = {k: v for k, v in data.pop("fingerprint").items()}
        fp["cores"] = 16
        store.create_or_update({**data, "fingerprint": fp})
        assert get_profile("site-audiences").fingerprint.cores == 8  # type: ignore[union-attr]

        # 失效后立即拿到新值
        invalidate_cache("site-audiences")
        assert get_profile("site-audiences").fingerprint.cores == 16  # type: ignore[union-attr]

        # 全量失效
        invalidate_cache()
        assert get_profile("site-audiences").fingerprint.cores == 16  # type: ignore[union-attr]
