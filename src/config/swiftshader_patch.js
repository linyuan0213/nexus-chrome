// SwiftShader workaround — fake WebGPU adapter + accelerate WebGL ReadPixels
(function() {
    'use strict';

    // 1. 移除 navigator.gpu — Turnstile 不会尝试 WebGPU
    if (navigator.gpu) {
        try {
            delete navigator.gpu;
            Object.defineProperty(navigator, 'gpu', { get: () => undefined });
        } catch(e) {}
    }

    // 2. 缓存 WebGL readPixels 结果 — 避免 GPU stall
    var _rpCache = new Map();
    var origReadPixels = WebGLRenderingContext.prototype.readPixels;
    if (origReadPixels) {
        WebGL2RenderingContext.prototype.readPixels = function(x, y, w, h, fmt, type, pixels) {
            var key = x + ',' + y + ',' + w + ',' + h + ',' + fmt + ',' + type;
            if (_rpCache.has(key)) {
                var cached = _rpCache.get(key);
                if (pixels) {
                    for (var i = 0; i < cached.length; i++) pixels[i] = cached[i];
                }
                return;
            }
            try {
                origReadPixels.call(this, x, y, w, h, fmt, type, pixels);
                if (pixels && pixels.length < 100000) {
                    _rpCache.set(key, new Uint8Array(pixels));
                }
            } catch(e) {}
        };
        WebGLRenderingContext.prototype.readPixels = WebGL2RenderingContext.prototype.readPixels;
    }

    // 3. Canvas toDataURL/getImageData 缓存
    var _canvasCache = new Map();
    var origTDU = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        var key = this.width + 'x' + this.height + '_' + type;
        if (_canvasCache.has(key)) return _canvasCache.get(key);
        var result = origTDU.call(this, type);
        if (result.length < 50000) _canvasCache.set(key, result);
        return result;
    };

    console.log('[sw-patch] SwiftShader workarounds injected');
})();
