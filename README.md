# 旅行规划 Agent

输入一句自然语言需求，自动抽取偏好 → 搜集小红书攻略素材 → 生成每日行程 → 搜索酒店 → 规划交通，全流程自动化。

<img width="2196" height="1274" alt="image" src="https://github.com/user-attachments/assets/6d5f919e-5785-4ea8-b0a9-650875d8d1c1" />

---

## 核心流程

一次「生成行程」的端到端数据流：

```text
用户输入 "十一去苏州玩3天，喜欢园林和美食"
        │
        ▼
  ┌─────────────┐    DeepSeek (temp=0.0)     ┌──────────────────────────────────┐
  │   extract    │ ─────────────────────────▶ │  preferences:                    │
  │  抽取偏好     │    结构化 JSON 输出          │    destination: "苏州"            │
  │  (LLM)      │                            │    days: 3, pace: "适中"          │
  └─────────────┘                            │    interests: ["园林", "美食"]     │
        │                                    │    departure: "上海"              │
        ▼                                    └──────────────────────────────────┘
  ┌─────────────┐    小红书 MCP 搜索+详情      ┌──────────────────────────────────┐
  │  research   │ ─────────────────────────▶ │  research:                       │
  │  搜集素材     │    先查 SQLite 缓存(7天)     │    xhs_notes: [{title, summary}] │
  │  (纯代码)    │    未命中 → MCP 实时爬取      │    xhs_status: "live" | "cached" │
  └─────────────┘    命中 → 直接返回缓存        └──────────────────────────────────┘
        │
        ▼
  ┌─────────────┐    DeepSeek (temp=0.7)     ┌──────────────────────────────────┐
  │    plan     │ ─────────────────────────▶ │  itinerary: "## Day 1 ..."       │
  │  生成行程     │    结构化 JSON 输出          │  plan_days: [{day, spots}]       │
  │  (LLM)      │    含每天景点序列             │  accommodation_area: "观前街附近" │
  └─────────────┘    + 住宿区域建议            └──────────────────────────────────┘
        │
        ▼
  ┌─────────────┐    携程 CDP 爬虫            ┌──────────────────────────────────┐
  │ hotel_search│ ─────────────────────────▶ │  hotels: [{name, price, rating}] │
  │  搜索酒店     │    从住宿建议提取关键词       │  itinerary: (注入酒店推荐)        │
  │  (携程爬虫)  │    搜索 → 排序 → 取前2个     └──────────────────────────────────┘
  └─────────────┘
        │
        ▼
  ┌─────────────┐    高德地图 Web API         ┌──────────────────────────────────┐
  │  transport  │ ─────────────────────────▶ │  transit: {inter_city, days[]}   │
  │  规划交通     │    城际: 驾车/高铁/飞机      │  itinerary: (注入交通段落)        │
  │  (高德API)  │    市内: 步行<2km 否则比选     └──────────────────────────────────┘
  └─────────────┘
        │
        ▼
   写入 SQLite ──→ SSE 推送前端 ──→ 渲染行程 + 酒店卡片 + 地图路线
```

### 各节点数据从哪来

| 节点 | 做什么 | 数据来源 | 关键点 |
|---|---|---|---|
| **extract** | 从自然语言抽取结构化偏好 | DeepSeek LLM | `temperature=0.0` 追求稳定；解析失败用默认值兜底 |
| **research** | 搜集目的地攻略素材 | 小红书 MCP（xpzouying/xiaohongshu-mcp） | 先查 SQLite 缓存（7天有效），未命中才实时爬取；目的地名模糊匹配 |
| **plan** | 根据偏好 + 素材生成每日行程 | DeepSeek LLM | `temperature=0.7` 追求多样性；输出含 `plan_days`（景点序列）供交通节点用 |
| **hotel_search** | 根据住宿建议搜索酒店 | 携程（Chrome CDP 直连爬虫） | 从 `accommodation_area` 提取关键词 → 携程搜索 → 按性价比排序取前2个 |
| **transport** | 查真实交通并注入行程 | 高德地图 Web API | 城际交通 + 逐天市内交通；<2km 步行，否则对比驾车/地铁耗时 |

### 节点间通信：AgentState

五个节点通过 `AgentState`（TypedDict）共享数据，节点函数签名 `(state) -> dict`，返回的 dict 增量 merge 进 state：

```text
user_input ──▶ preferences ──▶ research ──▶ itinerary + plan_days + accommodation_area ──▶ hotels + itinerary ──▶ transit + itinerary
```

每个节点只写自己负责的字段，下游节点通过 `state["key"]` 读取上游产出。

### 修改模式（多轮对话）

用户对已生成的行程说"太累了，节奏放慢点"时，走修改模式：

```text
POST /api/generate  { user_input: "太累了", trip_id: 5 }
                            │
                            ▼
                    extract（修改意图提取）
                    从 user_input 提取修改意图，合并到上一轮 preferences
                            │
                            ├── 目的地变了 → 走完整流程（research → plan → hotel → transport）
                            │
                            └── 目的地没变 → 跳过 research，直接 plan → hotel → transport
```

修改模式下 `plan` 节点使用 `MODIFY_PLAN_PROMPT`，会把上一轮行程 + 对话历史一起给 LLM，在原基础上修改。最多支持 5 轮对话。

---

## 技术要点

### 1. LangGraph 编排（五节点 DAG）

用 `StateGraph(AgentState)` 组装，主链路纯线性，修改模式下 extract 后有条件分支：

```python
# graph.py
START → extract ──→ research ──→ plan ──→ hotel_search ──→ transport ──→ END
                ╲
                 ╲──→ plan (修改模式且目的地未变时跳过 research)
```

- 节点函数返回 dict → LangGraph 自动 merge 进 state
- 流式模式 `astream(stream_mode=["updates", "custom"])`：`updates` 推送节点完成事件，`custom` 推送小红书采集进度

### 2. 小红书攻略采集（MCP 协议）

通过 [xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 的 MCP Streamable HTTP 协议采集：

```text
XHS_MCP_URL 未配置 → 跳过（enabled()=False）
XHS_MCP_URL 已配置 → 搜索笔记 → 逐篇取详情 → 写入缓存
                          │
                          ├── 有缓存（7天内、同目的地）→ 秒回
                          └── 无缓存 → 实时爬取，逐篇通过 SSE 推给前端
```

**安全约束**：MCP 暴露了 publish/comment/like 等写操作，代码硬编码只读白名单（`search_notes`、`get_note_detail`、`get_login_qrcode`、`check_login_status`），让越权在结构上不可能。

### 3. 携程酒店爬虫（Chrome CDP 直连）

去掉 MCP 中间层，直接通过 WebSocket 协议控制 Docker 内常驻 Chrome：

```text
getHotelKeywords API（城市名 → 城市 ID，长期缓存 365 天）
        │
        ▼
拼 URL: https://m.ctrip.com/html5/hotel/hotellist/{cityId}/...
        │
        ▼
CDP WebSocket → page.goto(url) → page.evaluate(JS提取DOM)
        │
        ▼
解析酒店卡片 → 按性价比排序（价格/评分）→ 取前2个
```

- **缓存**：城市 ID 缓存 365 天，酒店搜索结果缓存 3 天
- **自愈**：Chrome 不可达 → `enabled()=False`，调用方跳过；超时/异常 → 返回空列表，不阻塞主流程
- **串行锁**：进程级 `threading.Lock()`，同一时刻只允许一个操作控制 Chrome

### 4. 高德地图交通规划

用高德 Web 服务 API（需申请 key）做两件事：

**城际交通**（有出发地时）：
- LLM 建议交通方式（`driving` / `train` / `flight`）
- 驾车 → `amap.driving_route()`；高铁 → `amap.railway_route()`；飞机 → 文字提示
- 国外目的地跳过高德（只支持中国境内），给文字提示

**市内交通**（逐天、相邻景点两两查）：
- 先查驾车获取距离 → <2km → 步行
- ≥2km → 对比驾车和地铁耗时，选耗时短的
- 结果注入行程 markdown，穿插在景点之间（🚶步行 / 🚇地铁 / 🚗驾车）

### 5. LLM 输出解析的兜底策略

DeepSeek 输出格式不稳定，`_parse_json()` + `_parse_plan()` 用多层策略兜底：

```text
_parse_json:
  1. json.loads 直接解析（已启用 response_format=json_object）
  2. 返回数组 [{...}] → 自动取第一个元素

_parse_plan:
  1. _parse_json 解析 → 取 markdown 字段
  2. markdown 字段以 "{" 开头 → 嵌套 JSON，剥一层再取
  3. 正则挽救：从原始 content 提取 "markdown": "..." 字段
  4. 全部失败 → 抛 ValueError（前端展示错误提示）
```

### 6. 流式进度推送（SSE）

前端通过 SSE 实时接收进度：

```text
data: {"type": "stage", "stage": "extract", "status": "done", "message": "偏好已确认"}
data: {"type": "xhs_note", "index": 0, "title": "苏州3日游攻略", "cover": "..."}  ← 小红书逐篇推送
data: {"type": "stage", "stage": "research", "status": "done", "message": "素材已就绪"}
data: {"type": "stage", "stage": "plan", "status": "done", "message": "行程已生成"}
data: {"type": "stage", "stage": "hotel_search", "status": "done", "message": "酒店已搜索"}
data: {"type": "stage", "stage": "transport", "status": "done", "message": "交通已规划"}
data: {"type": "done", "trip": {...完整行程数据...}}
```

前端 `store/trip.ts` 的 STAGES 数组与后端节点顺序对齐，逐个标记 `pending → running → done`。

---

## 项目结构

```text
backend/
  app/
    main.py              # FastAPI 入口 + CORS + 启动建表 + 轻量迁移 + 北京时间日志
    config.py            # pydantic-settings 从 .env 读配置
    schemas.py           # 接口入参/出参 Pydantic 模型（与前端 types/index.ts 对齐）
    database.py          # SQLite 引擎 + SessionLocal + get_db 依赖
    models.py            # 5 张表：Trip / UserProfile / XhsNoteCache / CtripCityCache / CtripHotelCache
    agent/
      state.py           # AgentState（TypedDict）—— 节点间共享数据的唯一通道
      prompts.py         # EXTRACT_PROMPT / MODIFY_EXTRACT_PROMPT / PLAN_PROMPT / MODIFY_PLAN_PROMPT
      nodes.py           # 五个节点：extract_preferences / research / generate_itinerary / hotel_search / plan_transport
      graph.py           # 组装 LangGraph DAG，含修改模式条件分支
    data/
      destinations.py    # 预置目的地数据（酒店/景点/美食/交通，多城市）
    tools/
      amap.py            # 高德地图 API 封装（地理编码 / 铁路 / 地铁 / 步行 / 驾车）
      xhs_mcp.py         # 小红书 MCP 客户端（搜索 / 详情 / 登录二维码）
      chrome_manager.py  # Chrome CDP 连接管理器（WebSocket 直连 + 串行锁 + 自愈）
      ctrip_crawler.py   # 携程酒店爬虫（URL 导航 + JS 提取 DOM）
    routers/
      trips.py           # 行程接口：generate / generate/stream / list / detail + 小红书登录
  .env.example           # 环境变量模板

frontend/
  src/
    views/Home.vue                 # 主页面（输入 → 进度 → 结果 + 历史侧栏）
    components/
      TripForm.vue                 # 需求输入区 + 历史记录列表
      GenerateProgress.vue         # 五步进度条（与后端节点对齐）
      ItineraryView.vue            # 行程展示（每日行程 / 信息素材 tab + 酒店卡片）
      HotelCard.vue                # 酒店卡片（图片/价格/评分/位置/跳转链接）
      ResearchPanel.vue            # 素材面板（酒店/景点/美食/交通折叠展示）
      MapRoute.vue                 # 高德地图路线可视化（城际 + 市内）
    store/trip.ts                  # Pinia store：状态 + generate / modify / loadHistory / openTrip
    api/trips.ts                   # axios 封装 + SSE 流式接收
    types/index.ts                 # TS 类型（与后端 schemas.py 一一对应）
  vite.config.ts                   # dev 代理 /api → http://localhost:8000

docs/
  PRD.md                           # 产品需求文档
  交通规划.md                       # 交通规划逻辑详解
  方案-*.md                         # 各功能方案设计文档
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Node 18+
- （可选）Chrome 带 `--remote-debugging-port=9222`（携程酒店爬虫需要）

### 你需要准备的

| 项 | 必需 | 从哪来 |
|---|---|---|
| `DEEPSEEK_API_KEY` | ✅ | [platform.deepseek.com](https://platform.deepseek.com)，按量付费 |
| `AMAP_WEB_KEY` | ✅ | [高德开放平台](https://console.amap.com/dev/key/app)，服务平台选 **Web服务** |
| `XHS_MCP_URL` | ❌ | 自建 [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp)，不配则跳过小红书采集 |
| `CHROME_DEBUG_URL` | ❌ | `http://127.0.0.1:9222`，不配则跳过携程酒店搜索 |

> `.env` 已在 `.gitignore` 中，真实密钥不会进版本库。

### 启动后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env    # 填入 DEEPSEEK_API_KEY

uvicorn app.main:app --reload
```

- 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173（`/api` 已代理到后端 8000 端口）。

### （可选）启动 Chrome 调试模式

```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

在 `backend/.env` 中配置 `CHROME_DEBUG_URL=http://127.0.0.1:9222` 即可启用携程酒店爬虫。

---

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/generate` | `{ "user_input": "...", "trip_id": null }`，同步生成并落库 |
| `POST` | `/api/generate/stream` | 同上，SSE 流式返回进度 + 最终结果 |
| `GET` | `/api/trips` | 历史行程摘要列表（目的地、天数、创建时间） |
| `GET` | `/api/trips/{id}` | 单条行程完整详情（含 hotels / transit / chat_history） |
| `GET` | `/api/profile` | 读取用户记住的出发地 |
| `POST` | `/api/profile` | `{ "departure": "上海" }` 保存出发地 |
| `GET` | `/api/xhs-qrcode` | 获取小红书登录二维码（MCP 方案） |
| `GET` | `/api/xhs-login-status` | 检查小红书登录状态 |
| `GET` | `/health` | 健康检查 |

---

## 部署

线上部署在 Docker Compose，包含三个容器：

```text
┌──────────────────────────────────────────────────────────────┐
│  docker-compose                                              │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  chrome       │  │  backend     │  │  frontend    │       │
│  │  (headless)   │←─│  (FastAPI)   │  │  (nginx)     │       │
│  │  :9223 CDP    │  │  :8000       │  │  :80         │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         ↑                  │                                  │
│         └── network_mode: host（共享网络，直连 localhost）      │
└──────────────────────────────────────────────────────────────┘
```

- **Chrome 容器**：常驻 headless Chrome，绑定 `127.0.0.1:9223`
- **Backend 容器**：`network_mode: host`，直连 Chrome 的 CDP 端口
- **Frontend 容器**：nginx 托管构建产物，反代 `/api` 到后端

详细部署步骤见 [deploy/部署更新文档.md](deploy/部署更新文档.md)。

---

## 后续扩展

- **更多数据源**：小红书已接入，可照同样方式加 Tavily 搜索、网页抓取
- **多轮对话优化**：当前最多 5 轮，可扩展为无限轮 + 上下文压缩
- **预算估算**：新增独立节点，根据酒店价格 + 门票 + 交通估算总费用
- **地图增强**：高德地图 JS API 互动地图（缩放、点选、路线编辑）

---

## 许可证

MIT — 个人项目，随便看、随便改。
