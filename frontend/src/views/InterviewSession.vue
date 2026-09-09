<template>
  <div class="session">
    <!-- 题目进度 -->
    <div class="progress-bar">
      <span>第 {{ currentIndex + 1 }} / {{ totalQuestions }} 题</span>
      <el-progress :percentage="progressPct" :stroke-width="10" class="bar" />
      <span class="answered-count">已回答 {{ answeredCount }} 轮</span>
    </div>

    <!-- 空态：题库为空 / LLM 未生成题目 -->
    <div v-if="loading" class="empty-state" v-loading="true"></div>
    <div v-else-if="!totalQuestions" class="empty-state">
      <el-empty description="暂未生成面试题">
        <el-button type="primary" @click="$router.push('/interview')">返回重试</el-button>
      </el-empty>
    </div>

    <!-- 当前题 -->
    <el-card v-else class="question-card">
      <div class="q-header">
        <el-tag size="small" :type="typeColor">{{ typeLabel }}</el-tag>
        <el-tag v-if="currentQ?.difficulty" size="small" type="info">
          {{ difficultyLabel }}
        </el-tag>
        <el-tag v-if="currentQ?.is_follow_up" size="small" type="warning">深入追问</el-tag>
      </div>
      <h3 class="question-text">{{ currentQ?.question }}</h3>

      <el-input
        v-model="answer"
        type="textarea"
        :rows="7"
        placeholder="在这里输入你的回答... 尽量结构化、具体"
        class="answer-input"
      />
      <div class="actions">
        <el-button type="primary" size="large" :loading="submitting" :disabled="!answer.trim()"
                   @click="submit">
          提交回答
        </el-button>
      </div>
      <div v-if="streamMessage" class="stream-status">
        <el-icon v-if="submitting" class="is-loading"><Loading /></el-icon>
        <span>{{ streamMessage }}</span>
      </div>
    </el-card>

    <!-- 上一题评分 -->
    <el-card v-if="lastFeedback" class="feedback-card">
      <template #header>
        <div class="fb-header">
          <span>上一题评分</span>
          <el-rate :model-value="lastFeedback.score" disabled show-score score-template="{value} 分" />
        </div>
      </template>
      <p class="fb-comment">{{ lastFeedback.comments }}</p>
      <div v-if="lastFeedback.strengths?.length" class="fb-section">
        <b>✅ 亮点</b>
        <ul><li v-for="(s, i) in lastFeedback.strengths" :key="i">{{ s }}</li></ul>
      </div>
      <div v-if="lastFeedback.improvements?.length" class="fb-section">
        <b>⚠️ 改进</b>
        <ul><li v-for="(s, i) in lastFeedback.improvements" :key="i">{{ s }}</li></ul>
      </div>
      <div v-if="lastFeedback.model_answer" class="fb-section">
        <b>💡 参考回答</b>
        <p class="model-answer">{{ lastFeedback.model_answer }}</p>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getFeedback, streamAnswer } from '../api/interview'

const route = useRoute()
const router = useRouter()
const sessionId = route.params.sessionId

// 会话初始状态：从 start 接口返回，存 localStorage 以便刷新恢复
const init = JSON.parse(localStorage.getItem(`interview_${sessionId}`) || '{}')

const interviewType = ref(init.interview_type || '')
const currentQ = ref(init.current_question || null)
const currentIndex = ref(init.current_question_index || 0)
const totalQuestions = ref(init.total_questions || 0)
const answeredCount = ref(init.answered_count || 0)
const typeLabel = computed(() => ({ hr: 'HR 面试', technical: '技术面试', system_design: '系统设计', mixed: '混合面试' }[interviewType.value] || '面试'))
const lastFeedback = ref(null)
const loading = ref(true)

const answer = ref('')
const submitting = ref(false)
const streamMessage = ref('')

const typeColor = computed(() => ({ hr: 'success', technical: 'primary', system_design: 'warning', mixed: 'danger' }[interviewType.value] || 'primary'))
const difficultyLabel = computed(() => ({ easy: '简单', medium: '中等', hard: '困难' }[currentQ.value?.difficulty] || ''))
const progressPct = computed(() => Math.round(((currentIndex.value) / totalQuestions.value) * 100))

// 每步保存会话状态，刷新可恢复
function persistSession() {
  localStorage.setItem(`interview_${sessionId}`, JSON.stringify({
    interview_type: interviewType.value,
    current_question: currentQ.value,
    current_question_index: currentIndex.value,
    total_questions: totalQuestions.value,
    answered_count: answeredCount.value,
  }))
}

async function submit() {
  submitting.value = true
  streamMessage.value = '正在提交回答'
  try {
    const resp = await streamAnswer(sessionId, answer.value, (event) => {
      if (event.message) streamMessage.value = event.message
    })
    lastFeedback.value = resp.last_feedback || null
    answeredCount.value = resp.answered_count || 0
    if (resp.status === 'completed') {
      localStorage.removeItem(`interview_${sessionId}`)
      ElMessage.success('面试完成！')
      router.push(`/interview/${sessionId}/result`)
      return
    }
    // 更新到下一题
    currentIndex.value = resp.current_question_index
    currentQ.value = resp.current_question
    totalQuestions.value = resp.total_questions
    answer.value = ''
    streamMessage.value = ''
    persistSession()
  } catch (e) {
    ElMessage.error(e.message || '面试处理失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    // The server-side checkpoint is authoritative after a refresh or re-login.
    const session = await getFeedback(sessionId)
    if (session.status === 'completed') {
      localStorage.removeItem(`interview_${sessionId}`)
      router.replace(`/interview/${sessionId}/result`)
      return
    }
    interviewType.value = session.interview_type
    currentQ.value = session.current_question
    currentIndex.value = session.current_question_index
    totalQuestions.value = session.total_questions
    answeredCount.value = session.answered_count || 0
    persistSession()
  } catch (e) {
    // The interceptor reports unavailable/deleted sessions.
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.session {
  max-width: 820px;
  margin: 0 auto;
}
.empty-state {
  margin-top: 80px;
}
.progress-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 20px 0;
  color: #606266;
}
.progress-bar .bar {
  flex: 1;
}
.answered-count {
  white-space: nowrap;
  color: #909399;
  font-size: 13px;
}
.question-card {
  margin-bottom: 20px;
}
.q-header {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.question-text {
  font-size: 18px;
  color: #303133;
  line-height: 1.6;
  margin-bottom: 16px;
}
.answer-input {
  margin-bottom: 16px;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.stream-status {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 10px;
  color: #409eff;
  font-size: 14px;
}
.feedback-card {
  margin-bottom: 32px;
}
.fb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.fb-comment {
  color: #606266;
}
.fb-section {
  margin-top: 10px;
}
.fb-section ul {
  margin: 4px 0 0 18px;
  color: #606266;
}
.model-answer {
  color: #606266;
  background: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  margin-top: 4px;
}
</style>
