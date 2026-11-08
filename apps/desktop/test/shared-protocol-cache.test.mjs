import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { stageWeb } from '../src/runtime.mjs';

test('source runtime keeps the Web shared protocol import resolvable', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'deeptutor-protocol-'));
  try {
    const source = path.join(root, 'source');
    const cache = path.join(root, 'cache');
    await mkdir(path.join(source, 'web', 'node_modules'), { recursive: true });
    await mkdir(path.join(source, 'deeptutor'), { recursive: true });
    const shared = path.join('packages', 'shared-protocol', 'src');
    await mkdir(path.join(source, shared), { recursive: true });
    await writeFile(path.join(source, 'deeptutor', '__version__.py'), '__version__ = "test"');
    await writeFile(path.join(source, shared, 'index.ts'), 'export type GameItem = string;');
    await stageWeb(source, cache);
    assert.equal(await readFile(path.join(cache, shared, 'index.ts'), 'utf8'), 'export type GameItem = string;');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
