export interface Preference {
  destination: string
  days: number
  pace: string
  interests: string[]
  hotel_preference: string[]
  departure: string
}

export interface Hotel {
  name: string
  price: number
  rating: number
  location: string
  image: string
  url: string
  pros: string[]
  cons: string[]
}

export interface Attraction {
  name: string
  area: string
  note: string
  tips: string
}

export interface Food {
  name: string
  category: string
  note: string
}

export interface Transport {
  mode: string
  detail: string
}

export interface XhsNote {
  title: string
  url: string
  summary: string
  cover: string
  author?: string       // 小红书作者名（MCP 方案不一定返回）
  like_count?: string   // 点赞数（MCP 方案不一定返回）
}

export interface ResearchInfo {
  destination: string
  hotels: Hotel[]
  attractions: Attraction[]
  food: Food[]
  transport: Transport[]
  xhs_notes: XhsNote[]
  xhs_status: string
  xhs_error: string
}

export interface TokenUsage {
  input: number
  output: number
}

export interface TransitPoint {
  name: string
  lng: number
  lat: number
}

export interface TransitLeg {
  from: TransitPoint
  to: TransitPoint
  mode: string
  summary: string
  duration_min: number
  distance_m: number
  polyline: [number, number][]
}

export interface InterCity {
  from: string
  to: string
  mode: string
  summary: string
  duration_min: number
  distance_m: number
  polyline: [number, number][]
}

export interface TransitDay {
  day: number
  legs: TransitLeg[]
}

export interface TransitInfo {
  source: 'amap' | 'none'
  transport_mode?: string
  transport_reason?: string
  inter_city?: InterCity | null
  days: TransitDay[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Trip {
  id: number
  user_input: string
  preferences: Preference
  research: ResearchInfo
  itinerary: string
  created_at: string
  usage?: { extract?: TokenUsage; plan?: TokenUsage }
  transit?: TransitInfo
  transit_error?: string  // 交通规划失败原因（非空时展示提示）
  hotels?: Hotel[]
  chat_history?: ChatMessage[]
  parent_id?: number | null
}

export interface TripSummary {
  id: number
  destination: string
  days: number
  created_at: string
}

export type StageKey = 'extract' | 'research' | 'plan' | 'hotel_search' | 'transport'
export type StageStatus = 'pending' | 'running' | 'done'

export interface StreamEvent {
  type: 'stage' | 'xhs_note' | 'done' | 'error'
  stage?: StageKey
  message?: string
  index?: number
  title?: string
  url?: string
  summary?: string
  cover?: string
  trip?: Trip
}
