"""应用配置：从环境变量 / .env 读取。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    database_url: str = "sqlite:///./trips.db"

    # 小红书 MCP（xpzouying/xiaohongshu-mcp）：空 = 不启用
    xhs_mcp_url: str = ""            # 例：http://127.0.0.1:18060/mcp
    xhs_mcp_timeout_s: int = 60      # 单次 MCP 调用整体超时（MCP 服务冷启动需 ~40s）
    xhs_collect_timeout_s: float = 60  # 一轮 xhs 采集总预算（搜索 + 详情）120s够爬5条
    xhs_notes_per_turn: int = 5      # 每次搜索最多取几篇笔记详情
    xhs_cache_ttl_days: int = 7      # 小红书笔记缓存有效期（天）

    # 高德地图 Web 服务 API（lbs.amap.com，Web服务 key）：空 = 不启用真实交通，走纯文本
    amap_web_key: str = ""
    amap_timeout_s: float = 8        # 单次高德请求超时（秒）

    # 携程酒店爬虫（原生 CDP WebSocket 直连 Chrome）：空 = 不启用酒店搜索
    ctrip_mcp_url: str = ""          # 非空即启用（如 "1"），字段名沿用旧版，实际走 CDP 直连
    ctrip_cache_ttl_days: int = 3    # 携程酒店缓存有效期（天）
    ctrip_city_cache_ttl_days: int = 365  # 城市 ID 缓存有效期（天，基本不变）

    # Chrome MCP 调试端口（chrome-devtools-mcp 连接用）
    chrome_debug_url: str = "http://127.0.0.1:9222"
    # Chrome 可执行文件路径：指定时 MCP 自己拉起 headless 浏览器（本地开发用）；
    # 留空时连接 chrome_debug_url 指向的常驻 Chrome（服务器部署用）
    chrome_executable: str = ""
    # 是否为远程常驻浏览器（影响自愈策略：True 时超时会杀 Chrome 等 Docker 重启）
    remote_browser: bool = False


settings = Settings()
