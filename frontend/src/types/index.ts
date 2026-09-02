export interface Preference {
  destination: string
  days: number
  pace: string
  interests: string[]
  hotel_preference: string[]
}

export interface Hotel {
  name: string
  price: string
  rating: string
  location: string
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
}

export interface ResearchInfo {
  destination: string
  hotels: Hotel[]
  attractions: Attraction[]
  food: Food[]
  transport: Transport[]
  xhs_notes: XhsNote[]
}

export interface Trip {
  id: number
  user_input: string
  preferences: Preference
  research: ResearchInfo
  itinerary: string
  created_at: string
}

export interface TripSummary {
  id: number
  destination: string
  days: number
  created_at: string
}

export type StageKey = 'extract' | 'research' | 'plan'
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
