<template>
  <div class="result">
    <!-- 生成中：三步进度条 + 实时爬取 -->
    <GenerateProgress v-if="store.loading" />

    <!-- 空状态 -->
    <div v-else-if="!store.current" class="empty">
      <div class="empty-art"><Icon name="map" :size="44" /></div>
      <h3>还没有行程</h3>
      <p>在左侧描述你的旅行想法，一键生成每日行程与素材</p>
    </div>

    <!-- 结果 -->
    <template v-else>
      <div class="result-head">
        <div class="result-title">
          <h2>{{ store.current.preferences.destination || '我的行程' }}</h2>
          <div class="chips">
            <span class="chip chip-days">
              <Icon name="calendar" :size="13" />{{ store.current.preferences.days }} 天
            </span>
            <span v-if="store.current.preferences.pace" class="chip chip-pace">
              <Icon name="clock" :size="13" />{{ store.current.preferences.pace }}
            </span>
            <span
              v-for="i in store.current.preferences.interests"
              :key="i"
              class="chip"
            >
              {{ i }}
            </span>
            <span
              v-if="store.current.research.xhs_status === 'live'"
              class="chip chip-live"
            >
              <Icon name="book" :size="13" />小红书实时
            </span>
            <span
              v-else-if="store.current.research.xhs_status === 'cached'"
              class="chip chip-cached"
            >
              <Icon name="clock" :size="13" />缓存数据
            </span>
            <span
              v-else-if="store.current.research.xhs_status === 'fallback'"
              class="chip chip-fallback"
            >
              <Icon name="book" :size="13" />兜底数据
            </span>
            <span v-if="tokenText" class="chip chip-token">{{ tokenText }}</span>
          </div>
        </div>

        <div class="toolbar">
          <el-button @click="onRegenerate">
            <Icon name="refresh" :size="15" class="btn-ic" />重新生成
          </el-button>
          <el-button type="primary" @click="onCopy">
            <Icon name="copy" :size="15" class="btn-ic" />复制
          </el-button>
        </div>
      </div>

      <el-tabs v-model="tab" class="tabs">
        <el-tab-pane label="每日行程" name="itinerary">
          <div
            v-if="store.current.itinerary"
            class="itinerary-md"
            v-html="itineraryHtml"
          ></div>
          <el-empty v-else description="暂无行程内容" :image-size="72" />
        </el-tab-pane>

        <el-tab-pane label="信息素材" name="research">
          <ResearchPanel v-if="store.current" :research="store.current.research" />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import GenerateProgress from '@/components/GenerateProgress.vue'
import Icon from '@/components/Icon.vue'
import ResearchPanel from '@/components/ResearchPanel.vue'
import { useTripStore } from '@/store/trip'
import { renderMarkdown } from '@/utils/markdown'

const store = useTripStore()
const tab = ref('itinerary')

const itineraryHtml = computed(() => renderMarkdown(store.current?.itinerary ?? ''))

const tokenText = computed(() => {
  const u = store.current?.usage
  if (!u) return ''
  const sum = (t?: { input?: number; output?: number }) =>
    t ? (t.input || 0) + (t.output || 0) : 0
  const parts: string[] = []
  if (u.extract) parts.push(`抽取 ${sum(u.extract)}`)
  if (u.plan) parts.push(`生成 ${sum(u.plan)}`)
  return parts.length ? `${parts.join(' · ')} tokens` : ''
})

function onRegenerate() {
  if (store.current) store.generate(store.current.user_input)
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
.result {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-sm);
  min-height: 70vh;
  padding: 24px;
}

/* —— 空状态 —— */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 52vh;
  text-align: center;
  color: var(--c-muted);
}
.empty-art {
  width: 84px;
  height: 84px;
  border-radius: 24px;
  display: grid;
  place-items: center;
  background: var(--c-surface-2);
  color: var(--c-primary);
  border: 1px dashed var(--c-border-strong);
  margin-bottom: 16px;
}
.empty h3 {
  margin: 0 0 6px;
  font-family: var(--font-serif);
  color: var(--c-ink);
  font-size: 18px;
}
.empty p {
  margin: 0;
  font-size: 13.5px;
}

/* —— 结果头部 —— */
.result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.result-title h2 {
  margin: 0 0 10px;
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.3px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--c-ink-2);
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
}
.chip-days {
  color: var(--c-teal);
  background: var(--c-teal-soft);
  border-color: transparent;
}
.chip-pace {
  color: var(--c-primary-hover);
  background: var(--c-primary-soft);
  border-color: transparent;
}
.chip-live {
  color: var(--c-primary-hover);
  background: var(--c-primary-soft);
  border-color: transparent;
}
.chip-cached {
  color: var(--c-teal);
  background: var(--c-teal-soft);
  border-color: transparent;
}
.chip-fallback {
  color: #b45309;
  background: rgba(245, 158, 11, 0.12);
  border-color: transparent;
}
.chip-token {
  color: var(--c-muted);
  background: var(--c-surface-2);
  border-color: var(--c-border);
}
.toolbar {
  display: flex;
  gap: 10px;
}
.btn-ic {
  margin-right: 4px;
  vertical-align: -2px;
}

/* —— Markdown 渲染的行程 —— */
.itinerary-md :deep(h2) {
  margin: 22px 0 12px;
  padding-left: 12px;
  border-left: 3px solid var(--c-primary);
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--c-ink);
  line-height: 1.4;
}
.itinerary-md :deep(h2:first-child) {
  margin-top: 4px;
}
.itinerary-md :deep(h3) {
  margin: 14px 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: var(--c-ink);
}
.itinerary-md :deep(p) {
  margin: 0 0 6px;
  font-size: 14px;
  line-height: 1.85;
  color: var(--c-ink-2);
}
.itinerary-md :deep(strong) {
  color: var(--c-primary-hover);
  font-weight: 700;
}
.itinerary-md :deep(ul),
.itinerary-md :deep(ol) {
  margin: 4px 0 10px;
  padding-left: 22px;
}
.itinerary-md :deep(li) {
  margin: 3px 0;
  font-size: 14px;
  line-height: 1.8;
  color: var(--c-ink-2);
}
.itinerary-md :deep(li::marker) {
  color: var(--c-primary);
}
.itinerary-md :deep(a) {
  color: var(--c-primary-hover);
  text-decoration: none;
}
.itinerary-md :deep(a:hover) {
  text-decoration: underline;
}
</style>
