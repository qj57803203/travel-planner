<template>
  <div class="research">
    <!-- 数据来源状态提示 -->
    <div v-if="research.xhs_status === 'fallback'" class="notice notice-fallback">
      <Icon name="book" :size="16" />
      <div class="notice-body">
        <strong>本次使用兜底数据</strong>
        <p v-if="research.xhs_error">{{ research.xhs_error }}</p>
        <p v-else>小红书未抓到笔记，以下为预置示例素材。</p>
      </div>
    </div>
    <div v-else-if="research.xhs_status === 'cached'" class="notice notice-cached">
      <Icon name="clock" :size="16" />
      <div class="notice-body">
        <strong>笔记来自一周内缓存</strong>
        <p>近期爬过该目的地，直接复用。</p>
      </div>
    </div>


    <!-- 小红书攻略 -->
    <section class="section">
      <header class="section-head">
        <span class="section-ic" style="background: var(--c-primary-soft); color: var(--c-primary)">
          <Icon name="book" :size="16" />
        </span>
        <h4>小红书攻略</h4>
        <span class="section-count">{{ research.xhs_notes.length }}</span>
      </header>
      <el-empty v-if="!research.xhs_notes.length" description="暂无小红书笔记" :image-size="44" />
      <div v-else class="list">
        <a
          v-for="n in research.xhs_notes"
          :key="n.url"
          class="item xhs-card"
          :href="n.url"
          target="_blank"
          rel="noopener noreferrer"
        >
          <img v-if="n.cover" class="xhs-cover" :src="n.cover" alt="" loading="lazy" />
          <div class="xhs-body">
            <h5 class="xhs-title">{{ n.title }}</h5>
            <div class="xhs-summary" v-html="renderMarkdown(n.summary)"></div>
          </div>
          <Icon name="arrow" :size="15" class="xhs-arrow" />
        </a>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/Icon.vue'
import type { ResearchInfo } from '@/types'
import { renderMarkdown } from '@/utils/markdown'

defineProps<{ research: ResearchInfo }>()
</script>

<style scoped>
.research {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: 4px;
}
.notice {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--r-lg);
  font-size: 13px;
  line-height: 1.6;
}
.notice :deep(svg) {
  flex: none;
  margin-top: 2px;
}
.notice-fallback {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.35);
  color: #b45309;
}
.notice-cached {
  background: var(--c-teal-soft);
  border: 1px solid var(--c-border);
  color: var(--c-teal);
}
.notice-body {
  min-width: 0;
}
.notice-body strong {
  display: block;
  margin-bottom: 2px;
  font-weight: 700;
}
.notice-body p {
  margin: 0;
  opacity: 0.9;
  word-break: break-all;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.section-ic {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex: none;
}
.section-head h4 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 15px;
  font-weight: 700;
  flex: 1;
}
.section-count {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--c-muted);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
}

.list {
  display: grid;
  gap: 12px;
}
.item {
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: 14px 16px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}
.item:hover {
  border-color: var(--c-border-strong);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.item-top h5 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--c-ink);
}
.price {
  font-weight: 700;
  color: var(--c-primary-hover);
  font-size: 14px;
  white-space: nowrap;
}
.item-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--c-muted);
  font-size: 12.5px;
  margin-top: 5px;
}
.rating {
  margin-left: 8px;
  color: #f59e0b;
  font-weight: 600;
}
.note {
  margin: 6px 0 0;
  font-size: 13.5px;
  color: var(--c-ink-2);
  line-height: 1.7;
}
.tips {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 12.5px;
  color: var(--c-teal);
  line-height: 1.6;
}
.tips :deep(svg) {
  flex: none;
  margin-top: 2px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.tag {
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 999px;
}
.tag-good {
  color: var(--c-success);
  background: rgba(47, 133, 90, 0.08);
}
.tag-bad {
  color: var(--c-muted);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
}
.chip-area {
  font-size: 11.5px;
  color: var(--c-primary-hover);
  background: var(--c-primary-soft);
  padding: 3px 9px;
  border-radius: 999px;
  white-space: nowrap;
}
.chip-area.teal {
  color: var(--c-teal);
  background: var(--c-teal-soft);
}
.xhs-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  text-decoration: none;
  color: inherit;
}
.xhs-card:hover {
  border-color: var(--c-primary);
}
.xhs-cover {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  object-fit: cover;
  flex: none;
  background: var(--c-surface);
}
.xhs-body {
  flex: 1;
  min-width: 0;
}
.xhs-title {
  margin: 0 0 4px;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--c-ink);
}
.xhs-card:hover .xhs-title {
  color: var(--c-primary-hover);
}
.xhs-summary {
  font-size: 13px;
  line-height: 1.6;
  color: var(--c-muted);
  max-height: 4.8em;
  overflow: hidden;
}
.xhs-summary :deep(p) {
  margin: 0;
}
.xhs-arrow {
  flex: none;
  color: var(--c-muted);
  margin-top: 6px;
  transition: transform 0.18s ease, color 0.18s ease;
}
.xhs-card:hover .xhs-arrow {
  transform: translateX(2px);
  color: var(--c-primary-hover);
}
</style>
