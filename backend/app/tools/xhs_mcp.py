"""小红书 MCP 客户端 —— xpzouying/xiaohongshu-mcp 薄封装。

用 Windows 二进制跑 xiaohongshu-mcp（127.0.0.1:18060，扫码登录 cookie 持久化），
本模块经 mcp streamable HTTP 调它的 search_feeds / get_feed_detail。

设计约束：
- `XHS_MCP_URL` 未配置 → `enabled()=False`，调用方跳过，走预置数据兜底；
- 一切失败（超时 / 未登录 / 结构变化）→ 返回空，绝不阻塞主流程；
- 这个第三方 MCP 还暴露了 publish / comment / like / favorite 等**写操作**，而登录态是全平台
  共享账号，一旦有代码路径把工具名交给 LLM 决定就可能越权发帖。这里硬编码只读白名单，
  让越权在结构上不可能。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from app.config import settings

logger = logging.getLogger(__name__)

# 每篇笔记采集成功后的回调：on_note(已抓到篇数, 完整 note dict)
NoteCallback = Callable[[int, dict], None]


def enabled() -> bool:
    return bool(settings.xhs_mcp_url)


def _https(url: str) -> str:
    """统一升级为 https，避免前端混合内容被拦截。"""
    if url and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


# ---------- 纯解析（可离线测） ----------

def _parse_feeds(text: str) -> list[dict]:
    """search_feeds 返回 JSON → [{feed_id, xsec_token, title, cover}]。

    实测结构：{"feeds": [{"xsecToken", "id", "noteCard": {"displayTitle", "cover"}}]}；
    兼容驼峰/下划线两种字段。没有 id+token 的条目丢弃。
    """
    try:
        data = json.loads(text)
    except ValueError:
        return []
    feeds = data.get("feeds") or data.get("data") or []
    out: list[dict] = []
    for f in feeds:
        if not isinstance(f, dict):
            continue
        fid = f.get("id") or f.get("feed_id") or ""
        token = f.get("xsec_token") or f.get("xsecToken") or ""
        card = f.get("noteCard") or f.get("note_card") or {}
        title = f.get("title") or card.get("displayTitle") or card.get("display_title") or ""
        cover_obj = card.get("cover") or {}
        cover = _https(
            cover_obj.get("urlDefault")
            or cover_obj.get("url_default")
            or cover_obj.get("urlPre")
            or ""
        )
        if fid and token:
            out.append({"feed_id": fid, "xsec_token": token, "title": title, "cover": cover})
    return out


def _parse_detail(text: str) -> dict | None:
    """get_feed_detail 返回 JSON → {title, desc, cover}；结构不符返回 None。

    实测结构：{"data": {"note": {"title", "desc", "imageList": [{"urlDefault"...}]}}}。
    没有正文的（纯图/广告位）返回 None。cover 取第一张正文图。
    """
    try:
        data = json.loads(text)
    except ValueError:
        return None
    note = ((data.get("data") or {}).get("note")) or data.get("note") or {}
    if not isinstance(note, dict):
        return None
    title = (note.get("title") or "").strip()
    desc = (note.get("desc") or "").strip()
    if not desc:
        return None
    cover = ""
    for raw in note.get("imageList") or note.get("image_list") or []:
        if isinstance(raw, dict):
            url = _https(
                raw.get("urlDefault") or raw.get("url_default")
                or raw.get("urlPre") or raw.get("url")
            )
            if url:
                cover = url
                break
    return {"title": title or desc[:30], "desc": desc, "cover": cover}


def note_url(feed_id: str) -> str:
    return f"https://www.xiaohongshu.com/explore/{feed_id}"


# ---------- MCP 调用 ----------

_READONLY_TOOLS = frozenset({"search_feeds", "get_feed_detail"})


class XHSToolNotAllowed(RuntimeError):
    """调用了非只读白名单内的小红书工具。"""


async def _call_tool(tool: str, args: dict) -> str:
    """单次 MCP 工具调用，返回文本内容。整体超时兜底（MCP 服务僵死不能拖垮主流程）。"""
    if tool not in _READONLY_TOOLS:
        logger.error("拒绝调用非只读小红书工具 %r（白名单：%s）", tool, sorted(_READONLY_TOOLS))
        raise XHSToolNotAllowed(f"xhs tool not allowed: {tool}")

    # 延迟导入：未启用小红书时无需安装 mcp 包，app 也能正常启动
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def _inner() -> str:
        async with streamablehttp_client(settings.xhs_mcp_url) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                return "\n".join(
                    c.text for c in res.content if getattr(c, "type", "") == "text"
                )

    return await asyncio.wait_for(_inner(), timeout=settings.xhs_mcp_timeout_s)


async def search_notes(keyword: str) -> list[dict]:
    """搜笔记 → [{feed_id, xsec_token, title, cover}]；未启用/失败返回 []。

    搜索是整条链路的网关（失败 = 这轮小红书全军覆没，回退预置数据），冷加载偶发超时——重试一次。
    """
    if not enabled():
        return []
    logger.info("开始搜索小红书：%s", keyword)
    for attempt in range(2):
        try:
            feeds = _parse_feeds(await _call_tool("search_feeds", {"keyword": keyword}))
            logger.info("小红书搜索完成，返回 %d 篇笔记", len(feeds))
            return feeds
        except Exception:  # noqa: BLE001 — 超时/未登录/服务挂了都静默降级
            logger.warning("小红书搜索失败（第 %d 次重试）：%s", attempt + 1, keyword,
                           exc_info=attempt == 1)
    return []


async def note_detail(feed_id: str, xsec_token: str) -> dict | None:
    """取笔记详情 → {title, desc, cover}；失败返回 None。"""
    if not enabled():
        return None
    try:
        det = _parse_detail(await _call_tool(
            "get_feed_detail", {"feed_id": feed_id, "xsec_token": xsec_token}
        ))
        if det is not None:
            logger.info("    详情成功：《%s》（正文 %d 字）", det["title"][:24], len(det["desc"]))
        return det
    except Exception:  # noqa: BLE001
        logger.warning("    详情失败：%s", feed_id, exc_info=True)
        return None


async def collect_xhs_sources(
    query: str,
    limit: int | None = None,
    on_note: NoteCallback | None = None,
) -> list[dict]:
    """搜索 + 取前 N 篇详情，组装成攻略素材 [{title, url, summary, cover}]；未启用/失败返回 []。

    - 详情串行取（MCP 后端是单浏览器会话，并发反而互相拖慢），每篇约 20s；
    - 整轮总预算 = xhs_collect_timeout_s，超时**交回已抓到的**（部分收成），不回退全丢；
    - 连续 2 次详情失败 → 熔断，快速放弃（否则每篇都等超时，纯浪费等待）。
    - on_note(已抓到篇数, note)：每采纳入库一篇就回调一次，供上层推送到前端。
    """
    if not enabled():
        return []

    logger.info("开始采集小红书笔记：%s", query)
    sink: list[dict] = []
    try:
        await asyncio.wait_for(
            _collect_within_budget(query, limit, sink, on_note),
            timeout=settings.xhs_collect_timeout_s,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "小红书采集超预算（%.0f 秒），已抓到 %d 篇，超时部分收成（不再继续等）",
            settings.xhs_collect_timeout_s, len(sink),
        )
    logger.info("小红书采集结束，共 %d 篇有效笔记", len(sink))
    return sink


async def _collect_within_budget(
    query: str,
    limit: int | None,
    out: list[dict],
    on_note: NoteCallback | None,
) -> list[dict]:
    """`out` 由调用方传入：预算超时时外层直接拿走已追加的部分（部分收成）。"""
    n = limit or settings.xhs_notes_per_turn
    feeds = await search_notes(query)
    attempts = 0
    consecutive_failures = 0
    for f in feeds:
        if len(out) >= n or attempts >= n + 2:
            break
        attempts += 1
        logger.info("  [%d/%d] 抓取第 %d 篇：《%s》",
                    len(out) + 1, n, attempts, (f.get("title") or "无标题")[:30])
        det = await note_detail(f["feed_id"], f["xsec_token"])
        if det is None:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                logger.warning("  连续 %d 次失败，熔断停止（小红书可能异常）", consecutive_failures)
                break
            continue
        consecutive_failures = 0
        if len(det["desc"]) < 100:  # 太短的笔记（纯图/广告位）不当来源，但不计故障
            logger.info("    跳过：正文过短（%d 字，纯图/广告位）", len(det["desc"]))
            continue
        note = {
            "title": f"小红书｜{det['title'][:40]}",
            "url": note_url(f["feed_id"]),
            "summary": det["desc"][:1500],  # 笔记细节是攻略质量原料，给足；截断控 token
            "cover": det.get("cover") or f.get("cover") or "",
        }
        out.append(note)
        logger.info("  已采纳入库第 %d 篇：《%s》", len(out), det["title"][:30])
        if on_note is not None:
            try:
                on_note(len(out), note)
            except Exception:  # noqa: BLE001 — 进度回调绝不能影响采集
                pass
    return out


def collect_xhs_sources_sync(
    query: str,
    limit: int | None = None,
    on_note: NoteCallback | None = None,
) -> list[dict]:
    """同步包装：供 LangGraph 的同步节点在 FastAPI 线程池里直接调用。"""
    if not enabled():
        return []
    try:
        return asyncio.run(collect_xhs_sources(query, limit, on_note))
    except Exception:  # noqa: BLE001
        logger.warning("小红书采集同步调用失败：%s", query, exc_info=True)
        return []
