import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as api from '@/api/trips'
import type { StageKey, StageStatus, Trip, TripSummary, XhsNote } from '@/types'

// 流程步骤（与后端节点顺序一致），label 用于进度条展示
export const STAGES: { key: StageKey; label: string }[] = [
  { key: 'extract', label: '抽取偏好' },
  { key: 'research', label: '搜集信息' },
  { key: 'plan', label: '生成行程' },
  { key: 'transport', label: '规划交通' },
]

export const useTripStore = defineStore('trip', () => {
  const current = ref<Trip | null>(null)
  const history = ref<TripSummary[]>([])
  const loading = ref(false)
  const error = ref('')
  const stages = ref<Record<StageKey, StageStatus>>({
    extract: 'pending',
    research: 'pending',
    plan: 'pending',
    transport: 'pending',
  })
  // 实时爬取到的小红书笔记（生成过程中逐个追加，带动画展示）
  const xhsNotes = ref<XhsNote[]>([])

  function resetStages() {
    stages.value = { extract: 'pending', research: 'pending', plan: 'pending', transport: 'pending' }
    xhsNotes.value = []
  }

  async function generate(input: string) {
    loading.value = true
    error.value = ''
    resetStages()
    stages.value.extract = 'running' // 提交即进入第一步
    try {
      current.value = await api.generateTripStream(input, (e) => {
        if (e.type === 'stage' && e.stage) {
          stages.value[e.stage] = 'done'
          // 线性流程：把下一步标记为进行中
          const next = STAGES.findIndex((s) => s.key === e.stage) + 1
          if (STAGES[next]) stages.value[STAGES[next].key] = 'running'
        } else if (e.type === 'xhs_note') {
          xhsNotes.value.push({
            title: e.title || '',
            url: e.url || '',
            summary: e.summary || '',
            cover: e.cover || '',
          })
        } else if (e.type === 'error') {
          error.value = e.message || '生成失败'
        }
      })
      await loadHistory()
    } catch (e: unknown) {
      // 已由 error 事件写入时不再覆盖
      if (!error.value) {
        const err = e as { message?: string }
        error.value = err?.message || '生成失败，请检查后端服务是否启动'
      }
    } finally {
      loading.value = false
    }
  }

  async function loadHistory() {
    try {
      history.value = await api.listTrips()
    } catch {
      // 历史加载失败不阻塞主流程
    }
  }

  async function openTrip(id: number) {
    loading.value = true
    error.value = ''
    try {
      current.value = await api.getTrip(id)
    } catch (e: unknown) {
      const err = e as { message?: string }
      error.value = err?.message || '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function saveDeparture(departure: string) {
    const d = departure.trim()
    if (!d) return
    try {
      await api.saveProfile(d)
      if (current.value) current.value.preferences.departure = d
    } catch {
      // 保存失败不阻塞，用户可重试
    }
  }

  return { current, history, loading, error, stages, xhsNotes, generate, loadHistory, openTrip, saveDeparture }
})
