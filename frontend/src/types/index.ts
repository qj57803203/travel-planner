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

export interface ResearchInfo {
  destination: string
  hotels: Hotel[]
  attractions: Attraction[]
  food: Food[]
  transport: Transport[]
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
