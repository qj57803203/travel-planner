<template>
  <div class="app">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="topbar-left">
          <button class="history-toggle" title="历史记录" @click="showHistory = !showHistory">
            <Icon name="book" :size="18" />
            <span v-if="store.history.length" class="history-badge">{{ store.history.length }}</span>
          </button>
          <div class="brand">
            <span class="brand-mark"><Icon name="compass" :size="20" /></span>
            <h1>旅行规划</h1>
          </div>
        </div>
        <span class="model-pill">
          <span class="model-dot"></span>
          DeepSeek · deepseek-v4-flash
        </span>
      </div>
    </header>

    <!-- 历史记录侧栏（抽屉式） -->
    <transition name="slide">
      <div v-if="showHistory" class="history-drawer">
        <div class="history-drawer-head">
          <span>历史记录</span>
          <button class="close-btn" @click="showHistory = false">
            <Icon name="arrow" :size="16" />
          </button>
        </div>
        <el-empty v-if="!store.history.length" description="还没有生成过行程" :image-size="48" />
        <ul v-else class="history-list">
          <li
            v-for="t in store.history"
            :key="t.id"
            class="history-item"
            :class="{ active: store.current?.id === t.id }"
            @click="store.openTrip(t.id); showHistory = false"
          >
            <span class="dot" :style="{ background: dotColor(t.destination) }"></span>
            <div class="history-meta">
              <span class="name">{{ t.destination || '未命名' }}</span>
              <span class="sub">{{ t.days }} 天 · {{ relative(t.created_at) }}</span>
            </div>
          </li>
        </ul>
      </div>
    </transition>
    <div v-if="showHistory" class="history-backdrop" @click="showHistory = false"></div>

    <main class="layout">
      <transition name="fade">
        <el-alert
          v-if="store.error"
          class="alert"
          :title="store.error"
          type="error"
          show-icon
          closable
          @close="store.error = ''"
        />
      </transition>

      <!-- 左侧：输入 + 对话/行程 -->
      <section class="main-panel">
        <TripForm />
        <ItineraryView />
      </section>

      <!-- 右侧：地图常驻 -->
      <aside class="map-panel">
        <MapRoute
          v-if="store.current"
          :transit="store.current.transit"
          :active="true"
        />
        <div v-else class="map-placeholder">
          <Icon name="map" :size="40" />
          <p>生成行程后，这里会显示地图路线</p>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import Icon from '@/components/Icon.vue'
import ItineraryView from '@/components/ItineraryView.vue'
import MapRoute from '@/components/MapRoute.vue'
import TripForm from '@/components/TripForm.vue'
import { useTripStore } from '@/store/trip'

const store = useTripStore()
const showHistory = ref(false)

const COLORS = ['#2563eb', '#0f766e', '#7c3aed', '#c026d3', '#0891b2', '#475569']

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

onMounted(() => store.loadHistory())
</script>

<style scoped>
.app {
  min-height: 100vh;
  background:
    radial-gradient(1100px 520px at 100% -10%, rgba(37, 99, 235, 0.06), transparent 60%),
    radial-gradient(900px 480px at -10% 24%, rgba(15, 118, 110, 0.04), transparent 55%),
    #f0f4f8;
}

/* —— 顶栏 —— */
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid #e2e8f0;
}
.topbar-inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.history-toggle {
  position: relative;
  appearance: none;
  border: 1px solid #e2e8f0;
  background: #fff;
  border-radius: 10px;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  cursor: pointer;
  color: #475569;
  transition: border-color 0.15s, color 0.15s, box-shadow 0.15s;
}
.history-toggle:hover {
  border-color: #2563eb;
  color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
.history-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: #2563eb;
  display: grid;
  place-items: center;
  line-height: 1;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  box-shadow: var(--shadow-md);
}
.brand h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #1e293b;
}
.model-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: #475569;
  padding: 5px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  white-space: nowrap;
}
.model-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #0f766e;
  box-shadow: 0 0 0 3px #e3f2f0;
}

/* —— 历史记录抽屉 —— */
.history-drawer {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: 300px;
  z-index: 100;
  background: #fff;
  box-shadow: 4px 0 24px rgba(30, 41, 59, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.history-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  border-bottom: 1px solid #e2e8f0;
}
.close-btn {
  appearance: none;
  border: none;
  background: none;
  cursor: pointer;
  color: #94a3b8;
  padding: 4px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  transition: color 0.15s, background 0.15s;
  transform: rotate(180deg);
}
.close-btn:hover {
  color: #475569;
  background: #f5f7fa;
}
.history-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;
  background: rgba(30, 41, 59, 0.2);
  backdrop-filter: blur(2px);
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow-y: auto;
  flex: 1;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.history-item:hover {
  background: #f5f7fa;
}
.history-item.active {
  background: #dbeafe;
  border-color: #2563eb;
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
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub {
  font-size: 11.5px;
  color: #94a3b8;
}

/* —— 主体布局 —— */
.layout {
  max-width: 1440px;
  margin: 0 auto;
  padding: 20px 20px 56px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 20px;
  align-items: start;
}
.alert {
  grid-column: 1 / -1;
}
.main-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.map-panel {
  position: sticky;
  top: 72px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.map-placeholder {
  height: 500px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #94a3b8;
  background: #f5f7fa;
}
.map-placeholder p {
  margin: 0;
  font-size: 13.5px;
}

/* —— 动画 —— */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.2s ease;
}
.slide-enter-from,
.slide-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 960px) {
  .layout {
    grid-template-columns: 1fr;
    padding: 16px 16px 40px;
  }
  .map-panel {
    position: static;
  }
  .topbar-inner {
    padding: 10px 16px;
  }
  .model-pill {
    display: none;
  }
}
</style>
