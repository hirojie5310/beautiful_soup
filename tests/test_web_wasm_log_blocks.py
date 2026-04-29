from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_build_log_blocks_preserves_all_action_headers_and_appends_reward_block() -> (
    None
):
    repo_root = Path(__file__).resolve().parents[1]
    battle_js_url = (repo_root / "web_wasm" / "battle_playback.js").resolve().as_uri()
    script = """
import {
  buildLogBlocks,
  injectResourceDiffsIntoRewardLogs,
} from "__BATTLE_JS_URL__";

const logs = [
  "Eaterの《Divide》！ 同じ敵が現れた。",
  "▶ Refia の行動（Fight）",
  "Eater Aに44のダメージ。",
  "◆ Greater Demon の行動",
  "Greater Demonの《Summon》！ Iron Clawsが現れた。",
  "▶ Arc の行動（Magic）",
  "敵全体に999のダメージ。",
  "▶ Ingus の行動（Fight）",
  "Ingusは敵が全滅していたため行動できなかった。",
];
const rewards = {
  gained_exp: 123,
  gained_gil: 45,
  gil_before: 10,
  gil_after: 55,
  gained_cp: 6,
  cp_before: 1,
  cp_after: 7,
  dropped_item: ["Potion"],
};
const blocks = buildLogBlocks(injectResourceDiffsIntoRewardLogs(logs, rewards));

console.log(JSON.stringify(blocks.map((block) => ({
  type: block.type,
  first: block.lines[0],
  size: block.lines.length,
}))));
""".replace("__BATTLE_JS_URL__", battle_js_url)
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload[0]["type"] == "system"
    assert payload[0]["first"] == "Eaterの《Divide》！ 同じ敵が現れた。"
    assert payload[1]["type"] == "action"
    assert payload[1]["first"] == "▶ Refia の行動（Fight）"
    assert payload[2]["type"] == "action"
    assert payload[2]["first"] == "◆ Greater Demon の行動"
    assert payload[3]["type"] == "action"
    assert payload[3]["first"] == "▶ Arc の行動（Magic）"
    assert payload[4]["type"] == "action"
    assert payload[4]["first"] == "▶ Ingus の行動（Fight）"
    assert payload[5]["type"] == "reward"
    assert payload[5]["first"] == "=== Battle Rewards ==="
