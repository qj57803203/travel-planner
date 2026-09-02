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
from app.data.destinations import DESTINATIONS
from app.database import SessionLocal
from app.models import XhsNoteCache
from app.tools import xhs_mcp

DEFAULT_PREFERENCES = {
    "destination": "",
    "days": 3,
    "pace": "适中",
    "interests": [],
    "hotel_preference": [],
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


def _parse_json(text: str) -> dict:
    """稳健地解析模型输出中的 JSON，容忍 markdown 代码块和多余说明。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


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
    """节点 1：从自然语言需求抽取结构化偏好。"""
    try:
        llm = _get_llm(temperature=0.0)
        chain = ChatPromptTemplate.from_template(EXTRACT_PROMPT) | llm
        resp = chain.invoke({"input": state["user_input"]})
        usage = _usage(resp)
        logger.info("extract 消耗 token：input=%s output=%s", usage["input"], usage["output"])
        data = _parse_json(resp.content)
        prefs = {**DEFAULT_PREFERENCES, **data}
        prefs["days"] = int(prefs.get("days") or 1)
        return {"preferences": prefs, "usage": {"extract": usage}}
    except Exception as e:  # 抽取失败时用默认值兜底，让流程继续
        return {"preferences": DEFAULT_PREFERENCES.copy(), "error": f"偏好抽取失败: {e}"}


def research(state: AgentState) -> dict:
    """节点 2：搜集信息素材 —— 预置结构化数据（兜底）+ 小红书攻略笔记（优先）。"""
    prefs = state.get("preferences", {})
    dest = (prefs.get("destination") or "").strip()

    # 1. 匹配预置的四类结构化数据（小红书不可用时的兜底，也作为补充）
    data = DESTINATIONS.get(dest)
    if data is None:
        # 模糊匹配：目的地名互为包含关系
        for key, value in DESTINATIONS.items():
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
    """节点 3：根据偏好 + 信息素材 + 小红书笔记生成每日行程。"""
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
        return {"itinerary": resp.content, "usage": usage_map}
    except Exception as e:
        return {"itinerary": "", "error": f"行程生成失败: {e}"}
