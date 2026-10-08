"""测试任意 UA 字段派生助手（src/fp/ua.py）。"""

from src.fp.ua import (
    derive_brand_version,
    derive_full_version,
    profile_fits_ua,
    resolve_ua_fields,
    ua_identity,
    ua_major,
)


class TestUaMajor:
    def test_chrome_major_extracted(self):
        assert ua_major("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/96.0.4664.45 Safari/537.36") == "96"

    def test_non_chrome_returns_none(self):
        assert ua_major("Mozilla/5.0 (X11) Gecko/20100101 Firefox/91.0") is None


class TestDerive:
    def test_full_from_major(self):
        assert derive_full_version("...Chrome/120.0.0.0...") == "120.0.0.0"

    def test_explicit_full_preserved(self):
        assert derive_full_version("...Chrome/120.0.0.0...", "120.0.6099.109") == "120.0.6099.109"

    def test_brand_from_major(self):
        assert derive_brand_version("...Chrome/120.0.0.0...") == "120"
        assert derive_brand_version("...Chrome/120.0.0.0...", "119") == "119"


class TestResolve:
    def test_arbitrary_ua_tuple(self):
        r = resolve_ua_fields("Mozilla/5.0 (X11; Linux x86_64) Chrome/96.0.0.0 Safari/537.36")
        assert r == {
            "ua": "Mozilla/5.0 (X11; Linux x86_64) Chrome/96.0.0.0 Safari/537.36",
            "ua_full": "96.0.0.0",
            "ua_brand": "96",
        }

    def test_no_ua_passthrough(self):
        assert resolve_ua_fields(None, "1.2.3.4", "1") == {
            "ua": None,
            "ua_full": "1.2.3.4",
            "ua_brand": "1",
        }


WIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
LINUX_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"


class TestUaIdentity:
    def test_windows_155(self):
        assert ua_identity(WIN_UA) == {"uad_platform": "Windows", "chrome_major": "155"}

    def test_linux_155(self):
        assert ua_identity(LINUX_UA) == {"uad_platform": "Linux", "chrome_major": "155"}

    def test_empty(self):
        assert ua_identity(None) == {"uad_platform": None, "chrome_major": None}


class TestProfileFitsUa:
    _WIN = {"FP_UAD_PLATFORM": "Windows", "FP_UA_BRAND": "155"}

    def test_match_platform_and_major(self):
        assert profile_fits_ua(self._WIN, WIN_UA) is True

    def test_conflict_platform(self):
        assert profile_fits_ua(self._WIN, LINUX_UA) is False

    def test_conflict_major(self):
        assert profile_fits_ua(self._WIN, WIN_UA.replace("Chrome/155", "Chrome/151")) is False

    def test_unknown_ua_not_restricted(self):
        assert profile_fits_ua(self._WIN, "curl/8.0") is True

    def test_missing_env_not_restricted(self):
        assert profile_fits_ua(None, WIN_UA) is True
