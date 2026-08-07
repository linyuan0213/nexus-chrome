"""全局事件总线（供 WebSocket 推送）。"""

import asyncio
from collections import defaultdict
from typing import Any, Dict, List, Optional

from loguru import logger

_event_subscribers: Dict[str, List["asyncio.Queue[Dict[str, Any]]"]] = defaultdict(list)


def publish_event(event_type: str, data: Dict[str, Any]) -> None:
    """发布事件到全局总线（异步安全：只放入队列，不等待消费）。"""
    payload = {"type": event_type, "data": data}
    for q in _event_subscribers[event_type]:
        try:
            q.put_nowait(payload)
        except Exception as e:
            logger.debug(f"事件推送失败(队列满或已关闭): {e}")
    # 也推送给"全部事件"订阅者
    for q in _event_subscribers["*"]:
        try:
            q.put_nowait(payload)
        except Exception as e:
            logger.debug(f"事件推送失败(队列满或已关闭): {e}")


async def subscribe_events(event_types: Optional[List[str]] = None) -> "asyncio.Queue[Dict[str, Any]]":
    """创建事件订阅队列（WebSocket 每连接一个）。"""
    q: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=100)
    types = event_types or ["*"]
    for t in types:
        _event_subscribers[t].append(q)
    return q


def unsubscribe_events(q: "asyncio.Queue[Dict[str, Any]]", event_types: Optional[List[str]] = None) -> None:
    for t in event_types or ["*"]:
        try:
            _event_subscribers[t].remove(q)
        except ValueError:
            pass
