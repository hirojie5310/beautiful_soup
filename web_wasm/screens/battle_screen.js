import { initializeBattleApp } from "../battle.js";

function renderLayout() {
  return `
    <style>
      .battle-screen { width:min(860px,100vw); margin:0 auto; min-height:100vh; padding:10px; display:grid; gap:10px; grid-template-rows:auto auto auto 1fr; }
      .battle-screen .frame { border:2px solid rgba(255,255,255,.45); border-radius:10px; background:rgba(16,24,56,.95); padding:10px; }
      .battle-screen #enemyFrame { background-size:cover; background-position:center; }
      .battle-screen .title{ margin:0 0 8px; color:#ffe588; font-size:.95rem; }
      .battle-screen .toolbar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
      .battle-screen .btn { border:1px solid rgba(255,255,255,.7); border-radius:8px; color:#eef2ff; background:linear-gradient(180deg,#4459bf,#20317e); padding:8px 10px; cursor:pointer; }
      .battle-screen .status { color:#acb6d7; font-size:.9rem; }
      .battle-screen .party-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
      .battle-screen .enemy-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(120px,1fr)); gap:8px; }
      .battle-screen .card { border:1px solid rgba(255,255,255,.35); border-radius:8px; padding:8px; background:rgba(0,0,0,.25); }
      .battle-screen .card.active { border-color:#ffe588; box-shadow:0 0 0 2px rgba(255,229,136,.35) inset; }
      .battle-screen .card.target { cursor:pointer; }
      .battle-screen .card.selected { border-color:#ffe588; }
      .battle-screen .party-card,.battle-screen .enemy-card{ position:relative; overflow:hidden; min-height:112px; isolation:isolate; background-size:cover; background-position:center; background-repeat:no-repeat; }
      .battle-screen .party-card::after,.battle-screen .enemy-card::after{ content:""; position:absolute; inset:0; z-index:1; pointer-events:none; background:linear-gradient(180deg, rgba(3,6,19,0.58), rgba(3,6,19,0.72)); }
      .battle-screen .party-face,.battle-screen .enemy-sprite{ position:absolute; inset:0; width:100%; height:100%; opacity:.9; filter:brightness(.55) saturate(.95); z-index:0; }
      .battle-screen .party-face{ object-fit:cover; object-position:center 22%; }
      .battle-screen .enemy-sprite{ object-fit:contain; object-position:center; }
      .battle-screen .party-face-fallback,.battle-screen .enemy-sprite-fallback{ position:absolute; inset:0; display:grid; place-items:center; background:rgba(4,8,24,.78); color:#acb6d7; font-size:.7rem; z-index:0; }
      .battle-screen .party-card-content,.battle-screen .enemy-card-content{ position:relative; z-index:2; text-shadow:0 1px 4px rgba(0,0,0,.82); display:flex; flex-direction:column; gap:2px; }
      .battle-screen .party-name-row { order: 1; }
      .battle-screen .party-hp-row { order: 2; }
      .battle-screen .party-level-row { order: 3; }
      .battle-screen .party-status-icons-row { order: 4; min-height: 16px; }
      .battle-screen .name { font-weight:700; font-size:.86rem; }
      .battle-screen .hp { font-size:.78rem; color:#89f0ac; }
      .battle-screen .combat-popup-layer { position:absolute; inset:0; z-index:3; pointer-events:none; }
      .battle-screen .combat-popup { position:absolute; left:50%; top:44%; transform:translate(-50%,-50%); font-weight:700; font-size:1.3rem; color:#ffb3b3; text-shadow:0 2px 6px rgba(0,0,0,.9); letter-spacing:.03em; animation:combat-popup-rise .45s ease-out both; }
      .battle-screen .combat-popup.heal { color:#9ff7ba; }
      .battle-screen .combat-popup.miss { color:#ffe588; font-size:1rem; }
      .battle-screen .combat-effect-layer { position:absolute; inset:0; z-index:3; pointer-events:none; overflow:hidden; }
      .battle-screen .combat-slash { position:absolute; width:41px; height:44px; left:0; top:0; background-image:var(--slash-image); background-repeat:no-repeat; background-size:82px 44px; image-rendering:auto; mix-blend-mode:screen; opacity:0; transform:translate(var(--slash-start-x, 0px), var(--slash-start-y, 0px)); animation:combat-slash-sweep .22s steps(2) both; }
      .battle-screen .command-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
      .battle-screen .command-grid.command-mode { grid-template-columns:repeat(4,minmax(0,1fr)); }
      .battle-screen .magic-group-header { padding:2px 6px 2px 2px; color:#ffe588; font-size:.84rem; font-weight:700; white-space:nowrap; }
      .battle-screen .magic-group-row { grid-column:1/-1; display:flex; align-items:center; gap:8px; }
      .battle-screen .magic-group-spells { display:flex; gap:8px; flex-wrap:nowrap; overflow-x:auto; }
      .battle-screen pre { margin:0; border:1px solid rgba(255,255,255,.28); border-radius:8px; background:#0b1229; max-height:300px; overflow:auto; white-space:pre-wrap; padding:8px; line-height:1.45; }
      .battle-screen .reward { border:1px solid rgba(255,229,136,.5); background:rgba(255,229,136,.09); border-radius:8px; padding:8px; display:none; }
      .battle-screen .reward.open { display:block; }
      .battle-screen .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
      @keyframes combat-popup-rise { from { opacity:0; transform:translate(-50%,-20%); } to { opacity:1; transform:translate(-50%,-60%); } }
      @keyframes combat-slash-sweep {
        0% { opacity:0; background-position:0 0; transform:translate(var(--slash-start-x, 0px), var(--slash-start-y, 0px)); }
        20% { opacity:1; }
        100% { opacity:0; background-position:-82px 0; transform:translate(var(--slash-end-x, 0px), var(--slash-end-y, 0px)); }
      }
    </style>
    <div class="battle-screen">
      <section class="frame">
        <h1 class="title">Battle Wasm Runner</h1>
        <div class="toolbar">
          <span id="battlePhase" class="status">起動中...</span>
          <button id="locationBtn" class="btn" type="button">Location選択</button>
          <button id="menuBtn" class="btn" type="button">メニュー</button>
          <button id="loadSaveBtn" class="btn" type="button">ロード</button>
          <input id="loadSaveInput" type="file" accept="application/json,.json" style="display:none;" />
        </div>
      </section>
      <section class="frame"><h2 class="title">PARTY</h2><div id="partyGrid" class="party-grid"></div></section>
      <section id="enemyFrame" class="frame"><h2 class="title">ENEMY（対象を選択）</h2><div id="enemyGrid" class="enemy-grid"></div></section>
      <section id="commandFrame" class="frame">
        <h2 class="title">COMMAND</h2>
        <div id="statusLine" class="status">エンジン起動中です...</div>
        <div id="commandGrid" class="command-grid"></div>
        <h3 class="title" style="margin-top:10px;">Planned Actions</h3>
        <pre id="plannedActionsView" class="mono">(none)</pre>
      </section>
      <section id="battleLogFrame" class="frame" style="display:none;">
        <div class="toolbar" style="justify-content:space-between; margin-top:10px;">
          <h3 class="title" style="margin:0;">Battle Logs</h3>
          <button id="downloadSaveBtn" class="btn" type="button">保存</button>
        </div>
        <pre id="logView">(not executed)</pre>
        <div id="rewardPanel" class="reward" style="margin-top:10px;"></div>
      </section>
    </div>
  `;
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();
  await initializeBattleApp({ root: mountNode, store, navigate });
  return () => {};
}
