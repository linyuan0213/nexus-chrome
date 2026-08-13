"""浏览器注入 JS 脚本常量（与配置值分离）。

从 settings.py 拆出，保持配置层聚焦环境变量与常量，
JS 资产集中于此，便于单独审查与测试。
"""

# 点击坐标随机化 JS：为 click 事件 screenX/screenY 添加小随机偏移，
# 降低点击坐标指纹的精确度。注意：当前运行态仅注入 CF_WIDGET_FIX_JS，
# 此脚本属于预置 profile 的 js_scripts（默认注入路径未启用）。
CLICK_RANDOMIZE_JS = """
function getRandomInt(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}
function modifyClickEvent(event) {
    if (!event._isModified) {
        event._screenX = event.screenX;
        event._screenY = event.screenY;
        Object.defineProperty(event, 'screenX', {
            get: function() {
                return this._screenX + getRandomInt(0, 200);
            }
        });
        Object.defineProperty(event, 'screenY', {
            get: function() {
                return this._screenY + getRandomInt(0, 200);
            }
        });
        event._isModified = true;
    }
}
const originalAddEventListener = EventTarget.prototype.addEventListener;
EventTarget.prototype.addEventListener = function(type, listener, options) {
    if (type === 'click') {
        const wrappedListener = function(event) {
            modifyClickEvent(event);
            listener.call(this, event);
        };
        originalAddEventListener.call(this, type, wrappedListener, options);
    } else {
        originalAddEventListener.call(this, type, listener, options);
    }
};
"""

# Turnstile 组件修复 JS（已清空）。
# 历史版本注入 navigator.gpu=undefined、硬编码 WebGL getParameter、
# 覆盖 console.* ——这些都是真实 Chrome 不具备的可检测行为，会被
# Cloudflare Turnstile/Managed Challenge 判为自动化或修改痕迹。
# 浏览器指纹已由 C++ fp_config 在二进制层处理，JS 注入不再需要。
CF_WIDGET_FIX_JS = ""
