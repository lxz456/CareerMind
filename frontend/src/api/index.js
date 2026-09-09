// axios 实例 + 拦截器
import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

// 由 Vite 环境变量指定后端地址；未配置时使用同域 /api/v1，便于生产部署。
const apiBaseURL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/+$/, '')

const request = axios.create({
  baseURL: apiBaseURL,
  timeout: 300000, // LLM 解析/规划可能很慢，放宽到 5 分钟
})

// 请求拦截器：自动附加 token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('careermind_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一错误处理
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      // 未认证：清 token 跳登录
      localStorage.removeItem('careermind_token')
      localStorage.removeItem('careermind_user')
      if (router.currentRoute.value.path !== '/login') {
        ElMessage.error('登录已过期，请重新登录')
        router.push('/login')
      }
    } else {
      const msg = typeof detail === 'string' ? detail : (error.message || '请求失败')
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  }
)

export default request
