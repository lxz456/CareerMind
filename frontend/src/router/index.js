// 路由 + 登录守卫
import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    component: () => import('../components/Layout.vue'),
    redirect: '/home',
    children: [
      {
        path: 'home',
        name: 'Home',
        component: () => import('../views/Home.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'planning',
        name: 'Planning',
        component: () => import('../views/Planning.vue'),
        meta: { title: '规划提升' },
      },
      {
        path: 'interview',
        name: 'Interview',
        component: () => import('../views/Interview.vue'),
        meta: { title: '模拟面试' },
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('../views/KnowledgeSearch.vue'),
        meta: { title: '题库/学习中心' },
      },
      {
        path: 'interview/:sessionId',
        name: 'InterviewSession',
        component: () => import('../views/InterviewSession.vue'),
        meta: { title: '面试中' },
      },
      {
        path: 'interview/:sessionId/result',
        name: 'InterviewResult',
        component: () => import('../views/InterviewResult.vue'),
        meta: { title: '面试报告' },
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '个人中心' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫
router.beforeEach((to) => {
  const userStore = useUserStore()
  document.title = to.meta.title ? `${to.meta.title} - CareerMind AI` : 'CareerMind AI'

  if (to.path !== '/login' && !userStore.isLoggedIn) {
    return { path: '/login' }
  }
  if (to.path === '/login' && userStore.isLoggedIn) {
    return { path: '/home' }
  }
  return true
})

export default router
