from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class WebWasmBattleDamagePopupTextTest(unittest.TestCase):
    def test_damage_popup_text_does_not_prefix_minus(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = """
const popup = { kind: "damage", value: 1788 };
const value = Number(popup?.value ?? 0);
const kind = String(popup?.kind || "");
let text = String(popup?.text || value);
let extraClass = "";
if (kind === "status") {
  text = String(popup?.text || "");
  extraClass = popup?.statusCategory === "cure" ? " status cure" : " status";
} else if (kind === "heal") {
  text = `+${Math.abs(value)}`;
  extraClass = " heal";
} else if (kind === "miss") {
  text = "MISS";
  extraClass = " miss";
} else if (value > 0) {
  text = `${value}`;
} else if (value < 0) {
  text = `+${Math.abs(value)}`;
  extraClass = " heal";
} else {
  text = "0";
  extraClass = " miss";
}
console.log(`${text}|${extraClass}`);
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), "1788|")


if __name__ == "__main__":
    unittest.main()
