# ============================================================
# debug_utils: 開発用ツール

# print_final_equipment	最終装備出力
# print_party_member_stats	パーティメンバーのステータス出力
# find_inventory_like	所持アイテムを表示
# dump_inventory_candidates	所持アイテム表示

# _show_dict_of_lists	敵の所持アイテム出力用ヘルパ
# _show_item_list	敵の所持アイテム出力用ヘルパ
# print_enemy_status	敵1体を表示
# print_enemies_status	複数体まとめて表示

# check_battle_end_before_round	ラウンド開始前の生存チェック
# print_end_reason	SideTurnResult.end_reason の表示専用
# print_planned_actions	入力結果（planned_actions）をデバッグ表示する
# print_logs	戦闘ログをまとめて出力
# print_round_header_and_state	毎ターン冒頭の表示（ヘッダ + 状態行）
# ============================================================

from __future__ import annotations
from typing import Any, Dict, List, Optional, Iterable, Sequence, Mapping

from combat.models import PartyMemberRuntime, EnemyRuntime, PlannedAction
from combat.life_check import any_char_alive, any_enemy_alive, is_out_of_battle
from combat.state_view import format_state_line


def _item_name(x: Any) -> str:
    """装備が obj(name=...) / str / None どれでも表示できるようにする"""
    if x is None:
        return "（なし）"
    name = getattr(x, "name", None)
    return name if isinstance(name, str) and name else str(x)


def _yn(v: bool) -> str:
    return "✓" if v else "-"


def _fmt_row(row: Any) -> str:
    # row が "front" / "back" / Enum など揺れてもそれっぽく
    s = getattr(row, "name", None) or str(row)
    s = s.upper()
    if s in ("FRONT", "BACK"):
        return s
    if "front" in s.lower():
        return "FRONT"
    if "back" in s.lower():
        return "BACK"
    return s


def _fmt_elems(elems: Any) -> str:
    if not elems:
        return "-"
    # list[str] / tuple / set など
    try:
        return ",".join(map(str, elems))
    except TypeError:
        return str(elems)


def _fmt_resists(stats: Any) -> str:
    # resist/null/weak/absorb を 1行にまとめる（無い属性でも落ちない）
    parts = []
    for label, attr in [
        ("Resist", "elemental_resists"),
        ("Null", "elemental_nulls"),
        ("Weak", "elemental_weaks"),
        ("Absorb", "elemental_absorbs"),
    ]:
        v = getattr(stats, attr, None)
        if v:
            parts.append(f"{label}:{_fmt_elems(v)}")
    return " ".join(parts) if parts else "-"


def _print_equipment_with_combat_stats(pm: Any) -> None:
    eq = getattr(pm, "equipment", None)
    stats = getattr(pm, "stats", None)
    if eq is None or stats is None:
        print("  Equipment: （なし）")
        return

    main_name = _item_name(getattr(eq, "main_hand", None))
    off_name = _item_name(getattr(eq, "off_hand", None))

    # main/off の戦闘系ステータスは pm.stats から拾う（あなたの既存設計に合わせる）
    print(
        f"    main_hand: {main_name:<18}"
        f"MAIN(Pow{getattr(stats,'main_power',0)} "
        f"Acc{getattr(stats,'main_accuracy',0)} "
        f"x{getattr(stats,'main_atk_multiplier',0)} "
        f"2H{_yn(bool(getattr(stats,'main_two',False)))} "
        f"Long{_yn(bool(getattr(stats,'main_long',False)))} "
        f"Elem[{_fmt_elems(getattr(stats,'main_weapon_elements',None))}])"
    )
    print(
        f"    off_hand : {off_name:<18}"
        f"OFF (Pow{getattr(stats,'off_power',0)} "
        f"Acc{getattr(stats,'off_accuracy',0)} "
        f"x{getattr(stats,'off_atk_multiplier',0)} "
        f"2H{_yn(bool(getattr(stats,'off_two',False)))} "
        f"Long{_yn(bool(getattr(stats,'off_long',False)))} "
        f"Elem[{_fmt_elems(getattr(stats,'off_weapon_elements',None))}])"
        f"  Shield:{getattr(stats,'shield_count',0)}"
    )

    # 他部位
    for slot, label in [("head", "head"), ("body", "body"), ("arms", "arms")]:
        v = getattr(eq, slot, None)
        if v is not None:
            print(f"    {label:<8}: {_item_name(v)}")


def print_character_debug_summary(pm: Any, magic_list: Sequence[Any]) -> None:
    stats = pm.stats
    state = pm.state

    header = f"[{pm.name} / {pm.job.name}]"
    line1 = (
        f"Lv{stats.level}/J{stats.job_level} {_fmt_row(stats.row)}  "
        f"HP {state.hp}/{stats.max_hp}  "
        f"DEF{stats.defense}(×{stats.defense_multiplier}) "
        f"MDEF{stats.magic_defense}(×{stats.magic_def_multiplier})"
    )
    line2 = (
        f"  Stats: STR{stats.strength} AGI{stats.agility} VIT{stats.vitality} "
        f"INT{stats.intelligence} MND{stats.mind} | "
        f"Elem:{_fmt_elems(getattr(stats,'main_weapon_elements',None))} | "
        f"Shield:{getattr(stats,'shield_count',0)} | "
        f"{_fmt_resists(stats)}"
    )

    print(header)
    print(line1)
    print(line2)

    # 魔法一覧
    print("Available Magics:")
    if magic_list:
        for m in magic_list:
            print(f"  - {_item_name(m)}")
    else:
        print("  (None)")

    # 装備 + 戦闘ステ表示
    _print_equipment_with_combat_stats(pm)


# キャラクターステータス・装備出力
def print_party_debug_summary(
    party_members: Iterable[Any], party_magic_lists: Any
) -> None:
    """
    party_magic_lists が
      - dict[pm.id] -> list
      - list[list] (party_members と同順)
    のどちらでも受けられるようにする
    """
    members = list(party_members)

    if isinstance(party_magic_lists, Mapping):
        for pm in members:
            magic_list = party_magic_lists.get(getattr(pm, "id", pm), [])
            print_character_debug_summary(pm, magic_list)
            print("-" * 40)
    else:
        # list/tuple などを想定。長さが合わなくても落ちないようにする
        for i, pm in enumerate(members):
            magic_list = party_magic_lists[i] if i < len(party_magic_lists) else []
            print_character_debug_summary(pm, magic_list)
            print("-" * 40)


def print_inventory(
    save: dict,
    *,
    show_zero: bool = False,
    sort_by: str = "name",  # "name" or "qty"
    desc: bool = False,
    show_category_subtotal: bool = True,
) -> None:
    inv = (save or {}).get("inventory")
    if not isinstance(inv, dict):
        print("Inventory\n  (None)")
        return

    print("Inventory")

    grand_total = 0
    grand_kinds = 0

    for category, items in inv.items():
        if not isinstance(items, dict):
            continue

        # qty=0 の除外（デフォルトは除外）
        rows = [
            (name, int(qty))
            for name, qty in items.items()
            if show_zero or int(qty) != 0
        ]

        # 空カテゴリは飛ばす（必要ならここを消す）
        if not rows:
            continue

        # ソート
        if sort_by == "qty":
            rows.sort(key=lambda x: (x[1], x[0]), reverse=desc)
        else:
            rows.sort(key=lambda x: x[0])

        print(f"[{category}]")

        cat_total = 0
        for name, qty in rows:
            print(f"  {name:<22} x{qty:>3}")
            cat_total += qty

        grand_total += cat_total
        grand_kinds += len(rows)

        if show_category_subtotal:
            print(f"  -- subtotal: {cat_total} ({len(rows)} kinds)")

    print(f"Total items (sum of qty): {grand_total}")
    print(f"Total kinds: {grand_kinds}")


# ----------------------------
# small helpers
# ----------------------------
def _fmt_pct(v: Any) -> str:
    if v is None:
        return "-"
    try:
        return f"{int(v)}%"
    except Exception:
        return str(v)


def _fmt_acc_from_spell(v: Any) -> str:
    # spell側は 0.83 のようなfloatのことがあるので %
    if v is None:
        return "-"
    if isinstance(v, (int, float)):
        # 0-1 を想定
        if 0.0 <= float(v) <= 1.0:
            return f"{int(round(float(v) * 100))}%"
        return f"{int(round(float(v)))}%"
    return str(v)


def _fmt_rate(v: Any) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return str(v)


def _join_or_dash(v: Any) -> str:
    if not v:
        return "-"
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)


def _print_group(title: str, data: Optional[Dict[str, List[str]]]) -> None:
    """
    例:
    Elements:
      Resist: Lightning, Ice
      Weakness: Air
    """
    if not data:
        return
    rows = [(k, vals) for k, vals in data.items() if vals]
    if not rows:
        return
    print(f"{title}:")
    for k, vals in rows:
        label = str(k).strip().rstrip(":")
        print(f"  {label}: {', '.join(map(str, vals))}")


def _get_spell_dict(enemy_json: dict) -> Dict[str, dict]:
    spells = enemy_json.get("Spells", [])
    if not isinstance(spells, list):
        return {}
    out: Dict[str, dict] = {}
    for sp in spells:
        if isinstance(sp, dict) and sp.get("Name"):
            out[str(sp["Name"])] = sp
    return out


def _collect_items(enemy_json: dict) -> Dict[str, List[dict]]:
    return {
        "Steal": enemy_json.get("Stolen Items") or [],
        "Drop": enemy_json.get("Dropped Items") or [],
    }


def _print_item_block(enemy_json: dict) -> None:
    items = _collect_items(enemy_json)
    rows: List[str] = []

    for kind, arr in items.items():
        if not isinstance(arr, list):
            continue
        for it in arr:
            if not isinstance(it, dict):
                continue
            name = it.get("Item", "-")
            rate = it.get("StealRate", it.get("DropRate"))
            rows.append(f"  {kind}: {name} x{_fmt_rate(rate)}")

    if rows:
        print("Drops:")
        for line in rows:
            print(line)


# ----------------------------
# main
# ----------------------------
def print_enemy_status_compact(enemy) -> None:
    """
    希望フォーマットに寄せた compact 表示
    EnemyRuntime が name/stats/state/json を持つ想定
    """
    name = enemy.name
    s = enemy.stats
    st = enemy.state
    j = enemy.json or {}

    print(f"[{name}]")
    print(f"Lv{s.level}/J{s.job_level}  HP {st.hp}/{s.hp}")
    print(
        f"ATK{s.attack_power}(x{s.attack_multiplier}) ACC{_fmt_pct(s.accuracy_percent)} | "
        f"DEF{s.defense}(x{s.defense_multiplier}) EVA{_fmt_pct(s.evasion_percent)} | "
        f"MDEF{s.magic_defense}(x{s.magic_def_multiplier}) RES{_fmt_pct(getattr(s, 'magic_resistance_percent', None))}"
    )

    _print_group("Elements", j.get("ElementalVulnerability"))
    _print_group("Status", j.get("StatusAilmentVulnerability"))

    # --- Special attacks ---
    specials = j.get("Special Attacks") or []
    rate_total = j.get("SpecialAttackRate", None)
    spells_by_name = _get_spell_dict(j)

    if isinstance(specials, list) and specials:
        rt = _fmt_rate(rate_total)
        print(f"Special Attacks (rate total: {rt})")

        # 列幅（固定で十分）
        w_name = 12
        w_rate = 5
        w_type = 8
        w_pow = 5
        w_acc = 6
        w_mul = 3
        w_tgt = 14
        w_sta = 5

        for atk in specials:
            if not isinstance(atk, dict):
                continue
            atk_name = str(atk.get("Attack", "-"))
            atk_rate = atk.get("Rate", None)
            sp = spells_by_name.get(atk_name, {})

            sp_type = str(sp.get("Type", "-")).lower() if sp else "-"
            sp_pow = sp.get("Power", "-") if sp else "-"
            sp_acc = _fmt_acc_from_spell(sp.get("Accuracy", None)) if sp else "-"
            sp_mul = sp.get("Multiplier", "-") if sp else "-"
            sp_tgt = sp.get("Target", "-") if sp else "-"
            sp_sta = sp.get("Status", "-") if sp else "-"
            sp_elem = sp.get("Element", "-") if sp else "-"

            line = (
                f"  {atk_name:<{w_name}} "
                f"r{_fmt_rate(atk_rate):<{w_rate}}  "
                f"{sp_type:<{w_type}} "
                f"Pow{str(sp_pow):<{w_pow}} "
                f"Acc{sp_acc:<{w_acc}} "
                f"x{str(sp_mul):<{w_mul}} "
                f"{str(sp_tgt):<{w_tgt}} "
                f"{str(sp_sta):<{w_sta}} "
                f"Elem:{sp_elem}"
            )
            print(line)

    _print_item_block(j)


def print_enemies_status_compact(enemies: List[Any]) -> None:
    for e in enemies:
        print_enemy_status_compact(e)
        print("-" * 60)


# ==================================================
# ３．戦闘ターン
# ==================================================
def check_battle_end_before_round(
    party_members: List[PartyMemberRuntime],
    enemies: List[EnemyRuntime],
) -> Optional[str]:
    """
    ラウンド開始前の生存チェック。
    - 戻り値: None (継続) / "char_defeated" / "enemy_defeated"
    """
    if not any_char_alive(party_members):
        return "char_defeated"
    if not any_enemy_alive(enemies):
        return "enemy_defeated"
    return None


def print_end_reason(end_reason: str) -> None:
    """
    SideTurnResult.end_reason の表示専用。
    """
    if end_reason == "escaped":
        print("パーティは戦闘から離脱した！")
    elif end_reason == "enemy_defeated":
        print("敵は全滅した！")
    elif end_reason == "char_defeated":
        print("パーティは全滅した…")
    elif end_reason == "enemy_escaped":
        print("敵は逃げ出した！")
    else:
        # 想定外の理由も落とさず見える化
        print(f"[end_reason] {end_reason}")


def print_planned_actions(
    party_members: List[PartyMemberRuntime],
    planned_actions: List[Optional[PlannedAction]],
    prefix: str = "[Debug:planned]",
) -> None:
    """
    入力結果（planned_actions）をデバッグ表示する。
    """
    for i, member in enumerate(party_members):
        act = planned_actions[i] if i < len(planned_actions) else None
        if act is None:
            continue
        # out-of-battle も一応表示したいなら外さない
        if is_out_of_battle(member.state):
            continue

        print(
            f"{prefix}{member.name}, kind:{act.kind}, command:{act.command}, "
            f"spell:{getattr(act, 'spell_name', None)}, item:{getattr(act, 'item_name', None)}, "
            f"target:{getattr(act, 'target_side', None)}, index:{getattr(act, 'target_index', None)}"
        )


def print_logs(logs: List[str]) -> None:
    """
    戦闘ログをまとめて出力。
    """
    for line in logs:
        print(line)


def print_round_header_and_state(
    turn: int,
    party_members: List[PartyMemberRuntime],
    enemies: List[EnemyRuntime],
) -> None:
    """
    毎ターン冒頭の表示（ヘッダ + 状態行）。
    ※ これも debug_utils に置くとループがさらに薄くなります。
    """
    print(f"\n=== Turn {turn} ===")
    print("味方:")
    for pm in party_members:
        print("  " + format_state_line(pm.name, pm.state))
    print("敵:")
    for em in enemies:
        print("  " + format_state_line(em.name, em.state))
