from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class WebWasmBattlePopupOverrideTest(unittest.TestCase):
    def test_named_miss_does_not_override_existing_damage_popup(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        battle_js_url = (repo_root / "web_wasm" / "battle_playback.js").resolve().as_uri()
        script = """
import { applyNamedPopupOverrides } from "__BATTLE_JS_URL__";

const current = {
  "enemy:0": { kind: "damage", value: 184 },
};
const next = applyNamedPopupOverrides(current, [
  { side: "enemy", index: 0, kind: "miss", value: 0 },
]);

console.log(JSON.stringify(next));
""".replace("__BATTLE_JS_URL__", battle_js_url)
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(payload["enemy:0"]["kind"], "damage")
        self.assertEqual(payload["enemy:0"]["value"], 184)


if __name__ == "__main__":
    unittest.main()
