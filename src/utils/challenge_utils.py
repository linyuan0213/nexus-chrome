"""挑战检测和处理工具"""

import random
import time
from typing import Any, NamedTuple, Optional, Tuple

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.config.settings import CHALLENGE_BOX_SELECTORS, CHALLENGE_SELECTORS, CHALLENGE_TITLES
from src.utils.humanize import human_click

# 单次点击后的判定等待窗口（秒）
_CLICK_JUDGE_TIMEOUT_S = 8.0


def _page_title_lower(page: Any) -> str:
    """廉价读取页面标题（DrissionPage title 走 CDP，远快于全量 html 序列化）。"""
    t0 = time.monotonic()
    try:
        t = str(page.title or "").strip().lower()  # type: ignore[union-attr]
        logger.debug(f"perf: page.title = {t!r} ({time.monotonic() - t0:.2f}s)")
        return t
    except Exception as e:
        logger.debug(f"perf: page.title 读取失败({e}) ({time.monotonic() - t0:.2f}s)")
        return ""


def page_title_is_challenge(page: Any) -> bool:
    """快路径：页面标题是否命中已知挑战标题（无需读全量 HTML）。

    读全量 HTML 在带跨域 iframe 的 CF 拦截页上约需 10s，而标题判定是
    CDP 单次调用。命中即确认仍在挑战页；未命中不能断言不在挑战（可能
    是无标题拦截页），需调用方回退完整检查。
    """
    t = _page_title_lower(page)
    return any(t == x.lower() for x in CHALLENGE_TITLES)


def under_challenge(html_text: str) -> bool:
    """
    检查页面是否处于挑战状态

    Args:
        html_text: 要检查的HTML内容

    Returns:
        bool: 如果页面处于挑战状态则为True，否则为False
    """
    # 获取页面标题
    if not html_text:
        return False

    page_title = str(pq(html_text)("title").text()).lower()  # type: ignore
    logger.debug(f"under_challenge page_title={page_title}")

    for title in CHALLENGE_TITLES:
        if page_title == title.lower():
            return True

    for selector in CHALLENGE_SELECTORS:
        html_doc = pq(html_text)
        if html_doc(selector):
            return True

    return False


def under_box_challenge(html_text: str) -> bool:
    """
    检查页面是否处于盒子挑战状态

    Args:
        html_text: 要检查的HTML内容

    Returns:
        bool: 如果页面处于盒子挑战状态则为True，否则为False
    """
    if not html_text:
        return False

    for selector in CHALLENGE_BOX_SELECTORS:
        html_doc = pq(html_text)
        if html_doc(selector):
            return True

    return False


class TurnstileBox(NamedTuple):
    """Turnstile 复选框定位结果。

    box: iframe 文档 body 的 shadow root（复选框容器，跨域 iframe 内元素）。
    origin: iframe 在主页面视口中的绝对左上角坐标（用于 CDP 鼠标事件定位，
            iframe 内元素的 rect 是 iframe 相对坐标，必须加上该偏移，
            否则人性化点击会点到错误位置）。
    """

    box: Any
    origin: Optional[Tuple[int, int]]


def locate_turnstile_box(page: ChromiumTab, timeout: int = 5) -> Optional[TurnstileBox]:
    """定位 Turnstile 复选框所在盒子（iframe body 的 shadow root）。

    兼容两种结构：
    1. 业务页面内嵌的 ``.cf-turnstile`` 组件（如签到页）
    2. Cloudflare 拦截页里的 Turnstile 组件（无 ``.cf-turnstile`` 类）

    两种情况下，复选框都位于 ``cf-turnstile-response`` 输入框父级
    shadow root 内的 iframe 文档 body 的 shadow root 中。组件未渲染时
    返回 None，绝不点击页面上的其它元素。

    Returns:
        TurnstileBox(box=shadow root, origin=iframe 绝对坐标)；找不到时返回 None。
    """
    _t = time.monotonic()
    cf_solution = page.ele("tag:input@name=cf-turnstile-response", timeout=min(timeout, 1))  # type: ignore[union-attr]
    logger.debug(f"perf: locate step input {time.monotonic() - _t:.2f}s")
    if not cf_solution:
        logger.debug("locate_turnstile_box: 无 cf-turnstile-response 输入框")
        return None
    try:
        wrapper = cf_solution.parent()  # type: ignore[union-attr]
        shadow = None
        try:
            shadow = wrapper.shadow_root  # type: ignore[union-attr]
        except Exception:
            shadow = None
        if not shadow:
            # 新版结构：shadow host 是 wrapper 内的 div（input 的兄弟节点），
            # 例如 .cf-turnstile > div > [div(host), input]
            try:
                host = wrapper.ele("tag:div", timeout=min(timeout, 1))  # type: ignore[union-attr]
                if host:
                    shadow = host.shadow_root  # type: ignore[union-attr]
            except Exception:
                shadow = None
        if not shadow:
            logger.debug("locate_turnstile_box: 输入框父级无 shadow root")
            return None
        _t2 = time.monotonic()
        cframe = shadow.ele("css:iframe", timeout=min(timeout, 1))  # type: ignore[union-attr]
        logger.debug(f"perf: locate step iframe {time.monotonic() - _t2:.2f}s")
        if not cframe:
            logger.debug("locate_turnstile_box: shadow root 内无 iframe")
            return None
        _t3 = time.monotonic()
        try:
            box: Any = cframe.ele("tag:body", timeout=min(timeout, 2)).shadow_root  # type: ignore[union-attr]
        except Exception:
            box = None
        logger.debug(f"perf: locate step body {time.monotonic() - _t3:.2f}s")
        # iframe 在主页面视口的绝对坐标（cframe 在主 frame 的 shadow DOM 中，
        # rect 为主 frame 视口坐标）。读取失败时 origin=None，点击回退元素级 CDP。
        origin: Optional[Tuple[int, int]] = None
        try:
            rect = cframe.rect  # type: ignore[reportUnknownVariableType, reportUnknownMemberType]
            origin = (  # type: ignore[reportUnknownMemberType]
                round(rect.viewport_location[0]),  # type: ignore[reportUnknownMemberType]
                round(rect.viewport_location[1]),  # type: ignore[reportUnknownMemberType]
            )
        except Exception as e:
            logger.debug(f"locate_turnstile_box: 读取 iframe 坐标失败: {e}")
        logger.debug(f"locate_turnstile_box: 定位到 iframe={bool(cframe)} box={bool(box)} origin={origin}")  # type: ignore[reportUnknownArgumentType]
        return TurnstileBox(box=box, origin=origin)  # type: ignore[reportUnknownVariableType]
    except Exception as e:
        logger.debug(f"locate_turnstile_box: 定位失败: {e}")
        return None


def turnstile_token(page: ChromiumTab) -> str:
    """读取页面中 Turnstile 响应输入框已生成的 token（空串表示未完成）。"""
    try:
        inp = page.ele("tag:input@name=cf-turnstile-response", timeout=1)  # type: ignore[union-attr]
        return str(inp.attr("value") or "") if inp else ""
    except Exception:
        return ""


def _checkbox_viewport_center(btn: Any, origin: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    """取复选框的主页面视口中心坐标，带 ±3px 随机偏移更像真人。

    iframe 内元素的 rect 是 iframe 相对坐标，必须加上 iframe 在主页面
    视口中的绝对偏移 origin；origin 不可用（None）时返回 None，调用方
    回退元素级 CDP 点击。
    """
    if origin is None:
        return None
    try:
        rect: Any = btn.rect
        x = origin[0] + rect.viewport_location[0] + rect.size[0] / 2
        y = origin[1] + rect.viewport_location[1] + rect.size[1] / 2
        return round(x) + random.randint(-3, 3), round(y) + random.randint(-3, 3)
    except Exception as e:
        logger.debug(f"turnstile_click: 读取复选框坐标失败: {e}")
        return None


def _find_turnstile_checkbox(box: Any) -> Any:
    """在 Turnstile 盒子（shadow root）内查找可点击复选框。"""
    for selector in (
        "css:input[type=checkbox]",
        "css:div[role=checkbox]",
        'css:[data-role="checkbox"]',
        "css:div.ctp-checkbox",
    ):
        try:
            el = box.ele(selector, timeout=2)  # type: ignore[union-attr]
        except Exception:
            el = None
        if el:
            return el
    return None


def turnstile_click(page: ChromiumTab, target_box: TurnstileBox, max_attempts: int = 3) -> bool:
    """人性化点击 Turnstile 复选框（shadow root 内），最多重试 max_attempts 次。

    新版 Turnstile 的可点击元素通常是 ``input[type=checkbox]``
    （aria-label 如“请验证您是真人”），老版本则是 ``div[role=checkbox]``。
    只接受复选框类元素，避免 shadow root 为空时泄漏到页面元素导致误点。

    点击采用人性化贝塞尔轨迹（移动 + 按下/释放），对抗 CF 的鼠标行为检测。
    坐标 = iframe 绝对偏移 + 复选框 iframe 内相对中心 + 微小随机偏移；
    坐标不可用时回退元素级 CDP 点击（btn.click 自带 iframe 偏移）。
    每次点击后等待判定（success 标记或 token），未通过则重试。
    """
    box = target_box.box
    origin = target_box.origin
    for attempt in range(1, max_attempts + 1):
        btn = _find_turnstile_checkbox(box)
        if not btn:
            # 组件可能尚未渲染出复选框，稍等重试
            logger.debug(f"turnstile_click: 第 {attempt} 次未找到复选框")
            if attempt < max_attempts:
                time.sleep(1.5)
                continue
            return False

        target = _checkbox_viewport_center(btn, origin)
        clicked = False
        if target is not None:
            try:
                logger.debug(f"turnstile_click: 人性化点击 ({target[0]}, {target[1]})")
                human_click(page, target)
                clicked = True
            except Exception as e:
                logger.debug(f"turnstile_click: 人性化点击失败({e})，回退元素点击")
        if not clicked:
            try:
                btn.click()  # type: ignore[union-attr]
                clicked = True
            except Exception as e:
                logger.debug(f"turnstile_click: btn.click 失败({e})，回退 actions")
                try:
                    page.actions.move_to(btn, duration=0.8)  # type: ignore[union-attr]
                    page.actions.click(btn)  # type: ignore[union-attr]
                    clicked = True
                except Exception as e2:
                    logger.debug(f"turnstile_click: actions 点击也失败: {e2}")
        if not clicked:
            continue

        # 等待本次点击的判定结果（成功标记出现或拿到 token 或页面已脱离挑战）
        deadline = time.monotonic() + _CLICK_JUDGE_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                if _turnstile_success(box):
                    return True
            except Exception as e:
                logger.debug(f"turnstile_click: success 判定失败（盒子可能已重渲染）: {e}")
            try:
                if turnstile_token(page):
                    return True
            except Exception as e:
                logger.debug(f"turnstile_click: token 读取失败: {e}")
            # 快退：标题已脱离挑战（CF 走 JS 自动通过时点击可能不产生 success 标记）
            if not page_title_is_challenge(page):
                return True
            time.sleep(0.5)
        logger.debug(f"turnstile_click: 第 {attempt} 次点击未通过判定")
    return False


def _turnstile_success(box: Any) -> bool:
    """判断 Turnstile 是否已通过。"""
    try:
        succ = box.ele("tag:div@id=success", timeout=1)  # type: ignore[union-attr]
        return bool(succ and succ.style("visibility") == "visible")  # type: ignore[union-attr]
    except Exception:
        return False


def _turnstile_error(page: ChromiumTab, box: Any) -> bool:
    """判断 Turnstile 是否报“验证失败/故障排除”等错误。"""
    try:
        err = box.ele("css:#challenge-error-text", timeout=1)  # type: ignore[union-attr]
        if err and err.text:
            return True
    except Exception as e:
        logger.debug(f"读取 Turnstile 错误元素失败: {e}")
    try:
        body = page.ele("tag:body", timeout=1)  # type: ignore[union-attr]
        text: str = str(body.text) if body else ""
    except Exception:
        text = ""
    lowered = text.lower()
    return "验证失败" in text or "verification failed" in lowered or "troubleshooting" in lowered or "故障排除" in text


def _solve_turnstile(
    page: ChromiumTab,
    tries: int,
    is_box: bool,
    prelocated: Optional[TurnstileBox] = None,
) -> Tuple[bool, bool]:
    """尝试解决 Turnstile 挑战，失败时刷新页面重试。

    Args:
        page: 浏览器标签页。
        tries: 最大尝试次数。
        is_box: 是否盒子挑战（决定检测函数）。
        prelocated: 调用方已定位的盒子（避免跨域 iframe 帧连接重复耗时，
            一次挑战解决流程只连接一次，约省 20s+）。

    Returns:
        (success, was_challenge)
    """
    check = under_box_challenge if is_box else under_challenge
    success = False
    located = prelocated
    for _ in range(max(1, tries)):
        # 快路径：标题命中挑战标题则不读全量 html（省 ~10s/次）
        if not page_title_is_challenge(page) and not check(page.html):
            success = True
            break

        # 仅在未预定位或盒子失效时才定位（跨域 iframe 帧连接约 10s）
        if located is None or located.box is None:
            located = locate_turnstile_box(page)
            if located is None or located.box is None:
                page.wait(2)
                continue

        if not turnstile_click(page, located):
            page.wait(2)
            continue

        # 等待挑战判定结果。复用已连接的盒子（元素可能重渲染，success/error
        # 判定内部捕获异常），避免每次循环都触发跨域 iframe 帧连接。
        for _ in range(15):
            cur_box = located.box
            if _turnstile_success(cur_box):
                success = True
                break
            if turnstile_token(page):
                success = True
                break
            if _turnstile_error(page, cur_box):
                logger.debug("Cloudflare 验证失败，刷新挑战后重试")
                break
            # 页面已脱离挑战态：连续两次确认（避免 Turnstile 重渲染瞬时变化误判）。
            # 快路径：标题仍命中挑战说明还没通过，直接跳过读 html；标题未命中
            # 才需要全量检查确认（此时已接近通过，读一次可接受）。
            if not page_title_is_challenge(page):
                page.wait(1)
                if not check(page.html):
                    logger.debug("页面已脱离 Cloudflare 挑战态，判定成功")
                    success = True
                    break
            page.wait(1)

        if success:
            break

        # 验证失败时刷新页面重新发起挑战
        try:
            page.refresh()  # type: ignore[union-attr]
        except Exception as e:
            logger.debug(f"刷新挑战页面失败: {e}")
        page.wait(2)
        located = None  # 页面刷新后旧盒子失效，重新定位

    return success, True


def sync_cf_retry(
    page: ChromiumTab,
    tries: int = 5,
    prelocated: Optional[TurnstileBox] = None,
) -> Tuple[bool, bool]:
    """
    同步重试CloudFlare挑战解决

    Args:
        page: 浏览器页面/标签页
        tries: 重试尝试次数
        prelocated: 调用方已定位的盒子（跳过重复跨域 iframe 连接）

    Returns:
        Tuple[bool, bool]: (成功, 是否挑战)
    """
    # 标题命中挑战 → 直接解决（跳过全量 html，省 ~10s）；
    # 标题未命中 → 读一次 html 确认是否挑战，正常页面短路返回
    if prelocated is not None:
        return _solve_turnstile(page, tries, is_box=False, prelocated=prelocated)
    if page_title_is_challenge(page):
        return _solve_turnstile(page, tries, is_box=False)
    if not under_challenge(page.html):
        return True, False
    return _solve_turnstile(page, tries, is_box=False)


def sync_cf_box_retry(
    page: ChromiumTab,
    tries: int = 3,
    prelocated: Optional[TurnstileBox] = None,
) -> Tuple[bool, bool]:
    """
    同步重试CloudFlare盒子挑战解决

    Args:
        page: Browser page/tab
        tries: Number of retry attempts
        prelocated: 调用方已定位的盒子（跳过重复跨域 iframe 连接）

    Returns:
        Tuple[bool, bool]: (success, was_challenge)
    """
    if prelocated is not None:
        return _solve_turnstile(page, tries, is_box=True, prelocated=prelocated)
    if page_title_is_challenge(page):
        return _solve_turnstile(page, tries, is_box=True)
    if not under_box_challenge(page.html):
        return True, False
    return _solve_turnstile(page, tries, is_box=True)
