"""Session 基类 — 属性声明与标签页/指纹底层原语。

属性在此处只做类型声明（赋值在 Session.__init__），供继承链上的
各 mixin 获得完整的 pyright 类型信息。
"""

import time
from typing import Any, Dict, Optional

from DrissionPage import Chromium
from DrissionPage._pages.chromium_tab import ChromiumTab
from loguru import logger

from src.config.scripts import CF_WIDGET_FIX_JS
from src.config.settings import DEFAULT_UA, DEFAULT_UA_BRAND, DEFAULT_UA_FULL
from src.core.cookie_store import CookieStore
from src.core.fingerprint import FingerprintManager


class SessionBase:
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

    @property
    def last_used_at(self) -> float:
        return self._last_used_at

    def touch(self) -> None:
        """更新会话最后使用时间。"""
        self._last_used_at = time.monotonic()

    # ---------- 标签页原语 ----------

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

    def _get_active_tab(self) -> ChromiumTab:
        if self._active_tab_name and self._active_tab_name in self._tabs:
            return self._tabs[self._active_tab_name]
        # 无活跃标签页时自动创建一个（about:blank）：截图/交互等操作无需先 navigate。
        # 典型场景：新建会话后直接用 VNC 导航，或直接点截图。
        try:
            return self._create_tab_internal("about:blank")  # type: ignore[attr-defined, reportUnknownMemberType, reportUnknownVariableType]
        except Exception as e:
            logger.warning(f"[Session:{self.id}] 自动创建标签页失败: {e}")
            raise ValueError("没有活跃的标签页，请先调用 navigate") from e

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

    # ---------- 指纹 / 网络层一致性原语 ----------

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
        grease = "99"
        grease_full = "99.0.0.0"
        try:
            # brands/fullVersionList 必须与 fp_config 的 UaBrands 完全一致
            # （品牌名与顺序：Google Chrome, Chromium, Not_A Brand），
            # 否则请求头与 JS userAgentData 不一致会被严格 Turnstile 判定。
            tab.run_cdp(  # type: ignore[union-attr]
                "Network.setUserAgentOverride",
                userAgent=v["ua"],
                userAgentMetadata={
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
                },
            )
        except Exception as e:
            logger.debug(f"[Session:{self.id}] 设置网络层 UA 覆盖失败: {e}")
