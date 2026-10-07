"""快看漫画 Web 端 API 客户端（逆向自 PC 站点，见 README）。

公开未登录可用的能力：
- 列表类接口（首页/日更/联想/会员价目）：纯 HTTP，无需浏览器
- 作品详情 + 话数列表、单话图片：需真实浏览器上下文（answer 反爬）
仅支持免费内容；付费/会员话接口只返回元数据，本库不提供也不会绕过。
"""
from .client import KuaikanClient, KuaikanBrowser  # noqa: F401

__version__ = "0.1.0"
__all__ = ["KuaikanClient", "KuaikanBrowser"]
