"""组装 LangGraph 编排：抽取 → 搜集 → 生成 → 酒店搜索 → 交通。

修改模式下（is_modification=True 且目的地未变），跳过 research 节点直接进 plan。
"""
from langgraph.graph import END, START, StateGraph
import logging
from app.agent.nodes import extract_preferences, generate_itinerary, hotel_search, plan_transport, research
from app.agent.state import AgentState

logger = logging.getLogger(__name__)
def _route_after_extract(state: AgentState) -> str:
    """extract 之后的条件路由：修改模式且目的地未变时跳过 research。"""
    is_mod = state.get("is_modification", False)
    dest_changed = state.get("_destination_changed", False)
    if is_mod and not dest_changed:
        logger.info("_route_after_extract: 跳过 research（修改模式=%s, 目的地变化=%s）", is_mod, dest_changed)
        return "plan"
    logger.info("_route_after_extract: 进入 research（修改模式=%s, 目的地变化=%s）", is_mod, dest_changed)
    return "research"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("extract", extract_preferences)
    g.add_node("research", research)
    g.add_node("plan", generate_itinerary)
    g.add_node("hotel_search", hotel_search)
    g.add_node("transport", plan_transport)

    g.add_edge(START, "extract")
    # 条件分支：修改模式跳过 research
    g.add_conditional_edges("extract", _route_after_extract, {"plan": "plan", "research": "research"})
    g.add_edge("research", "plan")
    g.add_edge("plan", "hotel_search")
    g.add_edge("hotel_search", "transport")
    g.add_edge("transport", END)

    return g.compile()


agent_graph = build_graph()
