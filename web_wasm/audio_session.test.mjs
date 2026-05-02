import test from "node:test";
import assert from "node:assert/strict";

import { configureAmbientAudioSession } from "./audio_session.js";

test("configureAmbientAudioSession sets ambient when Audio Session API is available", () => {
  const mockNavigator = {
    audioSession: {
      type: "playback",
    },
  };

  assert.equal(configureAmbientAudioSession(mockNavigator), true);
  assert.equal(mockNavigator.audioSession.type, "ambient");
});

test("configureAmbientAudioSession is a no-op when Audio Session API is unavailable", () => {
  assert.equal(configureAmbientAudioSession({}), false);
  assert.equal(configureAmbientAudioSession(null), false);
});

test("configureAmbientAudioSession tolerates read-only or rejecting audio sessions", () => {
  const mockNavigator = {
    audioSession: Object.defineProperty({}, "type", {
      get() {
        return "playback";
      },
      set() {
        throw new Error("read only");
      },
    }),
  };

  assert.equal(configureAmbientAudioSession(mockNavigator), false);
});
