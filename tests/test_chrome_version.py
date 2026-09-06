"""验证 Chrome 版本单一事实源（.chrome-version ↔ 镜像 ENV CHROME_VERSION）一致性。

settings 模块在 import 时读取版本，因此用子进程隔离验证两种通道取值一致。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_file_version() -> str:
    return (ROOT / ".chrome-version").read_text().strip()


def _subprocess_ua_full(env_ver: str | None = None) -> tuple[str, str]:
    env = dict(__import__("os").environ)
    if env_ver is not None:
        env["CHROME_VERSION"] = env_ver
    else:
        env.pop("CHROME_VERSION", None)
    code = (
        "from src.config.settings import DEFAULT_UA_FULL, DEFAULT_UA_BRAND; "
        "print(DEFAULT_UA_FULL); print(DEFAULT_UA_BRAND)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = out.stdout.splitlines()
    return (lines[0], lines[1])


class TestChromeVersionSingleSource:
    def test_file_channel_matches_defaults(self):
        full, brand = _subprocess_ua_full()
        file_ver = _read_file_version()
        assert full == file_ver
        assert brand == file_ver.split(".", 1)[0]

    def test_env_channel_overrides_file(self):
        full, brand = _subprocess_ua_full("120.0.6099.109")
        assert full == "120.0.6099.109"
        assert brand == "120"

    def test_env_empty_falls_back_to_file(self):
        full, _ = _subprocess_ua_full("")
        assert full == _read_file_version()
