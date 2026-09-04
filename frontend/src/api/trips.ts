import axios from 'axios'

import type { StreamEvent, Trip, TripSummary } from '@/types'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000, // 生成涉及多次 LLM 调用，放宽超时
})

// 流式生成：用原生 fetch 逐段读取 SSE，实时拿到每一步进度
// tripId 不为空时为修改模式，在上一轮行程基础上修改
export async function generateTripStream(
  userInput: string,
  onEvent: (e: StreamEvent) => void,
  tripId?: number,
): Promise<Trip> {
  const body: Record<string, unknown> = { user_input: userInput }
  if (tripId) body.trip_id = tripId
  const resp = await fetch('/api/generate/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok || !resp.body) {
    throw new Error('生成失败，请检查后端服务是否启动')
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let trip: Trip | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      const e = JSON.parse(line.slice(5).trim()) as StreamEvent
      if (e.type === 'done') trip = e.trip ?? null
      else onEvent(e)
    }
  }

  if (!trip) throw new Error('生成失败，请检查后端服务是否启动')
  return trip
}

export async function listTrips(): Promise<TripSummary[]> {
  const { data } = await http.get<TripSummary[]>('/trips')
  return data
}

export async function getTrip(id: number): Promise<Trip> {
  const { data } = await http.get<Trip>(`/trips/${id}`)
  return data
}

export async function getProfile(): Promise<{ departure: string }> {
  const { data } = await http.get<{ departure: string }>('/profile')
  return data
}

export async function saveProfile(departure: string): Promise<{ departure: string }> {
  const { data } = await http.post<{ departure: string }>('/profile', { departure })
  return data
}
