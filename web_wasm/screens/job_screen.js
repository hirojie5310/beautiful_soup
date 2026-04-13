import { applyJobChangeToSaveEntry } from "../job_persistence.js";
import { findPartyMemberIndex } from "../shared_party.js";
import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import {
  bindButtonHandlers,
  bindMenuSubpageNavigation,
  persistMenuEnvelope,
  stepMenuMemberSelection,
  syncMenuMemberSelection,
} from "./screen_shared.js";

function asNum(v, d = 0) { const n = Number(v); return Number.isFinite(n) ? n : d; }

function renderLayout() {
  return renderMenuSubpageShell({
    width: "medium",
    content: `
      <section class="frame title-row"><h1 class="title">ジョブ</h1></section>
      <section class="frame">
        <div id="memberLine" class="member-line">-</div>
        <div class="sep"></div>
        <div id="jobGrid" class="job-grid"></div>
        <div class="action-row">
          <div id="selectedJobLine" class="selected-job">選択中: -</div>
          <button id="changeJobBtn" class="btn" type="button">ジョブチェンジ決定</button>
        </div>
      </section>
      <section class="frame">
        <div class="footer">
          <button id="leftBtn" class="btn" type="button">◀</button>
          <button id="backBtn" class="btn" type="button">BACK</button>
          <button id="rightBtn" class="btn" type="button">▶</button>
        </div>
        <p class="hint">←/→ でキャラクター切替、Esc/Enter で戻る</p>
      </section>
    `,
    styles: `
      .title-row { display:flex; justify-content:space-between; align-items:center; gap:8px; }
      .title { margin:0; color:#ffe588; font-size:1.1rem; }
      .member-line { font-size:1.15rem; font-weight:700; margin-bottom:8px; }
      .member-line .muted { font-size:0.95rem; font-weight:400; }
      .sep { border-top:1px solid rgba(255,255,255,0.35); margin:8px 0; }
      .job-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:8px; }
      .job-card { border:1px solid rgba(255,255,255,0.35); border-radius:8px; background:rgba(0,0,0,0.2); padding:8px; min-height:84px; }
      .job-card.current { border-color:#ffe588; box-shadow:0 0 0 1px rgba(255,229,136,0.45) inset; }
      .job-card.selected { box-shadow:0 0 0 2px rgba(137,240,172,0.6) inset; }
      .job-name { font-size:0.9rem; font-weight:700; margin-bottom:4px; word-break:break-word; }
      .job-meta { color:#acb6d7; font-size:0.84rem; line-height:1.2; display:flex; align-items:center; gap:8px; white-space:nowrap; }
      .empty { border:1px dashed rgba(255,255,255,0.4); border-radius:8px; padding:10px; color:#acb6d7; }
      .footer { display:grid; grid-template-columns:1fr 1.5fr 1fr; gap:8px; }
      .hint, .selected-job { color:#acb6d7; font-size:0.88rem; }
      .action-row { margin-top:10px; display:flex; gap:8px; align-items:center; justify-content:space-between; }
    `,
  });
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();
  const memberLine = mountNode.querySelector("#memberLine");
  const jobGrid = mountNode.querySelector("#jobGrid");
  const selectedJobLine = mountNode.querySelector("#selectedJobLine");
  const changeJobBtn = mountNode.querySelector("#changeJobBtn");
  const leftBtn = mountNode.querySelector("#leftBtn");
  const rightBtn = mountNode.querySelector("#rightBtn");
  const backBtn = mountNode.querySelector("#backBtn");

  let memberIndex = Number(store.getState().menuMemberIndex ?? 0);
  const selectedJobNameByMember = {};

  function renderMemberLine(member, currentRow, resources) {
    memberLine.innerHTML = `${String(member?.name || "-")}　${String(currentRow?.job_name || member?.job || "-")}　<span class="muted">CP ${asNum(resources?.cp, 0)}/${asNum(resources?.cp_max, 255)}</span>`;
  }

  function findCurrentJobRow(member, rows) {
    const currentJob = String(member?.job || "");
    return rows.find((row) => Boolean(row?.is_current))
      || rows.find((row) => String(row?.job_name || "") === currentJob)
      || null;
  }

  function renderJobs(rows, fallbackJobs, currentRow) {
    jobGrid.innerHTML = "";
    const sourceRows = rows.length ? rows : fallbackJobs.map((jobName) => ({ job_name: String(jobName || ""), cp_cost: 0, saved_job_level: 1, is_current: false }));
    if (!sourceRows.length) {
      jobGrid.innerHTML = '<div class="empty">表示できるジョブ情報がありません。バトル画面で状態同期後に再度開いてください。</div>';
      return;
    }
    sourceRows.forEach((row) => {
      const selectedJobName = selectedJobNameByMember[memberIndex];
      const isSelected = String(row?.job_name || "") === String(selectedJobName || "");
      const isCurrent = Boolean(row?.is_current) || String(row?.job_name || "") === String(currentRow?.job_name || "");
      const card = document.createElement("article");
      card.className = `job-card${isCurrent ? " current" : ""}${isSelected ? " selected" : ""}`;
      card.innerHTML = `<div class="job-name">${isCurrent ? "▶ " : ""}${String(row?.job_name || "-")}${isCurrent ? " [E]" : ""}</div><div class="job-meta"><span>Lv ${asNum(row?.saved_job_level, 1)}</span><span>CP ${asNum(row?.cp_cost, 0)}</span></div>`;
      card.addEventListener("click", () => {
        selectedJobNameByMember[memberIndex] = String(row?.job_name || "");
        render();
      });
      jobGrid.appendChild(card);
    });
  }

  function applyJobChange() {
    const state = store.getState();
    const menuState = state.menuState;
    const party = Array.isArray(menuState?.party) ? menuState.party : [];
    if (!party.length) return;
    const member = party[memberIndex] || {};
    const rows = Array.isArray(menuState?.job_candidates_by_member?.[memberIndex]) ? menuState.job_candidates_by_member[memberIndex] : Array.isArray(menuState?.jobCandidatesByMember?.[memberIndex]) ? menuState.jobCandidatesByMember[memberIndex] : [];
    const selectedName = String(selectedJobNameByMember[memberIndex] || "");
    const currentJob = String(member?.job || "");
    const row = rows.find((r) => String(r?.job_name || "") === selectedName);
    const currentRow = rows.find((r) => Boolean(r?.is_current)) || rows.find((r) => String(r?.job_name || "") === currentJob);
    if (!selectedName || !row) return window.alert("ジョブを選択してください。");
    if (selectedName === currentJob) return window.alert("現在のジョブです。");
    const requiredCp = asNum(row?.cp_cost, 0);
    const currentCp = asNum(menuState?.resources?.cp, 0);
    if (currentCp < requiredCp) return window.alert(`CPが足りません。必要 ${requiredCp} / 現在 ${currentCp}`);
    if (!window.confirm(`${member?.name || "このキャラ"}を ${selectedName} に変更しますか？\n必要CP: ${requiredCp}`)) return;

    const nextParty = party.map((rowMember, idx) => {
      if (idx !== memberIndex) return rowMember;
      const syncedJobState = applyJobChangeToSaveEntry(
        { ...rowMember, current_job: rowMember?.current_job ?? currentJob, job: rowMember?.job ?? currentJob, job_level: rowMember?.job_level ?? { level: currentRow?.saved_job_level ?? 1, skill_point: 0 }, job_levels: rowMember?.job_levels },
        {
          currentJob,
          nextJob: selectedName,
          currentJobLevel: currentRow?.saved_job_level ?? 1,
          currentJobSkillPoint: rowMember?.job_levels?.[currentJob]?.skill_point ?? rowMember?.job_level?.skill_point ?? 0,
          nextJobLevel: row?.saved_job_level ?? 1,
          nextJobSkillPoint: rowMember?.job_levels?.[selectedName]?.skill_point ?? 0,
        },
      );
      return { ...rowMember, ...syncedJobState, job: selectedName, current_job: selectedName };
    });
    const nextResources = { ...(menuState?.resources || {}), cp: currentCp - requiredCp };
    const nextJobCandidatesByMember = (menuState?.job_candidates_by_member || menuState?.jobCandidatesByMember || []).map((memberRows, idx) => {
      if (idx !== memberIndex || !Array.isArray(memberRows)) return memberRows;
      return memberRows.map((cand) => ({ ...cand, is_current: String(cand?.job_name || "") === selectedName }));
    });
    const nextMenuState = {
      ...(menuState && typeof menuState === "object" ? menuState : {}),
      party: nextParty,
      resources: nextResources,
      job_candidates_by_member: nextJobCandidatesByMember,
    };
    const nextEnvelope = structuredClone(state.saveEnvelope || store.createDefaultEnvelope());
    nextEnvelope.menu_state = nextMenuState;
    if (nextEnvelope?.save) {
      nextEnvelope.save.CP = currentCp - requiredCp;
      const saveParty = Array.isArray(nextEnvelope.save.party) ? nextEnvelope.save.party : [];
      const saveIndex = findPartyMemberIndex(saveParty, member, memberIndex);
      if (saveIndex >= 0 && saveParty[saveIndex]) {
        nextEnvelope.save.party[saveIndex] = applyJobChangeToSaveEntry(saveParty[saveIndex], {
          currentJob,
          nextJob: selectedName,
          currentJobLevel: currentRow?.saved_job_level ?? 1,
          currentJobSkillPoint: saveParty[saveIndex]?.job_level?.skill_point ?? 0,
          nextJobLevel: row?.saved_job_level ?? 1,
        });
      }
    }
    persistMenuEnvelope(store, nextMenuState, nextEnvelope);
    selectedJobNameByMember[memberIndex] = selectedName;
    window.alert(`ジョブを ${selectedName} に変更しました。`);
    render();
  }

  function render() {
    const state = store.getState();
    const menuState = state.menuState;
    const selection = syncMenuMemberSelection(store, memberIndex);
    const party = selection.party;
    if (!party.length) {
      memberLine.textContent = "No party members";
      jobGrid.innerHTML = '<div class="empty">パーティ情報がありません。</div>';
      return;
    }
    memberIndex = selection.memberIndex;
    const member = selection.member || {};
    const rowsRaw = Array.isArray(menuState?.job_candidates_by_member?.[memberIndex]) ? menuState.job_candidates_by_member[memberIndex] : Array.isArray(menuState?.jobCandidatesByMember?.[memberIndex]) ? menuState.jobCandidatesByMember[memberIndex] : [];
    const rows = rowsRaw.filter((row) => row && typeof row === "object").map((row) => ({
      job_name: String(row?.job_name || ""),
      cp_cost: asNum(row?.cp_cost, 0),
      saved_job_level: asNum(row?.saved_job_level, 1),
      is_current: Boolean(row?.is_current),
    })).filter((row) => row.job_name);
    const currentRow = findCurrentJobRow(member, rows);
    if (!selectedJobNameByMember[memberIndex]) selectedJobNameByMember[memberIndex] = String(currentRow?.job_name || member?.job || "");
    const selectedName = String(selectedJobNameByMember[memberIndex] || "");
    const selectedRow = rows.find((row) => String(row?.job_name || "") === selectedName) || currentRow;
    renderMemberLine(member, currentRow, menuState?.resources);
    renderJobs(rows, menuState?.jobs || [], currentRow);
    selectedJobLine.textContent = `選択中: ${String(selectedRow?.job_name || "-")} / 必要CP ${asNum(selectedRow?.cp_cost, 0)}`;
  }

  const onLeft = () => { memberIndex = stepMenuMemberSelection(store, memberIndex, -1); render(); };
  const onRight = () => { memberIndex = stepMenuMemberSelection(store, memberIndex, 1); render(); };
  const onBack = () => navigate("menu");
  const unbindButtons = bindMenuSubpageNavigation({
    leftBtn,
    rightBtn,
    backBtn,
    onLeft,
    onRight,
    onBack,
  });
  const unbindJobButton = bindButtonHandlers([{ target: changeJobBtn, handler: applyJobChange }]);
  render();
  return () => {
    unbindButtons();
    unbindJobButton();
  };
}
