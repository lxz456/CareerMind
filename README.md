# CareerMind AI

基于大语言模型、LangGraph 和混合检索的职业规划与自适应模拟面试平台。

CareerMind AI 面向求职者提供简历分析、真实岗位检索、技能差距评估、职业学习规划、自适应模拟面试以及题库/学习资源检索。项目采用前后端分离架构，后端通过两个持久化 LangGraph 工作流组织 LLM 应用能力。

> 当前定位：单机 Demo / 学习与求职展示项目。项目已经具备完整的 LLM 应用工程链路，但不是能够自由规划并自主选择任意工具的通用 ReAct Agent。

## 核心功能

### 路径 A：规划提升

- 上传 PDF 或 DOCX 简历并提取文本；
- 根据用户必填的目标职位调用 JSearch 搜索真实岗位；
- 简历分析与岗位搜索并行执行；
- 综合简历技能和多个岗位要求生成技能差距；
- 生成简体中文的月度职业发展计划；
- 通过 Tavily 为规划任务补充真实学习资料；
- 使用后台 `asyncio.Task` 执行长任务，前端轮询展示进度；
- 后端重启后将未完成任务标记为 `interrupted`，由用户在个人中心手动继续。

```text
                    ┌─ resume_analysis ─┐
START ──────────────┤                    ├─ skill_gap ─ career_plan ─ summary ─ END
                    └─ job_search ──────┘
```
ene
### 路径 B：自适应模拟面试

- 支持 HR、技术、系统设计和混合面试；
- 支持“复习巩固”和“进阶提升”两种模式；
- 面试题由 LLM 生成，复习模式优先复用 RAG 题库；
- 使用 LangGraph `interrupt()` 暂停并等待用户回答；
- 使用 `Command(resume=...)` 从相同 checkpoint 恢复；
- 对回答进行 0～10 分评价，每道基础题最多追问一次；
- 根据整道题表现动态升高、保持或降低下一题难度；
- 回答接口使用 SSE 输出评估、决策和下一题生成阶段事件；
- 刷新页面或重新登录后，可从面试历史继续未完成会话。

```text
START
  └─ initialize
       └─ prepare_question
            └─ ask_question
                 └─ wait_for_answer ── interrupt
                          ▲                 │
                          │          Command(resume=answer)
                          │                 │
                          └─ decide ◀─ evaluate
                               ├─ follow_up ── ask_question
                               ├─ next_question ── prepare_question
                               └─ finish ── build_report ── END
```

### 题库 / 学习中心

- SQLite FTS5 BM25 关键词召回；
- ChromaDB 向量语义召回；
- 按稳定业务 ID 合并去重；
- 使用 RRF（`k=60`）进行无量纲排名融合；
- 使用本地 `BAAI/bge-reranker-v2-m3` 精排；
- 最终返回带相关性分数的 Top 20；
- 面试题和学习资源统一双写关系数据库与向量数据库，并在入库前去重。

```text
用户查询
  ├─ SQLite FTS5 BM25 Top 50
  └─ Chroma 向量检索 Top 50
                │
          按业务 ID 合并去重
                │
           RRF 排名融合
                │
          保留候选 Top 50
                │
    BAAI/bge-reranker-v2-m3
                │
          最终返回 Top 20
```

## 技术栈

| 范围 | 技术 |
|---|---|
| 前端 | Vue 3、Vite、Element Plus、Pinia、Vue Router、Axios |
| Web 后端 | FastAPI、Pydantic v2、Uvicorn、Python AsyncIO |
| Agent 编排 | LangGraph、LangChain Core |
| LLM | 阿里云百炼 DashScope OpenAI 兼容接口、通义千问 |
| 数据访问 | SQLAlchemy 2 Async、aiosqlite |
| 业务数据库 | SQLite、WAL、FTS5 |
| 短期记忆 | LangGraph `AsyncSqliteSaver` |
| 向量检索 | ChromaDB、DashScope `text-embedding-v3` |
| 精排 | Transformers、PyTorch、`BAAI/bge-reranker-v2-m3` |
| 外部数据 | JSearch、Tavily |
| 文件解析 | PyMuPDF、PyPDF2、python-docx |
| 鉴权 | JWT、FastAPI 依赖注入 |

## 总体架构

```text
┌────────────────────────────── Frontend ──────────────────────────────┐
│ Vue 3 / Vite / Element Plus                                         │
│ 规划提升 / 模拟面试 / 题库学习中心 / 个人中心                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP JSON / multipart / SSE
┌───────────────────────────────▼──────────────────────────────────────┐
│ FastAPI                                                             │
│ API → Service → Repository → SQLAlchemy Model                       │
│          └→ Agent → Tool / LLM / Memory                             │
└───────────────┬──────────────────┬─────────────────┬────────────────┘
                │                  │                 │
       SQLite 业务数据库   SQLite Checkpoint     ChromaDB
       用户/简历/历史       LangGraph 状态         知识向量
                │                  │                 │
                └────────────── 外部服务 ────────────┘
                         DashScope / JSearch / Tavily
```

后端遵循以下主要依赖方向：

```text
api → services → repositories → models / vector_store
        └→ agents → tools → llm
                    └→ repositories（RAG 检索与知识缓存）
```

## 项目目录

```text
CareerMind/
├─ backend/
│  ├─ app/
│  │  ├─ api/              # FastAPI 路由、鉴权依赖、请求响应
│  │  ├─ services/         # 业务编排、事务、后台任务和图的启动
│  │  ├─ repositories/     # SQLite 与 Chroma 数据访问
│  │  ├─ models/           # SQLAlchemy ORM 模型
│  │  ├─ schemas/          # Pydantic 数据契约
│  │  ├─ agents/           # 两条 LangGraph、状态和路径 A 节点
│  │  ├─ llm/              # LLM、Embedding、提示词和 BGE 精排
│  │  ├─ tools/            # JSearch、Tavily、面试和学习资源工具
│  │  ├─ memory/           # SQLite checkpointer 生命周期
│  │  ├─ core/             # 日志等基础设施
│  │  ├─ utils/            # JWT、文件解析、重试工具
│  │  ├─ database.py       # 异步 SQLAlchemy 与 SQLite 初始化
│  │  ├─ vector_store.py   # ChromaDB 通用封装
│  │  └─ main.py           # FastAPI 应用入口
│  ├─ scripts/             # 数据回填脚本
│  ├─ DEVELOPMENT.md       # 完整实现文档
│  └─ requirements.txt     # Python 依赖唯一清单
├─ frontend/
│  ├─ src/
│  │  ├─ api/              # 前端请求封装
│  │  ├─ components/       # 公共组件
│  │  ├─ views/            # 功能页面
│  │  ├─ router/           # 路由和登录守卫
│  │  └─ stores/           # Pinia 状态
│  ├─ package.json         # Node 依赖和脚本
│  └─ .env.example         # 前端环境变量示例
├─ requirements.txt        # 根目录安装入口，引用后端依赖
├─ .gitignore
└─ README.md
```

## 快速开始

### 1. 环境要求

- Python 3.11 或更高版本；
- Node.js 20 或更高版本；
- npm；
- 可访问 DashScope、JSearch 和 Tavily 的网络；
- BGE 精排可使用 CPU；有兼容 CUDA 的 PyTorch 时可自动使用 NVIDIA GPU。

### 2. 获取项目

```powershell
git clone https://github.com/lxz456/CareerMind.git
cd CareerMind
```

### 3. 安装后端依赖

在项目根目录执行：

```powershell
python -m venv backend/venv
.\backend\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

根目录 `requirements.txt` 会引用 `backend/requirements.txt`。前端 npm 依赖不属于 Python requirements。

> `torch` 默认安装版本不一定包含 CUDA。如果需要 GPU 精排，请根据本机 CUDA 环境安装对应的 PyTorch；否则将 `BGE_RERANK_DEVICE=cpu`。

### 4. 配置后端

在 `backend/` 下创建 `.env`。最小可用配置示例：

```dotenv
APP_NAME=CareerMind AI
APP_VERSION=1.0.0
APP_DEBUG=false

DATABASE_URL=sqlite+aiosqlite:///./data/careermind.db
CHECKPOINT_DB_PATH=./data/langgraph_checkpoints.db
JWT_SECRET_KEY=replace-with-a-random-secret

LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=your-dashscope-api-key
DASHSCOPE_MODEL=qwen3.8-flash
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_ENABLE_THINKING=false
EMBEDDING_MODEL=text-embedding-v3

JSEARCH_API_KEY=your-jsearch-api-key
JSEARCH_RAPIDAPI_HOST=api.openwebninja.com
TAVILY_API_KEY=your-tavily-api-key

UPLOAD_DIR=./uploads
CHROMA_PERSIST_DIR=./chroma_db

BGE_RERANK_MODEL=BAAI/bge-reranker-v2-m3
BGE_RERANK_MODEL_DIR=./venv/models/bge-reranker-v2-m3
BGE_RERANK_DEVICE=auto
```

说明：

- `.env` 已被 `.gitignore` 排除，禁止提交真实密钥；
- 路径 A 的真实岗位搜索需要 JSearch；
- 学习资料实时采集需要 Tavily；
- BGE 模型首次使用时会从 Hugging Face 下载到配置目录，后续复用本地文件；
- 所有后端相对路径都以 `backend/` 为运行目录。

### 5. 启动后端

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
```

开发阶段可以追加 `--reload`，但代码变化会重启进程并中断正在运行的路径 A。重启后任务会显示为 `interrupted`，需要用户从个人中心点击“继续”。

后端地址：

- API：`http://localhost:8010/api/v1`
- Swagger：`http://localhost:8010/docs`
- 健康检查：`http://localhost:8010/health`

### 6. 安装并启动前端

打开另一个终端：

```powershell
cd frontend
Copy-Item .env.example .env.development
npm install
npm run dev
```

前端默认地址：`http://localhost:5173`。

`VITE_API_BASE_URL` 默认开发配置为：

```dotenv
VITE_API_BASE_URL=http://localhost:8010/api/v1
```

## 数据与持久化

| 数据 | 默认位置 | 作用 |
|---|---|---|
| 业务 SQLite | `backend/data/careermind.db` | 用户、简历、规划历史、面试历史、题目和资源元数据 |
| LangGraph checkpoint | `backend/data/langgraph_checkpoints.db` | 两条路径的运行状态和中断点，即持久化短期记忆 |
| ChromaDB | `backend/chroma_db/` | 面试题与学习资源的向量数据 |
| 上传文件 | `backend/uploads/` | 用户上传的 PDF/DOCX 简历 |
| BGE 模型 | `backend/venv/models/` | 本地精排模型文件 |

这些运行数据、密钥、虚拟环境和模型文件均不会提交到 Git。删除业务数据库不会自动删除 ChromaDB，反之亦然；需要清理知识数据时应同时考虑两类存储。

## 状态恢复机制

### 路径 A

1. 创建 `workflow_runs` 业务记录；
2. 使用 `career_planning:<run_id>` 作为 LangGraph `thread_id`；
3. 使用后台 `asyncio.Task` 执行图，并把节点进度写回业务库；
4. 后端重启后，遗留的 `running` 记录改为 `interrupted`，不会自动恢复；
5. 用户点击“继续”后调用恢复接口，有 checkpoint 则断点续跑，否则尝试使用原始简历重启。

### 路径 B

1. `session_id` 同时作为业务会话标识和 LangGraph `thread_id`；
2. `wait_for_answer` 节点通过 `interrupt()` 保存状态并暂停；
3. 用户提交答案后使用 `Command(resume={"answer": "..."})` 继续；
4. 页面刷新、重新登录或从面试历史进入时，以服务端 checkpoint 为准恢复。

## 主要 API

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册并返回 JWT |
| POST | `/api/v1/auth/login` | 登录并返回 JWT |
| GET/PUT | `/api/v1/users/me` | 获取或修改个人资料 |
| POST | `/api/v1/resume/upload` | 上传并提取简历文本 |
| GET | `/api/v1/resume/{resume_id}` | 查询简历详情 |
| POST | `/api/v1/workflow/career-planning` | 创建路径 A 后台任务 |
| GET | `/api/v1/workflow/{run_id}/status` | 查询规划进度 |
| POST | `/api/v1/workflow/{run_id}/resume` | 显式恢复中断的规划 |
| GET | `/api/v1/workflow/{run_id}/result` | 获取已完成规划结果 |
| GET | `/api/v1/workflow/plans` | 查询规划历史 |
| POST | `/api/v1/interview/start` | 创建路径 B 面试 |
| POST | `/api/v1/interview/{session_id}/answer` | SSE 提交回答并推进图 |
| GET | `/api/v1/interview/{session_id}/feedback` | 获取面试状态或报告 |
| GET | `/api/v1/interview/sessions` | 查询面试历史 |
| POST | `/api/v1/knowledge/search` | 混合检索题目或学习资料 |

完整接口契约请启动后端后访问 Swagger。

## 错误处理与可观测性

- FastAPI 中间件为每个 HTTP 请求生成或透传 `X-Request-ID`；
- 标准 `logging` 输出请求、节点、模型调用耗时和 token 使用量；
- LLM 配置单次传输超时、总操作超时和自动重试；
- JSearch、Tavily 和 Embedding 对连接错误、429 及部分 5xx 执行有限次数重试；
- 路径 A 将稳定的 `error_code` 与面向用户的错误信息写入 `workflow_runs`；
- 可选的学习资源补充失败不会覆盖 LLM 已生成的规划内容；
- BGE 推理通过 `asyncio.to_thread()` 执行，避免同步 PyTorch 计算直接阻塞事件循环。

## 构建与基础检查

后端语法检查：

```powershell
cd backend
.\venv\Scripts\python.exe -m compileall -q app
```

前端生产构建：

```powershell
cd frontend
npm run build
```

向量知识回填：

```powershell
cd backend
.\venv\Scripts\python.exe scripts/backfill_vector_knowledge.py
```

当前仓库尚未配置自动化测试套件，涉及图路由、checkpoint 或双数据库一致性的改动，应至少手工执行一次路径 A、路径 B 和知识检索的端到端冒烟测试。

## 已知限制

- 当前是 SQLite + ChromaDB 的单机 Demo，不适合多进程、高并发生产部署；
- `create_all()` 不是完整数据库迁移方案，正式项目应引入 Alembic；
- 当前 JSearch 市场和前端筛选不包含中国大陆 `cn`；
- SSE 输出的是工作流阶段更新，不是模型 token 级输出；
- BGE 首次下载和首次加载耗时较长，4GB 显存设备可能需要使用较小 batch 或 CPU；
- 密码哈希为 Demo 实现，生产环境应迁移到 Argon2id、scrypt 或 bcrypt；
- 当前工具由确定性工作流调用，不是让 LLM 自主循环选择工具的通用 Agent Harness。

## 开发文档

更详细的状态字段、节点职责、混合检索、双写去重、错误处理、配置项和数据模型说明，请阅读 [backend/DEVELOPMENT.md](backend/DEVELOPMENT.md)。

## Git 安全提醒

提交前请确认以下内容没有进入暂存区：

```text
backend/.env
frontend/.env.development
backend/data/
backend/chroma_db/
backend/uploads/
backend/venv/
frontend/node_modules/
frontend/dist/
```

推荐检查：

```powershell
git status
git diff --cached --stat
git diff --cached --check
```
