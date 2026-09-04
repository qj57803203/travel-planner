<template>
  <div class="hotel-card" @click="openHotel">
    <div class="hotel-image">
      <img v-if="hotel.image" :src="hotel.image" :alt="hotel.name" loading="lazy" />
      <div v-else class="image-placeholder">
        <el-icon><Picture /></el-icon>
      </div>
    </div>
    <div class="hotel-info">
      <div class="hotel-name">{{ hotel.name }}</div>
      <div class="hotel-meta">
        <span v-if="hotel.rating" class="rating">
          <el-icon><Star /></el-icon>
          {{ hotel.rating.toFixed(1) }}
        </span>
        <span v-if="hotel.location" class="location">
          <el-icon><Location /></el-icon>
          {{ hotel.location }}
        </span>
      </div>
      <div class="hotel-price">
        <span v-if="hotel.price" class="price">
          <span class="currency">¥</span>
          <span class="amount">{{ hotel.price.toFixed(0) }}</span>
          <span class="unit">/晚</span>
        </span>
        <span v-else class="price-unavailable">价格待询</span>
      </div>
    </div>
    <div class="hotel-action">
      <el-button type="primary" size="small" @click.stop="openHotel">
        查看详情
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Picture, Star, Location } from '@element-plus/icons-vue'
import type { Hotel } from '@/types'

const props = defineProps<{
  hotel: Hotel
}>()

const openHotel = () => {
  if (props.hotel.url) {
    window.open(props.hotel.url, '_blank')
  }
}
</script>

<style scoped>
.hotel-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: all 0.2s ease;
  backdrop-filter: blur(10px);
}

.hotel-card:hover {
  background: #fff;
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
  transform: translateY(-2px);
}

.hotel-image {
  flex-shrink: 0;
  width: 120px;
  height: 90px;
  border-radius: 8px;
  overflow: hidden;
}

.hotel-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  color: #c0c4cc;
  font-size: 32px;
}

.hotel-info {
  flex: 1;
  min-width: 0;
}

.hotel-name {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hotel-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
}

.hotel-meta .rating {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #f7ba2a;
  font-weight: 600;
}

.hotel-meta .location {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hotel-price {
  font-size: 14px;
}

.price {
  color: #f56c6c;
  font-weight: 600;
}

.price .currency {
  font-size: 13px;
}

.price .amount {
  font-size: 20px;
}

.price .unit {
  font-size: 12px;
  color: #909399;
  margin-left: 2px;
}

.price-unavailable {
  color: #909399;
  font-size: 13px;
}

.hotel-action {
  flex-shrink: 0;
}

@media (max-width: 600px) {
  .hotel-card {
    flex-wrap: wrap;
  }

  .hotel-image {
    width: 100%;
    height: 160px;
  }

  .hotel-action {
    width: 100%;
  }

  .hotel-action .el-button {
    width: 100%;
  }
}
</style>
