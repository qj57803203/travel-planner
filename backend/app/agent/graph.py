"""组装 LangGraph 编排：抽取 → 搜集 → 生成 → 交通。"""
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import extract_preferences, generate_itinerary, plan_transport, research
from app.agent.state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("extract", extract_preferences)
    g.add_node("research", research)
    g.add_node("plan", generate_itinerary)
    g.add_node("transport", plan_transport)

    g.add_edge(START, "extract")
    g.add_edge("extract", "research")
    g.add_edge("research", "plan")
    g.add_edge("plan", "transport")
    g.add_edge("transport", END)

    return g.compile()


agent_graph = build_graph()
