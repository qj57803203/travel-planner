"""接口入参 / 出参的 Pydantic 模型。"""
import re
from typing import Any, Annotated, Optional

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    user_input: str = Field(..., description="自然语言旅行需求，如「9 月去东京玩 5 天，不想太累」")
    trip_id: int | None = Field(None, description="修改模式：传入要修改的行程 ID，会在上一轮基础上修改")


class Preference(BaseModel):
    destination: str = ""
    days: int = 1
    pace: str = "适中"
    interests: list[str] = []
    hotel_preference: list[str] = []
    departure: str = ""   # 出发城市（可空，用于城际交通）


class Hotel(BaseModel):
    name: str
    price: float = 0
    rating: float = 0
    location: str = ""
    image: str = ""
    url: str = ""
    pros: list[str] = []
    cons: list[str] = []

    @field_validator("price", "rating", mode="before")
    @classmethod
    def parse_numeric(cls, v: Any) -> float:
        """兼容价格/评分为字符串的情况，如 '约 1500 元/晚' → 1500.0。"""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            m = re.search(r"[\d.]+", v)
            if m:
                return float(m.group())
        return 0.0


class Attraction(BaseModel):
    name: str
    area: str = ""
    note: str = ""
    tips: str = ""


class Food(BaseModel):
    name: str
    category: str = ""
    note: str = ""


class Transport(BaseModel):
    mode: str
    detail: str = ""


class XhsNote(BaseModel):
    title: str
    url: str = ""
    summary: str = ""
    cover: str = ""


class ResearchInfo(BaseModel):
    destination: str = ""
    hotels: list[Hotel] = []
    attractions: list[Attraction] = []
    food: list[Food] = []
    transport: list[Transport] = []
    xhs_notes: list[XhsNote] = []
    xhs_status: str = ""   # live / cached / fallback；空 = 未启用小红书
    xhs_error: str = ""    # 失败原因，供前端透出


class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色：user 或 assistant")
    content: str = Field("", description="消息内容")


class TripResponse(BaseModel):
    id: int
    user_input: str
    preferences: Preference
    research: ResearchInfo
    itinerary: str
    created_at: str
    usage: dict = {}   # 各 LLM 节点的 token 用量（extract/plan 的 input+output）
    transit: dict = {}  # 高德交通结果（结构化：source/inter_city/days，字段见 nodes.plan_transport）
    transit_error: str = ""  # 交通规划失败原因（非空时前端展示提示）
    hotels: list[Hotel] = []  # 携程酒店搜索结果
    chat_history: list[ChatMessage] = []  # 多轮对话历史
    parent_id: int | None = None           # 关联原始行程 ID（修改链头）


class ProfileUpdate(BaseModel):
    departure: str = ""


class ProfileResponse(BaseModel):
    departure: str = ""


class TripSummary(BaseModel):
    id: int
    destination: str
    days: int
    created_at: str
