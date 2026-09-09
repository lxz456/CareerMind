// 用户状态：token + 用户信息（localStorage 持久化）
import { defineStore } from 'pinia'
import { login as loginApi, register as registerApi } from '../api/auth'
import { getProfile } from '../api/user'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('careermind_token') || '',
    user: JSON.parse(localStorage.getItem('careermind_user') || 'null'),
  }),

  getters: {
    isLoggedIn: (state) => !!state.token,
    username: (state) => state.user?.username || '',
  },

  actions: {
    async login(payload) {
      const data = await loginApi(payload)
      this.token = data.access_token
      this.user = { id: data.user_id, username: data.username }
      this._persist()
    },

    async register(payload) {
      const data = await registerApi(payload)
      this.token = data.access_token
      this.user = { id: data.user_id, username: data.username }
      this._persist()
    },

    async refreshProfile() {
      try {
        this.user = await getProfile()
        localStorage.setItem('careermind_user', JSON.stringify(this.user))
      } catch (e) {
        // 忽略：未登录时无需刷新
      }
    },

    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('careermind_token')
      localStorage.removeItem('careermind_user')
    },

    _persist() {
      localStorage.setItem('careermind_token', this.token)
      localStorage.setItem('careermind_user', JSON.stringify(this.user))
    },
  },
})
