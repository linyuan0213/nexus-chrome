"""SessionManager 持久化注册表测试。"""

import json

from src.core.session.manager import RECOVERED_TTL_SECONDS, SessionManager


class TestRecoveredTTL:
    def test_stale_records_pruned_on_load(self, tmp_path):
        """超过 TTL 的遗留记录在加载时被丢弃。"""
        import time as _time

        now = _time.time()
        p = tmp_path / "sessions.json"
        p.write_text(
            json.dumps(
                {
                    "sessions": [
                        {"id": "fresh", "fingerprint": "stealth", "updated_at": now - 3600},
                        {"id": "stale", "fingerprint": "stealth", "updated_at": now - RECOVERED_TTL_SECONDS - 100},
                        {"id": "legacy-no-ts", "fingerprint": "stealth"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        sm = SessionManager(pool=None, persist_file=str(p))
        ids = [r["id"] for r in sm.recovered_sessions()]
        assert "fresh" in ids
        assert "legacy-no-ts" in ids  # 无时间戳的历史记录保留
        assert "stale" not in ids

    def test_clear_recovered(self, tmp_path):
        p = tmp_path / "sessions.json"
        p.write_text(
            json.dumps({"sessions": [{"id": "a", "fingerprint": "stealth"}]}),
            encoding="utf-8",
        )
        sm = SessionManager(pool=None, persist_file=str(p))
        assert sm.clear_recovered() == 1
        assert sm.recovered_sessions() == []
        assert json.loads(p.read_text(encoding="utf-8"))["sessions"] == []
