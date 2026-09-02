"""FastAPI 应用入口。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.database import Base, engine
from app.routers import trips

# 首次启动时建表
Base.metadata.create_all(bind=engine)
# 轻量迁移：为已存在的 trips 表补 usage 列（create_all 不会改旧表结构）
if "usage" not in [c["name"] for c in inspect(engine).get_columns("trips")]:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE trips ADD COLUMN usage JSON"))

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
