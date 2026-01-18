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
from combat.enums import BattleKind
from combat.constants import FIELD_ITEM_TARGET_REQUIRED, STATUS_ENUM_BY_KEY
from combat.models import PlannedAction, TargetSide
from combat.inventory import build_item_list, is_item_visible_in_context
from combat.input_ui import normalize_battle_command
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import CommandCandidate
from ui_pygame.field_effects import (
    get_battle_state,
    set_hp,
    clear_status,
    sync_hp_status_to_save,
    sync_mp_to_save,
    dec_inventory_item,
    FIELD_ITEM_TYPES,
)


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
    "Poisona": "poison",
    "Blindna": "blind",
    "Stona": "petrification",  # Partial Petrification も消すなら下で追加
}

ESUNA_CURES = {
    "poison",
    "blind",
    "mini",
    "silence",
    "toad",
    "petrification",
    "partial petrification",
    "confusion",
    "sleep",
    "paralysis",
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
        # build_magic_fn から lv だけ引いて、cost は常に 1
        for n, lv, _cost in build_magic_fn(caster_idx):
            if str(n) == spell_name:
                return int(lv), 1
        return None

    def _mp_pool(actor):
        st = get_battle_state(actor)
        return st.mp_pool if st is not None else {}

    def _max_mp_pool(actor):
        st = get_battle_state(actor)
        return st.max_mp_pool if st is not None else {}

    def _consume_mp(actor, lv: int, cost: int) -> bool:
        mp_pool = _mp_pool(actor)
        cur = int(mp_pool.get(lv, 0))
        if cur < cost:
            return False
        mp_pool[lv] = cur - cost
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
                changed = set_hp(tgt_actor, tgt_actor.max_hp) or changed
            else:
                changed = set_hp(tgt_actor, int(tgt_actor.hp) + amt) or changed

        # ---- Raise / Arise ----
        elif spell_name in RAISE_SPELLS:
            if int(tgt_actor.hp) > 0:
                changed = False
            else:
                if spell_name == "Arise":
                    changed = set_hp(tgt_actor, tgt_actor.max_hp)
                else:
                    # Raise は半分回復などにしたければここを変更
                    changed = set_hp(tgt_actor, max(1, tgt_actor.max_hp // 2))

                # KO/石化などを savedata 側で持ってるならここで解除
                # changed = _clear_status(tgt_actor, "KO") or changed

        # ---- Single status cure ----
        elif spell_name in STATUS_KEY_BY_SPELL:
            key = STATUS_KEY_BY_SPELL[spell_name]
            changed = clear_status(tgt_actor, key, save_dict) or changed
            # Stona で Partial Petrification も消したいなら
            if spell_name == "Stona":
                changed = (
                    clear_status(tgt_actor, "Partial Petrification", save_dict)
                    or changed
                )

        # ---- Esuna ----
        elif spell_name == "Esuna":
            for k in list(ESUNA_CURES):
                changed = clear_status(tgt_actor, k, save_dict) or changed

        if not changed:
            if toast:
                toast("No effect")
            return False

        # 成功したので MP 消費
        if not _consume_mp(caster, lv, cost):
            # ここには来ないはず（上でチェック済み）
            return False

        # savedata 同期（任意）
        sync_mp_to_save(caster, save_dict, toast)
        sync_hp_status_to_save(tgt_actor, save_dict)

        if toast:
            mp_pool = _mp_pool(caster)
            max_mp_pool = _max_mp_pool(caster)
            remain = int(mp_pool.get(lv, 0))
            maxmp = int(max_mp_pool.get(lv, remain))
            toast(f"{spell_name} OK (MP{lv} {remain}/{maxmp})")

        print("[DBG] cast_field_magic called", caster_idx, spell_name, target_idx)

        return True

    return cast_field_magic


# アイテム使用ロジック（効果発現＋個数-1）
def make_use_field_item_fn(
    *,
    party,
    items_by_name: dict[str, dict],
    save_dict: Optional[dict] = None,
    toast: Optional[Callable[[str], None]] = None,
) -> Callable[[int, str, Optional[int], Optional[str]], bool]:

    def _canon(s: str) -> str:
        return str(s).strip().lower()

    def _needs_target(item_name: str) -> bool:
        return _canon(item_name) in FIELD_ITEM_TARGET_REQUIRED

    def _find_item_type(item_name: str, hint: str | None) -> str | None:
        if hint in FIELD_ITEM_TYPES:
            return hint
        if not isinstance(save_dict, dict):
            return None
        inv = save_dict.get("inventory", {})
        for itype in FIELD_ITEM_TYPES:
            b = inv.get(itype, {})
            if isinstance(b, dict) and int(b.get(item_name, 0) or 0) > 0:
                return itype
        return None

    def _heal_amount_by_item(item_name: str) -> int:
        n = _canon(item_name)
        if n == "potion":
            return 90
        if n in ("hi-potion", "hi potion"):
            return 360
        # if n == "elixir":  # ← 消す（ElixirはSpellEffectで処理する）
        #     return 9999
        return 0

    def _toast(msg: str) -> None:
        if toast:
            toast(msg)

    # Elixir（HP+MP全回復）
    def _restore_mp_all(tgt) -> bool:
        """MPを全回復。1つでも増えたらTrue"""
        st = get_battle_state(
            tgt
        )  # field_effects.py の get_battle_state を import 済み前提
        if st is None:
            return False
        changed = False
        for lv in range(1, 9):
            cur = int(st.mp_pool.get(lv, 0))
            mx = int(st.max_mp_pool.get(lv, cur))
            if cur < mx:
                st.mp_pool[lv] = mx
                changed = True
        return changed

    def _restore_mp_by_level(tgt, lv: int, amount: int) -> bool:
        """指定LvのMPを amount 回復（maxでクランプ）。増えたらTrue"""
        st = get_battle_state(tgt)
        if st is None:
            return False
        lv = int(lv)
        if not (1 <= lv <= 8):
            return False
        cur = int(st.mp_pool.get(lv, 0))
        mx = int(st.max_mp_pool.get(lv, cur))
        newv = min(mx, cur + int(amount))
        if newv == cur:
            return False
        st.mp_pool[lv] = newv
        return True

    # Ether 系（MP回復）
    def _mp_restore_by_item(item_name: str) -> tuple[int, int]:
        """
        (lv, amount) を返す。該当しなければ (0,0)
        例:
        ether -> Lv1 +1
        hi-ether -> Lv2 +1
        """
        n = _canon(item_name)
        if n == "ether":
            return (1, 1)
        if n in ("hi-ether", "hi ether"):
            return (2, 1)
        return (0, 0)

    def use_field_item(
        user_idx: int,
        item_name: str,
        target_idx: int | None,
        item_type_hint: str | None = None,
    ) -> bool:
        item = items_by_name.get(item_name, {})
        if not item:
            _toast("Item not found")
            return False

        itype_data = item.get("ItemType")
        if itype_data not in FIELD_ITEM_TYPES:
            _toast("Cannot use here")
            return False

        inv_type = _find_item_type(item_name, item_type_hint)
        if inv_type is None:
            _toast("Not in inventory")
            return False

        # 対象
        tgt = None
        if _needs_target(item_name):
            if target_idx is None:
                _toast("Target required")
                return False
            tgt = party[target_idx]

        changed = False
        msg: str | None = None  # ★成功時に表示するメッセージ

        spell_eff = item.get("SpellEffect")

        # -------------------------
        # (A) 回復アイテム
        # -------------------------
        amt = _heal_amount_by_item(item_name)
        if amt > 0:
            if tgt is None:
                _toast("Target required")
                return False

            before = int(tgt.hp)

            if amt >= 9999:
                changed_hp = set_hp(tgt, tgt.max_hp)
                changed_mp = _restore_mp_all(tgt)  # ★追加
                changed = (changed_hp or changed_mp) or changed
            else:
                changed = set_hp(tgt, int(tgt.hp) + amt) or changed

            after = int(tgt.hp)
            healed = max(0, after - before)

            if changed:
                # FFっぽい文言（日本語に寄せる）
                if amt >= 9999:
                    msg = f"{tgt.name} は HPとMPが ぜんかいふくした！"
                else:
                    msg = f"{tgt.name} の HPが {healed} かいふくした！"

        # -------------------------
        # (B) SpellEffect 系（状態回復/蘇生など）
        # -------------------------
        elif isinstance(spell_eff, str) and spell_eff:
            se = str(spell_eff)

            if se == "Poisona":
                if tgt is None:
                    _toast("Target required")
                    return False
                changed = clear_status(tgt, "poison", save_dict) or changed
                if changed:
                    msg = f"{tgt.name} の どく が なおった！"

            elif se == "Blindna":
                if tgt is None:
                    _toast("Target required")
                    return False
                changed = clear_status(tgt, "blind", save_dict) or changed
                if changed:
                    msg = f"{tgt.name} の くらやみ が なおった！"

            elif se == "Stona":
                if tgt is None:
                    _toast("Target required")
                    return False
                changed = clear_status(tgt, "petrification", save_dict) or changed
                changed = (
                    clear_status(tgt, "partial petrification", save_dict) or changed
                )
                if changed:
                    msg = f"{tgt.name} の せきか が なおった！"

            elif se in ("Raise", "Arise"):
                if tgt is None:
                    _toast("Target required")
                    return False

                if int(tgt.hp) > 0:
                    changed = False
                else:
                    # KO解除（あなたのキーに合わせる）
                    clear_status(tgt, "ko", save_dict)
                    before = int(tgt.hp)
                    changed = set_hp(tgt, max(1, tgt.max_hp // 2)) or changed
                    if changed:
                        msg = f"{tgt.name} は いきかえった！"

            elif se == "Elixir":
                if tgt is None:
                    _toast("Target required")
                    return False

                changed_hp = set_hp(tgt, tgt.max_hp)
                changed_mp = _restore_mp_all(tgt)
                changed = (changed_hp or changed_mp) or changed

                if changed:
                    msg = f"{tgt.name} は HPとMPが ぜんかいふくした！"

            else:
                _toast("Not implemented")
                return False

        else:
            _toast("Not implemented")
            return False

        # 効果なし
        if not changed:
            _toast("No effect")
            return False

        # 個数-1
        if isinstance(save_dict, dict):
            if not dec_inventory_item(save_dict, inv_type, item_name):
                _toast("Inventory error")
                return False

        # save反映
        if tgt is not None and isinstance(save_dict, dict):
            sync_hp_status_to_save(tgt, save_dict)
            sync_mp_to_save(tgt, save_dict)  # ★追加

        # ★成功メッセージ（なければ従来通り）
        _toast(msg or f"{item_name} OK")
        return True

    return use_field_item
