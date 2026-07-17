"""测试用户数据目录清理工具。"""

import os
import time

from src.utils.cleanup import cleanup_user_data_dir, get_directory_size


class TestCleanupUserDataDir:
    def test_removes_default_cache_items(self, tmp_path):
        root = tmp_path / "user_data"
        (root / "DeferredBrowserMetrics" / "metrics").mkdir(parents=True)
        (root / "DeferredBrowserMetrics" / "metrics" / "data.bin").write_bytes(b"x" * 100)
        (root / "Default" / "Cache").mkdir(parents=True)
        (root / "Default" / "Cache" / "index").write_bytes(b"y" * 50)
        (root / "Cookies").write_bytes(b"cookie")
        (root / "Local State").write_bytes(b"state")

        result = cleanup_user_data_dir(root, keep_cookies=True)

        assert not (root / "DeferredBrowserMetrics").exists()
        assert not (root / "Default" / "Cache").exists()
        assert (root / "Cookies").exists()
        assert (root / "Local State").exists()
        assert result["removed"] >= 2
        assert result["bytes_freed"] >= 150

    def test_keeps_cookies_when_requested(self, tmp_path):
        root = tmp_path / "user_data"
        root.mkdir()
        (root / "Cookies").write_bytes(b"cookie")
        (root / "Cookies-journal").write_bytes(b"journal")
        (root / "DeferredBrowserMetrics").mkdir()

        cleanup_user_data_dir(root, keep_cookies=True)

        assert (root / "Cookies").exists()
        assert (root / "Cookies-journal").exists()
        assert not (root / "DeferredBrowserMetrics").exists()

    def test_removes_cookies_when_keep_false(self, tmp_path):
        root = tmp_path / "user_data"
        root.mkdir()
        (root / "Cookies").write_bytes(b"cookie")
        (root / "Cookies-journal").write_bytes(b"journal")

        cleanup_user_data_dir(root, keep_cookies=False)

        assert not (root / "Cookies").exists()
        assert not (root / "Cookies-journal").exists()

    def test_respects_max_age(self, tmp_path):
        root = tmp_path / "user_data"
        old_dir = root / "DeferredBrowserMetrics"
        new_dir = root / "Cache"
        old_dir.mkdir(parents=True)
        new_dir.mkdir(parents=True)

        now = time.time()
        os.utime(old_dir, (now - 7200, now - 7200))
        os.utime(new_dir, (now - 60, now - 60))

        result = cleanup_user_data_dir(root, max_age_seconds=3600)

        assert not old_dir.exists()
        assert new_dir.exists()
        assert result["removed"] == 1

    def test_aggressive_mode_removes_additional_items(self, tmp_path):
        root = tmp_path / "user_data"
        (root / "Safe Browsing" / "db").mkdir(parents=True)
        (root / "Safe Browsing" / "db" / "file").write_bytes(b"z")

        cleanup_user_data_dir(root, aggressive=False)
        assert (root / "Safe Browsing").exists()

        cleanup_user_data_dir(root, aggressive=True)
        assert not (root / "Safe Browsing").exists()

    def test_extra_items_can_be_specified(self, tmp_path):
        root = tmp_path / "user_data"
        (root / "MyCustomCache" / "data").mkdir(parents=True)
        (root / "MyCustomCache" / "data" / "file").write_bytes(b"z")

        result = cleanup_user_data_dir(root, extra_items=["MyCustomCache"])

        assert not (root / "MyCustomCache").exists()
        assert result["removed"] == 1

    def test_missing_directory_returns_zero(self, tmp_path):
        root = tmp_path / "does_not_exist"
        result = cleanup_user_data_dir(root)
        assert result == {"removed": 0, "bytes_freed": 0}


class TestGetDirectorySize:
    def test_calculates_total_size(self, tmp_path):
        (tmp_path / "a").write_bytes(b"12345")
        (tmp_path / "b" / "c").mkdir(parents=True)
        (tmp_path / "b" / "c" / "d").write_bytes(b"678")
        assert get_directory_size(tmp_path) == 8

    def test_returns_zero_for_missing_path(self, tmp_path):
        assert get_directory_size(tmp_path / "missing") == 0
