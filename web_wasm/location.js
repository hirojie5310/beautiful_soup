import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";
import {
  prepareExplicitGroups,
  preparePythonBundle,
  getStoredLocationSelection,
  syncStoredLocationSelection,
} from "./location_shared.js";

const statusLine = document.getElementById("statusLine");
const locationGroupSelect = document.getElementById("locationGroupSelect");
const locationSelect = document.getElementById("locationSelect");
const startBattleBtn = document.getElementById("startBattleBtn");
const shopBtn = document.getElementById("shopBtn");
const innBtn = document.getElementById("innBtn");
const menuBtn = document.getElementById("menuBtn");

const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";

let pyodide = null;
let locationGroups = [];

function setSelectOptions(select, values, selectedValue = "") {
  if (!select) return;
  const wanted = String(selectedValue || "");
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    if (String(value) === wanted) option.selected = true;
    select.appendChild(option);
  });
  if (values.length && !select.value) {
    select.value = String(values[0]);
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
  syncStoredLocationSelection(payload.selected_location_group, payload.selected_location);
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

  const stored = getStoredLocationSelection();
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

  syncStoredLocationSelection(String(locationGroupSelect.value || ""), String(locationSelect.value || ""));
  startBattleBtn.disabled = false;
  statusLine.textContent = "Locationを選択して「戦闘開始」を押してください。";
}

locationGroupSelect?.addEventListener("change", () => {
  renderLocationSelectors();
  syncStoredLocationSelection(String(locationGroupSelect.value || ""), String(locationSelect.value || ""));
});
locationSelect?.addEventListener("change", () => {
  syncStoredLocationSelection(String(locationGroupSelect.value || ""), String(locationSelect.value || ""));
});
startBattleBtn?.addEventListener("click", () => saveAndGoBattle());
shopBtn?.addEventListener("click", () => {
  syncStoredLocationSelection(String(locationGroupSelect.value || ""), String(locationSelect.value || ""));
  window.location.href = "./shop.html";
});
innBtn?.addEventListener("click", () => {
  syncStoredLocationSelection(String(locationGroupSelect.value || ""), String(locationSelect.value || ""));
  window.location.href = "./inn.html";
});
menuBtn?.addEventListener("click", () => {
  syncStoredLocationSelection(String(locationGroupSelect.value || ""), String(locationSelect.value || ""));
  window.location.href = "./menu.html";
});

bootLocationScreen().catch((error) => {
  statusLine.textContent = `起動失敗: ${String(error)}`;
});
