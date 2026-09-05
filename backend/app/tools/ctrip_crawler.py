"""携程酒店爬虫 —— 通过 Chrome MCP (chrome-devtools-mcp) 爬取携程酒店列表。

新方案（2026-09-04 重写）：
- 不再模拟输入/点击，直接拼 URL 导航到搜索结果页
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




async def _resolve_city_id(chrome, city: str) -> int | None:
    """解析城市名→携程数字 ID"""
    # 1. 查缓存
    cached = _load_city_cache(city)
    if cached is not None:
        return cached

    # # 2. 打开携程页面（需要在携程页面上下文才能调 fetch）
    # page = await chrome.call("navigate_page", {"url": "https://hotels.ctrip.com/hotels/listPage?city=2"})
    # # navigate_page 不返回有效内容，只确保页面加载
    # await asyncio.sleep(2)

    # # 3. 在页面上下文调 getHotelKeywords API
    # try:
    #     raw = await chrome.call("evaluate_script", {"function": _city_suggest_js(city)})
    #     val = _decode_eval(raw)
    #     logger.warning("携程城市 ID 解析失败：返回值=%s", raw[:200])
    #     return None
    # except Exception as e:
    #     logger.warning("携程城市 ID 解析异常：%s", e, exc_info=True)
    #     return None


# ============================================================
# 酒店列表提取（参考 browser_tool.py 的 CTRIP_CARDS_JS）
# ============================================================

# JS：调用携程 getAdHotels API 获取酒店列表（含 hotelId）
def _get_hotels_js(city_id: int, keyword: str) -> str:
    """生成 JS 代码：调用 getAdHotels API 获取酒店列表。"""
    return (
        "async () => {"
        f" const cityId = {city_id};"
        f" const keyword = {json.dumps(keyword, ensure_ascii=False)};"
        " const body = {"
        "   head: {platform: 'PC', bu: 'HBU', group: 'ctrip', locale: 'zh-CN', region: 'CN'},"
        "   cityId: cityId,"
        "   keyword: keyword,"
        "   checkIn: new Date().toISOString().split('T')[0],"
        "   checkOut: new Date(Date.now() + 86400000).toISOString().split('T')[0],"
        "   roomQuantity: 1,"
        "   adultQuantity: 1,"
        "   childQuantity: 0,"
        "   childAgeInfos: [],"
        "   pageIndex: 1,"
        "   pageSize: 10,"
        "   sortType: 'Default',"
        "   promotionType: '',"
        "   filterInfo: {},"
        "   sessionId: '',"
        "   traceId: '',"
        " };"
        " const res = await fetch('https://m.ctrip.com/restapi/soa2/34951/getAdHotels',"
        "   {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body)});"
        " const data = await res.json();"
        " return JSON.stringify(data);"
        "}"
    )


# JS：从携程酒店列表页提取卡片数据（备用方案，从 DOM 提取）
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


def _parse_api_response(raw_json: str) -> list[dict]:
    """解析 getAdHotels API 返回的酒店数据。"""
    val = _decode_eval(raw_json)
    if not isinstance(val, dict):
        logger.warning("getAdHotels API 返回格式异常: %s", str(val)[:200])
        return []

    hotels = []
    # 从 responseHotelList 提取酒店
    hotel_list = val.get("responseHotelList", [])
    if not isinstance(hotel_list, list):
        return []

    for item in hotel_list:
        if not isinstance(item, dict):
            continue
        hotel_info = item.get("hotelInfo", {})
        if not isinstance(hotel_info, dict):
            continue

        name = hotel_info.get("hotelName", "").strip()
        if not name:
            continue

        # 跳过广告
        if item.get("adInfo"):
            continue

        # 价格
        price_info = hotel_info.get("priceInfo", {})
        price = price_info.get("price", 0) if isinstance(price_info, dict) else 0

        # 评分
        score = hotel_info.get("score", 0)

        # 位置
        position_info = hotel_info.get("positionInfo", {})
        location = ""
        if isinstance(position_info, dict):
            location = position_info.get("address", "")

        # 图片
        hotel_img = hotel_info.get("hotelImg", "")
        image = hotel_img if hotel_img.startswith("http") else ""

        hotels.append({
            "name": name,
            "price": float(price) if price else 0,
            "rating": float(score) if score else 0,
            "location": location,
            "image": image,
        })

    return hotels


def _parse_cards(raw_json: str) -> list[dict]:
    """解析 JS 提取的酒店卡片数据（备用方案），转为标准格式。"""
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
        # 解析价格
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
        })
    return hotels


async def _extract_hotels_via_api(chrome, city_id: int, keyword: str) -> list[dict]:
    """通过 getAdHotels API 获取酒店列表（含 hotelId）。"""
    try:
        js_code = _get_hotels_js(city_id, keyword)
        raw = await chrome.call("evaluate_script", {"function": js_code})
        hotels = _parse_api_response(raw)
        if hotels:
            logger.info("getAdHotels API 获取成功：%d 条", len(hotels))
            return hotels
        logger.warning("getAdHotels API 返回空结果")
        return []
    except Exception:
        logger.warning("getAdHotels API 调用失败", exc_info=True)
        return []


async def _extract_hotels_with_retry(chrome, attempts: int = 5) -> list[dict]:
    """轮询等待酒店卡片渲染并提取（备用方案）。拿不到 ≥2 张卡时重试。"""
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

def _load_hotel_cache(destination: str, keyword: str) -> tuple[list[dict], str]:
    """加载一周内该目的地+关键词的酒店缓存。

    Returns:
        (hotels, list_page_url) — hotels 为酒店列表，list_page_url 为携程列表页链接
    """
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
        if not rows:
            return [], ""
        # 同一批缓存的 list_page_url 相同，取第一条
        list_page_url = rows[0].url or ""
        hotels = [
            {
                "name": r.hotel_name,
                "price": r.price,
                "rating": r.rating,
                "location": r.location,
                "image": r.image,
            }
            for r in rows
        ]
        return hotels, list_page_url
    except Exception:
        logger.warning("读取携程酒店缓存失败：%s %s", destination, keyword, exc_info=True)
        return [], ""


def _save_hotel_cache(destination: str, keyword: str, hotels: list[dict], list_page_url: str) -> None:
    """把爬取到的酒店写入缓存（按 destination+keyword+hotel_name 去重）。

    Args:
        list_page_url: 携程列表页完整链接，存入每条记录的 url 字段
    """
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
                        url=list_page_url,  # 列表页链接
                    )
                )
            db.commit()
    except Exception:
        logger.warning("写入携程酒店缓存失败：%s %s", destination, keyword, exc_info=True)


# ============================================================
# 核心搜索流程
# ============================================================

async def _crawl_hotels(destination: str, keyword: str, limit: int) -> tuple[list[dict], str]:
    """实时爬取携程酒店：解析 city_id → 调用 API 获取酒店列表。

    Returns:
        (hotels, list_page_url) — hotels 为酒店列表，list_page_url 为携程列表页链接
    """
    from app.tools.mcp_client import ChromeMCP

    async with ChromeMCP() as chrome:
        # 1. 先访问携程首页，建立正常浏览上下文
        await chrome.call("navigate_page", {"url": "https://www.ctrip.com"})
        await asyncio.sleep(2)

        # 2. 解析城市 ID
        city_id = await _resolve_city_id(chrome, destination)
        if not city_id:
            logger.warning("携程城市 ID 解析失败，跳过酒店搜索：%s", destination)
            return [], ""

        # 3. 构建列表页 URL（用于返回给前端"查看更多"按钮）
        search_url = (
            f"https://hotels.ctrip.com/hotels/listPage"
            f"?city={city_id}"
            f"&cityName={quote(destination)}"
            f"&destName={quote(destination)}"
            f"&searchWord={quote(keyword)}"
        )

        # # 4. 优先通过 getAdHotels API 获取酒店列表
        # hotels = await _extract_hotels_via_api(chrome, city_id, keyword)
        # if hotels:
        #     logger.info("携程酒店 API 获取成功：%s %s，共 %d 条", destination, keyword, len(hotels))
        #     return hotels[:limit], search_url

        # # 5. API 失败，回退到 DOM 提取方案
        # logger.info("API 获取失败，回退到 DOM 提取方案")
        logger.info("携程酒店搜索 URL: %s", search_url)
        await chrome.call("navigate_page", {"url": search_url})
        await asyncio.sleep(3)

        hotels = await _extract_hotels_with_retry(chrome, attempts=5)
        logger.info("携程酒店提取完成：%s %s，共 %d 条", destination, keyword, len(hotels))

        return hotels[:limit], search_url


async def search_hotels(destination: str, keyword: str, limit: int = 5) -> tuple[list[dict], str]:
    """搜索携程酒店 → (hotels, list_page_url)。

    优先使用缓存（一周内有效），缓存未命中再实时爬取。
    返回:
        (hotels, list_page_url) — hotels 为酒店列表，list_page_url 为携程列表页链接
    """
    if not enabled():
        return [], ""

    logger.info("携程酒店搜索：目的地=%s，关键词=%s", destination, keyword)

    # 1. 先查酒店缓存
    cached, list_page_url = _load_hotel_cache(destination, keyword)
    if cached:
        logger.info("携程酒店缓存命中：%s %s，返回 %d 条", destination, keyword, len(cached))
        return cached[:limit], list_page_url

    # 2. 缓存未命中，实时爬取
    try:
        hotels, list_page_url = await _crawl_hotels(destination, keyword, limit)
        if hotels:
            _save_hotel_cache(destination, keyword, hotels, list_page_url)
            logger.info("携程酒店爬取成功并缓存：%s %s，共 %d 条", destination, keyword, len(hotels))
        else:
            logger.warning("携程酒店爬取无结果：%s %s", destination, keyword)
        return hotels, list_page_url
    except Exception as e:
        logger.warning("携程酒店搜索失败：%s", e, exc_info=True)
        return [], ""


def search_hotels_sync(destination: str, keyword: str, limit: int = 5) -> tuple[list[dict], str]:
    """同步包装：供 LangGraph 的同步节点在 FastAPI 线程池里直接调用。

    返回:
        (hotels, list_page_url) — hotels 为酒店列表，list_page_url 为携程列表页链接
    """
    if not enabled():
        return [], ""
    try:
        return asyncio.run(search_hotels(destination, keyword, limit))
    except Exception as e:
        logger.warning("携程酒店搜索同步调用失败：%s %s", destination, keyword, exc_info=True)
        return [], ""


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
