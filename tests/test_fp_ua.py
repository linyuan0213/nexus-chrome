"""测试任意 UA 字段派生助手（src/fp/ua.py）。"""

from src.fp.ua import (
    derive_brand_version,
    derive_full_version,
    resolve_ua_fields,
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
