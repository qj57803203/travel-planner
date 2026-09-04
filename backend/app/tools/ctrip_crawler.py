"""携程酒店爬虫 —— 通过 Chrome MCP (chrome-devtools-mcp) 爬取携程酒店列表。

新方案（2026-09-04 重写）：
- 不再模拟输入/点击，直接拼 URL 导航到搜索结果页
- 城市 ID 通过携程 getHotelKeywords API 获取（在页面上下文调 fetch）
- 酒店数据用 JS 直读 DOM 提取（.list-item 选择器），比正则解析 HTML 稳定
- 城市 ID 长期缓存 + 酒店搜索结果一周缓存

设计约束：
- CTRIPE_MCP_URL 未配置 → enabled()=False，调用方跳过；
- 一切失败（超时 / 页面异常 / 结构变化）→ 返回空列表，绝不阻塞主流程；
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from app.config import settings
from app.database import SessionLocal
from app.models import CtripCityCache, CtripHotelCache

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """携程爬虫是否启用（需要配置 CTRIPE_MCP_URL 非空）。"""
    return bool(settings.ctrip_mcp_url)


# ============================================================
# Chrome MCP 连接（简化版，每次搜索新建连接，用完关闭）
# ============================================================

async def _get_chrome() -> "ChromeMCP":
    """创建 Chrome MCP 连接。"""
    from app.tools.mcp_client import ChromeMCP
    return ChromeMCP()


# ============================================================
# 城市 ID 解析（参考 browser_tool.py 的 _city_suggest_js）
# ============================================================

def _city_suggest_js(city: str) -> str:
    """生成 JS 代码：调携程 getHotelKeywords API 获取城市数字 ID。

    在携程页面上下文执行 fetch（CORS 允许 hotels.ctrip.com 源）。
    """
    city_json = json.dumps(city, ensure_ascii=False)
    return (
        "async () => {"
        f" const CITY = {city_json};"
        " const body = {queryInfo: {keyword: CITY, actionType: 'destination'},"
        "   head: {platform: 'PC', cver: '0', bu: 'HBU', group: 'ctrip', locale: 'zh-CN',"
        "          region: 'CN', timezone: '8', currency: 'CNY', isSSR: false, extension: []}};"
        " const res = await fetch('//m.ctrip.com/restapi/soa2/34951/getHotelKeywords',"
        "   {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body)});"
        " const data = await res.json();"
        " const kws = (((data || {}).data || {}).mainKeywordList || {}).keywords || [];"
        " for (const k of kws) {"
        "   const info = ((k || {}).keyword || {}).keywordContentInfo || {};"
        "   if (info.typeName === '城市' && (info.keyword || '').includes(CITY)) {"
        "     return JSON.stringify({id: info.keywordId, name: info.keyword});"
        "   }"
        " }"
        " return JSON.stringify({id: null});"
        "}"
    )


def _load_city_cache(city_name: str) -> int | None:
    """从缓存查城市 ID；未命中返回 None。"""
    try:
        with SessionLocal() as db:
            row = (
                db.query(CtripCityCache)
                .filter(CtripCityCache.city_name == city_name)
                .first()
            )
            if row:
                return row.city_id
    except Exception:
        logger.warning("读取携程城市缓存失败：%s", city_name, exc_info=True)
    return None


def _save_city_cache(city_name: str, city_id: int) -> None:
    """缓存城市 ID（幂等写入）。"""
    try:
        with SessionLocal() as db:
            existing = db.query(CtripCityCache).filter(CtripCityCache.city_name == city_name).first()
            if existing:
                existing.city_id = city_id
            else:
                db.add(CtripCityCache(city_name=city_name, city_id=city_id))
            db.commit()
    except Exception:
        logger.warning("写入携程城市缓存失败：%s", city_name, exc_info=True)


async def _resolve_city_id(chrome, city: str) -> int | None:
    """解析城市名→携程数字 ID。先查缓存，未命中则调 API。"""
    # 1. 查缓存
    cached = _load_city_cache(city)
    if cached is not None:
        logger.info("携程城市 ID 缓存命中：%s → %d", city, cached)
        return cached

    # 2. 打开携程页面（需要在携程页面上下文才能调 fetch）
    page = await chrome.call("navigate_page", {"url": "https://hotels.ctrip.com/hotels/listPage?city=2"})
    # navigate_page 不返回有效内容，只确保页面加载
    await asyncio.sleep(2)

    # 3. 在页面上下文调 getHotelKeywords API
    try:
        raw = await chrome.call("evaluate_script", {"function": _city_suggest_js(city)})
        val = _decode_eval(raw)
        if isinstance(val, dict) and isinstance(val.get("id"), int):
            city_id = val["id"]
            _save_city_cache(city, city_id)
            logger.info("携程城市 ID 解析成功：%s → %d", city, city_id)
            return city_id
        logger.warning("携程城市 ID 解析失败：返回值=%s", raw[:200])
        return None
    except Exception as e:
        logger.warning("携程城市 ID 解析异常：%s", e, exc_info=True)
        return None


# ============================================================
# 酒店列表提取（参考 browser_tool.py 的 CTRIP_CARDS_JS）
# ============================================================

# JS：从携程酒店列表页提取卡片数据
# 选择器 .list-item 为实测所得，站点改版时返回空列表
CTRIP_CARDS_JS = r"""
() => {
  const cards = [...document.querySelectorAll('[class*="list-item"]')]
  const out = []
  for (const c of cards) {
    const lines = (c.innerText || '').split('\n').map(s => s.trim()).filter(Boolean)
    if (lines.length < 2) continue
    const name = lines[0]
    if (!name || name.length < 2 || name.includes('¥')) continue
    const pm = (c.innerText || '').match(/¥\s*([\d,]+)/)
    const img = [...c.querySelectorAll('img')].map(i => i.src || i.getAttribute('data-src') || '')
      .find(u => u && u.startsWith('http')) || ''
    out.push({
      name,
      ad: lines.includes('广告'),
      score: lines.find(s => /^\d\.\d$/.test(s)) || '',
      review: lines.find(s => s.includes('点评')) || '',
      loc: (lines.find(s => s.includes('查看地图')) || '').replace('查看地图', ''),
      price: pm ? pm[1].replace(/,/g, '') : '',
      img,
    })
  }
  return JSON.stringify(out)
}
"""


def _parse_cards(raw_json: str) -> list[dict]:
    """解析 JS 提取的酒店卡片数据，转为标准格式。"""
    val = _decode_eval(raw_json)
    if not isinstance(val, list):
        return []

    hotels = []
    for card in val:
        if not isinstance(card, dict):
            continue
        name = card.get("name", "").strip()
        if not name:
            continue
        # 跳过广告
        if card.get("ad"):
            continue
        # 解析价格（去掉 ¥ 前缀，逗号已由 JS 处理）
        price_str = card.get("price", "")
        try:
            price = float(price_str) if price_str else 0
        except (ValueError, TypeError):
            price = 0
        # 解析评分
        score_str = card.get("score", "")
        try:
            rating = float(score_str) if score_str else 0
        except (ValueError, TypeError):
            rating = 0

        hotels.append({
            "name": name,
            "price": price,
            "rating": rating,
            "location": card.get("loc", "").strip(),
            "image": card.get("img", ""),
            "url": "",  # JS 提取的卡片没有详情链接，留空
        })
    return hotels


async def _extract_hotels_with_retry(chrome, attempts: int = 5) -> list[dict]:
    """轮询等待酒店卡片渲染并提取。拿不到 ≥2 张卡时重试。"""
    for attempt in range(attempts):
        if attempt:
            await asyncio.sleep(2.5)  # 等待异步渲染
        try:
            raw = await chrome.call("evaluate_script", {"function": CTRIP_CARDS_JS})
            hotels = _parse_cards(raw)
            if len(hotels) >= 2:
                return hotels
            logger.info("携程酒店提取：%d 条（第 %d 次尝试），继续等待...", len(hotels), attempt + 1)
        except Exception:
            logger.info("携程酒店提取失败（第 %d 次尝试），继续...", attempt + 1, exc_info=True)
    # 最后一次尝试，有多少返回多少
    try:
        raw = await chrome.call("evaluate_script", {"function": CTRIP_CARDS_JS})
        return _parse_cards(raw)
    except Exception:
        return []


# ============================================================
# 酒店缓存（一周有效）
# ============================================================

def _load_hotel_cache(destination: str, keyword: str) -> list[dict]:
    """加载一周内该目的地+关键词的酒店缓存。"""
    cutoff = datetime.utcnow() - timedelta(days=settings.ctrip_cache_ttl_days)
    try:
        with SessionLocal() as db:
            rows = (
                db.query(CtripHotelCache)
                .filter(
                    CtripHotelCache.destination == destination,
                    CtripHotelCache.keyword == keyword,
                    CtripHotelCache.created_at >= cutoff,
                )
                .order_by(CtripHotelCache.id.desc())
                .limit(10)
                .all()
            )
        return [
            {
                "name": r.hotel_name,
                "price": r.price,
                "rating": r.rating,
                "location": r.location,
                "image": r.image,
                "url": r.url,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("读取携程酒店缓存失败：%s %s", destination, keyword, exc_info=True)
        return []


def _save_hotel_cache(destination: str, keyword: str, hotels: list[dict]) -> None:
    """把爬取到的酒店写入缓存（按 destination+keyword+hotel_name 去重）。"""
    if not hotels:
        return
    try:
        with SessionLocal() as db:
            for h in hotels:
                hotel_name = h.get("name", "")
                if not hotel_name:
                    continue
                if (
                    db.query(CtripHotelCache.id)
                    .filter(
                        CtripHotelCache.destination == destination,
                        CtripHotelCache.keyword == keyword,
                        CtripHotelCache.hotel_name == hotel_name,
                    )
                    .first()
                ):
                    continue
                db.add(
                    CtripHotelCache(
                        destination=destination,
                        keyword=keyword,
                        hotel_name=hotel_name,
                        price=h.get("price", 0),
                        rating=h.get("rating", 0),
                        location=h.get("location", ""),
                        image=h.get("image", ""),
                        url=h.get("url", ""),
                    )
                )
            db.commit()
    except Exception:
        logger.warning("写入携程酒店缓存失败：%s %s", destination, keyword, exc_info=True)


# ============================================================
# 核心搜索流程
# ============================================================

async def _crawl_hotels(destination: str, keyword: str, limit: int) -> list[dict]:
    """实时爬取携程酒店：解析 city_id → 拼 URL 导航 → JS 提取。"""
    from app.tools.mcp_client import ChromeMCP

    async with ChromeMCP() as chrome:
        # 1. 解析城市 ID（先查缓存，未命中调 API）
        city_id = await _resolve_city_id(chrome, destination)
        if not city_id:
            logger.warning("携程城市 ID 解析失败，跳过酒店搜索：%s", destination)
            return []

        # 2. 拼搜索 URL 并导航
        search_url = (
            f"https://hotels.ctrip.com/hotels/listPage"
            f"?city={city_id}"
            f"&cityName={quote(destination)}"
            f"&destName={quote(destination)}"
            f"&searchWord={quote(keyword)}"
        )
        logger.info("携程酒店搜索 URL: %s", search_url)
        await chrome.call("navigate_page", {"url": search_url})
        await asyncio.sleep(3)  # 等待页面加载

        # 3. 等待并提取酒店卡片
        hotels = await _extract_hotels_with_retry(chrome, attempts=5)
        logger.info("携程酒店提取完成：%s %s，共 %d 条", destination, keyword, len(hotels))

        return hotels[:limit]


async def search_hotels(destination: str, keyword: str, limit: int = 5) -> list[dict]:
    """搜索携程酒店 → [{"name", "price", "rating", "image", "url", "location"}]。

    优先使用缓存（一周内有效），缓存未命中再实时爬取。
    """
    if not enabled():
        return []

    logger.info("携程酒店搜索：目的地=%s，关键词=%s", destination, keyword)

    # 1. 先查酒店缓存
    cached = _load_hotel_cache(destination, keyword)
    if cached:
        logger.info("携程酒店缓存命中：%s %s，返回 %d 条", destination, keyword, len(cached))
        return cached[:limit]

    # 2. 缓存未命中，实时爬取
    try:
        hotels = await _crawl_hotels(destination, keyword, limit)
        if hotels:
            _save_hotel_cache(destination, keyword, hotels)
            logger.info("携程酒店爬取成功并缓存：%s %s，共 %d 条", destination, keyword, len(hotels))
        else:
            logger.warning("携程酒店爬取无结果：%s %s", destination, keyword)
        return hotels
    except Exception as e:
        logger.warning("携程酒店搜索失败：%s", e, exc_info=True)
        return []


def search_hotels_sync(destination: str, keyword: str, limit: int = 5) -> list[dict]:
    """同步包装：供 LangGraph 的同步节点在 FastAPI 线程池里直接调用。"""
    if not enabled():
        return []
    try:
        return asyncio.run(search_hotels(destination, keyword, limit))
    except Exception as e:
        logger.warning("携程酒店搜索同步调用失败：%s %s", destination, keyword, exc_info=True)
        return []


# ============================================================
# 工具函数
# ============================================================

def _decode_eval(raw: str):
    """从 evaluate_script 返回文本解出 JSON 值。

    mcp 返回形如：```json\n<payload>\n```，也可能是纯 JSON 字符串。
    """
    body = raw
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        body = fence.group(1).strip()
    try:
        val = json.loads(body)
    except Exception:
        return None
    if isinstance(val, str):  # 双重编码
        try:
            val = json.loads(val)
        except Exception:
            return None
    return val
