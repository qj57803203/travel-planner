# 部署步骤（完整版）

服务器 IP：`118.89.71.196`

## 第一步：初始化服务器

在本地运行（会自动 SSH 到服务器执行）：

```bash
cd deploy
ssh root@118.89.71.196 'bash -s' < server-init.sh
```

或者手动 SSH 登录后执行：

```bash
ssh root@118.89.71.196
# 登录后
bash /tmp/server-init.sh  # 如果已上传
```

## 第二步：配置环境变量

在服务器上执行：

```bash
# 进入项目目录
cd /opt/travel-planner/deploy

# 创建环境变量文件
cp backend.env.example backend.env

# 编辑填入 API Key
vim backend.env
```

填入内容：
```
DEEPSEEK_API_KEY=sk-你的key
AMAP_WEB_KEY=你的高德key（可选）
```

## 第三步：上传代码

在本地 deploy 目录下执行：

```bash
# Windows Git Bash 或 Linux/Mac
./upload.sh
```

脚本会自动：
1. 构建前端（npm run build）
2. 打包代码
3. 上传到服务器

## 第四步：启动服务

SSH 登录服务器：

```bash
ssh root@118.89.71.196

# 进入项目目录
cd /opt/travel-planner/deploy

# 启动服务
./start.sh
```

## 第五步：验证部署

```bash
# 检查服务状态
docker compose ps

# 应该看到 4 个服务都是 running 状态：
# - travel-frontend
# - travel-backend
# - xiaohongshu-mcp
# - travel-chrome

# 访问测试
curl http://localhost/health
```

浏览器访问：http://118.89.71.196

## 第六步：登录小红书（可选）

```bash
# 启动登录浏览器
docker compose --profile login up -d xhs-browser

# 访问 VNC 远程桌面
# 浏览器打开: http://118.89.71.196:6080
# VNC 密码: xhs123（在 docker-compose.yml 中修改）
```

在远程桌面的 Chromium 浏览器中：
1. 打开 https://www.xiaohongshu.com
2. 扫码登录
3. 导出 cookies（参考 xhs/COOKIES_GUIDE.md）
4. 保存到 xhs/data/cookies.json
5. 重启服务：`docker compose restart`

## 常用命令

```bash
# 查看所有服务状态
docker compose ps

# 查看日志（实时）
docker compose logs -f

# 查看某个服务日志
docker compose logs -f backend

# 重启所有服务
docker compose restart

# 重启某个服务
docker compose restart backend

# 停止所有服务
docker compose down

# 启动所有服务
docker compose up -d

# 进入容器调试
docker compose exec backend bash

# 查看资源使用
docker stats
```

## 故障排查

### 服务启动失败

```bash
# 查看详细日志
docker compose logs backend

# 常见问题：
# 1. 端口被占用 → 修改 docker-compose.yml 端口映射
# 2. 内存不足 → 增加 Swap 或升级配置
# 3. 镜像拉取失败 → 配置 Docker 镜像加速
```

### 无法访问前端

```bash
# 检查 Nginx 是否运行
docker compose ps frontend

# 检查前端文件是否存在
docker compose exec frontend ls /usr/share/nginx/html

# 检查防火墙
ufw status
```

### 小红书采集失败

```bash
# 检查 cookies 是否有效
cat xhs/data/cookies.json

# 重新登录
docker compose --profile login up -d xhs-browser
```

## 更新代码

```bash
# 本地：上传新代码
./upload.sh

# 服务器：重新构建并重启
ssh root@118.89.71.196
cd /opt/travel-planner/deploy
docker compose build
docker compose up -d
```

## 备份数据

```bash
# 备份 SQLite 数据库
cp data/trips.db backup/trips_$(date +%Y%m%d).db

# 备份 cookies
cp xhs/data/cookies.json backup/cookies_$(date +%Y%m%d).json

# 下载到本地
scp root@118.89.71.196:/opt/travel-planner/deploy/data/trips.db ./backup/
```
