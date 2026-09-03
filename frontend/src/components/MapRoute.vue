<template>
  <div class="map-wrap">
    <!-- 交通方式提示 -->
    <div v-if="transit?.transport_mode" class="transport-info">
      <span class="transport-mode">{{ transportModeText }}</span>
      <span v-if="transit?.transport_reason" class="transport-reason">{{ transit.transport_reason }}</span>
    </div>
    <div v-if="!hasData" class="map-empty">
      <Icon name="map" :size="36" />
      <p>{{ emptyText }}</p>
    </div>
    <div v-else-if="loadError" class="map-empty">
      <Icon name="map" :size="36" />
      <p>地图加载失败，请检查高德 key / 安全密钥是否正确配置</p>
    </div>
    <div v-show="hasData && !loadError" ref="mapEl" class="map-canvas"></div>
  </div>
</template>

<script setup lang="ts">
import AMapLoader from '@amap/amap-jsapi-loader'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import Icon from '@/components/Icon.vue'
import type { TransitInfo, TransitLeg } from '@/types'

const props = withDefaults(defineProps<{
  transit?: TransitInfo
  active?: boolean
}>(), { active: true })

const mapEl = ref<HTMLDivElement | null>(null)
const loadError = ref(false)
let map: any = null
let amapPromise: Promise<any> | null = null

const legs = computed<TransitLeg[]>(() => props.transit?.days?.flatMap((d) => d.legs ?? []) ?? [])
const hasData = computed(
  () => props.transit?.source === 'amap' && (legs.value.length > 0 || !!props.transit?.inter_city),
)

const emptyText = computed(() => {
  if (!props.transit || props.transit.source !== 'amap') {
    return '暂无交通路线。未配置高德 key，或本次行程未提取到景点序列。'
  }
  return '暂无路线数据'
})

const transportModeText = computed(() => {
  const mode = props.transit?.transport_mode
  const modeMap: Record<string, string> = {
    driving: '🚗 驾车',
    train: '🚄 高铁/火车',
    flight: '✈️ 飞机',
  }
  return modeMap[mode || ''] || '🚗 驾车'
})

// 从 legs 里收集去重的站点坐标，作为地图 marker
function collectMarkers(): { name: string; lng: number; lat: number }[] {
  const seen = new Set<string>()
  const out: { name: string; lng: number; lat: number }[] = []
  for (const leg of legs.value) {
    for (const p of [leg.from, leg.to]) {
      const key = `${p.lng},${p.lat}`
      if (!seen.has(key)) {
        seen.add(key)
        out.push(p)
      }
    }
  }
  return out
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

async function loadAMap(): Promise<any> {
  if (!amapPromise) {
    ;(window as any)._AMapSecurityConfig = {
      securityJsCode: import.meta.env.VITE_AMAP_SECURITY_CODE || '',
    }
    amapPromise = AMapLoader.load({
      key: import.meta.env.VITE_AMAP_JS_KEY || '',
      version: '2.0',
    })
  }
  return amapPromise
}

async function render() {
  if (!hasData.value) return
  loadError.value = false
  await nextTick()
  if (!mapEl.value) return

  try {
    const AMap = await loadAMap()
    if (map) {
      map.destroy()
      map = null
    }
    map = new AMap.Map(mapEl.value, { zoom: 12 })

    const markers = collectMarkers()
    console.log('[MapRoute] markers:', markers.length, markers)
    for (const m of markers) {
      const marker = new AMap.Marker({
        position: [m.lng, m.lat],
        title: m.name,
        anchor: 'bottom-center',
      })
      marker.setLabel({
        content: `<span class="amap-spot-label">${esc(m.name)}</span>`,
        direction: 'top',
      })
      map.add(marker)
    }

    console.log('[MapRoute] legs:', legs.value.length, legs.value)
    for (const leg of legs.value) {
      console.log('[MapRoute] leg polyline:', leg.from.name, '->', leg.to.name, 'points:', leg.polyline?.length)
      if (leg.polyline?.length) {
        map.add(
          new AMap.Polyline({
            path: leg.polyline,
            strokeColor: '#2563eb',
            strokeWeight: 5,
            strokeOpacity: 0.75,
            lineJoin: 'round',
          }),
        )
      }
    }

    map.setFitView(null, false, [60, 60, 60, 60])
  } catch (e) {
    console.error('高德地图加载失败', e)
    loadError.value = true
  }
}

watch(() => props.transit, () => render())

onMounted(render)
onBeforeUnmount(() => {
  if (map) {
    map.destroy()
    map = null
  }
})
</script>

<style scoped>
.map-wrap {
  position: relative;
  width: 100%;
  min-height: 500px;
  overflow: hidden;
}
.map-canvas {
  width: 100%;
  height: 500px;
}
.map-empty {
  min-height: 500px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #94a3b8;
  background: #f5f7fa;
}
.map-empty p {
  margin: 0;
  font-size: 13.5px;
  max-width: 280px;
  text-align: center;
}
.transport-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: #dbeafe;
  border-bottom: 1px solid #e2e8f0;
  font-size: 14px;
}
.transport-mode {
  font-weight: 600;
  color: #1d4ed8;
}
.transport-reason {
  color: #475569;
  font-size: 13px;
}
</style>

<style>
/* marker 上的站点名标签（AMap 生成到地图容器内，需全局样式） */
.amap-spot-label {
  font-size: 12px;
  color: #1f2937;
  background: rgba(255, 255, 255, 0.92);
  padding: 2px 8px;
  border-radius: 999px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
}
</style>
