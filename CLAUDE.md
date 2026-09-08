# 旅行规划 Agent

个人自用的旅行规划工具：输入一句自然语言需求，自动抽取偏好 → 搜集信息 → 生成每日行程。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia + Axios |
| 后端 | Python + FastAPI + Pydantic + SQLAlchemy |
| Agent 编排 | LangChain + LangGraph（抽取 → 搜集 → 生成 → 酒店搜索 → 交通五步 DAG） |
| LLM | DeepSeek（`deepseek-v4-flash`） |
| 存储 | SQLite（`backend/trips.db`，启动时自动建表） |
| 数据源 | 预置目的地数据 + 小红书攻略（MCP 协议，含缓存） + 携程酒店（Chrome CDP 直连爬虫） + 高德地图（交通规划） |

## 目录结构

```text
backend/
  app/
    main.py              # FastAPI 入口 + CORS + 启动建表 + 日志配置
    config.py            # 环境变量配置（pydantic-settings，读 .env）
    schemas.py           # 接口入参/出参 + 数据结构 Pydantic 模型
    database.py          # SQLite 引擎 + SessionLocal + get_db 依赖
    models.py            # Trip / UserProfile / XhsNoteCache / CtripCityCache / CtripHotelCache ORM 模型
    agent/
      state.py           # AgentState 状态定义（跨节点共享数据）
      prompts.py         # EXTRACT_PROMPT / MODIFY_EXTRACT_PROMPT / PLAN_PROMPT / MODIFY_PLAN_PROMPT 提示词
      nodes.py           # 五个节点函数：抽取偏好 / 搜集信息 / 生成行程 / 酒店搜索 / 交通规划
      graph.py           # 组装 LangGraph DAG，导出 agent_graph
    data/
      destinations.py    # 预置目的地数据（多城市，含酒店/景点/美食/交通）
    tools/
      amap.py            # 高德地图 API 封装（地理编码 / 铁路 / 地铁 / 步行 / 驾车）
      xhs_mcp.py         # 小红书攻略采集（MCP 协议，361 MiB，含只读白名单安全约束）
      chrome_manager.py  # Chrome CDP 连接管理器（WebSocket 直连 + 串行锁 + 自愈）
      ctrip_crawler.py   # 携程酒店爬虫（Chrome CDP 直连，URL 导航 + JS 提取）
    routers/
      trips.py           # 行程接口：generate / generate/stream / list / detail + 小红书登录 + 用户配置
  .env.example           # 环境变量样例（DeepSeek Key / 高德 Key / 小红书配置）
  requirements.txt

frontend/
  src/
    views/Home.vue                 # 主页面（输入 → 进度 → 结果 + 历史侧栏）
    components/
      TripForm.vue                 # 需求输入区 + 历史记录列表
      GenerateProgress.vue         # 五步进度条（与后端节点对齐，支持修改模式跳过 research）
      ItineraryView.vue            # 结果区：每日行程 / 信息素材 两个 tab + 推荐酒店
      HotelCard.vue                # 酒店卡片组件（图片/价格/评分/位置/跳转链接）
      ResearchPanel.vue            # 素材展示（酒店/景点/美食/交通折叠面板）
      MapRoute.vue                 # 高德地图路线可视化（城际 + 市内，AMap JS API）
      Icon.vue                     # 图标组件
    store/trip.ts                  # Pinia store：状态 + 五个 action（generate / modify / loadHistory / openTrip / saveDeparture）
    api/trips.ts                   # axios 封装 + SSE 流式接收（generateTripStream）
    types/index.ts                 # TS 类型（与后端 schemas.py 对齐）
  vite.config.ts                   # dev 代理 /api → http://localhost:8000

docs/PRD.md                        # 产品需求文档
docs/交通规划.md                    # 交通规划逻辑（城际/市内/注入行程）
```

## 核心流程走向（重点）

### 1. 一次「生成行程」的端到端调用链

```text
[前端] TripForm.vue 输入需求，点「生成行程」
  → onGenerate() → store.generate(input)
  → store/trip.ts generate() → api.generateTripStream(input, callback)
  → api/trips.ts POST /api/generate/stream  { user_input: "..." }
     （SSE 流式：逐个接收 stage/xhs_note 事件，done 事件携带完整 Trip）

[后端] routers/trips.py generate_trip_stream()
  → 校验 user_input 非空
  → agent_graph.astream(state, stream_mode=["updates", "custom"])
  → 每完成一个节点 → SSE 推送 stage 事件
  → research 节点内 → SSE 推送 xhs_note 事件（小红书逐篇）
  → 全部完成 → Trip 落库 SQLite → SSE 推送 done 事件（含完整 Trip）

[前端] store.current = done 事件里的 Trip
  → ItineraryView.vue 渲染行程，ResearchPanel.vue 渲染素材
  → generate() 里再调 loadHistory() 刷新左侧历史列表
```

### 2. LangGraph 内部：五个节点，修改模式有分支

`graph.py` 里用 `StateGraph(AgentState)` 组装的 DAG，主链路线性，修改模式下 extract 后有条件分支：

```text
START → extract ──→ research ──→ plan ──→ hotel_search ──→ transport ──→ END
        (LLM)        (纯代码)      (LLM)      (携程爬虫)       (高德API)
                ╲
                 ╲──→ plan（修改模式且目的地未变时跳过 research）
```

条件分支由 `_route_after_extract()` 判断：`is_modification=True` 且 `_destination_changed=False` 时直接进 plan，跳过 research（素材不变无需重新采集）。

| 节点 | 函数 | 干什么 | 关键点 |
|---|---|---|---|
| extract | `extract_preferences` | LLM 从自然语言抽取结构化偏好 | `temperature=0.0`；解析失败用默认值兜底，流程不中断 |
| research | `research` | 小红书攻略采集 | 先查缓存（7天有效），未命中则通过 MCP 协议实时爬取；目的地名模糊匹配 |
| plan | `generate_itinerary` | LLM 根据偏好+素材生成每日行程 | `temperature=0.7`；输出含 days（景点序列）供交通节点使用；**必须输出 accommodation_area（住宿建议）** |
| hotel_search | `hotel_search` | 根据住宿建议搜索携程酒店 | 从 accommodation_area 提取关键词（如"乐桥站"）；Chrome CDP 直连爬取携程（URL 导航 + JS 提取）；按性价比排序取前2个；注入行程 |
| transport | `plan_transport` | 查高德 API 生成真实交通 | 城际交通 + 逐天市内交通；结果注入行程 markdown |

### 3. AgentState 字段流转

`state.py` 定义的状态，节点通过返回 dict 增量写入下一个节点可读到的字段：

```text
user_input ──[extract]──▶ preferences ──[research]──▶ research ──[plan]──▶ itinerary + plan_days + accommodation_area ──[hotel_search]──▶ hotels + itinerary(注入酒店) ──[transport]──▶ transit + itinerary(注入交通)
```

- `user_input`：原始自然语言需求（入口传入）
- `profile_departure`：从用户配置读取的出发地（供 extract 兜底）
- `preferences`：`{destination, days, pace, interests, hotel_preference, departure}`
- `research`：`{destination, hotels[], attractions[], food[], transport[], xhs_notes[], xhs_status, xhs_error}`
- `itinerary`：生成的行程文本（含 `## Day 1` 等标题，hotel_search 节点会注入酒店推荐，transport 节点会注入交通段落）
- `plan_days`：每天景点序列 `[{"day": 1, "spots": ["景点A", "景点B"]}]`，供 transport 节点查高德
- `accommodation_area`：住宿区域建议（如"地铁1号线/4号线沿线（如乐桥站、临顿路站附近）"），供 hotel_search 节点提取关键词
- `transport_mode` / `transport_reason`：LLM 建议的城际交通方式及理由（`driving` / `train` / `flight`）
- `hotels`：携程酒店搜索结果 `[{name, price, rating, image, url, location}]`，供前端展示酒店卡片
- `transit`：高德交通结果 `{source, transport_mode, transport_reason, inter_city, days[{day, legs[]}]}`
- `transit_error`：交通规划失败原因（非空时前端展示提示）
- `usage`：各 LLM 节点 token 用量 `{extract: {input, output}, plan: {input, output}}`
- `error`：出错信息（可选，兜底时写入）
- `is_modification`：True = 修改模式，False = 首次生成
- `chat_history`：多轮对话历史 `[{"role": "user"|"assistant", "content": str}]`
- `previous_itinerary`：上一轮行程 markdown（供 plan 节点参考修改）
- `_destination_changed`：extract 节点输出，供 graph 条件分支判断是否跳过 research

### 4. 多轮对话（修改模式）

用户对已生成的行程提出修改意见时，传入 `trip_id` 触发修改模式：

```text
POST /api/generate  { user_input: "太累了，节奏放慢点", trip_id: 5 }
  → _initial_state() 加载上一轮的 preferences / research / itinerary / chat_history
  → extract（MODIFY_EXTRACT_PROMPT）：提取修改意图，合并到上一轮 preferences
  → 条件分支：目的地变了 → 走完整流程；目的地没变 → 跳过 research
  → plan（MODIFY_PLAN_PROMPT）：在上一轮行程基础上修改
  → hotel_search → transport → 落库（parent_id 指向链头，chat_history 累积）
```

- 最多 5 轮对话（`MAX_CHAT_ROUNDS = 5`），超过要求新建行程
- parent_id 始终指向链头（原始行程 ID），方便追溯
- 前端 store 的 `modify()` action 会传入当前 `current.value.id` 作为 `trip_id`

### 5. 支线流程

```text
历史列表：TripForm.vue onMounted → store.loadHistory() → GET /api/trips → 渲染左侧
查看详情：点击历史项 → store.openTrip(id) → GET /api/trips/{id} → 覆盖 store.current
重新生成：Home.vue onRegenerate() → 复用 store.current.user_input 再走一遍 generate
复制行程：Home.vue onCopy() → 前端 clipboard，纯前端不调后端
保存出发地：store.saveDeparture(departure) → POST /api/profile → 写入 user_profile 表
```

## 后端关键文件

- `main.py`：创建 FastAPI 实例，`Base.metadata.create_all()` 启动建表 + 轻量迁移（`ALTER TABLE ADD COLUMN`），配置 CORS（放行 5173 / 3000 / 线上 IP），挂载 `trips.router`，`/health` 健康检查。**日志配置**：`colorlog` 带颜色输出，`level=logging.INFO`，第三方库（httpcore/httpx/http11）自动调到 WARNING。
- `config.py`：`Settings`（pydantic-settings）从 `.env` 读 `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DATABASE_URL` / `AMAP_WEB_KEY` / `XHS_MCP_URL` / `CHROME_DEBUG_URL` / `CTRIPE_MCP_URL` 等。
- `database.py`：SQLite 需要 `check_same_thread=False` 才能在 FastAPI 线程池复用；`get_db()` 是请求级会话依赖。
- `models.py`：5 张表 —— `Trip`（行程，含 `usage`/`transit`/`hotels`/`chat_history`/`parent_id` JSON 列）、`UserProfile`（记住出发地）、`XhsNoteCache`（小红书缓存）、`CtripCityCache`（携程城市 ID 缓存，365天）、`CtripHotelCache`（携程酒店缓存，3天）。
- `nodes.py`：五个节点函数 + `_parse_json()` 稳健解析 + `_get_llm()` 统一创建实例 + `_strip_injected_blocks()` 清理注入内容。
- `graph.py`：组装 LangGraph DAG，含 `_route_after_extract()` 条件分支（修改模式跳过 research）。
- `tools/amap.py`：高德地图 API 封装（geocode / railway_route / metro_route / walking_route / driving_route）。
- `tools/xhs_mcp.py`：小红书攻略采集，MCP Streamable HTTP 协议调用，含只读白名单安全约束 + 缓存机制（7天有效）。
- `tools/chrome_manager.py`：Chrome CDP 连接管理器，WebSocket 直连 Docker 内常驻 Chrome，进程级串行锁 + 三层自愈。
- `tools/ctrip_crawler.py`：携程酒店爬虫，URL 导航 + JS 提取 DOM，城市 ID 缓存 365 天 + 酒店结果缓存 3 天。
- `data/destinations.py`：多城市预置数据（酒店/景点/美食/交通四类素材）。

## 前端关键文件

- `store/trip.ts`：唯一数据源。`current`（当前行程）、`history`（历史列表）、`loading`、`error`、`stages`（五步进度）、`xhsNotes`（实时采集的小红书笔记）六个状态；`generate` / `modify` / `loadHistory` / `openTrip` / `saveDeparture` 五个 action。`loadHistory` 失败不阻塞主流程（catch 后静默）。`markStageDone()` 会自动补齐被跳过的中间阶段（修改模式下 research 被跳过）。
- `api/trips.ts`：axios 实例 `baseURL: '/api'`，`timeout: 120000`。`generateTripStream()` 用 SSE 流式接收进度事件（stage / xhs_note / done / error）。
- `components/GenerateProgress.vue`：五步进度条，与后端 STAGES 对齐（extract → research → plan → hotel_search → transport）。
- `components/MapRoute.vue`：高德地图 JS API 路线可视化，渲染城际 + 市内交通的 polyline。
- `vite.config.ts`：`@` 别名指向 `src`；dev 下 `/api` 代理到后端 8000。
- 前后端类型对齐：`frontend/src/types/index.ts` 与 `backend/app/schemas.py` 字段一一对应，改接口时两边要同步。

## 启动方式

### 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 填入 DEEPSEEK_API_KEY
uvicorn app.main:app --reload
```

- 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 前端

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173，/api 已代理到 8000
```

### Chrome 调试模式（可选，用于携程酒店爬虫）

```bash
# Windows：启动带调试端口的 Chrome
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

- 调试端口：http://127.0.0.1:9222（默认，可通过 `CHROME_DEBUG_URL` 配置）
- 在 `backend/.env` 中配置：`CHROME_DEBUG_URL=http://127.0.0.1:9222`（非空即启用携程爬虫）
- 爬虫通过原生 CDP WebSocket 直连 Chrome，无需 MCP 中间层
- 线上部署：Docker Compose 中 Chrome 容器绑定 `127.0.0.1:9223`，后端容器 `network_mode: host` 直连

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/generate` | `{ "user_input": "...", "trip_id": null }`，同步生成并落库（含酒店搜索） |
| POST | `/api/generate/stream` | 同上，SSE 流式返回进度 + 最终结果（前端主力接口） |
| GET | `/api/trips` | 历史行程摘要列表（目的地、天数、创建时间） |
| GET | `/api/trips/{id}` | 单条行程完整详情（含 hotels / transit / chat_history） |
| GET | `/api/profile` | 读取用户记住的出发地 |
| POST | `/api/profile` | `{ "departure": "上海" }` 保存出发地 |
| GET | `/api/xhs-qrcode` | 获取小红书登录二维码（MCP 方案，返回 base64 图片） |
| GET | `/api/xhs-login-status` | 检查小红书登录状态 |
| GET | `/api/xhs-cookies` | 查询小红书 Cookie 配置状态 |
| GET | `/health` | 健康检查 |

## 开发约定与注意点

- **LLM 调用只有两处**：`extract`（temperature=0.0，追求稳定抽取）和 `plan`（temperature=0.7，追求多样性）。修改模式下分别使用 `MODIFY_EXTRACT_PROMPT` 和 `MODIFY_PLAN_PROMPT`。改提示词去 `prompts.py`，改节点逻辑去 `nodes.py`。
- **节点间通信只靠 AgentState**：节点函数签名是 `(state: AgentState) -> dict`，返回的 dict 会 merge 进 state，不要用全局变量跨节点传数据。
- **数据源三路**：小红书攻略（MCP 协议，有缓存 7 天）+ 携程酒店（Chrome CDP 直连爬取）+ 高德地图（交通规划）。`research` 节点先查缓存再实时爬取。
- **携程酒店爬虫**：`hotel_search` 节点从 `accommodation_area` 提取关键词（如"乐桥站"），通过 Chrome CDP 直连爬取携程。流程：① 调携程 API 获取城市 ID（`getHotelKeywords`，缓存 365 天）→ ② 拼 URL 直接导航到搜索结果页 → ③ JS 直读 DOM 提取酒店卡片。按性价比排序取前2个注入行程。**前提**：需要启动带 `--remote-debugging-port=9222` 的 Chrome（线上通过 Docker 共享网络）。**缓存机制**：城市 ID 缓存 365 天，酒店结果缓存 3 天。
- **日志级别约定**：业务日志统一用 `logger.info` 或 `logger.warning`，不要用 `logger.debug`。`main.py` 已配置 `colorlog` 带颜色输出 + `level=logging.INFO`，第三方库（httpcore/httpx/http11）自动调到 WARNING，无需手动处理。

### 直接操作 SQLite 数据库

系统无 `sqlite3` 命令行工具，用 Python 操作：

```bash
cd backend
python -c "
import sqlite3
conn = sqlite3.connect('trips.db')
c = conn.cursor()
c.execute('SELECT id, substr(user_input, 1, 50) FROM trips')  # 查看
c.execute('DELETE FROM trips WHERE id BETWEEN 18 AND 23')      # 删除
conn.commit()
conn.close()
"
```

- 路径：`backend/trips.db`
- 主表：`trips`（行程）、`xhs_note_cache`（小红书缓存）、`ctrip_hotel_cache`（携程酒店缓存）、`ctrip_city_cache`（携程城市 ID 缓存）、`user_profiles`（用户偏好）

## 踩坑记录

### LLM 输出格式不稳定

DeepSeek 返回的 JSON 格式不稳定，当前已启用 `response_format=json_object` 强制 JSON 输出，但仍有多层兜底：

**`_parse_json()`**：直接 `json.loads` 解析（已启用 json_mode）。兜底：返回数组 `[{...}]` 时自动取第一个元素。

**`_parse_plan()`**（解析行程 JSON）：
1. `_parse_json` 解析 → 取 `markdown` 字段
2. `markdown` 字段以 `{` 开头 → 嵌套 JSON，剥一层再取
3. 正则挽救：从原始 content 提取 `"markdown": "..."` 字段
4. 全部失败 → 抛 ValueError（前端展示错误提示）

**提示词要求**（在 `prompts.py` 中已强调）：
- 必须使用双引号（"），不能使用单引号（'）
- 不要用 markdown 代码块包裹，直接输出 JSON

### 高德 API 返回格式不一致

高德公交路径规划 API 的 `segments` 数组中，`walking`/`bus`/`railway` 字段在无数据时可能返回空数组 `[]` 而非空对象 `{}`。

**修复**：在 `amap.py` 中加 `isinstance(seg["walking"], dict)` 类型检查，避免对 list 调用 `.get()` 报错。

### 高德地理编码国外地名会返回中国坐标

高德地图地理编码 API 只支持中国境内地名。对国外地名（如"东京浅草寺"）会错误返回中国境内坐标，导致路线画在中国。

**修复**：`_build_legs()` 检测到国外目的地时直接跳过高德地理编码，返回提示信息。维护一份 `foreign_cities` 集合做判断。

### 流式接口的 LangGraph astream 格式

`/api/generate/stream` 使用 `agent_graph.astream(state, stream_mode=["updates", "custom"])`，返回的 `data` 在新版 LangGraph 中可能是 list `[(node, update), ...]` 而非 dict，需要兼容：

```python
items = data.items() if isinstance(data, dict) else data
for node, update in items:
    state.update(update)
```

### 前端 SSE 流式接收

`generateTripStream()` 用 `fetch` + `ReadableStream` 解析 SSE，不能用 axios（axios 不支持流式读取）。每收到一个 `data:` 帧就解析并回调，`done` 事件携带完整 Trip 数据。

## 提交到 GitHub

仓库：<https://github.com/qj57803203/travel-planner> （`origin`，分支 `main`）。git 身份已配置为 `qinjie` / `qj57803203@gmail.com`。

- remote 已切换为 SSH 协议：`git@github.com:qj57803203/travel-planner.git`
- SSH key 路径：`~/.ssh/id_ed25519`（ed25519，邮箱 qj57803203@gmail.com）
- 如果要提交的代码，各改动区别很大，可以分多次来提交。（不超过三次）

注意点：

- `.env`（含 `DEEPSEEK_API_KEY`）、`*.db`（含 `-wal`/`-shm`）、`node_modules/`、`.venv/`、`__pycache__/` 等已写入 `.gitignore`，**真实 API Key 绝不能提交**，只提交 `.env.example` 模板。

# 部署
## 本地远程连接命令
ssh ubuntu@118.89.71.196

## 更新代码
用子agent执行，参考 deploy\部署更新文档.md 中的 更新代码章节