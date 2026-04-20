import test from "node:test";
import assert from "node:assert/strict";

import {
  readCachedImageUrl,
  resolveCachedImageUrl,
  resetImageCandidateCache,
} from "./image_cache.js";

class MockImage {
  static loadCounts = new Map();

  constructor() {
    this.listeners = { load: [], error: [] };
  }

  addEventListener(type, handler) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(handler);
  }

  set src(value) {
    this._src = value;
    MockImage.loadCounts.set(value, (MockImage.loadCounts.get(value) || 0) + 1);
    queueMicrotask(() => {
      const type = String(value).includes("ok") ? "load" : "error";
      (this.listeners[type] || []).forEach((handler) => handler());
    });
  }
}

test.beforeEach(() => {
  resetImageCandidateCache();
  MockImage.loadCounts = new Map();
  globalThis.Image = MockImage;
});

test.after(() => {
  delete globalThis.Image;
});

test("resolveCachedImageUrl caches the first successful candidate", async () => {
  const candidates = ["missing.png", "sprite-ok.png"];

  const first = await resolveCachedImageUrl(candidates);
  const second = await resolveCachedImageUrl(candidates);

  assert.equal(first, "sprite-ok.png");
  assert.equal(second, "sprite-ok.png");
  assert.equal(readCachedImageUrl(candidates), "sprite-ok.png");
  assert.equal(MockImage.loadCounts.get("missing.png"), 1);
  assert.equal(MockImage.loadCounts.get("sprite-ok.png"), 1);
});

test("resolveCachedImageUrl caches misses to avoid repeated retries", async () => {
  const candidates = ["missing-a.png", "missing-b.png"];

  const first = await resolveCachedImageUrl(candidates);
  const second = await resolveCachedImageUrl(candidates);

  assert.equal(first, "");
  assert.equal(second, "");
  assert.equal(readCachedImageUrl(candidates), "");
  assert.equal(MockImage.loadCounts.get("missing-a.png"), 1);
  assert.equal(MockImage.loadCounts.get("missing-b.png"), 1);
});
