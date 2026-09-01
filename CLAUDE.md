# 旅行规划 Agent

个人自用的旅行规划工具：输入一句自然语言需求，自动抽取偏好 → 搜集信息 → 生成每日行程。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia + Axios |
| 后端 | Python + FastAPI + Pydantic + SQLAlchemy |
| Agent 编排 | LangChain + LangGraph（抽取 → 搜集 → 生成三步 DAG） |
| LLM | DeepSeek（`deepseek-chat`） |
| 存储 | SQLite（`backend/trips.db`，启动时自动建表） |
| 数据源 | 预置固定示例数据（东京 / 大阪 / 巴黎），MVP 阶段无真实抓取 |

## 目录结构

```text
backend/
  app/
    main.py              # FastAPI 入口 + CORS + 启动建表
    config.py            # 环境变量配置（pydantic-settings，读 .env）
    schemas.py           # 接口入参/出参 + 数据结构 Pydantic 模型
    database.py          # SQLite 引擎 + SessionLocal + get_db 依赖
    models.py            # Trip ORM 模型
    agent/
      state.py           # AgentState 状态定义（跨节点共享数据）
      prompts.py         # EXTRACT_PROMPT / PLAN_PROMPT 提示词
      nodes.py           # 三个节点函数：抽取偏好 / 搜集信息 / 生成行程
      graph.py           # 组装 LangGraph DAG，导出 agent_graph
    data/
      destinations.py    # 预置目的地数据（东京/大阪/巴黎）
    routers/
      trips.py           # 行程接口：generate / list / detail
  .env.example           # DeepSeek Key 等环境变量样例
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

### 2. LangGraph 内部：三个节点串行执行

`graph.py` 里用 `StateGraph(AgentState)` 组装的 DAG，纯线性无分支：

```text
START → extract ──→ research ──→ plan ──→ END
        (LLM)        (纯代码)      (LLM)
```

| 节点 | 函数 | 干什么 | 关键点 |
|---|---|---|---|
| extract | `extract_preferences` | LLM 从自然语言抽取结构化偏好 | `temperature=0.0`；解析失败用默认值兜底，流程不中断 |
| research | `research` | 按目的地匹配预置四类素材 | 纯 Python 不调 LLM；目的地名做互为包含的模糊匹配 |
| plan | `generate_itinerary` | LLM 根据偏好+素材生成每日行程 | `temperature=0.7`；失败返回空 itinerary + error |

### 3. AgentState 字段流转

`state.py` 定义的状态，节点通过返回 dict 增量写入下一个节点可读到的字段：

```text
user_input ──[extract]──▶ preferences ──[research]──▶ research ──[plan]──▶ itinerary
```

- `user_input`：原始自然语言需求（入口传入）
- `preferences`：`{destination, days, pace, interests, hotel_preference}`
- `research`：`{destination, hotels[], attractions[], food[], transport[]}`
- `itinerary`：生成的行程文本（`Day 1 / Day 2` 分天）
- `error`：出错信息（可选，兜底时写入）

### 4. 支线流程

```text
历史列表：TripForm.vue onMounted → store.loadHistory() → GET /api/trips → 渲染左侧
查看详情：点击历史项 → store.openTrip(id) → GET /api/trips/{id} → 覆盖 store.current
重新生成：Home.vue onRegenerate() → 复用 store.current.user_input 再走一遍 generate
复制行程：Home.vue onCopy() → 前端 clipboard，纯前端不调后端
```

## 后端关键文件

- `main.py`：创建 FastAPI 实例，`Base.metadata.create_all()` 启动建表，配置 CORS（只放行 5173），挂载 `trips.router`，`/health` 健康检查。
- `config.py`：`Settings` 从 `.env` 读 `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DATABASE_URL`，默认 `deepseek-chat` 和 `sqlite:///./trips.db`。
- `database.py`：SQLite 需要 `check_same_thread=False` 才能在 FastAPI 线程池复用；`get_db()` 是请求级会话依赖。
- `models.py`：`Trip` 表，`preferences`/`research` 用 JSON 列，`itinerary` 用 Text，`created_at` 默认 `datetime.utcnow`。
- `nodes.py`：`_parse_json()` 容忍 markdown 代码块和多余说明，稳健解析 LLM 输出的 JSON；`_get_llm()` 统一创建 DeepSeek 实例。
- `data/destinations.py`：DESTINATIONS 字典，键是目的地名。**后续接真实数据源（搜索/抓取），只需改 `research` 节点的数据来源，保持字段结构不变。**

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
- **数据源是静态兜底**：MVP 阶段目的地只有东京/大阪/巴黎三个，`research` 找不到就返回空素材，`plan` 仍会基于空素材尽力生成。
- 若后端未启动，前端 error 会提示「生成失败，请检查后端服务是否启动」，问题多半在后端 8000 端口没起来。
- 环境变量缺失（未配 `DEEPSEEK_API_KEY`）会导致 extract/plan 节点失败，但流程会走兜底继续返回结果，注意别把「成功返回」误当成「LLM 正常工作了」。
