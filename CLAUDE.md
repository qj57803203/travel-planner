# 旅行规划 Agent

个人自用的旅行规划工具：输入一句自然语言需求，自动抽取偏好 → 搜集信息 → 生成每日行程。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia + Axios |
| 后端 | Python + FastAPI + Pydantic + SQLAlchemy |
| Agent 编排 | LangChain + LangGraph（抽取 → 搜集 → 生成三步 DAG） |
| LLM | DeepSeek（`deepseek-v4-flash`） |
| 存储 | SQLite（`backend/trips.db`，启动时自动建表） |
| 数据源 | 预置目的地数据 + 小红书攻略（MCP 实时爬取/缓存） + 高德地图（交通规划） |

## 目录结构

```text
backend/
  app/
    main.py              # FastAPI 入口 + CORS + 启动建表 + 日志配置
    config.py            # 环境变量配置（pydantic-settings，读 .env）
    schemas.py           # 接口入参/出参 + 数据结构 Pydantic 模型
    database.py          # SQLite 引擎 + SessionLocal + get_db 依赖
    models.py            # Trip / XhsNoteCache / UserProfile ORM 模型
    agent/
      state.py           # AgentState 状态定义（跨节点共享数据）
      prompts.py         # EXTRACT_PROMPT / PLAN_PROMPT 提示词
      nodes.py           # 四个节点函数：抽取偏好 / 搜集信息 / 生成行程 / 交通规划
      graph.py           # 组装 LangGraph DAG，导出 agent_graph
    data/
      destinations.py    # 预置目的地数据（多城市，含酒店/景点/美食/交通）
    tools/
      amap.py            # 高德地图 API 封装（地理编码 / 公交 / 步行 / 驾车）
      xhs_mcp.py         # 小红书攻略采集（MCP 协议，含缓存）
    routers/
      trips.py           # 行程接口：generate / generate/stream / list / detail
  .env.example           # 环境变量样例（DeepSeek Key / 高德 Key / 小红书配置）
  requirements.txt

frontend/
  src/
    views/Home.vue                 # 三段式主页面（输入 | 结果 | 底部操作）
    components/TripForm.vue        # 需求输入区 + 历史记录列表
    components/ItineraryView.vue   # 结果区：每日行程 / 信息素材 两个 tab
    components/ResearchPanel.vue   # 素材展示（酒店/景点/美食/交通折叠面板）
    store/trip.ts                  # Pinia store：状态 + 三个 action
    api/trips.ts                   # axios 封装，调后端接口
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
  → store/trip.ts generate() → api.generateTrip()
  → api/trips.ts POST /api/generate  { user_input: "..." }

[后端] routers/trips.py generate_trip()
  → 校验 user_input 非空
  → agent_graph.invoke({"user_input": ...})   # 跑 LangGraph
  → Trip 落库 SQLite（trips 表）
  → 返回 TripResponse

[前端] store.current = 返回的 Trip
  → ItineraryView.vue 渲染行程，ResearchPanel.vue 渲染素材
  → generate() 里再调 loadHistory() 刷新左侧历史列表
```

### 2. LangGraph 内部：四个节点串行执行

`graph.py` 里用 `StateGraph(AgentState)` 组装的 DAG，纯线性无分支：

```text
START → extract ──→ research ──→ plan ──→ transport ──→ END
        (LLM)        (纯代码)      (LLM)      (高德API)
```

| 节点 | 函数 | 干什么 | 关键点 |
|---|---|---|---|
| extract | `extract_preferences` | LLM 从自然语言抽取结构化偏好 | `temperature=0.0`；解析失败用默认值兜底，流程不中断 |
| research | `research` | 预置数据 + 小红书攻略采集 | 先查缓存，未命中则实时爬取；目的地名模糊匹配 |
| plan | `generate_itinerary` | LLM 根据偏好+素材生成每日行程 | `temperature=0.7`；输出含 days（景点序列）供交通节点使用 |
| transport | `plan_transport` | 查高德 API 生成真实交通 | 城际交通 + 逐天市内交通；结果注入行程 markdown |

### 3. AgentState 字段流转

`state.py` 定义的状态，节点通过返回 dict 增量写入下一个节点可读到的字段：

```text
user_input ──[extract]──▶ preferences ──[research]──▶ research ──[plan]──▶ itinerary + plan_days ──[transport]──▶ transit + itinerary(注入交通)
```

- `user_input`：原始自然语言需求（入口传入）
- `preferences`：`{destination, days, pace, interests, hotel_preference, departure}`
- `research`：`{destination, hotels[], attractions[], food[], transport[], xhs_notes[], xhs_status, xhs_error}`
- `itinerary`：生成的行程文本（含 `## Day 1` 等标题，transport 节点会注入交通段落）
- `plan_days`：每天景点序列 `[{"day": 1, "spots": ["景点A", "景点B"]}]`，供 transport 节点查高德
- `transit`：高德交通结果 `{source, inter_city, days[{day, legs[]}]}`
- `usage`：各 LLM 节点 token 用量 `{extract: {input, output}, plan: {input, output}}`
- `error`：出错信息（可选，兜底时写入）

### 4. 支线流程

```text
历史列表：TripForm.vue onMounted → store.loadHistory() → GET /api/trips → 渲染左侧
查看详情：点击历史项 → store.openTrip(id) → GET /api/trips/{id} → 覆盖 store.current
重新生成：Home.vue onRegenerate() → 复用 store.current.user_input 再走一遍 generate
复制行程：Home.vue onCopy() → 前端 clipboard，纯前端不调后端
```

## 后端关键文件

- `main.py`：创建 FastAPI 实例，`Base.metadata.create_all()` 启动建表，配置 CORS（只放行 5173），挂载 `trips.router`，`/health` 健康检查。**日志配置**：`logging.basicConfig(level=logging.DEBUG)` 用于调试。
- `config.py`：`Settings` 从 `.env` 读 `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DATABASE_URL` / `AMAP_WEB_KEY` / `XHS_*` 等。
- `database.py`：SQLite 需要 `check_same_thread=False` 才能在 FastAPI 线程池复用；`get_db()` 是请求级会话依赖。
- `models.py`：`Trip` 表（含 `usage`/`transit` JSON 列）、`XhsNoteCache` 表（小红书缓存）、`UserProfile` 表（记住出发地）。
- `nodes.py`：四个节点函数 + `_parse_json()` 稳健解析 + `_get_llm()` 统一创建实例。
- `tools/amap.py`：高德地图 API 封装（geocode / transit_route / walking_route / driving_route）。
- `tools/xhs_mcp.py`：小红书攻略采集，MCP 协议调用，含缓存机制（一周内有效）。
- `data/destinations.py`：多城市预置数据（酒店/景点/美食/交通四类素材）。

## 前端关键文件

- `store/trip.ts`：唯一数据源。`current`（当前行程）、`history`（历史列表）、`loading`、`error` 四个状态；`generate` / `loadHistory` / `openTrip` 三个 action。`loadHistory` 失败不阻塞主流程（catch 后静默）。
- `api/trips.ts`：axios 实例 `baseURL: '/api'`，`timeout: 120000`（生成涉及多次 LLM 调用，放宽超时）。
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

## 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/generate` | `{ "user_input": "..." }`，跑 Agent 并落库 |
| GET | `/api/trips` | 历史行程摘要列表 |
| GET | `/api/trips/{id}` | 单条行程完整详情 |

## 开发约定与注意点

- **LLM 调用只有两处**：`extract`（temperature=0.0，追求稳定抽取）和 `plan`（temperature=0.7，追求多样性）。改提示词去 `prompts.py`，改节点逻辑去 `nodes.py`。
- **节点间通信只靠 AgentState**：节点函数签名是 `(state: AgentState) -> dict`，返回的 dict 会 merge 进 state，不要用全局变量跨节点传数据。
- **数据源混合**：预置结构化数据（兜底）+ 小红书攻略（优先，有缓存）+ 高德地图（交通规划）。`research` 节点先查缓存再实时爬取。
- **日志级别约定**：业务日志统一用 `logger.info` 或 `logger.warning`，不要用 `logger.debug`（DEBUG 级别日志太多会淹没业务日志）。`main.py` 配置了 `logging.basicConfig(level=logging.DEBUG)`，但 httpcore/httpx 的 DEBUG 日志太多会淹没业务日志，可临时调高其级别：`logging.getLogger("httpcore").setLevel(logging.WARNING)`。

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
- 主表：`trips`（行程）、`xhs_note_cache`（小红书缓存）、`user_profiles`（用户偏好）

## 踩坑记录

### LLM 输出格式不稳定

DeepSeek 返回的 JSON 格式不一致，`_parse_json()` 用三层策略兜底：

1. **策略 1**：去除首尾 ` ```json ``` ` 代码块标记后解析
2. **策略 2**：正则提取 ` ```...``` ` 代码块内容
3. **策略 3**：找第一个 `{` 和最后一个 `}` 截取

**常见问题**：
- LLM 返回 Python 单引号格式 `{'key': 'value'}` 而非 JSON 双引号 `{"key": "value"}` → `_clean_json_text()` 用 `ast.literal_eval()` 转换
- LLM 返回数组 `[{...}]` 而非对象 `{...}` → `_ensure_dict()` 自动取第一个元素
- markdown 字段内嵌套一层 JSON → `_parse_plan()` 检测后自动剥层

**提示词要求**（在 `prompts.py` 中已强调）：
- 必须使用双引号（"），不能使用单引号（'）
- 不要用 markdown 代码块包裹，直接输出 JSON

### 高德 API 返回格式不一致

高德公交路径规划 API（`/v3/direction/transit/integrated`）的 `segments` 数组中，`walking`/`bus`/`railway` 字段在无数据时可能返回空数组 `[]` 而非空对象 `{}`。

**修复**：在 `amap.py` 的 `transit_route()` 中加 `isinstance(seg["walking"], dict)` 类型检查，避免对 list 调用 `.get()` 报错。

### 流式接口的 LangGraph astream 格式

`/api/generate/stream` 使用 `agent_graph.astream(state, stream_mode=["updates", "custom"])`，返回的 `data` 在新版 LangGraph 中可能是 list `[(node, update), ...]` 而非 dict，需要兼容：

```python
items = data.items() if isinstance(data, dict) else data
for node, update in items:
    state.update(update)
```

## 提交到 GitHub

仓库：<https://github.com/qj57803203/travel-planner> （`origin`，分支 `main`）。git 身份已配置为 `qinjie` / `qj57803203@gmail.com`，首次提交已推送完成。
如果要提交的代码，各改动区别很大，可以分多次来提交。（不超过三次）

注意点：

- `.env`（含 `DEEPSEEK_API_KEY`）、`*.db`（含 `-wal`/`-shm`）、`node_modules/`、`.venv/`、`__pycache__/` 等已写入 `.gitignore`，**真实 API Key 绝不能提交**，只提交 `.env.example` 模板。
- 首次 push 走 HTTPS + Git Credential Manager，凭证已缓存，之后 push 无需重复登录。
