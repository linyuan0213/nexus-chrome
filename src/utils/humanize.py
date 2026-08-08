"""人性化鼠标轨迹 — 对抗滑动/鼠标轨迹检测。

真实鼠标移动特征：
- 路径为轻微弧线（贝塞尔），非直线
- 速度先加速后减速（ease-in-out）
- 存在微小的低频抖动
- 步进间隔有随机性

通过 CDP `Input.dispatchMouseEvent` 逐点驱动，模拟真实鼠标事件序列。
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, List, Tuple

from DrissionPage._pages.chromium_tab import ChromiumTab

Point = Tuple[int, int]


def ease_in_out(t: float) -> float:
    """smoothstep：加速-匀速-减速的时间分布。"""
    return t * t * (3 - 2 * t)


def generate_trajectory(
    start: Point,
    end: Point,
    duration: float = 0.5,
    jitter: float = 0.6,
    curvature: float | None = None,
) -> List[Point]:
    """生成人性化贝塞尔轨迹点（含弧线、加速减速、抖动）。

    Args:
        start: 起点 (x, y)
        end: 终点 (x, y)
        duration: 移动时长（秒）
        jitter: 抖动幅度（像素）
        curvature: 弧线偏移比例（None 时随机 0.05~0.2）
    """
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    dist = (dx * dx + dy * dy) ** 0.5 or 1.0
    if curvature is None:
        curvature = random.uniform(0.05, 0.2)
    perp = curvature * dist

    # 贝塞尔控制点：沿路径方向 1/3、2/3 处，垂直偏移产生弧线
    c1x = sx + dx * 0.3 - dy / dist * perp
    c1y = sy + dy * 0.3 + dx / dist * perp
    c2x = sx + dx * 0.7 - dy / dist * perp * 0.6
    c2y = sy + dy * 0.7 + dx / dist * perp * 0.6

    steps = max(int(duration * 60), 12)
    points: List[Point] = []
    # 低频平滑噪声（用正弦近似，避免随机跳变）
    noise_phase = random.uniform(0, 6.28)
    noise_freq = random.uniform(0.5, 1.5)
    noise_amp_x = random.uniform(0, jitter)
    noise_amp_y = random.uniform(0, jitter * 0.6)

    for i in range(1, steps + 1):
        t = ease_in_out(i / steps)
        mt = 1 - t
        x = mt * mt * mt * sx + 3 * mt * mt * t * c1x + 3 * mt * t * t * c2x + t * t * t * ex
        y = mt * mt * mt * sy + 3 * mt * mt * t * c1y + 3 * mt * t * t * c2y + t * t * t * ey
        # 正弦噪声：平滑低频抖动
        n = noise_amp_x * _sin(noise_phase + i * noise_freq)
        m = noise_amp_y * _sin(noise_phase + i * noise_freq * 0.8 + 1.5)
        points.append((round(x + n), round(y + m)))
    points.append((ex, ey))
    return points


def _sin(v: float) -> float:
    return math.sin(v)


def _dispatch(tab: ChromiumTab, type_: str, x: int, y: int, **kwargs: Any) -> None:
    tab.run_cdp(  # type: ignore[union-attr]
        "Input.dispatchMouseEvent",
        type=type_,
        x=x,
        y=y,
        **kwargs,
    )


def human_move(
    tab: ChromiumTab,
    start: Point,
    end: Point,
    duration: float = 0.5,
) -> None:
    """按人性化轨迹移动鼠标（不按下）。"""
    points = generate_trajectory(start, end, duration)
    for px, py in points:
        _dispatch(tab, "mouseMoved", px, py)
        time.sleep(0.01 + random.random() * 0.008)


def human_drag(
    tab: ChromiumTab,
    start: Point,
    end: Point,
    duration: float = 1.0,
) -> None:
    """人性化拖拽（滑块）：按下 → 弧线移动 → 释放。

    移动起点与滑块按住位置一致，路径为带弧线和速度变化的贝塞尔曲线，
    释放点在终点。适用于滑块验证码等轨迹检测场景。
    """
    _dispatch(tab, "mouseMoved", start[0], start[1])
    time.sleep(0.05 + random.random() * 0.05)
    _dispatch(tab, "mousePressed", start[0], start[1], button="left", clickCount=1)
    time.sleep(0.08 + random.random() * 0.06)
    points = generate_trajectory(start, end, duration)
    for px, py in points:
        _dispatch(tab, "mouseMoved", px, py, button="left", buttons=1)
        time.sleep(0.012 + random.random() * 0.01)
    time.sleep(0.05 + random.random() * 0.04)
    _dispatch(tab, "mouseReleased", end[0], end[1], button="left", clickCount=1)


def human_click(
    tab: ChromiumTab,
    target: Point,
    move_from: Point | None = None,
    duration: float = 0.4,
) -> None:
    """人性化点击：移动到目标（弧线轨迹）→ 按下 → 释放。"""
    start = move_from or (target[0] + random.randint(-80, 80), target[1] + random.randint(-40, 40))
    human_move(tab, start, target, duration)
    time.sleep(0.05 + random.random() * 0.05)
    _dispatch(tab, "mousePressed", target[0], target[1], button="left", clickCount=1)
    time.sleep(0.05 + random.random() * 0.05)
    _dispatch(tab, "mouseReleased", target[0], target[1], button="left", clickCount=1)


def element_center(tab: ChromiumTab, selector: str) -> Point:
    """取元素视口中心坐标（用于轨迹驱动）。"""
    ele: Any = tab.ele(selector)  # type: ignore[union-attr]
    if ele is None:
        raise ValueError(f"元素未找到: {selector}")
    rect = ele.rect
    return (
        round(rect.viewport_location[0] + rect.size[0] / 2),
        round(rect.viewport_location[1] + rect.size[1] / 2),
    )


def human_click_selector(tab: ChromiumTab, selector: str) -> None:
    """按选择器人性化点击元素。"""
    target = element_center(tab, selector)
    human_click(tab, target)


def human_drag_selector(
    tab: ChromiumTab,
    selector: str,
    offset_x: int,
    offset_y: int = 0,
    duration: float = 1.0,
) -> None:
    """按选择器人性化拖拽（滑块向右 offset_x 像素）。"""
    start = element_center(tab, selector)
    end = (start[0] + offset_x, start[1] + offset_y)
    human_drag(tab, start, end, duration)
