"""LangGraph 的三个节点：抽取偏好 → 搜集信息 → 生成行程。"""
import json
import logging
import re
from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek

from app.agent.prompts import EXTRACT_PROMPT, MODIFY_EXTRACT_PROMPT, MODIFY_PLAN_PROMPT, PLAN_PROMPT
from app.agent.state import AgentState
from app.config import settings
from app.database import SessionLocal
from app.models import XhsNoteCache
from app.tools import amap, xhs_mcp
# from app.tools import xhs_browser

DEFAULT_PREFERENCES = {
    "destination": "",
    "days": 3,
    "pace": "适中",
    "interests": [],
    "hotel_preference": [],
    "departure": "",
}

logger = logging.getLogger(__name__)


def _get_llm(temperature: float = 0.0, json_mode: bool = False) -> ChatDeepSeek:
    """创建 LLM 实例。

    Args:
        temperature: 温度参数，0.0 追求稳定，0.7 追求多样性
        json_mode: 是否强制输出 JSON（通过 response_format=json_object）
    """
    kwargs = {
        "model": settings.deepseek_model,
        "api_key": settings.deepseek_api_key,
        "temperature": temperature,
    }
    if json_mode:
        # 强制模型输出合法 JSON
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatDeepSeek(**kwargs)


def _usage(resp) -> dict:
    """从 LLM 响应提取 token 用量，兼容 langchain 不同版本的 usage 字段。"""
    um = getattr(resp, "usage_metadata", None)
    if um:
        return {
            "input": um.get("input_tokens") or um.get("prompt_tokens") or 0,
            "output": um.get("output_tokens") or um.get("completion_tokens") or 0,
        }
    meta = resp.response_metadata or {}
    tu = meta.get("token_usage") or meta.get("usage") or {}
    return {
        "input": tu.get("prompt_tokens") or tu.get("input_tokens") or 0,
        "output": tu.get("completion_tokens") or tu.get("output_tokens") or 0,
    }


def _parse_json(text: str) -> dict:
    """解析 LLM 输出的 JSON（已启用 response_format=json_object，直接解析即可）。

    Returns:
        解析后的 dict。解析失败时抛出 ValueError（由调用方 fallback）。
    """
    if not isinstance(text, str):
        raise TypeError(f"期望 str，实际收到 {type(text).__name__}")

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("_parse_json: JSON 解析失败 — %s\n原始输出:\n%s", e, text)
        raise ValueError(f"JSON 解析失败: {e}") from e

    # LLM 有时返回数组包裹对象，自动取第一个
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return result[0]
    if not isinstance(result, dict):
        raise ValueError(f"期望 JSON 对象，实际收到 {type(result).__name__}")
    return result


def _stream_writer():
    """返回 LangGraph 的 stream writer；不可用（非流式调用 / 版本不支持）时返回 None。"""
    try:
        from langgraph.config import get_stream_writer
        return get_stream_writer()
    except Exception:  # noqa: BLE001 — 非流式场景下无 writer，静默降级
        return None


def _emit_xhs_note(writer, index: int, note: dict) -> None:
    """把小红书单篇采集进度推给前端（writer 为 None 时跳过）。"""
    logger.info("  xhs_note 推送: #%d title=%s, cover=%s", index, note.get("title", "")[:30], note.get("cover", "")[:80])
    if writer is not None:
        writer({"type": "xhs_note", "index": index, **note})


def extract_preferences(state: AgentState) -> dict:
    """节点 1：从自然语言需求抽取结构化偏好。

    修改模式下（is_modification=True），从用户反馈中提取修改意图，
    与上一轮 preferences 合并后返回。

    Returns:
        {
            "preferences": {...},
            "usage": {"extract": {...}},
            "_destination_changed": bool  # 供 graph 条件分支判断是否跳过 research
        }
    """
    is_mod = state.get("is_modification", False)

    try:
        llm = _get_llm(temperature=0.0, json_mode=True)

        if is_mod:
            # ── 修改模式：提取修改意图，合并到上一轮偏好 ──
            prev_prefs = state.get("preferences", {})
            chain = ChatPromptTemplate.from_template(MODIFY_EXTRACT_PROMPT) | llm
            resp = chain.invoke({
                "input": state["user_input"],
                "previous_preferences": json.dumps(prev_prefs, ensure_ascii=False),
            })
            usage = _usage(resp)
            data = _parse_json(resp.content)
            logger.info("extract_preferences(修改模式): 修改意图=%s", data.get("modification_intent", ""))

            # 合并：上一轮偏好 + 修改意图
            prefs = {**prev_prefs}
            new_dest = (data.get("destination") or "").strip()
            if new_dest:
                prefs["destination"] = new_dest
            new_pace = (data.get("pace") or "").strip()
            if new_pace:
                prefs["pace"] = new_pace

            # 兴趣增删
            old_interests = set(prefs.get("interests") or [])
            old_interests.update(data.get("interests_to_add") or [])
            old_interests -= set(data.get("interests_to_remove") or [])
            prefs["interests"] = list(old_interests)

            # 判断目的地是否变化（供 graph 跳过 research）
            old_dest = (prev_prefs.get("destination") or "").strip()
            dest_changed = bool(new_dest) and new_dest != old_dest

            return {"preferences": prefs, "usage": {"extract": usage}, "_destination_changed": dest_changed}
        else:
            # ── 首次生成：原有逻辑 ──
            chain = ChatPromptTemplate.from_template(EXTRACT_PROMPT) | llm
            resp = chain.invoke({"input": state["user_input"]})
            usage = _usage(resp)

            data = _parse_json(resp.content)
            logger.debug("extract_preferences: _parse_json 返回 type=%s, data=%s", type(data).__name__, str(data)[:200])
            prefs = {**DEFAULT_PREFERENCES, **data}
            prefs["days"] = int(prefs.get("days") or 1)
            # 出发地兜底：输入里没提取到就用用户配置里记住的出发地
            if not (prefs.get("departure") or "").strip():
                prefs["departure"] = (state.get("profile_departure") or "").strip()
            return {"preferences": prefs, "usage": {"extract": usage}}
    except Exception as e:
        logger.error("extract_preferences 异常: %s", e, exc_info=True)
        raise


def research(state: AgentState) -> dict:
    """节点 2：搜集信息素材 —— 小红书攻略笔记。

    小红书采集使用 MCP 方案（xiaohongshu-mcp 容器，通过 MCP 协议调用）。

    Returns:
        {
            "research": {
                "destination": str,
                "hotels": [{"name": str, "price": str, "rating": str, ...}],
                "attractions": [{"name": str, "area": str, "note": str, ...}],
                "food": [{"name": str, "category": str, "note": str}],
                "transport": [{"mode": str, "detail": str}],
                "xhs_notes": [{"title": str, "url": str, "summary": str, "cover": str}],
                "xhs_status": "live" | "cached" | "fallback" | "",
                "xhs_error": str,
            }
        }
    """
    prefs = state.get("preferences", {})
    dest = (prefs.get("destination") or "").strip()

    research_info = {
        "destination": dest,
        "hotels": [],
        "attractions": [],
        "food": [],
        "transport": [],
        "xhs_notes": [],
        "xhs_status": "",   # live / cached / fallback；空 = 未启用小红书
        "xhs_error": "",    # 失败原因（如 ConnectError: ...），供前端透出
    }

    # 2. 小红书笔记 —— 先查一周内目的地缓存，命中秒回；未命中才实时爬取并写缓存
    #    使用 MCP 方案（xiaohongshu-mcp 容器，通过 MCP 协议调用）
    if dest:
        cached = _load_xhs_cache(dest)
        if cached:
            research_info["xhs_notes"] = cached
            research_info["xhs_status"] = "cached"
            logger.info("小红书：命中缓存，%s 共 %d 篇笔记", dest, len(cached))
        else:
            interests = " ".join((prefs.get("interests") or [])[:2])
            query = f"{dest} 旅游攻略{' ' + interests if interests else ''}"
            writer = _stream_writer()

            # ── MCP 主力方案 ──
            notes, err = [], ""
            if xhs_mcp.enabled():
                logger.info("小红书：使用 MCP 方案采集笔记")
                notes, err = xhs_mcp.collect_xhs_sources_sync(
                    query,
                    on_note=lambda i, note: _emit_xhs_note(writer, i, note),
                )
            else:
                logger.warning("小红书：MCP 未启用（XHS_MCP_URL 未配置），跳过采集")


            research_info["xhs_notes"] = notes
            _save_xhs_cache(dest, notes)
            if notes:
                research_info["xhs_status"] = "live"
            else:
                research_info["xhs_status"] = "fallback"
                research_info["xhs_error"] = err

    return {"research": research_info}


def _load_xhs_cache(destination: str) -> list[dict]:
    """查一周内该目的地的小红书笔记缓存；未命中/出错返回 []（回退实时爬取）。"""
    cutoff = datetime.utcnow() - timedelta(days=settings.xhs_cache_ttl_days)
    try:
        with SessionLocal() as db:
            rows = (
                db.query(XhsNoteCache)
                .filter(
                    XhsNoteCache.destination == destination,
                    XhsNoteCache.created_at >= cutoff,
                )
                .order_by(XhsNoteCache.id.desc())
                .limit(settings.xhs_notes_per_turn)
                .all()
            )
        notes = [
            {"title": r.title, "url": r.url, "summary": r.summary, "cover": r.cover}
            for r in rows
        ]
        for n in notes:
            logger.info("  缓存笔记: title=%s, cover=%s", n["title"][:30], n["cover"][:80] if n["cover"] else "(空)")
        return notes
    except Exception:  # noqa: BLE001 — 缓存不可用绝不阻塞主流程
        logger.warning("读取小红书缓存失败：%s", destination, exc_info=True)
        return []


def _save_xhs_cache(destination: str, notes: list[dict]) -> None:
    """把采集到的笔记写入缓存（按 url 去重，已存在则跳过）；失败静默。"""
    if not notes:
        return
    try:
        with SessionLocal() as db:
            for n in notes:
                url = n.get("url", "")
                if not url:
                    continue
                if (
                    db.query(XhsNoteCache.id)
                    .filter(
                        XhsNoteCache.destination == destination,
                        XhsNoteCache.url == url,
                    )
                    .first()
                ):
                    continue
                db.add(
                    XhsNoteCache(
                        destination=destination,
                        url=url,
                        title=n.get("title", ""),
                        summary=n.get("summary", ""),
                        cover=n.get("cover", ""),
                    )
                )
            db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("写入小红书缓存失败：%s", destination, exc_info=True)


def _format_xhs_notes(notes: list[dict]) -> str:
    if not notes:
        return "（无小红书笔记，参考结构化素材即可）"
    parts = []
    for i, n in enumerate(notes, 1):
        parts.append(f"{i}. {n.get('title', '')}\n   {n.get('summary', '')}")
    return "\n".join(parts)


def _format_chat_history(history: list[dict]) -> str:
    """将对话历史格式化为可读文本，供 MODIFY_PLAN_PROMPT 使用。"""
    if not history:
        return "（无对话历史）"
    parts = []
    for msg in history:
        role = "用户" if msg.get("role") == "user" else "助手"
        parts.append(f"【{role}】{msg.get('content', '')[:500]}")
    return "\n\n".join(parts)


def generate_itinerary(state: AgentState) -> dict:
    """节点 3：根据偏好 + 信息素材 + 小红书笔记生成每日行程。

    修改模式下（is_modification=True），使用 MODIFY_PLAN_PROMPT 在上一轮行程基础上修改。

    Returns:
        {
            "itinerary": str,          # 行程 markdown 正文（含 ## Day 1 等标题）
            "plan_days": [{"day": 1, "spots": ["景点A", "景点B"]}],  # 每天景点序列
            "transport_mode": str,     # "driving" | "train" | "flight" | ""
            "transport_reason": str,   # 交通方式选择理由
            "usage": {"extract": {...}, "plan": {"input": int, "output": int}},
        }
    """
    prefs = state.get("preferences", {})
    research = state.get("research", {})
    is_mod = state.get("is_modification", False)
    llm = _get_llm(temperature=0.7, json_mode=True)
    # 结构化素材单独给，小红书笔记单独一段，避免重复
    structured = {k: v for k, v in research.items() if k != "xhs_notes"}

    if is_mod:
        # ── 修改模式：在上一轮行程基础上修改 ──
        chat_history = state.get("chat_history", [])
        previous_itinerary = state.get("previous_itinerary", "")
        prompt = MODIFY_PLAN_PROMPT.format(
            pace=prefs.get("pace", "适中"),
            preferences=json.dumps(prefs, ensure_ascii=False, indent=2),
            research=json.dumps(structured, ensure_ascii=False, indent=2),
            xhs_notes=_format_xhs_notes(research.get("xhs_notes", [])),
            chat_history=_format_chat_history(chat_history),
            previous_itinerary=_strip_injected_blocks(previous_itinerary)[:3000],  # 剥离旧的注入内容（酒店+交通），避免重复
        )
        logger.info("generate_itinerary: 修改模式，使用 MODIFY_PLAN_PROMPT")
    else:
        # ── 首次生成：原有逻辑 ──
        prompt = PLAN_PROMPT.format(
            pace=prefs.get("pace", "适中"),
            interests="、".join(prefs.get("interests", [])) or "无特殊偏好",
            preferences=json.dumps(prefs, ensure_ascii=False, indent=2),
            research=json.dumps(structured, ensure_ascii=False, indent=2),
            xhs_notes=_format_xhs_notes(research.get("xhs_notes", [])),
        )

    resp = llm.invoke(prompt)
    usage = _usage(resp)
    logger.info("plan 消耗 token：input=%s output=%s", usage["input"], usage["output"])
    usage_map = state.get("usage", {})
    usage_map["plan"] = usage
    markdown, days, transport_mode, transport_reason, accommodation_area = _parse_plan(resp.content)
    return {
        "itinerary": markdown,
        "plan_days": days,
        "transport_mode": transport_mode,
        "transport_reason": transport_reason,
        "accommodation_area": accommodation_area,
        "usage": usage_map,
    }


def _parse_plan(content: str) -> tuple[str, list, str, str]:
    """解析 plan 节点 LLM 的结构化 JSON 输出，提取行程 markdown 和交通信息。

    ────────────────────────────────────────────────────────────
    LLM 理想输出（PLAN_PROMPT 明确要求）：

        {
            "markdown": "线路概览\\n- Day1：...\\n\\n## Day 1\\n**上午** ...",
            "days": [{"day": 1, "spots": ["浅草寺", "涩谷 SKY"]}],
            "transport_mode": "train",
            "transport_reason": "上海到东京距离较远，建议乘坐飞机"
        }

    即：一个合法 JSON 对象，markdown 字段是纯文本行程（含 markdown 格式符号），
    days 是每天景点名数组（供后续查高德交通），transport_* 是城际交通建议。

    ────────────────────────────────────────────────────────────
    LLM 实际常犯的问题（按本函数逻辑依次兜底）：

    问题 1 — JSON 整体格式问题（代码块包裹、前后多余文字等）
      → 由 _parse_json 的三层策略处理，本函数只看解析结果。

    问题 2 — JSON 解析成功，但 markdown 字段里又是一层 JSON 字符串：
        {"markdown": "{\"markdown\": \"## Day 1...\", \"days\": [...]}"}
      → 本函数检测 markdown 以 `{` 开头时，尝试 _parse_json 剥一层。

    问题 3 — JSON 解析成功，但缺少 markdown 字段（LLM 用了别的 key 名）
      → data.get("markdown") 为空 → 尝试正则从原始 content 挽救。

    问题 4 — 所有挽救均失败
      → 返回原始 content 作为 itinerary（前端会原样展示，可从日志定位原因）。

    ────────────────────────────────────────────────────────────

    Returns:
        (markdown, days, transport_mode, transport_reason, accommodation_area)
    """
    # ── 第 1 步：尝试正常解析 JSON ──
    try:
        data = _parse_json(content)
        logger.debug("_parse_plan: _parse_json 返回 type=%s, keys=%s", type(data).__name__, list(data.keys()) if isinstance(data, dict) else "N/A")
    except Exception as e:
        logger.warning("_parse_plan: _parse_json 解析失败 — %s", e)
        data = None

    if isinstance(data, dict):
        markdown = data.get("markdown") or ""
        days = data.get("days") or []
        transport_mode = data.get("transport_mode") or ""
        transport_reason = data.get("transport_reason") or ""
        accommodation_area = data.get("accommodation_area") or ""

        # ── 问题 2：markdown 字段里嵌套了一层 JSON，尝试剥一层 ──
        if isinstance(markdown, str) and markdown.strip().startswith("{"):
            logger.info("_parse_plan: markdown 字段以 '{' 开头，疑似嵌套 JSON，尝试剥一层")
            try:
                inner = _parse_json(markdown)
                if isinstance(inner, dict) and inner.get("markdown"):
                    logger.info("_parse_plan: 剥层成功，取出内层 markdown（长度=%d）", len(inner["markdown"]))
                    markdown = inner["markdown"]
                else:
                    logger.warning("_parse_plan: 剥层后无 markdown 字段，用外层原值")
            except Exception as e:  # noqa: BLE001
                logger.warning("_parse_plan: 剥层失败（%s），用外层原值", e)

        if isinstance(markdown, str) and markdown.strip():
            logger.info(
                "_parse_plan: 解析成功 — markdown=%d字符, days=%d天, transport=%s, accommodation=%s",
                len(markdown), len(days), transport_mode or "无", accommodation_area or "无",
            )
            return (
                markdown,
                days if isinstance(days, list) else [],
                transport_mode,
                transport_reason,
                accommodation_area,
            )
        else:
            logger.warning(
                "_parse_plan: JSON 解析成功但 markdown 字段为空，keys=%s",
                list(data.keys()),
            )

    # ── 第 2 步：JSON 解析失败或缺少 markdown，尝试正则挽救 ──
    m = re.search(r'"markdown"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]', content, re.DOTALL)
    if m:
        try:
            markdown = json.loads(f'"{m.group(1)}"')  # 还原转义
            if markdown.strip():
                logger.info("_parse_plan: 正则挽救成功，提取 markdown 字段（长度=%d）", len(markdown))
                return markdown, [], "", "", ""
        except Exception as e:  # noqa: BLE001
            logger.warning("_parse_plan: 正则挽救后 json.loads 失败 — %s", e)

    # ── 第 3 步：完全失败，抛出异常 ──
    logger.error(
        "_parse_plan: 所有策略均失败（长度=%d，前 200 字符）：\n%s",
        len(content), content[:200],
    )
    raise ValueError("行程解析失败：LLM 输出格式不符合预期")


def hotel_search(state: AgentState) -> dict:
    """节点 4：根据住宿建议搜索携程酒店，取前2个高性价比酒店注入行程。

    Returns:
        {
            "hotels": [{"name": str, "price": float, "rating": float, "image": str, "url": str, "location": str}],
            "itinerary": str  # 注入酒店推荐后的完整行程
        }
    """
    from app.tools import ctrip_crawler

    accommodation_area = state.get("accommodation_area", "")
    destination = state.get("preferences", {}).get("destination", "")
    itinerary = state.get("itinerary", "")

    # 分别判断跳过原因，打清楚日志
    if not accommodation_area:
        logger.warning("hotel_search: 跳过 — 未提取到住宿建议（accommodation_area 为空）")
        return {"hotels": []}
    if not ctrip_crawler.enabled():
        logger.warning("hotel_search: 跳过 — 携程爬虫未启用（CTRIPE_MCP_URL 未配置）")
        return {"hotels": []}

    # 从住宿建议中提取搜索关键词（如"乐桥站"、"临顿路站"）
    keywords = _extract_hotel_keywords(accommodation_area)
    if not keywords:
        logger.warning("hotel_search: 跳过 — 无法从住宿建议中提取关键词，原始文本: %s", accommodation_area[:100])
        return {"hotels": []}

    logger.info("hotel_search: 开始搜索携程酒店，目的地=%s，关键词=%s", destination, keywords)

    # 搜索携程酒店（取第一个关键词搜索，取前5条）
    hotels, list_page_url = ctrip_crawler.search_hotels_sync(destination, keywords[0], limit=5)

    if not hotels:
        logger.warning("hotel_search: 携程搜索无结果（爬虫运行正常但未返回数据），关键词=%s", keywords[0])
        return {"hotels": []}

    # 按性价比排序（价格低、评分高），取前2个
    hotels_sorted = sorted(hotels, key=lambda h: (h.get("price", 9999) / (h.get("rating", 1) or 1)))[:2]
    logger.info("hotel_search: 排序完成，选取前 %d 个酒店", len(hotels_sorted))

    # 给每个酒店加上列表页链接（前端"查看更多"按钮用）
    for h in hotels_sorted:
        h["url"] = list_page_url

    # 注入酒店推荐到行程
    hotel_block = _format_hotel_block(hotels_sorted)
    if hotel_block:
        # 在"住宿建议"后面插入酒店推荐
        itinerary = _inject_hotels(itinerary, accommodation_area, hotel_block)

    return {"hotels": hotels_sorted, "itinerary": itinerary}


def _extract_hotel_keywords(accommodation_area: str) -> list[str]:
    """从住宿建议中提取搜索关键词（地铁站名、商圈名等）。

    支持多种格式：
    - "地铁1号线/4号线沿线（如乐桥站、临顿路站附近）" → ["乐桥站", "临顿路站"]
    - "建议住宿在地铁2号线/4号线沿线，如江汉路、中南路附近" → ["江汉路", "中南路"]
    - "西湖附近（如龙翔桥站、凤起路站）" → ["龙翔桥站", "凤起路站"]
    """
    import re

    # 策略 1：提取「（如...）」或「(如...)」括号内的内容
    m = re.search(r'[（(]如(.+?)[）)]', accommodation_area)
    if m:
        content = m.group(1)
        keywords = re.split(r'[、，,]', content)
        # 去掉"站"、"附近"等后缀，只保留核心名称
        return [re.sub(r'(站|附近)$', '', k.strip()) for k in keywords if k.strip()]

    # 策略 2：提取「，如...」或「，如...附近」后面的内容
    m = re.search(r'[,，]如(.+?)(?:，|。|$)', accommodation_area)
    if m:
        content = m.group(1)
        keywords = re.split(r'[、，,]', content)
        return [re.sub(r'(站|附近)$', '', k.strip()) for k in keywords if k.strip()]

    # 策略 3：尝试提取所有「XX站」
    keywords = re.findall(r'([一-龥]{2,6}站)', accommodation_area)
    if keywords:
        return [k.rstrip('站') for k in keywords]

    return []


def _format_hotel_block(hotels: list[dict]) -> str:
    """格式化酒店推荐块。"""
    if not hotels:
        return ""

    lines = ["**🏨 推荐酒店**"]
    for i, h in enumerate(hotels, 1):
        name = h.get("name", "")
        price = h.get("price", 0)
        rating = h.get("rating", 0)
        location = h.get("location", "")
        url = h.get("url", "")

        price_text = f"¥{price:.0f}/晚" if price else "价格待询"
        rating_text = f"⭐{rating:.1f}" if rating else ""
        location_text = f"📍{location}" if location else ""

        line = f"- **{name}** {price_text} {rating_text}"
        if location_text:
            line += f" {location_text}"
        if url:
            line += f" [查看详情]({url})"
        lines.append(line)

    return "\n".join(lines)


def _inject_hotels(itinerary: str, accommodation_area: str, hotel_block: str) -> str:
    """将酒店推荐注入到行程的住宿建议后面。"""
    # 先清理残留的注入内容（酒店+交通），避免重复
    itinerary = _strip_injected_blocks(itinerary)

    # 查找"住宿建议"所在行
    lines = itinerary.split('\n')
    new_lines = []
    injected = False

    for line in lines:
        new_lines.append(line)
        # 在"住宿建议"后面插入酒店推荐
        if '住宿建议' in line and not injected:
            new_lines.append('')
            new_lines.append(hotel_block)
            injected = True

    # 如果没有找到"住宿建议"，在行程开头插入
    if not injected:
        new_lines.insert(0, hotel_block + '\n')

    return '\n'.join(new_lines)


def plan_transport(state: AgentState) -> dict:
    """节点 4：按 plan 的景点序列查高德，生成真实交通并注入行程正文。

    Returns:
        {
            "transit": {
                "source": "amap" | "none",
                "transport_mode": str,
                "transport_reason": str,
                "inter_city": {                   # 城际交通（无出发地时为 null）
                    "from": str, "to": str,
                    "mode": str, "summary": str,
                    "duration_min": int, "distance_m": int,
                    "polyline": [[lng, lat], ...],
                } | null,
                "days": [                         # 逐天市内交通
                    {
                        "day": int,
                        "legs": [{
                            "from": {"name": str, "lng": float, "lat": float},
                            "to":   {"name": str, "lng": float, "lat": float},
                            "mode": str, "summary": str,
                            "duration_min": int, "distance_m": int,
                            "polyline": [[lng, lat], ...],
                        }]
                    }
                ]
            },
            "itinerary": str   # 注入交通段落后的完整行程 markdown
        }
    """
    prefs = state.get("preferences", {})
    days = state.get("plan_days", []) or []
    destination = (prefs.get("destination") or "").strip()
    departure = (prefs.get("departure") or "").strip()
    itinerary = state.get("itinerary", "") or ""
    transport_mode = state.get("transport_mode", "") or ""
    transport_reason = state.get("transport_reason", "") or ""

    # 未配置 key / 无目的地 / 无景点序列：直接透传空交通
    if not amap.enabled() or not destination or not days:
        logger.warning(
            "plan_transport: 跳过交通规划 — amap.enabled=%s, destination='%s', days=%d",
            amap.enabled(), destination, len(days),
        )
        return {"transit": {"source": "none", "inter_city": None, "days": []}}

    logger.info("plan_transport: 开始 — destination='%s', departure='%s', days=%d, transport_mode=%s",
                destination, departure, len(days), transport_mode)

    # 检测国外目的地：高德地图只支持中国境内
    # 国外目的地跳过所有高德路线规划，只给文字提示
    foreign_cities = {"东京", "大阪", "巴黎", "伦敦", "纽约", "首尔", "曼谷", "新加坡", "悉尼", "迪拜", "罗马", "巴塞罗那", "洛杉矶", "旧金山", "温哥华", "墨尔本", "吉隆坡", "马尔代夫", "普吉岛", "巴厘岛"}
    is_foreign_dest = destination in foreign_cities
    is_foreign_dep = departure in foreign_cities

    # 1. 城际交通（出发地 ≠ 目的地且都非空）
    inter_city = None
    if departure and departure != destination:
        # 如果出发地或目的地是国外，跳过高德路线规划
        if is_foreign_dest or is_foreign_dep:
            logger.info("plan_transport: 出发地或目的地为国外，跳过高德城际路线规划")
            # 根据 LLM 建议的交通方式给出文字提示
            mode_name = {"driving": "驾车", "train": "高铁/火车", "flight": "飞机"}.get(transport_mode, "飞机")
            inter_city = {
                "from": departure,
                "to": destination,
                "transport_mode": transport_mode,
                "transport_reason": transport_reason,
                "mode": mode_name,
                "summary": f"建议乘坐{mode_name}从 {departure} 到 {destination}",
                "duration_min": 0,
                "distance_m": 0,
                "polyline": [],
            }
        else:
            dep_geo = amap.geocode(departure)
            dst_geo = amap.geocode(destination)
            if dep_geo and dst_geo:
                # 根据 LLM 建议的交通方式选择路线查询
                if transport_mode == "train":
                    # 高铁：查铁路路线
                    r = amap.railway_route(dep_geo["lnglat"], dst_geo["lnglat"], departure, destination)
                    if r is None:
                        # 查不到铁路，降级为驾车
                        r = amap.driving_route(dep_geo["lnglat"], dst_geo["lnglat"])
                elif transport_mode == "flight":
                    # 飞机：高德不支持航班查询，给文字提示
                    r = {
                        "mode": "飞机",
                        "summary": f"建议乘坐飞机从 {departure} 到 {destination}",
                        "duration_min": 0,
                        "distance_m": 0,
                        "polyline": [],
                    }
                else:
                    # 驾车（默认）
                    r = amap.driving_route(dep_geo["lnglat"], dst_geo["lnglat"])
                if r:
                    inter_city = {
                        "from": departure,
                        "to": destination,
                        "transport_mode": transport_mode,
                        "transport_reason": transport_reason,
                        **r,
                    }

    # 2. 逐天逐站查交通（任何一天有景点编码失败 → 整体不返回交通）
    transit_days = []
    all_errors = []
    for d in days:
        # 防御性检查：确保 d 是 dict 格式
        if not isinstance(d, dict):
            logger.warning("plan_transport: days 中有非 dict 元素，跳过 — type=%s, value=%s", type(d).__name__, d)
            continue
        try:
            day_no = int(d.get("day", 1))
        except (TypeError, ValueError):
            continue
        legs, err = _build_legs(d.get("spots") or [], destination)
        if err:
            all_errors.append(f"Day {day_no}：{err}")
        if legs:
            transit_days.append({"day": day_no, "legs": legs})

    # 有任何一天的景点编码失败 → 整体不返回交通，告知前端原因
    if all_errors:
        error_summary = "；".join(all_errors)
        logger.warning("plan_transport: 存在地理编码失败，跳过整个交通规划 — %s", error_summary)
        empty_transit = {"source": "none", "transport_mode": transport_mode, "transport_reason": transport_reason, "inter_city": None, "days": []}
        return {"transit": empty_transit, "transit_error": error_summary, "itinerary": itinerary}

    transit = {
        "source": "amap" if (transit_days or inter_city) else "none",
        "transport_mode": transport_mode,
        "transport_reason": transport_reason,
        "inter_city": inter_city,
        "days": transit_days,
    }

    # 汇总日志
    total_legs = sum(len(d.get("legs", [])) for d in transit_days)
    total_polylines = sum(
        1 for d in transit_days for leg in d.get("legs", []) if leg.get("polyline")
    )
    logger.info(
        "plan_transport: 完成 — source=%s, 城际=%s, 天数=%d, 总路段=%d, 有polyline=%d",
        transit["source"],
        "有" if inter_city else "无",
        len(transit_days),
        total_legs,
        total_polylines,
    )
    if total_legs > 0 and total_polylines == 0:
        logger.error("plan_transport: ⚠️ 有路段但无 polyline！地图将无法画线")

    return {"transit": transit, "itinerary": _inject_transit(itinerary, transit)}


def _build_legs(spots: list, city: str) -> tuple[list[dict], str]:
    """对一串景点相邻两两查高德，生成市内交通。

    逻辑：
    - 距离 < 2km → 步行
    - 否则 → 对比驾车和地铁耗时，选耗时短的

    Returns:
        (legs, error) — legs 为路段列表，error 为失败原因（空串=成功）。
        任何景点地理编码失败时，error 非空，legs 为空列表（不返回不完整的交通）。
    """
    # 检测国外目的地：高德地图地理编码 API 只支持中国境内地名
    # 对于国外地名（如日本大阪），高德会错误返回中国境内坐标，导致路线画在中国
    # 因此检测到国外目的地时，直接跳过，给出文字提示
    foreign_cities = {"东京", "大阪", "巴黎", "伦敦", "纽约", "首尔", "曼谷", "新加坡", "悉尼", "迪拜", "罗马", "巴塞罗那", "洛杉矶", "旧金山", "温哥华", "墨尔本", "吉隆坡", "马尔代夫", "普吉岛", "巴厘岛"}
    if city in foreign_cities:
        logger.info("_build_legs: 检测到国外目的地 '%s'，跳过高德地理编码", city)
        return [], f"国外目的地（{city}）暂不支持高德地图路线规划"

    # 1. 批量地理编码
    coords: dict[str, dict] = {}
    for name in spots:
        name = (name or "").strip()
        if not name:
            continue
        geo = amap.geocode(f"{city}{name}", city)
        if geo:
            coords[name] = geo
        else:
            logger.warning("地理编码失败：%s%s → 无结果", city, name)

    # 诊断：哪些景点没编码成功
    names = [n.strip() for n in spots if (n or "").strip()]
    missing = [n for n in names if n not in coords]
    if missing:
        error_msg = f"以下景点无法在高德地图定位：{'、'.join(missing)}，无法生成交通路线"
        logger.warning("_build_legs: %s", error_msg)
        return [], error_msg
    if not coords:
        error_msg = "所有景点均无法在高德地图定位，无法生成交通路线"
        logger.error("_build_legs: %s", error_msg)
        return [], error_msg

    # 2. 逐段查交通
    legs = []
    for i in range(len(names) - 1):
        a, b = names[i], names[i + 1]
        ga, gb = coords.get(a), coords.get(b)
        if not ga or not gb:
            logger.warning("跳过路段 %s → %s：坐标缺失（ga=%s, gb=%s）", a, b, bool(ga), bool(gb))
            continue

        # 先查驾车，获取距离
        driving = amap.driving_route(ga["lnglat"], gb["lnglat"])
        distance = driving.get("distance_m", 0) if driving else 0

        # 距离 < 2km → 步行
        if distance < 2000:
            r = amap.walking_route(ga["lnglat"], gb["lnglat"])
            if r is None:
                logger.warning("路段 %s → %s：步行路线查询失败", a, b)
                continue
        else:
            # 对比驾车和地铁耗时
            metro = amap.metro_route(ga["lnglat"], gb["lnglat"], city)
            driving_time = driving.get("duration_min", 999) if driving else 999
            metro_time = metro.get("duration_min", 999) if metro else 999

            if metro and metro_time <= driving_time:
                r = metro
            elif driving:
                r = driving
            else:
                logger.warning("路段 %s → %s：驾车和地铁均查询失败", a, b)
                continue

        # 校验返回数据完整性
        polyline = r.get("polyline")
        if not polyline or not isinstance(polyline, list) or len(polyline) == 0:
            logger.error("路段 %s → %s：%s 返回的 polyline 为空或无效，mode=%s", a, b, r.get("mode"), r.get("mode"))

        legs.append({
            "from": {"name": a, "lng": ga["lng"], "lat": ga["lat"]},
            "to": {"name": b, "lng": gb["lng"], "lat": gb["lat"]},
            **r,
        })

    logger.info("_build_legs: %s 市内共生成 %d/%d 路段", city, len(legs), len(names) - 1)
    return legs, ""


def _format_leg_line(leg: dict) -> str:
    """格式化单条交通路线，用 emoji 区分交通方式。"""
    summary = leg.get("summary", "")
    duration = leg.get("duration_min", 0)
    distance = leg.get("distance_m", 0)
    mode = leg.get("mode", "")

    # 根据 summary 或 mode 判断交通方式并选择 emoji
    if "步行" in summary or mode == "walking":
        emoji = "🚶‍"
        # 从 summary 提取距离信息
        dist_text = f"{distance // 1000}km" if distance >= 1000 else f"{distance}m"
        return f"{emoji} 步行 {dist_text} · {duration}分钟"
    elif "地铁" in summary or "轨" in summary or mode == "metro":
        emoji = "🚇"
        return f"{emoji} 地铁 · {duration}分钟"
    elif "驾车" in summary or "打车" in summary or mode == "driving":
        emoji = "🚗"
        dist_text = f"{distance // 1000}km" if distance >= 1000 else f"{distance}m"
        return f"{emoji} 驾车 {dist_text} · {duration}分钟"
    else:
        emoji = "🚌"
        return f"{emoji} {summary} · {duration}分钟"


def _strip_injected_blocks(itinerary: str) -> str:
    """剥离行程中所有代码注入的内容（酒店推荐 + 交通信息），返回干净的 LLM 原始行程。

    二次对话时 previous_itinerary 已包含注入内容，LLM 可能原样保留，
    再叠加新一轮注入就会重复。本函数在两个时机调用：
    1. generate_itinerary 传给 LLM 前（让 LLM 只看到干净行程）
    2. _inject_hotels / _inject_transit 注入前（清除残留，避免重复）

    清理目标：
    - 酒店推荐块：**🏨 推荐酒店** 标题 + 下方 `- **酒店名**` 列表项
    - 城际交通块：**🚗 城际交通** 标题 + 下方列表项（含 💡 提示行）
    - 市内交通行：🚶 步行 / 🚇 地铁 / 🚗 驾车 / 🚌 公交 等交通段落
    """
    import re
    lines = itinerary.split('\n')
    cleaned = []
    skip_block = False  # 跳过城际交通/酒店推荐的多行块

    for line in lines:
        stripped = line.strip()

        # ── 城际交通标题行：**🚗/🚄/✈️ 城际交通（...）** ──
        if re.match(r'\*\*[🚗🚄✈️🚌]\s*城际交通', stripped):
            skip_block = True
            continue

        # ── 酒店推荐标题行：**🏨 推荐酒店** ──
        if re.match(r'\*\*🏨\s*推荐酒店', stripped):
            skip_block = True
            continue

        # ── 多行块内的内容（城际交通/酒店推荐的列表项和空行） ──
        if skip_block:
            if stripped == '' or stripped.startswith('- '):
                continue  # 空行或列表项，继续跳过
            else:
                skip_block = False  # 遇到非空非列表行，结束跳过

        # ── 市内交通行：以交通 emoji 开头的行 ──
        # 匹配：🚶 步行 365m · 5分钟 / 🚇 地铁 · 15分钟 / 🚗 驾车 3km · 10分钟
        if re.match(r'-?\s*[🚶🚇🚗🚌]\s*(步行|地铁|驾车|公交)', stripped):
            continue

        cleaned.append(line)

    return '\n'.join(cleaned)


def _inject_transit(itinerary: str, transit: dict) -> str:
    """把城际出发 + 每天交通注入正文，交通信息穿插在景点之间。

    格式示例：
        - 🏛️ 苏州博物馆（2小时）
        - 🚶 步行 0.9km · 11分钟
        - 🏘️ 平江路历史街区（1.5小时）
        - 🚇 地铁 · 15分钟
        - 🌙 山塘街（晚餐+夜游）
    """
    if not itinerary:
        return itinerary

    # 先清理残留的注入内容（酒店+交通），避免重复
    itinerary = _strip_injected_blocks(itinerary)

    # 预处理每天的交通 legs
    day_legs: dict[int, list] = {}
    for d in transit.get("days") or []:
        legs = d.get("legs") or []
        if legs:
            try:
                day_legs[int(d.get("day", 0))] = legs
            except (TypeError, ValueError):
                continue

    out: list[str] = []

    # 1. 城际交通（放在最前面）
    inter = transit.get("inter_city")
    if inter:
        mode = inter.get("transport_mode", "")
        mode_emoji = {"driving": "🚗", "train": "🚄", "flight": "✈️"}.get(mode, "🚗")
        mode_name = {"driving": "驾车", "train": "高铁/火车", "flight": "飞机"}.get(mode, "驾车")
        transport_reason = inter.get("transport_reason", "")
        reason_line = f"\n- 💡 {transport_reason}" if transport_reason else ""
        out.append(
            f"**{mode_emoji} 城际交通（{mode_name}）**\n"
            f"- 从 {inter.get('from', '')} 到 {inter.get('to', '')}：{inter.get('summary', '')}{reason_line}\n\n"
        )

    # 2. 按 Day 分割行程，注入每日交通
    if day_legs:
        segs = re.split(r"(?m)(?=^##\s*Day\s*\d+)", itinerary)
        for i, seg in enumerate(segs):
            m = re.match(r"##\s*Day\s*(\d+)", seg.strip())
            if m:
                day_no = int(m.group(1))
                legs = day_legs.get(day_no, [])
                if legs:
                    # 将交通信息插入到景点之间
                    lines = seg.split("\n")
                    new_lines = []
                    leg_idx = 0
                    for line in lines:
                        new_lines.append(line)
                        # 检查当前行是否包含景点名（from 景点）
                        if leg_idx < len(legs):
                            from_name = legs[leg_idx].get("from", {}).get("name", "")
                            if from_name and from_name in line:
                                # 在景点后面插入交通信息
                                transit_line = _format_leg_line(legs[leg_idx])
                                new_lines.append(transit_line)
                                leg_idx += 1
                    out.append("\n".join(new_lines))
                else:
                    out.append(seg)
            else:
                out.append(seg)
            # 确保 Day 之间有换行分隔
            if i < len(segs) - 1:
                out.append("\n\n")
        return "".join(out)

    # 没有每日交通，只有城际时直接前缀
    return "".join(out) + itinerary
