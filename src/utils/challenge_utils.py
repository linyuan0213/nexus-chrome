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


def _locate_turnstile_box(page: ChromiumTab, timeout: int = 5) -> Any:
    """定位 Turnstile 复选框所在的 shadow root。

    Returns:
        复选框 shadow root，或找不到时返回 None。
    """
    cf_solution = page.ele("tag:input@name=cf-turnstile-response", timeout=timeout)  # type: ignore[union-attr]
    if not cf_solution:
        return None
    try:
        cf_wrapper = cf_solution.parent()  # type: ignore[union-attr]
        cf_iframe = cf_wrapper.shadow_root.ele("tag:iframe", timeout=timeout)  # type: ignore[union-attr]
        if not cf_iframe:
            return None
        return cf_iframe.ele("tag:body").shadow_root  # type: ignore[union-attr]
    except Exception:
        return None


def _turnstile_click(page: ChromiumTab, box: Any) -> bool:
    """以模拟真人鼠标的方式点击 Turnstile 复选框。

    新版 Turnstile 的可点击元素通常是 `div[role=checkbox]`，而非 `input`。
    """
    btn: Any = (
        box.ele("css:div[role=checkbox]", timeout=2)  # type: ignore[union-attr]
        or box.ele('css:[data-role="checkbox"]', timeout=2)  # type: ignore[union-attr]
        or box.ele("tag:input", timeout=2)  # type: ignore[union-attr]
    )
    if not btn:
        return False
    try:
        page.actions.move_to(btn, duration=0.8)
        page.actions.click(btn)
    except Exception:
        btn.click()  # type: ignore[union-attr]
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
        page.wait(3)
        if not check(page.html):
            success = True
            break

        box = _locate_turnstile_box(page)
        if box is None:
            page.wait(2)
            continue

        if not _turnstile_click(page, box):
            page.wait(2)
            continue

        # 等待挑战判定结果
        for _ in range(10):
            if _turnstile_success(box):
                success = True
                break
            if _turnstile_error(page, box):
                logger.debug("Cloudflare 验证失败，刷新挑战后重试")
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
