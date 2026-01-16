# ============================================================
# input_ui: ユーザー入力

# normalize_battle_command	バトルコマンド文字列をBattleKindに正規化
# choose_magic	Lv別の魔法一覧を表示し、ユーザーに番号入力で魔法を選ばせて選択された魔法名を返す
# categorize_anywhere_item	アイテムのEffectテキストからキーワードを判定し、Anywhereアイテムをカテゴリ名に割り振る。
# categorize_combat_item	アイテムのEffectテキストからキーワードを判定し、Combatアイテムをカテゴリ名に割り振る。
# build_grouped_item_menu	Anywhere/Combat別、細分別に表示順のアイテム名リスト（番号→名前対応用）を返す。
# choose_item	効果別にグループ化されたアイテムメニューを表示し、ユーザーに番号で選ばせて選択されたアイテム名を返す
# ask_action_for_member	戦闘コマンドをインタラクティブに入力させてPlannedActionを組み立てて返す関数
# ask_actions_for_party	パーティ全員分の行動入力を行い、planned_actions を返す
# ============================================================

from __future__ import annotations

from typing import Dict, Any, Tuple, List, Optional, Callable
from collections import defaultdict
import unicodedata

from combat.constants import COMMAND_TO_KIND
from combat.enums import BattleKind
from combat.models import (
    BattleActorState,
    PartyMemberRuntime,
    EnemyRuntime,
    PlannedAction,
)
from combat.magic_menu import print_magic_menu_by_level, print_magic_menu_by_level
from combat.state_view import format_state_line
from combat.life_check import (
    choose_target_index_from_enemies,
    choose_target_index_from_allies,
    is_out_of_battle,
    first_alive_enemy_index,
)
from combat.inventory import build_item_list, is_item_visible_in_context


# 1) コマンド正規化 ===========================================================================
def _normalize_command_key(cmd: str) -> str:
    """
    battle command 用の最小正規化
    - NFKC（全角半角/互換文字）
    - strip
    - 全角空白→半角空白
    - 連続空白の正規化
    - lower（大小文字ゆれ吸収）
    """
    s = unicodedata.normalize("NFKC", cmd)
    s = s.strip().replace("　", " ")
    s = " ".join(s.split())
    return s.lower()


# COMMAND_TO_KIND は「正規化済みキー」で引けるようにする
_COMMAND_TO_KIND_NORM: Dict[str, BattleKind] = {
    _normalize_command_key(k): v for k, v in COMMAND_TO_KIND.items()
}


def normalize_battle_command(cmd: str) -> BattleKind:
    """
    コマンド文字列から BattleKind を返す。
    未知のコマンドは安全側で "special" に寄せる。
    """
    if not cmd:
        return "physical"

    key = _normalize_command_key(cmd)
    return _COMMAND_TO_KIND_NORM.get(key, "special")


def choose_magic(char_state: BattleActorState, magic_list) -> str:
    """
    magic_list から番号で魔法を選ばせて「魔法名」を返す。
    表示は Lv別まとめ形式。
    """
    if not magic_list:
        print("使用可能な魔法が定義されていません。")
        return ""

    print("使用する魔法を選んでください。")
    print_magic_menu_by_level(magic_list, char_state)

    while True:
        s = input(f"番号を入力してください (1-{len(magic_list)}): ").strip()
        if s.isdigit():
            n = int(s)
            if 1 <= n <= len(magic_list):
                spell_name, _, _ = magic_list[n - 1]
                return spell_name
        print("入力が正しくありません。")


def categorize_anywhere_item(effect_text: str) -> str:
    e = effect_text.lower()
    if "revive from ko" in e:
        return "Revive"
    if "cure " in e:
        return "Cure"
    if "restore" in e:
        return "Restore"
    return "Other"


def categorize_combat_item(effect_text: str) -> str:
    e = effect_text.lower()
    if "deal" in e and "damage" in e:
        return "Damage"
    if "inflict " in e:
        return "Inflict"
    return "Support"


def build_grouped_item_menu(
    item_list: List[Tuple[str, str, int]],  # [(name, itype, qty), ...]
    items_by_name: Dict[str, Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    anywhere_buckets = defaultdict(list)  # {cat: [(name, qty), ...]}
    combat_buckets = defaultdict(list)

    for name, itype, qty in item_list:
        if qty <= 0:
            continue

        item_json = items_by_name.get(name, {})
        spell_info = item_json.get("SpellInfo") or {}
        effect_text = spell_info.get("Effect") or ""

        t = (itype or "").strip().lower()
        if t == "anywhere":
            cat = categorize_anywhere_item(effect_text)
            anywhere_buckets[cat].append((name, qty))
        elif t == "combat":
            cat = categorize_combat_item(effect_text)
            combat_buckets[cat].append((name, qty))
        else:
            anywhere_buckets["Other"].append((name, qty))

    anywhere_order = ["Restore", "Revive", "Cure", "Other"]
    combat_order = ["Damage", "Inflict", "Support"]

    label_anywhere = {
        "Restore": "Restore（回復）",
        "Revive": "Revive（蘇生）",
        "Cure": "Cure（治療）",
        "Other": "Other（その他）",
    }
    label_combat = {
        "Damage": "Damage（攻撃）",
        "Inflict": "Inflict（状態異常）",
        "Support": "Support（補助/その他）",
    }

    ELEMENT_ORDER = {
        "": 0,
        "none": 0,
        "-": 0,
        "ice": 1,
        "wind": 2,
        "lightning": 3,
        "thunder": 3,
        "earth": 4,
        "holy": 5,
        "dark": 6,
        "fire": 7,
    }

    def damage_sort_key(name: str):
        item_json = items_by_name.get(name, {})
        spell_info = item_json.get("SpellInfo") or {}

        elem_raw = spell_info.get("Element") or spell_info.get("Elements") or ""
        if isinstance(elem_raw, list):
            elem = elem_raw[0] if elem_raw else ""
        else:
            elem = str(elem_raw)

        elem_l = elem.strip().lower()
        elem_rank = ELEMENT_ORDER.get(elem_l, 99)

        power = spell_info.get("BasePower")
        if power is None:
            power = item_json.get("Value", 0) or 0
        power = int(power)

        return (elem_rank, -power, name)

    if combat_buckets.get("Damage"):
        combat_buckets["Damage"].sort(key=lambda x: damage_sort_key(x[0]))

    # ---- ここから「出力生成」：print しない ----
    lines: List[str] = []
    shown_names: List[str] = []
    idx = 1

    def append_category_block(
        header: str, order: List[str], labels: Dict[str, str], buckets
    ):
        nonlocal idx
        if not any(buckets.get(c) for c in order):
            return

        lines.append(header)
        for cat in order:
            entries: List[Tuple[str, int]] = buckets.get(cat, [])
            if not entries:
                continue

            # 1行にまとめる（あなたの元の表示形式を踏襲）
            parts = []
            for n, q in entries:
                parts.append(f"{idx}: {n}({q})")
                shown_names.append(n)
                idx += 1

            cat_label = labels.get(cat, cat)
            lines.append(f"  {cat_label}: " + ", ".join(parts))

    append_category_block(
        "【Anywhere】", anywhere_order, label_anywhere, anywhere_buckets
    )
    append_category_block("【Combat】", combat_order, label_combat, combat_buckets)

    return lines, shown_names


def choose_item(
    items_by_name,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> str:
    """
    ITEM_LIST から番号でアイテムを選ばせて、選ばれた「アイテム名」を返す。
    Effect分類つき表示版。
    """
    if not ITEM_LIST:
        output_func("使用可能なアイテムがありません。")
        return ""

    output_func("使用するアイテムを選んでください。")

    lines, menu_order = build_grouped_item_menu(ITEM_LIST, items_by_name)
    if not menu_order:
        output_func("使用可能なアイテムがありません。")
        return ""

    for line in lines:
        output_func(line)

    while True:
        s = input_func(f"番号を入力してください (1-{len(menu_order)}): ").strip()
        if s.isdigit():
            n = int(s)
            if 1 <= n <= len(menu_order):
                return menu_order[n - 1]
        output_func("入力が正しくありません。")


# 各メンバーから「行動だけ」入力させる関数
# ※ここでは 単純化のため に：各キャラの魔法リスト・アイテムリストは
# 既存の MAGIC_LIST / ITEM_LIST をそのまま使う形にしています。
# 実際は build_magic_list や build_item_list をキャラごとに呼ぶとさらに自然です。
def ask_action_for_member(
    member_index: int,
    party_members: List[PartyMemberRuntime],
    enemies: List[EnemyRuntime],
    spells_by_name: Dict[str, Dict[str, Any]],
    items_by_name: Dict[str, Dict[str, Any]],
    party_magic_lists,  # ★ 追加：キャラごとの magic_list の配列
    save: dict,
) -> PlannedAction:
    member = party_members[member_index]
    job_data = member.job

    # --- ジョブの戦闘コマンドを表示 ---
    commands = [
        job_data.raw[f"BattleCommand{i}"]["Command"]
        for i in range(1, 5)
        if job_data.raw.get(f"BattleCommand{i}")
    ]
    if not commands:
        commands = ["Fight", "Defend", "Item", "Run"]

    print(f"\n{member.name} の行動を選んでください。")
    print(format_state_line(member.name, member.state))
    for idx, cmd in enumerate(commands, start=1):
        print(f"  {idx}: {cmd}")

    while True:
        s = input(f"番号を入力してください (1-{len(commands)}): ").strip()
        if s.isdigit() and 1 <= int(s) <= len(commands):
            selected_command = commands[int(s) - 1]
            break
        print("入力が正しくありません。")

    normalized_kind = normalize_battle_command(selected_command)
    print(f"[Debug:input_ui]《{normalized_kind}》{selected_command} が選択されました。")

    # special: 対象不要
    SPECIAL_NO_TARGET = {"Cheer", "Scare", "Flee", "Terrain", "Boost"}

    # special: 敵単体
    SPECIAL_ENEMY_TARGET = {
        "Steal",
        "Peep",
        "Study",
    }  # もし special 扱いなら

    if normalized_kind == "special":
        if selected_command in SPECIAL_NO_TARGET:
            return PlannedAction(
                kind="special",
                command=selected_command,
                target_side="ally",
                target_index=None,
                target_all=True,  # 味方全体にしておく
            )

        if selected_command in SPECIAL_ENEMY_TARGET:
            t_idx = choose_target_index_from_enemies(enemies)
            return PlannedAction(
                kind="special",
                command=selected_command,
                target_side="enemy",
                target_index=t_idx,
            )

        # 未分類 special は一旦「自分」扱いにするなど
        return PlannedAction(
            kind="special",
            command=selected_command,
            target_side="self",
            target_index=member_index,
        )

    if normalized_kind == "jump":
        t_idx = choose_target_index_from_enemies(enemies)
        return PlannedAction(
            kind="jump",
            command="Jump",
            target_side="enemy",
            target_index=t_idx,
        )

    # =========================
    # 物理 / special
    # =========================
    if normalized_kind == "physical":
        t_idx = choose_target_index_from_enemies(enemies)
        if t_idx is None:
            # ターゲットがいない → 一応 Fight だが実質何もできない
            return PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=None,
            )

        return PlannedAction(
            kind=normalized_kind,
            command=selected_command,
            target_side="enemy",
            target_index=t_idx,
        )

    # =========================
    # Defend / Run
    # =========================
    if normalized_kind == "defend":
        return PlannedAction(
            kind="defend",
            command="Defend",
            target_side="self",
            target_index=member_index,
        )

    if normalized_kind == "run":
        return PlannedAction(
            kind="run",
            command=selected_command,
            target_side="self",
            target_index=member_index,
        )

    # =========================
    # Magic
    # =========================
    if normalized_kind == "magic":
        magic_list = party_magic_lists[member_index]  # ★ このメンバーの魔法メニュー
        spell_name = choose_magic(member.state, magic_list)
        if not spell_name:
            print("魔法が選択されなかったため、物理攻撃として扱います。")
            t_idx = choose_target_index_from_enemies(enemies)
            return PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=t_idx,
            )

        print("魔法の対象を選んでください。")
        print("  1: 敵単体")
        print("  2: 味方単体")
        print("  3: 自分")

        while True:
            s = input("番号を入力してください (1-3): ").strip()
            if s == "1":
                t_side = "enemy"
                t_idx = choose_target_index_from_enemies(enemies)
                break
            elif s == "2":
                t_side = "ally"
                t_idx = choose_target_index_from_allies(party_members, member_index)
                break
            elif s == "3":
                t_side = "self"
                t_idx = member_index
                break
            print("入力が正しくありません。")

        return PlannedAction(
            kind="magic",
            command=selected_command,
            spell_name=spell_name,
            target_side=t_side,
            target_index=t_idx,
        )

    # =========================
    # Item
    # =========================
    if normalized_kind == "item":
        # 戦闘用 ITEM_LIST を生成
        item_list = build_item_list(items_by_name, save, in_battle=True)
        item_list = [
            (name, itype, qty)
            for (name, itype, qty) in item_list
            if is_item_visible_in_context(items_by_name.get(name, {}), in_combat=True)
        ]
        if not item_list:
            print("使用可能なアイテムがないため、物理攻撃として扱います。")
            t_idx = choose_target_index_from_enemies(enemies)
            return PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=t_idx,
            )

        # 既存の choose_item() はグローバル ITEM_LIST を見る前提なので更新
        global ITEM_LIST
        ITEM_LIST = item_list

        item_name = choose_item(items_by_name)  # ユーザーにアイテムを選んでもらう
        if not item_name:
            print("アイテムが選択されなかったため、物理攻撃として扱います。")
            t_idx = choose_target_index_from_enemies(enemies)
            return PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=t_idx,
            )

        print("アイテムの使用対象を選んでください。")
        print("  1: 敵単体")
        print("  2: 味方単体")
        print("  3: 自分")

        while True:
            s = input("番号を入力してください (1-3): ").strip()
            if s == "1":
                t_side = "enemy"
                t_idx = choose_target_index_from_enemies(enemies)
                break
            elif s == "2":
                t_side = "ally"
                t_idx = choose_target_index_from_allies(party_members, member_index)
                break
            elif s == "3":
                t_side = "self"
                t_idx = member_index
                break
            print("入力が正しくありません。")

        return PlannedAction(
            kind="item",
            command=selected_command,
            item_name=item_name,  # ★ここがポイント
            target_side=t_side,
            target_index=t_idx,
        )

    # =========================
    # フォールバック
    # =========================
    print(f"《{selected_command}》は未実装のため、物理攻撃として扱います。")
    t_idx = choose_target_index_from_enemies(enemies)
    return PlannedAction(
        kind="physical",
        command="Fight",
        target_side="enemy",
        target_index=t_idx,
    )


# パーティ全員分の行動入力を行い、planned_actions を返す
def ask_actions_for_party(
    *,
    party_members: List[PartyMemberRuntime],
    enemies: List[EnemyRuntime],
    spells_by_name: Dict[str, Dict[str, Any]],
    items_by_name: Dict[str, Dict[str, Any]],
    party_magic_lists: List[Any],  # build_magic_list の戻り型に合わせて
    save: dict,
) -> List[Optional[PlannedAction]]:
    """
    パーティ全員分の行動入力を行い、planned_actions を返す。
    ループ側は「これを呼ぶだけ」にする。
    """
    planned_actions: List[Optional[PlannedAction]] = [None] * len(party_members)

    for i, member in enumerate(party_members):
        if is_out_of_battle(member.state):
            continue

        # ★ ③：ジャンプ中なら入力をスキップして「降下攻撃」を予約
        if getattr(member.state, "is_jumping", False):
            t_idx = getattr(member.state, "jump_target_index", None)

            # ターゲットが死んでたら生存してる敵に差し替え
            if (
                t_idx is None
                or t_idx >= len(enemies)
                or is_out_of_battle(enemies[t_idx].state)
            ):
                t_idx = first_alive_enemy_index(enemies)

            planned_actions[i] = PlannedAction(
                kind="special",
                command="JumpDive",  # ★ 区別用（名前は好きに）
                target_side="enemy",
                target_index=t_idx,
            )
            continue

        # 通常入力
        planned_actions[i] = ask_action_for_member(
            member_index=i,
            party_members=party_members,
            enemies=enemies,
            spells_by_name=spells_by_name,
            items_by_name=items_by_name,
            party_magic_lists=party_magic_lists,
            save=save,
        )

    return planned_actions
