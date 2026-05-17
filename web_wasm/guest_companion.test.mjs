import test from "node:test";
import assert from "node:assert/strict";

import {
  isCidGuestActive,
  isSaraGuestActive,
  resolveActiveGuestFollowerType,
  resolveGuestPortraitDescriptor,
} from "./guest_companion.js";

test("Sara guest remains active until the leave flag is set", () => {
  assert.equal(isSaraGuestActive({
    save: {
      event_flag: {
        sealed_cave_b2_2_sara_escort_started: true,
      },
    },
  }), true);
  assert.equal(isSaraGuestActive({
    save: {
      event_flag: {
        sealed_cave_b2_2_sara_escort_started: true,
        sara_left_party: true,
      },
    },
  }), false);
});

test("Cid guest becomes active after the Kazus join event", () => {
  assert.equal(isCidGuestActive({
    save: {
      event_flag: {
        kazus_cid_follower_joined: true,
      },
    },
  }), true);
});

test("active guest follower prefers forced or active Sara before Cid", () => {
  assert.equal(resolveActiveGuestFollowerType({
    save: {
      event_flag: {
        kazus_cid_follower_joined: true,
      },
    },
  }, {
    forceSaraVisible: true,
  }), "sara");
  assert.equal(resolveActiveGuestFollowerType({
    save: {
      event_flag: {
        sealed_cave_b2_2_sara_escort_started: true,
        kazus_cid_follower_joined: true,
      },
    },
  }), "sara");
  assert.equal(resolveActiveGuestFollowerType({
    save: {
      event_flag: {
        sara_left_party: true,
        kazus_cid_follower_joined: true,
      },
    },
  }), "cid");
});

test("guest portrait descriptor resolves Sara and Cid portraits", () => {
  assert.deepEqual(resolveGuestPortraitDescriptor({
    save: {
      event_flag: {
        sealed_cave_b2_2_sara_escort_started: true,
      },
    },
  }), {
    label: "SARA",
    alt: "Sara portrait",
    imageUrl: "../assets/images/faces/portrait_sara.png",
    fallbackText: "SARA",
  });
  assert.deepEqual(resolveGuestPortraitDescriptor({
    save: {
      event_flag: {
        sara_left_party: true,
        kazus_cid_follower_joined: true,
      },
    },
  }), {
    label: "CID",
    alt: "Cid portrait",
    imageUrl: "../assets/images/faces/portrait_cid.png",
    fallbackText: "CID",
  });
});
