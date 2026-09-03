"""LangGraph 的三个节点：抽取偏好 → 搜集信息 → 生成行程。"""
import json
import logging
import re
from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek

from app.agent.prompts import EXTRACT_PROMPT, PLAN_PROMPT
from app.agent.state import AgentState
from app.config import settings
from app.data.destinations import 兜底数据
from app.database import SessionLocal
from app.models import XhsNoteCache
from app.tools import amap, xhs_mcp

DEFAULT_PREFERENCES = {
    "destination": "",
    "days": 3,
    "pace": "适中",
    "interests": [],
    "hotel_preference": [],
    "departure": "",
}

logger = logging.getLogger(__name__)


def _get_llm(temperature: float = 0.0) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        temperature=temperature,
    )


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


def _clean_json_text(text: str) -> str:
    """清理 LLM 输出中的 JSON 文本，修正常见格式瑕疵。

    LLM 理想输出：合法 JSON 字符串，如 `{"key": "value"}`。
    实际常遇到的问题：
    - 字符串值内含裸换行/制表符（json.loads 不认，需转义为 \\n \\t）
    - JSON 末尾多写逗号 trailing comma，如 `{"a": 1,}`（json.loads 不认）
    - LLM 用 Python 单引号格式 `{'key': 'value'}` 而非 JSON 双引号（DeepSeek 常见）
    """
    # 处理单引号格式：{'key': 'value'} → {"key": "value"}
    # 只在开头是 { 且包含单引号时尝试转换（用 ast.literal_eval 安全解析 Python 字面量）
    if text.startswith("{") and "'" in text:
        try:
            import ast
            text = str(ast.literal_eval(text))
        except Exception:
            pass  # 转换失败则继续用原文，让后续策略处理
    text = text.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    text = re.sub(r",\s*([}\]])", r"\1", text)  # trailing comma
    return text


def _parse_json(text: str) -> dict:
    """稳健地解析 LLM 输出中的 JSON，按优先级尝试多种策略。

    ────────────────────────────────────────────────────────────
    LLM 理想输出（PLAN_PROMPT / EXTRACT_PROMPT 都明确要求）：

        {"destination": "东京", "days": 5, ...}

    即：一个合法 JSON **对象**，无任何前后缀、无代码块包裹。

    ────────────────────────────────────────────────────────────
    LLM 实际常犯的问题（按本函数策略依次兜底）：

    问题 A — 用 markdown 代码块包裹：
        ```json
        {"destination": "东京", ...}
        ```
      → 策略 1：strip 首尾 ``` 标记后直接解析。

    问题 B — 代码块中间夹杂说明文字，首尾 ``` 不在字符串首尾：
        以下是抽取结果：
        ```json
        {"destination": "东京", ...}
        ```
        以上是抽取结果。
      → 策略 2：正则搜索 ```...``` 代码块，提取块内内容解析。

    问题 C — 无代码块，但 JSON 前后有多余说明文字：
        好的，以下是结构化偏好：{"destination": "东京", ...} 以上就是。
      → 策略 3：找第一个 { 和最后一个 }，截取中间内容解析。

    问题 D — LLM 返回的是 JSON 数组而非对象：
        [{"destination": "东京", ...}]
      → 解析成功后校验类型；若为 list 且首元素是 dict，自动取第一个元素。

    ────────────────────────────────────────────────────────────

    Returns:
        解析后的 dict。所有策略均失败时抛出 ValueError（由调用方决定 fallback）。
    """
    if not isinstance(text, str):
        raise TypeError(f"期望 str，实际收到 {type(text).__name__}")

    text = text.strip()

    # ── 策略 1：去除首尾 ``` 标记后直接解析（问题 A）──
    cleaned = re.sub(r"^```(?:json)?\s*", "", text)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        result = json.loads(_clean_json_text(cleaned))
        logger.debug("_parse_json: 策略 1 解析结果 type=%s", type(result).__name__)
        result = _ensure_dict(result, "策略 1（首尾去 ```）")
        return result
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.debug("_parse_json: 策略 1 失败 — %s", e)

    # ── 策略 2：正则提取 ```...``` 代码块内容（问题 B）──
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if m:
        try:
            result = json.loads(_clean_json_text(m.group(1).strip()))
            logger.debug("_parse_json: 策略 2 解析结果 type=%s", type(result).__name__)
            result = _ensure_dict(result, "策略 2（正则提取代码块）")
            return result
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug("_parse_json: 策略 2 失败 — %s", e)
    else:
        logger.debug("_parse_json: 策略 2 跳过（未找到 ```...``` 代码块）")

    # ── 策略 3：手动匹配最外层 { }（问题 C）──
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(_clean_json_text(text[start : end + 1]))
            logger.debug("_parse_json: 策略 3 解析结果 type=%s", type(result).__name__)
            result = _ensure_dict(result, "策略 3（匹配最外层 {}）")
            return result
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug("_parse_json: 策略 3 失败 — %s", e)
    else:
        logger.debug("_parse_json: 策略 3 跳过（未找到 { }）")

    # 所有策略均失败
    logger.error(
        "_parse_json: 所有策略均失败，无法解析 LLM 输出（前 200 字符）：\n%s",
        text[:200],
    )
    raise ValueError("无法从 LLM 输出中提取有效 JSON")


def _ensure_dict(result, strategy_name: str) -> dict:
    """校验 JSON 解析结果必须是 dict；若为 list 且首元素是 dict 则自动取第一个。

    LLM 有时把对象包在数组里返回，如 [{"destination": "东京", ...}]。
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, list) and result and isinstance(result[0], dict):
        logger.warning(
            "_parse_json: %s 解析结果是 list[%d]，取第一个元素（LLM 返回了数组而非对象）",
            strategy_name, len(result),
        )
        return result[0]
    logger.error(
        "_parse_json: %s 解析结果类型异常 — %s（期望 dict）",
        strategy_name, type(result).__name__,
    )
    raise TypeError(f"JSON 解析结果是 {type(result).__name__}，期望 dict")


def _stream_writer():
    """返回 LangGraph 的 stream writer；不可用（非流式调用 / 版本不支持）时返回 None。"""
    try:
        from langgraph.config import get_stream_writer
        return get_stream_writer()
    except Exception:  # noqa: BLE001 — 非流式场景下无 writer，静默降级
        return None


def _emit_xhs_note(writer, index: int, note: dict) -> None:
    """把小红书单篇采集进度推给前端（writer 为 None 时跳过）。"""
    if writer is not None:
        writer({"type": "xhs_note", "index": index, **note})


def extract_preferences(state: AgentState) -> dict:
    """节点 1：从自然语言需求抽取结构化偏好。

    Returns:
        {
            "preferences": {
                "destination": str,   # 目的地
                "days": int,          # 旅行天数
                "pace": str,          # 节奏："轻松" / "适中" / "紧凑"
                "interests": [str],   # 兴趣列表，如 ["美食", "拍照"]
                "hotel_preference": [str],  # 酒店偏好
                "departure": str,     # 出发城市（可空）
            },
            "usage": {"extract": {"input": int, "output": int}}
        }
    """
    try:
        llm = _get_llm(temperature=0.0)
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
    except Exception as e:  # 抽取失败时用默认值兜底，让流程继续
        return {"preferences": DEFAULT_PREFERENCES.copy(), "error": f"偏好抽取失败: {e}"}


def research(state: AgentState) -> dict:
    """节点 2：搜集信息素材 —— 预置结构化数据（兜底）+ 小红书攻略笔记（优先）。

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

    # 1. 匹配预置的四类结构化数据（小红书不可用时的兜底，也作为补充）
    data = 兜底数据.get(dest)
    if data is None:
        # 模糊匹配：目的地名互为包含关系
        for key, value in 兜底数据.items():
            if key in dest or dest in key:
                dest, data = key, value
                break

    research_info = {
        "destination": dest,
        "hotels": (data or {}).get("hotels", []),
        "attractions": (data or {}).get("attractions", []),
        "food": (data or {}).get("food", []),
        "transport": (data or {}).get("transport", []),
        "xhs_notes": [],
        "xhs_status": "",   # live / cached / fallback；空 = 未启用小红书
        "xhs_error": "",    # 失败原因（如 ConnectError: ...），供前端透出
    }

    # 2. 小红书笔记 —— 先查一周内目的地缓存，命中秒回；未命中才实时爬取并写缓存
    if xhs_mcp.enabled() and dest:
        cached = _load_xhs_cache(dest)
        if cached:
            research_info["xhs_notes"] = cached
            research_info["xhs_status"] = "cached"
        else:
            interests = " ".join((prefs.get("interests") or [])[:2])
            query = f"{dest} 旅游攻略{' ' + interests if interests else ''}"
            writer = _stream_writer()
            notes, err = xhs_mcp.collect_xhs_sources_sync(
                query,
                on_note=lambda i, note: _emit_xhs_note(writer, i, note),
            )
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
        return [
            {"title": r.title, "url": r.url, "summary": r.summary, "cover": r.cover}
            for r in rows
        ]
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


def generate_itinerary(state: AgentState) -> dict:
    """节点 3：根据偏好 + 信息素材 + 小红书笔记生成每日行程。

    LLM 返回 JSON（见 PLAN_PROMPT），经 _parse_plan 解析后拆成四段。

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
    llm = _get_llm(temperature=0.7)
    # 结构化素材单独给，小红书笔记单独一段，避免重复
    structured = {k: v for k, v in research.items() if k != "xhs_notes"}
    prompt = PLAN_PROMPT.format(
        pace=prefs.get("pace", "适中"),
        interests="、".join(prefs.get("interests", [])) or "无特殊偏好",
        preferences=json.dumps(prefs, ensure_ascii=False, indent=2),
        research=json.dumps(structured, ensure_ascii=False, indent=2),
        xhs_notes=_format_xhs_notes(research.get("xhs_notes", [])),
    )
    try:
        resp = llm.invoke(prompt)
        usage = _usage(resp)
        logger.info("plan 消耗 token：input=%s output=%s", usage["input"], usage["output"])
        usage_map = state.get("usage", {})
        usage_map["plan"] = usage
        markdown, days, transport_mode, transport_reason = _parse_plan(resp.content)
        return {
            "itinerary": markdown,
            "plan_days": days,
            "transport_mode": transport_mode,
            "transport_reason": transport_reason,
            "usage": usage_map,
        }
    except Exception as e:
        return {"itinerary": "", "error": f"行程生成失败: {e}"}


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
        (markdown, days, transport_mode, transport_reason)
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
                "_parse_plan: 解析成功 — markdown=%d字符, days=%d天, transport=%s",
                len(markdown), len(days), transport_mode or "无",
            )
            return (
                markdown,
                days if isinstance(days, list) else [],
                transport_mode,
                transport_reason,
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
                return markdown, [], "", ""
        except Exception as e:  # noqa: BLE001
            logger.warning("_parse_plan: 正则挽救后 json.loads 失败 — %s", e)

    # ── 第 3 步：完全失败，返回原始内容 ──
    logger.error(
        "_parse_plan: 所有策略均失败，返回原始内容作为 itinerary（长度=%d，前 200 字符）：\n%s",
        len(content), content[:200],
    )
    return content, [], "", ""


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
        return {"transit": {"source": "none", "inter_city": None, "days": []}}

    # 1. 城际交通（出发地 ≠ 目的地且都非空）
    inter_city = None
    if departure and departure != destination:
        dep_geo = amap.geocode(departure)
        dst_geo = amap.geocode(destination)
        if dep_geo and dst_geo:
            # 根据 LLM 建议的交通方式选择路线查询
            if transport_mode == "train":
                # 高铁：用公交 API（包含铁路段）
                # 注意：city 是起点城市，cityd 是终点城市
                r = amap.transit_route(dep_geo["lnglat"], dst_geo["lnglat"], departure, destination)
                if r is None:
                    # 公交 API 查不到铁路，降级为驾车
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

    # 2. 逐天逐站查交通
    transit_days = []
    for d in days:
        try:
            day_no = int(d.get("day", 1))
        except (TypeError, ValueError):
            continue
        legs = _build_legs(d.get("spots") or [], destination)
        if legs:
            transit_days.append({"day": day_no, "legs": legs})

    transit = {
        "source": "amap" if (transit_days or inter_city) else "none",
        "transport_mode": transport_mode,
        "transport_reason": transport_reason,
        "inter_city": inter_city,
        "days": transit_days,
    }

    return {"transit": transit, "itinerary": _inject_transit(itinerary, transit)}


def _build_legs(spots: list, city: str) -> list[dict]:
    """对一串景点相邻两两查高德；geocode 每站一次（run 内缓存），失败段跳过。"""
    coords: dict[str, dict] = {}
    for name in spots:
        name = (name or "").strip()
        if not name:
            continue
        geo = amap.geocode(f"{city}{name}", city)
        if geo:
            coords[name] = geo

    legs = []
    names = [n.strip() for n in spots if (n or "").strip()]
    for i in range(len(names) - 1):
        a, b = names[i], names[i + 1]
        ga, gb = coords.get(a), coords.get(b)
        if not ga or not gb:
            continue
        r = amap.transit_route(ga["lnglat"], gb["lnglat"], city)
        if r is None:
            r = amap.walking_route(ga["lnglat"], gb["lnglat"])
        if r is None:
            continue
        legs.append({
            "from": {"name": a, "lng": ga["lng"], "lat": ga["lat"]},
            "to": {"name": b, "lng": gb["lng"], "lat": gb["lat"]},
            **r,
        })
    return legs


def _inject_transit(itinerary: str, transit: dict) -> str:
    """把城际出发 + 每天交通作为 markdown 块注入正文；解析失败则原样返回。"""
    if not itinerary:
        return itinerary

    day_blocks: dict[int, str] = {}
    for d in transit.get("days") or []:
        legs = d.get("legs") or []
        if not legs:
            continue
        lines = [
            f"- {leg['from']['name']} → {leg['to']['name']}：{leg.get('summary', '')}（约{leg.get('duration_min', 0)}分钟）"
            for leg in legs
        ]
        try:
            day_blocks[int(d.get("day", 0))] = "**🚇 市内交通**\n" + "\n".join(lines)
        except (TypeError, ValueError):
            continue

    out: list[str] = []
    inter = transit.get("inter_city")
    if inter:
        # 根据交通方式选择 emoji
        mode = inter.get("transport_mode", "")
        mode_emoji = {"driving": "🚗", "train": "🚄", "flight": "✈️"}.get(mode, "🚗")
        mode_name = {"driving": "驾车", "train": "高铁/火车", "flight": "飞机"}.get(mode, "驾车")
        transport_reason = inter.get("transport_reason", "")
        reason_line = f"\n- 💡 {transport_reason}" if transport_reason else ""
        out.append(
            f"**{mode_emoji} 城际交通（{mode_name}）**\n- 从 {inter.get('from', '')} 到 {inter.get('to', '')}："
            f"{inter.get('summary', '')}{reason_line}\n\n"
        )

    if day_blocks:
        segs = re.split(r"(?m)(?=^##\s*Day\s*\d+)", itinerary)
        for seg in segs:
            out.append(seg)
            m = re.match(r"##\s*Day\s*(\d+)", seg.strip())
            if m:
                block = day_blocks.get(int(m.group(1)))
                if block:
                    out.append("\n\n" + block)
        return "".join(out)

    # 没有可注入的每日交通，只有城际段时直接前缀
    return "".join(out) + itinerary
