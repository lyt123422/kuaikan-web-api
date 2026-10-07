"""浏览器会话：answer 反爬的生成与业务接口的同域调用。

机制（逆向结论，详见 README）：
1. 站点脚本 gs.min.1.0.0.js 暴露 window.gs(url)：JSONP 加载
   /v1/aegis/api/web/challenge?callback=... 返回的混淆 JS 在真实浏览器里执行，
   产出 base64(浏览器指纹+时间戳) 即 answer；指纹内容会被源站校验，
   因此必须真浏览器环境（Playwright Chromium 实测可行）。
2. answer 以 query 参数追加到业务请求；同一 answer 会话内可复用多个话，
   但换 HTTP 客户端（curl/requests）会被拒（TLS/指纹绑定），所以业务请求
   也在页面内用 fetch 发出。

只封装免费内容；locked 话接口仅返回元数据，属服务端付费墙。
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from typing import Any, Callable, Awaitable

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .http_api import KuaikanApiError

log = logging.getLogger("kuaikan_api")

_HOMEPAGE = "https://www.kuaikanmanhua.com/"
_TOPIC_URL = "https://www.kuaikanmanhua.com/web/topic/{tid}/"

_CRASH_HINTS = ("target crashed", "target closed",
                "browser has been closed", "page has been closed")


class KuaikanBrowser:
    """单页面会话。启动一次 Chromium，复用到进程结束。

    >>> kb = KuaikanBrowser()
    >>> await kb.start()
    >>> data = await kb.comic(464863)          # 单话（含 comic_images）
    >>> topic = await kb.topic(10189)          # 作品 + 全部话数
    >>> await kb.close()
    """

    def __init__(self, *, headless: bool = True, timeout_ms: float = 20000):
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> "KuaikanBrowser":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(
            locale="zh-CN",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"),
        )
        self._page = await self._context.new_page()
        await self._page.goto(_HOMEPAGE, wait_until="domcontentloaded",
                              timeout=self._timeout_ms)
        # gs.min.1.0.0.js 只在阅读页等页面加载；首页缺失时手动注入
        await self._page.evaluate(
            """() => new Promise((res, rej) => {
                if (typeof window.gs === 'function') return res(true);
                const s = document.createElement('script');
                s.src = 'https://gamestatic.kkmh.com/kk-static/js/gs.min.1.0.0.js';
                s.onload = () => res(true);
                s.onerror = () => rej(new Error('gs.min.js 加载失败'));
                document.head.appendChild(s);
            })""")
        await self._page.wait_for_function("typeof window.gs === 'function'",
                                           timeout=self._timeout_ms)
        return self

    async def close(self) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._page = self._context = self._browser = self._pw = None

    async def __aenter__(self) -> "KuaikanBrowser":
        return await self.start()

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def _with_crash_retry(self, job: Callable[[], Awaitable[Any]]) -> Any:
        """渲染进程偶发崩溃（Target crashed）时重启会话并重试一次。"""
        try:
            return await job()
        except Exception as e:
            if not any(h in str(e).lower() for h in _CRASH_HINTS):
                raise
            log.warning("浏览器会话崩溃(%s)，重启后重试", e)
            try:
                await self.close()
            except Exception:
                pass
            await self.start()
            return await job()

    # ---- 内部 ----

    async def _answer(self) -> str:
        assert self._page is not None
        answer = await self._page.evaluate(
            "window.gs('/v1/aegis/api/web/challenge?callback=callback_' + Date.now())")
        if not answer or not isinstance(answer, str):
            raise KuaikanApiError("no-answer", "challenge 未返回 answer")
        return answer

    async def _fetch_in_page(self, path_and_query: str) -> dict[str, Any]:
        assert self._page is not None
        async with self._lock:  # 单页面：answer 生成与 fetch 串行
            answer = await self._answer()
            url = (path_and_query
                   + ("&" if "?" in path_and_query else "?")
                   + "answer=" + urllib.parse.quote(answer, safe=""))
            raw = await self._page.evaluate(
                """async (u) => {
                    const r = await fetch(u, {credentials: 'include',
                        headers: {Accept: 'application/json, text/plain, */*'}});
                    return await r.text();
                }""", url)
        j = json.loads(raw)
        if j.get("code") != 200:
            raise KuaikanApiError(j.get("code"), str(j.get("message", "")))
        return j.get("data") or {}

    # ---- 业务接口（均需 answer）----

    async def comic(self, comic_id: int | str) -> dict[str, Any]:
        """单话详情：comic_info(含 comic_images)、上一话/下一话、所属作品。

        locked=True 时 comic_info 不含图片（服务端付费墙，正常现象）。
        """
        async def job() -> dict[str, Any]:
            data = await self._fetch_in_page(
                f"/v2/pweb/comic/{comic_id}?source=&pc_go_app_exp=")
            return data.get("comic_info") or {}
        return await self._with_crash_retry(job)

    async def topic(self, topic_id: int | str) -> dict[str, Any]:
        """作品详情 + 全部话数列表（来自 SSR 注入的 __NUXT__，含 locked/is_free）。"""
        async def job() -> dict[str, Any]:
            assert self._page is not None
            async with self._lock:
                await self._page.goto(_TOPIC_URL.format(tid=topic_id),
                                      wait_until="domcontentloaded",
                                      timeout=self._timeout_ms)
                raw = await self._page.evaluate(
                    "() => { const d = window.__NUXT__ && window.__NUXT__.data;"
                    " return d && d[0] ? JSON.stringify({topicInfo: d[0].topicInfo,"
                    " comics: d[0].comics}) : null; }")
            if not raw:
                raise KuaikanApiError("no-nuxt",
                                      f"topic {topic_id} 页面数据为空（可能已下架）")
            out = json.loads(raw)
            out["topic_id"] = int(topic_id)
            return out
        return await self._with_crash_retry(job)

    async def chapter_by_number(self, topic_id: int | str,
                                number: int) -> dict[str, Any]:
        """按 1 起始序号取第 number 话：先查话数列表再取单话。"""
        topic = await self.topic(topic_id)
        comics = topic.get("comics") or []
        if not (1 <= number <= len(comics)):
            raise KuaikanApiError("bad-number",
                                  f"序号 {number} 超出范围 1-{len(comics)}")
        return await self.comic(comics[number - 1]["id"])
