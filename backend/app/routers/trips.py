"""行程相关接口：生成 / 列表 / 详情。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.graph import agent_graph
from app.database import get_db
from app.models import Trip
from app.schemas import GenerateRequest, TripResponse, TripSummary

router = APIRouter(prefix="/api", tags=["trips"])


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
