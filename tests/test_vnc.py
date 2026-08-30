"""VncStack 生命周期测试 — 防 websockify/x11vnc 进程泄漏。"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.browser_manager import vnc as vnc_module
from src.core.browser_manager.vnc import VncStack


@pytest.fixture(autouse=True)
def _enable_vnc(monkeypatch):
    monkeypatch.setattr(vnc_module, "VNC_ENABLED", True)
    VncStack._active_by_port.clear()
    yield
    VncStack._active_by_port.clear()


def _fake_proc(alive: bool = True) -> MagicMock:
    proc = MagicMock()
    proc.poll.return_value = None if alive else 0
    return proc


def _stack(port: int = 6081, key: str = "default") -> VncStack:
    return VncStack(key, ":1", 5901, port)


class TestVncStackStart:
    def test_start_spawns_both(self):
        with patch.object(vnc_module.subprocess, "Popen", side_effect=lambda *a, **k: _fake_proc()) as popen:
            stack = _stack()
            stack.start()
        assert popen.call_count == 2
        assert VncStack._active_by_port[6081] is stack

    def test_idempotent_when_both_alive(self):
        with patch.object(vnc_module.subprocess, "Popen", side_effect=lambda *a, **k: _fake_proc()) as popen:
            stack = _stack()
            stack.start()
            stack.start()
        assert popen.call_count == 2  # 第二次不重复拉起

    def test_partial_death_restarts_without_leak(self):
        """x11vnc 死亡、websockify 存活时重启：旧 websockify 必须先被停掉。"""
        procs: list[MagicMock] = []

        def factory(*args, **kwargs):
            p = _fake_proc()
            procs.append(p)
            return p

        with patch.object(vnc_module.subprocess, "Popen", side_effect=factory):
            stack = _stack()
            stack.start()
            x11vnc_1, websockify_1 = procs[0], procs[1]
            # 模拟部分死亡：x11vnc 退出，websockify 仍存活
            x11vnc_1.poll.return_value = 0
            stack.start()

        x11vnc_1.terminate.assert_called_once()
        websockify_1.terminate.assert_called_once()  # 旧 websockify 被清理，不泄漏
        assert stack._websockify_proc is not websockify_1
        assert len(procs) == 4  # 两次启动各 2 个进程

    def test_object_replacement_stops_previous_stack(self):
        """同端口新建 VncStack（旧对象句柄还在）→ 启动前停掉旧栈。"""
        procs: list[MagicMock] = []

        def factory(*args, **kwargs):
            p = _fake_proc()
            procs.append(p)
            return p

        with patch.object(vnc_module.subprocess, "Popen", side_effect=factory):
            old = _stack(key="default")
            old.start()
            old_x11vnc, old_ws = procs[0], procs[1]

            new = _stack(key="default")  # 同端口新对象（模拟实例对象被替换）
            new.start()

        old_x11vnc.terminate.assert_called_once()
        old_ws.terminate.assert_called_once()
        assert VncStack._active_by_port[6081] is new

    def test_stop_unregisters(self):
        with patch.object(vnc_module.subprocess, "Popen", side_effect=lambda *a, **k: _fake_proc()):
            stack = _stack()
            stack.start()
            stack.stop()
        assert 6081 not in VncStack._active_by_port

    def test_vnc_disabled_noop(self, monkeypatch):
        monkeypatch.setattr(vnc_module, "VNC_ENABLED", False)
        with patch.object(vnc_module.subprocess, "Popen") as popen:
            _stack().start()
        popen.assert_not_called()
