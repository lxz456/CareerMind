# CareerMind AI 前端

> Vue 3 + Element Plus + Pinia + vue-router + axios + Vite

## 运行

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

## 目录

```
src/
├── main.js            # 入口：挂载 app + Element Plus + Pinia
├── App.vue
├── router/index.js    # 路由 + 登录守卫
├── stores/user.js     # 登录态（token + 用户信息）
├── api/               # 后端接口封装（统一走 index.js 拦截器）
│   ├── index.js       # axios 实例：baseURL 读取 VITE_API_BASE_URL、自动附 token、401 跳登录
│   ├── auth.js  user.js  resume.js  job.js  skillGap.js
│   ├── careerPlan.js  interview.js  workflow.js  knowledge.js
├── components/
│   ├── Layout.vue      # 侧边导航（首页/规划提升/模拟面试/题库学习中心/个人中心）
│   ├── PlanTimeline.vue  SkillGapChart.vue  InterviewResult.vue
└── views/
    ├── Login.vue  Home.vue
    ├── Planning.vue          # 路径A：上传简历 → AI 分析（轮询进度）→ 结果
    ├── Interview.vue  InterviewSession.vue  InterviewResult.vue   # 路径B
    ├── KnowledgeSearch.vue   # 路径C：题库/学习中心（搜索面试题/学习资源）
    └── Profile.vue           # 个人中心（面试历史 / 职业规划历史）
```

## 说明

- API 地址由 `VITE_API_BASE_URL` 控制；本地 `frontend/.env.development` 默认为 `http://localhost:8010/api/v1`。
- `.env.development` 是本机配置且不会提交；新增环境时可复制 `.env.example`。生产环境未配置该变量时使用同域 `/api/v1`，并由网关反向代理。
- 浏览器访问 `http://localhost:5173` 或 `http://127.0.0.1:5173` 均可（后端 CORS 已放行）。
- 后端接口详见 [backend/DEVELOPMENT.md](../backend/DEVELOPMENT.md) 的 API 清单。
