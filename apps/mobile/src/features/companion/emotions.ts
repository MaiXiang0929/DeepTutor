import type { EmotionState } from "@deeptutor/shared-protocol";

export const emotionInputs = {
  idle: 0, happy: 1, proud: 2, empathetic: 3, thinking: 4, excited: 5,
} satisfies Record<EmotionState, number>;

export function decodePartnerReply(raw: string): {text: string; emotion_state: EmotionState} {
  try {
    const value = JSON.parse(raw.trim().replace(/^```(?:json)?\s*|\s*```$/g, ""));
    if (typeof value.text === "string") {
      const emotion = value.emotion_state;
      return {
        text: value.text.trim().slice(0, 80),
        emotion_state: Object.hasOwn(emotionInputs, emotion) ? emotion : "idle",
      };
    }
  } catch {}
  return {text: raw.trim().slice(0, 80), emotion_state: "idle"};
}
