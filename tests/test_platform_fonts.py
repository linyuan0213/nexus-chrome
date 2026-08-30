"""平台字体策略测试：按目标平台（macos/windows/linux）约束容器字体指纹。"""

import os
import subprocess
import sys
from pathlib import Path

from src.fp.platform_fonts import BLOCK_BY_PLATFORM, FONTCONFIG_ALIASES, merge_font_block, platform_font_config

REPO_DIR = Path(__file__).resolve().parents[1]
REPO_FONTS_DIR = os.path.join(REPO_DIR, "deploy", "fonts")


class TestBlockByPlatform:
    def test_macos_blocks_windows_fonts(self):
        block = BLOCK_BY_PLATFORM["macos"]
        assert "Calibri" in block
        assert "SimHei" in block
        assert "PMingLiU" in block
        assert "Tahoma" in block
        assert "DejaVu Sans" in block

    def test_macos_keeps_mac_native_fonts(self):
        block = BLOCK_BY_PLATFORM["macos"]
        assert "Arial" not in block
        assert "Georgia" not in block
        assert "Helvetica" not in block
        assert "Times New Roman" not in block

    def test_windows_blocks_linux_and_mac_fonts(self):
        block = BLOCK_BY_PLATFORM["windows"]
        assert "DejaVu Sans" in block
        assert "Noto Sans CJK SC" in block
        assert "Helvetica" in block
        assert "Calibri" not in block

    def test_linux_blocks_windows_fonts_keeps_linux(self):
        block = BLOCK_BY_PLATFORM["linux"]
        assert "Arial" in block
        assert "Calibri" in block
        assert "Helvetica" in block
        assert "DejaVu Sans" not in block
        assert "Carlito" not in block

    def test_wenquanyi_cjk_alias_targets_blocked_on_macos_windows(self):
        """CJK alias 目标字体（WenQuanYi）在 Mac/Windows 上被 C++ 屏蔽枚举，Linux 保留。"""
        assert "WenQuanYi Micro Hei" in BLOCK_BY_PLATFORM["macos"]
        assert "WenQuanYi Micro Hei" in BLOCK_BY_PLATFORM["windows"]
        assert "WenQuanYi Micro Hei" not in BLOCK_BY_PLATFORM["linux"]

    def test_macos_alias_targets_present_in_cpp_block(self):
        """macos 的容器 Linux alias 目标（Liberation 系）在 C++ 黑名单中屏蔽枚举，
        但必须保留 fontconfig 可解析（不进 rejectfont），否则 alias 解析失败。"""
        targets = set(FONTCONFIG_ALIASES["macos"].values())
        assert {"Liberation Sans", "Liberation Serif", "Liberation Mono"} <= targets
        assert {"Liberation Sans", "Liberation Serif", "Liberation Mono"} <= set(BLOCK_BY_PLATFORM["macos"])
        assert "Arial" not in BLOCK_BY_PLATFORM["macos"]


class TestMergeFontBlock:
    def test_explicit_first_no_duplicate(self):
        assert merge_font_block(["MyFont"], ["Arial", "MyFont"]) == ["MyFont", "Arial"]


class TestPlatformFontConfig:
    def test_missing_conf_returns_empty(self, monkeypatch):
        monkeypatch.setattr("src.fp.platform_fonts.FONT_PROFILE_DIR", "/nonexistent/fonts")
        block, path = platform_font_config("macos")
        assert "Calibri" in block
        assert path == ""

    def test_existing_conf_returns_path(self, monkeypatch):
        monkeypatch.setattr("src.fp.platform_fonts.FONT_PROFILE_DIR", REPO_FONTS_DIR)
        _, path = platform_font_config("macos")
        assert path == os.path.join(REPO_FONTS_DIR, "fonts-macos.conf")
        assert os.path.isfile(path)

    def test_unknown_platform_falls_back_to_linux(self):
        block, _ = platform_font_config("banana")
        assert block == BLOCK_BY_PLATFORM["linux"]


class TestFontconfigDriftGuard:
    def test_generated_confs_match_committed(self, tmp_path):
        """重新生成 fontconfig 配置并与提交版字节级比对，防止数据与 conf 漂移。"""
        subprocess.run(
            [sys.executable, str(REPO_DIR / "scripts" / "gen_fontconfig.py"), "--out", str(tmp_path)],
            check=True,
            cwd=REPO_DIR,
            capture_output=True,
        )
        for name in ("fonts-macos.conf", "fonts-windows.conf", "fonts-linux.conf"):
            assert (tmp_path / name).read_bytes() == (REPO_DIR / "deploy" / "fonts" / name).read_bytes()

    def test_alias_targets_excluded_from_rejectfont(self, tmp_path):
        """alias 目标字体不得出现在 rejectfont 中（否则 alias 解析失败）。"""
        subprocess.run(
            [sys.executable, str(REPO_DIR / "scripts" / "gen_fontconfig.py"), "--out", str(tmp_path)],
            check=True,
            cwd=REPO_DIR,
            capture_output=True,
        )
        for platform in ("macos", "windows"):
            targets = set(FONTCONFIG_ALIASES[platform].values())
            conf = (tmp_path / f"fonts-{platform}.conf").read_text()
            for target in targets:
                assert f"<string>{target}</string>" not in conf, (
                    f"{target} 是 alias 目标，不应出现在 {platform} rejectfont 中"
                )
