"""会话管理包 — Session / SessionManager / 全局事件总线。

Session 按职责沿继承链拆分（自顶向下）：
Session → TabMixin → MediaMixin → DownloadMixin → FetchMixin → CookieMixin → SessionBase
下层 mixin 只调用下层方法（FetchMixin._browser_fetch_get 经 cast 调用顶层 navigate 除外）。
"""

from src.core.session.events import publish_event, subscribe_events, unsubscribe_events
from src.core.session.manager import SessionManager
from src.core.session.session import Session

__all__ = [
    "Session",
    "SessionManager",
    "publish_event",
    "subscribe_events",
    "unsubscribe_events",
]
