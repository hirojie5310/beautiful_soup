# ============================================================
# elements: 属性

# parse_elements	"Air,Ice"/["Air",Ice]/None/"-"を想定してElementsを正規化
# _expand_synonyms	属性名リストをシノニム展開してsetで返す
# element_relation_and_hits_generic	攻撃属性と弱点/耐性/吸収/無効テーブルから属性相性とヒット属性集合を求める汎用関数
# element_relation_and_hits_for_monster	モンスターのElementalVulnerabilityと攻撃属性から属性相性とヒット属性を求めるラッパー,
# element_relation_for_monster	モンスターに対する属性相性（relation）だけを取得する薄いラッパー
# element_relation_and_hits_for_char	キャラ側の属性弱点/耐性/吸収/無効と攻撃属性から属性相性とヒット属性を求めるラッパー
# apply_element_relation_to_damage	属性相性（弱点/耐性/吸収/無効）に応じてダメージ値を補正する
# elements_from_monster_spell	モンスターのスペル定義からElement/Elementsを解析し、属性リストに正規化して返すヘルパー
# ============================================================

from __future__ import annotations

from typing import Dict, Any, Iterable

from combat.constants import _ELEMENT_SYNONYMS
from combat.enums import ElementRelation
from combat.models import FinalCharacterStats


# ============================================================
# JSON からの Elements パースの共通化
# ============================================================


def parse_elements(raw_elems) -> list[str]:
    """
    "Air, Ice" / ["Air","Ice"] / None / "-" を想定して
    トリム済み・小文字 list を返す共通ヘルパ
    """
    if not raw_elems or raw_elems == "-":
        return []

    if isinstance(raw_elems, str):
        elems = [e.strip().lower() for e in raw_elems.split(",") if e.strip()]
    elif isinstance(raw_elems, list):
        elems = [str(e).strip().lower() for e in raw_elems if str(e).strip()]
    else:
        elems = []

    return elems


# ============================================================
# 相性を求める共通関数（「弱点/耐性/吸収/無効の4セット」と「攻撃側の属性」から）
# ============================================================


def _expand_synonyms(elems: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for e in elems:
        out |= _ELEMENT_SYNONYMS.get(e, {e})
    return out


def element_relation_and_hits_generic(
    attack_elements: list[str] | None,
    *,
    weak: Iterable[str] = (),
    resist: Iterable[str] = (),
    absorb: Iterable[str] = (),
    null: Iterable[str] = (),
) -> tuple[ElementRelation, list[str]]:
    """
    弱点/耐性/吸収/無効の候補と attack_elements から
    (relation, hit_elements) を返す汎用関数。
    hit_elements はマッチした属性名（小文字, ソート済み）。
    """
    elems = _expand_synonyms(parse_elements(attack_elements))
    if not elems:
        return "normal", []

    absorbs = _expand_synonyms(parse_elements(absorb))
    nulls = _expand_synonyms(parse_elements(null))
    resists = _expand_synonyms(parse_elements(resist))
    weaks = _expand_synonyms(parse_elements(weak))

    if elems & absorbs:
        return "absorb", sorted(elems & absorbs)
    if elems & nulls:
        return "null", sorted(elems & nulls)
    if elems & weaks:
        return "weak", sorted(elems & weaks)
    if elems & resists:
        return "resist", sorted(elems & resists)
    return "normal", []


# モンスター用ラッパ関数
def element_relation_and_hits_for_monster(
    monster: dict[str, Any],
    attack_elements: list[str] | None,
) -> tuple[ElementRelation, list[str]]:
    """
    monster["ElementalVulnerability"] と attack_elements から
    (relation, hit_elements) を返す。
    """
    ev = monster.get("ElementalVulnerability", {}) or {}

    return element_relation_and_hits_generic(
        parse_elements(attack_elements),  # ★ 攻撃側も正規化
        weak=parse_elements(ev.get("Weakness")),
        resist=parse_elements(ev.get("Resistance")),
        absorb=parse_elements(ev.get("Absorb")),
        null=parse_elements(ev.get("Null")),
    )


def element_relation_for_monster(
    monster: dict[str, Any],
    attack_elements: list[str] | None,
) -> ElementRelation:
    """
    互換用： relation だけ欲しい場合。
    既存コードを壊さないための薄いラッパ。
    """
    relation, _ = element_relation_and_hits_for_monster(monster, attack_elements)
    return relation


def element_relation_for_char(
    char: FinalCharacterStats,
    attack_elements: list[str] | None,
) -> ElementRelation:
    """
    互換用： relation だけ欲しい場合。
    既存コードを壊さないための薄いラッパ。
    """
    relation, _ = element_relation_and_hits_for_char(char, attack_elements)
    return relation


# キャラ用ラッパ関数
def element_relation_and_hits_for_char(
    char: FinalCharacterStats,
    attack_elements: list[str] | None,
) -> tuple[ElementRelation, list[str]]:
    """
    キャラの elemental_* と attack_elements から
    (relation, hit_elements) を返す。
    """
    return element_relation_and_hits_generic(
        attack_elements,
        weak=char.elemental_weaks,
        resist=char.elemental_resists,
        absorb=char.elemental_absorbs,
        null=char.elemental_nulls,
    )


# 属性相性をダメージに反映
def apply_element_relation_to_damage(damage: int, relation: ElementRelation) -> int:
    """属性相性をダメージに反映"""
    if relation == "weak":
        return damage * 2
    if relation == "resist":
        return int(damage * 0.5)
    if relation == "absorb":
        return -damage
    if relation == "null":  # ★追加
        return 0
    return damage


# ============================================================
# スペシャル攻撃の Element を取り出すためのヘルパ
# ============================================================


def elements_from_monster_spell(spell_def: Dict[str, Any]) -> list[str]:
    """モンスターの Spells 定義から Element / Elements をパースしてリスト化"""
    elem_raw = spell_def.get("Element") or spell_def.get("Elements") or ""
    return parse_elements(elem_raw)
