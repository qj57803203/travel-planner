"""应用配置：从环境变量 / .env 读取。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    database_url: str = "sqlite:///./trips.db"

    # 小红书 MCP（xpzouying/xiaohongshu-mcp）：空 = 不启用（走预置数据兜底）
    xhs_mcp_url: str = ""            # 例：http://127.0.0.1:18060/mcp
    xhs_mcp_timeout_s: int = 40      # 单次 MCP 调用整体超时（搜索页冷加载可超 25s）
    xhs_collect_timeout_s: float = 75  # 一轮 xhs 采集总预算（搜索 + 详情）
    xhs_notes_per_turn: int = 5      # 每次搜索最多取几篇笔记详情


settings = Settings()
