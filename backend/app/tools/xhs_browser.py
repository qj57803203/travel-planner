"""小红书浏览器爬虫 — 直接用 Playwright 浏览小红书网页提取攻略内容。

替代 xhs_mcp.py（MCP 协议 + 独立浏览器容器），去掉中间层：
- 通过 chrome_manager 直连 Docker 内常驻 Chrome
- 直接浏览搜索结果页 + 笔记详情页，提取文本内容
- 不需要 API 签名（x-s 等），不需要 MCP 容器

Cookie 管理：
- 优先从 MCP 容器的 cookies.json 加载（./xhs/data/cookies.json）
- 也可以通过环境变量 XHS_COOKIE 传入
- 没有 cookie 时功能受限（搜索结果可能为空），但不报错

设计约束：
- Chrome 不可用 → enabled()=False，调用方跳过走预置数据兜底
- 一切失败 → 返回空列表并带出原因，绝不阻塞主流程
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# MCP 容器的 cookies 文件路径（Docker volume 挂载到 /app/xhs_data）
_COOKIES_PATHS = [
    "/app/xhs_data/cookies.json",       # Docker 内路径
    "./xhs/data/cookies.json",           # 本地开发路径
    "../xhs/data/cookies.json",          # 相对 backend 目录
]


def enabled() -> bool:
    """Chrome 可用即启用（通过 chrome_debug_url 检测）。

    注意：小红书需要登录才能搜索，没有 cookie 时搜索会返回空结果。
    用户可通过 /xhs-login.html 页面配置 cookie。
    """
    if not settings.chrome_debug_url:
        return False
    # 检查 cookie 是否配置（仅用于日志提示，不阻止启用）
    cookies = _load_cookies()
    if not cookies:
        logger.warning("小红书浏览器爬虫已启用但未配置 Cookie，搜索可能返回空结果。请访问 /xhs-login.html 配置")
    return True


def _load_cookies() -> list[dict]:
    """从文件或环境变量加载 cookies。"""
    # 1. 环境变量优先
    cookie_str = os.environ.get("XHS_COOKIE", "")
    if cookie_str:
        # 环境变量格式：name1=value1; name2=value2
        cookies = []
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                })
        if cookies:
            return cookies

    # 2. 从文件加载
    for path in _COOKIES_PATHS:
        try:
            p = Path(path)
            if p.exists():
                raw_text = p.read_text(encoding="utf-8").strip()
                if not raw_text:
                    logger.warning("Cookie 文件为空：%s", path)
                    continue
                data = json.loads(raw_text)
                if isinstance(data, list):
                    logger.info("从 %s 加载 %d 个 cookie", path, len(data))
                    return data
                if isinstance(data, dict) and "cookies" in data:
                    logger.info("从 %s 加载 %d 个 cookie", path, len(data["cookies"]))
                    return data["cookies"]
                logger.warning("Cookie 文件格式不符合预期：%s（type=%s）", path, type(data).__name__)
        except json.JSONDecodeError:
            logger.warning("Cookie 文件 JSON 解析失败：%s", path)
        except Exception as e:
            logger.warning("读取 Cookie 文件失败：%s — %s", path, e)

    logger.warning("未找到任何有效的 Cookie 文件（已检查路径：%s）",
                    ", ".join(_COOKIES_PATHS))
    return []


def note_url(note_id: str) -> str:
    """构造小红书笔记链接。"""
    return f"https://www.xiaohongshu.com/explore/{note_id}"


# 登录等待超时时间（秒）
_LOGIN_WAIT_TIMEOUT = 180  # 3 分钟
_LOGIN_POLL_INTERVAL = 3   # 每 3 秒轮询一次


async def _wait_for_xhs_login(page, search_url: str) -> bool:
    """等待用户完成小红书登录（截图直播 + 手机扫码）。

    Args:
        page: CDP Page 实例
        search_url: 登录成功后要重新访问的搜索页 URL

    Returns:
        True 登录成功，False 超时
    """
    # 导入全局变量
    from app.routers.trips import _xhs_login_screenshot, _xhs_login_waiting
    import app.routers.trips as trips_module

    # 设置等待状态
    trips_module._xhs_login_waiting = True
    trips_module._xhs_login_screenshot = ""

    try:
        # 先截一帧，避免前端第一次拉图 404
        screenshot_data = await page.screenshot(quality=60)
        trips_module._xhs_login_screenshot = screenshot_data

        waited = 0.0
        while waited < _LOGIN_WAIT_TIMEOUT:
            await asyncio.sleep(_LOGIN_POLL_INTERVAL)
            waited += _LOGIN_POLL_INTERVAL

            # 刷新截图
            try:
                screenshot_data = await page.screenshot(quality=60)
                trips_module._xhs_login_screenshot = screenshot_data
            except Exception:
                logger.warning("小红书登录截图失败", exc_info=True)

            # 检测页面是否已登录（搜索结果出现）
            try:
                feed_items = await page.query_selector_all('[class*="note-item"], [class*="feed-item"], section[class*="note"]')
                if not feed_items:
                    feed_items = await page.query_selector_all('a[href*="/explore/"]')
                if feed_items:
                    logger.info("小红书登录成功，检测到 %d 个搜索结果", len(feed_items))
                    return True
            except Exception:
                logger.warning("小红书登录检测失败", exc_info=True)

        logger.warning("小红书登录等待超时（%.0f 秒）", _LOGIN_WAIT_TIMEOUT)
        return False
    finally:
        # 清除等待状态
        trips_module._xhs_login_waiting = False
        trips_module._xhs_login_screenshot = ""


# ============================================================
# 核心爬取逻辑
# ============================================================

async def _search_and_extract(query: str, limit: int) -> tuple[list[dict], str]:
    """用 CDP 浏览小红书搜索页 + 详情页，提取攻略内容。"""
    from app.tools.chrome_manager import get_chrome_page

    notes: list[dict] = []
    error = ""

    try:
        async with get_chrome_page(timeout_s=90) as page:
            # 1. 加载 cookies（通过 CDP Network.setCookie）
            cookies = _load_cookies()
            if cookies:
                try:
                    await page._send("Network.enable")
                    for c in cookies:
                        await page._send("Network.setCookie", {
                            "name": c.get("name", ""),
                            "value": c.get("value", ""),
                            "domain": c.get("domain", ".xiaohongshu.com"),
                            "path": c.get("path", "/"),
                        })
                    logger.info("已加载 %d 个小红书 cookie", len(cookies))
                except Exception as e:
                    logger.warning("加载 cookies 失败：%s", e)

            # 2. 访问小红书搜索页
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={query}&source=web_search_result_notes"
            logger.info("访问小红书搜索页：%s", search_url)
            await page.goto(search_url, wait_until="load", timeout=30000)
            await asyncio.sleep(3)  # 等待动态内容渲染

            # 3. 提取搜索结果
            # 小红书搜索结果的常见选择器（可能需要根据实际情况调整）
            feed_items = await page.query_selector_all('[class*="note-item"], [class*="feed-item"], section[class*="note"]')

            if not feed_items:
                # 备用选择器：尝试更通用的方案
                feed_items = await page.query_selector_all('a[href*="/explore/"]')
                logger.info("使用备用选择器，找到 %d 个链接", len(feed_items))

            if not feed_items:
                # 再尝试：检查页面状态
                page_text = await page.inner_text("body")
                if "登录" in page_text[:200] or "login" in page_text[:200].lower():
                    # 检测到登录墙，进入等待模式
                    logger.warning("小红书需要登录，进入等待模式：%s", search_url)
                    login_result = await _wait_for_xhs_login(page, search_url)
                    if login_result:
                        # 登录成功，重新提取搜索结果
                        feed_items = await page.query_selector_all('[class*="note-item"], [class*="feed-item"], section[class*="note"]')
                        if not feed_items:
                            feed_items = await page.query_selector_all('a[href*="/explore/"]')
                            logger.info("登录后使用备用选择器，找到 %d 个链接", len(feed_items))
                    else:
                        error = "需要登录小红书（请扫码登录）"
                        logger.warning("小红书登录等待超时：%s", search_url)
                        return [], error
                else:
                    error = f"搜索结果为空（页面无匹配元素）"
                    logger.warning("小红书搜索结果为空：%s", search_url[:100])
                    return [], error

            logger.info("找到 %d 个搜索结果", len(feed_items))

            # 4. 提取笔记基本信息
            seen_ids = set()
            raw_items = []

            for item in feed_items[:limit + 5]:  # 多取一些，后面可能有重复/广告
                try:
                    # 提取链接
                    href = await item.get_attribute("href") or ""
                    if not href:
                        link_el = await item.query_selector("a[href*='/explore/']")
                        if link_el:
                            href = await link_el.get_attribute("href") or ""

                    # 提取笔记 ID
                    note_id = ""
                    if "/explore/" in href:
                        note_id = href.split("/explore/")[-1].split("?")[0].split("#")[0]
                    elif "/discovery/item/" in href:
                        note_id = href.split("/discovery/item/")[-1].split("?")[0]

                    if not note_id or note_id in seen_ids:
                        continue
                    seen_ids.add(note_id)

                    # 提取标题
                    title_el = await item.query_selector("[class*='title'], [class*='desc'], span, p")
                    title = ""
                    if title_el:
                        title = (await title_el.inner_text()).strip()[:80]

                    # 提取封面图
                    img_el = await item.query_selector("img")
                    cover = ""
                    if img_el:
                        cover = await img_el.get_attribute("src") or ""

                    raw_items.append({
                        "note_id": note_id,
                        "title": title or "无标题",
                        "cover": cover,
                    })
                except Exception:
                    continue

            if not raw_items:
                error = "搜索结果解析失败（未提取到有效笔记）"
                return [], error

            logger.info("解析到 %d 篇有效笔记", len(raw_items))

            # 5. 逐个访问详情页提取正文
            consecutive_failures = 0
            for item in raw_items:
                if len(notes) >= limit:
                    break

                try:
                    detail_url = note_url(item["note_id"])
                    logger.info("  [%d/%d] 抓取详情：%s", len(notes) + 1, limit, item["title"][:30])

                    await page.goto(detail_url, wait_until="load", timeout=20000)
                    await asyncio.sleep(1.5)

                    # 提取正文内容
                    desc = await _extract_note_content(page)

                    if not desc or len(desc) < 50:
                        logger.info("    跳过：正文过短（%d 字）", len(desc or ""))
                        consecutive_failures += 1
                        if consecutive_failures >= 3:
                            logger.warning("  连续 %d 次内容过短，停止", consecutive_failures)
                            break
                        continue

                    consecutive_failures = 0
                    notes.append({
                        "title": f"小红书｜{item['title'][:40]}",
                        "url": detail_url,
                        "summary": desc[:1500],
                        "cover": item["cover"],
                    })
                    logger.info("    成功：《%s》（%d 字）", item["title"][:30], len(desc))

                except Exception as e:
                    consecutive_failures += 1
                    logger.warning("    详情抓取失败：%s", e)
                    if consecutive_failures >= 3:
                        logger.warning("  连续 %d 次失败，停止", consecutive_failures)
                        break

    except Exception as e:
        error = f"浏览器操作失败：{type(e).__name__}: {e}"
        logger.warning("小红书浏览器爬虫异常：%s", e, exc_info=True)

    return notes, error


async def _extract_note_content(page) -> str:
    """从笔记详情页提取正文内容。"""
    # 尝试多种选择器（小红书前端结构可能变化）
    selectors = [
        "[class*='note-text']",
        "[class*='desc']",
        "[class*='content']",
        "#detail-desc",
        "[class*='note'] [class*='text']",
    ]

    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if len(text) > 30:
                    return text
        except Exception:
            continue

    # 兜底：提取 body 文本（去掉导航等噪音）
    try:
        body_text = await page.inner_text("body")
        # 取中间部分（跳过头部导航和底部）
        lines = body_text.split("\n")
        # 过滤掉太短的行（导航、按钮等）
        content_lines = [l.strip() for l in lines if len(l.strip()) > 10]
        return "\n".join(content_lines[:30])
    except Exception:
        return ""


# ============================================================
# 公共接口（与 xhs_mcp.py 对齐）
# ============================================================

async def collect_xhs_sources(
    query: str,
    limit: int | None = None,
    on_note=None,
) -> tuple[list[dict], str]:
    """搜索 + 取详情，组装成攻略素材。接口与 xhs_mcp.collect_xhs_sources 完全一致。"""
    if not enabled():
        return [], ""

    n = limit or settings.xhs_notes_per_turn
    logger.info("小红书浏览器爬虫开始：%s（limit=%d）", query, n)

    try:
        notes, error = await asyncio.wait_for(
            _search_and_extract(query, n),
            timeout=settings.xhs_collect_timeout_s,
        )
    except asyncio.TimeoutError:
        error = f"采集超时（>{settings.xhs_collect_timeout_s:.0f}s）"
        notes = []
        logger.warning("小红书浏览器爬虫超时")

    # 回调通知（与 MCP 版一致）
    if on_note:
        for i, note in enumerate(notes, 1):
            try:
                on_note(i, note)
            except Exception:
                pass

    logger.info("小红书浏览器爬虫结束：%d 篇笔记", len(notes))
    return notes, error


def collect_xhs_sources_sync(
    query: str,
    limit: int | None = None,
    on_note=None,
) -> tuple[list[dict], str]:
    """同步包装：供 LangGraph 的同步节点在 FastAPI 线程池里直接调用。"""
    if not enabled():
        return [], ""
    try:
        return asyncio.run(collect_xhs_sources(query, limit, on_note))
    except Exception as e:
        logger.warning("小红书浏览器爬虫同步调用失败：%s", query, exc_info=True)
        return [], f"{type(e).__name__}: {e}"
