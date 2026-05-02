import test from "node:test";
import assert from "node:assert/strict";

import {
  AUDIO_SETTINGS_STORAGE_KEY,
  DEFAULT_BGM_VOLUME,
  applyStoredBgmVolume,
  getStoredBgmVolume,
  loadAudioSettings,
  normalizeBgmVolume,
  saveAudioSettings,
} from "./audio_settings.js";

function createMemoryStorage(seed = {}) {
  const values = new Map(Object.entries(seed));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

test("normalizeBgmVolume clamps values into the valid range", () => {
  assert.equal(normalizeBgmVolume(0.5), 0.5);
  assert.equal(normalizeBgmVolume(-1), 0);
  assert.equal(normalizeBgmVolume(10), 1);
  assert.equal(normalizeBgmVolume("abc"), DEFAULT_BGM_VOLUME);
});

test("loadAudioSettings falls back to the default BGM volume", () => {
  assert.deepEqual(loadAudioSettings(createMemoryStorage()), { bgmVolume: DEFAULT_BGM_VOLUME });
});

test("saveAudioSettings persists normalized BGM volume", () => {
  const storage = createMemoryStorage();
  const saved = saveAudioSettings({ bgmVolume: 0.35 }, storage);
  assert.deepEqual(saved, { bgmVolume: 0.35 });
  assert.deepEqual(JSON.parse(storage.getItem(AUDIO_SETTINGS_STORAGE_KEY)), { bgmVolume: 0.35 });
});

test("getStoredBgmVolume and applyStoredBgmVolume read the saved volume", () => {
  const storage = createMemoryStorage({
    [AUDIO_SETTINGS_STORAGE_KEY]: JSON.stringify({ bgmVolume: 0.42 }),
  });
  const audioElement = { volume: 1 };

  assert.equal(getStoredBgmVolume(storage), 0.42);
  assert.equal(applyStoredBgmVolume(audioElement, storage), 0.42);
  assert.equal(audioElement.volume, 0.42);
});
