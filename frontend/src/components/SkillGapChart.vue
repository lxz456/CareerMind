<template>
  <div class="skill-gap">
    <!-- 匹配度 -->
    <div v-if="hasRequiredSkills" class="match-rate">
      <el-progress type="dashboard" :percentage="matchPercentage" :width="120"
                   :stroke-width="10" color="#409eff" />
      <span class="match-label">整体匹配度</span>
    </div>

    <!-- 技能对比 -->
    <div v-if="hasRequiredSkills" class="skills">
      <div v-for="(row, i) in mergedSkills" :key="i" class="skill-row">
        <span class="skill-name">{{ row.skill }}</span>
        <div class="bars">
          <div class="bar current" :style="{ width: row.current * 20 + '%' }" :title="`当前 ${row.current}/5`"></div>
          <div class="bar required" :style="{ width: row.required * 20 + '%' }" :title="`要求 ${row.required}/5`"></div>
        </div>
        <span class="skill-tag" :class="gapClass(row)">{{ row.current >= row.required ? '已达标' : `差 ${row.required - row.current} 级` }}</span>
      </div>
    </div>
    <el-empty v-else description="岗位要求不足，暂时无法生成技能差距" :image-size="60" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const matchPercentage = computed(() => Math.round(props.data.match_percentage || 0))
const hasRequiredSkills = computed(() => (props.data.required_skills || []).length > 0)

// 只展示目标岗位要求的技能；优先使用 gaps 中由模型评估的当前等级。
const mergedSkills = computed(() => {
  const currentMap = {}
  ;(props.data.current_skills || []).forEach((s) => {
    currentMap[String(s.skill || '').trim().toLowerCase()] = Number(s.level) || 0
  })
  const gapMap = {}
  ;(props.data.gaps || []).forEach((gap) => {
    gapMap[String(gap.skill || '').trim().toLowerCase()] = Number(gap.current_level) || 0
  })
  return (props.data.required_skills || []).map((required) => {
    const key = String(required.skill || '').trim().toLowerCase()
    return {
      skill: required.skill,
      current: key in gapMap ? gapMap[key] : (currentMap[key] || 0),
      required: Number(required.level) || 0,
    }
  })
})

function gapClass(row) {
  return row.current >= row.required ? 'tag-ok' : 'tag-gap'
}
</script>

<style scoped>
.skill-gap {
  padding: 8px;
}
.match-rate {
  text-align: center;
  margin-bottom: 20px;
}
.match-label {
  display: block;
  margin-top: 8px;
  color: #909399;
  font-size: 13px;
}
.skills {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.skill-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.skill-name {
  width: 100px;
  font-weight: 500;
  color: #303133;
}
.bars {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bar {
  height: 8px;
  border-radius: 6px;
  transition: width 0.4s;
}
.bar.current {
  background: #409eff;
}
.bar.required {
  background: #e6a23c;
}
.skill-tag {
  width: 80px;
  text-align: center;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}
.tag-ok {
  color: #67c23a;
  background: #f0f9eb;
}
.tag-gap {
  color: #f56c6c;
  background: #fef0f0;
}
</style>
