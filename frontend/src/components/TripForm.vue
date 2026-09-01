<template>
  <el-card class="form-card">
    <template #header>旅行需求</template>

    <el-input
      v-model="input"
      type="textarea"
      :rows="5"
      placeholder="例如：我 9 月去东京玩 5 天，喜欢美食和拍照，不想太累，酒店希望靠近地铁"
    />
    <el-button class="generate-btn" type="primary" :loading="store.loading" @click="onGenerate">
      生成行程
    </el-button>

    <el-divider>历史记录</el-divider>
    <el-empty v-if="!store.history.length" description="暂无历史记录" :image-size="60" />
    <ul v-else class="history">
      <li v-for="t in store.history" :key="t.id" @click="store.openTrip(t.id)">
        <span>{{ t.destination || '未命名' }} · {{ t.days }} 天</span>
        <span class="time">{{ formatTime(t.created_at) }}</span>
      </li>
    </ul>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { useTripStore } from '@/store/trip'

const store = useTripStore()
const input = ref('')

function onGenerate() {
  if (!input.value.trim()) return
  store.generate(input.value.trim())
}

function formatTime(s: string) {
  return new Date(s).toLocaleString('zh-CN')
}

onMounted(() => store.loadHistory())
</script>

<style scoped>
.generate-btn {
  width: 100%;
  margin-top: 12px;
}
.history {
  list-style: none;
  padding: 0;
  margin: 0;
}
.history li {
  display: flex;
  justify-content: space-between;
  padding: 8px 4px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
}
.history li:hover {
  color: #409eff;
}
.time {
  color: #999;
  font-size: 12px;
}
</style>
