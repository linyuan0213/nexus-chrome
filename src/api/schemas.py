"""API 请求和响应模型。"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    session_id: str = Field(..., description="会话唯一标识")
    fingerprint_profile: str = Field("stealth", description="指纹配置: default / stealth / paranoid")
    user_agent: Optional[str] = Field(None, description="自定义 User-Agent")
    proxy: Optional[str] = Field(None, description="代理地址，如 http://user:pass@host:port")
    fp_profile_id: Optional[str] = Field(None, description="指纹画像 ID（配置中心，启用 FP_* 环境变量）")


class NavigateRequest(BaseModel):
    url: str = Field(..., description="目标 URL")
    tab_name: Optional[str] = Field(None, description="标签页名称，不指定则自动生成")
    cookie: Optional[str] = Field(None, description="预设 Cookie，格式: key=value; key2=value2")
    local_storage: Optional[Dict[str, str]] = Field(None, description="预设 LocalStorage 键值对")
    referer: Optional[str] = Field(None, description="Referer 头")
    timeout: int = Field(30, description="挑战超时秒数")


class ClickRequest(BaseModel):
    selector: str = Field(..., description="CSS 选择器或 XPath")
    humanize: bool = Field(True, description="人性化轨迹移动后点击（对抗鼠标轨迹检测）")


class DragRequest(BaseModel):
    selector: str = Field(..., description="滑块元素选择器")
    offset_x: int = Field(..., description="水平拖拽距离（像素）")
    offset_y: int = Field(0, description="垂直拖拽距离（像素）")
    duration: float = Field(1.0, description="拖拽时长（秒）")


class InputRequest(BaseModel):
    selector: str = Field(..., description="CSS 选择器或 XPath")
    text: str = Field(..., description="要输入的文本")


class ExecuteRequest(BaseModel):
    script: str = Field(..., description="要执行的 JavaScript 代码")


class HttpFetchRequest(BaseModel):
    url: str = Field(..., description="请求 URL")
    method: str = Field("GET", description="HTTP 方法")
    headers: Optional[Dict[str, str]] = Field(None, description="自定义请求头（会自动合并 Cookie）")
    data: Any = Field(None, description="请求体（字符串或 JSON 对象）")
    timeout: int = Field(30, description="超时秒数")


class RequestOperation(BaseModel):
    """聚合请求：fetch + 可选 navigate 过盾 / browser_fetch 过盾。"""

    url: str = Field(..., description="目标 URL")
    method: str = Field("GET", description="HTTP 方法")
    headers: Optional[Dict[str, str]] = Field(None, description="自定义请求头")
    data: Any = Field(None, description="请求体")
    cookie: Optional[str] = Field(None, description="初始 Cookie")
    navigate_if_challenge: bool = Field(True, description="命中挑战时自动 navigate 过盾")
    browser_fetch_on_challenge: bool = Field(True, description="命中挑战时改用浏览器网络栈 fetch 取原始响应")
    return_html: bool = Field(False, description="True=返回渲染后 HTML，False=返回原始 HTTP 响应")
    timeout: int = Field(30, description="导航/请求超时秒数")


class CookiesQuery(BaseModel):
    domain: Optional[str] = Field(None, description="按域名过滤")


class DownloadRequest(BaseModel):
    url: str = Field(..., description="下载 URL")
    save_path: Optional[str] = Field(None, description="保存路径（默认自动目录）")
    timeout: int = Field(60, description="下载超时秒数")


class ScreenshotRequest(BaseModel):
    tab_name: Optional[str] = Field(None, description="标签页名称，None 用活动标签页")
    full_page: bool = Field(False, description="True=整页截图")


class CreateTabRequest(BaseModel):
    name: Optional[str] = Field(None, description="标签页名称，不指定自动生成")
    url: Optional[str] = Field(None, description="可选：创建后导航到此 URL")


class SwitchTabRequest(BaseModel):
    name: str = Field(..., description="目标标签页名称")


class CloseTabRequest(BaseModel):
    name: str = Field(..., description="标签页名称")


class M3u8Request(BaseModel):
    url: str = Field(..., description="m3u8 播放列表 URL")
    timeout: int = Field(30, description="抓取超时秒数")


class SetProxyRequest(BaseModel):
    proxy: str = Field(..., description="代理地址，如 http://user:pass@host:port")


class ApiResponse(BaseModel):
    code: int = Field(0, description="0=成功, 非0=错误")
    message: str = Field("ok", description="描述信息")
    data: Any = Field(None, description="响应数据")
