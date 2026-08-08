# WebGL persona 预设

对齐真实 GPU 的 WebGL 参数/扩展集画像预设（配合 1025-webgl-params-extensions.patch 使用）。

## 使用

```bash
# 直接 POST 到配置中心
curl -X POST http://<host>:9850/api/profiles \
  -H "Content-Type: application/json" \
  -d @examples/fp_profiles/intel_iris_xe_linux.json
```

## 原理

SwiftShader 软渲染的 WebGL 能力值/扩展集与真实 GPU 不同，仅改 vendor/renderer
字符串会被参数级交叉校验识破。预设通过三个字段对齐：

- `webgl_params`：MAX_* 能力值覆盖（友好名，渲染层映射为 GLenum）
- `webgl_viewport_dims`：MAX_VIEWPORT_DIMS 二维覆盖
- `webgl_extensions_remove`：隐藏目标 GPU 不支持的扩展（只减不增——
  缺失扩展无法伪造实现，真实 GPU 有而软渲染没有的除外）

桌面 GPU（Intel/NVIDIA/AMD/Apple）均不支持移动端压缩纹理扩展
（ASTC/ETC/PVRTC 大部分），SwiftShader 却支持——这是最常见的暴露点。
Apple M 例外：保留 ASTC。

## 注意

参数值基于公开 ANGLE 指纹数据整理，属 best-effort。生产使用前建议用真实设备
（BrowserLeaks /webgl "raw keys" 全量参数）校验一次，差异项在画像中覆盖即可。
