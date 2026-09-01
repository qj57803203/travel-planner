import axios from 'axios'

import type { Trip, TripSummary } from '@/types'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000, // 生成涉及多次 LLM 调用，放宽超时
})

export async function generateTrip(userInput: string): Promise<Trip> {
  const { data } = await http.post<Trip>('/generate', { user_input: userInput })
  return data
}

export async function listTrips(): Promise<TripSummary[]> {
  const { data } = await http.get<TripSummary[]>('/trips')
  return data
}

export async function getTrip(id: number): Promise<Trip> {
  const { data } = await http.get<Trip>(`/trips/${id}`)
  return data
}
