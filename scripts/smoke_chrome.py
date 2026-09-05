#!/usr/bin/env python3
"""smoke_chrome.py — Chrome 版本冒烟（旁路栈，不打扰生产 9850）

用法:
  python3 scripts/smoke_chrome.py 155.0.8044.0 [--down]
  # 前置: chrome-cache/chrome-<ver>-x64.tar.gz 存在（优先）或 GitHub 可下载
  # 结果: deviceandbrowserinfo isBot=false（mac/windows）+ javlib CF 通过 → exit 0
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = "9860"
BASE = "http://127.0.0.1:" + PORT
IDENTITIES = ["user_1", "user_windows"]
BOT_URL = "https://deviceandbrowserinfo.com/are_you_a_bot"
CF_URL = "https://www.javlibrary.com/tw/"


def run(*cmd: str) -> None:
    subprocess.run(list(cmd), cwd=ROOT, check=True, capture_output=True, text=True)


def api(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read()[:300].decode(errors="replace")}


def wait_ready(timeout: float = 120) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(BASE + "/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(2)
    return False


def nav_and_isbot(sid: str) -> dict:
    api(f"/sessions/{sid}/navigate", "POST", {"url": BOT_URL, "timeout": 50})
    html = ""
    for _ in range(8):
        d = api(f"/sessions/{sid}/html")
        html = d.get("data", {}).get("html") or ""
        m = re.search(r'"isBot":\s*(true|false)', html)
        if m:
            return {"isBot": m.group(1) == "true"}
        time.sleep(6)
    return {"isBot": None, "html_sniff": "no isBot marker"}


def nav_cf(sid: str) -> dict:
    d = api(f"/sessions/{sid}/navigate", "POST", {"url": CF_URL, "timeout": 60})
    data = d.get("data", {})
    title = data.get("title") or ""
    ch = data.get("challenge", {}) or {}
    ok = bool(ch.get("solved")) or "歡迎" in title
    return {"cf_ok": ok, "challenge_solved": ch.get("solved"), "title": title[:40]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="chrome 版本，如 155.0.8044.0")
    ap.add_argument("--down", action="store_true", help="冒烟结束后拆除旁路栈")
    a = ap.parse_args()
    ver = a.version

    cache = ROOT / "chrome-cache" / f"chrome-{ver}-x64.tar.gz"
    if not cache.exists():
        print(f"缺少本地包: {cache}\n请先从构建机拷贝 dist 产物再跑（优先 chrome-cache）。")
        sys.exit(2)

    data_dir = ROOT / f".smoke-{ver}"
    override = ROOT / f".smoke-{ver}.yml"
    if not data_dir.exists():
        data_dir.mkdir()
        shutil.copy(ROOT / "data/fp_config_center.db", data_dir / "fp_config_center.db")
    override.write_text(
        f"""services:
  nexus-chrome:
    image: linyuan0213/nexus-chrome-smoke:{ver}
    container_name: nexus-chrome-smoke-{ver}
    build:
      args:
        CHROME_VERSION: "{ver}"
    ports:
      - "{PORT}:9850"
    volumes:
      - ./{data_dir.name}:/app/data
      - /dev/shm:/dev/shm
"""
    )
    print(f"==> 启动旁路冒烟栈 chrome-{ver}（{PORT}，project smoke-{ver}）")
    run(
        "docker",
        "compose",
        "-p",
        f"smoke-{ver}",
        "-f",
        "docker-compose.yml",
        "-f",
        override.name,
        "up",
        "-d",
        "--build",
    )

    if not wait_ready():
        print("服务未就绪")
        sys.exit(1)

    results = {}
    ok = True
    for pid in IDENTITIES:
        api("/sessions", "POST", {"session_id": f"sm_{pid}", "fp_profile_id": pid})
        bot = nav_and_isbot(f"sm_{pid}")
        cf = nav_cf(f"sm_{pid}")
        results[pid] = {**bot, **cf}
        good = bot["isBot"] is False and cf["cf_ok"]
        ok = ok and good
        print(f"  {pid:14} isBot={bot['isBot']} cf_ok={cf['cf_ok']} title={cf['title']} {'PASS' if good else 'FAIL'}")
        api(f"/sessions/sm_{pid}", "DELETE")

    if a.down:
        run(
            "docker",
            "compose",
            "-p",
            f"smoke-{ver}",
            "-f",
            "docker-compose.yml",
            "-f",
            override.name,
            "down",
        )
        override.unlink(missing_ok=True)

    summary = {"version": ver, "ok": ok, "results": results}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
