"""Session 基类 — 属性声明与标签页/指纹底层原语。

属性在此处只做类型声明（赋值在 Session.__init__），供继承链上的
各 mixin 获得完整的 pyright 类型信息。
"""

import time
from threading import Condition, RLock, Semaphore
from typing import Any, Dict, Optional

from DrissionPage import Chromium
from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.config.scripts import CF_WIDGET_FIX_JS
from src.config.settings import DEFAULT_UA, DEFAULT_UA_BRAND, DEFAULT_UA_FULL
from src.core.cookie_store import CookieStore
from src.core.fingerprint import FingerprintManager
from src.fp.ua import derive_platform, resolve_ua_fields


class SessionBase:
    # 域名“已验证”窗口；超过窗口后重新串行探测一次。
    DOMAIN_VERIFY_TTL = 30.0
    # 过盾成功后同域并发上限，避免一次性并发触发站点 5xx/限流。
    DOMAIN_PARALLEL_LIMIT = 2

    """Session 共享状态与底层原语（不直接实例化）。"""

    id: str
    _browser: Chromium
    fingerprint: FingerprintManager
    fp_profile_id: Optional[str]
    _fp_env: Dict[str, str]
    cookie_store: CookieStore
    _user_agent: Optional[str]
    _proxy: Optional[str]
    _proxy_context: Any
    _tabs: Dict[str, ChromiumTab]
    instance_key: Optional[str]
    _active_tab_name: Optional[str]
    _tab_counter: int
    _last_used_at: float
    _lock: Any
    _tab_locks: Dict[str, Any]
    _challenge_locks: Dict[str, Any]
    _challenge_generations: Dict[str, int]
    _challenge_failed: set[str]
    _verified_at: Dict[str, float]
    _probing_domains: set[str]
    _probe_conditions: Dict[str, Any]
    _parallel_gates: Dict[str, Any]
    _parallel_gates: Dict[str, Any]
    _closed: bool

    @property
    def last_used_at(self) -> float:
        return self._last_used_at

    def touch(self) -> None:
        """更新会话最后使用时间。"""
        self._last_used_at = time.monotonic()

    # ---------- 标签页原语 ----------

    def _tab_lock_for(self, tab_name: str) -> Any:
        """返回某个 tab 的独立锁；session 锁只保护注册表读取/创建."""
        with self._lock:
            lock = self._tab_locks.get(tab_name)
            if lock is None:
                lock = RLock()
                self._tab_locks[tab_name] = lock
            return lock

    def _has_clearance(self, domain: str) -> bool:
        """当前 session 是否已有该域名的有效过盾 Cookie；失败域视为无效."""
        with self._lock:
            if domain in self._challenge_failed:
                return False
        return any(str(c.get("name") or "") == "cf_clearance" for c in self.cookie_store.get(domain))

    def _mark_challenge_failed(self, domain: str) -> None:
        with self._lock:
            self._challenge_failed.add(domain)
            self._verified_at.pop(domain, None)

    def _mark_challenge_solved(self, domain: str) -> None:
        with self._lock:
            self._challenge_failed.discard(domain)

    def _parallel_gate(self, domain: str):
        with self._lock:
            gate = self._parallel_gates.get(domain)
            if gate is None:
                gate = Semaphore(self.DOMAIN_PARALLEL_LIMIT)
                self._parallel_gates[domain] = gate
            return gate

    def _probe_condition(self, domain: str):
        with self._lock:
            cond = self._probe_conditions.get(domain)
            if cond is None:
                cond = Condition(self._lock)
                self._probe_conditions[domain] = cond
            return cond

    def _domain_verified(self, domain: str) -> bool:
        with self._lock:
            ts = self._verified_at.get(domain)
            return bool(ts and time.monotonic() - ts <= self.DOMAIN_VERIFY_TTL)

    def _mark_domain_verified(self, domain: str) -> None:
        with self._lock:
            self._verified_at[domain] = time.monotonic()
            self._probing_domains.discard(domain)
            cond = self._probe_conditions.get(domain)
            if cond is not None:
                cond.notify_all()

    def _clear_domain_verified(self, domain: str) -> None:
        with self._lock:
            self._verified_at.pop(domain, None)

    def _clear_clearance_cookies(self, tab: ChromiumTab, domain: str) -> None:
        """挑战失败后清除失效的 cf_clearance/cf_chl_*，让下一次重新过盾."""
        with self._lock:
            self._verified_at.pop(domain, None)
        names = ("cf_clearance", "cf_chl_rc_ni", "cf_chl_prog", "cf_chl_2")
        for name in names:
            self.cookie_store.delete_cookie(domain, name)
            for cookie_domain in (domain, f".{domain}"):
                try:
                    tab.run_cdp(  # type: ignore[union-attr]
                        "Network.deleteCookies",
                        name=name,
                        domain=cookie_domain,
                        path="/",
                    )
                except Exception:
                    continue

    def _challenge_gate(self, domain: str) -> tuple[Any, int]:
        """按 session+domain 串行过盾；返回锁和当前代次."""
        with self._lock:
            lock = self._challenge_locks.get(domain)
            if lock is None:
                lock = RLock()
                self._challenge_locks[domain] = lock
            return lock, self._challenge_generations.get(domain, 0)

    def _bump_challenge_generation(self, domain: str) -> None:
        with self._lock:
            self._challenge_generations[domain] = self._challenge_generations.get(domain, 0) + 1

    def _lookup_tab(self, tab_name: Optional[str] = None) -> tuple[str, ChromiumTab]:
        """在 session 注册表锁内定位 tab，返回名称和句柄，不持有锁."""
        with self._lock:
            if self._closed:
                raise RuntimeError(f"[Session:{self.id}] 会话已关闭")
            name = tab_name or self._active_tab_name
            if not name:
                raise ValueError("没有活跃的标签页，请先调用 navigate")
            tab = self._tabs.get(name)
            if tab is None:
                raise ValueError(f"标签页 '{name}' 未找到")
            return name, tab

    def _create_tab_handle(self, tab_name: Optional[str] = None) -> tuple[str, ChromiumTab]:
        """由 Session 实现：创建并注册空 tab，不执行导航."""
        raise NotImplementedError

    def _load_tab(
        self,
        tab: ChromiumTab,
        url: str,
        *,
        cookie: Optional[str] = None,
        referer: Optional[str] = None,
        timeout: int = 30,
        local_storage: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """由 Session 实现：在调用方持有的 tab 锁内导航并返回快照."""
        raise NotImplementedError

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

    def _active_tab_or_none(self) -> Optional[ChromiumTab]:
        """返回活动标签页；无活动页时返回 None，绝不隐式创建页面。"""
        name = self._active_tab_name
        if not name:
            return None
        tab = self._tabs.get(name)
        if tab is None:
            self._active_tab_name = next(reversed(self._tabs), None)
            return None
        try:
            _ = tab.url
        except Exception:
            # 浏览器进程重启或目标页已崩溃：移除失效句柄，避免后续读取空指针。
            logger.warning(f"[Session:{self.id}] 活动标签页 {name} 已失效，移除句柄")
            self._tabs.pop(name, None)
            self._active_tab_name = next(reversed(self._tabs), None)
            return None
        return tab

    def _get_active_tab(self) -> ChromiumTab:
        tab = self._active_tab_or_none()
        if tab is None:
            raise ValueError("没有活跃的标签页，请先调用 navigate")
        return tab

    def _close_tab_handle(self, name: str, tab: ChromiumTab) -> None:
        """关闭标签页；常规关闭失败时用 CDP 兜底，两者都失败才抛错."""
        try:
            tab.close()
            return
        except Exception:
            logger.warning(f"[Session:{self.id}] 常规关闭标签页 {name} 失败，尝试 CDP 关闭")
        try:
            target_id = getattr(tab, "tab_id", None) or tab._target_id
            browser_any: Any = self._browser
            browser_any._run_cdp("Target.CloseTarget", {"targetId": target_id})
        except Exception as e:
            raise RuntimeError(f"标签页 {name} 关闭失败: {e}") from e

    def close_tab(self, tab_name: str) -> None:
        with self._lock:
            tab = self._tabs.get(tab_name)
            if tab is None:
                raise ValueError(f"标签页 '{tab_name}' 未找到")
        tab_lock = self._tab_lock_for(tab_name)
        with tab_lock:
            with self._lock:
                if self._tabs.get(tab_name) is not tab:
                    raise ValueError(f"标签页 '{tab_name}' 未找到")
            # 成功关闭后才移除句柄；失败时保留，调用方可重试或由 session 清理。
            self._close_tab_handle(tab_name, tab)
            with self._lock:
                if self._tabs.get(tab_name) is tab:
                    self._tabs.pop(tab_name, None)
                    self._tab_locks.pop(tab_name, None)
                    if self._active_tab_name == tab_name:
                        self._active_tab_name = next(reversed(self._tabs), None)

    def close_all_tabs(self) -> None:
        # 不能持有 session 锁等待 tab 锁：导航线程可能持有 tab 锁后需要
        # 更新 active/注册表，会形成 ABBA 死锁。
        with self._lock:
            names = list(self._tabs.keys())
        for name in names:
            try:
                self.close_tab(name)
            except Exception as e:
                logger.warning(f"[Session:{self.id}] 关闭标签页 {name} 失败: {e}")

    # ---------- 指纹 / 网络层一致性原语 ----------

    def _apply_user_agent(self, tab: ChromiumTab) -> None:
        """覆盖会话级 UA，并同步 Emulation platform + 完整 UA-CH metadata。

        仅改 UA 字符串会让 `navigator.platform` 保持实例原值（如 Linux），与
        Mac/Windows UA 自相矛盾，被 Cloudflare Turnstile 判为异常而拒绝渲染。
        但 DrissionPage 的 `tab.set.user_agent(ua, platform=...)` 只发送
        `Emulation.setUserAgentOverride` 的 userAgent/platform 两个字段，会
        **清空** `_apply_ua_metadata` 已写入的 userAgentMetadata，导致
        `navigator.userAgentData.brands=[]`、`userAgentData.platform=''`，
        与自定义 UA 自相矛盾（Cloudflare 直接拒绝 Turnstile）。

        这里改为携带完整 metadata 的 Emulation 覆盖，与 `_apply_ua_metadata`
        的网络层覆盖保持一致，避免互相清空。
        """
        ua = self._user_agent
        if not ua:
            return
        user_agent, metadata, platform = self._build_ua_override()
        try:
            tab.run_cdp(  # type: ignore[union-attr]
                "Emulation.setUserAgentOverride",
                userAgent=user_agent,
                platform=platform,
                userAgentMetadata=metadata,
            )
        except Exception as e:
            raise RuntimeError(f"[Session:{self.id}] Emulation UA 覆盖失败，不能继续使用不自洽的指纹: {e}") from e

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
        """从本会话的指纹 env 解析 UA 值（用于网络层请求头一致性）。

        base 兜底值必须与 base_fp_env/实例启动环境一致（UA/版本常量来自
        settings），否则 CDP metadata 会与 Blink 层 fp_config 读到不同的值，
        出现「JS 说 platformVersion=15.0.0、HTTP 头却是空」的自相矛盾。
        """
        base = {
            "ua": DEFAULT_UA,
            "ua_full": DEFAULT_UA_FULL,
            "ua_brand": DEFAULT_UA_BRAND,
            "platform": "Linux x86_64",
            "uad_platform": "Linux",
            "uad_platform_version": "",
            "uad_arch": "x86_64",
            "uad_model": "",
        }
        env = self._fp_env
        # 会话级任意 UA（user_agent 参数）优先：brand/fullVersion 从该 UA 派生，
        # 避免与画像/兜底元数据不一致（支持声称任意版本的 UA）
        if self._user_agent:
            resolved = resolve_ua_fields(self._user_agent)
            # 平台必须随 UA 覆盖：否则 Cookie 级 UA 是 Mac、platform/Sec-CH-UA-Platform
            # 仍是实例的 Linux，Cloudflare Turnstile 会因身份自相矛盾拒绝渲染组件。
            plat = derive_platform(self._user_agent)
            return {
                "ua": resolved["ua"] or DEFAULT_UA,
                "ua_full": resolved["ua_full"] or DEFAULT_UA_FULL,
                "ua_brand": resolved["ua_brand"] or DEFAULT_UA_BRAND,
                "platform": plat.get("js_platform") or env.get("FP_PLATFORM", base["platform"]),
                "uad_platform": plat.get("uad_platform") or env.get("FP_UAD_PLATFORM", base["uad_platform"]),
                "uad_platform_version": env.get("FP_UAD_PLATFORM_VERSION", base["uad_platform_version"]),
                "uad_arch": env.get("FP_UAD_ARCH", base["uad_arch"]),
                "uad_model": env.get("FP_UAD_MODEL", base["uad_model"]),
            }
        return {
            "ua": env.get("FP_UA", base["ua"]),
            "ua_full": env.get("FP_UA_FULL", base["ua_full"]),
            "ua_brand": env.get("FP_UA_BRAND", base["ua_brand"]),
            "platform": env.get("FP_PLATFORM", base["platform"]),
            "uad_platform": env.get("FP_UAD_PLATFORM", base["uad_platform"]),
            "uad_platform_version": env.get("FP_UAD_PLATFORM_VERSION", base["uad_platform_version"]),
            "uad_arch": env.get("FP_UAD_ARCH", base["uad_arch"]),
            "uad_model": env.get("FP_UAD_MODEL", base["uad_model"]),
        }

    def _build_ua_override(self) -> tuple[str, Dict[str, Any], str]:
        """构造自洽的 UA 覆盖三元组 (userAgent, userAgentMetadata, platform)。

        - userAgent：会话级 UA 优先，否则取画像/兜底 UA；
        - platform：JS `navigator.platform`（如 Win32 / MacIntel / Linux x86_64）；
        - userAgentMetadata：UA-CH（brands/fullVersionList/platform/platformVersion/
          architecture/model）。

        补丁 chrome 的 CDP schema 将 architecture/bitness 等字段设为必填，缺失会
        导致 setUserAgentOverride 被拒（覆盖静默失败、请求头发原生版本）。必须提供
        完整字段；完整 metadata 同时会替换原生 client-hint 策略，抑制原生
        high-entropy 头（sec-ch-ua-full-version/arch 等）泄漏。
        """
        v = self._resolve_ua_values()
        brand = v["ua_brand"]
        full = v["ua_full"]
        grease = "99"
        grease_full = "99.0.0.0"
        # brands/fullVersionList 必须与 fp_config 的 UaBrands 完全一致
        # （品牌名与顺序：Not_A Brand, Google Chrome, Chromium），否则请求头与
        # JS userAgentData 不一致会被严格 Turnstile 判定。
        metadata: Dict[str, Any] = {
            "brands": [
                {"brand": "Not=A?Brand", "version": grease},
                {"brand": "Google Chrome", "version": brand},
                {"brand": "Chromium", "version": brand},
            ],
            "fullVersionList": [
                {"brand": "Not=A?Brand", "version": grease_full},
                {"brand": "Google Chrome", "version": full},
                {"brand": "Chromium", "version": full},
            ],
            "fullVersion": full,
            "platform": v["uad_platform"],
            # platformVersion/architecture/model 必须逐字段取自画像 env，
            # 与 fp_config（FP_UAD_PLATFORM_VERSION/FP_UAD_ARCH/FP_UAD_MODEL）
            # 完全一致；硬编码空值/x86_64 会让 Sec-CH-UA-Platform-Version 等
            # 头缺失或与 JS userAgentData 矛盾（Windows 画像会被 CF 判异常）。
            "platformVersion": v["uad_platform_version"],
            "architecture": v["uad_arch"],
            "model": v["uad_model"],
            "mobile": False,
            "bitness": "64",
        }
        return v["ua"], metadata, v["platform"]

    def _apply_ua_metadata(self, tab: ChromiumTab) -> None:
        """用 CDP 覆盖网络层 UA 请求头（User-Agent + Sec-CH-UA），与 JS 指纹一致。

        fp_config 只 patch Blink 层（JS 可见的 userAgentData），HTTP 请求头仍是
        真实版本（如 153），导致"JS 说 151、请求头说 153"的不一致被 Cloudflare 判自动化。
        此方法按画像动态设置 Network.setUserAgentOverride，使请求头与指纹一致。
        """
        user_agent, metadata, _platform = self._build_ua_override()
        try:
            tab.run_cdp(  # type: ignore[union-attr]
                "Network.setUserAgentOverride",
                userAgent=user_agent,
                userAgentMetadata=metadata,
            )
        except Exception as e:
            raise RuntimeError(f"[Session:{self.id}] 设置网络层 UA 覆盖失败: {e}") from e
