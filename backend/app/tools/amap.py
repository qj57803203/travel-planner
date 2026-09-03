"""高德地图 Web 服务 API 封装。

只做三件事：地理编码（地名→经纬度）、路径规划（公交/步行/驾车）、结果精简。
所有函数在失败时返回 None 而非抛异常，由调用方按需降级，绝不阻塞主流程。

坐标系：高德返回 GCJ-02（火星坐标），与前端 JS API 一致，无需转换。
"""
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE = "https://restapi.amap.com"

# QPS 限流：高德免费版限制 30 QPS，每次请求间隔至少 50ms
_last_request_time = 0.0
QPS_INTERVAL = 0.05  # 50ms，留点余量


def enabled() -> bool:
    """未配置 key 时不启用真实交通。"""
    return bool(settings.amap_web_key)


def _get(path: str, params: dict, max_retries: int = 3) -> dict | None:
    """带 key 的 GET 请求；超时 / 网络 / 业务错误统一返回 None。

    遇到 QPS 限制（CUQPS_HAS_EXCEEDED_THE_LIMIT）时自动等待重试。
    """
    global _last_request_time
    if not enabled():
        return None

    for attempt in range(max_retries):
        # 限流：确保两次请求间隔足够
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < QPS_INTERVAL:
            time.sleep(QPS_INTERVAL - elapsed)

        try:
            with httpx.Client(timeout=settings.amap_timeout_s) as client:
                r = client.get(f"{BASE}{path}", params={"key": settings.amap_web_key, **params})
                _last_request_time = time.monotonic()
                r.raise_for_status()
                data = r.json()
        except Exception as e:  # noqa: BLE001 — 任何失败都降级，不中断
            logger.warning("高德请求失败 %s：%s", path, e)
            return None

        if data.get("status") != "1":
            info = data.get("info") or ""
            # QPS 超限：等待后重试
            if "EXCEEDED_THE_LIMIT" in info and attempt < max_retries - 1:
                wait = 0.5 * (attempt + 1)  # 递增等待 0.5s, 1s, 1.5s
                logger.warning("高德 QPS 超限，%.1f秒后重试（%d/%d）", wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            logger.warning("高德返回业务错误 %s：%s", path, info)
            return None
        return data

    return None


def _parse_polyline(s: str) -> list[list[float]]:
    """高德 polyline 为 "lng,lat;lng,lat;..."，转成 [[lng,lat],...] 供前端直接绘制。"""
    out: list[list[float]] = []
    for p in (s or "").split(";"):
        if "," not in p:
            continue
        lng, _, lat = p.partition(",")
        try:
            out.append([float(lng), float(lat)])
        except ValueError:
            continue
    return out


def geocode(address: str, city: str = "") -> dict | None:
    """地名 → {"lng","lat","lnglat"}；查不到或失败返回 None。"""
    params: dict = {"address": address}
    if city:
        params["city"] = city
    data = _get("/v3/geocode/geo", params)
    geos = (data or {}).get("geocodes") or []
    if not geos:
        return None
    loc = geos[0].get("location", "")
    if "," not in loc:
        return None
    lng, _, lat = loc.partition(",")
    try:
        return {"lng": float(lng), "lat": float(lat), "lnglat": loc}
    except ValueError:
        return None


def transit_route(origin: str, dest: str, city: str, cityd: str = "") -> dict | None:
    """公交路径规划（融合地铁/公交/步行/铁路）。origin/dest 为 "lng,lat"。

    city: 起点城市（必填）
    cityd: 终点城市（可选，默认与 city 相同，城际交通需传目的地城市）

    注意：高德 API 返回的 segments 中，walking/bus/railway 字段在无数据时
    可能返回空数组 [] 而非空对象 {}，必须用 isinstance(x, dict) 检查后再调用 .get()。
    """
    data = _get(
        "/v3/direction/transit/integrated",
        {"origin": origin, "destination": dest, "city": city, "cityd": cityd or city},
    )
    transits = ((data or {}).get("route") or {}).get("transits") or []
    if not transits:
        return None
    t = transits[0]
    duration_s = int(t.get("duration") or 0)
    distance_m = int(t.get("distance") or 0)
    parts: list[str] = []
    polyline: list[list[float]] = []
    for seg in t.get("segments") or []:
        if "walking" in seg and isinstance(seg["walking"], dict):
            w = seg["walking"]
            parts.append(f"步行{int(w.get('distance') or 0)}m")
            for st in w.get("steps") or []:
                polyline += _parse_polyline(st.get("polyline") or "")
        elif "bus" in seg and isinstance(seg["bus"], dict):
            for ln in (seg["bus"].get("buslines") or []):
                dep = (ln.get("departure_stop") or {}).get("name", "")
                arr = (ln.get("arrival_stop") or {}).get("name", "")
                name = ln.get("name") or "公交"
                parts.append(f"{name} {dep}→{arr}")
                polyline += _parse_polyline(ln.get("polyline") or "")
        elif "railway" in seg and isinstance(seg["railway"], dict):
            for ln in (seg["railway"].get("lines") or []):
                dep = (ln.get("departure_stop") or {}).get("name", "")
                arr = (ln.get("arrival_stop") or {}).get("name", "")
                name = ln.get("name") or "铁路"
                parts.append(f"{name} {dep}→{arr}")
                # 铁路段也有 polyline，需要解析
                polyline += _parse_polyline(ln.get("polyline") or "")
    return {
        "mode": "公交/地铁/铁路",
        "summary": " · ".join(parts) if parts else "公交/地铁/铁路",
        "duration_min": round(duration_s / 60),
        "distance_m": distance_m,
        "polyline": polyline,
    }


def walking_route(origin: str, dest: str) -> dict | None:
    """步行路径规划（近距离兜底）。"""
    data = _get("/v3/direction/walking", {"origin": origin, "destination": dest})
    paths = ((data or {}).get("route") or {}).get("paths") or []
    if not paths:
        return None
    p = paths[0]
    duration_s = int(p.get("duration") or 0)
    distance_m = int(p.get("distance") or 0)
    return {
        "mode": "步行",
        "summary": f"步行约{round(distance_m / 1000, 1)}公里，约{round(duration_s / 60)}分钟",
        "duration_min": round(duration_s / 60),
        "distance_m": distance_m,
        "polyline": _parse_polyline(p.get("polyline") or ""),
    }


def driving_route(origin: str, dest: str) -> dict | None:
    """驾车路径规划（城际参考：出发地 → 目的地城市）。"""
    data = _get("/v3/direction/driving", {"origin": origin, "destination": dest})
    paths = ((data or {}).get("route") or {}).get("paths") or []
    if not paths:
        return None
    p = paths[0]
    duration_s = int(p.get("duration") or 0)
    distance_m = int(p.get("distance") or 0)
    return {
        "mode": "驾车",
        "summary": f"驾车约{round(distance_m / 1000)}公里，约{round(duration_s / 3600, 1)}小时",
        "duration_min": round(duration_s / 60),
        "distance_m": distance_m,
        "polyline": _parse_polyline(p.get("polyline") or ""),
    }
