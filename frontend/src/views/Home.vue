<template>
  <el-container class="home">
    <el-header class="header">
      <h1>🧳 旅行规划 Agent</h1>
      <span class="subtitle">输入需求 → 自动搜集信息 → 生成每日行程</span>
    </el-header>

    <el-main class="main">
      <el-alert v-if="store.error" :title="store.error" type="error" show-icon closable class="alert" @close="store.error = ''" />
      <el-row :gutter="16">
        <el-col :span="8">
          <TripForm />
        </el-col>
        <el-col :span="16">
          <ItineraryView v-loading="store.loading" />
        </el-col>
      </el-row>
    </el-main>

    <el-footer class="footer">
      <el-button :disabled="!store.current" @click="onRegenerate">重新生成</el-button>
      <el-button type="primary" :disabled="!store.current" @click="onCopy">复制行程</el-button>
    </el-footer>
  </el-container>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'

import ItineraryView from '@/components/ItineraryView.vue'
import TripForm from '@/components/TripForm.vue'
import { useTripStore } from '@/store/trip'

const store = useTripStore()

function onRegenerate() {
  if (store.current) {
    store.generate(store.current.user_input)
  }
}

async function onCopy() {
  if (!store.current) return
  try {
    await navigator.clipboard.writeText(store.current.itinerary)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}
</script>

<style scoped>
.home {
  height: 100vh;
}
.header {
  display: flex;
  align-items: baseline;
  gap: 16px;
  background: #fff;
  border-bottom: 1px solid #eee;
}
.header h1 {
  font-size: 20px;
  margin: 0;
  line-height: 60px;
}
.subtitle {
  color: #999;
  font-size: 13px;
}
.main {
  background: #f5f7fa;
}
.alert {
  margin-bottom: 12px;
}
.footer {
  background: #fff;
  border-top: 1px solid #eee;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}
</style>
