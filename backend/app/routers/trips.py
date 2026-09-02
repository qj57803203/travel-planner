"""行程相关接口：生成 / 列表 / 详情。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.graph import agent_graph
from app.database import get_db
from app.models import Trip
from app.schemas import GenerateRequest, TripResponse, TripSummary

router = APIRouter(prefix="/api", tags=["trips"])

# 各节点完成后的进度文案（与前端三步进度条对齐）
STAGE_MESSAGES = {
    "extract": "偏好已确认",
    "research": "素材已就绪",
    "plan": "行程已生成",
}


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
    )


@router.post("/generate", response_model=TripResponse)
def generate_trip(req: GenerateRequest, db: Session = Depends(get_db)):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    result = agent_graph.invoke({"user_input": req.user_input})

    trip = Trip(
        user_input=req.user_input,
        preferences=result.get("preferences", {}),
        research=result.get("research", {}),
        itinerary=result.get("itinerary", ""),
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return _to_response(trip)


@router.post("/generate/stream")
async def generate_trip_stream(req: GenerateRequest, db: Session = Depends(get_db)):
    """流式生成：以 SSE 实时推送三步进度（抽取 → 搜集 → 生成），完成后返回完整行程。"""
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    async def event_gen():
        state = {"user_input": req.user_input}
        try:
            # astream 同时监听节点完成（updates）和节点内自定义事件（custom）
            async for chunk in agent_graph.astream(state, stream_mode=["updates", "custom"]):
                mode, data = chunk
                if mode == "updates":
                    for node, update in data.items():
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
            yield _sse({"type": "error", "message": f"生成失败: {e}"})
            return

        trip = Trip(
            user_input=req.user_input,
            preferences=state.get("preferences", {}),
            research=state.get("research", {}),
            itinerary=state.get("itinerary", ""),
        )
        db.add(trip)
        db.commit()
        db.refresh(trip)
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
