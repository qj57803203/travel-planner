<template>
  <div class="app">
    <header class="topbar">
      <div class="topbar-inner">
        <div class="brand">
          <span class="brand-mark"><Icon name="compass" :size="22" /></span>
          <div class="brand-text">
            <h1>旅行规划</h1>
            <p>把一句话，变成一份可执行的行程</p>
          </div>
        </div>
        <span class="model-pill">
          <span class="model-dot"></span>
          DeepSeek · deepseek-v4-flash
        </span>
      </div>
    </header>

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

      <aside class="sidebar">
        <TripForm />
      </aside>

      <section class="content">
        <ItineraryView />
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/Icon.vue'
import ItineraryView from '@/components/ItineraryView.vue'
import TripForm from '@/components/TripForm.vue'
import { useTripStore } from '@/store/trip'

const store = useTripStore()
</script>

<style scoped>
.app {
  min-height: 100vh;
  background:
    radial-gradient(1100px 520px at 100% -10%, rgba(217, 72, 15, 0.08), transparent 60%),
    radial-gradient(900px 480px at -10% 24%, rgba(15, 118, 110, 0.06), transparent 55%),
    var(--c-bg);
}

/* —— 顶栏 —— */
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--c-border);
}
.topbar-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 14px 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-mark {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, var(--c-primary), #f2832f);
  box-shadow: var(--shadow-md);
}
.brand-text h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 0.5px;
  line-height: 1.2;
}
.brand-text p {
  margin: 2px 0 0;
  font-size: 12.5px;
  color: var(--c-muted);
}
.model-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--c-ink-2);
  padding: 6px 12px;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-surface);
  white-space: nowrap;
}
.model-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-teal);
  box-shadow: 0 0 0 3px var(--c-teal-soft);
}

/* —— 主体布局 —— */
.layout {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 28px 56px;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}
.alert {
  grid-column: 1 / -1;
}
.sidebar {
  position: sticky;
  top: 84px;
}
.content {
  min-width: 0;
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

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
    padding: 16px 16px 40px;
  }
  .sidebar {
    position: static;
  }
  .topbar-inner {
    padding: 12px 16px;
  }
}
</style>
