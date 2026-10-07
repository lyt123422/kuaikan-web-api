# kuaikan-web-api

快看漫画 PC Web 端（www.kuaikanmanhua.com）的 API 客户端。逆向研究 + 个人阅读用途。

> ⚠️ 仅支持**免费公开内容**。付费/会员话的服务端付费墙未被也不会被绕过；
> 请勿用于批量爬取或二次分发，内容版权归快看漫画及原作者所有。

## 逆向结论（TL;DR）

| 事项 | 结论 |
|------|------|
| API 域名 | 与页面同域、无前缀（`https://www.kuaikanmanhua.com/v2/pweb/...`）。`api.kuaikanmanhua.com` 是移动端接口，PC 端不用 |
| 列表接口 | `home` / `daily` / `suggest` / `vip_goods` 纯 HTTP 直连，无需任何签名 |
| 单话接口 | `GET /v2/pweb/comic/{id}` 必须带 `answer` 参数，否则 `code 3504` |
| answer 生成 | `gs.min.1.0.0.js` 注册硬编码回调 → JSONP 拉 `/v1/aegis/api/web/challenge` 返回混淆 JS → 真实浏览器执行后产出 `base64(指纹+时间戳)` |
| 校验强度 | 源站校验指纹内容与客户端 TLS 指纹：**curl/requests 无法伪造，必须真实浏览器内同源 fetch** |
| 缓存陷阱 | 热门话的响应有 CDN 缓存，任意非空 answer 也返回 200——别被这个骗了，换个未缓存话立刻 3504 |
| 付费边界 | `locked:true / is_pay_comic / need_vip` 的话接口只回元数据不给图，无绕过空间 |
| 作品话数 | `/v2/pweb/topic/{id}` 仅 SSR 内部可用（WAF 403），公开路径是解析页面 `__NUXT__` 注入数据 |

## 安装

```bash
pip install -e .
playwright install chromium
```

## 用法

```python
import asyncio
from kuaikan_api import KuaikanClient

async def main():
    kc = KuaikanClient()
    try:
        # 无需浏览器的列表接口
        hot = await kc.http.home()
        daily = await kc.http.daily("2026-10-07")
        titles = await kc.http.suggest("少女")

        # 需要浏览器（自动拉起 headless Chromium，会话复用）
        topic = await kc.topic(10189)          # 作品 + 192 话列表（含 locked/is_free）
        imgs = await kc.free_images(10189, 1)  # 第1话的图片直链（CDN 带签名，有时效）
        for u in imgs[:3]:
            print(u)
    finally:
        await kc.close()

asyncio.run(main())
```

示例见 [`examples/basic.py`](examples/basic.py)。

## 接口清单

### 无需浏览器（`KuaikanClient.http.*`）

| 方法 | 端点 | 说明 |
|------|------|------|
| `home()` | `GET /v2/pweb/home` | 首页聚合（热门/轮播） |
| `home_modules()` | `GET /v2/pweb/home/modules` | 首页模块化数据 |
| `daily(date)` | `GET /v2/pweb/daily/topics` | 每日更新 |
| `suggest(q)` | `GET /v1/search/suggestion_topic_author?q=&type=3&f=3` | 搜索联想（只回标题，无 id） |
| `vip_goods()` | `GET /v1/pay/member_good/pc/h5_list` | 会员价目（价格单位：分） |

### 需要浏览器（`KuaikanClient` 直接调用）

| 方法 | 说明 |
|------|------|
| `topic(id)` | 作品详情 + 话数列表（`__NUXT__` 数据源） |
| `comic(id)` | 单话详情：`comic_images[].url / url1280` |
| `chapter_by_number(tid, n)` | 按序号取话 |
| `free_images(tid, n)` | 免费话图片 URL 列表 |

## 已知限制

- PC 站没有带 id 的全量搜索（搜索框只有联想），关键词→作品 id 需要自己接其他数据源
- answer 内嵌毫秒时间戳，可能有时效；库内每次请求重新生成，无感
- 快看付费体系为「VIP 包月（约 ¥20/月）+ 单话快看币解锁」，锁话判断看 `locked` / `is_free` / `need_vip`

## 致谢与背景

社区里关于快看的公开资料停留在 2018 年前后的无签名时代（知乎 Android 逆向系列等）。
本项目的逆向记录（含对照实验与 answer 机制分析）写在仓库之外的分析报告中。

## License

MIT
