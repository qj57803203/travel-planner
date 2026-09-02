<template>
  <div class="result" v-loading="store.loading && store.current" element-loading-text="正在生成行程…">
    <!-- 首次加载骨架屏 -->
    <div v-if="store.loading && !store.current" class="skeleton">
      <div class="sk sk-title"></div>
      <div class="sk sk-chips"></div>
      <div v-for="n in 3" :key="n" class="sk sk-day"></div>
    </div>

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
          <div v-if="days.length" class="days">
            <div v-for="(d, i) in days" :key="i" class="day-card">
              <div class="day-head">
                <span class="day-badge">{{ i + 1 }}</span>
                <h3>{{ d.title || '行程' }}</h3>
              </div>
              <div class="day-body">
                <template v-for="(line, j) in d.lines" :key="j">
                  <p v-if="line.trim()" class="day-line" :class="{ time: isTime(line) }">
                    {{ line }}
                  </p>
                </template>
              </div>
            </div>
          </div>
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

import Icon from '@/components/Icon.vue'
import ResearchPanel from '@/components/ResearchPanel.vue'
import { useTripStore } from '@/store/trip'

const store = useTripStore()
const tab = ref('itinerary')

interface DayBlock {
  title: string
  lines: string[]
}

const TIME_RE = /^(上午|下午|晚上|早上|中午|清晨|傍晚|凌晨|早餐|午餐|晚餐|夜宵)/

const days = computed<DayBlock[]>(() => parseDays(store.current?.itinerary ?? ''))

function isTime(line: string) {
  return TIME_RE.test(line.trim())
}

function parseDays(text: string): DayBlock[] {
  const lines = text.split('\n')
  const dayRe = /^(Day\s*\d+|第\s*[0-9一二三四五六七八九十]+\s*天)\s*[:：]?\s*$/i
  const days: DayBlock[] = []
  let cur: DayBlock | null = null
  const head: string[] = []

  for (const line of lines) {
    const m = line.trim().match(dayRe)
    if (m) {
      cur = { title: m[1], lines: [] }
      days.push(cur)
    } else if (cur) {
      cur.lines.push(line)
    } else {
      head.push(line)
    }
  }

  if (days.length === 0) return [{ title: '', lines }]
  // 首个「Day」标记前的文字（如标题/简介）并入第一天
  if (head.some((l) => l.trim())) days[0].lines = [...head, ...days[0].lines]
  return days
}

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

/* —— 骨架屏 —— */
.skeleton {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.sk {
  border-radius: var(--r-md);
  background: linear-gradient(90deg, #f1ebe3 25%, #faf6f0 37%, #f1ebe3 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
.sk-title {
  height: 30px;
  width: 42%;
}
.sk-chips {
  height: 20px;
  width: 62%;
}
.sk-day {
  height: 140px;
}
@keyframes shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: 0 0;
  }
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
.toolbar {
  display: flex;
  gap: 10px;
}
.btn-ic {
  margin-right: 4px;
  vertical-align: -2px;
}

/* —— 分天卡片 —— */
.days {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 4px;
}
.day-card {
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 18px 20px;
}
.day-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.day-badge {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: #fff;
  font-weight: 600;
  font-size: 13px;
  background: linear-gradient(135deg, var(--c-primary), #f2832f);
  flex: none;
}
.day-head h3 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 700;
}
.day-body p {
  margin: 0 0 6px;
  font-size: 14px;
  line-height: 1.85;
  color: var(--c-ink-2);
  white-space: pre-wrap;
  word-break: break-word;
}
.day-body p:last-child {
  margin-bottom: 0;
}
.day-line.time {
  color: var(--c-ink);
  font-weight: 600;
  margin-top: 6px;
}
</style>
