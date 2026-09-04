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
    xhs_collect_timeout_s: float = 60  # 一轮 xhs 采集总预算（搜索 + 详情）60s够爬两三条
    xhs_notes_per_turn: int = 5      # 每次搜索最多取几篇笔记详情
    xhs_cache_ttl_days: int = 7      # 小红书笔记缓存有效期（天）

    # 高德地图 Web 服务 API（lbs.amap.com，Web服务 key）：空 = 不启用真实交通，走纯文本
    amap_web_key: str = ""
    amap_timeout_s: float = 8        # 单次高德请求超时（秒）

    # 携程酒店爬虫（Chrome MCP + chrome-devtools-mcp）：空 = 不启用酒店搜索
    ctrip_mcp_url: str = ""          # 非空即启用（如 "1"），已弃用旧 Playwright MCP 地址
    ctrip_cache_ttl_days: int = 3    # 携程酒店缓存有效期（天）
    ctrip_city_cache_ttl_days: int = 365  # 城市 ID 缓存有效期（天，基本不变）

    # Chrome MCP 调试端口（chrome-devtools-mcp 连接用）
    chrome_debug_url: str = "http://127.0.0.1:9222"


settings = Settings()
