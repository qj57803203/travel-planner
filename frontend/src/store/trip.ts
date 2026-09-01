import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as api from '@/api/trips'
import type { Trip, TripSummary } from '@/types'

export const useTripStore = defineStore('trip', () => {
  const current = ref<Trip | null>(null)
  const history = ref<TripSummary[]>([])
  const loading = ref(false)
  const error = ref('')

  async function generate(input: string) {
    loading.value = true
    error.value = ''
    try {
      current.value = await api.generateTrip(input)
      await loadHistory()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string }
      error.value = err?.response?.data?.detail || err?.message || '生成失败，请检查后端服务是否启动'
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

  return { current, history, loading, error, generate, loadHistory, openTrip }
})
