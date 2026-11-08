import assert from "node:assert/strict";
import test from "node:test";
import { mayInitiateBlePair, ProximityWindow } from "../src/features/nfc-social/proximityPolicy.ts";

test("requires sustained proximity and resets after a weak sample", () => {
  const signal = new ProximityWindow();
  assert.equal(signal.add(-35, 0), false);
  assert.equal(signal.add(-36, 399), false);
  assert.equal(signal.add(-42, 400), false);
  assert.equal(signal.add(-35, 500), false);
  assert.equal(signal.add(-35, 900), true);
});

test("both peers deterministically agree on one BLE pairing initiator", () => {
  const low = "a".repeat(32);
  const high = "b".repeat(32);
  assert.equal(mayInitiateBlePair(low, high), true);
  assert.equal(mayInitiateBlePair(high, low), false);
  assert.equal(mayInitiateBlePair(low, low), false);
  assert.equal(mayInitiateBlePair(low, "invalid"), false);
});
