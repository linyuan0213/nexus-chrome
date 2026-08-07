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

# Turnstile 组件修复 JS：仅包含不影响页面业务流程的安全修复
# （删除 navigator.gpu 强制走 WebGL、修复 NaN 传播、加速 WebGL getParameter），
# 不含 turnstile_hook.js 里的 reload 逻辑（那会干扰签到页内嵌组件的 cfCallback 提交）。
CF_WIDGET_FIX_JS = """
(function() {
    'use strict';
    try {
        Object.defineProperty(navigator, 'gpu', { get: () => undefined, configurable: true });
    } catch(e) {}
    var _origConsole = {};
    ['log','warn','error','debug','info'].forEach(function(m) {
        _origConsole[m] = console[m];
        console[m] = function() {
            var args = Array.prototype.slice.call(arguments);
            for (var i = 0; i < args.length; i++) {
                if (typeof args[i] === 'number' && isNaN(args[i])) {
                    args[i] = 0;
                }
            }
            return _origConsole[m].apply(console, args);
        };
    });
    var _origGetParam = WebGLRenderingContext.prototype.getParameter;
    // 注意：MAX_VIEWPORT_DIMS / ALIASED_POINT_SIZE_RANGE / ALIASED_LINE_WIDTH_RANGE
    // 必须返回数组（真实浏览器为 TypedArray），返回标量会被指纹检测识别为异常。
    var _fastValues = {
        3386: new Int32Array([32768, 32768]),
        33901: new Float32Array([1, 1024]),
        33902: new Float32Array([1, 1]),
        3410: 8192, 3411: 8192, 3412: 8192, 3413: 8192, 34024: 8192,
        3414: 16, 3415: 0, 3416: 16, 3417: 64, 34467: 1, 34921: 256,
    };
    // WebGL2 的 getParameter 是独立方法，必须两个原型都 patch，否则
    // WebGL2 的 UNMASKED 会泄漏 "Google Inc. / Vulkan / Subzero"。
    var _patchWebGLGetParam = function(proto) {
        var orig = proto.getParameter;
        proto.getParameter = function(p) {
            // 注意：UNMASKED_VENDOR/RENDERER(37445/37446) 由 C++ fp_config 按画像注入，
            // 此处不覆盖，否则会与指纹画像冲突。
            if (_fastValues[p] !== undefined) return _fastValues[p];
            return orig.call(this, p);
        };
    };
    _patchWebGLGetParam(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') {
        _patchWebGLGetParam(WebGL2RenderingContext.prototype);
    }
})();
"""
