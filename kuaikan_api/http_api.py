"""纯 HTTP 列表类接口：无需浏览器、无需 answer。

这些端点在 PC 站与页面同域、无前缀（api.kuaikanmanhua.com 是移动端域名，
PC 端不用）。响应统一为 {"code":200, "data":...}，code!=200 时抛 KuaikanApiError。
"""
from __future__ import annotations

import re
from typing import Any

import httpx

BASE = "https://www.kuaikanmanhua.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Referer": BASE + "/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class KuaikanApiError(RuntimeError):
    """业务码非 200 或响应不可解析。"""

    def __init__(self, code: int | str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"kuaikan api code={code} {message}")


def _check(j: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(j, dict) or "code" not in j:
        raise KuaikanApiError("non-json", "响应不是预期的 JSON 结构")
    if j["code"] != 200:
        raise KuaikanApiError(j["code"], str(j.get("message", "")))
    return j.get("data") or {}


class KuaikanHttp:
    """列表类接口的轻量封装（可长连接复用）。"""

    def __init__(self, *, base: str = BASE, timeout: float = 15.0):
        self._client = httpx.AsyncClient(
            base_url=base, headers=DEFAULT_HEADERS, timeout=timeout,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        r = await self._client.get(path, params={k: v for k, v in params.items() if v})
        r.raise_for_status()
        return _check(r.json())

    # ---- 公开列表接口 ----

    async def home(self) -> dict[str, Any]:
        """PC 首页聚合：popularity_topics(热门)、banner 等。"""
        return await self._get("/v2/pweb/home")

    async def home_modules(self) -> dict[str, Any]:
        """首页模块化数据（编辑推荐位等）。"""
        return await self._get("/v2/pweb/home/modules")

    async def daily(self, date: str | None = None) -> list[dict[str, Any]]:
        """每日更新列表，date 形如 2026-10-07，缺省为今天。"""
        data = await self._get("/v2/pweb/daily/topics", date=date)
        return data.get("topics") or data.get("list") or []

    async def suggest(self, q: str) -> list[str]:
        """搜索联想：只返回标题（PC 站没有带 id 的全量搜索结果页）。"""
        data = await self._get(
            "/v1/search/suggestion_topic_author", q=q, type=3, f=3)
        return [i.get("title", "") for i in (data.get("info") or []) if i.get("title")]

    async def vip_goods(self) -> list[dict[str, Any]]:
        """会员价目（无需登录）：recharge_goods 里 real_price/mark_price 单位为分。"""
        data = await self._get("/v1/pay/member_good/pc/h5_list")
        goods: list[dict[str, Any]] = []
        for grp in data.get("members") or []:
            goods.extend(grp.get("recharge_goods") or [])
        return goods


async def fetch_page_html(client: httpx.AsyncClient, path: str) -> str:
    """抓取站点 HTML（如 /web/topic/{id}），供调用方自行解析。"""
    r = await client.get(path)
    r.raise_for_status()
    return r.text


def extract_nuxt_payload(html: str) -> str | None:
    """取出 `window.__NUXT__=(function(...)(...))` 的 IIFE 文本。"""
    i = html.find("window.__NUXT__=")
    if i < 0:
        return None
    j = html.find("</script>", i)
    return html[i + len("window.__NUXT__="):j] if j > i else None


_IMG_HINT = re.compile(r"cover_image_url", re.I)
