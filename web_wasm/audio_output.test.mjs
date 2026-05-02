import test from "node:test";
import assert from "node:assert/strict";

import {
  applyStoredBgmVolume,
  ensureManagedAudioGraph,
  playManagedBgm,
  resetManagedAudioStateForTests,
  resumeManagedAudioContext,
} from "./audio_output.js";
import { AUDIO_SETTINGS_STORAGE_KEY } from "./audio_settings.js";

function createStorage(bgmVolume) {
  return {
    getItem(key) {
      if (key !== AUDIO_SETTINGS_STORAGE_KEY) return null;
      return JSON.stringify({ bgmVolume });
    },
  };
}

test("applyStoredBgmVolume falls back to HTML media volume when Web Audio is unavailable", () => {
  resetManagedAudioStateForTests();
  const audioElement = { volume: 1 };
  const storage = createStorage(0.4);

  assert.equal(applyStoredBgmVolume(audioElement, storage, {}), 0.4);
  assert.equal(audioElement.volume, 0.4);
});

test("ensureManagedAudioGraph creates a reusable gain graph for an audio element", () => {
  resetManagedAudioStateForTests();
  const createdSources = [];
  const createdGains = [];
  class MockAudioContext {
    constructor() {
      this.destination = { key: "destination" };
      this.state = "running";
    }

    createMediaElementSource(audioElement) {
      const sourceNode = {
        audioElement,
        connect(target) {
          sourceNode.connectedTarget = target;
        },
      };
      createdSources.push(sourceNode);
      return sourceNode;
    }

    createGain() {
      const gainNode = {
        gain: { value: 1 },
        connect(target) {
          gainNode.connectedTarget = target;
        },
      };
      createdGains.push(gainNode);
      return gainNode;
    }
  }

  const runtime = { AudioContext: MockAudioContext };
  const audioElement = { volume: 1 };
  const first = ensureManagedAudioGraph(audioElement, runtime);
  const second = ensureManagedAudioGraph(audioElement, runtime);

  assert.equal(first, second);
  assert.equal(createdSources.length, 1);
  assert.equal(createdGains.length, 1);
  assert.equal(first.sourceNode.connectedTarget, first.gainNode);
  assert.equal(first.gainNode.connectedTarget, first.context.destination);
});

test("applyStoredBgmVolume uses GainNode volume when Web Audio is available", () => {
  resetManagedAudioStateForTests();
  class MockAudioContext {
    constructor() {
      this.destination = {};
      this.state = "running";
    }

    createMediaElementSource() {
      return { connect() {} };
    }

    createGain() {
      return {
        gain: { value: 1 },
        connect() {},
      };
    }
  }

  const runtime = { AudioContext: MockAudioContext };
  const audioElement = { volume: 0.2 };
  const storage = createStorage(0.55);

  assert.equal(applyStoredBgmVolume(audioElement, storage, runtime), 0.55);
  const graph = ensureManagedAudioGraph(audioElement, runtime);
  assert.equal(graph.gainNode.gain.value, 0.55);
  assert.equal(audioElement.volume, 1);
});

test("resumeManagedAudioContext resumes a suspended audio context", async () => {
  resetManagedAudioStateForTests();
  class MockAudioContext {
    constructor() {
      this.destination = {};
      this.state = "suspended";
    }

    createMediaElementSource() {
      return { connect() {} };
    }

    createGain() {
      return {
        gain: { value: 1 },
        connect() {},
      };
    }

    resume() {
      this.state = "running";
      return Promise.resolve();
    }
  }

  const runtime = { AudioContext: MockAudioContext };
  const audioElement = { volume: 1 };
  const resumedContext = await resumeManagedAudioContext(audioElement, runtime);

  assert.equal(resumedContext?.state, "running");
});

test("playManagedBgm resumes first when the context starts suspended", async () => {
  resetManagedAudioStateForTests();
  const callOrder = [];
  class MockAudioContext {
    constructor() {
      this.destination = {};
      this.state = "suspended";
    }

    createMediaElementSource() {
      return { connect() {} };
    }

    createGain() {
      return {
        gain: { value: 1 },
        connect() {},
      };
    }

    resume() {
      callOrder.push("resume");
      this.state = "running";
      return Promise.resolve();
    }
  }

  const runtime = { AudioContext: MockAudioContext };
  const audioElement = {
    volume: 1,
    play() {
      callOrder.push("play");
      return Promise.resolve("played");
    },
  };

  const result = await playManagedBgm(audioElement, { runtime, storage: createStorage(0.7) });
  assert.equal(result, "played");
  assert.deepEqual(callOrder, ["resume", "play"]);
});
