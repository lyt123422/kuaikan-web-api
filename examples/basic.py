"""最小示例：热门列表（纯 HTTP）+ 第 1 话图片（浏览器）。

运行前：pip install -e . && playwright install chromium
"""
import asyncio

from kuaikan_api import KuaikanClient


async def main() -> None:
    kc = KuaikanClient()
    try:
        hot = await kc.http.home()
        topics = hot.get("popularity_topics") or []
        print("首页热门：")
        for t in topics[:5]:
            print(f"  [{t['id']}] {t.get('title', '')}")

        topic = await kc.topic(10189)
        comics = topic.get("comics") or []
        free = sum(1 for c in comics if not c.get("locked"))
        print(f"\n《{topic['topicInfo'].get('title')}》共 {len(comics)} 话，"
              f"免费 {free} 话")

        imgs = await kc.free_images(10189, 1)
        print(f"第 1 话共 {len(imgs)} 张图，前 2 张：")
        for u in imgs[:2]:
            print("  ", u)
    finally:
        await kc.close()


if __name__ == "__main__":
    asyncio.run(main())
