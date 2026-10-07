"""组合门面：KuaikanClient = 纯 HTTP 列表 + 浏览器详情/图片。

KuaikanBrowser 从 playwright.async_api 独立导入（见 browser_api），
此处仅做转发导出，保持 `from kuaikan_api import KuaikanClient, KuaikanBrowser` 可用。
"""
from __future__ import annotations

from typing import Any

from .http_api import KuaikanHttp
from .browser_api import KuaikanBrowser  # noqa: F401  (re-export)


class KuaikanClient:
    """高级封装。

    >>> kc = KuaikanClient()
    >>> hot = await kc.http.home()               # 无需浏览器
    >>> topic = await kc.topic(10189)            # 需浏览器
    >>> imgs = await kc.free_images(10189, 1)    # 第1话免费图片 URL
    >>> await kc.close()
    """

    def __init__(self, *, headless: bool = True):
        self.http = KuaikanHttp()
        self._browser: KuaikanBrowser | None = None
        self._headless = headless

    async def _ensure_browser(self) -> KuaikanBrowser:
        # 惰性启动：只用列表接口时不会拉起 Chromium
        if self._browser is None:
            self._browser = await KuaikanBrowser(headless=self._headless).start()
        return self._browser

    async def topic(self, topic_id: int | str) -> dict[str, Any]:
        """作品详情 + 话数列表。comics[*] 含 id/title/locked/is_free。"""
        return await (await self._ensure_browser()).topic(topic_id)

    async def comic(self, comic_id: int | str) -> dict[str, Any]:
        """单话详情（免费话含 comic_images）。"""
        return await (await self._ensure_browser()).comic(comic_id)

    async def chapter_by_number(self, topic_id: int | str,
                                number: int) -> dict[str, Any]:
        """第 number 话（1 起始）。锁定话只有元数据。"""
        return await (await self._ensure_browser()).chapter_by_number(
            topic_id, number)

    async def free_images(self, topic_id: int | str,
                          number: int) -> list[str]:
        """第 number 话的免费图片 URL 列表；锁定话抛 KuaikanApiError。"""
        ci = await self.chapter_by_number(topic_id, number)
        if ci.get("locked"):
            from .http_api import KuaikanApiError
            raise KuaikanApiError(
                ci.get("locked_code") or "locked",
                f"《{ci.get('title')}》为付费/会员内容，无图片返回")
        return [img.get("url1280") or img.get("url")
                for img in ci.get("comic_images") or [] if img.get("url")]

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        await self.http.aclose()
