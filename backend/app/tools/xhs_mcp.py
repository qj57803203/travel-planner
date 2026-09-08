"""小红书 MCP 客户端 —— xpzouying/xiaohongshu-mcp 薄封装（主力方案）。

通过 MCP Streamable HTTP 协议调用小红书搜索/详情/登录等工具。
登录机制：调用 get_login_qrcode 获取二维码（base64），开发者扫码后 MCP 自动保存 cookie。

设计约束：
- `XHS_MCP_URL` 未配置 → `enabled()=False`，调用方跳过；
- 一切失败（超时 / 未登录 / 结构变化）→ 返回空列表并带出原因，绝不阻塞主流程；
- 这个第三方 MCP 还暴露了 publish / comment / like / favorite 等**写操作**，而登录态是全平台
  共享账号，一旦有代码路径把工具名交给 LLM 决定就可能越权发帖。这里硬编码只读白名单，
  让越权在结构上不可能。

资源占用（线上实测）：361.6 MiB 内存，369 个进程
"""

from __future__ import annotations

import asyncio
import json
import logging
logging.basicConfig(level=logging.INFO)
# 静音第三方库的噪音 INFO 日志（httpx 请求记录、mcp 的 SSE 重连提示）
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)
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


def _err_text(e: BaseException) -> str:
    """穿透 anyio 的 ExceptionGroup/TaskGroup，取最底层异常的「类型: 消息」。

    连接失败时 mcp 的 streamable_http 会把 httpx.ConnectError 包进 ExceptionGroup，
    直接 str(e) 只会得到「unhandled errors in a TaskGroup」，这里递归取子异常还原真实原因。
    """
    subs = getattr(e, "exceptions", None)
    if subs:
        return _err_text(subs[0])
    return f"{type(e).__name__}: {e}"


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

# 只读白名单 + 登录管理工具（get_login_qrcode / check_login_status / delete_cookies 不写业务数据）
_READONLY_TOOLS = frozenset({"search_feeds", "get_feed_detail", "get_login_qrcode", "check_login_status", "delete_cookies"})


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
        import time
        t0 = time.time()
        logger.info("[MCP] 开始连接 %s，工具=%s", settings.xhs_mcp_url, tool)
        async with streamablehttp_client(settings.xhs_mcp_url) as (r, w, _):
            t1 = time.time()
            logger.info("[MCP] 连接建立耗时 %.1fs，开始初始化会话", t1 - t0)
            async with ClientSession(r, w) as s:
                await s.initialize()
                t2 = time.time()
                logger.info("[MCP] 会话初始化耗时 %.1fs，开始调用工具 %s", t2 - t1, tool)
                res = await s.call_tool(tool, args)
                t3 = time.time()
                logger.info("[MCP] 工具调用耗时 %.1fs，返回 %d 个 content", t3 - t2, len(res.content))
                return "\n".join(
                    c.text for c in res.content if getattr(c, "type", "") == "text"
                )

    return await asyncio.wait_for(_inner(), timeout=settings.xhs_mcp_timeout_s)


async def _call_tool_raw(tool: str, args: dict) -> list:
    """单次 MCP 工具调用，返回原始 content 列表（包含 text/image 等多种类型）。

    用于需要获取图片等非文本内容的场景（如 get_login_qrcode 返回二维码图片）。
    """
    if tool not in _READONLY_TOOLS:
        logger.error("拒绝调用非只读小红书工具 %r（白名单：%s）", tool, sorted(_READONLY_TOOLS))
        raise XHSToolNotAllowed(f"xhs tool not allowed: {tool}")

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def _inner() -> list:
        async with streamablehttp_client(settings.xhs_mcp_url) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                return res.content

    return await asyncio.wait_for(_inner(), timeout=settings.xhs_mcp_timeout_s)


# ---------- 登录管理（二维码扫码登录） ----------

async def get_login_qrcode() -> tuple[str, int, bool]:
    """获取小红书登录二维码。

    调用 MCP 的 get_login_qrcode 工具。
    MCP 返回格式（非 JSON）：
    - 已登录时：文本 "你当前已处于登录状态"
    - 未登录时：[文本 "请用小红书 App 在 ... 前扫码登录 👇", 图片 content(image/png)]

    Returns:
        (qrcode_base64, timeout_seconds, already_logged_in)
        - qrcode_base64: "data:image/png;base64,..." 格式，前端直接塞 <img src>
        - timeout_seconds: 二维码有效时间（秒），超时需重新获取
        - already_logged_in: 已登录时为 True，此时 qrcode_base64 为空
    """
    logger.info("开始获取小红书登录二维码")
    try:
        contents = await _call_tool_raw("get_login_qrcode", {})

        # 遍历 content 列表，提取文本和图片
        text_parts = []
        image_b64 = ""
        for c in contents:
            ctype = getattr(c, "type", "")
            if ctype == "text":
                text_parts.append(getattr(c, "text", ""))
            elif ctype == "image":
                # MCP 返回的是纯 base64（不含 data: 前缀），需要拼上
                raw_b64 = getattr(c, "data", "")
                mime = getattr(c, "mimeType", "image/png")
                if raw_b64:
                    image_b64 = f"data:{mime};base64,{raw_b64}"

        full_text = "\n".join(text_parts)
        logger.info("MCP get_login_qrcode 返回：text=%s, has_image=%s", full_text[:100], bool(image_b64))

        # 判断是否已登录
        if "已" in full_text and "登录" in full_text:
            logger.info("小红书：已处于登录状态，无需扫码")
            return "", 0, True

        if not image_b64:
            logger.warning("小红书：MCP 未返回二维码图片，text=%s", full_text[:200])
            return "", 0, False

        logger.info("小红书：二维码已获取，请扫码登录")
        return image_b64, 240, False

    except Exception as e:
        logger.error("获取小红书登录二维码失败：%s", _err_text(e), exc_info=True)
        return "", 0, False


async def check_login_status() -> tuple[bool, str]:
    """检查小红书登录状态。

    MCP 返回格式（非 JSON）：
    - 已登录："✅ 已登录\n用户名: xxx\n\n你可以使用其他功能了。"
    - 未登录："❌ 未登录\n\n请使用 get_login_qrcode 工具获取二维码进行登录。"

    Returns:
        (is_logged_in, message)
    """
    logger.info("检查小红书登录状态")
    try:
        text = await _call_tool("check_login_status", {})
        logger.info("MCP check_login_status 返回：%s", text[:200])

        # 判断登录状态：文本中包含 "✅ 已登录" 表示已登录
        logged_in = "✅" in text and "已登录" in text
        message = text.strip()
        logger.info("小红书登录状态：%s", "已登录" if logged_in else "未登录")
        return logged_in, message

    except Exception as e:
        err = _err_text(e)
        logger.error("检查小红书登录状态失败：%s", err, exc_info=True)
        return False, err


async def search_notes(keyword: str) -> tuple[list[dict], str]:
    """搜笔记 → ([{feed_id, xsec_token, title, cover}], 错误信息)；失败返回 ([], 原因)。

    搜索是整条链路的网关（失败 = 这轮小红书全军覆没），冷加载偶发超时——重试一次。
    """
    if not enabled():
        return [], ""
    logger.info("开始搜索小红书：%s", keyword)
    last_err = ""
    for attempt in range(2):
        try:
            feeds = _parse_feeds(await _call_tool("search_feeds", {"keyword": keyword}))
            logger.info("小红书搜索完成，返回 %d 篇笔记", len(feeds))
            return feeds, ""
        except Exception as e:  # noqa: BLE001 — 超时/未登录/服务挂了都降级，但把原因带出去
            last_err = _err_text(e)
            logger.warning("小红书搜索失败（第 %d 次重试）：%s %s", attempt + 1, keyword,
                           last_err, exc_info=attempt == 1)
    return [], last_err


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
) -> tuple[list[dict], str]:
    """搜索 + 取前 N 篇详情，组装成攻略素材 ([{title, url, summary, cover}], 错误信息)。

    - 详情串行取（MCP 后端是单浏览器会话，并发反而互相拖慢），每篇约 20s；
    - 整轮总预算 = xhs_collect_timeout_s，超时**交回已抓到的**（部分收成），不回退全丢；
    - 连续 2 次详情失败 → 熔断，快速放弃（否则每篇都等超时，纯浪费等待）。
    - on_note(已抓到篇数, note)：每采集成功一篇就回调一次，供上层推送到前端。
    - 第二元素为错误信息（空串=无错误），整轮失败/降级时非空，交给上层透传给前端。
    """
    if not enabled():
        return [], ""

    logger.info("开始采集小红书笔记：%s", query)
    sink: list[dict] = []
    error = ""
    try:
        error = await asyncio.wait_for(
            _collect_within_budget(query, limit, sink, on_note),
            timeout=settings.xhs_collect_timeout_s,
        )
    except asyncio.TimeoutError:
        error = f"采集超时（>{settings.xhs_collect_timeout_s:.0f}s）"
        logger.warning(
            "小红书采集超预算（%.0f 秒），已抓到 %d 篇，超时部分收成（不再继续等）",
            settings.xhs_collect_timeout_s, len(sink),
        )
    logger.info("小红书采集结束，共 %d 篇有效笔记", len(sink))
    return sink, error


async def _collect_within_budget(
    query: str,
    limit: int | None,
    out: list[dict],
    on_note: NoteCallback | None,
) -> str:
    """`out` 由调用方传入：预算超时时外层直接拿走已追加的部分（部分收成）。

    返回错误信息（空串=无错误）：搜索失败把网关错误直接带回；详情熔断且一无所获时给简短提示。
    """
    n = limit or settings.xhs_notes_per_turn
    feeds, search_err = await search_notes(query)
    if search_err:
        return search_err
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
                return "" if out else "详情连续失败，已熔断"
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
        logger.info("  已采集第 %d 篇：《%s》", len(out), det["title"][:30])
        if on_note is not None:
            try:
                on_note(len(out), note)
            except Exception:  # noqa: BLE001 — 进度回调绝不能影响采集
                pass
    return ""


def collect_xhs_sources_sync(
    query: str,
    limit: int | None = None,
    on_note: NoteCallback | None = None,
) -> tuple[list[dict], str]:
    """同步包装：供 LangGraph 的同步节点在 FastAPI 线程池里直接调用。"""
    if not enabled():
        return [], ""
    try:
        return asyncio.run(collect_xhs_sources(query, limit, on_note))
    except Exception as e:  # noqa: BLE001
        logger.warning("小红书采集同步调用失败：%s", query, exc_info=True)
        return [], _err_text(e)
