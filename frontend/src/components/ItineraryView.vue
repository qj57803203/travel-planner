<template>
  <el-card class="result-card">
    <el-tabs v-model="tab">
      <el-tab-pane label="每日行程" name="itinerary">
        <el-empty v-if="!store.current" description="输入需求后，点击「生成行程」查看结果" />
        <template v-else>
          <div class="meta">
            <el-tag v-if="store.current.preferences.destination">
              {{ store.current.preferences.destination }}
            </el-tag>
            <el-tag type="info">{{ store.current.preferences.days }} 天</el-tag>
            <el-tag type="warning">{{ store.current.preferences.pace }}</el-tag>
            <el-tag v-for="i in store.current.preferences.interests" :key="i" type="success">
              {{ i }}
            </el-tag>
          </div>
          <pre class="itinerary">{{ store.current.itinerary || '（无内容）' }}</pre>
        </template>
      </el-tab-pane>

      <el-tab-pane label="信息素材" name="research">
        <ResearchPanel v-if="store.current" :research="store.current.research" />
        <el-empty v-else description="暂无素材" />
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import ResearchPanel from '@/components/ResearchPanel.vue'
import { useTripStore } from '@/store/trip'

const store = useTripStore()
const tab = ref('itinerary')
</script>

<style scoped>
.result-card {
  min-height: 70vh;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.itinerary {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.8;
  margin: 0;
  background: #fafafa;
  padding: 16px;
  border-radius: 6px;
}
</style>
