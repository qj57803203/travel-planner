# 旅行规划 Agent

个人自用的旅行规划工具：输入一句自然语言需求，自动抽取偏好、搜集信息、生成每日行程。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia + Axios |
| 后端 | Python + FastAPI + Pydantic + SQLAlchemy |
| Agent | LangChain + LangGraph（编排抽取 → 搜集 → 生成三步） |
| LLM | DeepSeek（`deepseek-chat`） |
| 存储 | SQLite |
| 数据源 | 预置固定示例数据（东京 / 大阪 / 巴黎） |

## 目录结构

```text
backend/
  app/
    main.py              # FastAPI 入口 + CORS
    config.py            # 环境变量配置
    schemas.py           # 接口 Pydantic 模型
    database.py          # SQLite 连接
    models.py            # Trip ORM 模型
    agent/
      state.py           # LangGraph 状态定义
      prompts.py         # 抽取 / 生成提示词
      nodes.py           # 三个节点：抽取偏好 / 搜集信息 / 生成行程
      graph.py           # 组装 DAG
    data/
      destinations.py    # 预置目的地数据
    routers/
      trips.py           # 行程接口：生成 / 列表 / 详情
frontend/
  src/
    views/Home.vue       # 三段式主页面
    components/          # TripForm / ItineraryView / ResearchPanel
    store/trip.ts        # Pinia store
    api/trips.ts         # 后端接口调用
    types/index.ts       # TS 类型
docs/PRD.md
```

## 快速开始

### 1. 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

# 复制并填写 DeepSeek API Key
cp .env.example .env

uvicorn app.main:app --reload
```

- 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

> `DEEPSEEK_API_KEY` 在 https://platform.deepseek.com 获取。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 （已配置 `/api` 代理到后端 8000 端口）。

## 接口说明

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/generate` | 传入 `{ "user_input": "..." }`，运行 Agent 并落库 |
| GET | `/api/trips` | 历史行程列表 |
| GET | `/api/trips/{id}` | 单个行程详情 |

## 核心链路

```text
用户输入 → POST /api/generate
  → LangGraph: 抽取偏好(LLM) → 匹配预置信息素材 → 生成行程(LLM)
  → 写入 SQLite → 返回结构化结果 → 前端渲染
```

## 后续扩展点

- **接入真实数据源**：替换 `app/data/destinations.py` 的 `research` 节点数据来源即可（如 Tavily 搜索、网页抓取），字段结构保持不变。
- **多轮修改**：在 LangGraph 中增加反馈环（用户说「太累了」→ 调整 pace 后重新生成）。
- **酒店对比 / 预算估算**：新增独立节点。
- **浏览器 MCP**：第四阶段用 Chrome DevTools MCP 读取登录后内容。
