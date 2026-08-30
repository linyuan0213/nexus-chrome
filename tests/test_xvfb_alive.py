"""X11/Xvfb 存活性探测测试 — 防容器重启后残留 socket 误判。"""

import socket
import threading

from src.core.browser_manager.process import _unix_socket_alive, _xvfb_socket_alive, display_num


class TestDisplayNum:
    def test_strips_colon(self):
        assert display_num(":1") == 1
        assert display_num("12") == 12


class TestUnixSocketAlive:
    def test_path_not_exists(self, tmp_path):
        assert _unix_socket_alive(str(tmp_path / "nope")) is False

    def test_stale_socket_file_is_not_alive(self, tmp_path):
        """残留 socket 文件（无监听进程）连接被拒绝 → 判定死亡。"""
        stale = tmp_path / "X1"
        stale.touch()
        assert _unix_socket_alive(str(stale)) is False

    def test_listening_socket_is_alive(self, tmp_path):
        """真实监听的 unix socket → 判定存活。"""
        path = str(tmp_path / "X2")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(1)
        stop = threading.Event()

        def serve():
            while not stop.is_set():
                try:
                    srv.settimeout(0.2)
                    conn, _ = srv.accept()
                    conn.close()
                except OSError:
                    pass

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        try:
            assert _unix_socket_alive(path) is True
        finally:
            stop.set()
            srv.close()

    def test_closed_listener_is_dead(self, tmp_path):
        """监听进程退出后（socket 文件仍在）→ 判定死亡。"""
        path = str(tmp_path / "X3")
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(1)
        srv.close()
        assert _unix_socket_alive(path) is False


class TestXvfbSocketAlive:
    def test_nonexistent_display(self):
        """/tmp/.X11-unix/X987 几乎不可能存在。"""
        assert _xvfb_socket_alive(":987") is False
