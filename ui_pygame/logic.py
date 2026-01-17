# ============================================================
# logic: target_side input_modeの処理

# reset_target_flags: ターゲット関連のフラグをリセット
# make_planned_action: プランされた行動を作成
# build_magic_candidates_for_member: メンバーの魔法候補リストを構築
# build_item_candidates_for_battle: 戦闘中のアイテム候補リストを構築
# normalize_battle_command: 戦闘コマンドを正規化
# get_job_commands: ジョブから戦闘コマンドリストを取得
# find_next_unfilled: 次の未入力キャラを探す
# to_int: 任意の値を整数に変換
# ============================================================

from typing import Any, List, Optional, Tuple, cast, Callable
from combat.models import PlannedAction, TargetSide
from combat.enums import BattleKind
from combat.inventory import build_item_list, is_item_visible_in_context
from combat.input_ui import normalize_battle_command
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import CommandCandidate


SPECIAL_NO_TARGET = {"Cheer", "Scare", "Flee", "Terrain", "Boost"}
SPECIAL_ENEMY_TARGET = {"Steal", "Peep", "Study"}  # 必要なら増やす


def command_needs_target(cmd: str, kind: BattleKind) -> bool:
    if kind in ("physical", "magic", "item", "jump"):
        return True
    if kind in ("defend", "run"):
        return False
    if kind == "special":
        if cmd in SPECIAL_NO_TARGET:
            return False
        # 未分類 special はとりあえず「敵単体扱い」に寄せる（安全側）
        return True
    return True


def reset_target_flags(ui: BattleUIState) -> None:
    # ターゲット関連
    ui.selected_target_all = False
    ui.selected_target_idx = 0
    ui.selected_target_side_idx = 0
    ui.target_side = cast(TargetSide, "enemy")

    # 直前の選択内容（重要）
    ui.selected_spell_name = None
    ui.selected_item_name = None


def make_planned_action(
    *,
    kind: BattleKind,
    command: str,
    member_idx: int,
    target_side: TargetSide,
    target_index: Optional[int],
    spell_name: Optional[str] = None,
    item_name: Optional[str] = None,
    target_all: bool = False,  # ★追加
) -> PlannedAction:
    return PlannedAction(
        kind=kind,
        command=command,
        spell_name=spell_name,
        item_name=item_name,
        target_side=target_side,
        target_index=target_index,
        target_all=target_all,  # ★追加
    )


# メンバーの魔法候補リストを構築
def build_magic_candidates_for_member(
    party_magic_lists, member_idx: int
) -> list[tuple[str, int, int]]:
    """
    party_magic_lists の要素が (name, magic_type, level) の前提で
    UI 用に (name, level, cost) に変換する。
    cost は現状不明なので 0 にする（将来拡張で差し替え）。
    """
    out: list[tuple[str, int, int]] = []
    for row in party_magic_lists[member_idx] or []:
        name = str(row[0])
        lv = int(row[2])  # ★ level は row[2]
        cost = 0  # ★ MPコスト（必要なら後で spells マスタから引く）
        out.append((name, lv, cost))
    return out


# 戦闘中のアイテム候補リストを構築
def build_item_candidates_for_battle(items_by_name, save) -> List[Tuple[str, str, int]]:
    item_list = build_item_list(items_by_name, save, in_battle=True)
    item_list = [
        (name, itype, qty)
        for (name, itype, qty) in item_list
        if is_item_visible_in_context(items_by_name.get(name, {}), in_combat=True)
    ]
    return item_list


def get_job_commands(member) -> List[CommandCandidate]:
    """ジョブ定義の BattleCommand1..4 を読む。cmd と kind をここで確定する。"""
    job_data = member.job
    cmds: List[CommandCandidate] = []
    raw = getattr(job_data, "raw", {}) or {}

    for i in range(1, 5):
        bc = raw.get(f"BattleCommand{i}")
        if not bc:
            continue
        c = (bc.get("Command") or "").strip()
        if c:
            k: BattleKind = normalize_battle_command(c)
            cmds.append(CommandCandidate(cmd=c, kind=k))

    # 保険：空ならFF基本セット
    if not cmds:
        base = ["Fight", "Defend", "Item", "Run"]
        cmds = [CommandCandidate(cmd=c, kind=normalize_battle_command(c)) for c in base]

    return cmds


# 次の未入力キャラを探す
def find_next_unfilled(ui: BattleUIState) -> Optional[int]:
    n = len(ui.planned_actions)
    if n == 0:
        return None
    for offset in range(0, n):  # ★0から探す（現在位置も含めたい場合）
        i = (ui.selected_member_idx + offset) % n
        if ui.planned_actions[i] is None:
            return i
    return None


def to_int(x: Any, default: int = 0) -> int:
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        try:
            return int(x)
        except ValueError:
            return default
    return default


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


#### ------------------------------------------
# あなたの状態異常 enum/文字列に合わせてここだけ調整してください
# savedata/status_effects のキー名と合わせるのがコツです
STATUS_KEY_BY_SPELL = {
    "Poisona": "Poison",
    "Blindna": "Blind",
    "Stona": "Petrification",  # Partial Petrification も消すなら下で追加
}

ESUNA_CURES = {
    "Poison",
    "Blind",
    "Mini",
    "Silence",
    "Toad",
    "Petrification",
    "Partial Petrification",
    "Confusion",
    "Sleep",
    "Paralysis",
}

HEAL_SPELLS = {"Cure", "Cura", "Curaga", "Curaja"}
RAISE_SPELLS = {"Raise", "Arise"}


def make_cast_field_magic_fn(
    *,
    party,
    spells_by_name: dict[str, dict],
    build_magic_fn: Callable[[int], list[tuple[str, int, int]]],
    save_dict: Optional[dict] = None,
    toast: Optional[
        Callable[[str], None]
    ] = None,  # show_toast_message を薄く包んで渡す想定
) -> Callable[[int, str, Optional[int]], bool]:

    def _get_cost(caster_idx: int, spell_name: str) -> tuple[int, int] | None:
        # build_magic_fn から (lv,cost) を引く
        for n, lv, cost in build_magic_fn(caster_idx):
            if str(n) == spell_name:
                return int(lv), int(cost)
        return None

    def _mp_pool(actor):
        battle = getattr(actor, "battle", None)
        return getattr(actor, "mp_pool", None) or (battle.mp_pool if battle else {})

    def _max_mp_pool(actor):
        battle = getattr(actor, "battle", None)
        return getattr(actor, "max_mp_pool", None) or (
            battle.max_mp_pool if battle else {}
        )

    def _consume_mp(actor, lv: int, cost: int) -> bool:
        mp_pool = _mp_pool(actor)
        cur = int(mp_pool.get(lv, 0))
        if cur < cost:
            return False
        mp_pool[lv] = cur - cost
        return True

    def _sync_mp_to_save(actor):
        # savedata 側に mp dict を持たせる想定（あなたの設計）
        if not isinstance(save_dict, dict):
            return
        sp_list = save_dict.get("party", [])
        for sp in sp_list:
            if sp.get("name") == actor.name:
                mp_pool = _mp_pool(actor)
                sp["mp"] = {f"L{i}MP": int(mp_pool.get(i, 0)) for i in range(1, 9)}
                break

    def _sync_hp_status_to_save(actor):
        if not isinstance(save_dict, dict):
            return
        sp_list = save_dict.get("party", [])
        for sp in sp_list:
            if sp.get("name") == actor.name:
                sp["hp"] = int(actor.hp)
                # status_effects は dict として保持してる想定
                # actor 側に runtime の status_effects を持ってないなら、save 側だけ更新でもOK
                break

    def _get_status_effects_dict(actor) -> dict:
        # ここはあなたの設計に合わせて：
        # - battle.statuses (set[Status]) しかないなら、それを savedata形式(dict)に変換する必要がある
        # - 既に actor に status_effects(dict) があるならそれを使う
        se = getattr(actor, "status_effects", None)
        if isinstance(se, dict):
            return se
        # 無ければ save_dict 側を直接いじる方式にする（簡易）
        if isinstance(save_dict, dict):
            for sp in save_dict.get("party", []):
                if sp.get("name") == actor.name:
                    d = sp.get("status_effects")
                    if isinstance(d, dict):
                        return d
                    sp["status_effects"] = {}
                    return sp["status_effects"]
        return {}

    def _clear_status(actor, key: str) -> bool:
        se = _get_status_effects_dict(actor)
        if key in se:
            se.pop(key, None)
            return True
        return False

    def _set_hp(actor, new_hp: int) -> bool:
        old = int(actor.hp)
        new_hp = max(0, min(int(new_hp), int(actor.max_hp)))
        if new_hp == old:
            return False
        actor.hp = new_hp
        # battle 側も同期したいなら：
        battle = getattr(actor, "battle", None)
        if battle is not None and hasattr(battle, "hp"):
            battle.hp = new_hp
        return True

    def _heal_amount(spell_name: str, caster) -> int:
        # まず固定値でOK（あとでMind/JobLv等を入れられる）
        if spell_name == "Cure":
            return 50
        if spell_name == "Cura":
            return 150
        if spell_name == "Curaga":
            return 400
        if spell_name == "Curaja":
            return 9999  # 全回復扱い
        return 0

    def cast_field_magic(
        caster_idx: int, spell_name: str, target_idx: int | None
    ) -> bool:
        caster = party[caster_idx]
        sp = spells_by_name.get(spell_name, {})
        if not sp:
            if toast:
                toast("Spell not found")
            return False

        cost_info = _get_cost(caster_idx, spell_name)
        if cost_info is None:
            if toast:
                toast("Cannot cast")
            return False
        lv, cost = cost_info

        # 対象決定（targetが不要なら caster_idx で仮置き）
        tgt_actor = None
        if (
            spell_name in HEAL_SPELLS
            or spell_name in RAISE_SPELLS
            or spell_name in STATUS_KEY_BY_SPELL
            or spell_name == "Esuna"
        ):
            if target_idx is None:
                if toast:
                    toast("Target required")
                return False
            tgt_actor = party[target_idx]
        else:
            # この版は回復/状態回復だけ。対象不要魔法は「未実装」で返す
            if toast:
                toast("Not implemented")
            return False

        # MP足りる？
        mp_pool = _mp_pool(caster)
        if int(mp_pool.get(lv, 0)) < cost:
            if toast:
                toast("MP not enough")
            return False

        changed = False

        # ---- Heal ----
        if spell_name in HEAL_SPELLS:
            amt = _heal_amount(spell_name, caster)
            if amt >= 9999:
                changed = _set_hp(tgt_actor, tgt_actor.max_hp) or changed
            else:
                changed = _set_hp(tgt_actor, int(tgt_actor.hp) + amt) or changed

        # ---- Raise / Arise ----
        elif spell_name in RAISE_SPELLS:
            if int(tgt_actor.hp) > 0:
                changed = False
            else:
                if spell_name == "Arise":
                    changed = _set_hp(tgt_actor, tgt_actor.max_hp)
                else:
                    # Raise は半分回復などにしたければここを変更
                    changed = _set_hp(tgt_actor, max(1, tgt_actor.max_hp // 2))

                # KO/石化などを savedata 側で持ってるならここで解除
                # changed = _clear_status(tgt_actor, "KO") or changed

        # ---- Single status cure ----
        elif spell_name in STATUS_KEY_BY_SPELL:
            key = STATUS_KEY_BY_SPELL[spell_name]
            changed = _clear_status(tgt_actor, key) or changed
            # Stona で Partial Petrification も消したいなら
            if spell_name == "Stona":
                changed = _clear_status(tgt_actor, "Partial Petrification") or changed

        # ---- Esuna ----
        elif spell_name == "Esuna":
            for k in list(ESUNA_CURES):
                changed = _clear_status(tgt_actor, k) or changed

        if not changed:
            if toast:
                toast("No effect")
            return False

        # 成功したので MP 消費
        if not _consume_mp(caster, lv, cost):
            # ここには来ないはず（上でチェック済み）
            return False

        # savedata 同期（任意）
        _sync_mp_to_save(caster)
        _sync_hp_status_to_save(tgt_actor)

        if toast:
            toast(f"{spell_name} OK")
        return True

    return cast_field_magic
