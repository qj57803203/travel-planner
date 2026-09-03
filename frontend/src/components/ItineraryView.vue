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

      <div
        v-if="store.current && !store.current.preferences.departure"
        class="departure-bar"
      >
        <Icon name="pin" :size="14" class="departure-ic" />
        <span class="departure-text">从哪出发？设置后可自动补全城际交通</span>
        <el-input
          v-model="departureInput"
          size="small"
          placeholder="如：上海"
          class="departure-input"
          @keyup.enter="onSaveDeparture"
        />
        <el-button size="small" type="primary" @click="onSaveDeparture">记住</el-button>
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
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import GenerateProgress from '@/components/GenerateProgress.vue'
import Icon from '@/components/Icon.vue'
import ResearchPanel from '@/components/ResearchPanel.vue'
import { useTripStore } from '@/store/trip'
import { renderMarkdown } from '@/utils/markdown'

const store = useTripStore()
const tab = ref('itinerary')
const departureInput = ref('')

const itineraryHtml = computed(() => renderMarkdown(store.current?.itinerary ?? ''))

// 调试：监听 transit 数据变化
watch(
  () => store.current?.transit,
  (transit) => {
    console.log('[ItineraryView] transit data:', transit)
    console.log('[ItineraryView] transit source:', transit?.source)
    console.log('[ItineraryView] transit days:', transit?.days?.length)
    console.log('[ItineraryView] transit inter_city:', transit?.inter_city)
  },
  { immediate: true },
)

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

async function onSaveDeparture() {
  if (!departureInput.value.trim()) return
  await store.saveDeparture(departureInput.value)
  ElMessage.success('出发地已记住，下次自动补全城际交通')
  departureInput.value = ''
}
</script>

<style scoped>
.result {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  box-shadow: var(--shadow-sm);
  min-height: 40vh;
  padding: 20px;
}

/* —— 空状态 —— */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 36vh;
  text-align: center;
  color: #94a3b8;
}
.empty-art {
  width: 84px;
  height: 84px;
  border-radius: 24px;
  display: grid;
  place-items: center;
  background: #f5f7fa;
  color: #2563eb;
  border: 1px dashed #cbd5e1;
  margin-bottom: 16px;
}
.empty h3 {
  margin: 0 0 6px;
  font-family: var(--font-serif);
  color: #1e293b;
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
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: #1e293b;
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
  color: #475569;
  padding: 4px 10px;
  border-radius: 999px;
  background: #f5f7fa;
  border: 1px solid #e2e8f0;
}
.chip-days {
  color: #0f766e;
  background: #e3f2f0;
  border-color: transparent;
}
.chip-pace {
  color: #1d4ed8;
  background: #dbeafe;
  border-color: transparent;
}
.chip-live {
  color: #1d4ed8;
  background: #dbeafe;
  border-color: transparent;
}
.chip-cached {
  color: #0f766e;
  background: #e3f2f0;
  border-color: transparent;
}
.chip-fallback {
  color: #b45309;
  background: rgba(245, 158, 11, 0.12);
  border-color: transparent;
}
.chip-token {
  color: #94a3b8;
  background: #f5f7fa;
  border-color: #e2e8f0;
}
.toolbar {
  display: flex;
  gap: 10px;
}
.btn-ic {
  margin-right: 4px;
  vertical-align: -2px;
}

/* —— 设置出发地条 —— */
.departure-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #dbeafe;
  color: #475569;
  font-size: 13px;
}
.departure-ic {
  color: #2563eb;
  flex: none;
}
.departure-text {
  flex: 1;
  min-width: 0;
}
.departure-input {
  width: 140px;
}

/* —— Markdown 渲染的行程 —— */
.itinerary-md :deep(h2) {
  margin: 22px 0 12px;
  padding-left: 12px;
  border-left: 3px solid #2563eb;
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
}
.itinerary-md :deep(h2:first-child) {
  margin-top: 4px;
}
.itinerary-md :deep(h3) {
  margin: 14px 0 8px;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
}
.itinerary-md :deep(p) {
  margin: 0 0 6px;
  font-size: 14px;
  line-height: 1.85;
  color: #475569;
}
.itinerary-md :deep(strong) {
  color: #1d4ed8;
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
  color: #475569;
}
.itinerary-md :deep(li::marker) {
  color: #2563eb;
}
.itinerary-md :deep(a) {
  color: #1d4ed8;
  text-decoration: none;
}
.itinerary-md :deep(a:hover) {
  text-decoration: underline;
}
</style>
