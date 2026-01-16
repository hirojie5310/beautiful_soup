let battleId = null;
let currentState = null;

/* ===== UI状態 ===== */
const uiState = {
  actorIndex: 0,
  currentCommand: null,
};

/* ===== 共通 ===== */
function $(id) {
  return document.getElementById(id);
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : null,
  });
  return await res.json();
}

/* ===== 描画 ===== */
function render(state) {
  // Party
  $("party").innerHTML = state.party
    .map((p, i) => {
      const mark = (i === uiState.actorIndex) ? "▶ " : "  ";
      return `${mark}${p.name}  HP ${p.hp}/${p.max_hp}`;
    })
    .join("<br>");

  // Enemies
  $("enemies").innerHTML = state.enemies
    .map(e => `${e.name}  HP ${e.hp}/${e.max_hp}`)
    .join("<br>");

  // Logs
  $("log").textContent = state.logs.join("\n");
}

/* ===== コマンド選択 ===== */
function showCommandMenu() {
  const panel = $("commandPanel");
  const targetPanel = $("targetPanel");
  panel.innerHTML = "";
  targetPanel.innerHTML = "";

  const btnFight = document.createElement("button");
  btnFight.textContent = "たたかう";
  btnFight.onclick = () => {
    uiState.currentCommand = {
      kind: "fight",
      target_side: "enemy",
      target_all: false,
    };
    showTargetMenu();
  };

  panel.appendChild(btnFight);
}

/* ===== ターゲット選択 ===== */
function showTargetMenu() {
  const panel = $("targetPanel");
  panel.innerHTML = "";

  currentState.enemies.forEach((enemy, idx) => {
    const btn = document.createElement("button");
    btn.textContent = enemy.name;
    btn.onclick = () => finalizeAction(idx);
    panel.appendChild(btn);
  });
}

/* ===== 行動確定 ===== */
async function finalizeAction(targetIndex) {
  const actor = uiState.actorIndex;

  await postJson(`/api/battle/${battleId}/plan`, {
    actor_index: actor,
    kind: uiState.currentCommand.kind,
    target_side: "enemy",
    target_index: targetIndex,
    target_all: false,
  });

  uiState.actorIndex++;

  // 全員分入力した？
  if (uiState.actorIndex >= currentState.party.length) {
    const result = await postJson(
      `/api/battle/${battleId}/resolve`,
      null
    );

    currentState = result.state;
    render(currentState);

    // 次ラウンド準備
    uiState.actorIndex = 0;
    showCommandMenu();
  } else {
    // 次のキャラへ
    render(currentState);
    showCommandMenu();
  }
}

/* ===== バトル開始 ===== */
async function startBattle() {
  const data = await postJson("/api/battle/start", {
    enemy_names: ["Flyer", "Gutsco"], // テスト用
  });

  battleId = data.battle_id;
  currentState = data.state;

  uiState.actorIndex = 0;
  render(currentState);
  showCommandMenu();
}

/* ===== 初期化 ===== */
window.addEventListener("load", () => {
  startBattle();
});
