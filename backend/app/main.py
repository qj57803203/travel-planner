"""FastAPI 应用入口。"""
import logging
import time
from datetime import datetime, timezone, timedelta

import colorlog

# 强制日志时间使用北京时间（UTC+8），避免服务器时区为 UTC 导致差 8 小时
_BJT = timezone(timedelta(hours=8))
def _bjt_converter(*args):
    """返回北京时间的 struct_time，供 logging 格式化使用。"""
    return datetime.now(_BJT).timetuple()

logging.Formatter.converter = _bjt_converter
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

# 带颜色的日志配置
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    "%(asctime)s %(log_color)s%(levelname)-8s%(reset)s %(name)s: %(message)s",
    log_colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'bold_red',
    },
))
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
# 第三方库日志调高到 WARNING，避免淹没业务日志
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("http11").setLevel(logging.WARNING)
from app.database import Base, engine
from app.routers import trips



# 首次启动时建表
Base.metadata.create_all(bind=engine)
# 轻量迁移：为已存在的 trips 表补新增列（create_all 不会改旧表结构）
_trips_cols = [c["name"] for c in inspect(engine).get_columns("trips")]
for _col, _type in (("usage", "JSON"), ("transit", "JSON"), ("transit_error", "TEXT"), ("hotels", "JSON"), ("parent_id", "INTEGER"), ("chat_history", "JSON")):
    if _col not in _trips_cols:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE trips ADD COLUMN {_col} {_type}"))

app = FastAPI(title="旅行规划 Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://118.89.71.196:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trips.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理 CDP 连接。"""
    from app.tools.chrome_manager import close
    await close()
