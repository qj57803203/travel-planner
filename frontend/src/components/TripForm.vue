<template>
  <div class="form-card">
    <div class="form-row">
      <div class="input-col">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          class="textarea"
          placeholder="描述你的旅行想法，例如：9 月去东京玩 5 天，喜欢美食和拍照，不想太累"
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
      </div>
      <div class="action-col">
        <div class="departure-field">
          <label class="departure-label">
            <Icon name="pin" :size="13" /> 出发地
          </label>
          <el-input
            v-model="departure"
            size="default"
            placeholder="如：上海"
            class="departure-input"
            clearable
          />
        </div>
        <el-button
          class="generate-btn"
          type="primary"
          :loading="store.loading"
          @click="onGenerate"
        >
          <Icon v-if="!store.loading" name="sparkles" :size="16" />
          <span>{{ store.loading ? "正在规划…" : "生成行程" }}</span>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";

import Icon from "@/components/Icon.vue";
import * as api from "@/api/trips";
import { useTripStore } from "@/store/trip";

const store = useTripStore();
const input = ref("");
const departure = ref("");

const presets = [
  {
    label: "东京 · 美食拍照",
    text: "9 月去东京玩 5 天，喜欢美食和拍照，不想太累，酒店想靠近地铁",
  },
  {
    label: "大阪 · 亲子轻松",
    text: "带娃去大阪玩 3 天，节奏轻松一点，想去环球影城，住市中心",
  },
  {
    label: "巴黎 · 艺术浪漫",
    text: "11 月去巴黎玩 4 天，喜欢博物馆和艺术，慢节奏，想吃法餐",
  },
];

async function onGenerate() {
  if (!input.value.trim()) return;
  // 把出发地拼入 user_input（如果有值）
  let text = input.value.trim();
  if (departure.value.trim()) {
    text = `从${departure.value.trim()}出发，${text}`;
  }
  store.generate(text);
}

onMounted(async () => {
  // 加载用户默认出发地
  try {
    const profile = await api.getProfile();
    if (profile.departure) departure.value = profile.departure;
  } catch {
    // 静默失败
  }
});
</script>

<style scoped>
.form-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  box-shadow: var(--shadow-sm);
  padding: 18px 20px;
}

.form-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.input-col {
  flex: 1;
  min-width: 0;
}

.textarea :deep(.el-textarea__inner) {
  background: #f5f7fa;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.7;
  padding: 10px 14px;
  box-shadow: none;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}
.textarea :deep(.el-textarea__inner:focus) {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.preset {
  appearance: none;
  border: 1px solid #e2e8f0;
  background: #f5f7fa;
  color: #475569;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    color 0.15s ease,
    background 0.15s ease;
}
.preset:hover {
  border-color: #2563eb;
  color: #2563eb;
  background: #dbeafe;
}

.action-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 160px;
  justify-content: center;
}

.departure-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.departure-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 4px;
}
.departure-input {
  width: 100%;
}

.generate-btn {
  width: 100%;
  height: 42px;
  border: none;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%);
  box-shadow: 0 6px 16px -6px rgba(37, 99, 235, 0.5);
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease,
    filter 0.15s ease;
}
.generate-btn:hover {
  filter: brightness(1.05);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px -6px rgba(37, 99, 235, 0.55);
}
.generate-btn:active {
  transform: translateY(0);
}
.generate-btn :deep(.el-icon) {
  margin-right: 5px;
}

@media (max-width: 640px) {
  .form-row {
    flex-direction: column;
  }
  .action-col {
    flex-direction: row;
    align-items: flex-end;
    min-width: 0;
  }
  .departure-field {
    flex: 1;
  }
  .generate-btn {
    width: auto;
    min-width: 120px;
  }
}
</style>
