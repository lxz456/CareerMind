<template>
  <div class="plan-timeline">
    <el-timeline>
      <el-timeline-item
        v-for="month in props.data.plan || []"
        :key="month.month"
        :timestamp="`第 ${month.month} 个月`"
        placement="top"
        type="primary"
        color="#409eff"
      >
        <el-card shadow="hover">
          <h4>{{ month.theme }}</h4>
          <p class="outcome">{{ month.expected_outcome }}</p>
          <div v-for="(task, i) in month.tasks || []" :key="i" class="task">
            <div class="task-title">
              <el-icon><CaretRight /></el-icon>
              <span>{{ task.title }}</span>
              <el-tag v-if="task.estimated_hours" size="small" type="info">
                {{ task.estimated_hours }}h
              </el-tag>
            </div>
            <p class="task-desc" v-if="task.description">{{ task.description }}</p>
            <p class="task-idea" v-if="task.project_idea">💡 实战项目：{{ task.project_idea }}</p>
            <div v-if="(task.resources || []).length" class="resources">
              <el-tag
                v-for="(r, j) in task.resources"
                :key="j"
                size="small"
                class="res-tag"
                :type="r.url ? 'success' : 'info'"
              >
                <a v-if="r.url" :href="r.url" target="_blank" rel="noopener" class="res-link">{{ r.name || r.type }}</a>
                <template v-else>{{ r.name || r.type }}</template>
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-if="!props.data.plan || !props.data.plan.length" description="暂无规划" :image-size="60" />
  </div>
</template>

<script setup>
const props = defineProps({
  data: { type: Object, default: () => ({}) },
})
</script>

<style scoped>
.outcome {
  color: #909399;
  font-size: 13px;
  margin: 4px 0 12px;
}
.task {
  border-top: 1px dashed #e4e7ed;
  padding: 10px 0;
}
.task-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}
.task-desc {
  color: #606266;
  font-size: 13px;
  margin: 4px 0;
}
.task-idea {
  color: #e6a23c;
  font-size: 13px;
  margin: 4px 0;
}
.resources {
  margin-top: 6px;
}
.res-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}

.res-link {
  color: inherit;          /* 跟随 tag 文字色 */
  text-decoration: none;
}
.res-link:hover {
  text-decoration: underline;
}
</style>
