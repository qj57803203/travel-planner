# 旅行规划 Agent 部署指南

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                      腾讯云服务器                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐  │
│  │ Frontend │    │ Backend  │    │  xhs-browser         │  │
│  │  Nginx   │───▶│ FastAPI  │    │  (VNC 远程桌面)      │  │
│  │  :80     │    │  :8000   │    │  :6080 (noVNC)       │  │
│  └──────────┘    └────┬─────┘    └──────────┬───────────┘  │
│                       │                      │              │
│              ┌────────┼──────────────────────┤              │
│              │        │                      │              │
│              ▼        ▼                      ▼              │
│        ┌──────────┐ ┌──────────┐    ┌──────────────┐       │
│        │ xhs-mcp  │ │  Chrome  │    │  xhs/data    │       │
│        │  :18060  │ │  :9222   │    │  cookies     │       │
│        └──────────┘ └──────────┘    └──────────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 服务说明

| 服务 | 端口 | 说明 |
|---|---|---|
| frontend | 80 | Nginx 托管前端，反向代理 API |
| backend | 8000 | FastAPI 后端，核心业务逻辑 |
| xiaohongshu-mcp | 18060 (内部) | 小红书数据采集 |
| chrome | 9222 (内部) | 无头 Chrome，携程爬虫用 |
| xhs-browser | 6080 | VNC 远程桌面，扫码登录小红书 |

## 部署步骤

### 1. 准备服务器

```bash
# 腾讯云/阿里云，推荐配置：
# - 2核 4G 内存（最低）
# - 4核 8G 内存（推荐，Chrome 比较吃内存）
# - Ubuntu 22.04 LTS

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录让 docker 组生效

# 安装 Docker Compose
sudo apt install docker-compose-plugin
```

### 2. 上传代码

```bash
# 方式一：git clone
git clone <your-repo-url> /opt/travel-planner
cd /opt/travel-planner

# 方式二：scp 上传
scp -r ./travel-planner root@your-server-ip:/opt/
```

### 3. 配置环境变量

```bash
cd /opt/travel-planner/deploy

# 复制环境变量模板
cp backend.env.example backend.env

# 编辑填入真实的 API Key
vim backend.env
```

**必须配置**：
- `DEEPSEEK_API_KEY` - DeepSeek API 密钥

**可选配置**：
- `AMAP_WEB_KEY` - 高德地图 Key（无则走纯文本交通）

### 4. 创建数据目录

```bash
# 创建持久化目录
mkdir -p data xhs/data xhs/browser-data

# 初始化空的 cookies 文件（如果不存在）
if [ ! -f xhs/data/cookies.json ]; then
  echo '{"version":2,"seed":0,"saved_at":"","cookies":[]}' > xhs/data/cookies.json
fi
```

### 5. 构建并启动

```bash
# 构建后端镜像
docker compose build

# 启动所有服务
docker compose up -d

# 查看日志
docker compose logs -f

# 查看某个服务的日志
docker compose logs -f backend
```

### 6. 小红书登录

首次部署或 cookies 过期时，需要登录小红书。有两种方式：

#### 方式一：远程浏览器登录（推荐）

```bash
# 1. 启动登录浏览器服务
docker compose --profile login up -d xhs-browser

# 2. 访问 VNC 远程桌面
#    浏览器打开: http://your-server-ip:6080
#    输入 VNC 密码（默认 xhs123，在 docker-compose.yml 或 .env 中修改）

# 3. 在远程桌面的 Chromium 浏览器中
#    - 打开 https://www.xiaohongshu.com
#    - 扫码登录
#    - 按 F12 打开开发者工具 → Application → Cookies
#    - 复制所有 cookies

# 4. 将 cookies 保存到服务器
#    在服务器上编辑 xhs/data/cookies.json，粘贴 cookies 内容
#    或者使用浏览器插件导出 cookies 后上传

# 5. 重启服务使 cookies 生效
docker compose restart xiaohongshu-mcp

# 6. 登录完成后，可以停止浏览器服务（节省资源）
docker compose --profile login stop xhs-browser
```

#### 方式二：本地导出 cookies 上传

```bash
# 1. 在本地电脑浏览器登录小红书
# 2. 安装浏览器插件（如 "EditThisCookie" 或 "Cookie-Editor"）
# 3. 导出 cookies 为 JSON 格式
# 4. 上传到服务器的 xhs/data/cookies.json
# 5. 重启服务
docker compose restart xiaohongshu-mcp
```

#### 验证登录状态

```bash
# 查看后端日志，确认小红书 MCP 是否可用
docker compose logs backend | grep -i "小红书"

# 测试采集功能
curl -X POST http://localhost/api/generate \
  -H "Content-Type: application/json" \
  -d '{"user_input": "3天苏州游"}'
```

### 7. 验证部署

```bash
# 健康检查
curl http://localhost/health

# 访问前端
# 浏览器打开: http://your-server-ip

# 测试生成行程
curl -X POST http://localhost/api/generate \
  -H "Content-Type: application/json" \
  -d '{"user_input": "3天苏州游，预算中等"}'
```

## 常见问题

### Q1: 小红书采集失败，提示未登录

**原因**：cookies 过期或未登录

**解决**：
1. 访问 `http://your-server-ip:6080` 打开 VNC 远程桌面
2. 在浏览器中重新登录小红书
3. 重启服务：`docker compose restart xiaohongshu-mcp`

### Q2: 携程酒店搜索失败

**原因**：Chrome 容器未正常运行

**解决**：
```bash
# 检查 Chrome 容器状态
docker compose ps chrome

# 查看日志
docker compose logs chrome

# 重启
docker compose restart chrome
```

### Q3: 内存不足

**原因**：Chrome 比较吃内存

**解决**：
```bash
# 查看内存使用
docker stats

# 如果内存紧张，可以停掉 xhs-browser（登录完成后）
docker compose stop xhs-browser
```

### Q4: 如何更新代码

```bash
cd /opt/travel-planner

# 拉取最新代码
git pull

# 重新构建并重启
cd deploy
docker compose build
docker compose up -d
```

### Q5: 如何备份数据

```bash
# 备份 SQLite 数据库
cp data/trips.db backup/trips_$(date +%Y%m%d).db

# 备份小红书 cookies
cp xhs/data/cookies.json backup/cookies_$(date +%Y%m%d).json
```

## 安全建议

1. **修改默认密码**：
   - VNC 密码（docker-compose.yml 中的 `VNC_PASSWORD`）
   - 考虑给 VNC 端口加防火墙规则

2. **配置 HTTPS**：
   - 申请 SSL 证书（Let's Encrypt 免费）
   - 取消 nginx.conf 中 HTTPS 配置的注释

3. **限制端口访问**：
   ```bash
   # 只允许 80 和 443 端口对外
   sudo ufw allow 80
   sudo ufw allow 443
   sudo ufw enable

   # VNC 端口只允许特定 IP（可选）
   sudo ufw allow from your-ip to any port 6080
   ```

4. **定期更新 cookies**：
   - 小红书 cookies 一般 7-30 天过期
   - 建议每周登录一次

## 监控与维护

```bash
# 查看所有服务状态
docker compose ps

# 查看资源使用
docker stats

# 查看日志（实时）
docker compose logs -f

# 重启某个服务
docker compose restart backend

# 停止所有服务
docker compose down

# 停止并删除数据（谨慎！）
docker compose down -v
```

## 成本估算（腾讯云）

| 配置 | 价格 |
|---|---|
| 2核4G（轻量应用服务器） | ~60元/月 |
| 4核8G（轻量应用服务器） | ~120元/月 |
| 域名 | ~60元/年 |
| SSL 证书 | 免费（Let's Encrypt） |

**推荐**：4核8G 配置，因为 Chrome 和 LLM 调用都比较吃资源。
