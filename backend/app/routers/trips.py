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

MAX_CHAT_ROUNDS = 5  # 多轮对话最大修改轮数

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


def _count_rounds(db: Session, trip_id: int) -> int:
    """沿 parent_id 链计算当前对话轮数（不含首次生成）。"""
    visited = set()
    current_id = trip_id
    rounds = 0
    while current_id and current_id not in visited:
        visited.add(current_id)
        trip = db.get(Trip, current_id)
        if not trip or not trip.parent_id:
            break
        rounds += 1
        current_id = trip.parent_id
    return rounds


def _find_root_parent(db: Session, trip_id: int) -> int:
    """沿 parent_id 链找到链头（原始行程 ID）。"""
    visited = set()
    current_id = trip_id
    while current_id and current_id not in visited:
        visited.add(current_id)
        trip = db.get(Trip, current_id)
        if not trip or not trip.parent_id:
            return current_id
        current_id = trip.parent_id
    return current_id


def _initial_state(user_input: str, db: Session, trip_id: int | None = None) -> dict:
    """构造 Agent 初始状态。

    首次生成：只传 user_input + profile_departure。
    修改模式：加载上一轮 Trip 的 preferences/research/itinerary/chat_history，标记 is_modification。
    """
    if not trip_id:
        # ── 首次生成 ──
        return {"user_input": user_input, "profile_departure": _read_profile_departure(db)}

    # ── 修改模式 ──
    old_trip = db.get(Trip, trip_id)
    if not old_trip:
        raise HTTPException(status_code=404, detail="要修改的行程不存在")

    # 轮数限制：沿链计数
    rounds = _count_rounds(db, trip_id)
    if rounds >= MAX_CHAT_ROUNDS:
        raise HTTPException(status_code=400, detail=f"已达最大修改次数（{MAX_CHAT_ROUNDS}轮），请新建行程")

    # 构造对话历史：旧历史 + 上一轮 assistant 回复 + 本轮 user 输入
    old_history = old_trip.chat_history or []
    chat_history = old_history + [
        {"role": "assistant", "content": (old_trip.itinerary or "")},
        {"role": "user", "content": user_input},
    ]

    # parent_id 始终指向链头（原始行程）
    root_id = _find_root_parent(db, trip_id)

    return {
        "user_input": user_input,
        "profile_departure": _read_profile_departure(db),
        "preferences": old_trip.preferences or {},
        "research": old_trip.research or {},
        "previous_itinerary": old_trip.itinerary or "",
        "chat_history": chat_history,
        "is_modification": True,
        "_parent_id": root_id,  # 暂存，落库时用
        "_chat_history": chat_history,  # 暂存，落库时用
    }


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
        transit_error=trip.transit_error or "",
        hotels=trip.hotels or [],
        chat_history=trip.chat_history or [],
        parent_id=trip.parent_id,
    )


@router.post("/generate", response_model=TripResponse)
def generate_trip(req: GenerateRequest, db: Session = Depends(get_db)):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="输入不能为空")

    init_state = _initial_state(req.user_input, db, req.trip_id)
    try:
        result = agent_graph.invoke(init_state)
    except Exception as e:
        logger.error("generate_trip 异常: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="抱歉，这个问题目前超出了我的能力范围。我会持续学习，争取下次更快帮到您！",
        )

    trip = Trip(
        user_input=req.user_input,
        preferences=result.get("preferences", {}),
        research=result.get("research", {}),
        itinerary=result.get("itinerary", ""),
        usage=result.get("usage") or {},
        transit=result.get("transit") or {},
        transit_error=result.get("transit_error") or "",
        hotels=result.get("hotels") or [],
        parent_id=init_state.get("_parent_id"),
        chat_history=init_state.get("_chat_history"),
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

    # 提前校验（_initial_state 可能抛 HTTPException，SSE 里不好抛）
    if req.trip_id:
        old_trip = db.get(Trip, req.trip_id)
        if not old_trip:
            raise HTTPException(status_code=404, detail="要修改的行程不存在")
        rounds = _count_rounds(db, req.trip_id)
        if rounds >= MAX_CHAT_ROUNDS:
            raise HTTPException(status_code=400, detail=f"已达最大修改次数（{MAX_CHAT_ROUNDS}轮），请新建行程")

    async def event_gen():
        state = _initial_state(req.user_input, db, req.trip_id)
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
            yield _sse({"type": "error", "message": "抱歉，这个问题目前超出了我的能力范围。我会持续学习，争取下次更快帮到您！"})
            return

        trip = Trip(
            user_input=req.user_input,
            preferences=state.get("preferences", {}),
            research=state.get("research", {}),
            itinerary=state.get("itinerary", ""),
            usage=state.get("usage") or {},
            transit=state.get("transit") or {},
            transit_error=state.get("transit_error") or "",
            hotels=state.get("hotels") or [],
            parent_id=state.get("_parent_id"),
            chat_history=state.get("_chat_history"),
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


@router.get("/xhs-cookies")
def get_xhs_cookies_status():
    """查询小红书 Cookie 配置状态。"""
    from pathlib import Path

    cookies_path = Path("/app/xhs_data/cookies.json")
    if not cookies_path.exists():
        return {"has_cookies": False, "cookie_count": 0, "source": "未配置"}

    try:
        data = json.loads(cookies_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            count = len(data)
            source = "JSON 数组"
        elif isinstance(data, dict) and "cookies" in data:
            count = len(data["cookies"])
            source = "MCP 格式"
        else:
            count = 0
            source = "格式未知"
        return {"has_cookies": count > 0, "cookie_count": count, "source": source}
    except Exception:
        return {"has_cookies": False, "cookie_count": 0, "source": "文件损坏"}


# ============================================================
# 小红书 MCP 二维码登录（主力方案）
# ============================================================

@router.get("/xhs-qrcode")
async def get_xhs_qrcode():
    """获取小红书登录二维码（调用 MCP 的 get_login_qrcode 工具）。

    MCP 服务会启动浏览器打开小红书首页，提取二维码图片的 base64 数据，
    并在后台等待扫码（最多 4 分钟）。

    返回：
    - qrcode: base64 图片（"data:image/png;base64,..."），前端直接塞 <img src>
    - timeout: 二维码有效时间（秒）
    - already_logged_in: 已登录时为 True
    """
    from app.tools import xhs_mcp

    if not xhs_mcp.enabled():
        raise HTTPException(status_code=503, detail="小红书 MCP 未启用（XHS_MCP_URL 未配置）")

    qrcode, timeout, already_logged_in = await xhs_mcp.get_login_qrcode()

    if already_logged_in:
        return {"qrcode": "", "timeout": 0, "already_logged_in": True, "message": "已登录"}

    if not qrcode:
        raise HTTPException(status_code=500, detail="获取二维码失败，请查看后端日志")

    return {"qrcode": qrcode, "timeout": timeout, "already_logged_in": False, "message": "请用手机小红书 App 扫码"}


@router.get("/xhs-login-status")
async def get_xhs_login_status():
    """检查小红书登录状态（调用 MCP 的 check_login_status 工具）。"""
    from app.tools import xhs_mcp

    if not xhs_mcp.enabled():
        return {"logged_in": False, "message": "MCP 未启用"}

    logged_in, message = await xhs_mcp.check_login_status()
    return {"logged_in": logged_in, "message": message}
