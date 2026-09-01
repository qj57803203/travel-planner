<template>
  <el-collapse v-model="active">
    <el-collapse-item title="🏨 酒店候选" name="hotels">
      <el-empty v-if="!research.hotels.length" description="暂无数据" :image-size="50" />
      <div v-for="h in research.hotels" :key="h.name" class="item">
        <div class="row">
          <b>{{ h.name }}</b>
          <span class="dim">{{ h.price }}</span>
          <el-rate :model-value="Number(h.rating)" disabled size="small" />
        </div>
        <div class="dim">{{ h.location }}</div>
        <div class="line">👍 {{ h.pros.join('、') }}</div>
        <div class="line">👎 {{ h.cons.join('、') }}</div>
      </div>
    </el-collapse-item>

    <el-collapse-item title="📍 攻略要点 / 景点" name="attractions">
      <el-empty v-if="!research.attractions.length" description="暂无数据" :image-size="50" />
      <div v-for="a in research.attractions" :key="a.name" class="item">
        <div class="row">
          <b>{{ a.name }}</b>
          <el-tag size="small" type="info">{{ a.area }}</el-tag>
        </div>
        <div class="line">{{ a.note }}</div>
        <div v-if="a.tips" class="line dim">💡 {{ a.tips }}</div>
      </div>
    </el-collapse-item>

    <el-collapse-item title="🍜 美食" name="food">
      <el-empty v-if="!research.food.length" description="暂无数据" :image-size="50" />
      <div v-for="f in research.food" :key="f.name" class="item">
        <div class="row">
          <b>{{ f.name }}</b>
          <el-tag size="small" type="success">{{ f.category }}</el-tag>
        </div>
        <div v-if="f.note" class="line dim">{{ f.note }}</div>
      </div>
    </el-collapse-item>

    <el-collapse-item title="🚇 交通" name="transport">
      <el-empty v-if="!research.transport.length" description="暂无数据" :image-size="50" />
      <div v-for="t in research.transport" :key="t.mode" class="item">
        <div class="row">
          <b>{{ t.mode }}</b>
        </div>
        <div class="line dim">{{ t.detail }}</div>
      </div>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import type { ResearchInfo } from '@/types'

defineProps<{ research: ResearchInfo }>()

const active = ref(['hotels', 'attractions', 'food', 'transport'])
</script>

<style scoped>
.item {
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.line {
  margin-top: 4px;
  font-size: 13px;
}
.dim {
  color: #999;
}
</style>
