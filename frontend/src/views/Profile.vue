<template>
  <div class="profile">
    <el-row :gutter="20">
      <!-- 左侧：面试历史 -->
      <el-col :xs="24" :lg="12">
        <el-card class="history-card">
          <template #header><b>面试历史（{{ sessions.length }}）</b></template>
          <el-empty v-if="!sessions.length" description="还没有进行模拟面试" :image-size="60" />
          <el-table v-else :data="sessions" size="small" @row-click="goSession">
            <el-table-column prop="title" label="面试" show-overflow-tooltip />
            <el-table-column label="类型" width="110">
              <template #default="{ row }">
                <el-tag size="small">{{ row.type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="sessionStatusType(row.status)" size="small">
                  {{ sessionStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column label="" width="120">
              <template #default="{ row }">
                <el-link v-if="row.status !== 'unavailable'" type="primary" class="act-link" @click.stop="goSession(row)">
                  {{ row.status === 'completed' ? '查看' : '继续' }}
                </el-link>
                <el-popconfirm title="确定删除这条面试历史？" @confirm="removeSession(row)">
                  <template #reference>
                    <el-link type="danger" class="act-link" @click.stop>删除</el-link>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 右侧：职业规划历史 -->
      <el-col :xs="24" :lg="12">
        <el-card class="history-card">
          <template #header><b>职业规划历史（{{ plans.length }}）</b></template>
          <el-empty v-if="!plans.length" description="还没有进行职业规划" :image-size="60" />
          <el-table v-else :data="plans" size="small" @row-click="openPlan">
            <el-table-column prop="target_position" label="目标岗位" show-overflow-tooltip>
              <template #default="{ row }">{{ row.target_position || '自动推断' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="planStatusType(row.status)" size="small">
                  {{ planStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column label="" width="120">
              <template #default="{ row }">
                <el-link type="primary" class="act-link" @click.stop="openPlan(row)">
                  {{ isPlanContinuable(row.status) ? '继续' : '查看' }}
                </el-link>
                <el-popconfirm title="确定删除这条职业规划历史？" @confirm="removePlan(row)">
                  <template #reference>
                    <el-link type="danger" class="act-link" @click.stop>删除</el-link>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 规划历史详情弹窗 -->
    <el-dialog v-model="planDialog" title="职业规划方案" width="720px" top="6vh">
      <div v-loading="planLoading">
        <template v-if="planDetail">
          <el-alert v-if="planDetail.status === 'failed'" type="error" :closable="false"
                    title="该次规划执行失败，无可用结果" show-icon />
          <template v-else>
            <template v-if="planDetail.resume_result">
              <h4 class="pd-title">简历分析</h4>
              <div class="pd-text">
                <p>姓名：{{ planDetail.resume_result.name || '-' }}</p>
                <p>目标岗位：{{ planDetail.career_plan_result?.target_position || '-' }}</p>
                <p v-if="planDetail.resume_result.overall_assessment">
                  评估：{{ planDetail.resume_result.overall_assessment }}
                </p>
              </div>
            </template>

            <template v-if="planDetail.job_result?.jobs?.length">
              <h4 class="pd-title">岗位匹配</h4>
              <ul class="pd-list">
                <li v-for="(job, i) in planDetail.job_result.jobs.slice(0, 5)" :key="i">
                  <b>{{ job.title }}</b> @ {{ job.company }}
                  <span class="pd-score">匹配度 {{ Math.round((job.score || 0) * 100) }}%</span>
                  <div class="pd-reason">{{ job.reason }}</div>
                </li>
              </ul>
            </template>

            <template v-if="planDetail.skill_gap_result">
              <h4 class="pd-title">技能差距</h4>
              <p>整体匹配度：{{ planDetail.skill_gap_result.match_percentage || 0 }}%</p>
              <ul class="pd-list">
                <li v-for="(s, i) in (planDetail.skill_gap_result.gaps || [])" :key="i">
                  <b>{{ s.skill }}</b>：当前 {{ s.current_level || 0 }}/5，
                  要求 {{ s.required_level || 0 }}/5（{{ s.priority || 'medium' }}）
                </li>
              </ul>
            </template>

            <template v-if="planDetail.career_plan_result">
              <h4 class="pd-title">学习规划</h4>
              <p class="pd-summary">{{ planDetail.career_plan_result.overview }}</p>
              <ul class="pd-list">
                <li
                  v-for="(milestone, i) in (planDetail.career_plan_result.key_milestones || planDetail.career_plan_result.milestones || [])"
                  :key="i"
                >
                  {{ formatMilestone(milestone) }}
                </li>
              </ul>
            </template>
          </template>
        </template>
      </div>
      <template #footer>
        <el-button @click="planDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listSessions, deleteSession } from '../api/interview'
import { listPlanHistory, getWorkflowResult, resumeCareerPlanning, deletePlan } from '../api/workflow'

const router = useRouter()
const sessions = ref([])
const plans = ref([])
const planDialog = ref(false)
const planLoading = ref(false)
const planDetail = ref(null)

onMounted(async () => {
  try { sessions.value = (await listSessions()).sessions || [] } catch (e) {}
  try { plans.value = (await listPlanHistory()).plans || [] } catch (e) {}
})

function goSession(row) {
  if (row.status === 'unavailable') {
    ElMessage.warning('该旧面试没有可恢复的状态')
    return
  }
  const suffix = row.status === 'completed' ? '/result' : ''
  router.push(`/interview/${row.session_id}${suffix}`)
}

const sessionStatusLabel = (status) => ({
  completed: '已完成',
  in_progress: '进行中',
  unavailable: '不可恢复',
}[status] || status)

const sessionStatusType = (status) => ({
  completed: 'success',
  in_progress: 'warning',
  unavailable: 'info',
}[status] || 'info')

const isPlanContinuable = (status) => ['pending', 'running', 'interrupted'].includes(status)

// 新版规划使用字符串形式的 key_milestones；对象分支兼容已有旧记录。
const formatMilestone = (milestone) => {
  if (typeof milestone === 'string') return milestone
  if (!milestone || typeof milestone !== 'object') return ''
  return [milestone.period, milestone.objective].filter(Boolean).join(' — ')
}

const planStatusLabel = (status) => ({
  pending: '等待中',
  running: '进行中',
  interrupted: '已中断',
  completed: '已完成',
  failed: '失败',
}[status] || status)

const planStatusType = (status) => ({
  pending: 'info',
  running: 'warning',
  interrupted: 'warning',
  completed: 'success',
  failed: 'danger',
}[status] || 'info')

async function openPlan(row) {
  if (isPlanContinuable(row.status)) {
    // 后端重启遗留的任务不会自动执行；只有用户点击“继续”时才显式恢复。
    if (row.status === 'interrupted' || row.status === 'pending') {
      try {
        const status = await resumeCareerPlanning(row.run_id)
        row.status = status.status
        row.progress = status.progress
        ElMessage.success('职业规划已从中断处继续')
      } catch (e) {
        return
      }
    }
    // run_id 放进 URL：规划页刷新后仍能恢复用户从历史列表选择的这一条任务。
    router.push({ path: '/planning', query: { run_id: row.run_id } })
    return
  }
  viewPlan(row)
}

async function viewPlan(row) {
  planDialog.value = true
  planLoading.value = true
  planDetail.value = null
  try {
    planDetail.value = await getWorkflowResult(row.run_id)
  } catch (e) {
    planDetail.value = { status: 'failed', summary: null }
  } finally {
    planLoading.value = false
  }
}

async function removeSession(row) {
  try {
    await deleteSession(row.session_id)
    sessions.value = sessions.value.filter(s => s.session_id !== row.session_id)
    ElMessage.success('已删除该面试历史')
  } catch (e) {
    // 拦截器已提示
  }
}

async function removePlan(row) {
  try {
    await deletePlan(row.run_id)
    plans.value = plans.value.filter(p => p.run_id !== row.run_id)
    ElMessage.success('已删除该职业规划历史')
  } catch (e) {
    // 拦截器已提示
  }
}
</script>

<style scoped>
.profile {
  max-width: 1400px;
  margin: 0 auto;
}
.history-card {
  margin-top: 20px;
}
.act-link {
  margin-right: 12px;
}
.pd-title {
  margin: 14px 0 6px;
  color: #303133;
  border-left: 3px solid #409eff;
  padding-left: 8px;
}
.pd-summary {
  color: #606266;
  line-height: 1.6;
  white-space: pre-wrap;
  margin: 0 0 6px;
}
.pd-text {
  color: #606266;
  line-height: 1.7;
}
.pd-list {
  margin: 4px 0 0 18px;
  color: #606266;
  line-height: 1.7;
}
.pd-score {
  color: #409eff;
  margin-left: 8px;
}
.pd-reason {
  color: #909399;
  font-size: 12px;
}
</style>
