"""Session — 会话核心：初始化、导航过盾、页面交互、代理切换。"""

import time
from threading import RLock
from typing import Any, Dict, Optional, cast
from urllib.parse import urlparse

from DrissionPage import Chromium
from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.challenge.cloudflare import CloudflareResolver
from src.challenge.resolver import ChallengeOrchestrator
from src.config.settings import CHALLENGE_TIMEOUT
from src.core.cookie_store import CookieStore
from src.core.fingerprint import FingerprintManager
from src.core.session.tabs import TabMixin
from src.utils.challenge_utils import under_challenge
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
        requested_user_agent: Optional[str] = None,
        requested_fp_profile_id: Optional[str] = None,
    ):
        self.id = session_id
        self._browser = browser
        self.fingerprint = fingerprint
        self.fp_profile_id = fp_profile_id
        # 请求时声明的身份（供调用方对比实际生效值，感知 UA/画像被校正）
        self._requested_user_agent = requested_user_agent
        self._requested_fp_profile_id = requested_fp_profile_id
        self._fp_env: Dict[str, str] = dict(fp_env) if fp_env else {}
        self.cookie_store = CookieStore()
        self._user_agent = user_agent
        self._proxy = proxy
        self._proxy_context: Any = None
        self._tabs: Dict[str, ChromiumTab] = {}
        # registry 锁只保护 _tabs/_active_tab_name/_tab_locks；每个 tab 另有独立锁。
        self._lock = RLock()
        self._tab_locks: Dict[str, Any] = {}
        self._challenge_locks: Dict[str, Any] = {}
        self._challenge_generations: Dict[str, int] = {}
        self._challenge_failed: set[str] = set()
        self._verified_at: Dict[str, float] = {}
        self._probing_domains: set[str] = set()
        self._probe_conditions: Dict[str, Any] = {}
        self._parallel_gates: Dict[str, Any] = {}
        self._closed = False
        self.instance_key: Optional[str] = None
        self._active_tab_name: Optional[str] = None
        self._tab_counter = 0
        self._last_used_at = time.monotonic()
        logger.info(
            f"[Session:{self.id}] 已创建 "
            f"(fingerprint={fingerprint.profile_name}, fp_profile={fp_profile_id or 'default'})"
        )

    def _create_tab_handle(self, tab_name: Optional[str] = None) -> tuple[str, ChromiumTab]:
        """只创建并注册空标签页；导航在锁外由 _load_tab 完成."""
        with self._lock:
            if self._closed:
                raise RuntimeError(f"[Session:{self.id}] 会话已关闭")
            name = tab_name or self._auto_tab_name()
            if name in self._tabs:
                raise ValueError(f"标签页 '{name}' 已存在")

            tab = self._make_tab()
            try:
                tab.set.load_mode.none()  # type: ignore[union-attr]
                self._apply_init_js(tab)
                self._apply_ua_metadata(tab)  # type: ignore[union-attr]
                self._apply_user_agent(tab)
            except Exception:
                self._close_tab_handle(name, tab)
                raise

            self._tabs[name] = tab
            self._tab_locks.setdefault(name, RLock())
            self._active_tab_name = name
            return name, tab

    def _load_tab(
        self,
        tab: ChromiumTab,
        url: str,
        *,
        cookie: Optional[str] = None,
        referer: Optional[str] = None,
        timeout: int = CHALLENGE_TIMEOUT,
        local_storage: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """在调用方持有的 tab 锁内完成导航/挑战/快照."""
        tab.set.load_mode.none()  # type: ignore[union-attr]
        self._apply_tab_options(tab, url, cookie, referer, local_storage)
        tab.get(url)  # type: ignore[union-attr]
        tab.wait(1)
        return self._complete_navigation(tab, url, timeout)

    def _apply_tab_options(
        self,
        tab: ChromiumTab,
        url: str,
        cookie: Optional[str],
        referer: Optional[str],
        local_storage: Optional[Dict[str, str]],
    ) -> None:
        """应用 Cookie/Referer/LocalStorage；新建页和复用页共用同一套状态."""
        domain = urlparse(url).netloc
        # 会话内 cf_clearance 等 Cookie 不能被 provider 传入的静态 Cookie 覆盖；
        # 同名时显式 Cookie 优先，其余保留 session store 中的值。
        merged: Dict[str, Dict[str, Any]] = {}
        for c in self.cookie_store.get(domain):
            merged[str(c.get("name") or "")] = dict(c)
        if cookie:
            for c in self._parse_cookie_header(cookie):
                name = str(c.get("name") or "")
                # cf_clearance 绑定当前浏览器 UA/IP，provider 里可能还是旧值；
                # 会话内刚过盾的新 Cookie 绝不能被显式 Cookie 覆盖。
                if name in {"cf_clearance", "__cf_bm", "_cfuvid"} or name.startswith("cf_chl"):
                    if name in merged:
                        continue
                merged[name] = dict(c)
        cookies = [c for name, c in merged.items() if name]
        if cookies:
            cookies = self.limit_cookie_header(cookies)
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

    def navigate(
        self,
        url: str,
        tab_name: Optional[str] = None,
        cookie: Optional[str] = None,
        referer: Optional[str] = None,
        timeout: int = CHALLENGE_TIMEOUT,
        local_storage: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        # 没有 cf_clearance 时，导航本身也会触发挑战；必须在建 tab 之前
        # 按 session+domain 串行，否则并发请求会各自开一个“请稍候”标签页。
        domain = urlparse(url).netloc
        cond = self._probe_condition(domain)
        is_probe = False
        with cond:
            while True:
                if self._domain_verified(domain):
                    break
                if domain not in self._probing_domains:
                    self._probing_domains.add(domain)
                    is_probe = True
                    break
                # 有探针正在过盾：等它成功/失败后再决定并行或接力串行。
                # 排队等待探针，不把导航 timeout 消耗在队列等待上。
                cond.wait(timeout=300)
        if not is_probe:
            # clearance 已由探针验证后，从队列取出并发执行；限制同域并发，
            # 避免站点被突发请求打成 500。
            with self._parallel_gate(domain):
                return self._navigate_impl(url, tab_name, cookie, referer, timeout, local_storage)
        try:
            result = self._navigate_impl(url, tab_name, cookie, referer, timeout, local_storage)
            raw_challenge = result.get("challenge") if hasattr(result, "get") else None
            challenge = cast(dict[str, Any], raw_challenge) if isinstance(raw_challenge, dict) else {}
            html_text = str(result.get("html") or "") if hasattr(result, "get") else ""
            probe_ok = bool(challenge.get("solved"))
            # 求解器超时但页面已经脱离挑战时也应放行，不能把后续队列继续串行。
            if not probe_ok and html_text and not under_challenge(html_text):
                probe_ok = True
            with cond:
                if probe_ok:
                    self._mark_domain_verified(domain)
                else:
                    self._verified_at.pop(domain, None)
                    self._probing_domains.discard(domain)
                    cond.notify_all()
            return result
        except Exception:
            with cond:
                self._verified_at.pop(domain, None)
                self._probing_domains.discard(domain)
                cond.notify_all()
            raise

    def _navigate_impl(
        self,
        url: str,
        tab_name: Optional[str] = None,
        cookie: Optional[str] = None,
        referer: Optional[str] = None,
        timeout: int = CHALLENGE_TIMEOUT,
        local_storage: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._closed:
                raise RuntimeError(f"[Session:{self.id}] 会话已关闭")
            self.touch()
            target = self._tabs.get(tab_name) if tab_name else None
            previous = self._active_tab_name
            op_name = ""
            op_tab: Optional[ChromiumTab] = None
            created_name: Optional[str] = None
            replace_name: Optional[str] = None
            reused = False

            if target is not None and str(getattr(target, "url", "")).rstrip("/") == url.rstrip("/"):
                op_name, op_tab = tab_name or "", target  # type: ignore[assignment]
                reused = True
            elif not tab_name and previous and previous in self._tabs:
                current = self._tabs[previous]
                if str(getattr(current, "url", "")).rstrip("/") == url.rstrip("/"):
                    op_name, op_tab = previous, current
                    reused = True

            if op_tab is None:
                if not tab_name and previous and previous in self._tabs:
                    # 无 tab_name：导航当前标签页，不新建 tab。
                    op_name, op_tab = previous, self._tabs[previous]
                else:
                    replace_name = tab_name if target is not None else None
                    op_name, op_tab = self._create_tab_handle(None if replace_name else tab_name)
                    created_name = op_name
            if reused:
                self._active_tab_name = op_name

        tab_lock = self._tab_lock_for(op_name)
        with tab_lock:
            # 获取 tab 锁后复核注册表，避免并发 close 后使用失效句柄。
            with self._lock:
                if self._tabs.get(op_name) is not op_tab and not (replace_name and created_name):
                    raise ValueError(f"标签页 '{op_name}' 已关闭")
            domain = urlparse(url).netloc
            if reused:
                self._sync_page_cookies(op_tab, domain)
                return self._page_result(op_tab, domain, {"solved": True, "reused": True})

            try:
                result = self._load_tab(
                    op_tab,
                    url,
                    cookie=cookie,
                    referer=referer,
                    timeout=timeout,
                    local_storage=local_storage,
                )
            except Exception:
                # 本次新建页失败：只在锁内清理自己，不影响旧页。
                if created_name:
                    with self._lock:
                        self._tabs.pop(created_name, None)
                        self._tab_locks.pop(created_name, None)
                        if self._active_tab_name == created_name:
                            fallback = previous if previous in self._tabs else next(reversed(self._tabs), None)
                            self._active_tab_name = fallback
                    try:
                        self._close_tab_handle(created_name, op_tab)
                    except Exception:
                        logger.warning(f"[Session:{self.id}] 清理异常导航标签页 {created_name} 失败")
                raise

            old_tab: Optional[ChromiumTab] = None
            old_lock: Any = None
            with self._lock:
                if replace_name and created_name and created_name != replace_name:
                    old_tab = self._tabs.pop(replace_name, None)
                    old_lock = self._tab_locks.get(replace_name)
                    self._tabs.pop(created_name, None)
                    new_lock = self._tab_locks.pop(created_name, tab_lock)
                    self._tabs[replace_name] = op_tab
                    self._tab_locks[replace_name] = new_lock
                    self._active_tab_name = replace_name
                elif self._tabs.get(op_name) is op_tab:
                    self._active_tab_name = op_name

            if old_tab is not None:
                # 旧命名页在新页成功后才关闭；关闭失败只记录，不影响本次结果。
                try:
                    with old_lock or self._lock:
                        self._close_tab_handle(replace_name or "", old_tab)
                except Exception:
                    logger.warning(f"[Session:{self.id}] 关闭旧命名页 {replace_name} 失败")
            return result

    def _complete_navigation(self, tab: ChromiumTab, url: str, timeout: int) -> Dict[str, Any]:
        """对已加载的标签页执行挑战求解、错误页判断并构造返回结果."""
        orchestrator = ChallengeOrchestrator(timeout=timeout)
        domain = urlparse(url).netloc
        detected = orchestrator.detect(tab)
        challenge_result: Dict[str, Any]

        if detected is None:
            # 普通页面仍可并行；内嵌 Turnstile 属于页面级组件，不占用域名闸门。
            challenge_result = orchestrator.resolve(tab)
        else:
            # cf_clearance 是 session+domain 级别的 Cookie。多个 tab 同时过盾
            # 会互相覆盖 challenge 状态，所以每个域名只允许一个 tab 求解；
            # 其他 tab 等首个 tab 成功后刷新页面复用 Cookie。
            gate, generation = self._challenge_gate(domain)
            with gate:
                current_generation = self._challenge_gate(domain)[1]
                if current_generation != generation:
                    try:
                        tab.refresh()  # type: ignore[union-attr]
                        tab.wait(1)  # type: ignore[union-attr]
                    except Exception:
                        logger.debug(f"[Session:{self.id}] 等待过盾后刷新标签页失败")
                    if orchestrator.detect(tab) is None:
                        challenge_result = {
                            "detected": True,
                            "type": getattr(detected, "challenge_type", "challenge"),
                            "solved": True,
                            "reused": True,
                            "layers": [],
                        }
                    else:
                        challenge_result = orchestrator.resolve(tab)
                else:
                    challenge_result = orchestrator.resolve(tab)

                if challenge_result.get("solved"):
                    self._bump_challenge_generation(domain)

        if challenge_result.get("solved"):
            self._mark_challenge_solved(domain)
        elif detected is not None and orchestrator.detect(tab) is not None:
            # clearance 可能是旧 UA/IP 留下的失效 Cookie；标记该域需要重新过盾，
            # 并删除失效 Cookie，避免后续 tab 继续被放行到挑战页。
            self._mark_challenge_failed(domain)
            self._clear_clearance_cookies(tab, domain)

        html = self._read_html(tab)
        self._sync_page_cookies(tab, domain)

        page_url = url
        page_title = ""
        try:
            page_url = str(tab.url or url)
            page_title = str(tab.title or "")
        except Exception:
            logger.debug("读取页面 URL/标题失败，使用原始 URL")

        # 浏览器网络错误页和未通过挑战都不是“成功导航”。
        if self._is_browser_error_page(page_url, html):
            raise RuntimeError(f"浏览器导航失败: {page_url or url}")
        # 挑战器超时并不等于页面失败：Cloudflare 常在 solver 内部已经放行，
        # 页面业务内容已加载（标题/HTML 正常）。是否真正失败交给调用方按
        # 页面内容判断，避免把已加载的数据误报为 500。

        return {
            "url": page_url,
            "title": page_title,
            "html": html,
            "cookies": self.cookie_store.as_dict(domain),
            "cookie_header": self.cookie_store.as_header(domain),
            "challenge": challenge_result,
        }

    def _page_result(self, tab: ChromiumTab, domain: str, challenge: Dict[str, Any]) -> Dict[str, Any]:
        """构造页面结果，读取失败时返回空 HTML 而不是抛错。"""
        return {
            "url": getattr(tab, "url", ""),
            "title": getattr(tab, "title", ""),
            "html": self._read_html(tab),
            "cookies": self.cookie_store.as_dict(domain),
            "cookie_header": self.cookie_store.as_header(domain),
            "challenge": challenge,
        }

    def _read_html(self, tab: ChromiumTab) -> str:
        try:
            return str(tab.html)
        except Exception:
            logger.debug(f"[Session:{self.id}] 读取页面 HTML 失败")
            return ""

    @staticmethod
    def _is_browser_error_page(url: str, html: str) -> bool:
        """识别 Chromium 内置错误页（DNS/连接/超时等），不能当业务页面返回。"""
        lowered_url = str(url or "").lower()
        if lowered_url.startswith(("chrome-error://", "edge-error://", "about:neterror")):
            return True
        head = (html or "")[:30000].lower()
        return any(
            marker in head
            for marker in (
                "neterror",
                "--error-code-color",
                "#main-frame-error",
                'id="main-frame-error"',
                "err_connection_refused",
                "err_name_not_resolved",
                "err_timed_out",
                "err_internet_disconnected",
                "err_address_unreachable",
                "err_ssl_protocol_error",
            )
        )

    def get_html(self, tab_name: Optional[str] = None) -> Dict[str, Any]:
        self.touch()
        try:
            name, tab = self._lookup_tab(tab_name)
        except (ValueError, RuntimeError):
            # 读取是只读操作：没有标签页就返回空，绝不隐式创建 about:blank。
            return {"url": "", "html": ""}
        with self._tab_lock_for(name):
            if self._tabs.get(name) is not tab:
                return {"url": "", "html": ""}
            return {"url": str(getattr(tab, "url", "") or ""), "html": self._read_html(tab)}

    # ---------- 页面交互 ----------

    def click(self, selector: str, humanize: bool = True) -> None:
        """点击元素。

        humanize=True 时按人性化轨迹移动后点击（对抗鼠标轨迹检测）；
        否则使用 DrissionPage 原生 click。
        """
        self.touch()
        name, tab = self._lookup_tab()
        with self._tab_lock_for(name):
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
        name, tab = self._lookup_tab()
        with self._tab_lock_for(name):
            human_drag_selector(tab, selector, offset_x, offset_y, duration)

    def input_text(self, selector: str, text: str) -> None:
        self.touch()
        name, tab = self._lookup_tab()
        with self._tab_lock_for(name):
            ele = tab.ele(selector)
            ele.clear()  # type: ignore[union-attr]
            ele.input(text)  # type: ignore[union-attr]

    def execute(self, script: str, tab_name: Optional[str] = None) -> Any:
        self.touch()
        name, tab = self._lookup_tab(tab_name)
        with self._tab_lock_for(name):
            return tab.run_js(script)  # type: ignore[union-attr]

    def solve_turnstile(self, timeout: int = 25) -> Dict[str, Any]:
        """显式触发内嵌 Turnstile 求解（点击复选框/等待 token），供搜索等表单场景调用."""
        self.touch()
        name, tab = self._lookup_tab()
        with self._tab_lock_for(name):
            ok = CloudflareResolver().solve_embedded_widget(tab, timeout=timeout)
            return {"solved": bool(ok)}

    # ---------- 代理 ----------

    def set_proxy(self, proxy: str) -> Dict[str, Any]:
        """运行时切换会话代理。

        DrissionPage 5.0 的 Chromium 代理只能在创建上下文时指定，因此切换代理
        会重建标签页（迁移到带新代理的上下文）。返回迁移结果。
        """
        self.touch()
        with self._lock:
            if proxy == self._proxy and self._proxy_context is not None:
                return {"proxy": proxy, "applied_tabs": 1, "errors": []}
            self._closed = True
            old_active_url = ""
            try:
                if self._active_tab_name:
                    old_active_url = str(self._tabs[self._active_tab_name].url or "")
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 读取旧标签页 URL 失败(可忽略): {e}")
            old_context = self._proxy_context
            self._proxy_context = None

        self.close_all_tabs()
        if old_context is not None:
            try:
                old_context.close()  # type: ignore[union-attr]
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 关闭旧代理上下文失败(可忽略): {e}")

        errors: list[str] = []
        applied = 0
        with self._lock:
            self._proxy = proxy
            self._closed = False
        if proxy:
            try:
                name, new_tab = self._create_tab_handle()
                with self._tab_lock_for(name):
                    if old_active_url:
                        new_tab.get(old_active_url)  # type: ignore[union-attr]
                applied = 1
            except Exception as e:
                errors.append(f"{e}")
        return {"proxy": proxy, "applied_tabs": applied, "errors": errors}

    def get_proxy(self) -> Optional[str]:
        return self._proxy

    # ---------- 生命周期 ----------

    def close(self) -> None:
        with self._lock:
            self._closed = True
            proxy_context = self._proxy_context
            self._proxy_context = None
        self.close_all_tabs()
        if proxy_context is not None:
            try:
                proxy_context.close()  # type: ignore[union-attr]
            except Exception as e:
                logger.debug(f"[Session:{self.id}] 关闭代理上下文失败(可忽略): {e}")
        with self._lock:
            self._active_tab_name = None
            self._tab_locks.clear()
        self.cookie_store.clear()
        logger.info(f"[Session:{self.id}] 已关闭")

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "fingerprint": self.fingerprint.profile_name,
                "fp_profile_id": self.fp_profile_id,
                # 实际生效的 UA（None 表示会话 UA 覆盖已被放弃，使用画像原生 UA）
                "user_agent": self._user_agent,
                "ua_override_applied": bool(self._user_agent),
                # 请求时声明的身份，供调用方对比实际生效值
                "requested_user_agent": self._requested_user_agent,
                "requested_fp_profile_id": self._requested_fp_profile_id,
                "profile_reconciled": bool(
                    self._requested_fp_profile_id and self._requested_fp_profile_id != self.fp_profile_id
                ),
                "tabs": list(self._tabs.keys()),
                "active_tab": self._active_tab_name,
                "cookie_domains": self.cookie_store.list_domains(),
            }
