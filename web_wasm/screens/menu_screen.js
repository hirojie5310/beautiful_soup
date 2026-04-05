import {
  normalizePartyIdentityOrder,
  resolveFaceImageCandidates,
  resolveMemberJob,
} from "../shared_party.js";
import {
  LOCAL_MENU_STORAGE_KEY,
  makeSaveEnvelope,
  parseSaveEnvelope,
  restoreSaveEnvelopeFromStorage,
} from "../shared_storage.js";
import { bindButtonHandlers } from "./screen_shared.js";

const MENU_LABELS = ["アイテム", "まほう", "そうび", "ステータス", "ならびかえ", "ジョブ", "セーブ", "ロード"];
const MENU_ROUTE_BY_LABEL = {
  アイテム: "item",
  まほう: "magic",
  そうび: "equip",
  ステータス: "status",
  ジョブ: "job",
};

function renderLayout() {
  return `
    <div class="screen narrow" data-screen="menu">
      <section class="frame">
        <div class="toolbar">
          <h1 class="title" style="margin:0;">MENU</h1>
          <button id="backBtn" class="btn" type="button">Location選択へ戻る</button>
        </div>
      </section>

      <section class="frame">
        <h2 class="title">PARTY</h2>
        <div id="partyList" class="party-list"></div>
      </section>

      <section class="frame">
        <div id="menuButtons" class="menu-buttons"></div>
        <input id="menuLoadSaveInput" type="file" accept="application/json,.json" style="display:none;" />
        <div id="modeHint" class="mode-hint" aria-live="polite"></div>
      </section>

      <section class="frame">
        <div id="resourceRow" class="resource-row"></div>
      </section>
    </div>
  `;
}

function normalizeRow(rowValue) {
  return String(rowValue || "").toLowerCase() === "back" ? "back" : "front";
}

function toggleMemberRow(member) {
  return normalizeRow(member?.row) === "front" ? "back" : "front";
}

function levelMpText(member) {
  const mpLevels = member?.mp_levels && typeof member.mp_levels === "object" ? member.mp_levels : {};
  const chunks = [];
  for (let lv = 1; lv <= 8; lv += 1) {
    const row = mpLevels[String(lv)] || {};
    chunks.push(`${Number(row?.current ?? 0)}`);
  }
  return chunks.join("/");
}

function normalizeMenuState(raw) {
  const parsed = raw && typeof raw === "object" ? raw : {};
  const party = Array.isArray(parsed.party) ? parsed.party : [];
  const resources = parsed.resources && typeof parsed.resources === "object" ? parsed.resources : {};
  return {
    ...parsed,
    party: normalizePartyIdentityOrder(party).map((member, index) => ({
      ...member,
      index,
      row: normalizeRow(member?.row),
      job: resolveMemberJob(member, member),
      hp: Number(member?.hp ?? 0),
      max_hp: Number(member?.max_hp ?? 0),
      level: Number(member?.level ?? 0),
      mp_levels: member?.mp_levels && typeof member.mp_levels === "object" ? member.mp_levels : {},
    })),
    resources: {
      cp: Number(resources.cp ?? 0),
      cp_max: Number(resources.cp_max ?? 255),
      gil: Number(resources.gil ?? 0),
    },
  };
}

function extractMenuStateFromEnvelope(envelope) {
  if (envelope?.menu_state && typeof envelope.menu_state === "object") {
    return normalizeMenuState(envelope.menu_state);
  }
  const saveParty = Array.isArray(envelope?.save?.party) ? envelope.save.party : [];
  return normalizeMenuState({
    party: saveParty.map((entry, index) => ({
      index,
      name: String(entry?.name || "Unknown"),
      portrait_key: entry?.portrait_key ?? entry?.image_name ?? null,
      image_name: entry?.image_name ?? null,
      job: String(entry?.current_job || entry?.job || "Unknown"),
      level: Number(entry?.level ?? 0),
      row: normalizeRow(entry?.row),
      hp: Number(entry?.hp ?? 0),
      max_hp: Number(entry?.max_hp ?? 0),
      mp_levels: entry?.mp_levels && typeof entry.mp_levels === "object" ? entry.mp_levels : {},
      status: {},
      status_icons: [],
      equipment: entry?.equipment && typeof entry.equipment === "object" ? entry.equipment : {},
    })),
    resources: {
      cp: Number(envelope?.save?.CP ?? 0),
      cp_max: 255,
      gil: Number(envelope?.save?.gil ?? 0),
    },
  });
}

function patchSaveWithMenuState(saveObj, menuState) {
  const nextSave = saveObj && typeof saveObj === "object" ? { ...saveObj } : {};
  nextSave.party = Array.isArray(menuState?.party)
    ? menuState.party.map((member) => ({
      ...(member && typeof member === "object" ? member : {}),
      row: normalizeRow(member?.row),
      hp: Number(member?.hp ?? 0),
      max_hp: Number(member?.max_hp ?? 0),
    }))
    : [];
  nextSave.CP = Number(menuState?.resources?.cp ?? nextSave?.CP ?? 0);
  nextSave.gil = Number(menuState?.resources?.gil ?? nextSave?.gil ?? 0);
  return nextSave;
}

async function saveEnvelopeToLocalFile(envelope) {
  const payload = JSON.stringify(envelope, null, 2);
  const fileName = `ffiii_savedata_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  if (window.showSaveFilePicker) {
    const handle = await window.showSaveFilePicker({
      suggestedName: fileName,
      types: [{ description: "JSON save data", accept: { "application/json": [".json"] } }],
    });
    const writable = await handle.createWritable();
    await writable.write(payload);
    await writable.close();
    return true;
  }
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

async function pickSaveFileText(input) {
  if (window.showOpenFilePicker) {
    const [handle] = await window.showOpenFilePicker({
      multiple: false,
      types: [{ description: "JSON save data", accept: { "application/json": [".json"] } }],
      excludeAcceptAllOption: false,
    });
    if (!handle) return "";
    const file = await handle.getFile();
    return file.text();
  }
  return new Promise((resolve, reject) => {
    const onChange = async (event) => {
      input.removeEventListener("change", onChange);
      const file = event?.target?.files?.[0];
      if (!file) {
        reject(new Error("file not selected"));
        return;
      }
      try {
        resolve(await file.text());
      } catch (error) {
        reject(error);
      }
    };
    input.value = "";
    input.addEventListener("change", onChange, { once: true });
    input.click();
  });
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const partyList = mountNode.querySelector("#partyList");
  const menuButtons = mountNode.querySelector("#menuButtons");
  const resourceRow = mountNode.querySelector("#resourceRow");
  const backBtn = mountNode.querySelector("#backBtn");
  const modeHint = mountNode.querySelector("#modeHint");
  const menuLoadSaveInput = mountNode.querySelector("#menuLoadSaveInput");

  let isRowSwapMode = false;
  let state = normalizeMenuState(store.getState().menuState);

  if (!Array.isArray(state.party) || !state.party.length) {
    const stored = restoreSaveEnvelopeFromStorage();
    if (stored?.save) {
      state = extractMenuStateFromEnvelope(stored);
      store.updateMenuState(state);
      store.updateSaveEnvelope({
        ...stored,
        menu_state: state,
      });
    }
  }

  function persistMenuState(nextState) {
    state = normalizeMenuState(nextState);
    store.updateMenuState(state);
    const currentEnvelope = store.getState().saveEnvelope || restoreSaveEnvelopeFromStorage();
    if (!currentEnvelope?.save || typeof currentEnvelope.save !== "object") return true;
    return store.updateSaveEnvelope({
      ...currentEnvelope,
      save: patchSaveWithMenuState(currentEnvelope.save, state),
      menu_state: state,
      saved_at: new Date().toISOString(),
    });
  }

  function updateModeHint() {
    if (isRowSwapMode) {
      modeHint.textContent = "ならびかえモード: キャラクターをクリックで front/back を切り替え";
      modeHint.classList.add("active");
      return;
    }
    modeHint.textContent = "";
    modeHint.classList.remove("active");
  }

  function renderParty() {
    partyList.innerHTML = "";
    if (!state.party.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "表示できるパーティ情報がありません。バトル画面を起動後にメニューを開いてください。";
      partyList.appendChild(empty);
      return;
    }

    state.party.forEach((member, index) => {
      const card = document.createElement("article");
      card.className = "member-card";
      if (isRowSwapMode) {
        card.classList.add("row-mode");
        card.tabIndex = 0;
        const handleToggle = () => {
          const nextParty = state.party.map((entry, entryIndex) => (
            entryIndex === index ? { ...entry, row: toggleMemberRow(entry) } : entry
          ));
          persistMenuState({ ...state, party: nextParty });
          renderParty();
        };
        card.addEventListener("click", handleToggle);
        card.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          handleToggle();
        });
      }

      const fallback = document.createElement("div");
      fallback.className = "portrait-fallback";
      fallback.textContent = "NO PORTRAIT";
      const imageCandidates = resolveFaceImageCandidates(member);
      if (imageCandidates.length) {
        const img = document.createElement("img");
        img.className = "portrait";
        img.alt = "";
        let imageIndex = 0;
        img.addEventListener("load", () => fallback.remove());
        img.addEventListener("error", () => {
          imageIndex += 1;
          if (imageIndex < imageCandidates.length) {
            img.src = imageCandidates[imageIndex];
            return;
          }
          img.remove();
          if (!card.contains(fallback)) card.insertBefore(fallback, card.firstChild);
        });
        img.src = imageCandidates[imageIndex];
        card.appendChild(img);
      } else {
        card.appendChild(fallback);
      }

      const main = document.createElement("div");
      main.className = "member-main";
      main.innerHTML = `
        <div class="line-strong">${String(member?.name || "Unknown")}</div>
        <div class="muted">Job: ${String(member?.job || "Unknown")} / Lv ${Number(member?.level ?? 0)}</div>
        <div class="muted">row: ${String(member?.row || "front")}</div>
        <div class="hp">HP ${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}</div>
        <div class="mp">MP(1-8): ${levelMpText(member)}</div>
      `;
      card.appendChild(main);
      partyList.appendChild(card);
    });
  }

  function renderResources() {
    resourceRow.innerHTML = "";
    const cp = document.createElement("div");
    cp.textContent = `CP ${Number(state.resources?.cp ?? 0)}/${Number(state.resources?.cp_max ?? 255)}`;
    const gil = document.createElement("div");
    gil.textContent = `GIL ${Number(state.resources?.gil ?? 0)}`;
    resourceRow.append(cp, gil);
  }

  function renderButtons() {
    menuButtons.innerHTML = "";
    MENU_LABELS.forEach((label) => {
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", async () => {
        if (label === "ならびかえ") {
          isRowSwapMode = !isRowSwapMode;
          updateModeHint();
          renderParty();
          return;
        }
        isRowSwapMode = false;
        updateModeHint();
        renderParty();

        if (label === "セーブ") {
          persistMenuState(state);
          const currentState = store.getState();
          const currentEnvelope = currentState.saveEnvelope || makeSaveEnvelope({}, {});
          const nextEnvelope = {
            ...currentEnvelope,
            save: patchSaveWithMenuState(currentEnvelope.save || {}, state),
            menu_state: state,
            selected_location_group: currentState.selectedLocationGroup,
            selected_location: currentState.selectedLocation,
            saved_at: new Date().toISOString(),
          };
          if (!store.updateSaveEnvelope(nextEnvelope)) {
            window.alert("セーブ失敗: ブラウザ保存に失敗しました。");
            return;
          }
          try {
            await saveEnvelopeToLocalFile(nextEnvelope);
            window.alert("セーブ完了: ブラウザとローカルファイルに保存しました。");
          } catch (_error) {
            window.alert("ブラウザ保存は完了しました。ローカルファイル保存はキャンセルまたは失敗しました。");
          }
          return;
        }

        if (label === "ロード") {
          try {
            const text = await pickSaveFileText(menuLoadSaveInput);
            const envelope = parseSaveEnvelope(JSON.parse(text));
            if (!envelope?.save) {
              window.alert("ロード失敗: セーブデータ形式が不正です。");
              return;
            }
            const loadedMenuState = extractMenuStateFromEnvelope(envelope);
            persistMenuState(loadedMenuState);
            store.updateSaveEnvelope({ ...envelope, menu_state: loadedMenuState });
            renderParty();
            renderResources();
            window.alert("ロード完了: セーブデータを復元しました。");
          } catch (_error) {
            window.alert("ロード失敗: ファイル選択がキャンセルされたか、読み込みに失敗しました。");
          }
          return;
        }

        const routeName = MENU_ROUTE_BY_LABEL[label];
        if (routeName) navigate(routeName);
      });
      menuButtons.appendChild(button);
    });
  }

  const handleBack = () => navigate("location");
  const unbindButtons = bindButtonHandlers([{ target: backBtn, handler: handleBack }]);

  updateModeHint();
  renderParty();
  renderButtons();
  renderResources();

  return () => {
    unbindButtons();
  };
}
