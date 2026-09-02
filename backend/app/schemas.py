"""接口入参 / 出参的 Pydantic 模型。"""
from typing import Any, Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    user_input: str = Field(..., description="自然语言旅行需求，如「9 月去东京玩 5 天，不想太累」")


class Preference(BaseModel):
    destination: str = ""
    days: int = 1
    pace: str = "适中"
    interests: list[str] = []
    hotel_preference: list[str] = []


class Hotel(BaseModel):
    name: str
    price: str = ""
    rating: str = ""
    location: str = ""
    pros: list[str] = []
    cons: list[str] = []


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


class TripResponse(BaseModel):
    id: int
    user_input: str
    preferences: Preference
    research: ResearchInfo
    itinerary: str
    created_at: str


class TripSummary(BaseModel):
    id: int
    destination: str
    days: int
    created_at: str
