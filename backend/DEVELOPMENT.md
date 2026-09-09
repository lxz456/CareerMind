# CareerMind AI 项目开发文档

> 文档版本：V2.1
>
> 对齐日期：2026-09-03
>
> 对齐范围：`backend/app/`、`frontend/src/`、当前依赖与运行配置
>
> 核心技术：FastAPI、SQLAlchemy Async、LangGraph、SQLite Checkpointer、ChromaDB、Vue 3、Element Plus

本文档描述当前代码已经实现的行为。设计设想、未接入模块和已知限制会单独标注，不能视为已经上线的能力。

---

## 1. 项目定位与功能边界

CareerMind AI 是一个面向求职与职业发展的 LLM 应用，当前包含三组业务功能：

1. **路径 A：规划提升**
   - 上传并解析简历；
   - 按前端必填的目标岗位实时检索岗位，目标返回 3～5 个、代码上限为 5 个；
   - 并行完成简历分析和岗位搜索；
   - 汇总多个岗位要求，分析技能差距；
   - 生成逐月学习规划，并尽量补充真实学习资料链接；
   - 保存任务进度、结果和历史记录。

2. **路径 B：模拟面试**
   - 支持 HR、技术、系统设计和混合面试；
   - 支持“复习巩固”和“进阶提升”两种出题模式；
   - 使用 LangGraph `interrupt` 实现逐题等待用户回答；
   - 对每次回答进行评分，按分数决定追问；
   - 根据整道题的表现动态升降下一题难度；
   - 通过 SSE 输出评估、追问、难度调整等进度事件；
   - 保存运行状态、逐轮消息、最终报告和面试历史。

3. **题库 / 学习中心**
   - 搜索面试题或学习资料；
   - 面试题的新内容由 LLM 生成；
   - 学习资料的新内容由 Tavily 搜索并经 LLM 清洗；
   - 并行执行 SQLite FTS5 BM25 与 Chroma 向量召回，融合去重后使用本地 BGE Rerank 精排。

项目包含 Agent/LLM 应用开发要素：LangGraph 状态图、节点路由、中断恢复、SQLite checkpoint、RAG、Embedding、结构化 LLM 输出和可复用 Tool。不过，当前 JSearch、Tavily、面试工具主要由确定性工作流直接调用，尚未实现一个可自主规划并循环选择工具的通用 ReAct Agent。

---

## 2. 总体架构

```text
┌────────────────────────────── Frontend ──────────────────────────────┐
│ Vue 3 + Vite + Element Plus + Pinia + Vue Router                    │
│ Planning / Interview / Knowledge / Profile                          │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP JSON / multipart / SSE
                                │ http://localhost:8010/api/v1
┌───────────────────────────────▼──────────────────────────────────────┐
│ FastAPI                                                              │
│ api → services → repositories → SQLAlchemy models                    │
│              ↘ agents / llm / tools / memory / vector_store          │
└───────────────┬──────────────────┬─────────────────┬─────────────────┘
                │                  │                 │
       SQLite 业务库      SQLite checkpoint      ChromaDB
       用户/简历/历史      LangGraph 短期状态      题目/资源向量
                │                  │                 │
                └────────────┬─────┴──────────┬──────┘
                             │                │
                      DashScope/OpenAI   JSearch / Tavily
```
用户输入查询
    │
    ├─ 是否勾选“生成新题/实时搜索”？
    │      ├─ 是：生成或采集内容 → 双写 SQLite + Chroma
    │      └─ 否：直接检索已有数据
    │
    ├────────────── 并行召回 ──────────────┐
    │                                      │
SQLite FTS5 BM25                       Chroma 向量检索
关键词/全文匹配                         语义相似度匹配
    │                                      │
    └──────────── 合并并按 ID 去重 ─────────┘
                       │
               RRF 排名融合，k=60
                       │
               保留候选 Top 50
                       │
          BAAI/bge-reranker-v2-m3 精排
                       │
               最终返回 Top 20
                       │
              前端显示相关度

### 2.1 三类持久化数据

| 存储 | 默认位置（从 `backend/` 启动时） | 作用 |
|---|---|---|
| 业务 SQLite | `.env` 当前为 `./data/careermind.db` | 用户、简历、规划任务、面试历史、消息、题库和资源元数据 |
| Checkpoint SQLite | `./data/langgraph_checkpoints.db` | 路径 A/B 的 LangGraph 运行状态和中断点，即持久化短期记忆 |
| ChromaDB | `./chroma_db` | `interview_questions`、`learning_resources` 两个向量集合 |

所有相对路径都相对于后端进程的当前工作目录，因此应从 `backend/` 启动服务。

### 2.2 短期记忆与长期数据

- **短期记忆**：两条 LangGraph 都使用同一个应用级 `AsyncSqliteSaver`，但通过不同 `thread_id` 隔离状态。
- **业务长期数据**：用户资料、规划历史、面试消息与最终报告保存在业务 SQLite，可以跨线程、跨登录和跨进程读取。
- `memory/long_term.py` 提供用户画像、简历历史、学习进度和面试历史查询封装，但当前没有被路径 A、路径 B 或 API 主流程调用，属于预留能力，不应描述为已参与模型推理的长期记忆。

---

## 3. 项目目录

```text
backend/
├── app/
│   ├── main.py                 # FastAPI 入口、lifespan、路由注册
│   ├── config.py               # Pydantic Settings，读取 backend/.env
│   ├── database.py             # 异步 SQLAlchemy、SQLite WAL/busy_timeout、建表
│   ├── api/                    # 6 个路由模块
│   │   ├── auth.py             # 注册、登录
│   │   ├── users.py            # 当前用户资料
│   │   ├── resume.py           # 简历上传与详情
│   │   ├── workflow.py         # 路径 A 与规划历史
│   │   ├── interview.py        # 路径 B、SSE、面试历史
│   │   └── knowledge.py        # 题库/学习中心
│   ├── services/               # 业务编排、事务边界与统一知识双写
│   ├── repositories/           # SQLAlchemy 与 ChromaDB 数据访问
│   │   ├── knowledge_repo.py   # 题目/资源 SQL 元数据
│   │   └── vector_knowledge_repo.py # 题目/资源向量数据
│   ├── models/                 # 7 张业务表
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── agents/
│   │   ├── graph.py            # 路径 A LangGraph
│   │   ├── interview_graph.py  # 路径 B LangGraph
│   │   ├── state.py            # 两条路径的状态定义
│   │   └── *_agent.py          # 路径 A 节点
│   ├── llm/                    # 提示词、LLM/Embedding 调用
│   │   └── reranker.py         # 本地 BAAI BGE 精排模型适配器
│   ├── tools/
│   │   ├── jsearch.py          # JSearch HTTP、岗位搜索编排与去重
│   │   ├── tavily.py           # Tavily HTTP 与标准化
│   │   ├── learning_resources.py # 学习资源缓存优先检索与采集
│   │   └── interview.py        # 面试 RAG/生成/评分工具封装
│   ├── memory/
│   │   ├── checkpoint.py       # 应用级异步 SQLite checkpointer
│   │   └── long_term.py        # 未接入主流程的长期数据查询封装
│   ├── vector_store.py         # ChromaDB 两集合封装
│   └── utils/                  # JWT、密码哈希、文件解析
├── data/                       # 业务库与 checkpoint 库
├── chroma_db/                  # Chroma 持久化目录
├── uploads/<user_id>/          # 用户上传的简历
├── .env                        # 本地配置，禁止提交密钥
├── DEVELOPMENT.md
└── requirements.txt

frontend/
├── src/
│   ├── api/                    # axios/fetch 接口封装
│   ├── views/                  # 页面
│   ├── components/             # 规划、图表、报告、布局组件
│   ├── router/                 # 路由与登录守卫
│   └── stores/                 # Pinia 登录态
├── vite.config.js
└── package.json
```

---

## 4. 后端分层与依赖规则

```text
api → services → repositories → models / vector_store
        └→ agents → tools → llm
                    └→ repositories（RAG 检索与缓存写入）
```

| 层 | 当前职责 |
|---|---|
| `api` | 路由、鉴权依赖、请求/响应模型、SSE 编码 |
| `services` | 业务规则、事务编排、后台任务、图的启动/恢复、HTTPException |
| `repositories` | 封装 SQLAlchemy 和 ChromaDB 数据访问，不处理 HTTP 语义或业务流程 |
| `agents` | LangGraph 状态、节点、边和确定性路由 |
| `llm` | 提示词、结构化 JSON 解析、模型与 embedding 客户端 |
| `tools` | 外部 API 适配，以及可复用的“检索/调用 LLM/结果缓存”能力编排；当前由确定性工作流直接调用 |
| `memory` | LangGraph checkpoint 生命周期；长期数据查询预留模块 |

Service 负责用例级业务规则和 SQL 事务边界；`knowledge_ingestion_service.py` 是知识双写的唯一入口。`knowledge_repo.py` 封装业务表与 FTS5 BM25，`vector_knowledge_repo.py` 负责向量文档/metadata 序列化与集合访问，`vector_store.py` 只保留通用 Chroma 客户端能力。`memory/long_term.py` 通过各 Repository 聚合跨会话数据，目前仍是尚未接入主流程的预留能力。

---

## 5. 路径 A：规划提升

### 5.1 输入契约

`POST /api/v1/workflow/career-planning`

```json
{
  "resume_id": "已上传简历 ID，与 resume_text 二选一",
  "target_position": "LLM Engineer",
  "job_requirements": "under_3_years_experience",
  "target_location": "sg"
}
```

规则：

- `target_position` 必填，去除首尾空白后不能为空；
- `resume_id` 和 `resume_text` 必须且只能提供一个；
- `job_requirements` 可选值：`under_3_years_experience`、`more_than_3_years_experience`、`no_experience`、`no_degree`；
- `target_location` 可选值：`us`、`gb`、`de`、`jp`、`sg`、`hk`、`tw`；当前不包含中国大陆 `cn`。

前端 `Planning.vue` 的实际流程是先调用 `/resume/upload`，再使用返回的 `resume_id` 启动规划。

### 5.2 LangGraph 拓扑

```text
                    ┌→ resume_analysis ─┐
START ──────────────┤                    ├→ skill_gap → career_plan → summary → END
                    └→ job_search ──────┘
```

- `resume_analysis` 和 `job_search` 从同一初始状态并行启动；
- `job_search` 只使用前端给定的目标岗位和筛选条件，不依赖简历分析结果；
- `skill_gap` 是显式 join，只有两个并行节点都结束后才执行；
- `skill_gap` 或 `career_plan` 出现 `error_message` 时会跳到 `summary`；
- 图使用 `CareerPlanningState` 和 `completed_steps` 加法 reducer 合并并行分支结果。

### 5.3 节点职责

| 节点 | 输入 | 输出与行为 |
|---|---|---|
| `resume_analysis` | `resume_text` | 调用一次 LLM，解析姓名、技能、技能等级、经历、教育、项目等 |
| `job_search` | `target_position`、地区、工作要求 | JSearch 实时搜索，LLM 排序，最多保留 5 个去重岗位 |
| `skill_gap` | 简历数据 + 所有岗位 | 聚合所有岗位的要求并去重，再由 LLM 计算匹配度和技能差距 |
| `career_plan` | 目标岗位 + 技能差距 | LLM 生成简体中文逐月计划；每个任务尝试从资源向量库或 Tavily 获取真实链接 |
| `summary` | 前面所有结果 | 用确定性 Python 拼接 Markdown 汇总，不再调用 LLM |

各 LLM JSON 只保留后续节点、持久化或前端实际消费的字段。目标岗位以用户必填输入为准，不再要求简历 LLM 重复推断；学习资源由职业规划节点结合资源库/Tavily 补充，不再嵌入技能差距 JSON。

上传接口只完成文件保存和文本提取。结构化 LLM 分析只在路径 A 的 `resume_analysis` 节点执行一次；节点结束后，工作流服务将 `parsed_data`、完整度评分和分析摘要回写到对应 `resumes` 记录。

简历状态生命周期为：`pending → ready → processing → completed/failed`。其中 `ready` 表示文本已提取、可以启动工作流，不表示已经完成 LLM 分析。

### 5.4 岗位搜索

路径 A 的岗位链路为：

```text
目标岗位/地区/工作要求
  → tools/jsearch.search_jobs
      → 中文目标职位由 llm/job_search 转换为英文检索词
      → fetch_job_candidates 获取并标准化 OpenWebNinja JSearch 实时结果
      → llm/job_search.rank_jobs 进行 LLM 相关性排序
      → tools/jsearch 去重并截取 Top 5
```

- 请求 URL：`https://<JSEARCH_RAPIDAPI_HOST>/jsearch/search-v2`；当前 `.env` host 为 `api.openwebninja.com`；
- Header：`X-API-Key`；
- 参数：`query`、`num_pages=1`、`language`，以及可选 `country`、`job_requirements`；
- 用户填写的目标职位原文始终保存在工作流状态和历史记录中；仅当职位包含中文时，调用 LLM 转换为简洁英文职位关键词后再请求 JSearch；
- `language` 首次使用 `zh` 请求中文结果；若为空，自动按目标市场语言重试（如美国/新加坡为 `en`、日本为 `ja`），避免中文结果稀缺导致整条路径失败；
- 岗位要求优先读取 JSearch `job_highlights` 中的 Requirements/Qualifications；部分 `/search-v2` 结果会返回空 highlights，此时从完整职位描述的 Candidate Requirements、Qualifications 等段落提取；
- 排序 LLM 只返回候选编号、分数和理由，标题、公司、地点、岗位要求、描述和来源链接由代码按候选编号回填，防止真实字段在 LLM 重组 JSON 时丢失；
- 岗位标题、公司和地点保留 JSearch 原文，LLM 生成的推荐理由、技能改进建议和职业规划叙述使用简体中文；
- JSearch 无 key或请求失败时抛出异常；接口正常但无结果时返回空岗位，任何情况都不使用 LLM 编造岗位；
- 空岗位会形成 `job_search_error`，路径 A 最终标记为失败；
- 当前 HTTP 客户端设置 `verify=False`，是为规避本机证书吊销检查问题，但会降低 TLS 安全性，生产环境应恢复证书校验。

### 5.5 后台任务、进度与恢复

- 启动接口先创建 `workflow_runs`，生成 `thread_id=career_planning:<run_id>`，随后用 `asyncio.create_task` 后台运行图；
- 前端按用户把当前 `run_id` 保存到 localStorage，并每 2 秒轮询 `GET /workflow/{run_id}/status`；
- 图使用 `astream(stream_mode="values")` 获取每个 superstep 的完整状态；
- 五个逻辑节点各占 20%。两个并行节点在同一 superstep 合并，因此前端通常看到 `0 → 40 → 60 → 80 → 100`；
- 每次进度回写使用独立数据库 session，避免与主任务 session 争用；
- FastAPI 启动时只把上一个进程遗留的 `running` 规划标记为 `interrupted`，不会自动重新执行，避免用户不知情时消耗模型和外部搜索额度；
- 用户在个人中心对 `interrupted` 规划点击“继续”后，前端调用 `POST /workflow/{run_id}/resume`：有 checkpoint 就从最近图状态继续；首个 checkpoint 尚未产生时，才使用保存的 `resume_text` 或 `resume_id` 从头执行；
- 如果 checkpoint 和原始简历都不存在，恢复接口返回 409，任务保持中断状态；同一进程内按 `run_id` 跟踪后台任务，重复点击不会重复调度；
- 服务关闭时会取消当前进程内跟踪的后台任务；下次启动将对应业务记录标记为 `interrupted`，等待用户操作；
- 用户重新进入规划页时，前端可恢复仍在本进程运行的任务并继续轮询，但不会因为 localStorage 中保存了一个 `interrupted` 的 run_id 就自动启动它。

规划历史保存在 `workflow_runs`。删除规划历史时会同时删除业务表记录和 `thread_id` 对应的 LangGraph checkpoint。

---

## 6. 路径 B：自适应模拟面试

### 6.1 启动参数

`POST /api/v1/interview/start`

```json
{
  "interview_type": "technical",
  "job_title": "Backend Engineer",
  "question_mode": "review",
  "difficulty": "medium",
  "question_count": 5
}
```

| 字段 | 规则 |
|---|---|
| `interview_type` | `hr`、`technical`、`system_design`、`mixed` |
| `job_title` | 必填，1～100 字符 |
| `question_mode` | `review` 或 `advanced`，默认 `review` |
| `difficulty` | `easy`、`medium`、`hard`，默认 `medium` |
| `question_count` | API 允许 1～20；当前前端滑块允许 3～10 |

前端没有暴露初始难度选择，因此普通页面启动时使用后端默认的 `medium`。API 调用方仍可显式指定初始难度。

### 6.2 LangGraph 拓扑

```text
START
  │
  ▼
initialize              只生成第 1 道基础题
  │
  ▼
prepare_question        把当前基础题设为 current_question
  │
  ▼
ask_question            向前端发送当前题目
  │
  ▼
wait_for_answer         interrupt()：保存 checkpoint，暂停并等待回答
  │
  │ POST /answer + Command(resume={"answer": "..."})
  ▼
evaluate                LLM 评分并写入 answer / feedback
  │
  ▼
decide                   按分数、追问次数、基础题进度路由
  │
  ├── follow_up ──→ 生成当前基础题的追问
  │                    │
  │                    └──→ ask_question → wait_for_answer → evaluate → decide
  │                                                                    │
  │                       追问已用完，只能 next_question 或 finish ────┘
  │
  ├── next_question ─→ 计算本轮平均分
  │                    → 升/降/保持难度
  │                    → 按新难度生成下一道基础题
  │                    → prepare_question → ask_question → ...
  │
  └── finish ─────→ build_report → END
```

#### 一次完整的基础题轮次

```text
基础题 → 等待回答 → 评分
                       │
                       ├─ 得分 7～10 ──────→ 下一题 / 结束
                       │
                       └─ 得分 0～6.9 且未追问
                                      │
                                      ▼
                              尝试生成一次追问
                                      │
                    生成失败/内容为空 ─├──────────────────→ 下一题 / 结束
                                      ▼
                         等待追问回答 → 评分
                                      │
                                      ▼
                                 下一题 / 结束
```

| 节点 | 职责 | 是否调用 LLM/题库 |
|---|---|---|
| `initialize` | 按岗位、模式和初始难度生成第 1 道基础题 | 是 |
| `prepare_question` | 选中当前基础题，清空追问状态 | 否 |
| `ask_question` | 记录 AI 题目消息，发送 `question_ready` 事件 | 否 |
| `wait_for_answer` | 执行 `interrupt()`，恢复后记录用户回答 | 否 |
| `evaluate` | 评估当前回答，追加评分和反馈；同一次响应按需附带候选追问 | 是 |
| `decide` | 根据阈值、追问上限和候选追问进行确定性路由 | 否 |
| `follow_up` | 把生成的追问设为当前题，保留父题 ID | 否 |
| `next_question` | 计算本轮平均分，调整难度并生成下一道基础题 | 是 |
| `build_report` | 聚合所有 feedback，生成最终分数、优势和改进项 | 否（当前为本地规则聚合） |

关键运行机制：

- `wait_for_answer` 是图中唯一的人机交互暂停点；每道基础题和追问都会经过该节点；
- 启动会话时，Service 调用 `start_interview_graph()`；Graph 层内部通过 `state.create_interview_state()` 构造完整状态，并统一管理首次运行及 `thread_id` 配置；
- 提交回答时，Service 调用 `stream_interview_answer()` 消费事件；Graph 层内部用 `Command(resume={"answer": ...})` 恢复相同的 `session_id/thread_id`，执行会从暂停的 `wait_for_answer` 继续，不会重新跑 `initialize`；
- `decide` 是唯一的条件路由节点，只会输出 `follow_up`、`next_question` 或 `finish`；
- 追问不会增加 `current_index`，所以在 UI 和报告中仍归属当前基础题；只有 `next_question` 会把基础题索引加一；
- 每个 session 有进程内 `asyncio.Lock`，阻止同一进程中的并发重复提交；它不是跨进程分布式锁；
- 图使用与路径 A 相同的 SQLite checkpointer，但通过独立 `thread_id` 隔离会话。

### 6.3 逐题生成与自适应难度

路径 B 不再初始化整套题目：

1. `initialize` 只生成第一道基础题；
2. 当前基础题及其可选追问结束；
3. 计算本题轮次分数；
4. 调整难度；
5. 按新难度生成下一道基础题，并把已经问过的题目传入排除条件和提示词。

难度规则：

| 本题轮次得分 | 下一题难度 |
|---|---|
| `< 4` | 降低一级 |
| `4～7.9` | 保持 |
| `≥ 8` | 提高一级 |

难度边界固定为 `easy → medium → hard`，不会低于 `easy` 或高于 `hard`。如果当前基础题发生追问，轮次得分为基础回答和该次追问评分的平均值，因此每道基础题最多调整一次难度。

混合面试在逐题生成时按 `HR → 技术 → 系统设计` 循环选择题型。

### 6.4 追问规则

每道基础题最多追问一次：

| 当前回答得分 | 行为 |
|---|---|
| `0～3.9` | 使用本次评价响应同时生成的基础澄清型追问 |
| `4～6.9` | 使用本次评价响应同时生成的缺失细节型追问 |
| `7～10` | 不追问，进入下一道基础题或结束 |

代码负责分数阈值、次数上限和最终路由。评价 LLM 在同一次结构化响应中返回评分和候选追问，避免评分后再串行调用一次独立决策模型；候选为空或未通过中文校验时跳过追问。

追问提示词强制要求简体中文，Graph 在使用前还会拒绝完全不含中文的候选追问，确保英文追问不会直接进入 UI。

`answered_count` 统计回答轮次，包含追问；`total_questions` 只统计基础题数量。最终 `total_score` 当前会对所有 feedback 求平均，因此追问评分也参与总分。

### 6.5 两种出题模式

- **复习巩固 `review`**
  1. 根据目标岗位、题型和当前难度查询 Chroma；
  2. 使用 category/difficulty metadata 过滤；
  3. 只保留相似度 `≥ INTERVIEW_RAG_MIN_SCORE` 的候选；
  4. Chroma 已按相似度降序返回，直接选取未重复的中文 Top-N，不再调用 LLM 二次选择；
  5. 没有合格中文候选时由 LLM 生成。

- **进阶提升 `advanced`**
  - 跳过 RAG 检索，直接由 LLM 按目标岗位和当前难度生成。

所有直接生成提示词均使用中文 JSON 示例，并要求 `question`、`topic` 和 `expected_points` 使用简体中文。复习模式会跳过旧英文候选并转入直接生成；直接生成若仍返回英文题，统一语言校验层会额外执行一次批量中文本地化，二次校验仍失败则拒绝返回该批题目。Java、Python、HTTP、RAG 等技术专有名词允许保留英文。

路径 B 的 `tools/interview.py` 负责检索或生成，`InterviewService` 在拿到每道新基础题后调用统一入库服务，同时写入 `interview_questions` SQL 表和 Chroma。依赖具体回答生成的追问不进入公共题库。

Tavily 不参与面试题生成，只用于学习资料。

### 6.6 SSE 流式事件

回答接口使用 `astream(stream_mode="custom")`，后端编码为 `text/event-stream`。当前可能发送：

- `answer_received`：收到回答；
- `evaluating`：正在评分；
- `evaluation_completed`：评分完成；
- `generating_follow_up`：正在准备评价响应中已经生成的候选追问；
- `adapting_difficulty`：给出下一题难度；
- `question_ready`：追问或下一题已生成；
- `building_report`：正在汇总报告；
- `session_updated` / `session_completed`：包含最终安全序列化后的 session；
- `error`：本轮处理失败。

前端使用 `fetch + ReadableStream` 解析 SSE，而不是浏览器 `EventSource`，因为回答接口需要 POST JSON 和 Authorization Header。当前流式粒度是业务事件，不是 LLM token 逐字输出。

### 6.7 历史与恢复

- 运行中的完整图状态保存在 checkpoint SQLite；刷新页面或重新登录后，答题页以服务端 checkpoint 为准恢复当前题；
- 每次成功处理的用户回答和对应评分分别写入 `messages`；
- 面试完成后，完整 `InterviewSessionResponse` 归档到 `conversations.metadata.interview_archive`；
- 历史列表状态为 `completed`、`in_progress` 或 `unavailable`；
- 删除面试历史会删除 conversation、级联删除 messages，并删除对应 checkpoint；
- 路径 B 是等待用户交互的状态机，不会像路径 A 那样在启动时自动后台执行未完成步骤；用户重新进入会话并提交回答时才继续。

---

## 7. 题库、学习中心与 RAG

### 7.1 Chroma 集合

当前只有两个集合：

| 集合 | 内容 |
|---|---|
| `interview_questions` | 问题文本、考察点、题型、难度、主题 |
| `learning_resources` | 资源名称、主题、描述、类型、URL |

旧版数据库中的以下空置/重复字段已从 ORM 及调用链删除：`users.skills`、`workflow_runs.interview_result`、`messages.token_count`、`interview_questions.answer_reference`、`interview_questions.source_url`、`learning_resources.source_url`。`init_db()` 会在 SQLite 启动时检测并删除旧表中的这些列；新建数据库不会创建它们。

岗位始终通过 JSearch 实时获取，不存入 Chroma，也不存在 `jobs` 向量集合。

Chroma 使用 cosine space，返回分数为 `1 - cosine_distance`。业务代码通过异步 `VectorKnowledgeRepo` 访问题目和资源集合；底层同步 Embedding/Chroma 调用由 Repository 放入工作线程，不阻塞 asyncio 事件循环。

### 7.2 学习中心搜索

`POST /api/v1/knowledge/search` 请求：

```json
{
  "type": "interview",
  "query": "RAG 系统设计",
  "category": "technical",
  "difficulty": "hard",
  "limit": 10,
  "refresh": false
}
```

- `type`：`interview` 或 `resource`；
- `category`：面试题分类，或学习资源类型；
- `difficulty`：仅面试题有效；
- `limit`：1～20；
- `refresh=true`：面试题由 LLM 生成新题，资源由 Tavily 实时搜索并清洗，然后入库。

实际检索并非“SQL 候选再交给向量库重排”的严格两阶段检索，而是：

```text
SQLite FTS5 BM25 Top 50 ─┐
                          ├→ 稳定 ID 合并去重 → RRF(k=60) → Top 50
Chroma 向量召回 Top 50 ──┘                                  ↓
                                                BGE Rerank → Top 20
```

- FTS5 使用 trigram tokenizer，现有业务数据会在启动时回填，insert/update/delete 由数据库触发器同步；
- BM25 与向量召回只需提供各自的有序结果，不直接混合两类原始分数；
- 两路候选按稳定知识 ID 合并，通过 `1 / (k + rank)` 累加 RRF 分数；
- `k` 默认 60，两路各召回最多 50 条，RRF 融合后保留 Top 50；
- 使用本地多语言 `BAAI/bge-reranker-v2-m3` 精排，最终最多返回 20；
- 模型默认缓存在 `backend/venv/models/bge-reranker-v2-m3`，同一后端进程只加载一次；
- 模型加载或推理失败时按融合分降级，搜索仍可用。

`from_cache=false` 只在本次刷新成功时返回；若 LLM/Tavily 刷新失败，服务会降级查询已有数据并返回 `from_cache=true`。

### 7.3 学习资料在路径 A 中的使用

职业规划生成后，会收集每个月的所有 task，并按 `LEARNING_RESOURCE_CONCURRENCY` 限制并发补充资源：

1. 直接使用任务标题或描述调用 Tavily，不预先查询本地缓存；
2. Tavily 结果经 LLM 清洗为名称、类型、URL、主题和描述；
3. 每个任务最多采用 2 条带真实 URL 的资料；
4. 成功时替换 LLM 原先生成的资源列表，失败时保留原列表。

当前默认最多同时处理 3 个任务，避免原先逐任务串行等待 Tavily 和清洗 LLM；并发上限不会改变每个任务最终最多 2 条资源的规则。

Graph 把本轮 Tavily 实际采集的资源返回给 `WorkflowService`，再由统一入库服务同时写入 `learning_resources` SQL 表和 Chroma。入库在单批次内按 URL 去重，跨批次先按稳定内容 ID、再按真实 URL 查询已有 SQL 记录；重复资料沿用已有 ID，并通过 Chroma upsert 避免生成重复向量条目。

双入库以 SQLite 关系表为业务数据源，以 Chroma 为可重建的检索索引。`KnowledgeIngestionService` 会分别统计本次去重后的条目数、关系库新增数、向量成功数和向量失败数；向量写入异常会保留 SQL 数据并记录完整异常与失败数量，不再把本次刷新报告为完整成功。

如果外部 Embedding 服务曾不可用，或旧代码导致 SQL 与 Chroma 数量不一致，可在 `backend` 目录执行补偿命令：

```powershell
$env:PYTHONPATH='.'
python scripts/backfill_vector_knowledge.py --type resources
# 也可使用 --type questions 或 --type all
```

该命令只读取关系库知识表并按原稳定 ID upsert 到 Chroma，不会新增或删除关系库业务数据。

---

## 8. 外部模型与工具

### 8.1 LLM

`llm/llm_client.py` 使用 `ChatOpenAI` 访问 OpenAI 兼容接口：

- 当前模型服务固定使用 DashScope 的 OpenAI 兼容协议和 `DASHSCOPE_*` 配置；
- 其他值走 `OPENAI_*`；
- `llm_json_call` 去除 Markdown code fence 后用 `json.loads` 解析；
- `llm_text_call` 返回纯文本；
- DashScope 请求通过 `LLM_ENABLE_THINKING` 控制思考模式；当前 `qwen3.8-flash` 配置为非思考模式；
- LLM 单次请求超时、整次操作超时和重试次数分别由 `LLM_TIMEOUT_SECONDS`、`LLM_OPERATION_TIMEOUT_SECONDS`、`LLM_MAX_RETRIES` 配置；调用日志记录 operation、模型、耗时和可用的 Token 用量；
- 当前没有 schema-guided decoding，JSON 格式错误会直接抛异常。
- JSearch、Tavily 的超时由 `.env` 配置；只对网络异常、HTTP 408/429/500/502/503/504 重试一次，参数错误和空结果不重试。
- 后端使用标准 `logging` 输出控制台日志，每个 HTTP 请求携带 `request_id`；路径 A 失败时在 `workflow_runs.error_code` 中保存稳定错误码，详细堆栈仅保留在日志中。

当前本地 `.env` 使用 DashScope，模型名为 `qwen3.8-flash`，并设置 `LLM_ENABLE_THINKING=false`。密钥不得写入文档或提交 Git。

### 8.2 Embedding

- DashScope Embedding 模型由 `.env` 的 `EMBEDDING_MODEL` 配置，当前使用 `text-embedding-v3`；
- `embed_texts()` 在 Embedding 层统一分批并保持输入输出顺序；DashScope v3 每批会强制限制为最多 10 条，避免路径 A 一次收集大量学习资料时触发 HTTP 400。

### 8.3 JSearch 工具层

`tools/jsearch.py` 负责市场映射、HTTP、响应检查、标准化、调用排序器与最终去重；`llm/job_search.py` 负责中文职位检索词转换和候选岗位排序。当前路径 A 直接调用 `search_jobs`，并没有让模型自主选择工具。

### 8.4 Tavily 工具层

`tools/tavily.py` 返回稳定字段：`title`、`content`、`url`、`score`。`tools/learning_resources.py` 在它之上组合 LLM 清洗与向量缓存查询；持久化由调用方所在 Service 统一完成。学习中心及路径 A 复用这一能力，不属于模型自主选择工具的循环。

### 8.5 Rerank

`llm/reranker.py` 使用 Transformers 在本地加载 `BAAI/bge-reranker-v2-m3`，输入原始查询和融合后的候选文本，分批计算相关性并按候选索引返回 0～1 分数。模型采用进程内单例延迟加载，同步推理通过工作线程执行，避免阻塞 FastAPI 事件循环。该模块只处理模型协议，不进行数据库查询、候选融合或 HTTP 响应组装。

---

## 9. 数据模型

业务 SQLite 共 7 张表：

| 表 | 关键字段与用途 |
|---|---|
| `users` | 账号、盐化密码摘要、资料、职业目标、技能 |
| `resumes` | 用户、原文件、路径、原文、解析 JSON、完整度分数、状态 |
| `conversations` | 面试标题、类型、thread_id、最终归档 metadata |
| `messages` | 每轮 user/assistant 消息和结构化 feedback metadata |
| `workflow_runs` | 路径 A 输入、进度、各节点结果、summary、thread_id、错误 |
| `interview_questions` | 学习中心题库的 SQL 元数据 |
| `learning_resources` | 学习中心资源的 SQL 元数据 |

注意：

- 使用 `Base.metadata.create_all()` 自动建表，没有 Alembic 迁移；已有数据库不会因模型变化自动增加或修改列；
- SQLite 启用 WAL、`busy_timeout=30000` 和 `synchronous=NORMAL`；
- `conversations → messages` 配置 ORM 级 `all, delete-orphan`；
- 其他外键没有统一声明数据库级级联删除。

---

## 10. API 清单

统一前缀为 `/api/v1`。除注册、登录、`/`、`/health` 外均需要：

```http
Authorization: Bearer <JWT>
```

### 10.1 认证

| Method | Path | 请求/作用 |
|---|---|---|
| POST | `/api/v1/auth/register` | `email, username, password`，成功即返回 JWT |
| POST | `/api/v1/auth/login` | `username` 字段可填写用户名或邮箱 |

### 10.2 用户

| Method | Path | 作用 |
|---|---|---|
| GET | `/api/v1/users/me` | 当前用户资料 |
| PUT | `/api/v1/users/me` | 更新允许的资料字段 |

### 10.3 简历

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/resume/upload` | multipart 上传 PDF/DOCX，使用唯一文件名保存并同步提取文本，不调用 LLM |
| GET | `/api/v1/resume/{resume_id}` | 获取当前用户指定简历详情 |

上传成功返回的状态为 `ready`。文本提取失败时接口仍返回对应记录，但 `status=failed`；结构化解析结果要在路径 A 执行后通过该详情接口读取。

### 10.4 路径 A

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/workflow/career-planning` | 创建后台规划任务并立即返回 run_id |
| GET | `/api/v1/workflow/{run_id}/status` | 获取状态和进度 |
| POST | `/api/v1/workflow/{run_id}/resume` | 用户显式恢复 interrupted/pending 规划；重复请求不会重复调度 |
| GET | `/api/v1/workflow/{run_id}/result` | 仅 completed 时返回完整结果 |
| GET | `/api/v1/workflow/plans` | 当前用户规划历史 |
| DELETE | `/api/v1/workflow/plans/{run_id}` | 删除规划业务记录及对应 checkpoint，204 |

### 10.5 路径 B

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/interview/start` | 创建面试、生成首题并返回 session |
| POST | `/api/v1/interview/{session_id}/answer` | 提交回答，返回 SSE 业务事件流 |
| GET | `/api/v1/interview/{session_id}/feedback` | 获取进行中状态或完成报告 |
| GET | `/api/v1/interview/sessions` | 面试历史和可恢复状态 |
| DELETE | `/api/v1/interview/{session_id}` | 删除业务历史及 checkpoint，204 |

### 10.6 知识中心与健康检查

| Method | Path | 作用 |
|---|---|---|
| POST | `/api/v1/knowledge/search` | 搜索/刷新面试题或学习资源 |
| GET | `/` | 应用名称、版本、状态、文档地址 |
| GET | `/health` | `{"status":"healthy"}`；只表示进程可响应，不探测数据库/LLM/外部 API |

---

## 11. 前端实现

### 11.1 技术栈与接口

- Vue 3、Vite、Element Plus、Pinia、Vue Router、Axios；
- `src/api/index.js` 的 baseURL 读取 `VITE_API_BASE_URL`，未配置时回退到同域 `/api/v1`；
- axios 超时为 300 秒；
- token 和用户摘要保存在 localStorage；
- 401 会清理登录态并跳转 `/login`；
- 本地 `frontend/.env.development` 指向 `http://localhost:8010/api/v1`；该文件不提交，示例见 `frontend/.env.example`；
- 生产环境建议将 `VITE_API_BASE_URL` 设置为 `/api/v1`，通过同域网关转发到 FastAPI。

### 11.2 页面路由

| 路由 | 页面 |
|---|---|
| `/login` | 登录/注册 |
| `/home` | 功能入口 |
| `/planning` | 简历上传、路径 A 进度和结果 |
| `/interview` | 面试类型、模式、题数和目标岗位配置 |
| `/interview/:sessionId` | 逐题回答、难度标签、SSE 状态、上一轮反馈 |
| `/interview/:sessionId/result` | 总分、强弱项、建议、基础题/追问明细 |
| `/knowledge` | 面试题/学习资源查询 |
| `/profile` | 个人资料、面试历史、规划历史，以及两类进行中任务的继续入口 |

答题页 localStorage 只用作首屏缓存；`onMounted` 会调用后端 feedback 接口，以服务端 checkpoint 为权威状态。职业规划历史中的 `running` 或 `interrupted` 记录显示“继续”；点击 `interrupted` 记录时先调用恢复接口，再跳转到 `/planning?run_id=...`。规划页通过 URL、本地 `run_id`、规划历史和状态接口恢复运行进度或最终结果，localStorage 不保存路径 A 的图状态，也不会自动恢复中断任务。

---

## 12. 配置说明

配置由 `app/config.py::Settings` 读取当前工作目录的 `.env`。关键变量：

| 变量 | 说明 |
|---|---|
| `APP_NAME`, `APP_VERSION`, `APP_DEBUG` | 应用信息与 SQLAlchemy echo；使用项目专属名称以避免通用 `DEBUG` 环境变量污染 |
| `DATABASE_URL` | 异步 SQLAlchemy URL，当前使用 SQLite |
| `CHECKPOINT_DB_PATH` | checkpoint SQLite；当前 `.env` 未显式配置时使用默认值 |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | JWT 配置 |
| `LLM_PROVIDER` | 当前固定为 `dashscope`，用于日志标识 |
| `DASHSCOPE_API_KEY`, `DASHSCOPE_MODEL`, `DASHSCOPE_BASE_URL` | 千问兼容接口 |
| `LLM_TEMPERATURE` | 默认温度；各任务可覆盖 |
| `EMBEDDING_MODEL` | DashScope Embedding 模型，当前为 `text-embedding-v3` |
| `EMBEDDING_BATCH_SIZE` | 单次 Embedding 批量大小；DashScope v3 即使配置更大也会限制为 10 |
| `MAX_UPLOAD_SIZE_MB`, `UPLOAD_DIR` | 上传限制与目录 |
| `CORS_ORIGINS` | 允许的前端来源，JSON 数组格式 |
| `CHROMA_PERSIST_DIR` | Chroma 目录 |
| `JSEARCH_API_KEY`, `JSEARCH_RAPIDAPI_HOST`, `JSEARCH_MAX_RESULTS` | JSearch |
| `TAVILY_API_KEY`, `TAVILY_MAX_RESULTS` | Tavily；后者统一控制每次外部搜索获取的原始网页数，路径 A 再按任务截取最终资源 |
| `LEARNING_RESOURCE_CONCURRENCY` | 路径 A 并发补充学习资源的任务数，当前默认 3 |
| `INTERVIEW_RAG_MIN_SCORE` | 面试复习模式最低相似度；当前默认 0.5 |
| `HYBRID_CANDIDATE_LIMIT` | BM25、向量各自的召回上限及 RRF 后送入精排的候选上限，默认 50 |
| `HYBRID_RRF_K` | RRF 排名平滑常数，默认 60 |
| `RERANK_FINAL_LIMIT` | 精排最大输出数，接口同时硬限制为 20 |
| `BGE_RERANK_MODEL`, `BGE_RERANK_MODEL_DIR` | BGE 精排模型 ID 与本地模型目录 |
| `BGE_RERANK_DEVICE` | `auto` 自动选择 CUDA/CPU，也可显式设置 `cpu` 或 `cuda` |
| `BGE_RERANK_BATCH_SIZE`, `BGE_RERANK_MAX_LENGTH` | 本地精排批大小与单个 query-document 输入长度上限 |
| `AGENT_RECURSION_LIMIT` | 路径 A/B 共用的 LangGraph 单次调用递归上限 |

仓库当前没有 `.env.example`。新增环境必须人工建立 `.env`，且不得复制或提交真实 API key。

---

## 13. 启动、构建与基本验证

项目代码使用 `str | None` 等语法，建议 Python 3.10 以上。当前本地虚拟环境为 Python 3.14。

### 13.1 后端

PowerShell：

```powershell
cd backend
./venv/Scripts/Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
```

访问：

- Swagger：`http://localhost:8010/docs`
- 健康检查：`http://localhost:8010/health`

开发时可以使用 `--reload`，但文件变化会重启进程并取消当前内存中的后台任务。新进程会把这类路径 A 任务标记为 `interrupted`，需要用户在个人中心点击“继续”；执行长规划时建议关闭 reload。

### 13.2 前端

```powershell
cd frontend
npm install
npm run dev
```

默认地址：`http://localhost:5173`。

生产构建校验：

```powershell
cd frontend
npm run build
```

后端静态语法校验：

```powershell
cd backend
python -m compileall -q app
```

当前仓库没有自动化测试套件。涉及 LangGraph 路由、checkpoint 或数据库结构的修改，除构建检查外还应手工完成一次路径 A 和路径 B 的端到端冒烟测试。

---

## 14. 常见问题与已知限制

| 现象/限制 | 当前原因与处理 |
|---|---|
| 路径 A 岗位为空并失败 | JSearch 未配置、市场不支持、请求失败或无结果；系统不会让 LLM 编造真实岗位 |
| JSearch 403 | key/host 不匹配；当前服务商使用 `api.openwebninja.com` 和 `X-API-Key` |
| 中国大陆岗位无法筛选 | 当前 schema 和市场表没有 `cn`，JSearch 服务本身也可能缺少中国大陆数据 |
| 路径 A 首段进度直接到 40% | 简历和岗位节点并行，在一个 LangGraph superstep 合并 |
| 上传成功但 `parsed_data` 为空 | `ready` 只表示文本提取完成；启动并完成路径 A 后才会写入结构化分析 |
| 面试下一题等待较久 | 下一题按新难度实时生成；SSE 只提供阶段事件，不是 token 流 |
| 面试历史显示 unavailable | 业务 conversation 存在，但没有完成归档且找不到 checkpoint |
| 修改 ORM 后数据库没有新列 | `create_all()` 不做迁移；开发阶段需手动迁移/重建，正式项目应引入 Alembic |
| SQLite `database is locked` | 已启用 WAL 和 30 秒 busy timeout；仍应避免多进程高并发写入 |
| 后端重载导致任务中断 | 新进程启动后任务显示 `interrupted`；用户在个人中心点击“继续”后按 checkpoint 恢复 |
| 前端代理端口不一致 | axios 直连 8010，Vite 中 8003 proxy 是残留配置，不参与请求 |

### 安全注意事项

- 当前密码存储为随机 salt + 单次 SHA-256，不适合作为生产级密码哈希；生产应迁移到 Argon2id、scrypt 或 bcrypt；
- 默认 JWT secret 只适合开发，部署必须覆盖；
- JSearch `verify=False` 会关闭 TLS 证书校验，生产必须修复证书链并启用校验；
- `.env`、业务数据库、checkpoint、Chroma 数据和 uploads 都可能包含敏感信息，不应提交到 Git；
- `/health` 不代表 LLM、JSearch、Tavily、数据库或 Chroma 一定可用。

---

## 15. 修改代码时的同步检查清单

1. 修改请求字段时，同步检查 `schemas/`、前端表单和 `src/api/`。
2. 修改 LangGraph state 时，考虑旧 checkpoint 是否仍能恢复。
3. 修改节点名称时，同步检查路径 A 进度标签和历史恢复。
4. 修改面试评分阈值时，同时检查追问规则、难度规则和报告统计。
5. 修改题目 metadata 时，同时检查 Chroma `where` 过滤和已有向量数据。
6. 修改 ORM 时，不要依赖 `create_all()` 迁移已有数据库。
7. 新增外部 API 时放入 `tools/`，业务排序/清洗放入 `llm/` 或 `services/`。
8. 完成修改后至少运行后端 compileall、前端 build，并执行相关业务链路冒烟测试。

---

*本文件以当前代码行为为准；`REFACTOR_PLAN.md` 是历史重构方案，不代表所有内容仍待实施或与现状一致。*
