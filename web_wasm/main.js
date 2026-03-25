import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

const bootBtn = document.getElementById("bootBtn");
const nextRoundBtn = document.getElementById("nextRoundBtn");
const battlePhase = document.getElementById("battlePhase");
const partyGrid = document.getElementById("partyGrid");
const enemyGrid = document.getElementById("enemyGrid");
const commandGrid = document.getElementById("commandGrid");
const statusLine = document.getElementById("statusLine");
const logView = document.getElementById("logView");
const plannedActionsView = document.getElementById("plannedActionsView");
const rewardPanel = document.getElementById("rewardPanel");

let pyodide = null;
let sessionStatus = { party: [], enemies: [] };
let pendingActions = [];
let currentMemberIndex = 0;
let selectedEnemyIndex = 0;
let lifecycleState = "ready_for_actions";
let battleFinished = false;

const COMMAND_DEFS = [
  { kind: "physical", command: "Fight", label: "たたかう", targetSide: "enemy" },
  { kind: "defend", command: "Defend", label: "ぼうぎょ", targetSide: "self" },
  { kind: "run", command: "Flee", label: "にげる", targetSide: "self" },
  { kind: "special", command: "Cheer", label: "おうえん", targetSide: "ally" },
];

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

function selectedEnemySafeIndex() {
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  if (!enemies.length) return 0;
  return Math.min(selectedEnemyIndex, enemies.length - 1);
}

function buildActionFromCommand(def) {
  const enemyIndex = selectedEnemySafeIndex();
  if (def.targetSide === "self") {
    return {
      kind: def.kind,
      command: def.command,
      target_side: "self",
      target_index: currentMemberIndex,
      target_all: false,
    };
  }
  if (def.targetSide === "ally") {
    return {
      kind: def.kind,
      command: def.command,
      target_side: "ally",
      target_index: currentMemberIndex,
      target_all: false,
    };
  }
  return {
    kind: def.kind,
    command: def.command,
    target_side: "enemy",
    target_index: enemyIndex,
    target_all: false,
  };
}

function renderParty() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  partyGrid.innerHTML = "";
  party.forEach((member, idx) => {
    const card = document.createElement("article");
    const activeClass = idx === currentMemberIndex && !battleFinished ? " active" : "";
    card.className = `card${activeClass}`;
    card.innerHTML = `
      <div class="name">${member?.name ?? `Member ${idx + 1}`}</div>
      <div class="hp">HP ${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}</div>
      <div class="status">Lv ${Number(member?.level ?? 0)}</div>
    `;
    partyGrid.appendChild(card);
  });
}

function renderEnemies() {
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  enemyGrid.innerHTML = "";
  enemies.forEach((enemy, idx) => {
    const card = document.createElement("article");
    const selectedClass = idx === selectedEnemySafeIndex() ? " selected" : "";
    card.className = `card target${selectedClass}`;
    card.innerHTML = `
      <div class="name">${enemy?.name ?? `Enemy ${idx + 1}`}</div>
      <div class="hp">HP ${Number(enemy?.hp ?? 0)} / ${Number(enemy?.max_hp ?? 0)}</div>
    `;
    card.addEventListener("click", () => {
      if (battleFinished) return;
      selectedEnemyIndex = idx;
      renderEnemies();
      renderStatus();
    });
    enemyGrid.appendChild(card);
  });
}

function renderCommandButtons() {
  commandGrid.innerHTML = "";
  COMMAND_DEFS.forEach((def) => {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = def.label;
    button.disabled = !pyodide || battleFinished;
    button.addEventListener("click", () => {
      chooseCommand(def);
    });
    commandGrid.appendChild(button);
  });
}

function renderPlannedActions() {
  plannedActionsView.textContent = pendingActions.length
    ? JSON.stringify(pendingActions, null, 2)
    : "(none)";
}

function renderStatus() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  if (battleFinished) {
    statusLine.textContent = "戦闘終了。Bootし直すと再開始できます。";
    return;
  }
  const actor = party[currentMemberIndex];
  const target = enemies[selectedEnemySafeIndex()];
  if (!actor) {
    statusLine.textContent = "操作可能なメンバーがいません。";
    return;
  }
  statusLine.textContent = `行動入力: ${actor.name} / 対象: ${target?.name ?? "(なし)"} / 入力済み ${pendingActions.length}/${party.length}`;
}

function maybeShowRewards(payload) {
  if (payload?.end_reason === "enemy_defeated" && payload?.victory_rewards) {
    const rewards = payload.victory_rewards;
    rewardPanel.classList.add("open");
    rewardPanel.innerHTML = `
      <strong>Victory Rewards</strong><br>
      EXP +${Number(rewards?.gained_exp ?? 0)} / Gil +${Number(rewards?.gained_gil ?? 0)} / CP +${Number(rewards?.gained_cp ?? 0)}<br>
      Drop: ${Array.isArray(rewards?.dropped_item) && rewards.dropped_item.length ? rewards.dropped_item.join(", ") : "(none)"}
    `;
    return;
  }
  rewardPanel.classList.remove("open");
  rewardPanel.textContent = "";
}

function rerenderAll() {
  renderParty();
  renderEnemies();
  renderCommandButtons();
  renderPlannedActions();
  renderStatus();
  nextRoundBtn.disabled = !pyodide || battleFinished || pendingActions.length === 0;
}

function chooseCommand(def) {
  if (battleFinished) return;
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  if (!party.length) return;
  const action = buildActionFromCommand(def);
  pendingActions.push(action);
  currentMemberIndex = Math.min(pendingActions.length, Math.max(0, party.length - 1));
  if (pendingActions.length >= party.length) {
    nextRoundBtn.disabled = false;
    battlePhase.textContent = "全員入力済み。ラウンド実行できます。";
  } else {
    nextRoundBtn.disabled = true;
    battlePhase.textContent = `${pendingActions.length}/${party.length} 入力済み`;
  }
  rerenderAll();
}

async function bootEngine() {
  bootBtn.disabled = true;
  battlePhase.textContent = "Pyodide 起動中...";

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
  const initialPayload = JSON.parse(getInitialPayloadJson());
  sessionStatus = initialPayload?.session_status ?? { party: [], enemies: [] };
  lifecycleState = "ready_for_actions";
  battleFinished = false;
  pendingActions = [];
  currentMemberIndex = 0;
  selectedEnemyIndex = 0;

  battlePhase.textContent = "起動完了。コマンド入力を開始してください。";
  nextRoundBtn.disabled = true;
  logView.textContent = "(not executed)";
  rewardPanel.classList.remove("open");
  rewardPanel.textContent = "";
  rerenderAll();
}

async function executeRound() {
  if (!pyodide || battleFinished) return;
  const runRound = pyodide.globals.get("run_battle_round_wasm");
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  if (pendingActions.length < party.length) {
    statusLine.textContent = `まだ ${party.length - pendingActions.length} 人分の入力が必要です。`;
    return;
  }

  nextRoundBtn.disabled = true;
  battlePhase.textContent = "ラウンド解決中...";
  const payload = {
    planned_actions: pendingActions,
    lifecycle_state: lifecycleState,
  };
  const resultJson = runRound(JSON.stringify(payload));
  const result = JSON.parse(resultJson);

  sessionStatus = result?.session_status ?? sessionStatus;
  lifecycleState = result?.lifecycle?.after === "ready_for_next_round"
    ? "ready_for_actions"
    : (result?.lifecycle?.after ?? "ready_for_actions");
  battleFinished = Boolean(result?.lifecycle?.battle_finished);

  const logs = Array.isArray(result?.logs) ? result.logs : [];
  logView.textContent = logs.length ? logs.join("\n") : "(no logs)";
  maybeShowRewards(result);

  pendingActions = [];
  currentMemberIndex = 0;
  selectedEnemyIndex = 0;
  battlePhase.textContent = battleFinished
    ? `戦闘終了: ${result?.end_reason ?? "finished"}`
    : "次ターンの入力を開始してください。";

  rerenderAll();
}

bootBtn.addEventListener("click", () => {
  bootEngine().catch((error) => {
    battlePhase.textContent = `Boot失敗: ${String(error)}`;
    bootBtn.disabled = false;
  });
});

nextRoundBtn.addEventListener("click", () => {
  executeRound().catch((error) => {
    logView.textContent = String(error);
  });
});

rerenderAll();
