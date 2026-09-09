<template>
  <div class="result" v-if="result">
    <!-- 总分 -->
    <el-card class="score-card">
      <div class="score-wrap">
        <el-progress type="circle" :percentage="scorePct" :width="150" :stroke-width="12"
                     :color="scoreColor" />
        <div class="score-info">
          <h2>{{ result.overall_assessment }}</h2>
          <p class="score-sub">综合评分：{{ result.total_score }} / 10</p>
        </div>
      </div>
    </el-card>

    <!-- 强项 / 弱项 -->
    <el-row :gutter="20" class="summary-row">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><b>✅ 强项</b></template>
          <el-empty v-if="!result.strengths?.length" description="暂无" :image-size="40" />
          <ul v-else class="list"><li v-for="(s, i) in result.strengths" :key="i">{{ s }}</li></ul>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><b>⚠️ 待改进</b></template>
          <el-empty v-if="!result.areas_to_improve?.length" description="暂无" :image-size="40" />
          <ul v-else class="list"><li v-for="(s, i) in result.areas_to_improve" :key="i">{{ s }}</li></ul>
        </el-card>
      </el-col>
    </el-row>

    <!-- 建议 -->
    <el-card v-if="result.tips?.length" class="tips-card">
      <template #header><b>💡 备考建议</b></template>
      <ol class="list"><li v-for="(t, i) in result.tips" :key="i">{{ t }}</li></ol>
    </el-card>

    <!-- 逐题反馈 -->
    <el-collapse class="detail-collapse">
      <el-collapse-item
        v-for="(fb, i) in result.feedbacks || []"
        :key="fb.question_id || i"
        :title="feedbackTitle(fb, i)"
      >
        <p class="fb-q"><b>题目：</b>{{ fb.question }}</p>
        <p class="fb-a"><b>你的回答：</b>{{ fb.answer }}</p>
        <p class="fb-c"><b>评语：</b>{{ fb.comments }}</p>
        <div v-if="fb.strengths?.length" class="fb-sec">✅ <span v-for="(s, j) in fb.strengths" :key="j" class="chip">{{ s }}</span></div>
        <div v-if="fb.improvements?.length" class="fb-sec">⚠️ <span v-for="(s, j) in fb.improvements" :key="j" class="chip warn">{{ s }}</span></div>
        <div v-if="fb.model_answer" class="fb-model">
          <b>参考回答：</b>
          <p>{{ fb.model_answer }}</p>
        </div>
      </el-collapse-item>
    </el-collapse>

    <div class="actions">
      <el-button type="primary" @click="$router.push('/interview')">再练一次</el-button>
      <el-button @click="$router.push('/home')">返回首页</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, default: null },
})

const scorePct = computed(() => Math.round((props.result?.total_score || 0) * 10))
const scoreColor = computed(() => {
  const s = props.result?.total_score || 0
  if (s >= 8) return '#67c23a'
  if (s >= 6) return '#409eff'
  if (s >= 4) return '#e6a23c'
  return '#f56c6c'
})

const feedbackTitle = (feedback, index) => {
  const questionNumber = feedback.question_number || index + 1
  const suffix = feedback.is_follow_up ? '追问' : ''
  return `第 ${questionNumber} 题${suffix} · ${feedback.score} 分`
}
</script>

<style scoped>
.result {
  max-width: 860px;
  margin: 0 auto;
  padding-bottom: 32px;
}
.score-card {
  margin-bottom: 20px;
}
.score-wrap {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 16px;
}
.score-info h2 {
  font-size: 17px;
  color: #303133;
  line-height: 1.6;
}
.score-sub {
  color: #909399;
  margin-top: 8px;
}
.summary-row {
  margin-bottom: 20px;
}
.list {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.9;
}
.tips-card {
  margin-bottom: 20px;
}
.detail-collapse {
  margin-bottom: 20px;
}
.fb-q, .fb-a, .fb-c {
  color: #606266;
  font-size: 14px;
  margin: 6px 0;
}
.fb-sec {
  margin-top: 8px;
}
.chip {
  display: inline-block;
  background: #f0f9eb;
  color: #67c23a;
  padding: 2px 10px;
  border-radius: 12px;
  margin-right: 6px;
  margin-bottom: 4px;
  font-size: 13px;
}
.chip.warn {
  background: #fef0f0;
  color: #f56c6c;
}
.fb-model {
  background: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  margin-top: 10px;
  color: #606266;
  font-size: 14px;
}
.actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
