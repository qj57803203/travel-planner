"""行程相关接口：生成 / 列表 / 详情。"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.graph import agent_graph
from app.database import get_db
from app.models import Trip, UserProfile
from app.schemas import GenerateRequest, ProfileResponse, ProfileUpdate, TripResponse, TripSummary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["trips"])

# 各节点完成后的进度文案（与前端进度条对齐）
STAGE_MESSAGES = {
    "extract": "偏好已确认",
    "research": "素材已就绪",
    "plan": "行程已生成",
    "hotel_search": "酒店已搜索",
    "transport": "交通已规划",
}


def _read_profile_departure(db: Session) -> str:
    """读用户记住的出发地（无记录返回空串）。"""
    row = db.query(UserProfile).order_by(UserProfile.id.desc()).first()
    return (row.departure_city or "").strip() if row else ""


def _initial_state(user_input: str, db: Session) -> dict:
    """构造 Agent 初始状态，附带用户配置里的出发地供 extract 兜底。"""
    return {"user_input": user_input, "profile_departure": _read_profile_departure(db)}


def _save_departure(db: Session, departure: str) -> None:
    """把出发地写入用户配置（单行 upsert），下次生成自动复用。"""
    departure = (departure or "").strip()
    if not departure:
        return
    row = db.query(UserProfile).order_by(UserProfile.id.desc()).first()
    if row:
        row.departure_city = departure
    else:
        db.add(UserProfile(departure_city=departure))
    db.commit()


def _sse(payload: dict) -> str:
    """把一条事件序列化为 SSE 的 data 帧。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _to_response(trip: Trip) -> TripResponse:
    return TripResponse(
        id=trip.id,
        user_input=trip.user_input,
        preferences=trip.preferences,
        research=trip.research,
        itinerary=trip.itinerary,
        created_at=trip.created_at.isoformat(),
        usage=trip.usage or {},
        transit=trip.transit or {},
        hotels=trip.hotels or [],
    )


@router.post("/generate", response_model=TripResponse)
def generate_trip(req: GenerateRequest, db: Session = Depends(get_db)):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    result = agent_graph.invoke(_initial_state(req.user_input, db))

    trip = Trip(
        user_input=req.user_input,
        preferences=result.get("preferences", {}),
        research=result.get("research", {}),
        itinerary=result.get("itinerary", ""),
        usage=result.get("usage") or {},
        transit=result.get("transit") or {},
        hotels=result.get("hotels") or [],
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    _save_departure(db, (result.get("preferences") or {}).get("departure", ""))
    return _to_response(trip)


@router.post("/generate/stream")
async def generate_trip_stream(req: GenerateRequest, db: Session = Depends(get_db)):
    """流式生成：以 SSE 实时推送三步进度（抽取 → 搜集 → 生成），完成后返回完整行程。"""
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    async def event_gen():
        state = _initial_state(req.user_input, db)
        try:
            # astream 同时监听节点完成（updates）和节点内自定义事件（custom）
            async for chunk in agent_graph.astream(state, stream_mode=["updates", "custom"]):
                mode, data = chunk
                logger.debug("generate_trip_stream: chunk mode=%s, data type=%s", mode, type(data).__name__)
                if mode == "updates":
                    # 新版 LangGraph 的 data 是列表 [(node, update), ...]
                    items = data.items() if isinstance(data, dict) else data
                    for node, update in items:
                        logger.debug("generate_trip_stream: node=%s, update type=%s, update keys=%s", node, type(update).__name__, list(update.keys()) if isinstance(update, dict) else "N/A")
                        state.update(update)  # 手动累积，循环结束即完整 AgentState
                        yield _sse(
                            {
                                "type": "stage",
                                "stage": node,
                                "status": "done",
                                "message": STAGE_MESSAGES.get(node, ""),
                            }
                        )
                elif mode == "custom":
                    # research 节点内推送的小红书采集进度，原样透传给前端
                    yield _sse(data)
        except Exception as e:
            logger.exception("generate_trip_stream 异常详情：")
            yield _sse({"type": "error", "message": f"LLM返回失败: {e}"})
            return

        trip = Trip(
            user_input=req.user_input,
            preferences=state.get("preferences", {}),
            research=state.get("research", {}),
            itinerary=state.get("itinerary", ""),
            usage=state.get("usage") or {},
            transit=state.get("transit") or {},
            hotels=state.get("hotels") or [],
        )
        db.add(trip)
        db.commit()
        db.refresh(trip)
        _save_departure(db, (state.get("preferences") or {}).get("departure", ""))
        yield _sse({"type": "done", "trip": _to_response(trip).model_dump()})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/trips", response_model=list[TripSummary])
def list_trips(db: Session = Depends(get_db)):
    trips = db.query(Trip).order_by(Trip.id.desc()).all()
    return [
        TripSummary(
            id=t.id,
            destination=(t.preferences or {}).get("destination", ""),
            days=(t.preferences or {}).get("days", 1),
            created_at=t.created_at.isoformat(),
        )
        for t in trips
    ]


@router.get("/trips/{trip_id}", response_model=TripResponse)
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    return _to_response(trip)


@router.get("/profile", response_model=ProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    return ProfileResponse(departure=_read_profile_departure(db))


@router.post("/profile", response_model=ProfileResponse)
def save_profile(req: ProfileUpdate, db: Session = Depends(get_db)):
    _save_departure(db, req.departure)
    return ProfileResponse(departure=_read_profile_departure(db))
