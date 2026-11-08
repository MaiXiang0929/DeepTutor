export type Subject = "math" | "physics" | "literature" | "history" | "coding";
export type ItemCategory = "card_fragment" | "companion_skin" | "room_decor" | "badge";
export type Rarity = "common" | "rare" | "epic" | "legendary";
export type EmotionState = "idle" | "happy" | "proud" | "empathetic" | "thinking" | "excited";
export type QuickEmoteId = "thumbs_up" | "please" | "thank_you" | "wow";

export interface GameItem {
  item_id: string;
  name: string;
  category: ItemCategory;
  subject_tag: Subject;
  rarity: Rarity;
  quantity: number;
}

export interface InventoryItem extends GameItem {
  id: number;
  is_equipped: boolean;
  acquired_at: string;
  acquired_source: "desktop_study" | "minigame" | "nfc_trade" | "synthesis";
}

export interface GamificationReward {
  energy_points: number;
  item: GameItem;
}

export type CompanionPersona = "cyber_navigator" | "pixel_alchemist" | "oriental_spirit";

export interface CompanionIdentity {
  name: string;
  persona_id: CompanionPersona;
}

export interface UserGameProfile {
  user_id: string;
  companion?: (CompanionIdentity & {partner_id: string}) | null;
  energy_points: number;
  lucky_subject: Subject;
  daily_game_minutes_remaining: number;
  daily_game_minutes_used: number;
  daily_trade_count: number;
  inventory: InventoryItem[];
}

export type StreamEventType =
  | "stage_start" | "stage_end" | "thinking" | "observation" | "content"
  | "tool_call" | "tool_result" | "progress" | "sources" | "result" | "error"
  | "session" | "session_meta" | "done" | "wait_for_input";

export interface StreamEvent {
  type: StreamEventType;
  source?: string;
  stage?: string;
  content?: string;
  metadata?: Record<string, unknown> & { gamification_reward?: GamificationReward };
  timestamp: number;
  turn_id?: string;
  session_id?: string;
  seq?: number;
  protocol_version?: "2.0";
}

export interface CompanionGreeting {
  text: string;
  emotion_state: EmotionState;
  audio_url: string;
  reward_bubble: (GamificationReward & { already_granted: boolean }) | null;
}

export interface TradeSessionState {
  session_id: string;
  status: "pending_pair" | "active" | "locked" | "completed" | "cancelled" | "expired";
  side: "initiator" | "responder";
  initiator_items_json: Record<string, number>;
  responder_items_json: Record<string, number>;
  initiator_locked: boolean;
  responder_locked: boolean;
  initiator_confirmed: boolean;
  responder_confirmed: boolean;
  expires_at: number;
  revision: number;
  version: number;
  synthesis_unlocks: string[];
  peer_companion?: CompanionIdentity | null;
  quick_emote: { side: "initiator" | "responder"; emote_id: QuickEmoteId; seq: number } | null;
}

export type TradeCommand =
  | { type: "trade:update_offer"; items: Record<string, number> }
  | { type: "trade:lock" | "trade:confirm"; revision: number }
  | { type: "trade:cancel" }
  | { type: "trade:quick_emote"; emote_id: QuickEmoteId };

export function websocketUrl(base: string, path: string): string {
  const url = new URL(path, base);
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error("Expected an HTTP(S) server URL");
  }
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export async function requestJson<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(new URL(path, base), { credentials: "include", ...init });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}
