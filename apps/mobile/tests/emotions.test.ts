import assert from "node:assert/strict";
import test from "node:test";
import { decodePartnerReply, emotionInputs } from "../src/features/companion/emotions.ts";

test("all six server emotions map to distinct Rive inputs", () => {
  assert.equal(new Set(Object.values(emotionInputs)).size, 6);
  for (const emotion of Object.keys(emotionInputs)) {
    assert.equal(decodePartnerReply(JSON.stringify({text: "Hi", emotion_state: emotion})).emotion_state, emotion);
  }
});

test("invalid output falls back to idle and caps the spoken text", () => {
  assert.deepEqual(decodePartnerReply(JSON.stringify({text: "A".repeat(82), emotion_state: "other"})), {
    text: "A".repeat(80), emotion_state: "idle",
  });
});
