const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";

const memberLine = document.getElementById("memberLine");
const jobGrid = document.getElementById("jobGrid");
const selectedJobLine = document.getElementById("selectedJobLine");
const changeJobBtn = document.getElementById("changeJobBtn");
const leftBtn = document.getElementById("leftBtn");
const rightBtn = document.getElementById("rightBtn");
const backBtn = document.getElementById("backBtn");

let memberIndex = 0;
const selectedJobNameByMember = {};

function asNum(v, d = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

function parseState() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    const parsed = text ? JSON.parse(text) : {};
    return {
      raw: parsed,
      party: Array.isArray(parsed?.party) ? parsed.party : [],
      resources: parsed?.resources && typeof parsed.resources === "object"
        ? parsed.resources
        : { cp: 0, cp_max: 255 },
      jobs: Array.isArray(parsed?.jobs) ? parsed.jobs : [],
      jobCandidatesByMember: Array.isArray(parsed?.job_candidates_by_member)
        ? parsed.job_candidates_by_member
        : [],
    };
  } catch (_error) {
    return {
      raw: {},
      party: [],
      resources: { cp: 0, cp_max: 255 },
      jobs: [],
      jobCandidatesByMember: [],
    };
  }
}

function persistMenuState(state) {
  try {
    localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch (_error) {
    return false;
  }
}

function parseSaveEnvelope() {
  try {
    const text = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!text) return null;
    const parsed = JSON.parse(text);
    if (parsed?.version === 1 && parsed?.save && typeof parsed.save === "object") {
      return parsed;
    }
    if (parsed?.party && Array.isArray(parsed.party)) {
      return {
        version: 1,
        saved_at: "",
        selected_location_group: "",
        selected_location: "",
        save: parsed,
      };
    }
    return null;
  } catch (_error) {
    return null;
  }
}

function persistSaveEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object") return false;
  try {
    localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));
    return true;
  } catch (_error) {
    return false;
  }
}

function findCurrentJobRow(member, rows) {
  const currentJob = String(member?.job || "");
  const byFlag = rows.find((row) => Boolean(row?.is_current));
  if (byFlag) return byFlag;
  return rows.find((row) => String(row?.job_name || "") === currentJob) || null;
}

function renderMemberLine(member, currentRow, resources) {
  const name = String(member?.name || "-");
  const currentJob = String(currentRow?.job_name || member?.job || "-");
  const cp = asNum(resources?.cp, 0);
  const cpMax = asNum(resources?.cp_max, 255);
  memberLine.innerHTML = `${name}　${currentJob}　<span class="muted">CP ${cp}/${cpMax}</span>`;
}

function renderJobs(rows, fallbackJobs, currentRow) {
  jobGrid.innerHTML = "";
  const sourceRows = rows.length
    ? rows
    : fallbackJobs.map((jobName) => ({
      job_name: String(jobName || ""),
      cp_cost: 0,
      saved_job_level: 1,
      is_current: false,
    }));

  if (!sourceRows.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "表示できるジョブ情報がありません。バトル画面で状態同期後に再度開いてください。";
    jobGrid.appendChild(empty);
    return;
  }

  sourceRows.forEach((row) => {
    const card = document.createElement("article");
    const selectedJobName = selectedJobNameByMember[memberIndex];
    const isSelected = String(row?.job_name || "") === String(selectedJobName || "");
    const isCurrent = Boolean(row?.is_current)
      || String(row?.job_name || "") === String(currentRow?.job_name || "");
    card.className = `job-card${isCurrent ? " current" : ""}${isSelected ? " selected" : ""}`;

    const title = document.createElement("div");
    title.className = "job-name";
    const marker = isCurrent ? "▶ " : "";
    const currentSuffix = isCurrent ? " [E]" : "";
    title.textContent = `${marker}${String(row?.job_name || "-")}${currentSuffix}`;

    const meta = document.createElement("div");
    meta.className = "job-meta";
    meta.innerHTML = `Lv ${asNum(row?.saved_job_level, 1)}<br>CP ${asNum(row?.cp_cost, 0)}`;

    card.append(title, meta);
    card.addEventListener("click", () => {
      selectedJobNameByMember[memberIndex] = String(row?.job_name || "");
      render();
    });
    jobGrid.appendChild(card);
  });
}

function render() {
  const state = parseState();
  if (!state.party.length) {
    memberLine.textContent = "No party members";
    jobGrid.innerHTML = '<div class="empty">パーティ情報がありません。</div>';
    return;
  }

  memberIndex = ((memberIndex % state.party.length) + state.party.length) % state.party.length;
  const member = state.party[memberIndex] || {};
  const rowsRaw = Array.isArray(state.jobCandidatesByMember?.[memberIndex])
    ? state.jobCandidatesByMember[memberIndex]
    : [];
  const rows = rowsRaw
    .filter((row) => row && typeof row === "object")
    .map((row) => ({
      job_name: String(row?.job_name || ""),
      cp_cost: asNum(row?.cp_cost, 0),
      saved_job_level: asNum(row?.saved_job_level, 1),
      is_current: Boolean(row?.is_current),
    }))
    .filter((row) => row.job_name);

  const currentRow = findCurrentJobRow(member, rows);
  if (!selectedJobNameByMember[memberIndex]) {
    selectedJobNameByMember[memberIndex] = String(currentRow?.job_name || member?.job || "");
  }
  const selectedName = String(selectedJobNameByMember[memberIndex] || "");
  const selectedRow = rows.find((row) => String(row?.job_name || "") === selectedName) || currentRow;
  renderMemberLine(member, currentRow, state.resources);
  renderJobs(rows, state.jobs, currentRow);
  if (selectedJobLine) {
    selectedJobLine.textContent = `選択中: ${String(selectedRow?.job_name || "-")} / 必要CP ${asNum(selectedRow?.cp_cost, 0)}`;
  }
}

function goBack() {
  window.location.href = "./menu.html";
}

function applyJobChange() {
  const state = parseState();
  if (!state.party.length) return;
  const member = state.party[memberIndex] || {};
  const rows = Array.isArray(state.jobCandidatesByMember?.[memberIndex])
    ? state.jobCandidatesByMember[memberIndex]
    : [];
  const selectedName = String(selectedJobNameByMember[memberIndex] || "");
  const row = rows.find((r) => String(r?.job_name || "") === selectedName);
  if (!selectedName || !row) {
    window.alert("ジョブを選択してください。");
    return;
  }
  const currentJob = String(member?.job || "");
  if (selectedName === currentJob) {
    window.alert("現在のジョブです。");
    return;
  }
  const requiredCp = asNum(row?.cp_cost, 0);
  const currentCp = asNum(state?.resources?.cp, 0);
  if (currentCp < requiredCp) {
    window.alert(`CPが足りません。必要 ${requiredCp} / 現在 ${currentCp}`);
    return;
  }

  const ok = window.confirm(`${member?.name || "このキャラ"}を ${selectedName} に変更しますか？\n必要CP: ${requiredCp}`);
  if (!ok) return;

  const nextState = {
    ...state,
    party: state.party.map((rowMember, idx) => {
      if (idx !== memberIndex) return rowMember;
      return { ...rowMember, job: selectedName };
    }),
    resources: {
      ...state.resources,
      cp: currentCp - requiredCp,
    },
    jobCandidatesByMember: state.jobCandidatesByMember.map((memberRows, idx) => {
      if (idx !== memberIndex || !Array.isArray(memberRows)) return memberRows;
      return memberRows.map((cand) => ({
        ...cand,
        is_current: String(cand?.job_name || "") === selectedName,
      }));
    }),
  };
  if (!persistMenuState({
    ...(state.raw && typeof state.raw === "object" ? state.raw : {}),
    ...nextState,
    job_candidates_by_member: nextState.jobCandidatesByMember,
  })) {
    window.alert("メニュー状態の保存に失敗しました。");
    return;
  }

  const envelope = parseSaveEnvelope();
  if (envelope?.save && Array.isArray(envelope.save.party) && envelope.save.party[memberIndex]) {
    envelope.save.CP = currentCp - requiredCp;
    envelope.save.party[memberIndex].job = selectedName;
    envelope.saved_at = new Date().toISOString();
    persistSaveEnvelope(envelope);
  }

  selectedJobNameByMember[memberIndex] = selectedName;
  window.alert(`ジョブを ${selectedName} に変更しました。`);
  render();
}

leftBtn?.addEventListener("click", () => {
  memberIndex -= 1;
  render();
});
rightBtn?.addEventListener("click", () => {
  memberIndex += 1;
  render();
});
backBtn?.addEventListener("click", goBack);
changeJobBtn?.addEventListener("click", applyJobChange);

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    memberIndex -= 1;
    render();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    memberIndex += 1;
    render();
  } else if (event.key === "Escape" || event.key === "Enter" || event.key === "Backspace") {
    event.preventDefault();
    goBack();
  }
});

render();
