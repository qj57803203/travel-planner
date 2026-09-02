<template>
  <div class="form-card">
    <div class="form-head">
      <h2>想去哪儿？</h2>
      <p class="form-sub">描述目的地、天数与偏好，剩下的交给 AI</p>
    </div>

    <el-input
      v-model="input"
      type="textarea"
      :rows="5"
      resize="none"
      class="textarea"
      placeholder="例如：9 月去东京玩 5 天，喜欢美食和拍照，不想太累，酒店想靠近地铁"
    />

    <div class="presets">
      <button
        v-for="p in presets"
        :key="p.label"
        class="preset"
        type="button"
        @click="input = p.text"
      >
        {{ p.label }}
      </button>
    </div>

    <el-button class="generate-btn" type="primary" :loading="store.loading" @click="onGenerate">
      <Icon v-if="!store.loading" name="sparkles" :size="16" />
      <span>{{ store.loading ? '正在规划…' : '生成行程' }}</span>
    </el-button>

    <div class="history-head">
      <span>历史记录</span>
      <span v-if="store.history.length" class="count">{{ store.history.length }}</span>
    </div>

    <el-empty v-if="!store.history.length" description="还没有生成过行程" :image-size="56" />
    <ul v-else class="history">
      <li
        v-for="t in store.history"
        :key="t.id"
        class="history-item"
        :class="{ active: store.current?.id === t.id }"
        @click="store.openTrip(t.id)"
      >
        <span class="dot" :style="{ background: dotColor(t.destination) }"></span>
        <div class="history-meta">
          <span class="name">{{ t.destination || '未命名' }}</span>
          <span class="sub">{{ t.days }} 天 · {{ relative(t.created_at) }}</span>
        </div>
        <Icon name="arrow" :size="15" class="history-arrow" />
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import Icon from '@/components/Icon.vue'
import { useTripStore } from '@/store/trip'

const store = useTripStore()
const input = ref('')

const presets = [
  { label: '东京 · 美食拍照', text: '9 月去东京玩 5 天，喜欢美食和拍照，不想太累，酒店想靠近地铁' },
  { label: '大阪 · 亲子轻松', text: '带娃去大阪玩 3 天，节奏轻松一点，想去环球影城，住市中心' },
  { label: '巴黎 · 艺术浪漫', text: '11 月去巴黎玩 4 天，喜欢博物馆和艺术，慢节奏，想吃法餐' },
]

const COLORS = ['#d9480f', '#0f766e', '#2f6fed', '#c026d3', '#b7791f', '#475569']

function dotColor(name: string) {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return COLORS[h % COLORS.length]
}

function relative(s: string) {
  const diff = Date.now() - new Date(s).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  const days = Math.floor(h / 24)
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  return new Date(s).toLocaleDateString('zh-CN')
}

function onGenerate() {
  if (!input.value.trim()) return
  store.generate(input.value.trim())
}

onMounted(() => store.loadHistory())
</script>

<style scoped>
.form-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-sm);
  padding: 22px;
}

.form-head h2 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.3px;
}
.form-sub {
  margin: 4px 0 16px;
  font-size: 12.5px;
  color: var(--c-muted);
}

.textarea :deep(.el-textarea__inner) {
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  font-size: 14px;
  line-height: 1.7;
  padding: 12px 14px;
  box-shadow: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.textarea :deep(.el-textarea__inner:focus) {
  border-color: var(--c-primary);
  box-shadow: 0 0 0 3px var(--c-primary-soft);
}

.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.preset {
  appearance: none;
  border: 1px solid var(--c-border);
  background: var(--c-surface-2);
  color: var(--c-ink-2);
  font-size: 12.5px;
  padding: 6px 11px;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.preset:hover {
  border-color: var(--c-primary);
  color: var(--c-primary-hover);
  background: var(--c-primary-soft);
}

.generate-btn {
  width: 100%;
  height: 46px;
  margin-top: 16px;
  border: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #d9480f 0%, #ef6b2a 100%);
  box-shadow: 0 8px 20px -8px rgba(217, 72, 15, 0.55);
  transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}
.generate-btn:hover {
  filter: brightness(1.03);
  transform: translateY(-1px);
  box-shadow: 0 12px 26px -8px rgba(217, 72, 15, 0.6);
}
.generate-btn:active {
  transform: translateY(0);
}
.generate-btn :deep(.el-icon) {
  margin-right: 5px;
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 22px 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--c-ink-2);
  letter-spacing: 0.5px;
}
.count {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  font-size: 12px;
  color: var(--c-muted);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
}

.history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.history-item:hover {
  background: var(--c-surface-2);
}
.history-item.active {
  background: var(--c-primary-soft);
  border-color: var(--c-primary);
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
}
.history-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--c-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub {
  font-size: 11.5px;
  color: var(--c-muted);
}
.history-arrow {
  color: var(--c-muted);
  flex: none;
  opacity: 0;
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.history-item:hover .history-arrow {
  opacity: 1;
  transform: translateX(2px);
}
</style>
