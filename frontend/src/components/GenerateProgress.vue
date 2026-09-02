<template>
  <div class="progress">
    <div class="steps">
      <template v-for="(s, i) in STAGES" :key="s.key">
        <div class="step" :class="store.stages[s.key]">
          <span class="dot">
            <Icon v-if="store.stages[s.key] === 'done'" name="check" :size="14" />
            <span v-else-if="store.stages[s.key] === 'running'" class="spin"></span>
          </span>
          <span class="label">{{ s.label }}</span>
        </div>
        <span
          v-if="i < STAGES.length - 1"
          class="line"
          :class="{ on: store.stages[s.key] === 'done' }"
        ></span>
      </template>
    </div>
    <p class="hint">{{ hint }}</p>

    <!-- 实时爬取到的小红书笔记（逐个淡入） -->
    <TransitionGroup v-if="store.xhsNotes.length" name="xhs" tag="div" class="xhs-live">
      <a
        v-for="n in store.xhsNotes"
        :key="n.url"
        class="xhs-live-item"
        :href="n.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        <img v-if="n.cover" class="xhs-live-cover" :src="n.cover" alt="" loading="lazy" />
        <span class="xhs-live-title">{{ n.title }}</span>
        <Icon name="arrow" :size="14" class="xhs-live-arrow" />
      </a>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import Icon from '@/components/Icon.vue'
import { STAGES, useTripStore } from '@/store/trip'
import type { StageKey } from '@/types'

const store = useTripStore()

const RUNNING_TEXT: Record<StageKey, string> = {
  extract: '正在抽取你的旅行偏好…',
  research: '正在搜集目的地信息…',
  plan: '正在生成每日行程…',
}

const runningStage = computed(() => STAGES.find((s) => store.stages[s.key] === 'running'))
const hint = computed(() => {
  const stage = runningStage.value
  if (!stage) return ''
  // research 阶段且小红书在爬：显示已爬到几篇
  if (stage.key === 'research' && store.xhsNotes.length) {
    return `正在爬小红书 · 已爬到第 ${store.xhsNotes.length} 篇`
  }
  return RUNNING_TEXT[stage.key]
})
</script>

<style scoped>
.progress {
  padding: 40px 8px;
}
.steps {
  display: flex;
  align-items: center;
}
.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  flex: none;
}
.dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  background: var(--c-surface-2);
  border: 2px solid var(--c-border-strong);
  transition: background 0.25s ease, border-color 0.25s ease;
}
.step.done .dot {
  background: var(--c-teal);
  border-color: var(--c-teal);
}
.step.running .dot {
  background: var(--c-surface);
  border-color: var(--c-primary);
}
.spin {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid var(--c-primary-soft);
  border-top-color: var(--c-primary);
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.label {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-muted);
  white-space: nowrap;
  transition: color 0.25s ease;
}
.step.done .label {
  color: var(--c-teal);
}
.step.running .label {
  color: var(--c-primary);
}
.line {
  flex: 1;
  height: 2px;
  margin: 0 12px 22px;
  border-radius: 2px;
  background: var(--c-border);
  transition: background 0.25s ease;
}
.line.on {
  background: var(--c-teal);
}
.hint {
  margin: 24px 0 0;
  text-align: center;
  font-size: 13.5px;
  color: var(--c-muted);
}

/* —— 实时爬取卡片 —— */
.xhs-live {
  margin-top: 20px;
  display: grid;
  gap: 8px;
}
.xhs-live-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-surface-2);
  text-decoration: none;
  color: inherit;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.xhs-live-item:hover {
  border-color: var(--c-primary);
  box-shadow: var(--shadow-sm);
}
.xhs-live-cover {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  object-fit: cover;
  flex: none;
  background: var(--c-surface);
}
.xhs-live-title {
  flex: 1;
  min-width: 0;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--c-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.xhs-live-arrow {
  flex: none;
  color: var(--c-muted);
}

/* 逐个进入动画 */
.xhs-enter-active {
  transition: all 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}
.xhs-enter-from {
  opacity: 0;
  transform: translateY(14px) scale(0.96);
}
</style>
