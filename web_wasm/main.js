import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

const bootBtn = document.getElementById("bootBtn");
const roundBtn = document.getElementById("roundBtn");
const initialPayloadEl = document.getElementById("initialPayload");
const roundResultEl = document.getElementById("roundResult");

let pyodide = null;

async function preparePythonBundle(instance) {
  const response = await fetch("./python_bundle.zip");
  if (!response.ok) {
    throw new Error(`python_bundle.zip fetch failed: ${response.status}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/python_bundle.zip", bytes);
  await instance.runPythonAsync(`
import sys
import zipfile

with zipfile.ZipFile("/tmp/python_bundle.zip", "r") as bundle:
    bundle.extractall("/")

if "/" not in sys.path:
    sys.path.insert(0, "/")
`);
}

async function bootEngine() {
  bootBtn.disabled = true;
  initialPayloadEl.textContent = "booting...";

  pyodide = await loadPyodide();
  await pyodide.loadPackage("typing-extensions");
  await preparePythonBundle(pyodide);
  await pyodide.runPythonAsync(`
from combat.wasm_api import WasmBattleEngine

engine = WasmBattleEngine.create_default(seed=7)

def get_initial_payload_json():
    import json
    return json.dumps(engine.build_initial_payload(), ensure_ascii=False)

def run_battle_round_wasm(js_input_json):
    return engine.execute_round_json(js_input_json)
`);

  const getInitialPayloadJson = pyodide.globals.get("get_initial_payload_json");
  initialPayloadEl.textContent = JSON.stringify(
    JSON.parse(getInitialPayloadJson()),
    null,
    2,
  );
  roundBtn.disabled = false;
}

async function executeRound() {
  if (!pyodide) {
    return;
  }
  roundResultEl.textContent = "executing...";
  const runRound = pyodide.globals.get("run_battle_round_wasm");
  const resultJson = runRound(
    JSON.stringify({
      planned_actions: [],
      lifecycle_state: "ready_for_actions",
    }),
  );
  roundResultEl.textContent = JSON.stringify(JSON.parse(resultJson), null, 2);
}

bootBtn.addEventListener("click", () => {
  bootEngine().catch((error) => {
    initialPayloadEl.textContent = String(error);
    bootBtn.disabled = false;
  });
});

roundBtn.addEventListener("click", () => {
  executeRound().catch((error) => {
    roundResultEl.textContent = String(error);
  });
});
