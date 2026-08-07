"""测试动态 SwiftShader 伪装器 — 模式匹配、原地 patch、多路径定位。"""

import os

from src.utils.swiftshader_patch import (
    VENDOR_GOOGLE,
    VENDOR_INTEL,
    _has_patchable,
    find_swiftshader_libs,
    patch_bytes,
    patch_lib,
)


def _synthetic_lib() -> bytes:
    """构造一份带 Google/SwiftShader 特征的模拟二进制。"""
    return (
        b"MZ"
        + b"\x00" * 64
        + b"Google\x00"
        + b"SwiftShader Device\x00"
        + b"SwiftShader driver\x00"
        + VENDOR_GOOGLE
        + b"\x01\x02\x03\x04"
        + VENDOR_GOOGLE
        + b"tail"
    )


class TestPatchBytes:
    def test_replaces_all_vendor_ids(self):
        data, stats = patch_bytes(_synthetic_lib())
        assert data.count(VENDOR_GOOGLE) == 0
        assert data.count(VENDOR_INTEL) == 2
        assert stats["vendorID"] == 2

    def test_replaces_strings_keeping_length(self):
        data, stats = patch_bytes(_synthetic_lib())
        assert b"Google" not in data
        assert b"SwiftShader Device" not in data
        assert b"SwiftShader driver" not in data
        assert b"Intel" in data
        assert b"Intel Iris Pro" in data
        assert b"Intel Iris drvr" in data

    def test_output_same_length(self):
        original = _synthetic_lib()
        data, _ = patch_bytes(original)
        assert len(data) == len(original)


class TestPatchableDetection:
    def test_detects_unpatched(self):
        assert _has_patchable(_synthetic_lib()) is True

    def test_clean_binary_not_patchable(self):
        clean = b"\x00" * 128 + b"nothing relevant here"
        assert _has_patchable(clean) is False


class TestPatchLib:
    def test_patch_in_place_with_backup(self, tmp_path):
        lib = tmp_path / "libvk_swiftshader.so"
        lib.write_bytes(_synthetic_lib())
        result = patch_lib(str(lib))
        assert result["patched"] is True
        patched_data = lib.read_bytes()
        assert patched_data.count(VENDOR_GOOGLE) == 0
        assert (tmp_path / "libvk_swiftshader.so.orig").exists()
        assert (tmp_path / "libvk_swiftshader.so.orig").read_bytes().count(VENDOR_GOOGLE) == 2

    def test_already_patched_skips(self, tmp_path):
        lib = tmp_path / "libvk_swiftshader.so"
        already = _synthetic_lib()
        already, _ = patch_bytes(already)
        lib.write_bytes(already)
        result = patch_lib(str(lib))
        assert result["patched"] is False

    def test_missing_file_reports_failure(self, tmp_path):
        result = patch_lib(str(tmp_path / "nope.so"))
        assert result["patched"] is False


class TestFindLibs:
    def test_explicit_path(self, tmp_path):
        lib = tmp_path / "libvk_swiftshader.so"
        lib.write_bytes(b"\x00")
        found = find_swiftshader_libs(explicit=str(lib))
        assert found == [str(lib)]

    def test_explicit_missing_returns_empty(self, tmp_path):
        assert find_swiftshader_libs(explicit=str(tmp_path / "missing.so")) == []

    def test_globs_standard_paths(self):
        # 在已知路径存在时能发现（CI/本机不一定有 Chrome，只验证不抛异常）
        found = find_swiftshader_libs()
        assert isinstance(found, list)
        for p in found:
            assert os.path.basename(p) == "libvk_swiftshader.so"
