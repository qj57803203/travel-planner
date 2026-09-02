<template>
  <div class="research">
    <!-- 酒店 -->
    <section class="section">
      <header class="section-head">
        <span class="section-ic" style="background: var(--c-primary-soft); color: var(--c-primary)">
          <Icon name="bed" :size="16" />
        </span>
        <h4>酒店候选</h4>
        <span class="section-count">{{ research.hotels.length }}</span>
      </header>
      <el-empty v-if="!research.hotels.length" description="暂无数据" :image-size="44" />
      <div v-else class="list">
        <article v-for="h in research.hotels" :key="h.name" class="item">
          <div class="item-top">
            <h5>{{ h.name }}</h5>
            <span class="price">{{ h.price }}</span>
          </div>
          <div class="item-meta">
            <Icon name="pin" :size="13" />{{ h.location }}
            <span v-if="h.rating" class="rating">★ {{ h.rating }}</span>
          </div>
          <div class="tags">
            <span v-for="p in h.pros" :key="'p' + p" class="tag tag-good">✓ {{ p }}</span>
            <span v-for="c in h.cons" :key="'c' + c" class="tag tag-bad">✕ {{ c }}</span>
          </div>
        </article>
      </div>
    </section>

    <!-- 景点 -->
    <section class="section">
      <header class="section-head">
        <span class="section-ic" style="background: var(--c-teal-soft); color: var(--c-teal)">
          <Icon name="pin" :size="16" />
        </span>
        <h4>攻略要点 · 景点</h4>
        <span class="section-count">{{ research.attractions.length }}</span>
      </header>
      <el-empty v-if="!research.attractions.length" description="暂无数据" :image-size="44" />
      <div v-else class="list">
        <article v-for="a in research.attractions" :key="a.name" class="item">
          <div class="item-top">
            <h5>{{ a.name }}</h5>
            <span class="chip-area">{{ a.area }}</span>
          </div>
          <p class="note">{{ a.note }}</p>
          <p v-if="a.tips" class="tips"><Icon name="sun" :size="13" />{{ a.tips }}</p>
        </article>
      </div>
    </section>

    <!-- 美食 -->
    <section class="section">
      <header class="section-head">
        <span class="section-ic" style="background: var(--c-primary-soft); color: var(--c-primary)">
          <Icon name="utensils" :size="16" />
        </span>
        <h4>美食</h4>
        <span class="section-count">{{ research.food.length }}</span>
      </header>
      <el-empty v-if="!research.food.length" description="暂无数据" :image-size="44" />
      <div v-else class="list">
        <article v-for="f in research.food" :key="f.name" class="item">
          <div class="item-top">
            <h5>{{ f.name }}</h5>
            <span class="chip-area teal">{{ f.category }}</span>
          </div>
          <p v-if="f.note" class="note">{{ f.note }}</p>
        </article>
      </div>
    </section>

    <!-- 交通 -->
    <section class="section">
      <header class="section-head">
        <span class="section-ic" style="background: var(--c-teal-soft); color: var(--c-teal)">
          <Icon name="train" :size="16" />
        </span>
        <h4>交通</h4>
        <span class="section-count">{{ research.transport.length }}</span>
      </header>
      <el-empty v-if="!research.transport.length" description="暂无数据" :image-size="44" />
      <div v-else class="list">
        <article v-for="t in research.transport" :key="t.mode" class="item">
          <div class="item-top"><h5>{{ t.mode }}</h5></div>
          <p class="note">{{ t.detail }}</p>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/Icon.vue'
import type { ResearchInfo } from '@/types'

defineProps<{ research: ResearchInfo }>()
</script>

<style scoped>
.research {
  display: flex;
  flex-direction: column;
  gap: 24px;
  margin-top: 4px;
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
</style>
