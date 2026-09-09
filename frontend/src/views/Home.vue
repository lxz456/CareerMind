<template>
  <div class="home">
    <div class="hero">
      <h1>你好，{{ userStore.username }}</h1>
      <p>CareerMind AI 基于多智能体架构，帮你完成职业成长</p>
    </div>

    <div class="cards">
      <!-- 路径A：规划提升 -->
      <el-card class="path-card" shadow="hover" @click="$router.push('/planning')">
        <div class="card-icon">
          <el-icon :size="40" color="#409eff"><TrendCharts /></el-icon>
        </div>
        <h3>规划提升</h3>
        <p>上传简历，AI 分析你的技能与目标岗位的差距，生成个性化学习路线</p>
        <el-button type="primary" round>开始规划</el-button>
      </el-card>

      <!-- 路径B：模拟面试 -->
      <el-card class="path-card" shadow="hover" @click="$router.push('/interview')">
        <div class="card-icon">
          <el-icon :size="40" color="#67c23a"><ChatDotRound /></el-icon>
        </div>
        <h3>模拟面试</h3>
        <p>HR / 技术 / 系统设计三类面试官，逐题问答，实时评分与改进建议</p>
        <el-button type="success" round>开始面试</el-button>
      </el-card>

      <!-- 路径C：题库/学习中心 -->
      <el-card class="path-card" shadow="hover" @click="$router.push('/knowledge')">
        <div class="card-icon">
          <el-icon :size="40" color="#e6a23c"><Notebook /></el-icon>
        </div>
        <h3>题库/学习中心</h3>
        <p>联网搜索真实面试题与学习资料，按标签/难度筛选，语义匹配推荐</p>
        <el-button type="warning" round>去搜索</el-button>
      </el-card>
    </div>

    <div class="features">
      <el-row :gutter="20">
        <el-col :span="6" v-for="f in features" :key="f.title">
          <el-card shadow="never">
            <el-icon :size="22" :color="f.color"><component :is="f.icon" /></el-icon>
            <h4>{{ f.title }}</h4>
            <p>{{ f.desc }}</p>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { useUserStore } from '../stores/user'

const userStore = useUserStore()

const features = [
  { title: '简历分析', desc: 'LLM 结构化解析简历，评估技能水平', icon: 'Document', color: '#409eff' },
  { title: '岗位匹配', desc: '基于技能语义检索真实岗位', icon: 'Search', color: '#e6a23c' },
  { title: '技能差距', desc: '逐技能对比你与目标岗位的差距', icon: 'DataAnalysis', color: '#f56c6c' },
  { title: '面试评估', desc: '逐题评分 + 完整报告 + 改进建议', icon: 'Trophy', color: '#67c23a' },
]
</script>

<style scoped>
.home {
  max-width: 1000px;
  margin: 0 auto;
}
.hero {
  text-align: center;
  padding: 48px 0 32px;
}
.hero h1 {
  font-size: 30px;
  color: #303133;
  margin-bottom: 8px;
}
.hero p {
  color: #909399;
  font-size: 15px;
}
.cards {
  display: flex;
  gap: 24px;
  margin: 24px 0;
}
.path-card {
  flex: 1;
  text-align: center;
  padding: 24px 8px;
  cursor: pointer;
  border-radius: 12px;
}
.card-icon {
  margin-bottom: 12px;
}
.path-card h3 {
  font-size: 20px;
  color: #303133;
  margin-bottom: 8px;
}
.path-card p {
  color: #909399;
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 16px;
  min-height: 44px;
}
.features {
  margin-top: 12px;
}
.features h4 {
  margin: 8px 0 4px;
  color: #303133;
}
.features p {
  color: #909399;
  font-size: 13px;
}
</style>
