<template>
  <div class="planning">
    <!-- 步骤条 -->
    <el-steps :active="step" align-center finish-status="success" class="steps">
      <el-step title="上传简历" />
      <el-step title="AI 分析" />
      <el-step title="查看结果" />
    </el-steps>

    <!-- 步骤 1：上传 -->
    <div v-if="step === 1" class="step-body">
      <el-card class="upload-card">
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          accept=".pdf,.docx"
          :on-change="handleFileChange"
          :on-exceed="handleExceed"
          :file-list="fileList"
        >
          <el-icon :size="48" color="#409eff"><UploadFilled /></el-icon>
          <div class="el-upload__text">将简历拖到此处，或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 PDF / DOCX，最大 10MB</div>
          </template>
        </el-upload>

        <el-form label-width="90px" class="goal-form">
          <el-form-item label="目标职位" required>
            <el-input v-model="targetPosition" placeholder="必填，如：Java开发工程师 / Java Developer" clearable maxlength="100" />
          </el-form-item>
          <el-form-item label="工作要求">
            <el-select v-model="jobRequirements" placeholder="选填" clearable style="width: 100%">
              <el-option label="3 年以下工作经验" value="under_3_years_experience" />
              <el-option label="3 年以上工作经验" value="more_than_3_years_experience" />
              <el-option label="无需工作经验" value="no_experience" />
              <el-option label="无学历要求" value="no_degree" />
            </el-select>
          </el-form-item>
          <el-form-item label="求职地区">
            <el-select v-model="targetLocation" placeholder="选填" clearable style="width: 100%">
              <el-option label="美国" value="us" />
              <el-option label="英国" value="gb" />
              <el-option label="德国" value="de" />
              <el-option label="日本" value="jp" />
              <el-option label="新加坡" value="sg" />
              <el-option label="中国香港" value="hk" />
              <el-option label="中国台湾" value="tw" />
            </el-select>
          </el-form-item>
        </el-form>

        <el-button type="primary" size="large" :loading="starting"
                   :disabled="!selectedFile || !targetPosition.trim()"
                   @click="startAnalysis">
          开始 AI 分析
        </el-button>
      </el-card>
    </div>

    <!-- 步骤 2：分析中 -->
    <div v-if="step === 2" class="step-body">
      <el-card class="progress-card">
        <el-progress type="circle" :percentage="progress" :width="140" :stroke-width="12"
                     color="#409eff" />
        <h3>{{ statusText }}</h3>
        <p class="sub">{{ currentStepText }}</p>
        <el-button v-if="failed" type="danger" plain @click="reset">重新开始</el-button>
        <el-button v-else-if="interrupted" type="primary" plain @click="router.push('/profile')">
          前往个人中心继续
        </el-button>
      </el-card>
    </div>

    <!-- 步骤 3：结果 -->
    <div v-if="step === 3" class="step-body">
      <el-card class="result-summary">
        <template #header>
          <div class="summary-header">
            <span>分析报告</span>
            <el-button size="small" @click="reset">重新规划</el-button>
          </div>
        </template>
        <pre class="summary-text">{{ result?.summary }}</pre>
      </el-card>

      <el-collapse v-model="activePanels" class="result-collapse">
        <!-- 简历分析 -->
        <el-collapse-item title="📄 简历分析" name="resume">
          <div v-if="result?.resume_result">
            <h4>{{ result.resume_result.name || '未识别姓名' }}</h4>
            <p class="sub">目标岗位：{{ targetPosition }}</p>
            <div class="tags">
              <el-tag v-for="(s, i) in result.resume_result.skills" :key="i" size="small"
                      class="tag" type="primary">{{ s }}</el-tag>
            </div>
            <p v-if="result.resume_result.overall_assessment" class="assessment">
              {{ result.resume_result.overall_assessment }}
            </p>
          </div>
        </el-collapse-item>

        <!-- 岗位搜索 -->
        <el-collapse-item title="💼 岗位搜索结果" name="jobs">
          <div v-if="result?.job_result?.jobs?.length">
            <el-table :data="result.job_result.jobs" size="small">
              <el-table-column prop="title" label="岗位" min-width="140" />
              <el-table-column prop="company" label="公司" min-width="100" />
              <el-table-column prop="location" label="地点" width="90" />
              <el-table-column prop="salary_range" label="薪资" width="130" />
              <el-table-column label="相关度" width="120">
                <template #default="{ row }">
                  <el-progress :percentage="Math.round((row.score || 0) * 100)" :stroke-width="10" />
                </template>
              </el-table-column>
              <el-table-column prop="reason" label="推荐理由" min-width="180" show-overflow-tooltip />
            </el-table>
          </div>
          <el-empty v-else description="抱歉，没有符合的岗位" :image-size="60" />
        </el-collapse-item>

        <!-- 技能差距 -->
        <el-collapse-item title="📊 技能差距" name="gap">
          <skill-gap-chart v-if="result?.skill_gap_result" :data="result.skill_gap_result" />
        </el-collapse-item>

        <!-- 学习规划 -->
        <el-collapse-item title="🗓️ 学习规划" name="plan">
          <plan-timeline v-if="result?.career_plan_result" :data="result.career_plan_result" />
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { uploadResume } from '../api/resume'
import {
  startCareerPlanning,
  getWorkflowStatus,
  getWorkflowResult,
} from '../api/workflow'
import SkillGapChart from '../components/SkillGapChart.vue'
import PlanTimeline from '../components/PlanTimeline.vue'

const route = useRoute()
const router = useRouter()
const step = ref(1)
const fileList = ref([])
const selectedFile = ref(null)
const targetPosition = ref('')
const jobRequirements = ref('')
const targetLocation = ref('')
const starting = ref(false)
const runId = ref('')
const failed = ref(false)
const interrupted = ref(false)
const progress = ref(0)
const result = ref(null)
const activePanels = ref(['resume', 'jobs', 'gap', 'plan'])

const STEP_LABELS = {
  parallel_analysis: '正在并行分析简历与搜索岗位',
  resume_analysis: '简历解析',
  job_search: '岗位搜索',
  skill_gap: '技能差距分析',
  career_plan: '生成学习规划',
  summary: '汇总报告',
}
const STEP_PROGRESS = { parallel_analysis: 0, resume_analysis: 20, job_search: 20, skill_gap: 60, career_plan: 80, summary: 100 }

const statusText = computed(() => {
  if (failed.value) return '分析失败'
  if (interrupted.value) return '任务已中断'
  return progress.value >= 100 ? '分析完成' : 'AI 分析中...'
})
const currentStepText = computed(() => {
  if (failed.value) return '请检查后端配置后重试'
  if (interrupted.value) return '后端曾重启，请在个人中心点击“继续”后恢复'
  return currentStepName.value ? `当前：${currentStepName.value}` : '准备中...'
})

const currentStepName = ref('')

function handleFileChange(file) {
  selectedFile.value = file.raw
  fileList.value = [file]
}
function handleExceed(files) {
  fileList.value = [files[0]]
  selectedFile.value = files[0].raw
}

async function startAnalysis() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择简历文件')
    return
  }
  const normalizedTargetPosition = targetPosition.value.trim()
  if (!normalizedTargetPosition) {
    ElMessage.warning('请输入目标岗位')
    return
  }
  starting.value = true
  try {
    // 1. 上传简历
    const resume = await uploadResume(selectedFile.value)
    // 2. 启动规划工作流
    const wf = await startCareerPlanning({
      resume_id: resume.id,
      target_position: normalizedTargetPosition,
      job_requirements: jobRequirements.value || null,
      target_location: targetLocation.value || null,
    })
    runId.value = wf.run_id
    step.value = 2
    pollStatus()
  } catch (e) {
    // 拦截器已提示
  } finally {
    starting.value = false
  }
}

let timer = null

async function applyWorkflowStatus(status) {
  currentStepName.value = STEP_LABELS[status.current_step] || ''
  progress.value = Math.round(status.progress ?? STEP_PROGRESS[status.current_step] ?? 0)

  if (status.status === 'completed') {
    result.value = await getWorkflowResult(runId.value)
    progress.value = 100
    failed.value = false
    interrupted.value = false
    step.value = 3
    return false
  }
  if (status.status === 'failed') {
    failed.value = true
    interrupted.value = false
    step.value = 2
    return false
  }
  if (status.status === 'interrupted') {
    interrupted.value = true
    failed.value = false
    step.value = 2
    return false
  }

  failed.value = false
  interrupted.value = false
  step.value = 2
  return true
}

async function pollStatus() {
  if (!runId.value) return
  const polledRunId = runId.value
  clearTimeout(timer)
  try {
    const status = await getWorkflowStatus(polledRunId)
    // 页面已切换到新建状态或另一个任务时，丢弃旧请求的迟到响应。
    if (runId.value !== polledRunId) return
    if (await applyWorkflowStatus(status)) {
      timer = setTimeout(pollStatus, 2000)
    }
  } catch (e) {
    if (runId.value === polledRunId) failed.value = true
  }
}

async function restoreRequestedPlanning() {
  clearTimeout(timer)
  const requestedRunId = typeof route.query.run_id === 'string'
    ? route.query.run_id
    : ''

  // 普通 /planning 始终是新建页面。只有个人中心携带 run_id 时才查看已有任务。
  if (!requestedRunId) {
    resetState()
    return
  }

  try {
    resetState()
    runId.value = requestedRunId
    const status = await getWorkflowStatus(runId.value)
    if (route.query.run_id !== requestedRunId || runId.value !== requestedRunId) return
    if (await applyWorkflowStatus(status)) {
      timer = setTimeout(pollStatus, 2000)
    }
  } catch (e) {
    // 请求拦截器负责提示；恢复失败时保留正常的新建规划页面。
  }
}

function resetState() {
  step.value = 1
  runId.value = ''
  result.value = null
  progress.value = 0
  failed.value = false
  interrupted.value = false
  fileList.value = []
  selectedFile.value = null
  targetPosition.value = ''
  jobRequirements.value = ''
  targetLocation.value = ''
  currentStepName.value = ''
  clearTimeout(timer)
}

function reset() {
  resetState()
  if (route.query.run_id) {
    router.replace({ path: '/planning' })
  }
}

// 同一 Planning 组件内从 ?run_id=... 切回侧边栏 /planning 时不会重新挂载，
// 因此监听 query 变化，确保普通入口立即回到初始页面。
watch(() => route.query.run_id, restoreRequestedPlanning)
onMounted(restoreRequestedPlanning)
onBeforeUnmount(() => clearTimeout(timer))
</script>

<style scoped>
.planning {
  max-width: 960px;
  margin: 0 auto;
}
.steps {
  margin: 24px 0;
}
.step-body {
  margin-top: 16px;
}
.upload-card, .progress-card {
  max-width: 560px;
  margin: 0 auto;
  text-align: center;
  padding: 16px;
}
.goal-form {
  margin: 20px 0 8px;
  text-align: left;
}
.progress-card {
  padding: 40px 0;
}
.progress-card h3 {
  margin-top: 16px;
  color: #303133;
}
.progress-card .sub {
  color: #909399;
  margin: 8px 0 16px;
}
.result-summary {
  margin-bottom: 16px;
}
.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.summary-text {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
}
.result-collapse {
  margin-bottom: 32px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}
.assessment {
  color: #606266;
  font-size: 14px;
  line-height: 1.6;
}
.sub {
  color: #909399;
  font-size: 13px;
}
</style>
