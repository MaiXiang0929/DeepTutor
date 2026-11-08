import assert from "node:assert/strict";
import test from "node:test";
import { TutorClient } from "../src/client.ts";

test("rejects a Metro manifest as a server address", async (t) => {
  const manifest = { runtimeVersion: "exposdk:54.0.0", launchAsset: {} };
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify(manifest)));
  const client = new TutorClient("http://192.168.31.102:8081");

  await assert.rejects(async () => client.isAuthenticated(), /DeepTutor 后端地址/);
});

test("accepts a DeepTutor session when authentication is disabled", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    Response.json({ enabled: false, authenticated: true }),
  );
  const client = new TutorClient("http://192.168.31.102:8001");

  assert.equal(await client.isAuthenticated(), true);
});
