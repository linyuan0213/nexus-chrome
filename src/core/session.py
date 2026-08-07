"""Session + SessionManager — DrissionPage 4.2 兼容，手动 CookieStore 隔离。"""

import asyncio
import json
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse

from DrissionPage import Chromium
from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.challenge.resolver import ChallengeOrchestrator
from src.config.scripts import CF_WIDGET_FIX_JS
from src.config.settings import (
    CHALLENGE_TIMEOUT,
    DEFAULT_UA,
    DEFAULT_UA_BRAND,
    DEFAULT_UA_FULL,
    MAX_SESSIONS,
    SESSION_TTL,
)
from src.core.cookie_store import CookieStore
from src.core.fingerprint import FingerprintManager
from src.utils.humanize import human_click_selector, human_drag_selector

# ---------- 全局事件总线（供 WebSocket 推送） ----------
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


class Session:
    def __init__(
        self,
        session_id: str,
        browser: Chromium,
        fingerprint: FingerprintManager,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        fp_profile_id: Optional[str] = None,
        fp_env: Optional[Dict[str, str]] = None,
    ):
        self.id = session_id
        self._browser = browser
        self.fingerprint = fingerprint
        self.fp_profile_id = fp_profile_id
        self._fp_env: Dict[str, str] = dict(fp_env) if fp_env else {}
        self.cookie_store = CookieStore()
        self._user_agent = user_agent
        self._proxy = proxy
        self._proxy_context: Any = None
        self._tabs: Dict[str, ChromiumTab] = {}
        self.instance_key: Optional[str] = None
        self._active_tab_name: Optional[str] = None
        self._tab_counter = 0
        self._last_used_at = time.monotonic()
        logger.info(
            f"[Session:{self.id}] 已创建 "
            f"(fingerprint={fingerprint.profile_name}, fp_profile={fp_profile_id or 'default'})"
        )

    @property
    def last_used_at(self) -> float:
        return self._last_used_at

    def touch(self) -> None:
        """更新会话最后使用时间。"""
        self._last_used_at = time.monotonic()

    def _auto_tab_name(self) -> str:
        self._tab_counter += 1
        return f"tab_{self._tab_counter}"

    def _make_tab(self) -> ChromiumTab:
        """创建标签页：配置了代理时使用带代理的浏览器上下文（DrissionPage 5.0
        的 Chromium tab 代理只能在创建上下文时指定）。上下文创建失败时回退无代理。"""
        if self._proxy:
            if self._proxy_context is None:
                try:
                    self._proxy_context = self._browser.new_context(proxy=self._proxy)  # type: ignore[union-attr]
                except Exception as e:
                    logger.warning(f"[Session:{self.id}] 创建代理上下文失败({e})，回退无代理")
                    return self._browser.new_tab()  # type: ignore[union-attr]
            return self._proxy_context.new_tab()  # type: ignore[union-attr]
        return self._browser.new_tab()  # type: ignore[union-attr]

    def _apply_init_js(self, tab: ChromiumTab) -> None:
        """在导航前注入 Turnstile 组件修复，提升挑战通过率。

        JS 指纹伪装已移除（会导致 userAgentData/版本号等不一致，反而触发
        Cloudflare 检测）；浏览器身份由二进制的干净 UA 与真实值保持一致。
        注意：不注入完整 turnstile_hook，其 reload 逻辑会干扰业务页面
        （如签到页）内嵌 Turnstile 的正常 cfCallback 提交流程。
        """
        try:
            tab.add_init_js(CF_WIDGET_FIX_JS)  # type: ignore[union-attr]
        except Exception as e:
            logger.warning(f"[Session:{self.id}] 注入 Turnstile 组件修复 JS 失败: {e}")

    def _resolve_ua_values(self) -> Dict[str, str]:
        """从本会话的指纹 env 解析 UA 值（用于网络层请求头一致性）。"""
        base = {
            "ua": DEFAULT_UA,
            "ua_full": DEFAULT_UA_FULL,
            "ua_brand": DEFAULT_UA_BRAND,
            "platform": "Linux x86_64",
            "uad_platform": "Linux",
        }
        env = self._fp_env
        return {
            "ua": env.get("FP_UA", base["ua"]),
            "ua_full": env.get("FP_UA_FULL", base["ua_full"]),
            "ua_brand": env.get("FP_UA_BRAND", base["ua_brand"]),
            "platform": env.get("FP_PLATFORM", base["platform"]),
            "uad_platform": env.get("FP_UAD_PLATFORM", base["uad_platform"]),
        }

    def _apply_ua_metadata(self, tab: ChromiumTab) -> None:
        """用 CDP 覆盖网络层 UA 请求头（User-Agent + Sec-CH-UA），与 JS 指纹一致。

        fp_config 只 patch Blink 层（JS 可见的 userAgentData），HTTP 请求头仍是
        真实版本（如 153），导致"JS 说 151、请求头说 153"的不一致被 Cloudflare 判自动化。
        此方法按画像动态设置 Network.setUserAgentOverride，使请求头与指纹一致。

        注意：补丁 chrome 的 CDP schema 将 architecture/bitness 等字段设为必填，
        缺失会导致 setUserAgentOverride 被拒（覆盖静默失败、请求头发原生 153）。
        必须提供完整字段；完整 metadata 同时会替换原生 client-hint 策略，
        从而抑制原生 high-entropy 头（sec-ch-ua-full-version/arch 等）泄漏。
        """
        v = self._resolve_ua_values()
        brand = v["ua_brand"]
        full = v["ua_full"]
        try:
            # brands/fullVersionList 必须与 fp_config 的 UaBrands 完全一致
            # （品牌名与顺序：Google Chrome, Chromium, Not_A Brand），
            # 否则请求头与 JS userAgentData 不一致会被严格 Turnstile 判定。
            tab.run_cdp(  # type: ignore[union-attr]
                "Network.setUserAgentOverride",
                userAgent=v["ua"],
                userAgentMetadata={
                    "brands": [
                        {"brand": "Not=A?Brand", "version": "99"},
                        {"brand": "Google Chrome", "version": brand},
                        {"brand": "Chromium", "version": brand},
                    ],
                    "fullVersionList": [
                        {"brand": "Not=A?Brand", "version": "99.0.0.0"},
                        {"brand": "Google Chrome", "version": full},
                        {"brand": "Chromium", "version": full},
                    ],
                    "fullVersion": full,
                    "platform": v["uad_platform"],
                    "platformVersion": "",
                    "architecture": "x86_64",
                    "model": "",
                    "mobile": False,
                    "bitness": "64",
                },
            )
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 设置网络层 UA 覆盖失败: {e}")

    def _create_tab_internal(
        self,
        url: str,
        tab_name: Optional[str] = None,
        cookie: Optional[str] = None,
        referer: Optional[str] = None,
        local_storage: Optional[Dict[str, str]] = None,
    ) -> ChromiumTab:
        name = tab_name or self._auto_tab_name()
        if name in self._tabs:
            raise ValueError(f"标签页 '{name}' 已存在")

        tab = self._make_tab()
        try:
            tab.set.load_mode.none()  # type: ignore[union-attr]
            self._apply_init_js(tab)
            self._apply_ua_metadata(tab)  # type: ignore[union-attr]
            if self._user_agent:
                tab.set.user_agent(self._user_agent)  # type: ignore[union-attr]
            if cookie:
                cookies = self._parse_cookie_header(cookie)
                domain = urlparse(url).netloc
                for c in cookies:
                    c.setdefault("domain", domain)
                    c.setdefault("path", "/")
                tab.set.cookies(cookies)  # type: ignore[union-attr]
            if referer:
                tab.set.headers({"Referer": referer})  # type: ignore[union-attr]
            if local_storage:
                try:
                    for key, value in local_storage.items():
                        escaped_key = key.replace("'", "\\'")
                        escaped_value = value.replace("'", "\\'")
                        tab.run_js(f"localStorage.setItem('{escaped_key}', '{escaped_value}')")  # type: ignore[union-attr]
                except Exception as e:
                    logger.warning(f"[Session:{self.id}] 设置标签页 LocalStorage 失败: {e}")

            tab.get(url)  # type: ignore[union-attr]
            tab.wait(3)
        except Exception:
            # 导航/初始化失败：关闭已创建的标签页，避免孤儿页面残留
            try:
                tab.close()
            except Exception:
                try:
                    target_id = getattr(tab, "tab_id", None) or tab._target_id
                    self._browser._run_cdp("Target.CloseTarget", {"targetId": target_id})  # type: ignore[union-attr]
                except Exception:
                    logger.warning(f"[Session:{self.id}] 清理初始化失败的标签页失败，可能已孤儿")
            raise

        self._tabs[name] = tab
        self._active_tab_name = name
        return tab

    def navigate(
        self,
        url: str,
        tab_name: Optional[str] = None,
        cookie: Optional[str] = None,
        referer: Optional[str] = None,
        timeout: int = CHALLENGE_TIMEOUT,
        local_storage: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.touch()
        if tab_name is None and self._active_tab_name is not None:
            self.close_tab(self._active_tab_name)
        elif tab_name is not None and tab_name in self._tabs:
            self.close_tab(tab_name)
        tab = self._create_tab_internal(url, tab_name, cookie=cookie, referer=referer, local_storage=local_storage)
        orchestrator = ChallengeOrchestrator(timeout=timeout)
        challenge_result = orchestrator.resolve(tab)
        domain = urlparse(url).netloc
        html = ""
        try:
            html = tab.html
            cookies = tab.cookies()
            if cookies:
                self._store_cookies(domain, cookies)
        except Exception:
            try:
                browser_any: Any = self._browser
                result = browser_any._run_cdp("Storage.getCookies")
                self._store_cookies_from_cdp(domain, result.get("cookies", []))
            except Exception:
                logger.debug("CDP 获取 Cookies 失败，跳过")

        page_url = url
        page_title = ""
        try:
            page_url = tab.url
            page_title = tab.title
        except Exception:
            logger.debug("读取页面 URL/标题失败，使用原始 URL")

        return {
            "url": page_url,
            "title": page_title,
            "html": html,
            "cookies": self.cookie_store.as_dict(domain),
            "cookie_header": self.cookie_store.as_header(domain),
            "challenge": challenge_result,
        }

    def _store_cookies(self, domain: str, cookies: List[Dict[str, str]]) -> None:
        for c in cookies:
            self.cookie_store.store(
                domain,
                [
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": c.get("domain", domain),
                        "path": c.get("path", "/"),
                    }
                ],
            )

    def _store_cookies_from_cdp(self, domain: str, cookies: List[Dict[str, str]]) -> None:
        for c in cookies:
            self.cookie_store.store(
                domain,
                [
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": c.get("domain", domain),
                        "path": c.get("path", "/"),
                    }
                ],
            )

    @staticmethod
    def _parse_cookie_header(cookie_str: str) -> List[Dict[str, str]]:
        """把 Cookie 头字符串解析为 DrissionPage 可识别的 cookie 列表。"""
        cookies: List[Dict[str, str]] = []
        if not cookie_str:
            return cookies
        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, value = part.split("=", 1)
            cookies.append({"name": name.strip(), "value": value.strip()})
        return cookies

    def _merge_cookies(
        self,
        domain: str,
        cookie_header: Optional[str],
    ) -> List[Dict[str, str]]:
        """合并 cookie_store 与用户传入的 Cookie。"""
        cookies = self.cookie_store.get(domain)
        for c in cookies:
            c.setdefault("domain", domain)
            c.setdefault("path", "/")
        if cookie_header:
            user_cookies = self._parse_cookie_header(cookie_header)
            existing_names = {c.get("name") for c in cookies}
            for c in user_cookies:
                if c.get("name") not in existing_names:
                    c.setdefault("domain", domain)
                    c.setdefault("path", "/")
                    cookies.append(c)
        return cookies

    def _create_fetch_tab(
        self,
        url: str,
        cookies: Optional[List[Dict[str, str]]] = None,
        referer: Optional[str] = None,
    ) -> ChromiumTab:
        """创建用于 browser_fetch 的标签页，不自动导航。"""
        tab = self._make_tab()
        tab.set.load_mode.none()  # type: ignore[union-attr]

        # init_js = self.fingerprint.get_init_js()
        # if init_js:
        #     tab.add_init_js(init_js)
        self._apply_init_js(tab)

        if self._user_agent:
            tab.set.user_agent(self._user_agent)  # type: ignore[union-attr]
        if cookies:
            tab.set.cookies(cookies)  # type: ignore[union-attr]
        if referer:
            tab.set.headers({"Referer": referer})  # type: ignore[union-attr]

        return tab

    def _browser_fetch_get(
        self,
        url: str,
        cookie: Optional[str],
        headers: Optional[Dict[str, str]],
        timeout: int,
    ) -> Dict[str, Any]:
        """使用浏览器网络栈通过 GET 请求 URL，并获取原始响应体。

        直接复用 navigate 的过盾能力，取回页面 HTML 作为原始响应体。
        """
        nav_result = self.navigate(url, cookie=cookie, timeout=timeout)
        return {
            "url": nav_result.get("url", url),
            "status_code": 200,
            "headers": {},
            "body": nav_result.get("html", ""),
            "challenge": nav_result.get("challenge"),
        }

    def _browser_fetch_js(
        self,
        url: str,
        cookie: Optional[str],
        method: str,
        headers: Optional[Dict[str, str]],
        data: Any,
        timeout: int,
    ) -> Dict[str, Any]:
        """非 GET 请求：先导航到同 origin 过盾，再用浏览器内 fetch 发送请求。"""
        self.touch()
        domain = urlparse(url).netloc
        cookies = self._merge_cookies(domain, cookie)
        tab = self._create_fetch_tab(url, cookies=cookies)
        name = self._auto_tab_name()
        self._tabs[name] = tab
        self._active_tab_name = name

        try:
            tab.get(url)  # type: ignore[union-attr]
            tab.wait(3)

            orchestrator = ChallengeOrchestrator(timeout=timeout)
            challenge_result = orchestrator.resolve(tab)

            headers_json = json.dumps(headers or {})
            body_str = data if isinstance(data, str) else json.dumps(data) if data is not None else ""

            script = f"""
            async () => {{
                try {{
                    const response = await fetch({json.dumps(url)}, {{
                        method: {json.dumps(method)},
                        headers: {headers_json},
                        body: {json.dumps(body_str)},
                        credentials: 'include'
                    }});
                    const text = await response.text();
                    const headers = {{}};
                    response.headers.forEach((value, key) => {{ headers[key] = value; }});
                    return {{
                        status: response.status,
                        headers: headers,
                        body: text,
                        url: response.url
                    }};
                }} catch (e) {{
                    return {{error: e.message}};
                }}
            }}
            """

            try:
                tab_any: Any = tab
                result: Any = tab_any.run_async_js(script, as_expr=False)
            except Exception as e:
                result = {"error": str(e)}

            if not result:
                result = {"error": "JS fetch did not return a result"}

            result = cast(Dict[str, Any], result)
            result_dict = cast(Dict[str, Any], result)

            if "error" in result_dict:
                raise RuntimeError(f"JS fetch failed: {result_dict.get('error')}")

            try:
                cookies = tab.cookies()
                if cookies:
                    self._store_cookies(domain, cookies)
            except Exception:
                try:
                    browser_any: Any = self._browser
                    result_cdp = cast(Dict[str, Any], browser_any._run_cdp("Storage.getCookies"))
                    self._store_cookies_from_cdp(domain, result_cdp.get("cookies", []))
                except Exception:
                    logger.debug("fetch 后 CDP 获取 Cookies 失败，跳过")

            return {
                "url": result_dict.get("url", tab.url),
                "status_code": result_dict.get("status", 200),
                "headers": result_dict.get("headers", {}),
                "body": result_dict.get("body", ""),
                "challenge": challenge_result,
            }
        finally:
            try:
                self.close_tab(name)
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 关闭 fetch 标签页 {name} 失败: {e}")

    def browser_fetch(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Any = None,
        cookie: Optional[str] = None,
        timeout: int = CHALLENGE_TIMEOUT,
    ) -> Dict[str, Any]:
        """使用浏览器网络栈请求 URL，自动过盾并返回原始响应体。"""
        domain = urlparse(url).netloc
        cookie_header = self.cookie_store.as_header(domain)
        if cookie:
            cookie_header = f"{cookie_header}; {cookie}" if cookie_header else cookie

        if method.upper() == "GET":
            return self._browser_fetch_get(url, cookie_header, headers, timeout)

        return self._browser_fetch_js(url, cookie_header, method, headers, data, timeout)

    def get_html(self) -> Dict[str, Any]:
        self.touch()
        tab = self._get_active_tab()
        return {"url": tab.url, "html": tab.html}

    def get_cookies(self, domain: Optional[str] = None) -> Dict[str, Any]:
        self.touch()
        if domain:
            return {domain: self.cookie_store.as_dict(domain)}
        return self.cookie_store.as_full_dict()

    def click(self, selector: str, humanize: bool = True) -> None:
        """点击元素。

        humanize=True 时按人性化轨迹移动后点击（对抗鼠标轨迹检测）；
        否则使用 DrissionPage 原生 click。
        """
        self.touch()
        tab = self._get_active_tab()
        if humanize:
            try:
                human_click_selector(tab, selector)
                return
            except Exception:
                logger.debug(f"[Session:{self.id}] 人性化点击失败，回退原生 click")
        tab.ele(selector).click(by_js=None)  # type: ignore[union-attr]

    def drag(self, selector: str, offset_x: int, offset_y: int = 0, duration: float = 1.0) -> None:
        """人性化拖拽（滑块验证码）：按住元素 → 弧线轨迹移动到目标偏移。

        Args:
            selector: 滑块元素选择器
            offset_x: 水平拖拽距离（像素）
            offset_y: 垂直拖拽距离（像素）
            duration: 拖拽时长（秒）
        """
        self.touch()
        human_drag_selector(self._get_active_tab(), selector, offset_x, offset_y, duration)

    def input_text(self, selector: str, text: str) -> None:
        self.touch()
        ele = self._get_active_tab().ele(selector)
        ele.clear()  # type: ignore[union-attr]
        ele.input(text)  # type: ignore[union-attr]

    def execute(self, script: str) -> Any:
        self.touch()
        return self._get_active_tab().run_js(script)  # type: ignore[union-attr]

    # ---------- P1 媒体场景能力 ----------

    def list_tabs(self) -> Dict[str, Any]:
        """列出会话内所有标签页（名称 + URL）。"""
        result: Dict[str, Any] = {"active": self._active_tab_name, "tabs": []}
        for name, tab in self._tabs.items():
            try:
                url = tab.url  # type: ignore[union-attr]
            except Exception:
                url = ""
            result["tabs"].append({"name": name, "url": url})
        return result

    def create_tab(self, name: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        """新建标签页（可选指定名称与 URL）。"""
        tab = self._make_tab()
        tab.set.load_mode.none()  # type: ignore[union-attr]
        self._apply_init_js(tab)
        self._apply_ua_metadata(tab)  # type: ignore[union-attr]
        if self._user_agent:
            tab.set.user_agent(self._user_agent)  # type: ignore[union-attr]
        tab_name = name or self._auto_tab_name()
        if tab_name in self._tabs:
            tab.close()  # type: ignore[union-attr]
            raise ValueError(f"标签页 '{tab_name}' 已存在")
        self._tabs[tab_name] = tab
        self._active_tab_name = tab_name
        if url:
            tab.get(url)  # type: ignore[union-attr]
        return {"name": tab_name, "url": tab.url if url else ""}

    def switch_tab(self, tab_name: str) -> Dict[str, Any]:
        """切换活动标签页。"""
        if tab_name not in self._tabs:
            raise ValueError(f"标签页 '{tab_name}' 未找到")
        self._active_tab_name = tab_name
        return {"active": tab_name, "url": self._tabs[tab_name].url}  # type: ignore[union-attr]

    def screenshot(self, tab_name: Optional[str] = None, full_page: bool = False) -> Dict[str, Any]:
        """对指定（或活动）标签页截图，返回 base64 PNG。

        Args:
            tab_name: 标签页名称，None 使用活动标签页
            full_page: True=整页截图，False=视口截图

        Returns:
            {"tab": 名称, "full_page": bool, "png_base64": "...", "size": N}
        """
        self.touch()
        if tab_name:
            if tab_name not in self._tabs:
                raise ValueError(f"标签页 '{tab_name}' 未找到")
            tab = self._tabs[tab_name]
        else:
            tab = self._get_active_tab()
        png = tab.get_screenshot(full_page=full_page, as_base64=True)  # type: ignore[union-attr]
        if isinstance(png, str):
            return {
                "tab": tab_name or self._active_tab_name,
                "full_page": full_page,
                "png_base64": png,
                "size": len(png),
            }
        raise RuntimeError("截图失败：get_screenshot 未返回 base64")

    def download(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        save_path: Optional[str] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """使用浏览器网络栈下载文件（自动携带会话 Cookie / UA / 过盾能力）。

        优先使用浏览器原生下载（DrissionPage download 管理器）；失败时回退到
        页面内 fetch 取二进制。返回 base64 与文件信息。

        Returns:
            {"url", "content_type", "base64", "size", "saved_path"(可选), "error"(可选)}
        """
        self.touch()
        domain = urlparse(url).netloc
        cookie_header = self.cookie_store.as_header(domain)
        if headers:
            cookie_header = (
                f"{cookie_header}; {headers.get('Cookie', '')}".strip("; ")
                if cookie_header
                else headers.get("Cookie", "")
            )
        # 先导航到同域过盾（如首次访问被 WAF 拦截），再触发下载
        try:
            if domain and (
                self._active_tab_name is None or urlparse(self._get_active_tab().url).netloc != domain  # type: ignore[union-attr]
            ):
                self._browser_fetch_get(url, cookie_header, None, timeout=min(timeout, 30))
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 下载前导航过盾失败(可忽略): {e}")

        tab = self._get_active_tab()
        # 浏览器原生下载：命中挑战时浏览器会自动过盾并落盘（DrissionPage 下载管理器）
        try:
            tab_any: Any = tab
            mission: Any = tab_any._download_by_browser(url, save_path=save_path, timeout=timeout)
            if mission is not None:
                if not hasattr(mission, "wait"):
                    raise RuntimeError(f"下载任务未创建: {mission!r}")
                mission.wait(timeout)
                path = mission.final_path
                if not path:
                    path = getattr(mission, "path", "") or ""
                if path and os.path.exists(path):
                    return self._encode_download_result(url, path)
                raise RuntimeError(f"下载任务未返回文件路径: {path!r}")
            raise RuntimeError("未创建下载任务")
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 浏览器原生下载失败({e})，回退 JS fetch 二进制")
            return self._download_via_js_fetch(url, timeout)

    def _download_via_js_fetch(self, url: str, timeout: int) -> Dict[str, Any]:
        """回退方案：页面内 fetch 取二进制（跨域受限时可能失败）。"""
        tab = self._get_active_tab()
        script = f"""
        async () => {{
            try {{
                const resp = await fetch({json.dumps(url)}, {{credentials: 'include'}});
                const ct = resp.headers.get('content-type') || '';
                const buf = await resp.arrayBuffer();
                let bin = '';
                const bytes = new Uint8Array(buf);
                for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
                return {{status: resp.status, content_type: ct, size: bytes.length,
                        base64: btoa(bin)}};
            }} catch (e) {{ return {{error: String(e)}}; }}
        }}
        """
        try:
            tab_any: Any = tab
            result: Any = tab_any.run_async_js(script, as_expr=False)
        except Exception as e:
            return {"url": url, "error": str(e)}
        if not result:
            return {"url": url, "error": "JS fetch 失败"}
        if result.get("error"):
            return {"url": url, "error": result.get("error")}
        return {
            "url": url,
            "content_type": result.get("content_type"),
            "base64": result.get("base64"),
            "size": result.get("size"),
        }

    @staticmethod
    def _encode_download_result(url: str, path: str) -> Dict[str, Any]:
        """读取已下载文件，编码为 base64 返回（大文件仅返回路径）。"""
        import os

        size = os.path.getsize(path)
        MAX_INLINE = 8 * 1024 * 1024  # 8MB 内联返回 base64
        result: Dict[str, Any] = {"url": url, "saved_path": path, "size": size}
        if size <= MAX_INLINE:
            with open(path, "rb") as f:
                import base64

                result["base64"] = base64.b64encode(f.read()).decode("ascii")
        return result

    def detect_m3u8(self, url: str, timeout: int = 30) -> Dict[str, Any]:
        """抓取并解析 m3u8 播放列表（支持主列表与媒体列表）。

        Returns:
            {"url", "type": "master"|"media"|"unknown", "streams": [{bandwidth, resolution, url}],
             "segments": [{duration, url}], "raw"(截断)}
        """
        self.touch()
        domain = urlparse(url).netloc
        # 先确保已过盾（同域导航），再用浏览器下载管理器取播放列表（跨域可靠）
        try:
            if self._active_tab_name is None or urlparse(self._get_active_tab().url).netloc != domain:  # type: ignore[union-attr]
                self._browser_fetch_get(url, self.cookie_store.as_header(domain), None, timeout=min(timeout, 20))
        except Exception as e:
            logger.debug(f"[Session:{self.id}] m3u8 过盾导航失败(可忽略): {e}")
        tab = self._get_active_tab()
        try:
            tab_any: Any = tab
            mission: Any = tab_any._download_by_browser(url, save_path="/tmp", timeout=timeout)
            if mission is not None:
                mission.wait(timeout)
                path = mission.final_path or getattr(mission, "path", "")
                if path and os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        body = f.read()
                    if "EXTM3U" in body:
                        return self._parse_m3u8(url, body)
        except Exception as e:
            logger.debug(f"[Session:{self.id}] m3u8 浏览器下载失败({e})")
        return {"url": url, "type": "unknown", "streams": [], "segments": [], "raw": ""}

    @staticmethod
    def _parse_m3u8(base_url: str, body: str) -> Dict[str, Any]:
        """解析 m3u8 文本（主列表含 EXT-X-STREAM-INF；媒体列表含 EXTINF 分片）。"""

        base_dir = base_url.rsplit("/", 1)[0] if "/" in base_url else ""
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        streams: list[Dict[str, Any]] = []
        segments: list[Dict[str, Any]] = []
        cur_stream: Dict[str, Any] = {}
        cur_duration = 0.0

        def resolve(u: str) -> str:
            if u.startswith("http"):
                return u
            return f"{base_dir}/{u.lstrip('/')}" if base_dir else u

        for ln in lines:
            if ln.startswith("#EXT-X-STREAM-INF"):
                attrs: Dict[str, Any] = {}
                for kv in ln.replace("#EXT-X-STREAM-INF:", "").split(","):
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        attrs[k] = v.strip('"')
                cur_stream = {
                    "bandwidth": attrs.get("BANDWIDTH", ""),
                    "resolution": attrs.get("RESOLUTION", ""),
                    "codecs": attrs.get("CODECS", ""),
                    "url": "",
                }
            elif ln.startswith("#EXTINF"):
                try:
                    cur_duration = float(ln.replace("#EXTINF:", "").split(",")[0])
                except ValueError:
                    cur_duration = 0.0
            elif ln.startswith("#"):
                continue
            else:
                if cur_stream:
                    cur_stream["url"] = resolve(ln)
                    streams.append(cur_stream)
                    cur_stream = {}
                else:
                    segments.append({"duration": round(cur_duration, 3), "url": resolve(ln)})
                    cur_duration = 0.0

        ptype = "master" if streams else ("media" if segments else "unknown")
        return {
            "url": base_url,
            "type": ptype,
            "streams": streams[:50],
            "segments": segments[:500] if ptype == "media" else segments[:50],
            "segment_count": len(segments),
        }

    # ---------- P2 会话与网络能力 ----------

    def set_proxy(self, proxy: str) -> Dict[str, Any]:
        """运行时切换会话代理。

        DrissionPage 5.0 的 Chromium 代理只能在创建上下文时指定，因此切换代理
        会重建活动标签页（迁移到带新代理的上下文）。返回迁移结果。
        """
        self.touch()
        if proxy == self._proxy and self._proxy_context is not None:
            return {"proxy": proxy, "applied_tabs": 1, "errors": []}
        old_active_url = ""
        try:
            if self._active_tab_name:
                old_active_url = self._tabs[self._active_tab_name].url  # type: ignore[union-attr]
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 读取旧标签页 URL 失败(可忽略): {e}")

        # 关闭旧代理上下文
        if self._proxy_context is not None:
            try:
                self._proxy_context.close()  # type: ignore[union-attr]
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 关闭旧代理上下文失败(可忽略): {e}")
            self._proxy_context = None

        # 现有标签页清空（旧上下文即将被代理上下文替代）
        for name in list(self._tabs.keys()):
            self._tabs.pop(name)
        self._active_tab_name = None
        self._proxy = proxy

        errors: list[str] = []
        applied = 0
        if proxy:
            try:
                new_tab = self._make_tab()
                name = self._auto_tab_name()
                self._tabs[name] = new_tab
                self._active_tab_name = name
                applied = 1
                if old_active_url:
                    new_tab.get(old_active_url)  # type: ignore[union-attr]
            except Exception as e:
                errors.append(f"{e}")
        return {"proxy": proxy, "applied_tabs": applied, "errors": errors}

    def get_proxy(self) -> Optional[str]:
        return self._proxy

    def close_tab(self, tab_name: str) -> None:
        if tab_name not in self._tabs:
            raise ValueError(f"标签页 '{tab_name}' 未找到")
        tab = self._tabs.pop(tab_name)
        if self._active_tab_name == tab_name:
            self._active_tab_name = next(iter(self._tabs), None)
        try:
            tab.close()
        except Exception:
            logger.warning(f"[Session:{self.id}] 常规关闭标签页 {tab_name} 失败，尝试 CDP 关闭")
            try:
                target_id = getattr(tab, "tab_id", None) or tab._target_id
                browser_any: Any = self._browser
                browser_any._run_cdp("Target.CloseTarget", {"targetId": target_id})
            except Exception:
                logger.warning(f"[Session:{self.id}] CDP 关闭标签页 {tab_name} 也失败，标签页可能已孤儿")

    def close_all_tabs(self) -> None:
        for name in list(self._tabs.keys()):
            self.close_tab(name)

    def _get_active_tab(self) -> ChromiumTab:
        if not self._active_tab_name or self._active_tab_name not in self._tabs:
            raise ValueError("没有活跃的标签页，请先调用 navigate")
        return self._tabs[self._active_tab_name]

    def close(self) -> None:
        self.close_all_tabs()
        if self._proxy_context is not None:
            try:
                self._proxy_context.close()  # type: ignore[union-attr]
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 关闭代理上下文失败(可忽略): {e}")
            self._proxy_context = None
        self.cookie_store.clear()
        logger.info(f"[Session:{self.id}] 已关闭")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint.profile_name,
            "fp_profile_id": self.fp_profile_id,
            "tabs": list(self._tabs.keys()),
            "active_tab": self._active_tab_name,
            "cookie_domains": self.cookie_store.list_domains(),
        }


class SessionManager:
    def __init__(
        self,
        pool: Any,
        max_sessions: int = MAX_SESSIONS,
        session_ttl: int = SESSION_TTL,
        persist_file: Optional[str] = None,
    ):
        self._pool = pool
        self._sessions: Dict[str, Session] = {}
        self._max_sessions = max_sessions
        self._session_ttl = session_ttl
        self._persist_file = persist_file
        self._recovered: Dict[str, Dict[str, Any]] = {}
        self._load_persisted()

    @property
    def pool(self) -> Any:
        """浏览器实例池（供 services 层做实例路由）。"""
        return self._pool

    # ---------- P2-9 会话持久化 ----------

    def _load_persisted(self) -> None:
        """启动时加载持久化的会话注册表（供恢复/列出）。"""
        if not self._persist_file or not os.path.exists(self._persist_file):
            return
        try:
            with open(self._persist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for rec in data.get("sessions", []):
                self._recovered[rec["id"]] = rec
            logger.info(f"[SessionManager] 加载持久化会话注册表: {len(self._recovered)} 条")
        except Exception as e:
            logger.warning(f"[SessionManager] 加载持久化注册表失败: {e}")

    def _save_persisted(self) -> None:
        """将当前会话配置（含 Cookie 域）写入持久化文件。"""
        if not self._persist_file:
            return
        try:
            os.makedirs(os.path.dirname(self._persist_file), exist_ok=True)
            recs: List[Dict[str, Any]] = []
            for rec in self._recovered.values():
                recs.append(rec)
            for s in self._sessions.values():
                recs.append(s.to_dict())
            # 去重（以 id 为准）
            by_id: Dict[str, Dict[str, Any]] = {r["id"]: r for r in recs}
            tmp = f"{self._persist_file}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"sessions": list(by_id.values())}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._persist_file)
        except Exception as e:
            logger.debug(f"[SessionManager] 持久化失败: {e}")

    def recovered_sessions(self) -> List[Dict[str, Any]]:
        """上次进程遗留、尚未重新创建的会话记录。"""
        return list(self._recovered.values())

    def forget_recovered(self, session_id: str) -> None:
        self._recovered.pop(session_id, None)
        self._save_persisted()

    def create(
        self,
        session_id: str,
        fingerprint_profile: Optional[str],
        user_agent: Optional[str],
        proxy: Optional[str],
        browser: Chromium,
        fp_profile_id: Optional[str] = None,
        fp_env: Optional[Dict[str, str]] = None,
        instance_key: Optional[str] = None,
    ) -> Session:
        """创建会话。

        browser 已由服务层绑定到对应指纹实例（core 不感知 fp 层）。
        fp_env 为解析后的指纹环境变量（用于网络层 UA 头一致性）。
        instance_key 为该会话使用的浏览器实例 key（用于释放时回收）。
        """
        if session_id in self._sessions:
            raise ValueError(f"会话 '{session_id}' 已存在")
        if len(self._sessions) >= self._max_sessions:
            oldest_id = min(self._sessions, key=lambda sid: self._sessions[sid].last_used_at)
            logger.warning(f"会话数量达到上限 {self._max_sessions}，移除最旧会话 {oldest_id}")
            self.delete(oldest_id)
        fingerprint = FingerprintManager(fingerprint_profile)
        session = Session(
            session_id=session_id,
            browser=browser,
            fingerprint=fingerprint,
            user_agent=user_agent,
            proxy=proxy,
            fp_profile_id=fp_profile_id,
            fp_env=fp_env,
        )
        session.instance_key = instance_key
        self._sessions[session_id] = session
        self._recovered.pop(session_id, None)
        self._save_persisted()
        publish_event("session_created", {"id": session_id, "fp_profile_id": fp_profile_id})
        return session

    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise ValueError(f"会话 '{session_id}' 未找到")
        session = self._sessions[session_id]
        session.touch()
        return session

    def list_all(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._sessions.values()]

    def delete(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise ValueError(f"会话 '{session_id}' 未找到")
        session = self._sessions.pop(session_id)
        session.close()
        # 释放浏览器实例引用（无其他会话使用时回收实例，释放内存）
        if session.instance_key and self._pool is not None:
            try:
                self._pool.release(session.instance_key)
            except Exception as e:
                logger.debug(f"[SessionManager] 释放实例引用失败: {e}")
        self._save_persisted()
        publish_event("session_deleted", {"id": session_id})

    def delete_all(self) -> None:
        for sid in list(self._sessions.keys()):
            self.delete(sid)

    def delete_expired(self, max_idle_seconds: Optional[int] = None) -> int:
        """清理超过空闲时间的会话，返回清理数量。"""
        threshold = max_idle_seconds if max_idle_seconds is not None else self._session_ttl
        now = time.monotonic()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_used_at > threshold]
        for sid in expired:
            self.delete(sid)
        return len(expired)
