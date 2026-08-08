"""挑战检测和处理工具"""

from typing import Any, Tuple

from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger
from pyquery import PyQuery as pq  # type: ignore[import-untyped]

from src.config.settings import CHALLENGE_BOX_SELECTORS, CHALLENGE_SELECTORS, CHALLENGE_TITLES


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


def locate_turnstile_box(page: ChromiumTab, timeout: int = 5) -> Any:
    """定位 Turnstile 复选框所在盒子（iframe body 的 shadow root）。

    兼容两种结构：
    1. 业务页面内嵌的 ``.cf-turnstile`` 组件（如签到页）
    2. Cloudflare 拦截页里的 Turnstile 组件（无 ``.cf-turnstile`` 类）

    两种情况下，复选框都位于 ``cf-turnstile-response`` 输入框父级
    shadow root 内的 iframe 文档 body 的 shadow root 中。组件未渲染时
    返回 None，绝不点击页面上的其它元素。

    Returns:
        复选框所在盒子（shadow root），找不到时返回 None。
    """
    cf_solution = page.ele("tag:input@name=cf-turnstile-response", timeout=min(timeout, 3))  # type: ignore[union-attr]
    if not cf_solution:
        logger.debug("locate_turnstile_box: 无 cf-turnstile-response 输入框")
        return None
    try:
        wrapper = cf_solution.parent()  # type: ignore[union-attr]
        try:
            shadow = wrapper.shadow_root  # type: ignore[union-attr]
        except Exception:
            shadow = None
        if not shadow:
            logger.debug("locate_turnstile_box: 输入框父级无 shadow root")
            return None
        cframe = shadow.ele("tag:iframe", timeout=min(timeout, 3))  # type: ignore[union-attr]
        if not cframe:
            logger.debug("locate_turnstile_box: shadow root 内无 iframe")
            return None
        try:
            box: Any = cframe.ele("tag:body", timeout=timeout).shadow_root  # type: ignore[union-attr]
        except Exception:
            box = None
        logger.debug(f"locate_turnstile_box: 定位到 iframe={bool(cframe)} box={bool(box)}")  # type: ignore[reportUnknownArgumentType]
        return box  # type: ignore[reportUnknownVariableType]
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


def turnstile_click(page: ChromiumTab, box: Any) -> bool:
    """点击 Turnstile 复选框（shadow root 内）。

    新版 Turnstile 的可点击元素通常是 ``input[type=checkbox]``
    （aria-label 如“请验证您是真人”），老版本则是 ``div[role=checkbox]``。
    只接受复选框类元素，避免 shadow root 为空时泄漏到页面元素导致误点。
    """
    btn: Any = None
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
            btn = el
            break
    if not btn:
        logger.debug("turnstile_click: 组件内未找到复选框，不点击")
        return False
    try:
        tag = getattr(btn, "tag", "?")
        logger.debug(f"turnstile_click: 点击复选框 tag={tag}")
        # 优先使用元素级 CDP 点击：跨域 iframe 内的元素用 page.actions 计算视口
        # 坐标会点偏（点中页面其它元素导致误跳转），btn.click() 会自动带上 iframe 偏移。
        btn.click()  # type: ignore[union-attr]
    except Exception as e:
        logger.debug(f"turnstile_click: btn.click 失败({e})，回退 actions")
        try:
            page.actions.move_to(btn, duration=0.8)  # type: ignore[union-attr]
            page.actions.click(btn)  # type: ignore[union-attr]
        except Exception as e2:
            logger.debug(f"turnstile_click: actions 点击也失败: {e2}")
            return False
    return True


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


def _solve_turnstile(page: ChromiumTab, tries: int, is_box: bool) -> Tuple[bool, bool]:
    """尝试解决 Turnstile 挑战，失败时刷新页面重试。

    Args:
        page: 浏览器标签页。
        tries: 最大尝试次数。
        is_box: 是否盒子挑战（决定检测函数）。

    Returns:
        (success, was_challenge)
    """
    check = under_box_challenge if is_box else under_challenge
    success = False
    for _ in range(max(1, tries)):
        if not check(page.html):
            success = True
            break

        box = locate_turnstile_box(page)
        if box is None:
            page.wait(2)
            continue

        if not turnstile_click(page, box):
            page.wait(2)
            continue

        # 等待挑战判定结果。点击后 Turnstile 会重渲染盒子（旧 box 元素失效），
        # 需持续重新定位；部分挑战点击后还会出现第二次验证/复选框，需再次点击。
        for _ in range(15):
            try:
                cur_box = locate_turnstile_box(page) or box
            except Exception:
                cur_box = box
            if _turnstile_success(cur_box):
                success = True
                break
            if _turnstile_error(page, cur_box):
                logger.debug("Cloudflare 验证失败，刷新挑战后重试")
                break
            # 页面已脱离挑战态：连续两次确认（避免 Turnstile 重渲染瞬时变化误判），
            # 点击成功后 Cloudflare 会自动跳转到真实页面。
            if not check(page.html):
                page.wait(1)
                if not check(page.html):
                    logger.debug("页面已脱离 Cloudflare 挑战态，判定成功")
                    success = True
                    break
            # 验证过程中可能出现第二次复选框/需重试点击
            # （turnstile_click 内部只在找到复选框时才点击，无复选框时安全返回 False）
            try:
                box2 = locate_turnstile_box(page)
            except Exception:
                box2 = None
            if box2 is not None and turnstile_click(page, box2):
                logger.debug("验证过程中再次点击复选框")
            page.wait(1)

        if success:
            break

        # 验证失败时刷新页面重新发起挑战
        try:
            page.refresh()  # type: ignore[union-attr]
        except Exception as e:
            logger.debug(f"刷新挑战页面失败: {e}")
        page.wait(2)

    return success, True


def sync_cf_retry(page: ChromiumTab, tries: int = 5) -> Tuple[bool, bool]:
    """
    同步重试CloudFlare挑战解决

    Args:
        page: 浏览器页面/标签页
        tries: 重试尝试次数

    Returns:
        Tuple[bool, bool]: (成功, 是否挑战)
    """
    if not under_challenge(page.html):
        return True, False
    return _solve_turnstile(page, tries, is_box=False)


def sync_cf_box_retry(page: ChromiumTab, tries: int = 3) -> Tuple[bool, bool]:
    """
    同步重试CloudFlare盒子挑战解决

    Args:
        page: Browser page/tab
        tries: Number of retry attempts

    Returns:
        Tuple[bool, bool]: (success, was_challenge)
    """
    if not under_box_challenge(page.html):
        return True, False
    return _solve_turnstile(page, tries, is_box=True)
