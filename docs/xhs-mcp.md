# 小红书 MCP 部署说明

本项目通过 [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 抓取小红书攻略笔记，作为行程生成的非结构化素材，与预置结构化数据（东京/大阪/巴黎）并存。

## 架构

```text
前端 → 后端 FastAPI → LangGraph research 节点
                        └─ 小红书 MCP（http://127.0.0.1:18060/mcp，优先）
                            └─ search_feeds → get_feed_detail → 笔记摘要
```

小红书 MCP 用 **Windows 二进制** 跑（原生 Chrome、可开有头窗口，绕开无头风控）。

> Docker 方式在本地登录时，Linux 无头 Chromium 会被小红书风控卡住（`get_login_qrcode` 拿不到二维码），实测不推荐。`deploy/xhs/docker-compose.yml` 仅作服务器部署备选。

## 前置条件

- 一个小红书账号（建议实名，新号可能触发实名提示）
- 网络可访问小红书

## 部署步骤

### 1. 下载二进制

从 [GitHub Releases](https://github.com/xpzouying/xiaohongshu-mcp/releases) 下载 v2.5.0 的 Windows 版两个文件：

- `xiaohongshu-login-windows-amd64.exe`（登录工具）
- `xiaohongshu-mcp-windows-amd64.exe`（MCP 服务）

放到 `deploy/xhs/bin/` 目录。

### 2. 扫码登录（首次必做）

```bash
cd deploy/xhs/bin
./xiaohongshu-login-windows-amd64.exe
```

- 首次运行自动下载内置浏览器（140-190MB，仅一次）
- 会弹出浏览器窗口，用小红书 App 扫码登录
- 登录成功后 cookie 保存在 `C:\Users\<你>\AppData\Local\xiaohongshu-mcp\`

> 若被杀毒软件（Windows Defender）误杀，把 `C:\Users\<你>\AppData\Local\Temp\leakless-*` 目录加入排除项。

### 3. 启动 MCP 服务

```bash
cd deploy/xhs/bin
./xiaohongshu-mcp-windows-amd64.exe
```

服务监听 `http://127.0.0.1:18060/mcp`（日志出现「启动 HTTP 服务器: :18060」即就绪）。

### 4. 配置后端

在 `backend/.env` 加：

```bash
XHS_MCP_URL=http://127.0.0.1:18060/mcp
```

不填（或留空）则禁用小红书搜索，走预置数据兜底。

### 5. 验证

生成行程时，前端「信息素材」出现「小红书攻略」区块即接入成功；后端日志出现 `xhs search_notes` 相关记录。

## 问题

- **搜索失败 / 为空**：未登录或 cookie 过期，重跑登录工具重新扫码。
- **被杀毒误杀**：把 `leakless-*` 临时目录加入 Defender 排除项。
- **首次启动慢**：下载内置浏览器 140-190MB，仅首次需要。
- **Docker 方式登录卡住**：无头 Chromium 被风控，改用 Windows 二进制。

## 安全说明

- 后端只调用 `search_feeds` / `get_feed_detail` 两个只读工具（[xhs_mcp.py](../backend/app/tools/xhs_mcp.py) 内硬编码白名单），从结构上杜绝误触发发帖/评论/点赞等写操作。
- cookie 与二进制在 `deploy/xhs/` 下，已加入 `.gitignore`，**切勿提交**。
