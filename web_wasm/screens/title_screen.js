import { getPyodideRuntime } from "../pyodide_runtime.js";
import {
  AUTO_SAVE_SLOT_ID,
  listSaveSlotsFromIndexedDB,
  loadSaveEnvelopeFromIndexedDB,
} from "../shared_storage.js";
import {
  MANUAL_SAVE_SLOT_IDS,
  createNewGameSaveData,
  hydrateEnvelopeWithRuntime,
  persistAutoSave,
} from "../title_screen_state.js";

const TITLE_THEME_URL = new URL("../../assets/images/ffiii_theme.jpg", import.meta.url).href;

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
          background-image:
            linear-gradient(135deg, rgba(7, 10, 26, 0.22), rgba(7, 10, 26, 0.74)),
            linear-gradient(180deg, rgba(8, 12, 30, 0.02), rgba(8, 12, 30, 0.52)),
            url("${TITLE_THEME_URL}");
          background-size: 100% auto;
          background-position: center top;
          background-repeat: no-repeat;
        }
        .title-hero-frame::before {
          content: "";
          position: absolute;
          inset: 0;
          background:
            radial-gradient(circle at top right, rgba(255, 229, 136, 0.18), transparent 36%),
            linear-gradient(180deg, rgba(12, 18, 44, 0.12), rgba(12, 18, 44, 0.6));
          pointer-events: none;
        }
        .title-hero-content {
          position: relative;
          z-index: 1;
          text-shadow: 0 2px 10px rgba(0, 0, 0, 0.72);
        }
        .title-bottom-panel {
          position: relative;
          z-index: 1;
          display: grid;
          gap: 10px;
          margin-top: auto;
          padding: 12px;
          border: 1px solid rgba(255, 255, 255, 0.28);
          border-radius: 10px;
          background: linear-gradient(180deg, rgba(9, 13, 31, 0.48), rgba(9, 13, 31, 0.78));
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        }
        .title-menu-list {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
        }
        .title-menu-btn {
          display: block;
          padding: 8px 12px;
          text-align: center;
          background: linear-gradient(180deg, rgba(68, 89, 191, 0.9), rgba(32, 49, 126, 0.88));
          backdrop-filter: blur(2px);
        }
        .title-menu-btn-label {
          font-size: 0.88rem;
          font-weight: 700;
          line-height: 1.2;
        }
        @media (max-width: 420px) {
          .title-menu-list {
            grid-template-columns: 1fr;
          }
        }
      </style>
      <section class="frame title-hero-frame">
        <div class="title-hero-content" style="display:grid; gap:14px;">
          <div>
            <div style="color:#acb6d7; letter-spacing:.22em; font-size:.8rem;">BATTLE WASM RUNNER</div>
            <h1 style="margin:6px 0 0; color:#ffe588; font-size:2rem; line-height:1.15;">FINAL FANTASY III<br>Title Screen</h1>
          </div>
          <div style="height:1px; background:linear-gradient(90deg, rgba(255,229,136,.9), rgba(255,229,136,0));"></div>
        </div>
        <div class="title-bottom-panel">
          <div id="titleStatus" class="status" style="margin-bottom:0;">開始メニューを選択してください。</div>
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
      label: "ニューゲーム",
      description: "全員 Lv1 / Onion Knight / Gil 0 / CP 0 / アイテムなし で開始",
      disabled: false,
    },
    {
      id: "continue",
      label: "コンテニュー",
      description: "前回の AUTO SAVE から再開",
      disabled: !slotInfo.auto,
    },
    {
      id: "load",
      label: "ロード",
      description: "3 つのセーブスロットから選んで再開",
      disabled: false,
    },
    {
      id: "config",
      label: "コンフィグ",
      description: "今後実装予定",
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
  store.updateSaveEnvelope(hydratedEnvelope);
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
  const loadPanel = mountNode.querySelector("#loadPanel");
  const closeLoadBtn = mountNode.querySelector("#closeLoadBtn");
  const loadSlotList = mountNode.querySelector("#loadSlotList");

  const slots = await listSaveSlotsFromIndexedDB();
  const autoSlot = slots.find((row) => row.slot_id === AUTO_SAVE_SLOT_ID) || null;

  const openLoadPanel = () => {
    loadPanel.style.display = "";
    renderLoadSlots(loadSlotList, slots, async (slotId) => {
      const envelope = await loadSaveEnvelopeFromIndexedDB(slotId);
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
        const envelope = await loadSaveEnvelopeFromIndexedDB(AUTO_SAVE_SLOT_ID);
        if (!envelope?.save) {
          titleStatus.textContent = "AUTO SAVE の読み込みに失敗しました。";
          return;
        }
        await activateEnvelope({ store, navigate, statusLine: titleStatus, envelope });
      },
      load: () => {
        openLoadPanel();
      },
      config: () => {
        titleStatus.textContent = "コンフィグは今後実装予定です。";
      },
    },
    { auto: autoSlot },
  );

  closeLoadBtn.addEventListener("click", closeLoadPanel);

  return () => {
    closeLoadBtn.removeEventListener("click", closeLoadPanel);
  };
}
