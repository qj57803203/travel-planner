"""LangGraph 的状态定义。"""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    user_input: str          # 原始自然语言需求
    preferences: dict        # 抽取出的结构化偏好
    research: dict           # 搜集到的四类信息素材
    itinerary: str           # 生成的每日行程
    error: str               # 出错信息
    usage: dict              # 各 LLM 节点 token 用量 {"extract": {...}, "plan": {...}}
