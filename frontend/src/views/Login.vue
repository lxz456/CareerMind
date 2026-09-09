<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <el-icon :size="36" color="#409eff"><Opportunity /></el-icon>
        <h1>CareerMind AI</h1>
        <p>智能职业发展助手 · 规划提升 / 模拟面试</p>
      </div>

      <el-tabs v-model="tab" class="tabs">
        <!-- 登录 -->
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" label-width="70px">
            <el-form-item label="用户名">
              <el-input v-model="loginForm.username" placeholder="用户名或邮箱" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" show-password
                        placeholder="密码" @keyup.enter="handleLogin" />
            </el-form-item>
          </el-form>
          <el-button type="primary" size="large" :loading="loading" class="submit-btn"
                     @click="handleLogin">登 录</el-button>
        </el-tab-pane>

        <!-- 注册 -->
        <el-tab-pane label="注册" name="register">
          <el-form :model="regForm" label-width="70px">
            <el-form-item label="邮箱">
              <el-input v-model="regForm.email" placeholder="邮箱" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="regForm.username" placeholder="用户名" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="regForm.password" type="password" show-password
                        placeholder="至少 6 位" @keyup.enter="handleRegister" />
            </el-form-item>
          </el-form>
          <el-button type="primary" size="large" :loading="loading" class="submit-btn"
                     @click="handleRegister">注 册</el-button>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

const tab = ref('login')
const loading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const regForm = reactive({ email: '', username: '', password: '' })

async function handleLogin() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await userStore.login(loginForm)
    ElMessage.success('登录成功')
    router.push('/home')
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!regForm.email || !regForm.username || !regForm.password) {
    ElMessage.warning('请填写完整信息')
    return
  }
  loading.value = true
  try {
    await userStore.register(regForm)
    ElMessage.success('注册成功，欢迎使用')
    router.push('/home')
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a2a6c 0%, #3a5ba0 50%, #409eff 100%);
}
.login-card {
  width: 420px;
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.2);
}
.brand {
  text-align: center;
  margin-bottom: 24px;
}
.brand h1 {
  font-size: 24px;
  margin: 8px 0 4px;
  color: #303133;
}
.brand p {
  color: #909399;
  font-size: 13px;
}
.tabs {
  margin-top: 8px;
}
.submit-btn {
  width: 100%;
  margin-top: 8px;
}
</style>
