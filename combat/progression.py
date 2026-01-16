from __future__ import annotations

from typing import Iterable, Any, Tuple, List, Optional, Dict

from combat.models import PartyMemberRuntime, EquipmentSet, PlannedAction, Job
from combat.char_build import compute_character_final_stats
from system.exp_system import LevelTable


def apply_battle_exp_and_refresh(
    member: PartyMemberRuntime,
    gained_exp: int,
    level_table: LevelTable,
    weapons: dict,
    armors: dict,
) -> tuple[int, int]:
    old_level = member.base.level

    gained = max(0, int(gained_exp))
    member.base.total_exp = max(0, member.base.total_exp + gained)

    st = level_table.status_from_total_exp(member.base.total_exp)
    member.base.level = st.level

    eq = member.equipment if member.equipment is not None else EquipmentSet()

    member.stats = compute_character_final_stats(
        member.base, eq, weapons, armors, job_name=member.job.name
    )

    member.state.max_hp = member.stats.max_hp
    member.state.hp = min(member.state.hp, member.state.max_hp)

    return old_level, member.base.level


# 型はあなたのプロジェクトの import パスに合わせてください
# from combat.types import PartyMemberRuntime, EnemyRuntime
# from system.exp_system import LevelTable
# from combat.char_stats import compute_character_final_stats
# from combat.equipment import EquipmentSet


def compute_exp_reward(enemies: Iterable[Any]) -> int:
    """
    敵リストから総経験値を合計して返す。
    EnemyRuntime.json["Experience"] を想定。
    欠損や不正値は 0 扱い。
    """
    total = 0
    for e in enemies:
        exp_val = 0
        j = getattr(e, "json", None)
        if isinstance(j, dict):
            raw = j.get("Experience", 0)
            try:
                exp_val = int(raw)
            except (TypeError, ValueError):
                exp_val = 0
        if exp_val > 0:
            total += exp_val
    return total


def split_exp_evenly(total_exp: int, alive_count: int) -> tuple[int, int]:
    """
    均等配分の内訳を返す。
    戻り値: (per_member, remainder)
      - per_member: 各メンバーに必ず入る分
      - remainder: 余り（0..alive_count-1）
    """
    if alive_count <= 0:
        return 0, 0
    total_exp = max(0, int(total_exp))
    return total_exp // alive_count, total_exp % alive_count


def apply_victory_exp_rewards(
    party_members: List[Any],
    enemies: List[Any],
    *,
    level_table: Any,
    weapons: dict,
    armors: dict,
) -> list[tuple[str, int, int]]:
    """
    勝利時の経験値報酬を、生存メンバーに均等配分して適用する。
    戻り値: レベルが上がったメンバーの (name, old_level, new_level) 一覧
    """
    from combat.progression import apply_battle_exp_and_refresh

    total_exp = compute_exp_reward(enemies)
    alive_members = [m for m in party_members if getattr(m.state, "hp", 0) > 0]

    per_member = split_exp_evenly_no_remainder(total_exp, len(alive_members))
    if per_member == 0:
        return []  # 公平のため今回は加算なし

    levelups: list[tuple[str, int, int]] = []
    for m in alive_members:
        old_lv, new_lv = apply_battle_exp_and_refresh(
            m, per_member, level_table, weapons, armors
        )
        if new_lv != old_lv:
            levelups.append((m.name, old_lv, new_lv))

    return levelups


# 取得経験値に余りが出たら「全員0」にする
def split_exp_evenly_no_remainder(total_exp: int, alive_count: int) -> int:
    """
    均等配分（余りが出る場合は公平のため 0 を返す）
    戻り値: per_member（全員に加算する量。割り切れないなら0）
    """
    if alive_count <= 0:
        return 0
    total_exp = max(0, int(total_exp))
    if total_exp % alive_count != 0:
        return 0
    return total_exp // alive_count


def persist_party_progress_to_save(save: dict, party_members: list[Any]) -> None:
    """
    PartyMemberRuntime の base.level / base.total_exp を save["party"] に書き戻す（破壊的に更新）
    name で対応付け。
    """
    party = save.get("party")
    if not isinstance(party, list):
        return

    # name -> runtime member
    by_name = {m.name: m for m in party_members}

    for entry in party:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue

        m = by_name.get(name)
        if m is None:
            continue

        # savedata更新
        entry["level"] = int(m.base.level)
        entry["exp"] = int(m.base.total_exp)

        jl = entry.get("job_level")
        if not isinstance(jl, dict):
            jl = {}
            entry["job_level"] = jl

        jl["level"] = int(m.base.job_level)
        jl["skill_point"] = int(m.base.job_skill_point)


# ---------------------- Skill Point
JOB_SP_THRESHOLD = 100
JOB_LEVEL_MAX = 99  # 必要なら


def build_command_skillpoints(job_raw: Dict[str, Any]) -> Dict[str, int]:
    """
    job.raw から Command -> SkillPoints の辞書を作る
    """
    m: Dict[str, int] = {}
    for i in range(1, 5):
        bc = job_raw.get(f"BattleCommand{i}")
        if not isinstance(bc, dict):
            continue
        cmd = bc.get("Command")
        sp = bc.get("SkillPoints", 0)
        if isinstance(cmd, str) and cmd:
            try:
                m[cmd] = int(sp)
            except (TypeError, ValueError):
                m[cmd] = 0
    return m


def apply_job_skillpoints(base: Any, gained_sp: int) -> Tuple[int, int]:
    """
    base.job_skill_point に gained_sp を加算し、100ごとに job_level を上げる。
    戻り値: (old_job_level, new_job_level)
    """
    old = int(base.job_level)

    gained = max(0, int(gained_sp))
    sp_total = int(getattr(base, "job_skill_point", 0)) + gained

    # 最大到達時の扱い（好みで変更可）
    if int(base.job_level) >= JOB_LEVEL_MAX:
        setattr(base, "job_level", JOB_LEVEL_MAX)
        setattr(base, "job_skill_point", min(99, sp_total))
        return old, int(base.job_level)

    up = sp_total // JOB_SP_THRESHOLD
    if up > 0:
        new_level = min(JOB_LEVEL_MAX, int(base.job_level) + up)
        setattr(base, "job_level", new_level)
        sp_total = sp_total % JOB_SP_THRESHOLD

    setattr(base, "job_skill_point", max(0, min(99, sp_total)))
    return old, int(base.job_level)


def _skillpoints_for_command(job: Any, command_name: str) -> int:
    """
    job(raw)の BattleCommand 定義から、指定コマンドの SkillPoints を返す。
    見つからなければ 0
    """
    raw = getattr(job, "raw", None)
    if not isinstance(raw, dict):
        return 0

    cmd_map = build_command_skillpoints(raw)
    return int(cmd_map.get(command_name, 0))


def apply_job_sp_for_command(
    member: Any,  # PartyMemberRuntime
    command_name: str,
    *,
    weapons: dict,
    armors: dict,
    save_dict: dict | None = None,  # ★追加
    recompute_stats_on_levelup: bool = True,
) -> Tuple[int, int]:

    if not isinstance(command_name, str) or not command_name:
        return member.base.job_level, member.base.job_level

    gained = _skillpoints_for_command(member.job, command_name)
    if gained <= 0:
        return member.base.job_level, member.base.job_level

    # ---- runtime 更新（既存）----
    old_jl, new_jl = apply_job_skillpoints(member.base, gained)

    # ---- JobLvが変わったら再計算（既存）----
    if recompute_stats_on_levelup and new_jl != old_jl:
        eq = member.equipment if member.equipment is not None else EquipmentSet()
        member.stats = compute_character_final_stats(
            member.base, eq, weapons, armors, job_name=member.job.name
        )

    # ============================================================
    # ★追加：save_dict（= state.save）にも job_levels を同期する
    # ============================================================
    if save_dict is not None:
        sp_entry = None
        for p in save_dict.get("party", []):
            if p.get("name") == member.name:
                sp_entry = p
                break

        if sp_entry is not None:
            # job_levels dict を保証
            job_levels = sp_entry.get("job_levels")
            if not isinstance(job_levels, dict):
                job_levels = {}
                sp_entry["job_levels"] = job_levels

            job_name = member.job.name

            # 該当ジョブが無ければ初期化（念のため）
            jl = job_levels.get(job_name)
            if not isinstance(jl, dict):
                jl = {
                    "level": int(member.base.job_level),
                    "skill_point": int(member.base.job_skill_point),
                }
                job_levels[job_name] = jl

            # ここが本命：runtimeの最新値で上書き
            jl["level"] = int(member.base.job_level)
            jl["skill_point"] = int(member.base.job_skill_point)

            # 互換用：現在ジョブフィールドも同期（既存仕様との整合）
            sp_entry["job"] = job_name
            sp_entry["job_level"] = {
                "level": int(member.base.job_level),
                "skill_point": int(member.base.job_skill_point),
            }

    return old_jl, new_jl


def command_name_for_job_sp(action: PlannedAction) -> Optional[str]:
    """
    Job SkillPoints 加算に使うコマンド名を返す。
    Jobデータの BattleCommandX.Command と一致する文字列を返す。
    """

    # ① 明示的に command が指定されている場合（最優先）
    if isinstance(action.command, str) and action.command:
        return action.command

    # ② BattleKind から補完
    kind = action.kind

    if kind == "physical":
        return "Fight"
    if kind == "defend":
        return "Defend"
    if kind == "run":
        return "Run"
    if kind == "item":
        return "Item"

    if kind == "magic":
        # FF3のJob定義に合わせて調整する
        # 例: "White Magic" / "Black Magic" / "Summon"
        # 最低限動かすなら "Magic"
        return "Magic"

    if kind == "jump":
        return "Jump"

    if kind == "special":
        # ジョブ固有コマンド（例: Steal, Throw, Sing など）
        # action.command が None のまま来るなら加算しない
        return None

    return None
