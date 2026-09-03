"""FastAPI 应用入口。"""
import logging
# 配置日志级别为 DEBUG，方便调试
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.database import Base, engine
from app.routers import trips



# 首次启动时建表
Base.metadata.create_all(bind=engine)
# 轻量迁移：为已存在的 trips 表补新增列（create_all 不会改旧表结构）
_trips_cols = [c["name"] for c in inspect(engine).get_columns("trips")]
for _col, _type in (("usage", "JSON"), ("transit", "JSON")):
    if _col not in _trips_cols:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE trips ADD COLUMN {_col} {_type}"))

app = FastAPI(title="旅行规划 Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trips.router)


@app.get("/health")
def health():
    return {"status": "ok"}
