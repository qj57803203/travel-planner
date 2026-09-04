"""数据库 ORM 模型。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Trip(Base):
    """一次行程记录。

    preferences / research / transit 为 JSON 列，结构与 AgentState 同名字段一致：
    - preferences: {"destination", "days", "pace", "interests", "hotel_preference", "departure"}
    - research:    {"destination", "hotels", "attractions", "food", "transport", "xhs_notes", "xhs_status", "xhs_error"}
    - transit:     {"source", "transport_mode", "transport_reason", "inter_city", "days"}
    - usage:       {"extract": {"input", "output"}, "plan": {"input", "output"}}
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    research: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    itinerary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    transit: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    hotels: Mapped[list | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    """单行用户配置：记住出发地等个人偏好，供后续生成默认复用。"""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    departure_city: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class XhsNoteCache(Base):
    """小红书笔记缓存：按目的地存一周内的攻略笔记，问类似问题时直接复用。"""

    __tablename__ = "xhs_note_cache"
    __table_args__ = (UniqueConstraint("destination", "url", name="uq_xhs_dest_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    destination: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    cover: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CtripCityCache(Base):
    """携程城市 ID 缓存：城市名→数字ID 映射（如"上海"→2），基本不变，长期缓存。"""

    __tablename__ = "ctrip_city_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    city_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CtripHotelCache(Base):
    """携程酒店缓存：按目的地+关键词存一周内的酒店搜索结果，避免重复爬取。"""

    __tablename__ = "ctrip_hotel_cache"
    __table_args__ = (UniqueConstraint("destination", "keyword", "hotel_name", name="uq_ctrip_dest_keyword_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    destination: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    hotel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Integer, default=0)
    rating: Mapped[float] = mapped_column(Integer, default=0)
    location: Mapped[str] = mapped_column(String(255), default="")
    image: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
