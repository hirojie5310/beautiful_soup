from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_apply_event_to_playback_status_uses_event_delta_not_max_hp_gap() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    battle_js_url = (repo_root / "web_wasm" / "battle_playback.js").resolve().as_uri()
    script = """
import { applyEventToPlaybackStatus } from "__BATTLE_JS_URL__";

const playbackStatus = {
  party: [],
  enemies: [
    {
      name: "Goblin",
      hp: 40,
      max_hp: 100,
      status: { hp: 40 },
      status_icons: [],
      out_of_battle: false,
    },
  ],
};

const applied = applyEventToPlaybackStatus(playbackStatus, {
  type: "damage",
  target_side: "enemy",
  target_index: 0,
  value: 10,
  display_value: 12,
  old_hp: 40,
  new_hp: 30,
});

console.log(JSON.stringify({
  applied,
  hp: playbackStatus.enemies[0].hp,
  status_hp: playbackStatus.enemies[0].status.hp,
}));
""".replace("__BATTLE_JS_URL__", battle_js_url)
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["applied"]["popup"]["kind"] == "damage"
    assert payload["applied"]["popup"]["value"] == 12
    assert payload["hp"] == 30
    assert payload["status_hp"] == 30
