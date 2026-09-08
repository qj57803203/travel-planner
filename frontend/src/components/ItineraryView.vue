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
        <div class="result-title-row">
          <h2>{{ store.current.preferences.destination + "行程详情" }}</h2>
          <div class="chips">
            <span class="chip chip-days">
              <Icon name="calendar" :size="11" />{{
                store.current.preferences.days
              }}
              天
            </span>
            <span v-if="store.current.preferences.pace" class="chip chip-pace">
              <Icon name="clock" :size="11" />{{
                store.current.preferences.pace
              }}
            </span>
            <span
              v-for="i in store.current.preferences.interests"
              :key="i"
              class="chip"
            >
              {{ i }}
            </span>
            <!-- <span
              v-if="store.current.research.xhs_status === 'live'"
              class="chip chip-live"
            >
              <Icon name="book" :size="11" />小红书实时
            </span>
            <span
              v-else-if="store.current.research.xhs_status === 'cached'"
              class="chip chip-cached"
            >
              <Icon name="clock" :size="11" />缓存数据
            </span> -->
            <span v-if="tokenText" class="chip chip-token">{{
              tokenText
            }}</span>
          </div>
        </div>

        <div class="toolbar">
          <el-button circle @click="onRegenerate" title="重新生成">
            <Icon name="refresh" :size="15" />
          </el-button>
          <el-button circle type="primary" @click="onCopy" title="复制">
            <Icon name="copy" :size="15" />
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
        <el-button size="small" type="primary" @click="onSaveDeparture"
          >记住</el-button
        >
      </div>

      <!-- 交通规划失败提示 -->
      <div v-if="store.current.transit_error" class="transit-error">
        <span class="transit-error-ic">⚠️</span>
        <span>地图路线无法显示：{{ store.current.transit_error }}</span>
      </div>

      <!-- 推荐酒店 -->
      <div
        v-if="store.current.hotels && store.current.hotels.length > 0"
        class="hotels-section"
      >
        <h3 class="hotels-title">🏨 推荐酒店</h3>
        <div class="hotels-list">
          <HotelCard
            v-for="hotel in store.current.hotels"
            :key="hotel.name"
            :hotel="hotel"
          />
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

        <el-tab-pane label="小红书素材" name="research">
          <ResearchPanel
            v-if="store.current"
            :research="store.current.research"
          />
        </el-tab-pane>
      </el-tabs>

      <!-- ── 多轮对话区 ── -->
      <div class="chat-section">
        <!-- 对话历史：用户消息气泡 -->
        <div v-if="userMessages.length" class="chat-history">
          <div
            v-for="(msg, i) in userMessages"
            :key="i"
            class="chat-bubble-row"
          >
            <div class="chat-bubble user-bubble">{{ msg }}</div>
          </div>
        </div>

        <!-- 加载中提示 -->
        <div v-if="store.loading" class="chat-loading">
          <span class="chat-loading-dot"></span>
          正在调整行程…
        </div>

        <!-- 推荐提问 -->
        <div v-if="!store.loading && canModify" class="suggestions">
          <span class="suggestions-label">💡 继续提问</span>
          <div class="suggestions-list">
            <button
              v-for="q in suggestedQuestions"
              :key="q"
              class="suggestion-chip"
              type="button"
              @click="onSuggestionClick(q)"
            >
              {{ q }}
            </button>
          </div>
        </div>

        <!-- 输入框 -->
        <div v-if="canModify" class="chat-input-row">
          <el-input
            v-model="modifyInput"
            size="small"
            :placeholder="
              store.loading
                ? '正在生成中…'
                : '输入修改意见，如：行程太紧了、不想住这么远'
            "
            :disabled="store.loading"
            class="chat-input"
            @keyup.enter="onModify"
          >
            <template #suffix>
              <Icon
                name="send"
                :size="16"
                class="send-icon"
                :class="{ disabled: !modifyInput.trim() || store.loading }"
                @click="onModify"
              />
            </template>
          </el-input>
        </div>

        <!-- 轮数耗尽提示 -->
        <div v-if="roundExhausted" class="chat-exhausted">
          已达最大修改次数（5轮），请
          <el-button link type="primary" @click="onRegenerate"
            >重新生成</el-button
          >
          新行程
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";

import GenerateProgress from "@/components/GenerateProgress.vue";
import HotelCard from "@/components/HotelCard.vue";
import Icon from "@/components/Icon.vue";
import ResearchPanel from "@/components/ResearchPanel.vue";
import { useTripStore } from "@/store/trip";
import { renderMarkdown } from "@/utils/markdown";

const MAX_ROUNDS = 5;

const store = useTripStore();
const tab = ref("itinerary");
const departureInput = ref("");
const modifyInput = ref("");

const itineraryHtml = computed(() =>
  renderMarkdown(store.current?.itinerary ?? ""),
);

// 对话历史中用户发的消息（用于气泡展示）
const userMessages = computed(() => {
  const history = store.current?.chat_history ?? [];
  return history.filter((m) => m.role === "user").map((m) => m.content);
});

// 是否还能修改（轮数未耗尽 且 有当前行程）
const canModify = computed(() => {
  return !!store.current && store.chatRound < MAX_ROUNDS;
});

// 轮数是否已耗尽
const roundExhausted = computed(() => {
  return !!store.current && store.chatRound >= MAX_ROUNDS;
});

// 根据行程内容动态生成推荐提问
const suggestedQuestions = computed(() => {
  const dest = store.current?.preferences?.destination || "";
  const pace = store.current?.preferences?.pace || "适中";
  const itinerary = store.current?.itinerary || "";
  const interests = store.current?.preferences?.interests ?? [];

  const questions: string[] = [];

  // 节奏相关
  if (pace !== "轻松") questions.push("行程太紧了，节奏放轻松一点");
  // 景点相关：从 itinerary 提取第一个 Day 里的景点名
  const spotMatch = itinerary.match(
    /[-•]\s*\*?\*?([^*\n]{2,10})\*?\*?\s*[（(]/,
  );
  if (spotMatch) questions.push(`不想去${spotMatch[1].trim()}，换个地方`);
  // 兴趣相关
  if (!interests.includes("美食")) questions.push("多安排一些当地美食");
  // 通用
  if (dest) questions.push(`给${dest}加一天行程`);
  questions.push("住宿推荐换一个区域");

  return questions.slice(0, 4);
});

// 调试：监听 transit 数据变化
watch(
  () => store.current?.transit,
  (transit) => {
    console.log("[ItineraryView] transit data:", transit);
    console.log("[ItineraryView] transit source:", transit?.source);
    console.log("[ItineraryView] transit days:", transit?.days?.length);
    console.log("[ItineraryView] transit inter_city:", transit?.inter_city);
  },
  { immediate: true },
);

const tokenText = computed(() => {
  const u = store.current?.usage;
  if (!u) return "";
  const sum = (t?: { input?: number; output?: number }) =>
    t ? (t.input || 0) + (t.output || 0) : 0;
  const parts: string[] = [];
  // if (u.extract) parts.push(`抽取 ${sum(u.extract)}`);
  if (u.plan) parts.push(`生成 ${sum(u.plan)}`);
  return parts.length ? `${parts.join(" · ")} tokens` : "";
});

function onRegenerate() {
  if (store.current) store.generate(store.current.user_input);
}

async function onModify() {
  const text = modifyInput.value.trim();
  if (!text || store.loading) return;
  modifyInput.value = "";
  await store.modify(text);
  // 修改完成后滚到顶部看新行程
  const resultEl = document.querySelector(".result");
  if (resultEl) resultEl.scrollTop = 0;
}

function onSuggestionClick(question: string) {
  modifyInput.value = question;
  onModify();
}

async function onCopy() {
  if (!store.current) return;
  try {
    await navigator.clipboard.writeText(store.current.itinerary);
    ElMessage.success("已复制到剪贴板");
  } catch {
    ElMessage.warning("复制失败，请手动选择文本");
  }
}

async function onSaveDeparture() {
  if (!departureInput.value.trim()) return;
  await store.saveDeparture(departureInput.value);
  ElMessage.success("出发地已记住，下次自动补全城际交通");
  departureInput.value = "";
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
.result-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.result-title-row h2 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: #1e293b;
  white-space: nowrap;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: #475569;
  padding: 2px 7px;
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
  gap: 6px;
  flex-shrink: 0;
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

/* —— 交通规划失败提示 —— */
.transit-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid #fde68a;
  border-radius: 12px;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
}
.transit-error-ic {
  color: #f59e0b;
  flex: none;
}

/* —— 推荐酒店 —— */
.hotels-section {
  margin-bottom: 14px;
  padding: 10px 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 10px;
  color: #fff;
}

.hotels-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.hotels-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
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

/* —— 多轮对话区（吸底） —— */
.chat-section {
  position: sticky;
  bottom: 0;
  margin-top: 20px;
  padding: 16px 0 12px;
  background: #fff;
  border-top: 1px solid #e2e8f0;
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.06);
  /* 抵消父容器 padding，让横线和背景撑满 */
  margin-left: -20px;
  margin-right: -20px;
  padding-left: 20px;
  padding-right: 20px;
  /* 底部圆角 */
  border-radius: 0 0 18px 18px;
}

.chat-history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.chat-bubble-row {
  display: flex;
  justify-content: flex-end;
}
.chat-bubble {
  max-width: 80%;
  padding: 8px 14px;
  border-radius: 14px 14px 4px 14px;
  font-size: 13.5px;
  line-height: 1.6;
}
.user-bubble {
  background: #2563eb;
  color: #fff;
}

.chat-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 13px;
  color: #64748b;
}
.chat-loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2563eb;
  animation: pulse-dot 1s ease-in-out infinite;
}
@keyframes pulse-dot {
  0%,
  100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

/* 推荐提问 */
.suggestions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.suggestions-label {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
}
.suggestions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.suggestion-chip {
  appearance: none;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 999px;
  cursor: pointer;
  transition:
    border-color 0.15s,
    color 0.15s,
    background 0.15s;
}
.suggestion-chip:hover {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}

.chat-input-row {
  display: flex;
  gap: 10px;
  align-items: center;
  max-width: 100%;
}
.chat-input :deep(.el-input__wrapper) {
  border-radius: 20px;
  padding: 4px 16px;
  min-height: 40px;
  font-size: 14px;
}

/* 发送图标 */
.send-icon {
  cursor: pointer;
  color: #2563eb;
  transition:
    color 0.15s,
    opacity 0.15s;
}
.send-icon:hover {
  color: #1d4ed8;
}
.send-icon.disabled {
  color: #cbd5e1;
  pointer-events: none;
}

/* 轮数耗尽 */
.chat-exhausted {
  padding: 8px 0;
  font-size: 13px;
  color: #94a3b8;
}
</style>
