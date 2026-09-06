# MCP 移除方案：Playwright CDP 直连 Chrome

## 背景

线上环境中，小红书 MCP 容器和携程 Chrome MCP（stdio spawn npx）都不稳定。
两者共同问题是依赖 MCP 协议中间层，链路长、易断。

## 改造方案

**去掉 MCP 中间层，改为 Playwright CDP 直连 Docker 内常驻 Chrome。**

```
旧：Python → MCP协议 → npx chrome-devtools-mcp → CDP → Chrome
新：Python → Playwright CDP → Chrome
```

## 架构变化

### 改造前（4 个服务）

| 服务 | 说明 |
|------|------|
| backend | FastAPI + LangGraph |
| xiaohongshu-mcp | 小红书 MCP 容器（浏览器 + MCP 服务） |
| chrome | Headless Chrome（携程用） |
| xhs-browser | 小红书登录浏览器（按需） |

### 改造后（2 个必需服务 + 1 个可选）

| 服务 | 说明 |
|------|------|
| backend | FastAPI + LangGraph + Playwright（直连 Chrome） |
| chrome | Headless Chrome（小红书 + 携程共用） |
| xhs-browser | 小红书登录浏览器（按需，用于获取 cookie） |

**xiaohongshu-mcp 容器不再需要**（改为可选 fallback）。

## 文件变更

### 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/tools/chrome_manager.py` | Playwright CDP Chrome 管理器（串行锁 + 三层自愈） |
| `backend/app/tools/xhs_browser.py` | 小红书浏览器爬虫（直接浏览搜索页 + 详情页） |
| `backend/app/tools/xhs_login.py` | VNC 容器内的 cookie 导出脚本 |
| `frontend/public/xhs-login.html` | Cookie 配置引导页面（访问 /xhs-login.html） |
| `deploy/MCP_REMOVAL.md` | 本文档 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/app/tools/ctrip_crawler.py` | MCP → Playwright，`enabled()` 改为检测 Chrome |
| `backend/app/agent/nodes.py` | research 节点：浏览器优先 + MCP fallback |
| `backend/app/main.py` | 添加 shutdown 清理 Playwright 连接 |
| `backend/app/routers/trips.py` | 新增 cookie 管理 API（GET/POST /api/xhs-cookies） |
| `backend/requirements.txt` | 添加 `playwright>=1.40` |
| `deploy/Dockerfile.backend` | 移除 Node.js（不再需要 npx） |
| `deploy/docker-compose.yml` | xiaohongshu-mcp 改为可选，xhs-browser 挂载共享 cookie |

## 小红书 Cookie 管理

小红书需要登录才能搜索。Cookie 有效期约 7-30 天。

### 获取方式

**方式一：浏览器导出（推荐）**
1. 在本地浏览器登录 xiaohongshu.com
2. F12 → Network → 点任意请求 → 复制 Cookie 请求头
3. 访问 `http://服务器IP/xhs-login.html`，粘贴并提交

**方式二：虚拟桌面登录**
1. 启动：`docker compose --profile login up -d xhs-browser`
2. 访问：`http://服务器IP:6080`（密码: xhs123）
3. 在 Firefox 中登录小红书
4. 终端运行：`python3 /app/xhs_login.py`

### Cookie 存储路径

- 宿主机：`./xhs/data/cookies.json`
- 容器内：`/app/xhs_data/cookies.json`
- 格式：Playwright cookie 数组 `[{name, value, domain, path}, ...]`

## 部署步骤

### 1. 上传代码到服务器

```bash
# 打包（排除 .git、node_modules 等）
cd d:/项目/旅游攻略
tar --exclude='.git' --exclude='node_modules' --exclude='.venv' --exclude='__pycache__' \
    --exclude='*.db' --exclude='*.tar.gz' \
    -czf /tmp/travel-update.tar.gz \
    backend/app/ backend/requirements.txt \
    deploy/Dockerfile.backend deploy/docker-compose.yml deploy/MCP_REMOVAL.md \
    frontend/public/

# 上传
scp /tmp/travel-update.tar.gz ubuntu@118.89.71.196:~/

# 解压
ssh ubuntu@118.89.71.196 "cd ~/travel-planner && tar -xzf ~/travel-update.tar.gz"
```

### 2. 重建并重启

```bash
ssh ubuntu@118.89.71.196 "cd ~/travel-planner/deploy && sudo docker compose up -d --build backend"
```

### 3. 配置小红书 Cookie

访问 `http://118.89.71.196/xhs-login.html`，按页面提示操作。

### 4. 验证

```bash
# 健康检查
curl http://118.89.71.196/health

# 检查 cookie 状态
curl http://118.89.71.196/api/xhs-cookies

# 查看后端日志（确认 Playwright 连接正常）
sudo docker logs travel-backend -f
```

## 回滚方案

如需回滚到 MCP 方案：

```bash
# 恢复 docker-compose.yml 中的 MCP 服务
# 取消注释 depends_on 中的 xiaohongshu-mcp
# 取消注释 environment 中的 XHS_MCP_URL
sudo docker compose --profile mcp up -d
sudo docker compose up -d --build backend
```
