// Ultimate patch — 移除 WebGPU + Hook Turnstile postMessage 回调 + 修复 NaN
(function() {
    'use strict';

    // 1. 删除 navigator.gpu — 强制 Turnstile 走 WebGL 路径
    try {
        Object.defineProperty(navigator, 'gpu', { get: () => undefined, configurable: true });
    } catch(e) {}

    // 2. 对 Turnstile 隐藏 console 错误 — 防止 NaN 传播破坏状态机
    var _origConsole = {};
    ['log','warn','error','debug','info'].forEach(function(m) {
        _origConsole[m] = console[m];
        console[m] = function() {
            var args = Array.prototype.slice.call(arguments);
            // 过滤掉包含 NaN 的参数
            for (var i = 0; i < args.length; i++) {
                if (typeof args[i] === 'number' && isNaN(args[i])) {
                    args[i] = 0;
                }
            }
            return _origConsole[m].apply(console, args);
        };
    });

    // 3. Hook postMessage — 捕获 Turnstile 完成信号并重定向
    var _origPostMessage = window.postMessage.bind(window);
    window.addEventListener('message', function(e) {
        if (!e.data || typeof e.data !== 'string') return;
        // Turnstile 完成 token
        if (e.data.length > 50 && (e.data.indexOf('cf-chl-') === 0 || e.data.substring(0, 4) === '0x4A')) {
            window.__cf_token = e.data;
            location.reload();
        }
    });

    // 4. 每 2s 扫描 iframe 获取 Turnstile token
    setInterval(function() {
        var iframes = document.querySelectorAll('iframe');
        for (var i = 0; i < iframes.length; i++) {
            try {
                var doc = iframes[i].contentDocument || iframes[i].contentWindow.document;
                if (!doc) continue;
                var input = doc.querySelector('input[name="cf-turnstile-response"]');
                if (input && input.value) {
                    window.__cf_token = input.value;
                    var opt = window._cf_chl_opt;
                    if (opt && opt.cUPMDTk) {
                        location.replace(opt.cUPMDTk);
                    } else {
                        location.reload();
                    }
                    return;
                }
                // 点击期望交互的区域
                var body = doc.body;
                if (body) body.click();
            } catch(e) {}
        }
        // 检查 cookie
        if (document.cookie.indexOf('cf_clearance') !== -1) {
            location.reload();
        }
    }, 2000);

    // 5. 加速 WebGL getParameter 返回值 — 避免 GPU stall 导致的 NaN
    var _origGetParam = WebGLRenderingContext.prototype.getParameter;
    var _fastValues = {
        3415: 0, 33901: 1024, 33902: 1024, 3386: 8, 3410: 8192,
        3411: 8192, 3412: 8192, 3413: 8192, 3414: 16,
        3416: 16, 3417: 64, 34024: 8192, 34467: 1, 34921: 256,
    };
    WebGLRenderingContext.prototype.getParameter = function(p) {
        if (p === 37445) return 'Intel Inc.';
        if (p === 37446) return 'Intel Iris OpenGL Engine';
        if (_fastValues[p] !== undefined) return _fastValues[p];
        return _origGetParam.call(this, p);
    };

    console.log('[ultimate-patch] injected');
})();
