<template>
  <div class="personal-profile">
    <el-card class="profile-card">
      <template #header><b>个人资料</b></template>

      <el-form label-width="90px">
        <el-form-item label="用户名">
          <span>{{ profile.username || '-' }}</span>
        </el-form-item>
        <el-form-item label="邮箱">
          <span>{{ profile.email || '-' }}</span>
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.full_name" placeholder="选填" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.bio" type="textarea" :rows="3" placeholder="选填" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="选填" />
        </el-form-item>
        <el-form-item label="头像">
          <el-input v-model="form.avatar_url" placeholder="选填，图片 URL" />
        </el-form-item>
        <el-form-item label="当前级别">
          <el-input v-model="form.current_level" placeholder="选填，如：高级 / 资深" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveProfile">
            保存资料
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getProfile, updateProfile } from '../api/user'

const profile = ref({})
const form = ref({
  full_name: '',
  bio: '',
  phone: '',
  avatar_url: '',
  current_level: '',
})
const saving = ref(false)

onMounted(loadProfile)

async function loadProfile() {
  try {
    const data = await getProfile()
    profile.value = data
    form.value = {
      full_name: data.full_name || '',
      bio: data.bio || '',
      phone: data.phone || '',
      avatar_url: data.avatar_url || '',
      current_level: data.current_level || '',
    }
  } catch (e) {
    // 请求拦截器统一展示错误。
  }
}

async function saveProfile() {
  saving.value = true
  try {
    const updated = await updateProfile(form.value)
    profile.value = { ...profile.value, ...updated }
    ElMessage.success('资料已保存')
  } catch (e) {
    // 请求拦截器统一展示错误。
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.personal-profile {
  max-width: 680px;
  margin: 20px auto;
}
.profile-card {
  width: 100%;
}
</style>
