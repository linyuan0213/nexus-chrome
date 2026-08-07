"""Session — 会话核心：初始化、导航过盾、页面交互、代理切换。"""

import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from DrissionPage import Chromium
from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.challenge.resolver import ChallengeOrchestrator
from src.config.settings import CHALLENGE_TIMEOUT
from src.core.cookie_store import CookieStore
from src.core.fingerprint import FingerprintManager
from src.core.session.tabs import TabMixin
from src.utils.humanize import human_click_selector, human_drag_selector


class Session(TabMixin):
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

    def get_html(self) -> Dict[str, Any]:
        self.touch()
        tab = self._get_active_tab()
        return {"url": tab.url, "html": tab.html}

    # ---------- 页面交互 ----------

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

    # ---------- 代理 ----------

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

    # ---------- 生命周期 ----------

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
