# ============================================================
# spell_repo: 魔法定義の検索・参照

# spell_from_json	魔法JSON1件からSpellInfoを構築
# _choose_monster_special_spell	敵の生データ（monster JSON）から、使用すべきスペル定義を“検索・決定”する関数
# _find_spell_json_for_enemy_attack	敵攻撃結果（special等）から対応するSpellJSONを引き直すためのヘルパ
# _find_monster_spell_definition	monsters.jsonやMASTER_SPELLS_BY_NAMEから敵が使うスペル定義を検索・取得するヘルパー
# <魔法DBを参照してモンスター側スペル定義を正規化・補完する>
# _spell_name_of	表記ゆれの補正
# _merge_spell_defs	DB(master_def) をベースに、monster_def で上書きする。
# enrich_monster_spell	smonster_json を破壊せず、Spells 等を魔法DBで補完した新しい dict を返す。
# ============================================================

import random
from typing import Optional, Dict, Any
from copy import deepcopy

from combat.models import SpellInfo, EnemyAttackResult
from combat.constants import MASTER_SPELLS_BY_NAME
from combat.elements import parse_elements


def spell_from_json(spell_json: Dict[str, Any]) -> SpellInfo:
    raw_type = str(spell_json.get("Type", "")).lower().strip()

    # Summon Magic 親の「Power最大の子を選ぶロジック」を削除
    """
    # ----------------------------------------
    # 1) Summon Magic（親：Titan / Bahamut など）
    # ----------------------------------------
    if "summon magic" in raw_type:
        inner_spells = spell_json.get("Spells") or []

        if inner_spells:
            candidates = [s for s in inner_spells if s.get("Power") is not None]
            chosen = max(candidates, key=lambda s: s.get("Power", 0)) if candidates else inner_spells[0]

            elem_raw = chosen.get("Element") or chosen.get("Elements") or ""
            elements: list[str] = parse_elements(elem_raw)

            power = int(chosen.get("Power") or 0)

            acc_raw = chosen.get("Accuracy", 100)
            if acc_raw is None:
                base_acc = 1.0
            else:
                acc_raw = float(acc_raw)
                base_acc = acc_raw / 100.0 if acc_raw > 1.0 else acc_raw
            acc_percent = int(round(base_acc * 100))

            return SpellInfo(
                power=power,
                accuracy_percent=acc_percent,
                magic_type="other",
                elements=elements,
            )

        return SpellInfo(
            power=0,
            accuracy_percent=100,
            magic_type="other",
            elements=[],
        )
    """

    # ----------------------------------------
    # 2) Summon（子：Titan: Earthen Fury など）
    # ----------------------------------------
    if raw_type == "summon" or raw_type.startswith("summon"):
        elem_raw = spell_json.get("Element") or spell_json.get("Elements") or ""
        elements: list[str] = parse_elements(elem_raw)

        power = int(spell_json.get("Power") or spell_json.get("BasePower") or 0)

        acc_raw = spell_json.get("Accuracy") or spell_json.get("BaseAccuracy") or 100
        acc_raw = float(acc_raw)
        base_acc = acc_raw / 100.0 if acc_raw > 1.0 else acc_raw
        acc_percent = int(round(base_acc * 100))

        return SpellInfo(
            power=power,
            accuracy_percent=acc_percent,
            magic_type="summon",
            elements=elements,
        )

    # ----------------------------------------
    # 3) Black / White / その他（従来）
    # ----------------------------------------
    elem_raw = spell_json.get("Element") or spell_json.get("Elements")
    elements: list[str] = parse_elements(elem_raw)

    power = int(spell_json.get("BasePower", 0))
    base_acc = float(spell_json.get("BaseAccuracy", 0.0) or 0.0)
    acc_percent = int(round(base_acc * 100))

    if "black" in raw_type:
        magic_type = "black"
    elif "white" in raw_type:
        magic_type = "white"
    else:
        magic_type = "other"

    return SpellInfo(
        power=power,
        accuracy_percent=acc_percent,
        magic_type=magic_type,
        elements=elements,
    )


# ============================================================
# 敵スペシャル攻撃ヘルパ
# ============================================================


def _choose_monster_special_spell(
    monster: Dict[str, Any],
    rng: Optional[random.Random] = None,
) -> Optional[Dict[str, Any]]:
    """
    モンスター JSON から 1 つスペシャル攻撃用 Spell を選ぶ。
    ・"Special Attacks" の Rate による重み付き抽選で Attack 名を選ぶ
    ・monster["Spells"] 内の Name == Attack のものを返す
    見つからなければ None を返す。
    """
    if rng is None:
        rng = random.Random()

    specials = monster.get("Special Attacks") or []
    if not specials:
        return None

    total_rate = sum((sa.get("Rate") or 0) for sa in specials)
    if total_rate <= 0:
        return None

    r = rng.random() * total_rate
    acc = 0.0
    chosen_attack_name = None
    for sa in specials:
        rate = sa.get("Rate") or 0.0
        acc += rate
        if r <= acc:
            chosen_attack_name = sa.get("Attack")
            break

    if not chosen_attack_name:
        return None

    spell_list = monster.get("Spells") or []
    for s in spell_list:
        if s.get("Name") == chosen_attack_name:
            return s

    return None


# まず Spell 定義を引けるようにする
# enemy_attack が special のときに Spell JSON を引き直すヘルパ
def _find_spell_json_for_enemy_attack(
    monster: Dict[str, Any],
    enemy_attack: EnemyAttackResult,
) -> Optional[Dict[str, Any]]:
    if enemy_attack.attack_name is None:
        return None
    return _find_monster_spell_definition(monster, enemy_attack.attack_name)


# 敵が使うスペルの JSON 定義を取得
def _find_monster_spell_definition(
    monster: Dict[str, Any], spell_name: str
) -> Optional[Dict[str, Any]]:
    """
    モンスターが使うスペルの JSON 定義を取得する。
    ・Name（または name）の大小文字を問わず一致させる
    ・子召喚などを含む場合は spells_by_name（MASTER_SPELLS_BY_NAME）からの fallback も可能

    戻り値:
        Spell の dict（spells.json 形式）または None
    """
    if not spell_name:
        return None

    sname = spell_name.strip().lower()

    # 1) モンスターの Spells セクションを探す（最優先）
    spells = monster.get("Spells") or monster.get("spells") or []
    for sp in spells:
        nm = (sp.get("Name") or sp.get("name") or "").strip().lower()
        if nm == sname:
            return sp

    # 2) 次に、本体の spells.json (MASTER_SPELLS_BY_NAME) から引く
    #    expand_spells_for_summons() を使っている場合、子召喚もここに入る
    global MASTER_SPELLS_BY_NAME
    if MASTER_SPELLS_BY_NAME:
        sp = MASTER_SPELLS_BY_NAME.get(spell_name)
        if sp:
            return sp
        # 大文字小文字ゆれにも対応
        for nm, js in MASTER_SPELLS_BY_NAME.items():
            if nm.lower() == sname:
                return js

    return None


# =========================
# 魔法DBを参照してモンスター側スペル定義を正規化・補完する
# =========================
def _spell_name_of(d: Dict[str, Any]) -> Optional[str]:
    return (d.get("Name") or d.get("name") or "").strip() or None


def _merge_spell_defs(
    monster_def: Dict[str, Any], master_def: Dict[str, Any]
) -> Dict[str, Any]:
    """
    DB(master_def) をベースに、monster_def で上書きする。
    ＝Reflectable/Target/Element 等はDBから補完され、Power等は敵固有が優先される。
    """
    merged = dict(master_def or {})
    merged.update(monster_def or {})

    # Name は揃えておく（どちらかに寄せる）
    if "Name" not in merged and "name" in merged:
        merged["Name"] = merged["name"]
    if "name" not in merged and "Name" in merged:
        merged["name"] = merged["Name"]

    return merged


def enrich_monster_spells(
    monster_json: Dict[str, Any], spells_by_name: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    monster_json を破壊せず、Spells 等を魔法DBで補完した新しい dict を返す。
    """
    mj = deepcopy(monster_json)

    # --- 1) Spells（モンスターが使う魔法一覧） ---
    spells = mj.get("Spells")
    if isinstance(spells, list):
        new_spells = []
        for s in spells:
            if not isinstance(s, dict):
                new_spells.append(s)
                continue

            nm = _spell_name_of(s)
            if not nm:
                new_spells.append(s)
                continue

            master = spells_by_name.get(nm) or spells_by_name.get(nm.lower())
            if isinstance(master, dict):
                new_spells.append(_merge_spell_defs(s, master))
            else:
                new_spells.append(s)

        mj["Spells"] = new_spells

    # --- 2) Special Attacks（ここに spell も混ざる設計なら同様に補完） ---
    specials = mj.get("Special Attacks")
    if isinstance(specials, list):
        new_specials = []
        for a in specials:
            if not isinstance(a, dict):
                new_specials.append(a)
                continue

            nm = _spell_name_of(a)
            if not nm:
                new_specials.append(a)
                continue

            # 「魔法DBに存在する名前なら補完」くらいの緩い判定でOK
            master = spells_by_name.get(nm) or spells_by_name.get(nm.lower())
            if isinstance(master, dict):
                new_specials.append(_merge_spell_defs(a, master))
            else:
                new_specials.append(a)

        mj["Special Attacks"] = new_specials

    return mj
