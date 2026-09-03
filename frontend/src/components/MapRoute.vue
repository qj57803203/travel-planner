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
  () => props.transit?.source === 'amap' && legs.value.length > 0,
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

// 每天的颜色（最多支持 10 天，循环使用）
const DAY_COLORS = [
  '#2563eb', // 蓝
  '#dc2626', // 红
  '#16a34a', // 绿
  '#ea580c', // 橙
  '#7c3aed', // 紫
  '#0891b2', // 青
  '#ca8a04', // 黄
  '#db2777', // 粉
  '#4f46e5', // 靛
  '#059669', // 翡翠
]

// 按天分组的 legs（带 day 编号和颜色）
interface DayLegs {
  day: number
  color: string
  legs: TransitLeg[]
}

const dayLegsGrouped = computed<DayLegs[]>(() => {
  const days = props.transit?.days ?? []
  return days.map((d, i) => ({
    day: d.day ?? i + 1,
    color: DAY_COLORS[i % DAY_COLORS.length],
    legs: d.legs ?? [],
  }))
})

// 按天收集站点坐标，附带当天路线颜色
function collectMarkers(): { name: string; lng: number; lat: number; color: string }[] {
  const seen = new Map<string, { name: string; lng: number; lat: number; color: string }>()
  for (const group of dayLegsGrouped.value) {
    for (const leg of group.legs) {
      for (const p of [leg.from, leg.to]) {
        if (!p || typeof p.lng !== 'number' || typeof p.lat !== 'number') {
          console.error('[MapRoute] ❌ 站点坐标无效:', p, '所属 leg:', leg.from?.name, '→', leg.to?.name)
          continue
        }
        const key = `${p.lng},${p.lat}`
        if (!seen.has(key)) {
          seen.set(key, { ...p, color: group.color })
        }
      }
    }
  }
  return [...seen.values()]
}

// 取某天所有 legs 的 polyline 中间点坐标
function getDayMidPosition(dayLegs: TransitLeg[]): { lng: number; lat: number } | null {
  // 收集所有 polyline 点
  const allPoints: [number, number][] = []
  for (const leg of dayLegs) {
    if (leg.polyline?.length) {
      allPoints.push(...leg.polyline)
    }
  }
  if (allPoints.length === 0) {
    // 没有 polyline，退回到第一个 leg 的 from/to 中点
    const first = dayLegs[0]
    if (!first) {
      console.warn('[MapRoute] ⚠️ getDayMidPosition: 无 legs')
      return null
    }
    if (typeof first.from?.lng !== 'number' || typeof first.to?.lng !== 'number') {
      console.error('[MapRoute] ❌ getDayMidPosition: leg 坐标无效', first.from, first.to)
      return null
    }
    return { lng: (first.from.lng + first.to.lng) / 2, lat: (first.from.lat + first.to.lat) / 2 }
  }
  // 取 polyline 总长度的中间那个点
  const midIdx = Math.floor(allPoints.length / 2)
  const pt = allPoints[midIdx]
  if (!pt || pt.length < 2 || typeof pt[0] !== 'number' || typeof pt[1] !== 'number') {
    console.error('[MapRoute] ❌ getDayMidPosition: polyline 中间点异常', pt, 'midIdx:', midIdx, 'total:', allPoints.length)
    return null
  }
  return { lng: pt[0], lat: pt[1] }
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
  // ── 数据诊断日志 ──
  console.group('[MapRoute] render()')
  console.log('transit:', JSON.parse(JSON.stringify(props.transit ?? null)))
  console.log('hasData:', hasData.value)
  console.log('days 数量:', props.transit?.days?.length ?? 0)
  console.log('dayLegsGrouped:', dayLegsGrouped.value.map(g => ({ day: g.day, legs: g.legs.length, color: g.color })))
  console.log('legs(扁平):', legs.value.length)

  if (!hasData.value) {
    // 诊断：为什么没数据
    if (!props.transit) {
      console.warn('[MapRoute] ❌ transit 为 undefined/null')
    } else if (props.transit.source !== 'amap') {
      console.warn('[MapRoute] ❌ transit.source 不是 amap，而是:', props.transit.source)
    } else {
      console.warn('[MapRoute] ❌ hasData=false，inter_city:', !!props.transit.inter_city, 'legs:', legs.value.length)
    }
    console.groupEnd()
    return
  }
  loadError.value = false
  await nextTick()
  if (!mapEl.value) {
    console.error('[MapRoute] ❌ mapEl 为 null，DOM 未就绪')
    console.groupEnd()
    return
  }

  try {
    const AMap = await loadAMap()
    if (map) {
      map.destroy()
      map = null
    }
    map = new AMap.Map(mapEl.value, { zoom: 12 })

    // 景点标记：实心圆点（颜色跟路线一致）+ 名称文字
    const markers = collectMarkers()
    console.log('[MapRoute] markers:', markers.length, markers)
    if (markers.length === 0) {
      console.warn('[MapRoute] ⚠️ 无站点坐标，地图上不会有任何标记')
    }
    for (const m of markers) {
      if (!m.lng || !m.lat) {
        console.error('[MapRoute] ❌ 站点坐标异常:', m)
        continue
      }
      const marker = new AMap.Marker({
        position: [m.lng, m.lat],
        anchor: 'center',
        zIndex: 100,
        content: `<div class="amap-marker-wrap"><div class="amap-dot" style="background:${m.color}"></div><span class="amap-spot-label">${esc(m.name)}</span></div>`,
      })
      map.add(marker)
    }

    // 按天绘制路线（只画景区之间，不画城际）
    let totalPolylines = 0
    for (const group of dayLegsGrouped.value) {
      let dayPolylines = 0
      for (const leg of group.legs) {
        // 诊断：每条 leg 的关键字段
        if (!leg.from?.lng || !leg.from?.lat) {
          console.error(`[MapRoute] ❌ Day${group.day} leg.from 坐标缺失:`, leg.from)
        }
        if (!leg.to?.lng || !leg.to?.lat) {
          console.error(`[MapRoute] ❌ Day${group.day} leg.to 坐标缺失:`, leg.to)
        }
        if (!leg.polyline || !Array.isArray(leg.polyline)) {
          console.error(`[MapRoute] ❌ Day${group.day} ${leg.from?.name}→${leg.to?.name} polyline 不是数组:`, typeof leg.polyline)
        } else if (leg.polyline.length === 0) {
          console.warn(`[MapRoute] ⚠️ Day${group.day} ${leg.from?.name}→${leg.to?.name} polyline 为空数组`)
        } else {
          // 检查首尾点是否合法
          const first = leg.polyline[0]
          const last = leg.polyline[leg.polyline.length - 1]
          if (!Array.isArray(first) || first.length < 2) {
            console.error(`[MapRoute] ❌ Day${group.day} polyline 点格式异常:`, first)
          } else {
            console.log(`[MapRoute] Day${group.day} ${leg.from?.name}→${leg.to?.name}: ${leg.polyline.length} 点, 首[${first}] 末[${last}]`)
          }
          map.add(
            new AMap.Polyline({
              path: leg.polyline,
              strokeColor: group.color,
              strokeWeight: 5,
              strokeOpacity: 0.8,
              lineJoin: 'round',
            }),
          )
          dayPolylines++
          totalPolylines++
        }
      }
      console.log(`[MapRoute] Day ${group.day}: ${group.legs.length} legs, 画了 ${dayPolylines} 条线, color: ${group.color}`)

      // 在当天路线的中间位置标记 "Day N"
      const midPos = getDayMidPosition(group.legs)
      if (midPos) {
        const dayMarker = new AMap.Marker({
          position: [midPos.lng, midPos.lat],
          anchor: 'center',
          zIndex: 120,
        })
        dayMarker.setContent(
          `<div class="amap-day-tag" style="background:${group.color}">Day ${group.day}</div>`,
        )
        map.add(dayMarker)
      }
    }

    if (totalPolylines === 0) {
      console.error('[MapRoute] ❌ 没有任何 polyline 被画出！路线不会显示')
    } else {
      console.log(`[MapRoute] ✅ 共画 ${totalPolylines} 条路线`)
    }

    map.setFitView(null, false, [60, 60, 60, 60])
    console.groupEnd()
  } catch (e) {
    console.error('[MapRoute] ❌ 高德地图加载/渲染失败', e)
    loadError.value = true
    console.groupEnd()
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
/* marker 容器：文字在圆点下方 */
.amap-marker-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* 实心圆点（颜色由 inline style 控制） */
.amap-dot {
  width: 10px;
  height: 10px;
  border: 2px solid #fff;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
  flex-shrink: 0;
}

/* 站点名：普通文字，无背景无边框 */
.amap-spot-label {
  margin-top: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #1e293b;
  white-space: nowrap;
  text-shadow: 0 0 3px #fff, 0 0 3px #fff, 0 0 3px #fff;
  line-height: 1;
}

/* Day N 标记气泡 */
.amap-day-tag {
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  padding: 3px 10px;
  border-radius: 12px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  white-space: nowrap;
  letter-spacing: 0.5px;
}
</style>
