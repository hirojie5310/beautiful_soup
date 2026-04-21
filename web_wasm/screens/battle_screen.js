import { initializeBattleApp } from "../battle.js";

function renderLayout() {
  return `
    <style>
      .battle-screen {
        --battle-gutter: 10px;
        --dock-height: 36vh;
        width: min(860px, 100vw);
        margin: 0 auto;
        min-height: 100vh;
        min-height: 100dvh;
        padding: var(--battle-gutter);
        box-sizing: border-box;
        display: grid;
        grid-template-rows: minmax(0, 1fr) minmax(260px, var(--dock-height));
        gap: var(--battle-gutter);
        background:
          radial-gradient(circle at top, rgba(74, 100, 201, 0.22), transparent 42%),
          linear-gradient(180deg, #0d1430 0%, #070b18 100%);
        position: relative;
      }
      .battle-screen .frame {
        border: 1px solid rgba(255,255,255,.22);
        border-radius: 18px;
        background: rgba(11,18,41,.92);
        box-shadow: 0 16px 40px rgba(0,0,0,.28);
        backdrop-filter: blur(6px);
      }
      .battle-screen .battle-stage {
        min-height: 0;
        display: grid;
        grid-template-rows: auto minmax(0, 1fr);
        gap: 10px;
      }
      .battle-screen .battle-stage-header {
        padding: 12px 14px;
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: flex-start;
      }
      .battle-screen .battle-stage-heading {
        display: grid;
        gap: 4px;
        min-width: 0;
      }
      .battle-screen .toolbar {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        justify-content: flex-end;
      }
      .battle-screen .btn {
        border: 1px solid rgba(255,255,255,.24);
        border-radius: 12px;
        color: #eef2ff;
        background: linear-gradient(180deg, #4459bf, #20317e);
        padding: 10px 12px;
        cursor: pointer;
      }
      .battle-screen .status {
        color: #acb6d7;
        font-size: .88rem;
      }
      .battle-screen .battle-stage-panel {
        min-height: 0;
        padding: 0;
        overflow: hidden;
      }
      .battle-screen #enemyFrame {
        height: 100%;
        background-size: cover;
        background-position: center;
        display: grid;
        grid-template-rows: auto minmax(0, 1fr);
      }
      .battle-screen .enemy-stage-head {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: center;
        padding: 10px 14px 0;
      }
      .battle-screen .enemy-stage-caption {
        color: #acb6d7;
        font-size: .76rem;
      }
      .battle-screen .enemy-stage-body {
        min-height: 0;
        display: grid;
        place-items: center;
        padding: 8px 14px 14px;
      }
      .battle-screen .party-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 8px;
      }
      .battle-screen .party-grid.party-hud {
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }
      .battle-screen .enemy-grid {
        width: min(100%, 420px);
        display: grid;
        grid-template-columns: repeat(2, minmax(120px, 1fr));
        grid-template-rows: repeat(2, minmax(0, 1fr));
        gap: 10px;
        grid-auto-flow: column;
        align-content: center;
        justify-content: center;
        justify-items: stretch;
        margin: 0 auto;
      }
      .battle-screen .enemy-grid[data-count="1"] {
        width: min(100%, 220px);
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: minmax(0, 1fr);
      }
      .battle-screen .enemy-grid[data-count="2"] {
        width: min(100%, 220px);
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: repeat(2, minmax(0, 1fr));
      }
      .battle-screen .enemy-grid[data-count="3"],
      .battle-screen .enemy-grid[data-count="4"] {
        width: min(100%, 320px);
        grid-template-columns: repeat(2, minmax(120px, 1fr));
        grid-template-rows: repeat(2, minmax(0, 1fr));
      }
      .battle-screen .enemy-grid[data-count="5"],
      .battle-screen .enemy-grid[data-count="6"] {
        width: min(100%, 420px);
        grid-template-columns: repeat(3, minmax(108px, 1fr));
        grid-template-rows: repeat(2, minmax(0, 1fr));
        gap: 8px;
      }
      .battle-screen .enemy-grid[data-count="5"] .enemy-card,
      .battle-screen .enemy-grid[data-count="6"] .enemy-card {
        min-height: 96px;
        padding: 6px;
      }
      .battle-screen .enemy-grid[data-count="5"] .enemy-card .name,
      .battle-screen .enemy-grid[data-count="6"] .enemy-card .name {
        font-size: .76rem;
      }
      .battle-screen .enemy-grid[data-count="5"] .enemy-card .hp,
      .battle-screen .enemy-grid[data-count="6"] .enemy-card .hp {
        font-size: .68rem;
      }
      .battle-screen .enemy-grid[data-count="5"] .enemy-card .status-icon-row,
      .battle-screen .enemy-grid[data-count="6"] .enemy-card .status-icon-row {
        display: none !important;
      }
      .battle-screen .battle-dock {
        min-height: 0;
        display: grid;
        grid-template-rows: auto auto minmax(0, 1fr);
        gap: 10px;
        padding: 12px;
        position: sticky;
        bottom: 0;
        overflow: visible;
      }
      .battle-screen .dock-topbar {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
      }
      .battle-screen .dock-progress {
        display: grid;
        gap: 4px;
        min-width: 0;
      }
      .battle-screen .dock-progress-label {
        color: #ffe588;
        font-size: .76rem;
        letter-spacing: .06em;
      }
      .battle-screen .dock-actions {
        display: flex;
        gap: 8px;
        align-items: center;
      }
      .battle-screen .dock-panels {
        min-height: 0;
        display: grid;
        grid-template-columns: minmax(0, 1.05fr) minmax(0, 1.35fr);
        gap: 10px;
        align-items: start;
      }
      .battle-screen .dock-panel {
        min-width: 0;
        min-height: 0;
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 14px;
        background: rgba(255,255,255,.04);
        padding: 10px;
        overflow: hidden;
      }
      .battle-screen .dock-panel.compact {
        display: grid;
        grid-template-rows: minmax(0, 1fr);
      }
      .battle-screen #commandFrame {
        align-items: start;
        overflow: visible;
        position: relative;
        z-index: 4;
      }
      .battle-screen #commandFrame.command-frame-expanded {
        box-shadow: 0 18px 40px rgba(0,0,0,.34);
      }
      .battle-screen .action-sheet-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(2, 6, 16, .56);
        opacity: 0;
        pointer-events: none;
        transition: opacity .18s ease-out;
        z-index: 20;
      }
      .battle-screen .action-sheet-backdrop.open {
        opacity: 1;
        pointer-events: auto;
      }
      .battle-screen .action-sheet {
        position: absolute;
        left: 0;
        right: 0;
        bottom: 0;
        margin: 0 auto;
        width: min(100%, 860px);
        padding: 14px 14px max(18px, env(safe-area-inset-bottom, 0px));
        border-radius: 22px 22px 0 0;
        border: 1px solid rgba(255,255,255,.18);
        background: linear-gradient(180deg, rgba(13, 21, 48, .98), rgba(7, 11, 24, .98));
        box-shadow: 0 -12px 40px rgba(0,0,0,.38);
        transform: translateY(calc(100% + 8px));
        transition: transform .22s ease-out;
        z-index: 21;
        display: grid;
        gap: 12px;
      }
      .battle-screen .action-sheet.open {
        transform: translateY(0);
      }
      .battle-screen .action-sheet-handle {
        width: 56px;
        height: 5px;
        margin: 0 auto;
        border-radius: 999px;
        background: rgba(255,255,255,.24);
      }
      .battle-screen .action-sheet-header {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
      }
      .battle-screen .action-sheet-title {
        color: #eef2ff;
        font-size: .95rem;
        font-weight: 700;
      }
      .battle-screen .action-sheet-body {
        display: grid;
        gap: 10px;
        max-height: min(48vh, 420px);
        overflow-y: auto;
        padding-right: 2px;
      }
      .battle-screen .action-sheet-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
      }
      .battle-screen .action-sheet-section {
        display: grid;
        gap: 8px;
      }
      .battle-screen .action-sheet-section-label {
        color: #ffe588;
        font-size: .8rem;
        font-weight: 700;
      }
      .battle-screen .card {
        border: 1px solid rgba(255,255,255,.22);
        border-radius: 12px;
        padding: 8px;
        background: rgba(0,0,0,.25);
      }
      .battle-screen .card.active {
        border-color: #ffe588;
        box-shadow: 0 0 0 2px rgba(255,229,136,.26) inset;
      }
      .battle-screen .card.target { cursor: pointer; }
      .battle-screen .card.selected { border-color: #ffe588; }
      .battle-screen .party-card,
      .battle-screen .enemy-card {
        position: relative;
        overflow: hidden;
        min-height: 112px;
        isolation: isolate;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
      }
      .battle-screen .party-card {
        min-height: 82px;
        padding: 7px;
      }
      .battle-screen .party-card::after,
      .battle-screen .enemy-card::after {
        content: "";
        position: absolute;
        inset: 0;
        z-index: 1;
        pointer-events: none;
        background: linear-gradient(180deg, rgba(3,6,19,0.46), rgba(3,6,19,0.78));
      }
      .battle-screen .party-face,
      .battle-screen .enemy-sprite {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        opacity: .9;
        filter: brightness(.55) saturate(.95);
        z-index: 0;
      }
      .battle-screen .party-face { object-fit: cover; object-position: center 22%; }
      .battle-screen .enemy-sprite { object-fit: contain; object-position: center; }
      .battle-screen .party-face-fallback,
      .battle-screen .enemy-sprite-fallback {
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        background: rgba(4,8,24,.78);
        color: #acb6d7;
        font-size: .7rem;
        z-index: 0;
      }
      .battle-screen .party-card-content,
      .battle-screen .enemy-card-content {
        position: relative;
        z-index: 2;
        text-shadow: 0 1px 4px rgba(0,0,0,.82);
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .battle-screen .party-name-row { order: 1; }
      .battle-screen .party-hp-row { order: 2; }
      .battle-screen .party-hp-bar-row { order: 3; }
      .battle-screen .party-level-row { order: 4; }
      .battle-screen .party-status-icons-row { order: 5; min-height: 12px; }
      .battle-screen .name { font-weight: 700; font-size: .82rem; }
      .battle-screen .hp { font-size: .76rem; color: #89f0ac; }
      .battle-screen .party-card .name {
        font-size: .74rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .battle-screen .party-card .hp {
        font-size: .68rem;
        color: #d6e6ff;
      }
      .battle-screen .party-card .status {
        font-size: .64rem;
      }
      .battle-screen .party-hp-bar-row {
        display: grid;
        gap: 4px;
      }
      .battle-screen .hp-bar {
        width: 100%;
        height: 7px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(255,255,255,.14);
        box-shadow: inset 0 1px 2px rgba(0,0,0,.35);
      }
      .battle-screen .hp-bar-fill {
        height: 100%;
        width: var(--hp-ratio, 0%);
        border-radius: inherit;
        background: linear-gradient(90deg, #48d77d 0%, #8ff0ab 100%);
        transition: width .18s ease-out, background .18s ease-out;
      }
      .battle-screen .hp-bar-fill.is-caution {
        background: linear-gradient(90deg, #e7bf41 0%, #f3de7d 100%);
      }
      .battle-screen .hp-bar-fill.is-danger {
        background: linear-gradient(90deg, #df5b5b 0%, #ff9e9e 100%);
      }
      .battle-screen .party-card .party-level-row {
        display: none;
      }
      .battle-screen .party-card .party-status-icons-row {
        min-height: 10px;
      }
      .battle-screen .combat-popup-layer { position:absolute; inset:0; z-index:3; pointer-events:none; }
      .battle-screen .combat-popup { position:absolute; left:50%; top:44%; transform:translate(-50%,-50%); font-weight:700; font-size:1.3rem; color:#ffb3b3; text-shadow:0 2px 6px rgba(0,0,0,.9); letter-spacing:.03em; animation:combat-popup-rise .45s ease-out both; }
      .battle-screen .combat-popup.heal { color:#9ff7ba; }
      .battle-screen .combat-popup.miss { color:#ffe588; font-size:1rem; }
      .battle-screen .combat-popup.status {
        top: 26%;
        font-size: .86rem;
        color: #8bd8ff;
        background: rgba(6, 17, 35, .72);
        border: 1px solid rgba(139, 216, 255, .42);
        border-radius: 999px;
        padding: 4px 8px;
        white-space: nowrap;
      }
      .battle-screen .combat-popup.status.cure {
        color: #aef7b9;
        border-color: rgba(174, 247, 185, .42);
      }
      .battle-screen .combat-effect-layer { position:absolute; inset:0; z-index:3; pointer-events:none; overflow:hidden; }
      .battle-screen .combat-slash { position:absolute; width:41px; height:44px; left:0; top:0; background-image:var(--slash-image); background-repeat:no-repeat; background-size:82px 44px; image-rendering:auto; mix-blend-mode:screen; opacity:0; transform:translate(var(--slash-start-x, 0px), var(--slash-start-y, 0px)); animation:combat-slash-sweep .22s steps(2) both; }
      .battle-screen .command-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
        align-content: start;
        min-width: 0;
        width: 100%;
      }
      .battle-screen .command-grid.command-mode { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      .battle-screen #commandFrame.command-frame-expanded .command-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
        max-height: min(42vh, 340px);
        overflow-y: auto;
        padding-right: 2px;
      }
      .battle-screen .command-grid > .btn,
      .battle-screen .command-grid > .magic-group-row > .magic-group-spells > .btn {
        width: 100%;
        min-width: 0;
        max-width: 100%;
        box-sizing: border-box;
      }
      .battle-screen .command-grid > .btn {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .battle-screen .magic-group-header { padding:2px 6px 2px 2px; color:#ffe588; font-size:.84rem; font-weight:700; white-space:nowrap; }
      .battle-screen .magic-group-row { grid-column:1/-1; display:flex; align-items:center; gap:8px; }
      .battle-screen .magic-group-spells { display:flex; gap:8px; flex-wrap:nowrap; overflow-x:auto; min-width:0; }
      .battle-screen #commandFrame.command-frame-expanded .magic-group-row {
        flex-direction: column;
        align-items: stretch;
      }
      .battle-screen #commandFrame.command-frame-expanded .magic-group-header {
        padding: 0;
      }
      .battle-screen #commandFrame.command-frame-expanded .magic-group-spells {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        overflow: visible;
      }
      .battle-screen pre {
        margin: 0;
        border: 1px solid rgba(255,255,255,.16);
        border-radius: 12px;
        background: #0b1229;
        max-height: 100%;
        overflow: auto;
        white-space: pre-wrap;
        padding: 8px;
        line-height: 1.45;
      }
      .battle-screen .reward { border:1px solid rgba(255,229,136,.5); background:rgba(255,229,136,.09); border-radius:12px; padding:8px; display:none; }
      .battle-screen .reward.open { display:block; }
      .battle-screen .mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
      .battle-screen .log-frame {
        display: none;
        margin-top: 8px;
        overflow: hidden;
      }
      .battle-screen .log-frame.open {
        display: block;
      }
      .battle-screen .log-frame-header {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
        padding: 12px 12px 0;
      }
      .battle-screen .log-frame-body {
        padding: 12px;
      }
      .battle-screen .log-frame.is-clickable-next .log-frame-body::after {
        content: "タップで次へ";
        display: block;
        margin-top: 8px;
        color: #ffe588;
        font-size: .76rem;
        text-align: right;
      }
      @keyframes combat-popup-rise { from { opacity:0; transform:translate(-50%,-20%); } to { opacity:1; transform:translate(-50%,-60%); } }
      @keyframes combat-slash-sweep {
        0% { opacity:0; background-position:0 0; transform:translate(var(--slash-start-x, 0px), var(--slash-start-y, 0px)); }
        20% { opacity:1; }
        100% { opacity:0; background-position:-82px 0; transform:translate(var(--slash-end-x, 0px), var(--slash-end-y, 0px)); }
      }
      @media (max-width: 720px) {
        .battle-screen {
          --battle-gutter: 8px;
          --dock-height: 37vh;
          grid-template-rows: minmax(0, 1fr) minmax(248px, var(--dock-height));
        }
        .battle-screen .battle-stage-header {
          align-items: stretch;
          flex-direction: column;
        }
        .battle-screen .toolbar {
          justify-content: flex-start;
        }
        .battle-screen .enemy-grid {
          width: min(100%, 300px);
          grid-template-columns: repeat(2, minmax(0, 144px));
          grid-template-rows: repeat(2, minmax(0, 1fr));
          grid-auto-flow: column;
          justify-items: stretch;
        }
        .battle-screen .enemy-grid[data-count="1"] {
          width: min(100%, 180px);
          grid-template-columns: minmax(0, 1fr);
          grid-template-rows: minmax(0, 1fr);
        }
        .battle-screen .enemy-grid[data-count="2"] {
          width: min(100%, 172px);
          grid-template-columns: minmax(0, 1fr);
          grid-template-rows: repeat(2, minmax(0, 1fr));
        }
        .battle-screen .enemy-grid[data-count="3"],
        .battle-screen .enemy-grid[data-count="4"] {
          width: min(100%, 300px);
          grid-template-columns: repeat(2, minmax(0, 144px));
          grid-template-rows: repeat(2, minmax(0, 1fr));
        }
        .battle-screen .enemy-grid[data-count="5"],
        .battle-screen .enemy-grid[data-count="6"] {
          width: min(100%, 300px);
          grid-template-columns: repeat(3, minmax(0, 96px));
          grid-template-rows: repeat(2, minmax(0, 1fr));
          gap: 6px;
        }
        .battle-screen .enemy-grid[data-count="3"] .enemy-card,
        .battle-screen .enemy-grid[data-count="4"] .enemy-card {
          min-height: 100px;
        }
        .battle-screen .enemy-grid[data-count="5"] .enemy-card,
        .battle-screen .enemy-grid[data-count="6"] .enemy-card {
          min-height: 84px;
          padding: 5px;
        }
        .battle-screen .enemy-grid[data-count="5"] .enemy-card .name,
        .battle-screen .enemy-grid[data-count="6"] .enemy-card .name {
          font-size: .7rem;
          line-height: 1.2;
        }
        .battle-screen .enemy-grid[data-count="5"] .enemy-card .hp,
        .battle-screen .enemy-grid[data-count="6"] .enemy-card .hp {
          display: none;
        }
        .battle-screen .dock-panels {
          grid-template-columns: minmax(0, 1fr);
          grid-template-rows: auto minmax(0, 1fr);
        }
        .battle-screen .party-grid {
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 6px;
        }
        .battle-screen .command-grid.command-mode {
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .battle-screen .action-sheet {
          width: 100%;
          padding: 12px 12px max(16px, env(safe-area-inset-bottom, 0px));
        }
        .battle-screen #commandFrame.command-frame-expanded .command-grid,
        .battle-screen #commandFrame.command-frame-expanded .magic-group-spells {
          grid-template-columns: minmax(0, 1fr);
          max-height: min(38vh, 300px);
        }
        .battle-screen .action-sheet-grid {
          grid-template-columns: minmax(0, 1fr);
        }
      }
      @media (max-width: 420px) {
        .battle-screen .battle-dock {
          padding: 10px;
        }
        .battle-screen .btn {
          padding: 10px;
          font-size: .9rem;
        }
        .battle-screen .enemy-grid {
          gap: 8px;
        }
        .battle-screen .enemy-grid[data-count="5"],
        .battle-screen .enemy-grid[data-count="6"] {
          width: min(100%, 258px);
          grid-template-columns: repeat(3, minmax(0, 82px));
          gap: 5px;
        }
        .battle-screen .party-card,
        .battle-screen .enemy-card {
          min-height: 96px;
        }
        .battle-screen .party-card {
          min-height: 76px;
          padding: 6px;
        }
        .battle-screen .party-card .name {
          font-size: .68rem;
        }
        .battle-screen .party-card .hp {
          font-size: .62rem;
        }
        .battle-screen .hp-bar {
          height: 6px;
        }
        .battle-screen .enemy-grid[data-count="5"] .enemy-card,
        .battle-screen .enemy-grid[data-count="6"] .enemy-card {
          min-height: 78px;
        }
      }
    </style>
    <div class="battle-screen">
      <section class="battle-stage">
        <section class="frame battle-stage-header">
          <div class="battle-stage-heading">
            <span id="battlePhase" class="status">起動中...</span>
          </div>
          <div class="toolbar">
            <button id="locationBtn" class="btn" type="button">Location選択</button>
            <button id="menuBtn" class="btn" type="button">メニュー</button>
            <button id="loadSaveBtn" class="btn" type="button">ロード</button>
            <input id="loadSaveInput" type="file" accept="application/json,.json" style="display:none;" />
          </div>
        </section>
        <section class="frame battle-stage-panel" id="enemyFrame">
          <div class="enemy-stage-head">
            <div class="enemy-stage-caption">対象選択と戦闘演出のメイン領域</div>
          </div>
          <div class="enemy-stage-body">
            <div id="enemyGrid" class="enemy-grid"></div>
          </div>
        </section>
      </section>
      <section class="frame battle-dock">
        <div class="dock-topbar">
          <div class="dock-progress">
            <div class="dock-progress-label">COMMAND DOCK</div>
            <div id="statusLine" class="status">エンジン起動中です...</div>
          </div>
          <div class="dock-actions">
            <button id="battleLogToggleBtn" class="btn" type="button">ログを開く</button>
          </div>
        </div>
        <div class="dock-panels">
          <section class="dock-panel compact">
            <div id="partyGrid" class="party-grid party-hud"></div>
          </section>
          <section id="commandFrame" class="dock-panel compact">
            <div id="commandGrid" class="command-grid"></div>
          </section>
        </div>
      </section>
      <section id="battleLogFrame" class="frame log-frame">
        <div class="log-frame-header">
          <div class="enemy-stage-caption">戦闘ログ</div>
          <button id="downloadSaveBtn" class="btn" type="button">保存</button>
        </div>
        <div class="log-frame-body">
          <pre id="logView">(not executed)</pre>
          <div id="rewardPanel" class="reward" style="margin-top:10px;"></div>
        </div>
      </section>
      <div id="actionSheetBackdrop" class="action-sheet-backdrop"></div>
      <section id="actionSheet" class="action-sheet" aria-hidden="true">
        <div class="action-sheet-handle"></div>
        <div class="action-sheet-header">
          <div id="actionSheetTitle" class="action-sheet-title">選択</div>
          <button id="actionSheetCloseBtn" class="btn" type="button">閉じる</button>
        </div>
        <div id="actionSheetBody" class="action-sheet-body"></div>
      </section>
    </div>
  `;
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();
  await initializeBattleApp({ root: mountNode, store, navigate });
  return () => {};
}
