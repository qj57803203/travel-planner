import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as api from '@/api/trips'
import type { StageKey, StageStatus, Trip, TripSummary, XhsNote } from '@/types'

// 流程步骤（与后端节点顺序一致），label 用于进度条展示
// 注意：修改模式下 research 会被跳过，由 generate/modify 中的逻辑自动标记为 done
export const STAGES: { key: StageKey; label: string }[] = [
  { key: 'extract', label: '理解需求' },
  { key: 'research', label: '搜集信息' },
  { key: 'plan', label: '生成行程' },
  { key: 'hotel_search', label: '搜索酒店' },
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
    hotel_search: 'pending',
    transport: 'pending',
  })
  // 实时爬取到的小红书笔记（生成过程中逐个追加，带动画展示）
  const xhsNotes = ref<XhsNote[]>([])

  // 当前对话轮数（chat_history 里 user 消息数），用于判断是否达到上限
  const chatRound = computed(() => {
    if (!current.value?.chat_history?.length) return 0
    return current.value.chat_history.filter((m) => m.role === 'user').length
  })

  function resetStages() {
    stages.value = { extract: 'pending', research: 'pending', plan: 'pending', hotel_search: 'pending', transport: 'pending' }
    xhsNotes.value = []
  }

  /** 标记某阶段完成，并自动补齐被跳过的中间阶段（修改模式下 research 会被跳过） */
  function markStageDone(stage: StageKey) {
    stages.value[stage] = 'done'
    // 自动补齐：如果该阶段之前的某个阶段还是 pending，标记为 done（说明被后端跳过了）
    const idx = STAGES.findIndex((s) => s.key === stage)
    for (let i = 0; i < idx; i++) {
      const prev = STAGES[i].key
      if (stages.value[prev] === 'pending') {
        stages.value[prev] = 'done'
      }
    }
    // 线性流程：把下一步标记为进行中
    const next = STAGES[idx + 1]
    if (next) stages.value[next.key] = 'running'
  }

  async function generate(input: string) {
    loading.value = true
    error.value = ''
    resetStages()
    stages.value.extract = 'running' // 提交即进入第一步
    try {
      current.value = await api.generateTripStream(input, (e) => {
        if (e.type === 'stage' && e.stage) {
          markStageDone(e.stage)
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

  async function modify(input: string) {
    if (!current.value) return
    loading.value = true
    error.value = ''
    resetStages()
    stages.value.extract = 'running'
    try {
      current.value = await api.generateTripStream(input, (e) => {
        if (e.type === 'stage' && e.stage) {
          markStageDone(e.stage)
        } else if (e.type === 'xhs_note') {
          // 修改模式通常跳过 research，但兼容处理
          xhsNotes.value.push({
            title: e.title || '',
            url: e.url || '',
            summary: e.summary || '',
            cover: e.cover || '',
          })
        } else if (e.type === 'error') {
          error.value = e.message || '修改失败'
        }
      }, current.value.id) // 传入 trip_id 触发修改模式
      await loadHistory()
    } catch (e: unknown) {
      if (!error.value) {
        const err = e as { message?: string }
        error.value = err?.message || '修改失败，请检查后端服务是否启动'
      }
    } finally {
      loading.value = false
    }
  }

  async function loadHistory() {
    try {
      history.value = await api.listTrips()
    } catch (e: unknown) {
      // 历史加载失败不阻塞主流程，但提示用户
      const err = e as { message?: string }
      error.value = err?.message || '加载历史记录失败'
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

  return { current, history, loading, error, stages, xhsNotes, chatRound, generate, modify, loadHistory, openTrip, saveDeparture }
})
