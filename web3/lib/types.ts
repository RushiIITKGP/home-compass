// Mirrors api/main.py's SSE event shapes and api/agent.py's
// synthesis_node output — see architecture sheets A-01, A-02.

export type ChatRole = "user" | "agent";

export interface Listing {
  id: string;
  address: string;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  price: number | null;
  beds: number | null;
  baths: number | null;
  sqft: number | null;
  status: string | null;
  source: string;
}

export interface Demographics {
  median_household_income: number | null;
  median_age: number | null;
  fetched_at: string | null;
  source: string;
  error?: string;
}

export interface SafetyStats {
  year: number;
  violent_crime_count: number | null;
  property_crime_count: number | null;
  fetched_at: string | null;
  source: string;
  note: string;
  error?: string;
}

export interface MarketStatEntry {
  source: string;
  period_start: string | null;
  period_end: string | null;
  median_sale_price: number | null;
  inventory_count: number | null;
  median_days_on_market: number | null;
  note: string;
}

export interface MarketTrends {
  redfin?: MarketStatEntry;
  realtor_com?: MarketStatEntry;
  error?: string;
}

export interface Enrichment {
  demographics?: Demographics;
  safety?: SafetyStats;
  market?: MarketTrends;
  amenities?: unknown;
}

export interface Recommendation {
  listing: Listing;
  /** How well the listing matches the user's stated criteria (0-1);
   * null when the user hasn't stated any scoreable criteria. */
  fit_score?: number | null;
  fit_components?: {
    budget: number | null;
    location: number | null;
    beds: number | null;
    baths: number | null;
  };
  /** How much verified data backs the listing — still computed, no
   * longer displayed on cards. */
  recommendation_confidence: number;
  enrichment: Enrichment;
}

/** Per-answer confidence from agent.py's score node — how good THIS
 * response is to THIS question, with its component breakdown. */
export interface AnswerConfidence {
  score: number;
  threshold: number;
  flagged: boolean;
  components: {
    intent_match: number | null;
    grounding: number | null;
    data_coverage: number | null;
    criteria_match: number | null;
    compliance: number | null;
  };
  redistributed: string[];
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  confidenceScore?: number;
  recommendations?: Recommendation[];
  statusLog?: string[];
  answerConfidence?: AnswerConfidence | null;
}

// --- Raw SSE event shapes from POST /chat ---

export interface ThreadIdEvent {
  thread_id: string;
}

export interface StatusEvent {
  status: string;
}

export interface TokenEvent {
  token: string;
}

/** Full-text replacement of the agent bubble — sent when the compliance
 * guardrail revised the answer after its draft tokens already streamed. */
export interface ReplaceEvent {
  replace: string;
}

export interface DoneEvent {
  done: true;
  confidence_score: number;
  missing_slot: string | null;
  recommendations: Recommendation[];
  answer_confidence?: AnswerConfidence | null;
}

export type ChatStreamEvent = ThreadIdEvent | StatusEvent | TokenEvent | ReplaceEvent | DoneEvent;
