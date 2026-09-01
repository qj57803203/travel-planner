"""LangGraph 的三个节点：抽取偏好 → 搜集信息 → 生成行程。"""
import json
import re

from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek

from app.agent.prompts import EXTRACT_PROMPT, PLAN_PROMPT
from app.agent.state import AgentState
from app.config import settings
from app.data.destinations import DESTINATIONS

DEFAULT_PREFERENCES = {
    "destination": "",
    "days": 3,
    "pace": "适中",
    "interests": [],
    "hotel_preference": [],
}


def _get_llm(temperature: float = 0.0) -> ChatDeepSeek:
    return ChatDeepSeek(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        temperature=temperature,
    )


def _parse_json(text: str) -> dict:
    """稳健地解析模型输出中的 JSON，容忍 markdown 代码块和多余说明。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def extract_preferences(state: AgentState) -> dict:
    """节点 1：从自然语言需求抽取结构化偏好。"""
    try:
        llm = _get_llm(temperature=0.0)
        chain = ChatPromptTemplate.from_template(EXTRACT_PROMPT) | llm
        resp = chain.invoke({"input": state["user_input"]})
        data = _parse_json(resp.content)
        prefs = {**DEFAULT_PREFERENCES, **data}
        prefs["days"] = int(prefs.get("days") or 1)
        return {"preferences": prefs}
    except Exception as e:  # 抽取失败时用默认值兜底，让流程继续
        return {"preferences": DEFAULT_PREFERENCES.copy(), "error": f"偏好抽取失败: {e}"}


def research(state: AgentState) -> dict:
    """节点 2：根据目的地匹配预置的四类信息素材。"""
    prefs = state.get("preferences", {})
    dest = (prefs.get("destination") or "").strip()

    data = DESTINATIONS.get(dest)
    if data is None:
        # 模糊匹配：目的地名互为包含关系
        for key, value in DESTINATIONS.items():
            if key in dest or dest in key:
                dest, data = key, value
                break

    if data is None:
        return {
            "research": {
                "destination": dest,
                "hotels": [],
                "attractions": [],
                "food": [],
                "transport": [],
            }
        }

    return {"research": {"destination": dest, **data}}


def generate_itinerary(state: AgentState) -> dict:
    """节点 3：根据偏好 + 信息素材生成每日行程。"""
    prefs = state.get("preferences", {})
    research = state.get("research", {})
    llm = _get_llm(temperature=0.7)
    prompt = PLAN_PROMPT.format(
        pace=prefs.get("pace", "适中"),
        interests="、".join(prefs.get("interests", [])) or "无特殊偏好",
        preferences=json.dumps(prefs, ensure_ascii=False, indent=2),
        research=json.dumps(research, ensure_ascii=False, indent=2),
    )
    try:
        resp = llm.invoke(prompt)
        return {"itinerary": resp.content}
    except Exception as e:
        return {"itinerary": "", "error": f"行程生成失败: {e}"}
