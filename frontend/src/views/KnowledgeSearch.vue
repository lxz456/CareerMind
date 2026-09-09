<template>
  <div class="knowledge">
    <el-card class="search-card">
      <template #header><b>题库 / 学习中心</b></template>

      <div class="controls">
        <el-radio-group v-model="type" @change="onTypeChange">
          <el-radio-button label="interview">面试题</el-radio-button>
          <el-radio-button label="resource">学习资源</el-radio-button>
        </el-radio-group>

        <el-input v-model="query" :placeholder="type === 'interview' ? '输入你想搜的面试题，如：如何设计一个 RAG 系统' : '输入你想学的内容，如：LangChain 教程'"
                  class="q-input" clearable @keyup.enter="doSearch">
          <template #append>
            <el-button :loading="loading" @click="doSearch">搜索</el-button>
          </template>
        </el-input>

        <el-select v-if="type === 'interview'" v-model="category" placeholder="分类" clearable style="width: 130px">
          <el-option label="技术题" value="technical" />
          <el-option label="行为题" value="behavioral" />
          <el-option label="系统设计" value="system_design" />
        </el-select>
        <el-select v-if="type === 'interview'" v-model="difficulty" placeholder="难度" clearable style="width: 110px">
          <el-option label="简单" value="easy" />
          <el-option label="中等" value="medium" />
          <el-option label="困难" value="hard" />
        </el-select>

        <el-checkbox v-model="refresh">
          {{ type === 'interview' ? '生成新题' : '实时搜索（联网采集最新）' }}
        </el-checkbox>
      </div>
    </el-card>

    <el-card v-if="searched" class="result-card">
      <template #header>
        <span>搜索结果（{{ results.length }}）{{ fromCache ? ' · 来自缓存' : '' }}</span>
      </template>

      <el-empty v-if="!results.length && !loading" description="没有找到相关内容" />
      <div v-loading="loading" class="list">
        <!-- 面试题 -->
        <template v-if="type === 'interview'">
          <div v-for="q in results" :key="q.id" class="item-qa">
            <div class="iq-head">
              <el-tag size="small" type="primary">{{ q.category || 'general' }}</el-tag>
              <el-tag size="small" :type="q.difficulty === 'hard' ? 'danger' : (q.difficulty === 'medium' ? 'warning' : 'info')">
                {{ q.difficulty || 'medium' }}
              </el-tag>
              <span v-if="q.score != null" class="score">相似度 {{ (q.score * 100).toFixed(0) }}%</span>
            </div>
            <p class="iq-q">{{ q.question }}</p>
            <div v-if="q.expected_points?.length" class="iq-points">
              <b>考察点：</b>
              <el-tag v-for="(p, i) in q.expected_points" :key="i" size="small" effect="plain" class="tag">{{ p }}</el-tag>
            </div>
          </div>
        </template>

        <!-- 学习资源 -->
        <template v-else>
          <div v-for="r in results" :key="r.id" class="item-qa">
            <div class="iq-head">
              <el-tag size="small" type="success">{{ r.type || 'resource' }}</el-tag>
              <span v-if="r.score != null" class="score">相关度 {{ (r.score * 100).toFixed(0) }}%</span>
            </div>
            <a v-if="r.url" :href="r.url" target="_blank" class="res-name">{{ r.name }}</a>
            <p v-else class="res-name">{{ r.name }}</p>
            <div class="iq-answer">{{ r.description }}</div>
            <div v-if="r.topic" class="iq-points"><el-tag size="small" effect="plain">{{ r.topic }}</el-tag></div>
          </div>
        </template>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { searchKnowledge } from '../api/knowledge'

const type = ref('interview')
const query = ref('')
const category = ref('')
const difficulty = ref('')
const refresh = ref(false)
const loading = ref(false)
const searched = ref(false)
const results = ref([])
const fromCache = ref(false)

function onTypeChange() {
  results.value = []
  searched.value = false
}

async function doSearch() {
  if (!query.value.trim()) {
    ElMessage.warning('请输入搜索内容')
    return
  }
  loading.value = true
  searched.value = true
  try {
    const res = await searchKnowledge({
      type: type.value,
      query: query.value.trim(),
      category: category.value || null,
      difficulty: difficulty.value || null,
      refresh: refresh.value,
      limit: 20,
    })
    results.value = res.results || []
    fromCache.value = res.from_cache
  } catch (e) {
    results.value = []
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.knowledge {
  max-width: 960px;
  margin: 0 auto;
}
.search-card {
  margin-bottom: 20px;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.q-input {
  flex: 1;
  min-width: 260px;
}
.result-card {
  margin-bottom: 20px;
}
.list {
  min-height: 120px;
}
.item-qa {
  padding: 12px 4px;
  border-bottom: 1px solid #ebeef5;
}
.item-qa:last-child {
  border-bottom: none;
}
.iq-head {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.score {
  color: #409eff;
  font-size: 12px;
  margin-left: auto;
}
.iq-q {
  font-size: 15px;
  color: #303133;
  line-height: 1.6;
  margin: 0 0 8px;
}
.iq-points {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 6px;
}
.tag {
  margin: 0;
}
.iq-answer {
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
}
.res-name {
  font-size: 16px;
  color: #409eff;
  font-weight: 600;
  text-decoration: none;
}
</style>
