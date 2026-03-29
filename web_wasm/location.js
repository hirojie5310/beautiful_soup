import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

const statusLine = document.getElementById("statusLine");
const locationGroupSelect = document.getElementById("locationGroupSelect");
const locationSelect = document.getElementById("locationSelect");
const startBattleBtn = document.getElementById("startBattleBtn");
const menuBtn = document.getElementById("menuBtn");

const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";
const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";

let pyodide = null;
let locationGroups = [];

async function preparePythonBundle(instance) {
  const response = await fetch("./python_bundle.zip");
  if (!response.ok) throw new Error(`python_bundle.zip fetch failed: ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/python_bundle.zip", bytes);
  await instance.runPythonAsync(`
import sys
import zipfile

with zipfile.ZipFile('/tmp/python_bundle.zip', 'r') as bundle:
    bundle.extractall('/')
if '/' not in sys.path:
    sys.path.insert(0, '/')
`);
}

async function prepareExplicitGroups(instance) {
  const response = await fetch("../assets/data/explicit_groups.json");
  if (!response.ok) {
    instance.FS.writeFile("/tmp/explicit_groups.json", new Uint8Array());
    return;
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/explicit_groups.json", bytes);
}

function parseStoredSelection() {
  try {
    const raw = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return {
      selected_location_group: String(parsed.selected_location_group || ""),
      selected_location: String(parsed.selected_location || ""),
    };
  } catch (_error) {
    return null;
  }
}

function renderLocationSelectors() {
  const selectedGroupName = locationGroupSelect.value;
  locationGroupSelect.innerHTML = "";
  locationGroups.forEach((group) => {
    const option = document.createElement("option");
    option.value = group.group_name;
    option.textContent = group.group_name;
    if (group.group_name === selectedGroupName) option.selected = true;
    locationGroupSelect.appendChild(option);
  });

  const currentGroup = locationGroups.find((g) => g.group_name === locationGroupSelect.value) || locationGroups[0];
  const locations = Array.isArray(currentGroup?.locations) ? currentGroup.locations : [];
  const selectedLocation = locationSelect.value;
  locationSelect.innerHTML = "";
  locations.forEach((loc) => {
    const option = document.createElement("option");
    option.value = loc;
    option.textContent = loc;
    if (loc === selectedLocation) option.selected = true;
    locationSelect.appendChild(option);
  });
  if (locations.length && !locationSelect.value) locationSelect.value = locations[0];
}

function saveAndGoBattle() {
  const payload = {
    selected_location_group: String(locationGroupSelect.value || ""),
    selected_location: String(locationSelect.value || ""),
  };
  sessionStorage.setItem(BATTLE_START_SELECTION_KEY, JSON.stringify(payload));
  window.location.href = "./battle.html";
}

async function bootLocationScreen() {
  statusLine.textContent = "Pyodide 起動中...";
  pyodide = await loadPyodide();
  await pyodide.loadPackage("typing-extensions");
  await preparePythonBundle(pyodide);
  await prepareExplicitGroups(pyodide);

  const bootstrapResponse = await fetch("./bootstrap_runtime.py");
  if (!bootstrapResponse.ok) throw new Error(`bootstrap_runtime.py fetch failed: ${bootstrapResponse.status}`);
  const bootstrapPython = await bootstrapResponse.text();
  await pyodide.runPythonAsync(bootstrapPython);

  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const selectionPayload = JSON.parse(getSelectionJson());
  locationGroups = Array.isArray(selectionPayload?.groups) ? selectionPayload.groups : [];
  renderLocationSelectors();

  const stored = parseStoredSelection();
  if (stored?.selected_location_group) {
    locationGroupSelect.value = stored.selected_location_group;
    renderLocationSelectors();
  } else if (selectionPayload?.selected_group) {
    locationGroupSelect.value = selectionPayload.selected_group;
    renderLocationSelectors();
  }

  if (stored?.selected_location) {
    locationSelect.value = stored.selected_location;
  } else if (selectionPayload?.selected_location) {
    locationSelect.value = selectionPayload.selected_location;
  }

  startBattleBtn.disabled = false;
  statusLine.textContent = "Locationを選択して「戦闘開始」を押してください。";
}

locationGroupSelect?.addEventListener("change", () => renderLocationSelectors());
startBattleBtn?.addEventListener("click", () => saveAndGoBattle());
menuBtn?.addEventListener("click", () => {
  window.location.href = "./menu.html";
});

bootLocationScreen().catch((error) => {
  statusLine.textContent = `起動失敗: ${String(error)}`;
});
