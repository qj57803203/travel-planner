"""LangGraph 的状态定义。

节点间共享数据的唯一通道；节点函数签名 (state: AgentState) -> dict，
返回的 dict 会 merge 进 state 供下游节点读取。

数据流：START -> extract -> research -> plan -> transport -> END
"""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ── 入口 ──
    user_input: str          # 原始自然语言需求（入口传入）
    profile_departure: str   # 从用户配置读取的出发地（供 extract 兜底）

    # ── 多轮对话（修改模式） ──
    chat_history: list       # 对话历史 [{"role": "user"|"assistant", "content": str}, ...]
    previous_itinerary: str  # 上一轮行程 markdown（供 plan 节点参考修改）
    is_modification: bool    # True = 修改模式，False = 首次生成

    # ── extract 节点输出 ──
    preferences: dict        # 结构化偏好
    #   {
    #     "destination": str, "days": int, "pace": str,
    #     "interests": [str], "hotel_preference": [str], "departure": str
    #   }

    # ── research 节点输出 ──
    research: dict           # 搜集到的信息素材
    #   {
    #     "destination": str,
    #     "hotels": [...], "attractions": [...], "food": [...], "transport": [...],
    #     "xhs_notes": [{"title": str, "url": str, "summary": str, "cover": str}],
    #     "xhs_status": "live" | "cached" | "fallback" | "",
    #     "xhs_error": str,
    #   }

    # ── plan 节点输出 ──
    itinerary: str           # 行程 markdown 正文（含 ## Day 1 等标题）
    plan_days: list          # 每天景点序列，供 transport 节点查交通
    #   [{"day": 1, "spots": ["景点A", "景点B"]}, ...]
    transport_mode: str      # LLM 建议的城际交通方式："driving" | "train" | "flight" | ""
    transport_reason: str    # 交通方式选择理由
    accommodation_area: str  # 住宿区域建议，如"地铁1号线/4号线沿线（如乐桥站附近）"

    # ── hotel_search 节点输出 ──
    hotels: list             # 携程酒店搜索结果
    #   [{"name": str, "price": float, "rating": float, "image": str, "url": str, "location": str}]

    # ── transport 节点输出 ──
    transit: dict            # 高德交通结果（结构化，供前端地图 + 文本注入）
    #   {"source": "amap"|"none", "inter_city": {...}|null, "days": [{"day":1,"legs":[...]}]}
    transit_error: str       # 交通规划失败原因（非空时前端展示提示，transit 为空）

    # ── 全局 ──
    error: str               # 出错信息（可选，兜底时写入）
    usage: dict              # 各 LLM 节点 token 用量
    #   {"extract": {"input": int, "output": int}, "plan": {"input": int, "output": int}}
