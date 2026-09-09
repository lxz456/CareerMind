<template>
  <div v-loading="loading">
    <interview-result v-if="result" :result="result" />
    <el-empty v-else-if="!loading" description="暂未找到该面试结果" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getFeedback } from '../api/interview'
import InterviewResult from '../components/InterviewResult.vue'

const route = useRoute()
const loading = ref(true)
const result = ref(null)

onMounted(async () => {
  try {
    const data = await getFeedback(route.params.sessionId)
    result.value = data.result
  } catch (e) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
})
</script>
