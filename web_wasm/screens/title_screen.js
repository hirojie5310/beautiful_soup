import { getPyodideRuntime } from "../pyodide_runtime.js";
import { AUTO_SAVE_SLOT_ID } from "../shared_storage.js";
import { saveRepository } from "../save_repository.js";
import {
  MANUAL_SAVE_SLOT_IDS,
  createNewGameSaveData,
  hydrateEnvelopeWithRuntime,
  persistAutoSave,
} from "../title_screen_state.js";
import { loadTitleStoryLines } from "../title_story.js";

const TITLE_THEME_URL = new URL("../../assets/images/ffiii_theme.jpg", import.meta.url).href;
const TITLE_HERO_CYCLE_MS = 60000;

function renderLayout() {
  return `
    <div class="screen narrow" data-screen="title">
      <style>
        .title-hero-frame {
          position: relative;
          min-height: min(78vh, 760px);
          padding: 22px 18px 18px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          background: linear-gradient(180deg, rgba(248, 249, 255, 0.94), rgba(235, 239, 248, 0.98));
        }
        .title-hero-frame::before {
          content: "";
          position: absolute;
          inset: 0;
          background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0.1) 30%, rgba(246, 248, 255, 0.18) 72%, rgba(238, 242, 252, 0.42)),
            radial-gradient(circle at top center, rgba(255, 255, 255, 0.22), transparent 40%);
          pointer-events: none;
          z-index: 1;
        }
        .title-hero-frame::after {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.2) 68%, rgba(255, 255, 255, 0.92));
          animation: title-hero-fadewash ${TITLE_HERO_CYCLE_MS}ms ease-in-out infinite;
          pointer-events: none;
          z-index: 1;
        }
        .title-hero-background {
          position: absolute;
          inset: 0;
          background-image: url("${TITLE_THEME_URL}");
          background-size: 100% auto;
          background-position: center bottom;
          background-repeat: no-repeat;
          animation: title-hero-pan ${TITLE_HERO_CYCLE_MS}ms ease-in-out infinite;
          transform-origin: center center;
          pointer-events: none;
          z-index: 0;
        }
        .title-hero-content {
          position: relative;
          z-index: 2;
          color: rgba(18, 24, 46, 0.92);
          text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5);
        }
        .title-story-line {
          min-height: 6.4em;
          max-width: 32rem;
          padding: 4px 0;
          color: rgba(20, 25, 42, 0.96);
          font-size: 0.98rem;
          line-height: 1.8;
          letter-spacing: 0.03em;
          white-space: pre-wrap;
          text-shadow:
            0 1px 0 rgba(255, 255, 255, 0.42),
            0 0 10px rgba(255, 255, 255, 0.2);
        }
        .title-bottom-panel {
          position: relative;
          z-index: 2;
          display: grid;
          gap: 10px;
          margin-top: auto;
          padding: 12px;
          border: 1px solid rgba(255, 255, 255, 0.55);
          border-radius: 10px;
          background: linear-gradient(180deg, rgba(255, 255, 255, 0.46), rgba(231, 237, 250, 0.82));
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28);
        }
        .title-status-line {
          color: rgba(24, 30, 48, 0.96);
        }
        .title-menu-list {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          justify-content: center;
          gap: 8px;
        }
        .title-menu-btn {
          display: block;
          padding: 8px 8px;
          text-align: center;
          background: linear-gradient(180deg, rgba(68, 89, 191, 0.9), rgba(32, 49, 126, 0.88));
          backdrop-filter: blur(2px);
        }
        .title-menu-btn-label {
          font-size: 0.8rem;
          font-weight: 700;
          line-height: 1.2;
        }
        @keyframes title-hero-pan {
          0% {
            background-position: center bottom;
            opacity: 0.96;
            filter: brightness(1) saturate(1);
            transform: scale(1);
          }
          80% {
            background-position: center top;
            opacity: 0.96;
            filter: brightness(1.04) saturate(0.96);
            transform: scale(1.02);
          }
          100% {
            background-position: center top;
            opacity: 0.4;
            filter: brightness(1.22) saturate(0.72);
            transform: scale(1.02);
          }
        }
        @keyframes title-hero-fadewash {
          0% {
            opacity: 0;
          }
          82% {
            opacity: 0;
          }
          100% {
            opacity: 1;
          }
        }
        @media (max-width: 420px) {
          .title-menu-list {
            gap: 6px;
          }
          .title-menu-btn {
            padding: 7px 6px;
          }
          .title-menu-btn-label {
            font-size: 0.75rem;
          }
        }
        @media (max-width: 360px) {
          .title-menu-list {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
      </style>
      <section class="frame title-hero-frame">
        <div id="titleHeroBackground" class="title-hero-background" aria-hidden="true"></div>
        <div class="title-hero-content" style="display:grid; gap:14px;">
          <div>
            <div style="color:rgba(18,24,46,.78); letter-spacing:.22em; font-size:.8rem; font-weight:700;">BATTLE WASM RUNNER</div>
          </div>
          <div style="height:1px; background:linear-gradient(90deg, rgba(24,34,68,.72), rgba(24,34,68,0));"></div>
          <div id="titleStoryLine" class="title-story-line" aria-live="polite"></div>
        </div>
        <div class="title-bottom-panel">
          <div id="titleStatus" class="status title-status-line" style="margin-bottom:0;">開始メニューを選択してください。</div>
          <div id="menuList" class="title-menu-list"></div>
        </div>
      </section>

      <section id="loadPanel" class="frame" style="display:none;">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px;">
          <h2 class="title" style="margin:0;">LOAD</h2>
          <button id="closeLoadBtn" class="btn" type="button">閉じる</button>
        </div>
        <div id="loadSlotList" class="slot-list"></div>
      </section>
    </div>
  `;
}

function formatSavedAt(value) {
  if (!value) return "未保存";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderMenuButtons(menuList, handlers, slotInfo) {
  const definitions = [
    {
      id: "new-game",
      label: "はじめから",
      disabled: false,
    },
    {
      id: "continue",
      label: "つづきから",
      disabled: !slotInfo.auto,
    },
    {
      id: "load",
      label: "読込",
      disabled: false,
    },
  ];

  menuList.innerHTML = "";
  definitions.forEach((definition) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn title-menu-btn";
    button.disabled = definition.disabled;
    button.innerHTML = `<span class="title-menu-btn-label">${definition.label}</span>`;
    button.addEventListener("click", () => handlers[definition.id]?.());
    menuList.appendChild(button);
  });
}

function renderLoadSlots(loadSlotList, slots, onLoad) {
  loadSlotList.innerHTML = "";
  MANUAL_SAVE_SLOT_IDS.forEach((slotId, index) => {
    const summaryRow = slots.find((row) => row.slot_id === slotId);
    const summary = summaryRow?.summary && typeof summaryRow.summary === "object"
      ? summaryRow.summary
      : {};

    const card = document.createElement("article");
    card.className = "slot-card";

    const title = document.createElement("div");
    title.className = "slot-title";
    title.textContent = `Slot ${index + 1}`;

    const meta = document.createElement("div");
    meta.className = "slot-meta";
    meta.innerHTML = summaryRow
      ? [
        `保存日時: ${formatSavedAt(summaryRow.saved_at)}`,
        `先頭: ${String(summary.lead_name || "-")} Lv ${Number(summary.lead_level || 0)}`,
        `GIL: ${Number(summary.gil || 0)} / 場所: ${String(summary.location_group || summary.location || "-")}`,
      ].join("<br>")
      : "このスロットは空です。";

    const action = document.createElement("div");
    action.className = "slot-actions";
    const loadBtn = document.createElement("button");
    loadBtn.className = "btn";
    loadBtn.type = "button";
    loadBtn.textContent = "このデータを再開";
    loadBtn.disabled = !summaryRow;
    loadBtn.addEventListener("click", () => onLoad(slotId));
    action.appendChild(loadBtn);

    card.append(title, meta, action);
    loadSlotList.appendChild(card);
  });
}

async function activateEnvelope({ store, navigate, statusLine, envelope, autosave = false }) {
  statusLine.textContent = "ゲームデータを準備しています...";
  const pyodide = await getPyodideRuntime();
  const hydratedEnvelope = await hydrateEnvelopeWithRuntime(pyodide, envelope);
  store.updateMenuState(hydratedEnvelope.menu_state || {});
  store.updateSaveEnvelope(hydratedEnvelope, { reason: "session_restored" });
  if (autosave) {
    await persistAutoSave(hydratedEnvelope);
  }
  statusLine.textContent = "準備が完了しました。";
  navigate("location");
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const titleStatus = mountNode.querySelector("#titleStatus");
  const menuList = mountNode.querySelector("#menuList");
  const titleHeroBackground = mountNode.querySelector("#titleHeroBackground");
  const titleStoryLine = mountNode.querySelector("#titleStoryLine");
  const loadPanel = mountNode.querySelector("#loadPanel");
  const closeLoadBtn = mountNode.querySelector("#closeLoadBtn");
  const loadSlotList = mountNode.querySelector("#loadSlotList");

  let storyIntervalId = 0;
  let storyCycleResetHandler = null;

  const stopStoryLoop = () => {
    if (storyIntervalId) {
      window.clearInterval(storyIntervalId);
      storyIntervalId = 0;
    }
  };

  const startStoryLoop = async () => {
    try {
      const lines = await loadTitleStoryLines();
      if (!titleStoryLine || lines.length === 0) {
        if (titleStoryLine) titleStoryLine.textContent = "";
        return;
      }
      let lineIndex = 0;
      const stepMs = Math.max(1000, Math.floor(TITLE_HERO_CYCLE_MS / lines.length));
      const renderCurrentLine = () => {
        titleStoryLine.textContent = lines[lineIndex] || "";
      };
      const restartStoryCycle = () => {
        stopStoryLoop();
        lineIndex = 0;
        renderCurrentLine();
        if (lines.length <= 1) return;
        storyIntervalId = window.setInterval(() => {
          if (lineIndex >= lines.length - 1) return;
          lineIndex += 1;
          renderCurrentLine();
        }, stepMs);
      };
      restartStoryCycle();
      if (titleHeroBackground) {
        storyCycleResetHandler = () => {
          restartStoryCycle();
        };
        titleHeroBackground.addEventListener("animationiteration", storyCycleResetHandler);
      }
    } catch (_error) {
      if (titleStoryLine) titleStoryLine.textContent = "";
    }
  };

  const slots = await saveRepository.listSlots();
  const autoSlot = slots.find((row) => row.slot_id === AUTO_SAVE_SLOT_ID) || null;

  const openLoadPanel = () => {
    loadPanel.style.display = "";
    renderLoadSlots(loadSlotList, slots, async (slotId) => {
      const envelope = await saveRepository.loadSlot(slotId);
      if (!envelope?.save) {
        titleStatus.textContent = "ロードに失敗しました。";
        return;
      }
      await activateEnvelope({ store, navigate, statusLine: titleStatus, envelope });
    });
    titleStatus.textContent = "再開したいセーブスロットを選択してください。";
  };

  const closeLoadPanel = () => {
    loadPanel.style.display = "none";
    titleStatus.textContent = "開始メニューを選択してください。";
  };

  renderMenuButtons(
    menuList,
    {
      "new-game": async () => {
        const hasExistingProgress = Boolean(store.getState().saveEnvelope?.save || autoSlot);
        if (hasExistingProgress && !window.confirm("現在の進行中データを新しいゲームで上書きします。続けますか？")) {
          return;
        }
        const envelope = {
          version: 1,
          saved_at: new Date().toISOString(),
          selected_location_group: "",
          selected_location: "",
          save: createNewGameSaveData(),
          menu_state: null,
        };
        await activateEnvelope({
          store,
          navigate,
          statusLine: titleStatus,
          envelope,
          autosave: true,
        });
      },
      continue: async () => {
        if (!autoSlot) {
          titleStatus.textContent = "AUTO SAVE が見つかりません。";
          return;
        }
        const envelope = await saveRepository.loadSlot(AUTO_SAVE_SLOT_ID);
        if (!envelope?.save) {
          titleStatus.textContent = "AUTO SAVE の読み込みに失敗しました。";
          return;
        }
        await activateEnvelope({ store, navigate, statusLine: titleStatus, envelope });
      },
      load: () => {
        openLoadPanel();
      },
    },
    { auto: autoSlot },
  );

  closeLoadBtn.addEventListener("click", closeLoadPanel);
  await startStoryLoop();

  return () => {
    stopStoryLoop();
    if (titleHeroBackground && storyCycleResetHandler) {
      titleHeroBackground.removeEventListener("animationiteration", storyCycleResetHandler);
    }
    closeLoadBtn.removeEventListener("click", closeLoadPanel);
  };
}
