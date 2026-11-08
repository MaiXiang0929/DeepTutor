import type { GamificationReward, UserGameProfile } from "../../../packages/shared-protocol/src";
import { notify } from "@/lib/notifications";
import { apiFetch, apiUrl } from "@/shared/api/client";

const delivered = new Set<string>();
export const PROFILE_CHANGED = "deeptutor:gamification-reward";

export async function loadGameProfile(signal: AbortSignal): Promise<UserGameProfile | null> {
  const response = await apiFetch(apiUrl("/api/v1/gamification/profile"), {
    signal,
    skipAuthRedirect: true,
    cache: "no-store",
  });
  return response.ok ? response.json() as Promise<UserGameProfile> : null;
}

export function presentReward(value: unknown, id: string | undefined): void {
  if (typeof window === "undefined" || !value || typeof value !== "object") return;
  const reward = value as Partial<GamificationReward>;
  if (!Number.isFinite(reward.energy_points) || typeof reward.item?.name !== "string") return;
  if (id) {
    if (delivered.has(id)) return;
    delivered.add(id);
    if (delivered.size > 256) delivered.delete(delivered.values().next().value!);
  }
  notify(`⚡ +${reward.energy_points} · ${reward.item.name} ×${reward.item.quantity}`, {
    tone: "success",
  });
  window.dispatchEvent(new Event(PROFILE_CHANGED));
}
