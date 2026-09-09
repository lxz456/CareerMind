<template>
  <div class="interview">
    <div class="page-title">
      <h2>选择面试类型</h2>
      <p>由不同的 AI 面试官出题，逐题作答并实时评分</p>
    </div>

    <el-row :gutter="20" class="type-cards">
      <el-col :span="6" v-for="t in types" :key="t.value">
        <el-card
          class="type-card"
          :class="{ active: selectedType === t.value }"
          shadow="hover"
          @click="selectedType = t.value"
        >
          <el-icon :size="36" :color="t.color"><component :is="t.icon" /></el-icon>
          <h3>{{ t.label }}</h3>
          <p>{{ t.desc }}</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="config-card">
      <el-row :gutter="20" align="middle">
        <el-col :span="8">
          <div class="config-label">出题模式</div>
          <el-radio-group v-model="questionMode">
            <el-radio-button value="review">复习巩固</el-radio-button>
            <el-radio-button value="advanced">进阶提升</el-radio-button>
          </el-radio-group>
        </el-col>
        <el-col :span="6">
          <div class="config-label">题目数量</div>
          <el-slider v-model="questionCount" :min="3" :max="10" show-stops />
        </el-col>
        <el-col :span="6">
          <div class="config-label">目标岗位</div>
          <el-input v-model="jobTitle" placeholder="必填，如 LLM Engineer" clearable maxlength="100" />
        </el-col>
        <el-col :span="4">
          <el-button type="primary" size="large" :loading="starting"
                     :disabled="!jobTitle.trim()" class="start-btn"
                     @click="start">
            开始面试
          </el-button>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { startInterview } from '../api/interview'

const router = useRouter()

const types = [
  { value: 'hr', label: 'HR 面试', desc: '项目经历、职业规划、行为面试', icon: 'User', color: '#67c23a' },
  { value: 'technical', label: '技术面试', desc: '技术深度、编程能力、框架原理', icon: 'Cpu', color: '#409eff' },
  { value: 'system_design', label: '系统设计', desc: '架构设计、扩展性、分布式', icon: 'Connection', color: '#e6a23c' },
  { value: 'mixed', label: '混合面试', desc: 'HR + 技术 + 架构全面评估', icon: 'Aim', color: '#f56c6c' },
]

const selectedType = ref('technical')
const questionCount = ref(5)
const questionMode = ref('review')
const jobTitle = ref('')
const starting = ref(false)

async function start() {
  const normalizedJobTitle = jobTitle.value.trim()
  if (!normalizedJobTitle) {
    ElMessage.warning('请输入目标岗位')
    return
  }
  starting.value = true
  try {
    const session = await startInterview({
      interview_type: selectedType.value,
      question_count: questionCount.value,
      job_title: normalizedJobTitle,
      question_mode: questionMode.value,
    })
    // 把面试会话初始化数据存入 localStorage，供 InterviewSession 读取（刷新可恢复）
    localStorage.setItem(`interview_${session.session_id}`, JSON.stringify({
      interview_type: session.interview_type,
      current_question: session.current_question,
      current_question_index: session.current_question_index,
      total_questions: session.total_questions,
      answered_count: session.answered_count || 0,
    }))
    router.push(`/interview/${session.session_id}`)
  } catch (e) {
    // 拦截器已提示
  } finally {
    starting.value = false
  }
}
</script>

<style scoped>
.interview {
  max-width: 960px;
  margin: 0 auto;
}
.page-title {
  text-align: center;
  padding: 24px 0 16px;
}
.page-title h2 {
  font-size: 24px;
  color: #303133;
}
.page-title p {
  color: #909399;
  margin-top: 4px;
}
.type-cards {
  margin-bottom: 20px;
}
.type-card {
  text-align: center;
  padding: 12px 4px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.2s;
}
.type-card.active {
  border-color: #409eff;
}
.type-card h3 {
  margin: 10px 0 4px;
  color: #303133;
}
.type-card p {
  color: #909399;
  font-size: 12px;
}
.config-card {
  padding: 8px 16px;
}
.config-label {
  color: #606266;
  margin-bottom: 8px;
  font-size: 14px;
}
.start-btn {
  width: 100%;
}
</style>
