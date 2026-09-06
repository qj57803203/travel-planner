# CDP 直连方案：去掉 MCP 中间层

## 一、背景问题

线上环境中，小红书和携程的数据采集都依赖 MCP 协议控制浏览器，链路长且不稳定：

```
Python → MCP 协议 → npx chrome-devtools-mcp → CDP → Chrome
                     ↑ 这一层经常出问题
```

| 服务 | 原方案 | 问题 |
|------|--------|------|
| 小红书 | MCP 容器（xiaohongshu-mcp） | 需要独立浏览器容器 + cookie 同步，维护成本高 |
| 携程 | Chrome MCP（stdio spawn npx） | npx 启动慢、CDP 会话互相干扰、三层自愈不稳定 |

## 二、改造方案

**去掉 MCP 中间层，后端直接通过 CDP WebSocket 协议控制 Chrome。**

```
新：Python → CDP WebSocket → Chrome（2层，直连）
```

### 核心设计

1. **后端共享 Chrome 网络**：通过 Docker `network_mode: "service:chrome"` 让后端容器和 Chrome 容器共享网络命名空间，后端直连 `localhost:9223`
2. **轻量 CDP 封装**：用 `websockets` 库直接发送 CDP 命令（`Page.navigate`、`Runtime.evaluate`），不依赖 Playwright/MCP
3. **串行锁**：进程级 `threading.Lock` 保证同一时刻只有一个操作控制 Chrome（防并发搞死 CDP 会话）
4. **三层自愈**：超时 → 重连 → 杀 Chrome 等 Docker 重启

### 网络架构

```
┌─────────────────────────────────────────────────┐
│  Docker 内部网络                                 │
│                                                 │
│  ┌──────────────┐    network_mode: service:chrome│
│  │ Chrome 容器   │◄────────────────────────────┐ │
│  │ 127.0.0.1:9223│                             │ │
│  │ (headless-shell)                            │ │
│  └──────────────┘    ┌──────────────┐          │ │
│        ▲              │ 后端容器      │          │ │
│        │              │ localhost:9223│ ─────────┘ │
│        │              │ :8000 (FastAPI)           │
│        │              └──────────────┘            │
│        │                      ▲                  │
│  ┌──────────────┐             │                  │
│  │ 前端 Nginx    │ ── proxy ──┘                  │
│  │ :80           │  (→ travel-chrome:8000)        │
│  └──────────────┘                                │
└─────────────────────────────────────────────────┘
```

关键点：后端通过 `network_mode: "service:chrome"` 共享 Chrome 的网络栈，可以直接访问 `localhost:9223`。前端 Nginx 通过 Chrome 容器名 `travel-chrome:8000` 访问后端（因为它们共享网络）。

## 三、文件变更清单

### 新增文件

| 文件 | 作用 |
|------|------|
| `backend/app/tools/chrome_manager.py` | CDP WebSocket 连接管理器（串行锁 + 自愈） |
| `backend/app/tools/xhs_browser.py` | 小红书浏览器爬虫（直接浏览搜索页 + 详情页） |
| `backend/app/tools/xhs_login.py` | VNC 容器内的 cookie 导出脚本 |
| `frontend/public/xhs-login.html` | Cookie 配置引导页面 |

### 修改文件

| 文件 | 变更内容 |
|------|----------|
| `backend/app/tools/ctrip_crawler.py` | MCP 调用改为 CDP 直连；`enabled()` 改为检测 `chrome_debug_url` |
| `backend/app/agent/nodes.py` | research 节点：浏览器方案优先，MCP 作为 fallback |
| `backend/app/main.py` | 添加 shutdown 事件清理连接 |
| `backend/app/routers/trips.py` | 新增 `GET/POST /api/xhs-cookies` cookie 管理接口 |
| `backend/requirements.txt` | 添加 `websockets>=12.0`，移除 `playwright` |
| `deploy/Dockerfile.backend` | 移除 Node.js（不再需要 npx） |
| `deploy/docker-compose.yml` | 后端 `network_mode` 共享 Chrome 网络；MCP 改为可选 |
| `deploy/nginx.conf` | proxy_pass 改为 `travel-chrome:8000` |

## 四、小红书 Cookie 管理

小红书必须登录才能搜索，Cookie 有效期约 7-30 天。

### 获取方式一：网页上传（推荐）

1. 本地浏览器登录 https://www.xiaohongshu.com
2. F12 → Network → 刷新页面 → 点任意请求 → 复制 `Cookie` 请求头
3. 访问 `http://118.89.71.196/xhs-login.html`，粘贴提交

### 获取方式二：虚拟桌面

```bash
# 启动虚拟桌面
docker compose --profile login up -d xhs-browser

# 访问 http://118.89.71.196:6080（密码 xhs123）
# 在 Firefox 中登录小红书，然后终端运行：
python3 /app/xhs_login.py
```

### Cookie 存储

- 宿主机路径：`./xhs/data/cookies.json`
- 容器内路径：`/app/xhs_data/cookies.json`
- 格式：`[{name, value, domain, path}, ...]`
- 保存后立即生效，无需重启服务

## 五、部署与更新

### 首次部署

```bash
cd ~/travel-planner/deploy
sudo docker compose up -d --build
```

### 更新后端代码

```bash
# 上传改动的文件
scp backend/app/tools/xxx.py ubuntu@118.89.71.196:~/travel-planner/backend/app/tools/

# 重建并重启
ssh ubuntu@118.89.71.196 "cd ~/travel-planner/deploy && sudo docker compose up -d --build backend"
```

### 更新 docker-compose / nginx

```bash
scp deploy/docker-compose.yml deploy/nginx.conf ubuntu@118.89.71.196:~/travel-planner/deploy/
ssh ubuntu@118.89.71.196 "cd ~/travel-planner/deploy && sudo docker compose down && sudo docker compose up -d"
```

## 六、验证

```bash
# 健康检查
curl http://118.89.71.196/health

# Cookie 状态
curl http://118.89.71.196/api/xhs-cookies

# 后端日志
sudo docker logs travel-backend -f

# 测试 CDP 连接
sudo docker exec travel-backend python -c "
import asyncio
async def test():
    from app.tools.chrome_manager import get_chrome_page
    async with get_chrome_page() as page:
        await page.goto('https://www.baidu.com', wait_until='load', timeout=15000)
        print('标题:', await page.evaluate('document.title'))
asyncio.run(test())
"
```

## 七、回滚方案

如需回滚到 MCP 方案：

```bash
# 恢复 docker-compose.yml 中的 MCP 服务配置
# 取消注释 xiaohongshu-mcp 服务、depends_on、XHS_MCP_URL 环境变量
# 后端代码回退到 git 上一个版本

sudo docker compose --profile mcp up -d
sudo docker compose up -d --build backend
```

## 八、踩坑记录

### 1. Chrome CDP 的 Host 头限制

Chrome 的 HTTP 端点（`/json/version`、`/json/list`）要求 `Host` 头为 `localhost`。
通过 Docker 服务名（`chrome`）访问时 Host 头不匹配，返回 HTTP 500。

**解决**：后端通过 `network_mode: "service:chrome"` 共享 Chrome 容器的网络，直连 `localhost:9223`。

### 2. Chrome 只绑定 127.0.0.1

`chromedp/headless-shell` 的 `--remote-debugging-address=0.0.0.0` 参数不生效，Chrome 始终只监听 `127.0.0.1:9223`。

**解决**：同上，通过共享网络命名空间解决。

### 3. WebSocket URL 缺少端口

Chrome `/json/version` 返回的 `webSocketDebuggerUrl` 可能不含端口（如 `ws://localhost/devtools/...`），websockets 库默认连 80 端口。

**解决**：从返回的 URL 中解析，补上 `chrome_debug_url` 配置的端口。
