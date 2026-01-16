# ============================================================
# turn_logic: 1キャラor1敵の行動フェーズ

# run_character_turn	「キャラ1人分の行動フェーズ」だけを担当する関数
# run_enemy_turn	「敵の1行動フェーズ」だけを担当する関数
# enemy_attack_to_char_with_special	敵がキャラクターに攻撃する1回分の攻撃結果を返す
# ============================================================

from random import Random
from types import SimpleNamespace
from typing import Literal, Dict, Any, List, Tuple, cast

from utils.safe_int_float import safe_int
from combat.enums import BattleKind, Status
from combat.models import (
    Optional,
    FinalCharacterStats,
    FinalEnemyStats,
    BattleActorState,
    EnemyAttackResult,
    SpellInfo,
    OneTurnResult,
    PartyMemberRuntime,
    EnemyCasterStats,
    AttackResult,
)
from combat.runtime_state import RuntimeState
from combat.spell_repo import _choose_monster_special_spell
from combat.elements import (
    elements_from_monster_spell,
    element_relation_and_hits_for_char,
    element_relation_and_hits_for_monster,
    parse_elements,
)
from combat.magic_damage import (
    magic_damage_enemy_to_char,
    enemy_cast_tornado_to_char,
    magic_heal_amount_to_char,
    enemy_cast_drain_to_char,
)
from combat.status_effects import (
    _get_status_name_from_monster_spell,
    apply_reflect_to_actor,
    apply_status_spell_to_enemy,
    apply_partial_petrify_from_status_attack,
    _compute_status_success_prob_for_enemy_spell,
    apply_partial_petrification,
    partial_petrify_amount_from_name,
    _apply_enemy_spell_ailments_to_char,
    ff3_confused_self_dummy_enemy,
    ff3_confused_self_dummy_char,
    calc_buff_hit_percent,
    apply_protect_buff,
    apply_haste_buff,
)
from combat.magic_damage import (
    use_mp_for_spell,
    magic_damage_char_to_enemy,
    enemy_caster_from_monster,
)
from combat.spell_repo import _find_spell_json_for_enemy_attack
from combat.magic_aoe import (
    enemy_cast_aoe_damage_spell_to_party,
    enemy_cast_aoe_damage_spell_to_party,
    spell_is_aoe,
    spell_base_power,
    spell_has_ailment,
    enemy_cast_aoe_status_spell_to_party,
)
from combat.item_effects import (
    apply_status_item_to_enemy,
    apply_item_effect_to_actor,
    spell_from_item,
    item_damage_char_to_enemy,
)
from combat.inventory import (
    consume_item_from_inventory,
    add_item_to_inventory,
    get_item_quantity,
)
from combat.phys_damage import (
    physical_damage_char_to_enemy,
    physical_damage_enemy_to_char,
)
from combat.life_check import any_char_alive, random_alive_char_index
from combat.logging import log_damage, relation_comment


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _as_attack_result(x: Any) -> AttackResult:
    # すでに AttackResult ならそのまま
    if isinstance(x, AttackResult):
        return x

    # tuple系（旧仕様互換）
    if isinstance(x, tuple):
        if len(x) == 3:
            dmg, crit, hits = x
            return AttackResult(
                damage=_to_int(dmg), hit_count=int(hits), is_critical=bool(crit)
            )
        if len(x) == 2:
            dmg, crit = x
            return AttackResult(
                damage=_to_int(dmg), hit_count=0, is_critical=bool(crit)
            )

    # int（旧仕様互換）
    return AttackResult(damage=_to_int(x), hit_count=0, is_critical=False)


def _as_damage(x: Any) -> int:
    if isinstance(x, int):
        return x
    if isinstance(x, tuple) and len(x) >= 1:
        return _to_int(x[0])
    # AttackResult などにも対応したい場合
    if hasattr(x, "damage"):
        return _to_int(getattr(x, "damage"))
    return _to_int(x)


# 4) キャラの1行動フェーズ（★ここだけが「キャラ側ロジック」）==========================================


def run_character_turn(
    *,
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: Dict[str, Any],
    char_state: BattleActorState,
    enemy_state: BattleActorState,
    char_attack_kind: BattleKind,
    char_battle_command: Optional[str],
    char_weapon_hand: Literal["main", "off"],
    char_spell: Optional[SpellInfo],
    char_spell_json: Optional[Dict[str, Any]],
    char_spell_healing_type: Optional[str],
    char_spell_name: Optional[str],
    char_item: Optional[Dict[str, Any]],
    logs: List[str],
    rng: Optional[Random] = None,
    save: Optional[dict] = None,
    spells_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
    enemies: Optional[list] = None,  # ★ 追加（EnemyRuntimeのリスト想定 / duck typing）
    target_side: str = "enemy",
    target_index: int = 0,
    party_members=None,
    aoe_selected_override: Optional[bool] = None,  # ★追加
) -> Tuple[int, Optional[OneTurnResult]]:
    """
    「キャラ1人分の行動フェーズ」だけを担当する関数。
    - HPや状態異常などは char_state / enemy_state / char_stats / enemy_stats に直接書き込む
    - ログは logs に append していく
    - 戦闘継続の場合： (dmg_to_enemy, None) を返す
    - 逃走成功 / ジャンプ上昇 / Terrain 即死などで「このターンで即座にターンを終える」場合：
        (dmg_to_enemy, OneTurnResult(...)) を返し、呼び出し側はそれをそのまま return する
    """
    logs.append(
        f"[DBG] kind={char_attack_kind}, cmd={char_battle_command}, is_jumping={getattr(char_state,'is_jumping',False)}"
    )

    if rng is None:
        rng = Random()

    # ---- 状態異常フラグ類の初期化 --------------------------------------------------
    char_is_blind = char_state.has(Status.BLIND)
    char_is_mini_or_toad = char_state.has(Status.MINI) or char_state.has(Status.TOAD)
    char_is_silenced = char_state.has(Status.SILENCE)
    char_sleep = char_state.has(Status.SLEEP)
    char_para = char_state.has(Status.PARALYZE)
    char_conf = char_state.has(Status.CONFUSION)

    # --- 麻痺の簡易回復判定（例：30%で回復） ---
    if char_para:
        r = rng.random()
        logs.append(f"[{char_name}] Paralysis check {r:.2f}")
        if r < 0.3:  # 好きな確率に調整
            char_state.statuses.discard(Status.PARALYZE)
            char_para = False
            logs.append(f"{char_name}の麻痺が解けた！")

    # ---------------------------------------------------------
    # Jump（上昇/着地）をここで完結させる
    # ---------------------------------------------------------
    if char_attack_kind == "jump":
        # すでにジャンプ中なら「着地攻撃」
        if getattr(char_state, "is_jumping", False):
            char_state.is_jumping = False

            # 本来は保存していたターゲットへ（無ければ今の target_index）
            jump_idx = getattr(char_state, "jump_target_index", None)
            # ※ run_character_turn は enemy_* が 1体分しか来ないので、
            #    ここで「別の敵に差し替える」ことはできません。
            #    したがって、simulate 側で "着地する敵" を enemy_* として渡す必要があります。
            #    ただ、今のログでは Unei's Clone を渡せているのでまずOK。

            # どちらの手で攻撃するか
            if char_weapon_hand == "main":
                weapon_damage = char_stats.main_power
                weapon_hit = char_stats.main_accuracy
            else:
                weapon_damage = char_stats.off_power
                weapon_hit = char_stats.off_accuracy
            print(
                "main_power",
                char_stats.main_power,
                "main_mul",
                char_stats.main_atk_multiplier,
                "main_acc",
                char_stats.main_accuracy,
            )

            strength = char_stats.strength
            agility = char_stats.agility
            level = char_stats.level
            job_level = char_stats.job_level
            print(strength, agility, level, job_level)

            attack_damage = (weapon_damage + (strength // 4)) * 3
            attack_multiplier = (agility // 16) + (level // 16) + 1
            hit_percent = weapon_hit + (agility // 4) + (job_level // 4)

            dmg_to_enemy = attack_damage * attack_multiplier
            print(dmg_to_enemy, attack_damage, attack_multiplier)

            old_enemy_hp = enemy_state.hp
            enemy_state.hp = max(enemy_state.hp - dmg_to_enemy, 0)

            log_damage(
                logs,
                f"{char_name}は空から降下攻撃！ ",
                enemy_name,
                dmg_to_enemy,
                old_enemy_hp,
                enemy_state.hp,
                "attacker",
                "remain",
                None,
                "",
                True,
            )

            # 攻撃後に消す
            if hasattr(char_state, "jump_target_index"):
                char_state.jump_target_index = None

            return dmg_to_enemy, None

        # ジャンプ中でないなら「上昇」
        char_state.is_jumping = True
        char_state.jump_target_index = target_index
        logs.append(f"{char_name}はジャンプした！次のターンに攻撃する。")
        return 0, None

    # ---- 状態異常で行動不能ならログだけ出して終わり ------------------------------
    if char_sleep:
        logs.append(f"{char_name}は眠っていて動けない…")
        dmg_to_enemy = 0
        return dmg_to_enemy, None

    if char_para:
        logs.append(f"{char_name}は麻痺していて動けない…")
        dmg_to_enemy = 0
        return dmg_to_enemy, None

    # ---- 混乱時の特別処理 --------------------------------------------------------
    if char_conf:
        # ★ 混乱中は入力を無視して物理攻撃。
        # 50%: 敵を攻撃 / 50%: 自分を攻撃
        if rng.random() < 0.5:
            # 敵を攻撃
            if char_weapon_hand == "main":
                attack_elems = char_stats.main_weapon_elements
            else:
                attack_elems = char_stats.off_weapon_elements

            relation, hit_elems = element_relation_and_hits_for_monster(
                enemy_json, attack_elems
            )

            res = _as_attack_result(
                physical_damage_char_to_enemy(
                    char=char_stats,
                    enemy=enemy_stats,
                    hand=char_weapon_hand,
                    element_relation=relation,
                    rng=rng,
                    use_expectation=False,
                    blind=char_is_blind,
                    attacker_is_mini_or_toad=char_is_mini_or_toad,
                    return_crit=True,
                    attacker_state=char_state,
                )
            )
            dmg_to_enemy = res.damage
            crit = res.is_critical
            net_hits = res.hit_count

            old_enemy_hp = enemy_state.hp
            enemy_state.hp = max(enemy_state.hp - dmg_to_enemy, 0)

            # ★ 共通ヘルパから相性コメント取得
            relation_msg = relation_comment(relation, hit_elems, perspective="attacker")

            # クリティカルかどうかで prefix だけ変える
            if crit:
                prefix = (
                    f"{char_name}の物理攻撃！ クリティカルヒット！ "
                    f"{relation_msg + ' ' if relation_msg else ''}"
                )
            else:
                prefix = (
                    f"{char_name}の物理攻撃！ "
                    f"{relation_msg + ' ' if relation_msg else ''}"
                )

            # ★ ダメージログ共通関数で出力
            log_damage(
                logs,
                prefix,
                enemy_name,
                dmg_to_enemy,
                old_enemy_hp,
                enemy_state.hp,
                "attacker",
                "remain",
            )

            dmg_to_char_from_self = 0  # 自傷はしていない

        else:
            # 自分を攻撃（自傷）
            res = _as_attack_result(
                physical_damage_char_to_enemy(
                    char=char_stats,
                    # 自分を「防御側」として扱うためのダミー敵
                    enemy=ff3_confused_self_dummy_enemy(char_stats),
                    hand=char_weapon_hand,
                    element_relation="normal",
                    rng=rng,
                    use_expectation=False,
                    blind=char_is_blind,
                    attacker_is_mini_or_toad=char_is_mini_or_toad,
                    return_crit=True,
                )
            )
            dmg_to_char_from_self = res.damage
            crit = res.is_critical
            net_hits = res.hit_count

            old_hp = char_state.hp
            char_state.hp = max(char_state.hp - dmg_to_char_from_self, 0)

            if crit:
                prefix = (
                    f"{char_name}は混乱して自分自身を攻撃した！ クリティカルヒット！ "
                )
            else:
                prefix = f"{char_name}は混乱して自分自身を攻撃した！ "

            # ★ ダメージログ共通関数で出力（自傷なので target 視点）
            log_damage(
                logs,
                prefix,
                char_name,
                dmg_to_char_from_self,
                old_hp,
                char_state.hp,
                "target",
                "remain",
            )

            dmg_to_enemy = 0

        # ★ 物理ダメージを「自分が受けた」場合は混乱解除
        if dmg_to_char_from_self > 0 and char_state.has(Status.CONFUSION):
            char_state.statuses.discard(Status.CONFUSION)
            logs.append(f"{char_name}の混乱が解けた！")

        return dmg_to_enemy, None

    # ----------------------------------------------------------------------
    # ここから attack_kind ごとの分岐（defend / run / magic / item / special / physical）
    # ----------------------------------------------------------------------
    # print(f"[Debug:turn_logic/run_character_turn] {char_attack_kind}")
    if char_attack_kind == "defend":
        char_state.temp_flags["defending"] = True
        logs.append(f"{char_name}は防御した！")
        dmg_to_enemy = 0
        return dmg_to_enemy, None

    elif char_attack_kind == "run":
        # ★ Thief の「Flee」系コマンドかどうか
        is_flee_cmd = char_battle_command in ("Flee", "Run(Flee)", "Run (Flee)")

        # ★PlotBattles持ちは逃げられない（イベント/ボス想定）
        if enemy_json.get("PlotBattles"):
            if is_flee_cmd:
                logs.append(
                    f"{char_name}は《{char_battle_command}》で逃げようとしたが、"
                    f"この戦いからは逃げられない！"
                )
            else:
                logs.append(f"{char_name}は逃げようとしたが、逃げられない！")
            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ★ Flee は 100% 逃走成功
        if is_flee_cmd:
            logs.append(f"{char_name}は《{char_battle_command}》で戦闘から逃げ出した！")
            result = OneTurnResult(
                char_state=char_state,
                enemy_state=enemy_state,
                logs=logs,
                enemy_attack_result=None,
                escaped=True,
                end_reason="escaped",
            )
            return 0, result

        # ★通常の Run コマンド（敏捷依存）
        char_agi = char_stats.agility
        enemy_weight = max(1.0, float(enemy_stats.evasion_percent))
        escape_chance = min(0.95, max(0.05, char_agi / (char_agi + enemy_weight)))

        if rng.random() < escape_chance:
            logs.append(f"{char_name}は逃げ出した！")
            result = OneTurnResult(
                char_state=char_state,
                enemy_state=enemy_state,
                logs=logs,
                enemy_attack_result=None,
                escaped=True,
                end_reason="escaped",
            )
            return 0, result
        else:
            logs.append(f"{char_name}は逃げ出せなかった…")
            dmg_to_enemy = 0
            return dmg_to_enemy, None

    elif char_attack_kind == "magic":
        # ★ターゲット解決（アイテムと同じ）
        target_state = char_state
        target_stats = char_stats
        target_name = char_name

        if target_side in ("ally", "self"):
            if party_members is not None and 0 <= int(target_index) < len(
                party_members
            ):
                tpm = party_members[int(target_index)]
                target_state = tpm.state
                target_stats = tpm.stats
                target_name = tpm.name

        # --- 魔法コマンド ---
        if char_is_silenced:
            logs.append(f"{char_name}は沈黙していて魔法が使えない！")
            dmg_to_enemy = 0
            return dmg_to_enemy, None

        if char_spell is None:
            raise ValueError("char_attack_kind='magic' のときは char_spell が必要です")

        heal_type = char_spell_healing_type

        # ------------------------
        # ① HP回復（Cure系）
        # ------------------------
        if heal_type == "hp":
            if char_spell_json is None:
                raise ValueError("回復魔法には char_spell_json が必要です")

            spell_label = char_spell_name or "魔法"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            spell_type = (char_spell_json.get("Type") or "").lower()
            spell_name_lower = (char_spell_name or "").lower()
            is_summon_heal = (
                spell_type.startswith("summon") or "healing light" in spell_name_lower
            )

            heal = magic_heal_amount_to_char(
                caster=char_stats,
                spell=char_spell,
                rng=rng,
                use_expectation=False,
                blind=char_is_blind,
            )
            old_hp = target_state.hp
            target_state.hp = min(target_state.hp + heal, target_stats.max_hp)
            actual = target_state.hp - old_hp

            spell_label = char_spell_name or (
                "召喚魔法" if is_summon_heal else "回復魔法"
            )
            lvl = int(char_spell_json.get("Level", 1))
            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            if actual > 0:
                if is_summon_heal:
                    logs.append(
                        f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                        f"癒しの光がパーティを包み、{target_name}のHPが{actual}回復。"
                        f"（{target_name} 残りHP: {target_state.hp}） {suffix}"
                    )
                else:
                    logs.append(
                        f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                        f"HPが{actual}回復。（{target_name} 残りHP: {target_state.hp}） {suffix}"
                    )
            else:
                if is_summon_heal:
                    logs.append(
                        f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                        f"しかしHPはこれ以上回復しない。（{target_name} 残りHP: {target_state.hp}） {suffix}"
                    )
                else:
                    logs.append(
                        f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                        f"しかしHPはこれ以上回復しない。（{target_name} 残りHP: {target_state.hp}） {suffix}"
                    )

            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ------------------------
        # ② 状態回復
        # ------------------------
        elif heal_type == "status":
            if char_spell_json is None:
                raise ValueError("status回復魔法には char_spell_json が必要です")

            spell_label = char_spell_name or "魔法"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            ailments = (
                char_spell_json.get("StatusAilment")
                or char_spell_json.get("StatusAilments")
                or ""
            )
            if isinstance(ailments, str):
                ailments_list = [
                    a.strip().lower() for a in ailments.split(",") if a.strip()
                ]
            else:
                ailments_list = []

            before = set(s.name.lower() for s in target_state.statuses)

            status_map = {
                "poison": Status.POISON,
                "blind": Status.BLIND,
                "mini": Status.MINI,
                "silence": Status.SILENCE,
                "toad": Status.TOAD,
                "confusion": Status.CONFUSION,
                "sleep": Status.SLEEP,
                "paralysis": Status.PARALYZE,
                "petrification": Status.PETRIFY,
                "partial petrification (1/3)": Status.PARTIAL_PETRIFY,
                "partial petrification (1/2)": Status.PARTIAL_PETRIFY,
                "partial petrification (full)": Status.PETRIFY,
            }

            for a in ailments_list:
                st = status_map.get(a)
                if st:
                    target_state.statuses.discard(st)
                    if st in (Status.PARTIAL_PETRIFY, Status.PETRIFY):
                        target_state.partial_petrify_gauge = 0.0

            after = set(s.name.lower() for s in target_state.statuses)
            cured = sorted(before - after)

            spell_label = char_spell_name or "状態回復魔法"
            lvl = int(char_spell_json.get("Level", 1))
            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            if cured:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                    f"状態異常が回復した: {', '.join(cured)} {suffix}"
                )
            else:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                    f"しかし治すべき状態異常が無かった。 {suffix}"
                )

            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ------------------------
        # ③ 蘇生
        # ------------------------
        elif heal_type == "revive":
            if char_spell_json is None:
                raise ValueError("蘇生魔法には char_spell_json が必要です")

            spell_label = char_spell_name or "魔法"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            spell_label = char_spell_name or "蘇生魔法"
            lvl = int(char_spell_json.get("Level", 1))
            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            if target_state.hp > 0 and not target_state.has(Status.KO):
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！しかし効果がない。 {suffix}"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            effect = (char_spell_json.get("Effect") or "").lower()

            if target_state.has(Status.KO):
                target_state.statuses.discard(Status.KO)

            if "full hp" in effect:
                target_state.hp = target_stats.max_hp
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                    f"{target_name}は完全に蘇生した！（HP: {target_state.hp}） {suffix}"
                )
            else:
                revived_hp = max(1, int(target_stats.max_hp * 0.20))
                target_state.hp = revived_hp
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                    f"{target_name}は蘇生した！（HP: {target_state.hp}） {suffix}"
                )

            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ------------------------
        # ④ Protect
        # ------------------------
        elif heal_type == "protect":
            if char_spell_json is None:
                raise ValueError("Protect には char_spell_json が必要です")

            spell_label = char_spell_name or "Protect"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            mind = char_stats.mind
            L = char_stats.level
            J = char_stats.job_level

            base_acc = char_spell_json.get("BaseAccuracy")
            if base_acc is None:
                base_acc = char_spell_json.get("Accuracy", 1.0)

            hit_percent = calc_buff_hit_percent(base_acc, mind)

            if rng.random() * 100.0 >= hit_percent:
                remain = char_state.mp_pool[lvl]
                maxmp = char_state.max_mp_pool.get(lvl, remain)
                suffix = f"（MP{lvl} {remain}/{maxmp}）"
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                    f"しかし何も起こらなかった… {suffix}"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            base_factor = (mind // 16) + (L // 16) + (J // 32) + 1
            base_power = float(char_spell_json.get("BasePower", 5))

            old_def, old_mdef = apply_protect_buff(
                target_stats,
                base_power=base_power,
                base_factor=base_factor,
                rng=rng,
            )

            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            logs.append(
                f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                f"防御力 {old_def}→{target_stats.defense}、"
                f"魔法防御 {old_mdef}→{target_stats.magic_defense} に上がった。 {suffix}"
            )

            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ------------------------
        # ⑤ Haste
        # ------------------------
        elif heal_type == "haste":
            if char_spell_json is None:
                raise ValueError("Haste には char_spell_json が必要です")

            spell_label = char_spell_name or "Haste"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            mind = char_stats.mind
            L = char_stats.level
            J = char_stats.job_level

            acc = char_spell_json.get("BaseAccuracy")
            if acc is None:
                acc = char_spell_json.get("Accuracy", 1.0)

            hit_percent = calc_buff_hit_percent(acc, mind)

            if rng.random() * 100.0 >= hit_percent:
                remain = char_state.mp_pool[lvl]
                maxmp = char_state.max_mp_pool.get(lvl, remain)
                suffix = f"（MP{lvl} {remain}/{maxmp}）"
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                    f"しかし何も起こらなかった… {suffix}"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            base_factor = (mind // 16) + (L // 16) + (J // 32) + 1
            base_power = float(char_spell_json.get("BasePower", 5))
            mul_default = base_factor

            (
                old_main_pow,
                old_off_pow,
                old_main_mul,
                old_off_mul,
            ) = apply_haste_buff(
                target_stats,
                base_power=base_power,
                base_factor=base_factor,
                mul_default=mul_default,
                rng=rng,
            )

            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            logs.append(
                f"{char_name}は{target_name}に《{spell_label}》を唱えた！ "
                f"攻撃力 右手 {old_main_pow}→{target_stats.main_power}"
                + (
                    f" / 左手 {old_off_pow}→{target_stats.off_power}"
                    if old_off_pow > 0
                    else ""
                )
                + f"、攻撃回数 右手 {old_main_mul}→{target_stats.main_atk_multiplier}"
                + (
                    f" / 左手 {old_off_mul}→{target_stats.off_atk_multiplier}"
                    if old_off_mul > 0
                    else ""
                )
                + f" に上がった。 {suffix}"
            )

            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ------------------------
        # ⑤.5 Reflect / Odin: Protective Light
        # ------------------------
        elif (char_spell_json or {}).get("name") in (
            "Reflect",
            "Odin: Protective Light",
        ):
            if char_spell_json is None:
                raise ValueError("Reflect 系には char_spell_json が必要です")

            raw_name = (char_spell_json or {}).get("name") or "Reflect"
            spell_label = char_spell_name or raw_name

            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は{target_name}に《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            if (
                str(char_spell_json.get("Type", "")).lower() == "summon"
                and raw_name == "Odin: Protective Light"
            ):
                base_acc = float(char_spell_json.get("Accuracy") or 0.0)
                if base_acc <= 1.0:
                    base_acc *= 100.0
                hit_percent = base_acc + float(getattr(char_stats, "intelligence", 0))
            else:
                mind = char_stats.mind
                acc = char_spell_json.get("BaseAccuracy")
                if acc is None:
                    acc = char_spell_json.get("Accuracy", 1.0)

                acc = float(acc)
                if acc > 1.0:
                    acc = acc / 100.0

                base_percent = acc * 100.0
                hit_percent = base_percent + (mind / 2.0)

            if hit_percent > 100.0:
                hit_percent = 100.0
            if hit_percent < 0.0:
                hit_percent = 0.0

            roll = rng.random() * 100.0

            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            if roll < hit_percent:
                target_state.reflect_charges = 1

                if raw_name == "Odin: Protective Light":
                    logs.append(
                        f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                        f"守護の光がパーティを包み、魔法を一度だけ跳ね返すバリアを張った。"
                        f"（命中率{hit_percent:.1f}% 判定{roll:.1f}） {suffix}"
                    )
                else:
                    logs.append(
                        f"{char_name}は《{spell_label}》を唱えた！ "
                        f"魔法を一度だけ跳ね返すバリアを張った。"
                        f"（命中率{hit_percent:.1f}% 判定{roll:.1f}） {suffix}"
                    )
            else:
                if raw_name == "Odin: Protective Light":
                    logs.append(
                        f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                        f"しかし何も起こらなかった…"
                        f"（命中率{hit_percent:.1f}% 判定{roll:.1f}） {suffix}"
                    )
                else:
                    logs.append(
                        f"{char_name}は《{spell_label}》を唱えた！ "
                        f"しかし何も起こらなかった…"
                        f"（命中率{hit_percent:.1f}% 判定{roll:.1f}） {suffix}"
                    )

            dmg_to_enemy = 0
            return dmg_to_enemy, None

        # ------------------------
        # ⑤.6 Chocobo: Chocobo Dash（50% で逃走）
        # ------------------------
        elif (char_spell_json or {}).get("name") == "Chocobo: Chocobo Dash":
            if char_spell_json is None:
                raise ValueError(
                    "Chocobo: Chocobo Dash には char_spell_json が必要です"
                )

            spell_label = char_spell_name or "Chocobo: Chocobo Dash"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            if not mp_used:
                logs.append(
                    f"{char_name}は召喚魔法《{spell_label}》を呼び出そうとしたが MP{lvl} が足りない！"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            if enemy_json.get("PlotBattles"):
                logs.append(
                    f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                    f"しかしこの戦いからは逃げられない！ {suffix}"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

            roll = rng.random()
            if roll < 0.5:
                logs.append(
                    f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                    f"チョコボのダッシュで戦闘から逃げ出した！ {suffix}"
                )
                result = OneTurnResult(
                    char_state=char_state,
                    enemy_state=enemy_state,
                    logs=logs,
                    enemy_attack_result=None,
                    escaped=True,
                    end_reason="escaped",
                )
                return 0, result
            else:
                logs.append(
                    f"{char_name}は召喚魔法《{spell_label}》を呼び出した！ "
                    f"しかしチョコボは逃げ切れなかった… {suffix}"
                )
                dmg_to_enemy = 0
                return dmg_to_enemy, None

        # ------------------------
        # ⑥ 上記以外は攻撃魔法
        # ------------------------
        else:
            if char_spell_json is None:
                raise ValueError("攻撃魔法には char_spell_json が必要です")

            spell_label = char_spell_name or "魔法"
            mp_used = use_mp_for_spell(char_state, char_spell_json)
            lvl = int(char_spell_json.get("Level", 1))

            # ★ elements
            raw_elements = getattr(char_spell, "elements", None)
            if not raw_elements and char_spell_json is not None:
                raw_elements = (
                    char_spell_json.get("Element")
                    or char_spell_json.get("Elements")
                    or ""
                )
            spell_elements = parse_elements(raw_elements)

            if not mp_used:
                logs.append(
                    f"{char_name}は《{spell_label}》を唱えようとしたが MP{lvl} が足りない！"
                )
                return 0, None

            remain = char_state.mp_pool[lvl]
            maxmp = char_state.max_mp_pool.get(lvl, remain)
            suffix = f"（MP{lvl} {remain}/{maxmp}）"

            # ------------------------
            # ターゲット判定：All / One/All
            # ------------------------
            target_raw = (char_spell_json.get("Target") or "").strip().lower()
            is_all_only = target_raw == "all enemies"
            is_one_or_all = target_raw == "one/all enemies"

            """
            aoe_selected = False
            if is_all_only:
                aoe_selected = True
            elif is_one_or_all:
                # ★ ここで単体/全体を選ばせる（UIをここに寄せる最小実装）
                # 1: 単体 / 2: 全体
                try:
                    choice = int(
                        input(
                            "魔法の対象を選んでください。 1: 敵単体 / 2: 敵全体 > "
                        ).strip()
                    )
                except Exception:
                    choice = 1
                aoe_selected = choice == 2
            """
            aoe_selected = False
            if is_all_only:
                aoe_selected = True
            elif is_one_or_all:
                # ★Pygame側で選んだ結果があればそれに従う（input()はしない）
                if aoe_selected_override is not None:
                    aoe_selected = aoe_selected_override
                else:
                    # 互換用：古い呼び出し（コンソール）対策で単体に寄せる
                    aoe_selected = False

            # AoE 用：生存敵リスト（duck typing：.state.hp / .name / .stats / .json を想定）
            alive_enemies = None
            if enemies is not None:
                alive_enemies = [em for em in enemies if getattr(em.state, "hp", 0) > 0]

            # ------------------------
            # Reflect（AoEでも「各敵ごと」に判定したいが、まずは最小：単体のみ対応）
            # AoEにReflectを入れたい場合は別途拡張（敵ごとに reflect_charges を見る必要がある）
            # ------------------------
            is_reflectable = (
                str(char_spell_json.get("Reflectable", "No")).strip().lower() == "yes"
            )
            if (
                (not aoe_selected)
                and is_reflectable
                and getattr(enemy_state, "reflect_charges", 0) > 0
            ):
                enemy_state.reflect_charges -= 1

                dummy_enemy = ff3_confused_self_dummy_enemy(char_stats)
                dmg_back = magic_damage_char_to_enemy(
                    caster=char_stats,
                    spell=char_spell,
                    enemy=dummy_enemy,
                    element_relation="normal",
                    rng=rng,
                    use_expectation=False,
                    blind=char_is_blind,
                )

                old_hp = char_state.hp
                char_state.hp = max(char_state.hp - dmg_back, 0)

                log_damage(
                    logs,
                    f"{enemy_name}を覆う魔法障壁が《{spell_label}》を跳ね返した！ ",
                    char_name,
                    dmg_back,
                    old_hp,
                    char_state.hp,
                    "target",
                    "remain",
                    None,
                    f" {suffix}",
                )
                return 0, None

            # ------------------------
            # 純ステータス魔法判定（あなたの既存ロジックを踏襲）
            # ------------------------
            pure_status_spells = {
                "Sleep",
                "Blind",
                "Poison",
                "Shade",
                "Erase",
                "Raze",
                "Warp",
                "Break",
                "Breakga",
                "Death",
                "Mini",
                "Toad",
                "Teleport",
                "Silence",
                "Confuse",
                "Mesmerize",
                "Mind Blast",
                "Demon Eye",
            }

            def is_pure_status_spell(name: str) -> bool:
                return any(name.endswith(ps) for ps in pure_status_spells)

            is_drain_spell = False
            effect_text = (char_spell_json.get("Effect") or "").lower()
            name_lower = (char_spell_json.get("Name") or "").lower()
            if "absorb hp" in effect_text or name_lower == "drain":
                is_drain_spell = True

            # ------------------------
            # AoE 実装（Reflect対応版 / Drainは合計ダメージ吸収）
            # ------------------------
            if aoe_selected and alive_enemies is not None and len(alive_enemies) >= 1:
                n = len(alive_enemies)

                # ★ ダメージ分割ルール
                # - All Enemies：割らない（各対象同ダメ）
                # - One/All Enemies（全体選択）：割る（対象数で割る）
                split = n if is_one_or_all else 1

                # ★ 敵に実際に入った合計（Drainの吸収量に使う）
                total_damage = 0

                # ★ 反射まとめ
                is_reflectable = (
                    str(char_spell_json.get("Reflectable", "No")).strip().lower()
                    == "yes"
                )
                reflect_count = 0
                reflect_total = 0

                for em in alive_enemies:
                    em_name = em.name
                    em_state = em.state
                    em_stats = em.stats
                    em_json = em.json

                    # --- 属性相性（敵ごと） ---
                    rel, hit_elems = element_relation_and_hits_for_monster(
                        em_json, spell_elements
                    )

                    # --- ダメージ算出 ---
                    if is_pure_status_spell(spell_label):
                        dmg = 0
                    else:
                        dmg = magic_damage_char_to_enemy(
                            caster=char_stats,
                            spell=char_spell,
                            enemy=em_stats,
                            element_relation=rel,
                            rng=rng,
                            use_expectation=False,
                            blind=char_is_blind,
                        )
                        if split > 1:
                            dmg = int(dmg / split)

                    dmg = int(max(0, dmg))

                    # =====================================================
                    # ★ Reflect：敵ごとに判定（反射した分は敵に入らない）
                    # =====================================================
                    if (
                        is_reflectable
                        and dmg > 0
                        and getattr(em_state, "reflect_charges", 0) > 0
                    ):
                        em_state.reflect_charges -= 1
                        reflect_count += 1
                        reflect_total += dmg

                        old_hp = char_state.hp
                        char_state.hp = max(0, old_hp - dmg)

                        # 反射ログ（個別） ※個別ログ不要ならここを丸ごと削ってOK
                        log_damage(
                            logs,
                            f"{em_name}を覆う魔法障壁が《{spell_label}》を跳ね返した！ ",
                            char_name,
                            dmg,
                            old_hp,
                            char_state.hp,
                            "target",
                            "remain",
                            None,
                            f" {suffix}",
                        )

                        # ★ 反射でキャラ死亡 → 即終了（ただし、ここまでの total_damage は返す）
                        if char_state.hp <= 0:
                            # まとめログ（2回以上のときだけ出す例）
                            if reflect_count >= 2:
                                logs.append(
                                    f"《{spell_label}》は{reflect_count}回反射された！（合計{reflect_total}ダメージ）"
                                )

                            return total_damage, OneTurnResult(
                                char_state=char_state,
                                enemy_state=enemy_state,
                                logs=logs,
                                enemy_attack_result=None,
                                end_reason="char_defeated",
                            )

                        continue  # ★ この敵にはダメージも状態異常も適用しない

                    # --- 通常ダメージ適用 ---
                    old_hp = em_state.hp
                    em_state.hp = max(em_state.hp - dmg, 0)
                    total_damage += dmg

                    # --- 状態異常（AoEなので敵ごと） ---
                    apply_status_spell_to_enemy(
                        spell_json=char_spell_json,
                        enemy_state=em_state,
                        enemy_json=em_json,
                        enemy_name=em_name,
                        rng=rng,
                        logs=logs,
                        caster_stats=char_stats,
                        summon_child_name=char_spell_name,
                    )

                    # --- ダメージログ（敵ごと） ---
                    if dmg > 0:
                        relation_msg = relation_comment(
                            rel, hit_elems, perspective="attacker"
                        )
                        log_damage(
                            logs,
                            f"{char_name}は《{spell_label}》を唱えた！ "
                            f"{relation_msg + ' ' if relation_msg else ''}",
                            em_name,
                            dmg,
                            old_hp,
                            em_state.hp,
                            "attacker",
                            "remain",
                            None,
                            f" {suffix}",
                        )

                # ★ まとめログ（複数反射だけ出す例。1回でも出したければ >=1 に）
                if reflect_count >= 2:
                    logs.append(
                        f"《{spell_label}》は{reflect_count}回反射された！（合計{reflect_total}ダメージ）"
                    )

                # ★ Drain：AoEは「敵に入った合計ダメージ」を吸収にする
                if is_drain_spell and total_damage > 0:
                    old_hp = char_state.hp
                    char_state.hp = min(char_state.hp + total_damage, char_stats.max_hp)
                    actual = char_state.hp - old_hp
                    if actual > 0:
                        logs.append(
                            f"{char_name}は敵からHPを{actual}吸収した！"
                            f"（{char_name} 残りHP: {char_state.hp}）"
                        )

                # ★ 行動後：敵全滅チェック（ここで end_reason だけ返す。ログは外側が出す想定）
                if enemies is not None and all(
                    getattr(e.state, "hp", 0) <= 0 for e in enemies
                ):
                    return total_damage, OneTurnResult(
                        char_state=char_state,
                        enemy_state=enemy_state,
                        logs=logs,
                        enemy_attack_result=None,
                        end_reason="enemy_defeated",
                    )

                return total_damage, None

            # ------------------------
            # 単体（従来通り）
            # ------------------------
            char_spell_relation, char_spell_hit_elems = (
                element_relation_and_hits_for_monster(
                    enemy_json,
                    spell_elements,
                )
            )

            if is_pure_status_spell(spell_label):
                dmg_to_enemy = 0
            else:
                dmg_to_enemy = magic_damage_char_to_enemy(
                    caster=char_stats,
                    spell=char_spell,
                    enemy=enemy_stats,
                    element_relation=char_spell_relation,
                    rng=rng,
                    use_expectation=False,
                    blind=char_is_blind,
                )

            old_enemy_hp = enemy_state.hp
            enemy_state.hp = max(enemy_state.hp - dmg_to_enemy, 0)

            apply_status_spell_to_enemy(
                spell_json=char_spell_json,
                enemy_state=enemy_state,
                enemy_json=enemy_json,
                enemy_name=enemy_name,
                rng=rng,
                logs=logs,
                caster_stats=char_stats,
                summon_child_name=char_spell_name,
            )

            relation_msg = relation_comment(
                char_spell_relation,
                char_spell_hit_elems,
                perspective="attacker",
            )

            # 即死系のログ抑制はあなたの既存ロジックを踏襲（必要ならここに移植）
            if dmg_to_enemy > 0:
                log_damage(
                    logs,
                    f"{char_name}は《{spell_label}》を唱えた！ "
                    f"{relation_msg + ' ' if relation_msg else ''}",
                    enemy_name,
                    dmg_to_enemy,
                    old_enemy_hp,
                    enemy_state.hp,
                    "attacker",
                    "remain",
                    None,
                    f" {suffix}",
                )

            if is_drain_spell and dmg_to_enemy > 0:
                old_hp = char_state.hp
                char_state.hp = min(char_state.hp + dmg_to_enemy, char_stats.max_hp)
                actual_heal = char_state.hp - old_hp
                if actual_heal > 0:
                    logs.append(
                        f"{char_name}は{enemy_name}からHPを{actual_heal}吸収した！"
                        f"（{char_name} 残りHP: {char_state.hp}）"
                    )

            return dmg_to_enemy, None

    elif char_attack_kind == "item":
        # --- アイテム使用 ---
        if char_item is None:
            raise ValueError("char_attack_kind='item' のときは char_item が必要です")

        item_name = (char_item.get("Name") or "").strip()

        # =========================
        # ターゲット解決
        # =========================
        target_state = char_state
        target_stats = char_stats
        target_name = char_name

        if target_side in ("ally", "self"):
            if party_members is not None and 0 <= int(target_index) < len(
                party_members
            ):
                tpm = party_members[int(target_index)]
                target_state = tpm.state
                target_stats = tpm.stats
                target_name = tpm.name

        spell_info = char_item.get("SpellInfo") or {}
        effect_text = (spell_info.get("Effect") or "").lower()
        item_spell_effect = str(char_item.get("SpellEffect") or "").lower()
        item_name_lower = (char_item.get("Name") or "").lower()

        # =========================
        # 攻撃/状態異常アイテム判定
        # =========================
        is_attack_item = False
        if "deal" in effect_text and "damage" in effect_text:
            is_attack_item = True
        if "inflict ko" in effect_text:
            is_attack_item = True
        if (
            "absorb hp" in effect_text
            or item_spell_effect == "drain"
            or "lilith's kiss" in item_name_lower
        ):
            is_attack_item = True

        # ============================================================
        # 1) 敵ターゲット：攻撃 or 状態異常（B案：消費できたら効果）
        # ============================================================
        if target_side == "enemy":
            # まず「敵に使う系」のアイテムだけ許可
            #  - 攻撃アイテム or 状態異常アイテム（apply_status_item_to_enemyで判定）
            # ここでは「使えるかどうか」を判定するために
            #   a) 攻撃アイテムなら is_attack_item=True
            #   b) 状態異常は apply_status_item_to_enemy の結果でログが出るので、
            #      先に消費→判定、に統一する

            # ---- 攻撃アイテム（ダメージ/即死/吸収など） ----
            if is_attack_item:
                # ★B案：在庫が無ければ効果ゼロ
                if save is None:
                    logs.append(
                        f"{char_name}は{item_name}を使おうとした！ しかしセーブデータが無いので使用できない…"
                    )
                    return 0, None

                if not consume_item_from_inventory(save, item_name):
                    logs.append(
                        f"{char_name}は{item_name}を使おうとした！ しかし在庫がなかった…"
                    )
                    return 0, None

                spell = spell_from_item(char_item)
                relation, hit_elems = element_relation_and_hits_for_monster(
                    enemy_json,
                    spell.elements,
                )

                dmg_to_enemy = item_damage_char_to_enemy(
                    item_spell=spell,
                    item_json=char_item,
                    enemy=enemy_stats,
                    element_relation=relation,
                    rng=rng,
                )

                old_enemy_hp = enemy_state.hp
                enemy_state.hp = max(enemy_state.hp - dmg_to_enemy, 0)

                relation_msg = relation_comment(
                    relation,
                    hit_elems,
                    perspective="attacker",
                )

                log_damage(
                    logs,
                    f"{char_name}は{char_item.get('Name')}を使った！ "
                    f"{relation_msg + ' ' if relation_msg else ''}",
                    enemy_name,
                    dmg_to_enemy,
                    old_enemy_hp,
                    enemy_state.hp,
                    "attacker",
                    "remain",
                )

                # 吸収系
                is_drain_item = (
                    "absorb hp" in effect_text
                    or item_spell_effect == "drain"
                    or "lilith's kiss" in item_name_lower
                )
                if is_drain_item and dmg_to_enemy > 0:
                    old_hp = char_state.hp
                    heal = dmg_to_enemy
                    char_state.hp = min(char_state.hp + heal, char_stats.max_hp)
                    actual_heal = char_state.hp - old_hp
                    if actual_heal > 0:
                        logs.append(
                            f"{char_name}は{enemy_name}からHPを{actual_heal}吸収した！"
                            f"（{char_name} 残りHP: {char_state.hp}）"
                        )

                # 即死系
                if "inflict ko" in effect_text:
                    ko_acc = spell_info.get("BaseAccuracy")
                    if ko_acc is None:
                        ko_acc = 1.0
                    if rng.random() < float(ko_acc):
                        enemy_state.hp = 0
                        logs.append(f"{enemy_name}に即死効果が発動した！")

                return dmg_to_enemy, None

            # ---- 状態異常アイテム（敵） ----
            # ★B案：在庫が無ければ効果ゼロ（消費できたら判定＆効果）
            if save is None:
                logs.append(
                    f"{char_name}は{item_name}を使おうとした！ しかしセーブデータが無いので使用できない…"
                )
                return 0, None

            if not consume_item_from_inventory(save, item_name):
                logs.append(
                    f"{char_name}は{item_name}を使おうとした！ しかし在庫がなかった…"
                )
                return 0, None

            handled_as_status = apply_status_item_to_enemy(
                item_json=char_item,
                enemy_state=enemy_state,
                enemy_name=enemy_name,
                rng=rng,
                logs=logs,
            )

            # 状態異常として処理できたならここで終了
            if handled_as_status:
                return 0, None

            # 状態異常としても処理できず、攻撃アイテムでもない場合
            # 例：回復アイテムを敵に使おうとした、など
            logs.append(f"{char_name}は{item_name}を使った！ しかし効果がなかった…")
            return 0, None

        # ============================================================
        # 2) 味方/自分ターゲット：回復/補助（B案：消費できたら効果）
        # ============================================================
        # 敵向け攻撃アイテムを味方に使おうとした場合は不発（消費しない）
        if is_attack_item:
            logs.append(
                f"{char_name}は{item_name}を使おうとした！ しかし対象が敵ではなかった…"
            )
            return 0, None

        # KO相手には不発（消費しない）にしたい場合
        if Status.KO in target_state.statuses:
            logs.append(
                f"{char_name}は{item_name}を使った！ "
                f"しかし{target_name}は戦闘不能で、何も起こらなかった…"
            )
            return 0, None

        # ★B案：在庫が無ければ効果ゼロ
        if save is None:
            logs.append(
                f"{char_name}は{item_name}を使おうとした！ しかしセーブデータが無いので使用できない…"
            )
            return 0, None

        if not consume_item_from_inventory(save, item_name):
            logs.append(
                f"{char_name}は{item_name}を使おうとした！ しかし在庫がなかった…"
            )
            return 0, None

        # Shining Curtain : Reflect と同様の反射バリア
        if item_name == "Shining Curtain":
            acc = spell_info.get("BaseAccuracy")
            if acc is None:
                acc = spell_info.get("Accuracy", 1.0)

            acc = float(acc)
            if acc > 1.0:
                acc = acc / 100.0

            base_percent = acc * 100.0
            mind = char_stats.mind
            hit_percent = base_percent + (mind / 2.0)

            if hit_percent > 100.0:
                hit_percent = 100.0
            if hit_percent < 0.0:
                hit_percent = 0.0

            roll = rng.random() * 100.0

            if roll < hit_percent:
                target_state.reflect_charges = 1
                logs.append(
                    f"{char_name}は{item_name}を使った！ "
                    f"{target_name}に魔法を一度だけ跳ね返すバリアを張った。"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
            else:
                logs.append(
                    f"{char_name}は{item_name}を使った！ "
                    f"しかし何も起こらなかった…"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )

            return 0, None

        # それ以外の回復・補助アイテム
        apply_item_effect_to_actor(
            item_json=char_item,
            target_state=target_state,
            target_name=target_name,
            max_hp=target_stats.max_hp,
            logs=logs,
            target_stats=target_stats,
            rng=rng,
            actor_name=char_name,  # ★追加
        )
        return 0, None

    elif char_attack_kind == "special":
        handled_special = False

        # Thief: Steal
        if char_battle_command == "Steal":
            handled_special = True

            success_percent = (char_stats.level / 3.0) + (char_stats.job_level / 3.0)
            success_percent = max(0.0, min(success_percent, 100.0))
            success_prob = success_percent / 100.0
            r = rng.random()
            logs.append(
                f"{char_name}の《Steal》！ 成功率 {success_percent:.1f}% 判定値 {r:.3f}"
            )

            if r >= success_prob:
                logs.append(f"しかし{enemy_name}からは何も盗めなかった…")
                dmg_to_enemy = 0
            else:
                stolen_list = enemy_json.get("Stolen Items") or []
                if not stolen_list:
                    logs.append(f"{enemy_name}から盗めるものは無いようだ…")
                    dmg_to_enemy = 0
                else:
                    total_weight = 0.0
                    for entry in stolen_list:
                        w = float(entry.get("StealRate", 0) or 0.0)
                        total_weight += max(w, 0.0)

                    if total_weight <= 0:
                        chosen = stolen_list[0]
                    else:
                        r_item = rng.random() * total_weight
                        acc = 0.0
                        chosen = stolen_list[-1]
                        for entry in stolen_list:
                            w = float(entry.get("StealRate", 0) or 0.0)
                            if w <= 0:
                                continue
                            acc += w
                            if r_item <= acc:
                                chosen = entry
                                break

                    item_name = chosen.get("Item")
                    if not item_name:
                        logs.append(f"{enemy_name}から盗めるアイテム名が不正です。")
                        dmg_to_enemy = 0
                    else:
                        if save is not None:
                            category = add_item_to_inventory(save, item_name, qty=1)
                            from_qty = get_item_quantity(save, item_name)
                            logs.append(
                                f"{enemy_name}から{item_name}を盗んだ！"
                                f"（{category or 'Anywhere'} に追加／所持数 {from_qty}）"
                            )
                        else:
                            logs.append(
                                f"{enemy_name}から{item_name}を盗んだ！（※セーブデータ未指定のため所持数は変化しません）"
                            )
                        dmg_to_enemy = 0

        # Scholar: Peep
        if char_battle_command == "Peep":
            handled_special = True
            logs.append(f"{char_name}の《Peep》！")

            ev = enemy_json.get("ElementalVulnerability", {}) or {}

            def _fmt_elems(raw) -> str:
                elems = parse_elements(raw)
                if not elems:
                    return ""
                return "/".join(e.title() for e in elems)

            weak_s = _fmt_elems(ev.get("Weakness"))
            absorb_s = _fmt_elems(ev.get("Absorb"))
            resist_s = _fmt_elems(ev.get("Resistance"))

            if weak_s:
                logs.append(f"{enemy_name}は{weak_s}属性に弱い。")
            if absorb_s:
                logs.append(f"{enemy_name}は{absorb_s}属性を吸収する。")
            if resist_s:
                logs.append(f"{enemy_name}は{resist_s}属性に強い。")

            if not (weak_s or absorb_s or resist_s):
                logs.append(f"{enemy_name}の属性相性に目立った特徴はないようだ。")

            dmg_to_enemy = 0

        # Scholar: Study
        if char_battle_command == "Study":
            handled_special = True
            logs.append(f"{char_name}の《Study》！")

            hpmax = (
                enemy_state.max_hp if enemy_state.max_hp is not None else enemy_state.hp
            )
            logs.append(f"{enemy_name}のHPは{enemy_state.hp}/{hpmax}だ。")

            dmg_to_enemy = 0

        # Geomancer: Terrain
        if char_battle_command == "Terrain":
            handled_special = True
            logs.append(f"{char_name}の《Terrain》！")

            surface = None
            if save is not None:
                surface = (save.get("map") or {}).get("surface")

            surface_str = str(surface or "Other").strip()
            surface_norm = surface_str.lower()

            surface_to_spell = {
                "sky": "Cyclone",
                "grassland": "Earthquake",
                "desert": "Quicksand",
                "marsh": "Sinkhole",
                "river": "Torrent",
                "ocean": "Whirlpool",
                "forest": "Wind Slash",
                "other": "Cave In",
            }

            spell_name = surface_to_spell.get(surface_norm)
            if spell_name is None:
                spell_name = surface_to_spell["other"]

            spell = None
            if spells_by_name is not None:
                spell = spells_by_name.get(spell_name)

            if not spell:
                logs.append("しかし何も起こらなかった…")
                dmg_to_enemy = 0
            else:
                logs.append(f"{spell_name} が発動！")

                base_power = spell.get("BasePower", 0)
                base_acc = float(spell.get("BaseAccuracy", 0.0))

                INT = char_stats.intelligence
                LV = char_stats.level
                JL = getattr(char_stats, "job_level", 1)

                magic_damage = base_power + (INT / 2.0)
                magic_mul = (INT / 16.0) + (LV / 16.0) + (JL / 32.0) + 1.0
                final_damage = max(0, int(magic_damage * magic_mul))

                hit_rate = base_acc + (INT / 200.0)
                hit_rate = max(0.05, min(0.95, hit_rate))

                r = rng.random()

                if r > hit_rate:
                    max_hp_char = getattr(
                        char_stats,
                        "max_hp",
                        (
                            char_state.max_hp
                            if char_state.max_hp is not None
                            else char_state.hp
                        ),
                    )
                    backfire = max(1, max_hp_char // 4)

                    logs.append(f"{spell_name}は不発に終わった！")

                    old_hp = char_state.hp
                    char_state.hp = max(char_state.hp - backfire, 0)

                    log_damage(
                        logs,
                        "バックファイア！",
                        char_name,
                        backfire,
                        old_hp,
                        char_state.hp,
                        "target",
                        "arrow",
                    )

                    if char_state.hp <= 0:
                        char_state.statuses.add(Status.KO)

                    dmg_to_enemy = 0

                else:
                    effect = spell.get("Effect", "")
                    target = (spell.get("Target") or "").strip().lower()
                    is_aoe = target == "all enemies"

                    if "Inflict KO" in effect:
                        if enemy_json.get("PlotBattles"):
                            logs.append(f"{spell_name}はボスには効かなかった！")
                            dmg_to_enemy = 0
                        else:
                            old_enemy_hp = enemy_state.hp
                            enemy_state.hp = 0
                            enemy_state.statuses.add(Status.KO)

                            logs.append(
                                f"{enemy_name}は{spell_name}に飲み込まれた！即死！"
                            )

                            dmg_to_enemy = old_enemy_hp

                        result = OneTurnResult(
                            char_state=char_state,
                            enemy_state=enemy_state,
                            logs=logs,
                            enemy_attack_result=None,
                            end_reason=(
                                "enemy_defeated" if enemy_state.hp <= 0 else "continue"
                            ),
                        )
                        return dmg_to_enemy, result

                    if is_aoe:
                        old_enemy_hp = enemy_state.hp
                        enemy_state.hp = max(enemy_state.hp - final_damage, 0)

                        log_damage(
                            logs,
                            "",
                            enemy_name,
                            final_damage,
                            old_enemy_hp,
                            enemy_state.hp,
                            "attacker",
                            "arrow",
                            None,
                            "",
                            True,
                        )
                        dmg_to_enemy = final_damage
                    else:
                        old_enemy_hp = enemy_state.hp
                        enemy_state.hp = max(enemy_state.hp - final_damage, 0)

                        log_damage(
                            logs,
                            "",
                            enemy_name,
                            final_damage,
                            old_enemy_hp,
                            enemy_state.hp,
                            "attacker",
                            "arrow",
                            None,
                            "",
                            True,
                        )
                        dmg_to_enemy = final_damage

        # Black Belt: Boost
        if char_battle_command == "Boost":
            handled_special = True

            if char_state.boost_count >= 2:
                logs.append(f"{char_name}は力をためすぎて《Overload》を起こした！")

                dmg_to_enemy = 0

                overload_damage = max(1, char_state.hp // 2)

                old_hp = char_state.hp
                char_state.hp = max(char_state.hp - overload_damage, 0)

                log_damage(
                    logs,
                    "オーバーロードで",
                    char_name,
                    overload_damage,
                    old_hp,
                    char_state.hp,
                    "target",
                    "remain",
                )

                char_state.boost_count = 0
                char_state.temp_flags.pop("boosting", None)
            else:
                char_state.boost_count += 1
                char_state.temp_flags["boosting"] = True

                logs.append(
                    f"{char_name}は力をためた！（Boost {char_state.boost_count}回目）"
                )

                dmg_to_enemy = 0

            return dmg_to_enemy, None

        # Bard: Scare
        if char_battle_command == "Scare":
            handled_special = True
            dmg_to_enemy = 0

            if not enemies:
                logs.append(f"{char_name}の《Scare》！ しかし敵がいなかった…")
                return dmg_to_enemy, None

            affected = 0
            details = []

            for e in enemies:
                # e は EnemyRuntime を想定（name, stats がある）
                est = e.stats
                before_lv = getattr(est, "level", None)

                # level が無い敵データが混じる可能性があるなら保険
                if before_lv is None:
                    continue

                if before_lv <= 1:
                    details.append(f"{e.name}: 効果なし（Lvはすでに1）")
                    continue

                est.level = max(1, before_lv - 3)
                decreased = before_lv - est.level
                affected += 1
                details.append(f"{e.name}: Lv {before_lv}→{est.level}（-{decreased}）")

            # ログ（長ければ1行に圧縮してもOK）
            if affected == 0:
                logs.append(f"{char_name}の《Scare》！ しかし誰にも効果がなかった…")
            else:
                logs.append(f"{char_name}の《Scare》！ 敵全員のレベルを下げた！")
                for line in details:
                    logs.append("  - " + line)

            return dmg_to_enemy, None

        # Bard: Cheer（物理攻撃力を +10）
        if char_battle_command == "Cheer":
            handled_special = True
            dmg_to_enemy = 0

            if party_members is not None:
                members = party_members
            else:
                members = [SimpleNamespace(name=char_name, stats=char_stats)]

            applied = []
            for pm in members:
                # PartyMemberRuntime に stats がある想定（pm.stats）
                st = getattr(pm, "stats", None)
                if st is None:
                    continue

                # 物理攻撃力としてどのフィールドを上げるかは設計次第。
                # ここでは「右手/左手の攻撃力（main_power/off_power）」を +10 する例。
                old_main = getattr(st, "main_power", None)
                old_off = getattr(st, "off_power", None)

                if old_main is not None:
                    st.main_power = old_main + 10
                if old_off is not None and old_off > 0:
                    st.off_power = old_off + 10

                applied.append(
                    (
                        pm.name,
                        old_main,
                        getattr(st, "main_power", None),
                        old_off,
                        getattr(st, "off_power", None),
                    )
                )

            # ログ
            logs.append(f"{char_name}の《Cheer》！ 味方全員の物理攻撃力が10上がった！")
            for name, m0, m1, o0, o1 in applied:
                if o0 is not None and o0 > 0:
                    logs.append(f"  - {name}: 右手 {m0}→{m1} / 左手 {o0}→{o1}")
                else:
                    logs.append(f"  - {name}: {m0}→{m1}")

            return dmg_to_enemy, None

        # 未実装 special → 物理にフォールバック
        if char_attack_kind == "special" and not handled_special:
            logs.append(
                f"{char_name}のコマンド《{char_battle_command}》は未実装なので物理攻撃として処理します"
            )
            char_attack_kind = "physical"

    # ----------------------------------------------------------------------
    # 最後に physical（通常攻撃）
    # ----------------------------------------------------------------------
    if char_attack_kind == "physical":
        if char_weapon_hand == "main":
            attack_elems = char_stats.main_weapon_elements
        else:
            attack_elems = char_stats.off_weapon_elements

        relation, hit_elems = element_relation_and_hits_for_monster(
            enemy_json, attack_elems
        )

        res = _as_attack_result(
            physical_damage_char_to_enemy(
                char=char_stats,
                enemy=enemy_stats,
                hand=char_weapon_hand,
                element_relation=relation,
                rng=rng,
                use_expectation=False,
                blind=char_is_blind,
                attacker_is_mini_or_toad=char_is_mini_or_toad,
                return_crit=True,
                return_hits=True,  # ★追加
                attacker_state=char_state,
            )
        )
        dmg_to_enemy = res.damage
        crit = res.is_critical
        net_hits = res.hit_count

        print(
            "main_power",
            char_stats.main_power,
            "main_mul",
            char_stats.main_atk_multiplier,
            "main_acc",
            char_stats.main_accuracy,
        )

        # 表示用（整数に丸める）
        hits_disp = max(0, int(round(net_hits)))  # 例：3.65 → 4
        hits_msg = f"（{hits_disp}ヒット）" if hits_disp > 0 else "（ミス）"

        # Black Belt: Boost 倍率適用
        boost_used = 0
        boost_comment = ""

        if getattr(char_state, "boost_count", 0) > 0:
            boost_used = char_state.boost_count

            if boost_used == 1:
                dmg_to_enemy *= 2
                boost_comment = " Boost効果でダメージ2倍！"
            elif boost_used == 2:
                dmg_to_enemy *= 3
                boost_comment = " Boost効果でダメージ3倍！"
            else:
                boost_comment = ""

            char_state.boost_count = 0
            char_state.temp_flags.pop("boosting", None)

        dmg_to_enemy = int(dmg_to_enemy)

        old_enemy_hp = enemy_state.hp
        enemy_state.hp = max(enemy_state.hp - dmg_to_enemy, 0)

        relation_msg = relation_comment(relation, hit_elems, perspective="attacker")

        attack_label = "の物理攻撃"
        if char_battle_command == "Sing":
            attack_label = "は歌った"

        relation_msg = relation_comment(relation, hit_elems, perspective="attacker")

        if crit:
            prefix = (
                f"{char_name}{attack_label} クリティカルヒット！{hits_msg} "
                f"{relation_msg + ' ' if relation_msg else ''}"
            )
        else:
            prefix = (
                f"{char_name}{attack_label}！{hits_msg} "
                f"{relation_msg + ' ' if relation_msg else ''}"
            )

        suffix = boost_comment

        log_damage(
            logs,
            prefix,
            enemy_name,
            dmg_to_enemy,
            old_enemy_hp,
            enemy_state.hp,
            "attacker",
            "remain",
            None,
            suffix,
        )

    # ここまで来たら戦闘は継続中（敵ターンへ）
    return dmg_to_enemy, None


# 5) 敵の1行動フェーズ（★ここだけが「敵側ロジック」）================================================


def run_enemy_turn(
    *,
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: Dict[str, Any],
    char_state: BattleActorState,
    enemy_state: BattleActorState,
    char_attack_kind: BattleKind,
    dmg_to_enemy: int,  # キャラ側ターンで与えたダメージ
    char_conf: bool,  # キャラが混乱中に攻撃していたかどうか
    char_is_mini_or_toad: bool,  # キャラ側の Mini/Toad（被弾時用）
    logs: List[str],
    state: RuntimeState,
    rng: Optional[Random] = None,
    party_members: list[PartyMemberRuntime],  # ← 型名はあなたの実装に合わせて
) -> OneTurnResult:
    """
    「敵の1行動フェーズ」だけを担当する関数。
    - HPや状態異常などは char_state / enemy_state / char_stats / enemy_stats に直接書き込む
    - ログは logs に append していく
    - 1ターンの最終結果を OneTurnResult として返す
    """
    if rng is None:
        rng = Random()

    # print(f"[Debug:turn_logic/run_enemy_turn - enemy_json] {enemy_json.get("Spells")}")

    enemy_attack = None  # 最後に OneTurnResult.enemy_attack_result に入れるやつ
    dmg_to_char = 0  # キャラが受けたダメージ

    # --- デフォルト（まず continue 扱い） ---
    end_reason = "continue"
    escaped = False
    enemy_attack = None  # ここはあなたの型に合わせる

    # ------------------------------------------------------------
    # 1) すでに敵が死んでいたら何もしない
    # ------------------------------------------------------------
    if enemy_state.hp <= 0:
        # logs.append(f"{enemy_name}を倒した！")
        return OneTurnResult(
            char_state=char_state,
            enemy_state=enemy_state,
            logs=logs,
            enemy_attack_result=None,
            escaped=False,
            end_reason="enemy_defeated",
        )

    # ★ キャラがこの時点で戦闘不能なら、敵ターンに入らず終了
    if char_state.hp <= 0:
        idx = random_alive_char_index(party_members, rng)
        if idx is None:
            logs.append(f"{char_name}は力尽きた…")
            return OneTurnResult(
                char_state=char_state,
                enemy_state=enemy_state,
                logs=logs,
                enemy_attack_result=None,
                escaped=False,
                end_reason="char_defeated",
            )
        # ターゲット差し替え
        new_target = party_members[idx]
        char_name = new_target.name
        char_stats = new_target.stats
        char_state = new_target.state

    # ------------------------------------------------------------
    # 敵ターンで使う状態異常フラグを最新状態から定義
    # ------------------------------------------------------------
    enemy_is_blind = enemy_state.has(Status.BLIND)
    enemy_is_mini_or_toad = enemy_state.has(Status.MINI) or enemy_state.has(Status.TOAD)
    enemy_is_silenced = enemy_state.has(Status.SILENCE)

    enemy_sleep = enemy_state.has(Status.SLEEP)
    enemy_para = enemy_state.has(Status.PARALYZE)
    enemy_conf = enemy_state.has(Status.CONFUSION)

    # ターン開始時点（＝キャラ行動後の「現時点」）で混乱していたか
    enemy_was_confused_at_start = enemy_conf

    # ------------------------------------------------------------
    # 2) 敵 麻痺の回復判定
    # ------------------------------------------------------------
    if enemy_para:
        r = rng.random()
        logs.append(f"[{enemy_name}] Paralysis check {r:.2f}")
        if r < 0.3:
            enemy_state.statuses.discard(Status.PARALYZE)
            enemy_para = False
            logs.append(f"{enemy_name}の麻痺が解けた！")

    # 麻痺が治ったかどうかを再確認
    enemy_para = enemy_state.has(Status.PARALYZE)

    # =========================================================
    # 3) 敵逃走判定（Boss 以外 & Lv 差 > 15）
    # =========================================================
    is_boss = bool(enemy_json.get("Boss") or enemy_json.get("IsBoss"))

    if not is_boss:
        lowest_char_level = char_stats.level
        level_diff = lowest_char_level - enemy_stats.level

        if level_diff > 15:
            monster_hit_percent = max(0, min(100, enemy_stats.accuracy_percent))
            chance_to_run = max(0, min(100, 100 - monster_hit_percent))

            r = rng.random() * 100.0

            logs.append(
                f"{enemy_name}は逃げ出そうとしている…"
                f"（Lv差 {level_diff} / 逃走率 {chance_to_run:.1f}% / 判定値 {r:.1f}）"
            )

            if r < chance_to_run:
                # 逃走成功：HPを0にして「戦闘から退場」扱い
                logs.append(f"{enemy_name}は逃げ出した！")
                enemy_state.hp = 0

                return OneTurnResult(
                    char_state=char_state,
                    enemy_state=enemy_state,
                    logs=logs,
                    enemy_attack_result=None,
                    escaped=True,
                    end_reason="enemy_escaped",
                )

    # =========================================================
    # 4) 「キャラが物理を当てたか」に応じた Sleep / Confusion 解除
    # =========================================================
    enemy_was_physically_hit = False

    # キャラ側の行動が physical で、かつダメージ > 0 なら「物理被弾あり」
    if char_attack_kind == "physical":
        enemy_was_physically_hit = dmg_to_enemy > 0

    # 混乱中の攻撃で敵を殴った場合も「物理扱い」
    if char_conf:
        enemy_was_physically_hit = enemy_was_physically_hit or (dmg_to_enemy > 0)

    if enemy_was_physically_hit:
        if enemy_state.has(Status.CONFUSION):
            enemy_state.statuses.discard(Status.CONFUSION)
            logs.append(f"{enemy_name}の混乱が解けた！")

        if enemy_state.has(Status.SLEEP):
            enemy_state.statuses.discard(Status.SLEEP)
            logs.append(f"{enemy_name}は目を覚ました！")

    # Sleep フラグ更新
    enemy_sleep = enemy_state.has(Status.SLEEP)

    # =========================================================
    # 5) 敵の状態異常を見て実際の行動を決める
    # =========================================================

    # ★ この時点で最新状態に更新（ただし enemy_was_confused_at_start はさっき保存済み）
    enemy_conf = enemy_state.has(Status.CONFUSION)
    enemy_sleep = enemy_state.has(Status.SLEEP)
    enemy_para = enemy_state.has(Status.PARALYZE)
    enemy_is_silenced = enemy_state.has(Status.SILENCE)

    # --- Sleep / Paralysis で行動不能 ---
    if enemy_sleep:
        logs.append(f"{enemy_name}は眠っていて動けない…")
        enemy_attack = None
        dmg_to_char = 0

    elif enemy_para:
        logs.append(f"{enemy_name}は麻痺していて動けない…")
        enemy_attack = None
        dmg_to_char = 0

    # --- Confusion（開始時から混乱状態だった場合のみ特別処理）---
    elif enemy_was_confused_at_start and enemy_state.has(Status.CONFUSION):
        logs.append(f"{enemy_name}は混乱している！")

        if rng.random() < 0.5:
            # ---- 自分を攻撃（自傷）----
            dummy_char = ff3_confused_self_dummy_char(enemy_stats)

            res = _as_attack_result(
                physical_damage_enemy_to_char(
                    enemy=enemy_stats,
                    char=dummy_char,
                    rng=rng,
                    use_expectation=False,
                    attacker_is_blind=enemy_is_blind,
                    attacker_is_mini_or_toad=enemy_is_mini_or_toad,
                    target_is_mini_or_toad=enemy_is_mini_or_toad,
                    return_crit=True,
                    target_state=enemy_state,
                )
            )

            dmg_to_self = res.damage
            crit = res.is_critical
            net_hits = res.hit_count

            # ★ 自傷も「通常攻撃」として EnemyAttackResult を作って統一
            enemy_attack = EnemyAttackResult(
                damage=dmg_to_self,
                attack_type="normal",
                attack_name="Physical",
                is_crit=crit,
                net_hits=net_hits,
                element_relation="normal",
                hit_elements=[],
                is_reflectable_spell=False,
            )

            # HP反映（自傷）
            old_enemy_hp = enemy_state.hp
            enemy_state.hp = max(enemy_state.hp - dmg_to_self, 0)

            # ★ ログは共通処理側で出したいので、ここでは出さない
            #   （もし「混乱して自分を攻撃」を必ず表示したいなら、専用prefix用のフラグを
            #    EnemyAttackResult に持たせる/別フィールドで表現するのがきれいです）
            # → 今回は “ログを統一” が目的なので、ここはHP反映と状態処理だけ。

            # 自傷ダメージ > 0 なら混乱解除
            if dmg_to_self > 0 and enemy_state.has(Status.CONFUSION):
                enemy_state.statuses.discard(Status.CONFUSION)
                logs.append(f"{enemy_name}の混乱が解けた！")

            # キャラはこの分岐では殴られてない
            dmg_to_char = 0

        else:
            # ---- キャラを攻撃 ----
            res = _as_attack_result(
                physical_damage_enemy_to_char(
                    enemy=enemy_stats,
                    char=char_stats,
                    rng=rng,
                    use_expectation=False,
                    attacker_is_blind=enemy_is_blind,
                    attacker_is_mini_or_toad=enemy_is_mini_or_toad,
                    target_is_mini_or_toad=char_is_mini_or_toad,
                    return_crit=True,
                    target_state=char_state,
                )
            )
            dmg_to_char = res.damage
            crit = res.is_critical
            net_hits = res.hit_count

            # ★ ここが重要：この分岐でも enemy_attack を作る（Noneにしない）
            enemy_attack = EnemyAttackResult(
                damage=dmg_to_char,
                attack_type="normal",
                attack_name="Physical",
                is_crit=crit,
                net_hits=net_hits,
                element_relation="normal",
                hit_elements=[],
                is_reflectable_spell=False,
            )

            # ※ HP反映とログは後段「Reflectしなかった通常ダメージ処理」に任せる
            #    なのでここでは char_state.hp を減らさない（後段で1回だけ減らす）

    # --- Silence 中：スペシャル禁止で通常物理のみ ---
    elif enemy_is_silenced:
        res = _as_attack_result(
            physical_damage_enemy_to_char(
                enemy=enemy_stats,
                char=char_stats,
                rng=rng,
                use_expectation=False,
                attacker_is_blind=enemy_is_blind,
                attacker_is_mini_or_toad=enemy_is_mini_or_toad,
                target_is_mini_or_toad=char_is_mini_or_toad,
                return_crit=True,
                target_state=char_state,
            )
        )
        dmg_to_char = res.damage
        crit = res.is_critical
        net_hits = res.hit_count

        # ★ 沈黙中でも enemy_attack を作って共通ログに流す（Noneにしない）
        enemy_attack = EnemyAttackResult(
            damage=dmg_to_char,
            attack_type="normal",
            attack_name="Physical",
            is_crit=crit,
            net_hits=net_hits,
            element_relation="normal",
            hit_elements=[],
            is_reflectable_spell=False,
        )

        # ※ ここでも HP反映とログは後段の共通処理に任せる
        #    （だから old_char_hp を取って減らす処理＆log_damage は削除）

    else:
        # --------------------------------------------------------
        # 6) 通常行動 or スペシャル行動
        # --------------------------------------------------------

        # ★ キャラがジャンプ中なら敵の攻撃は当たらない
        if char_state.is_jumping:
            logs.append(f"{char_name}は空中にいる！敵の攻撃は届かない！")
            return OneTurnResult(
                char_state=char_state,
                enemy_state=enemy_state,
                logs=logs,
                enemy_attack_result=None,
                escaped=False,
                end_reason="continue",
            )

        # print(f"[Debug:turn_logic/run_enemy_turn - enemy_json] {enemy_json}")
        # print(f"[Debug:turn_logic/run_enemy_turn - enemy_attack] {enemy_attack}")

        enemy_attack = enemy_attack_to_char_with_special(
            monster=enemy_json,
            enemy=enemy_stats,
            char=char_stats,
            state=state,
            rng=rng,
            use_expectation=False,
            attacker_is_blind=enemy_is_blind,
            attacker_is_mini_or_toad=enemy_is_mini_or_toad,
            target_is_mini_or_toad=char_is_mini_or_toad,
            return_crit=True,
            target_state=char_state,
        )
        # enemy_attack は出た（special / physical など）
        dmg_to_char = enemy_attack.damage if enemy_attack is not None else 0

        # --------------------------------------------------------
        # ★ AoE spell の場合は「ここで処理して return」する
        #    （単体Reflectブロックを通さないのが重要）
        # --------------------------------------------------------
        if (
            enemy_attack is not None
            and enemy_attack.attack_type == "special"
            and enemy_attack.attack_name is not None
        ):
            spell_def = _find_spell_json_for_enemy_attack(enemy_json, enemy_attack)

            if spell_def and spell_is_aoe(spell_def):
                # 状態異常AoE（Mind Blast型）
                if spell_base_power(spell_def) <= 0 and spell_has_ailment(spell_def):
                    enemy_cast_aoe_status_spell_to_party(
                        spell_json=spell_def,
                        enemy_name=enemy_name,
                        party_members=party_members,
                        rng=rng,
                        logs=logs,
                    )
                    return OneTurnResult(
                        char_state=char_state,
                        enemy_state=enemy_state,
                        logs=logs,
                        enemy_attack_result=None,
                        end_reason="continue",
                    )

                # ダメージAoE（Snowstorm 等）※ Reflectはこの関数内で「味方ごと」に処理される
                enemy_down = enemy_cast_aoe_damage_spell_to_party(
                    spell_json=spell_def,
                    enemy_name=enemy_name,
                    party_members=party_members,
                    rng=rng,
                    logs=logs,
                    caster_state=enemy_state,
                    caster_max_hp=getattr(enemy_state, "max_hp", None),
                )

                if enemy_down:
                    return OneTurnResult(
                        char_state=char_state,
                        enemy_state=enemy_state,
                        logs=logs,
                        enemy_attack_result=None,
                        end_reason="enemy_defeated",
                    )

                return OneTurnResult(
                    char_state=char_state,
                    enemy_state=enemy_state,
                    logs=logs,
                    enemy_attack_result=None,
                    end_reason="continue",
                )

        # --------------------------------------------------------
        # Reflect 判定（スペル / Reflectable: Yes のときだけ）
        # --------------------------------------------------------
        if (
            enemy_attack is not None
            and getattr(char_state, "reflect_charges", 0) > 0
            and getattr(enemy_attack, "is_reflectable_spell", False)
        ):
            # 1回分消費
            char_state.reflect_charges -= 1

            reflected_damage = dmg_to_char
            dmg_to_char = 0  # キャラはノーダメージ

            old_enemy_hp = enemy_state.hp
            enemy_state.hp = max(enemy_state.hp - reflected_damage, 0)

            log_damage(
                logs,
                f"{enemy_name}のスペル《{enemy_attack.attack_name}》はReflectで跳ね返された！ ",
                enemy_name,
                reflected_damage,
                old_enemy_hp,
                enemy_state.hp,
                "target",
                "remain",
            )

            # この攻撃は「キャラには当たっていない」扱いにしたいので、以降 enemy_attack=None
            enemy_attack = None

        # ==== Reflect しなかったスペル固有処理 =======================
        if (
            enemy_attack is not None
            and enemy_attack.attack_type == "special"
            and enemy_attack.attack_name is not None
        ):
            spell_def = _find_spell_json_for_enemy_attack(enemy_json, enemy_attack)
            spell_name = (spell_def or {}).get("Name") or enemy_attack.attack_name
            name_lower = spell_name.lower()

            # 0) spell_def が無いと Target も見れないので fallback
            if not spell_def:
                # ここは好み：通常攻撃へフォールバック or 何もしない
                pass

            # 1) Tornado など「固有処理」を先に（例）
            if name_lower == "tornado":
                enemy_cast_tornado_to_char(
                    spell_json=spell_def or {},
                    char_state=char_state,
                    char_stats=char_stats,
                    char_name=char_name,
                    enemy_name=enemy_name,
                    rng=rng,
                    logs=logs,
                )
                dmg_to_char = 0
                enemy_attack = None

            # 2) ★ Target が All Enemies なら汎用AoEへ
            elif spell_def and spell_is_aoe(spell_def):
                # 状態異常系全体攻撃（Mind Blast型：BasePower==0 かつ StatusAilmentあり）
                if spell_base_power(spell_def) <= 0 and spell_has_ailment(spell_def):
                    enemy_cast_aoe_status_spell_to_party(
                        spell_json=spell_def,
                        enemy_name=enemy_name,
                        party_members=party_members,
                        rng=rng,
                        logs=logs,
                    )
                # ダメージ系全体攻撃
                else:
                    enemy_down = enemy_cast_aoe_damage_spell_to_party(
                        spell_json=spell_def,
                        enemy_name=enemy_name,
                        party_members=party_members,
                        rng=rng,
                        logs=logs,
                        caster_state=enemy_state,  # ★ ここが重要：敵のstate
                        caster_max_hp=getattr(enemy_state, "max_hp", None),  # ★ あれば
                    )
                if enemy_down:
                    # ここで即勝利扱いにする（あなたの end_reason に合わせる）
                    return OneTurnResult(
                        char_state=char_state,
                        enemy_state=enemy_state,
                        logs=logs,
                        enemy_attack_result=None,
                        end_reason="enemy_defeated",
                    )
                dmg_to_char = 0
                enemy_attack = None

            # 3) それ以外（単体スペル）は従来の通常special処理へ
            else:
                # 3-1) Drain
                if name_lower == "drain":
                    if spell_def is not None:
                        spell_info = SpellInfo(
                            power=int(spell_def.get("BasePower", 0) or 0),
                            accuracy_percent=int(
                                (
                                    spell_def.get("BaseAccuracy")
                                    or spell_def.get("Accuracy")
                                    or 100
                                )
                            ),
                            magic_type=str(spell_def.get("Type") or "").lower(),
                            elements=parse_elements(spell_def.get("Element")),
                        )
                        enemy_caster = enemy_caster_from_monster(enemy_json)
                        enemy_cast_drain_to_char(
                            spell=spell_info,
                            enemy_stats=enemy_caster,
                            enemy_state=enemy_state,
                            char_stats=char_stats,
                            char_state=char_state,
                            char_name=char_name,
                            rng=rng,
                            logs=logs,
                        )
                        dmg_to_char = 0
                        enemy_attack = None

                # 3-2) Reflect（敵自身にバリア）
                elif name_lower == "reflect":
                    apply_reflect_to_actor(
                        target_state=enemy_state,
                        target_name=enemy_name,
                        logs=logs,
                        charges=1,
                    )
                    dmg_to_char = 0
                    enemy_attack = None

                # 3-3) Haste / Protect（自己バフ）
                elif name_lower == "haste":
                    # 命中判定（そのまま）
                    if spell_def is not None:
                        base_acc = spell_def.get("BaseAccuracy")
                        if base_acc is None:
                            base_acc = spell_def.get("Accuracy", 1.0)
                    else:
                        base_acc = 1.0

                    mind = getattr(enemy_stats, "mind", 0)
                    hit_percent = calc_buff_hit_percent(base_acc, mind)

                    if rng.random() * 100.0 >= hit_percent:
                        logs.append(
                            f"{enemy_name}は《Haste》を唱えた！ しかし何も起こらなかった…"
                        )
                        dmg_to_char = 0
                        enemy_attack = None
                    else:
                        # ★敵は main_power 等を持たない前提で、attack_multiplier を上げる
                        L = getattr(enemy_stats, "level", 1)
                        J = getattr(enemy_stats, "job_level", 0)
                        base_factor = (mind // 16) + (L // 16) + (J // 32) + 1

                        base_power = float((spell_def or {}).get("BasePower", 5) or 5)
                        # ざっくり：base_factor を 1 以上上げる（運用に合わせて調整OK）
                        # 例：BasePower に応じて上昇幅を増やす
                        add = max(1, int(round(base_power / 5.0)))
                        old_mul = int(getattr(enemy_stats, "attack_multiplier", 1))
                        enemy_stats.attack_multiplier = max(1, old_mul + add)

                        logs.append(
                            f"{enemy_name}は《Haste》を唱えた！ "
                            f"攻撃回数が {old_mul}→{enemy_stats.attack_multiplier} に上がった。"
                        )

                        dmg_to_char = 0
                        enemy_attack = None

                elif name_lower == "protect":
                    if spell_def is not None:
                        base_acc = spell_def.get("BaseAccuracy")
                        if base_acc is None:
                            base_acc = spell_def.get("Accuracy", 1.0)
                    else:
                        base_acc = 1.0

                    mind = 0
                    hit_percent = calc_buff_hit_percent(base_acc, mind)

                    if rng.random() * 100.0 >= hit_percent:
                        logs.append(
                            f"{enemy_name}は《Protect》を唱えた！ "
                            f"しかし何も起こらなかった…"
                        )
                        dmg_to_char = 0
                        enemy_attack = None

                    else:
                        L = enemy_stats.level
                        J = enemy_stats.job_level
                        base_factor = (mind // 16) + (L // 16) + (J // 32) + 1

                        if spell_def is not None:
                            base_power = float(spell_def.get("BasePower", 5))
                        else:
                            base_power = 5.0

                        enemy_stats_any = cast(Any, enemy_stats)
                        old_def, old_mdef = apply_protect_buff(
                            enemy_stats_any,
                            base_power=base_power,
                            base_factor=base_factor,
                            rng=rng,
                        )

                        logs.append(
                            f"{enemy_name}は《Protect》を唱えた！ "
                            f"防御力 {old_def}→{enemy_stats.defense}、"
                            f"魔法防御 {old_mdef}→{enemy_stats.magic_defense} に上がった。"
                        )
                        dmg_to_char = 0
                        enemy_attack = None

                # 3-4) Erase / Toad / Mini / その他状態異常魔法
                else:
                    handled = _apply_enemy_spell_ailments_to_char(
                        spell_json=spell_def or {},
                        enemy_json=enemy_json,
                        enemy_name=enemy_name,
                        char_stats=char_stats,
                        char_state=char_state,
                        char_name=char_name,
                        enemy_caster=enemy_caster_from_monster(enemy_json),
                        rng=rng,
                        logs=logs,
                    )
                    if handled:
                        dmg_to_char = 0
                        enemy_attack = None

        # --------------------------------------------------------
        # Reflect しなかった通常ダメージ処理
        # --------------------------------------------------------
        # ダメージ適用前のHPを記録
        old_char_hp = char_state.hp

        # 防御（Defend）によるダメージ軽減
        if getattr(char_state, "temp_flags", {}).get("defending"):
            if dmg_to_char > 0:
                dmg_to_char = int(dmg_to_char * 0.5)
                logs.append(f"{char_name}は防御してダメージを軽減した！")

        # 最終的なダメージを適用
        char_state.hp = max(char_state.hp - dmg_to_char, 0)

        # ここまでで char_state.hp は更新済み（old_char_hp もある）
        if enemy_attack is None:
            # 例：AOE/Tornado などで enemy_attack を None にした、または行動不能など
            if dmg_to_char > 0:
                log_damage(
                    logs=logs,
                    prefix=f"{enemy_name}の攻撃！ ",
                    target_name=char_name,
                    damage=dmg_to_char,
                    old_hp=old_char_hp,
                    new_hp=char_state.hp,
                    perspective="target",
                    hp_style="arrow_with_max",
                    max_hp=getattr(char_state, "max_hp", None),
                    shout=True,
                )
        else:
            # enemy_attack がある場合
            if dmg_to_char > 0:

                # ★ 追加：ヒット数を prefix に差し込む（通常攻撃のみ）
                hit_count = None
                if enemy_attack.attack_type == "normal":
                    hit_count = getattr(
                        enemy_attack, "net_hits", None
                    )  # または hit_count 等

                hit_suffix = ""
                if hit_count is not None:
                    # 表示を揃えたいなら丸める（例：2.8ヒット）
                    # hit_count が int の場合でも float にしてもOK
                    hits_disp = max(0, int(round(hit_count)))
                    hit_suffix = (
                        f"（{hits_disp}ヒット）" if hits_disp > 0 else "（ミス）"
                    )

                # ★ クリティカル表示（任意）
                is_crit = bool(getattr(enemy_attack, "is_crit", False))

                if enemy_attack.attack_type == "normal":
                    if is_crit:
                        prefix = (
                            f"  {enemy_name}の攻撃 クリティカルヒット！{hit_suffix}"
                        )
                    else:
                        prefix = f"  {enemy_name}の攻撃！{hit_suffix}"
                else:
                    spell_name = enemy_attack.attack_name or "攻撃"
                    prefix = f"{enemy_name}の《{spell_name}》！ "

                log_damage(
                    logs=logs,
                    prefix=prefix,
                    target_name=char_name,
                    damage=dmg_to_char,
                    old_hp=old_char_hp,
                    new_hp=char_state.hp,
                    perspective="target",
                    hp_style="arrow_with_max",
                    max_hp=getattr(char_state, "max_hp", None),
                    shout=True,
                )
            else:
                logs.append(f"{enemy_name}の攻撃！ しかしダメージを与えられなかった…")

    # ------------------------------------------------------------
    # 防御フラグを元に戻す
    # ------------------------------------------------------------
    if getattr(char_state, "temp_flags", None) is not None:
        char_state.temp_flags.pop("defending", None)

    # ------------------------------------------------------------
    # 7) 物理攻撃だった場合の Partial Petrify / Sleep / Confusion 解消
    # ------------------------------------------------------------
    was_physical = False
    if enemy_attack is None:
        # 上の「沈黙中の通常攻撃」など、明示的に物理攻撃した場合
        was_physical = dmg_to_char > 0
    else:
        if enemy_attack.attack_type == "normal":
            was_physical = True

    if was_physical and (enemy_attack is None or enemy_attack.attack_type == "normal"):
        status_attack_name = enemy_json.get("Status Attack")
        apply_partial_petrify_from_status_attack(
            target_state=char_state,
            status_attack_name=status_attack_name,
            logs=logs,
            target_name=char_name,
        )

        if char_state.has(Status.CONFUSION):
            char_state.statuses.discard(Status.CONFUSION)
            logs.append(f"{char_name}の混乱が解けた！")

        if char_state.has(Status.SLEEP):
            char_state.statuses.discard(Status.SLEEP)
            logs.append(f"{char_name}は目を覚ました！")

    # ------------------------------------------------------------
    # 8) enemy_attack.inflicted_status の処理
    # ------------------------------------------------------------
    if enemy_attack and enemy_attack.inflicted_status:
        name = enemy_attack.inflicted_status

        if name.startswith("Partial Petrification"):
            amount = partial_petrify_amount_from_name(name)
            apply_partial_petrification(
                target_state=char_state,
                amount=amount,
                target_name=char_name,
                logs=logs,
            )
        else:
            status_map = {
                "Poison": Status.POISON,
                "Blind": Status.BLIND,
                "Mini": Status.MINI,
                "Silence": Status.SILENCE,
                "Toad": Status.TOAD,
                "Confusion": Status.CONFUSION,
                "Sleep": Status.SLEEP,
                "Paralysis": Status.PARALYZE,
                "Petrification": Status.PETRIFY,
            }
            inflicted_status_target = status_map.get(name)

            if inflicted_status_target is not None:
                char_state.statuses.add(inflicted_status_target)
                logs.append(
                    f"{char_name}は{enemy_attack.attack_name}で{inflicted_status_target.name}状態になった！（簡易実装）"
                )

    # ------------------------------------------------------------
    # 9) キャラが倒れたかどうかチェック（既存ヘルパ使用）
    # ------------------------------------------------------------
    if char_state.hp <= 0:
        logs.append(f"{char_name}は力尽きた…")
        if not any_char_alive(party_members):
            end_reason = "char_defeated"
        else:
            end_reason = "continue"

    # 敵全滅チェック（必要なら）
    if enemy_state.hp <= 0:
        end_reason = "enemy_defeated"

    # ★ 必ずここで返す
    return OneTurnResult(
        char_state=char_state,
        enemy_state=enemy_state,
        logs=logs,
        enemy_attack_result=enemy_attack,
        escaped=escaped,
        end_reason=end_reason,
    )


def enemy_attack_to_char_with_special(
    monster: Dict[str, Any],
    enemy: FinalEnemyStats,
    char: FinalCharacterStats,
    state: RuntimeState,
    rng: Optional[Random] = None,
    use_expectation: bool = True,
    attacker_is_blind: bool = False,
    attacker_is_mini_or_toad: bool = False,
    target_is_mini_or_toad: bool = False,
    return_crit: bool = False,
    target_state: Optional[BattleActorState] = None,  # ★ 追加
) -> EnemyAttackResult:
    """
    敵がキャラクターに攻撃する 1 回分の攻撃結果を返す。
    ・SpecialAttackRate の確率で "Special Attacks" からスペシャル攻撃
    ・それ以外は通常物理攻撃（physical_damage_enemy_to_char）
    ・スペシャル攻撃のダメージは monster["Spells"] の
      {Name, Power, Accuracy, Multiplier, Element, StatusAilment} を使用
    ・キャラ防具の ElementalResist による属性半減も反映
    ・状態異常（Blind など）は、期待値モードでは成功確率、
      乱数モードでは実際に入ったかどうかを返す
    """

    if rng is None:
        rng = Random()

    special_rate = monster.get("SpecialAttackRate") or 0.0
    specials = monster.get("Special Attacks") or []

    # スペシャル攻撃が存在しない or 確率 0 の場合は、通常物理のみ
    if not specials or special_rate <= 0:
        res = _as_attack_result(
            physical_damage_enemy_to_char(
                enemy=enemy,
                char=char,
                rng=rng,
                use_expectation=use_expectation,
                attacker_is_blind=attacker_is_blind,
                attacker_is_mini_or_toad=attacker_is_mini_or_toad,
                target_is_mini_or_toad=target_is_mini_or_toad,
                return_crit=True,
                target_state=target_state,
            )
        )
        dmg = res.damage
        crit = res.is_critical
        net_hits = res.hit_count

        return EnemyAttackResult(
            damage=dmg,
            attack_type="normal",
            attack_name="Physical",
            is_crit=crit,
            net_hits=net_hits,  # ★ここ
        )

    # --------------------------------------------------------
    # 期待値モード：通常攻撃とスペシャル攻撃の期待値を混合
    # --------------------------------------------------------
    if use_expectation:
        normal_dmg = _as_damage(
            physical_damage_enemy_to_char(
                enemy=enemy,
                char=char,
                rng=rng,
                use_expectation=True,
                attacker_is_blind=attacker_is_blind,
                attacker_is_mini_or_toad=attacker_is_mini_or_toad,
                target_is_mini_or_toad=target_is_mini_or_toad,
                return_crit=False,
                target_state=target_state,
            )
        )

        spell_list = monster.get("Spells") or []
        total_rate = sum((sa.get("Rate") or 0) for sa in specials)

        special_expect = 0.0
        status_prob_expect = 0.0  # 状態異常成功確率の期待値
        if total_rate > 0:
            for sa in specials:
                rate = sa.get("Rate") or 0.0
                if rate <= 0:
                    continue
                attack_name = sa.get("Attack")
                spell_def = None
                for s in spell_list:
                    if s.get("Name") == attack_name:
                        spell_def = s
                        break
                if spell_def is None:
                    continue

                power = int(spell_def.get("Power", 0))
                mult = int(spell_def.get("Multiplier", 1) or 1)
                acc_percent = int(round((spell_def.get("Accuracy", 1.0) or 1.0) * 100))

                enemy_caster = EnemyCasterStats(
                    magic_power_base=power,
                    magic_multiplier=mult,
                    magic_accuracy_percent=acc_percent,
                )

                attack_elems = elements_from_monster_spell(spell_def)
                rel_to_char, hit_elems = element_relation_and_hits_for_char(
                    char, attack_elems
                )

                dmg_spec = magic_damage_enemy_to_char(
                    enemy_caster=enemy_caster,
                    char=char,
                    element_relation=rel_to_char,
                    rng=rng,
                    use_expectation=False,
                    split_to_targets=1,
                    attacker_is_blind=attacker_is_blind,
                    target_is_mini_or_toad=target_is_mini_or_toad,
                    target_state=target_state,  # ★ ここ！
                )

                # 状態異常がある場合は成功確率も計算
                status_name = _get_status_name_from_monster_spell(spell_def)
                status_prob = 0.0
                if status_name:
                    status_prob = _compute_status_success_prob_for_enemy_spell(
                        enemy_caster, char
                    )

                weight = rate / total_rate
                special_expect += weight * dmg_spec
                status_prob_expect += weight * status_prob

        mixed = (1.0 - special_rate) * normal_dmg + special_rate * special_expect
        return EnemyAttackResult(
            damage=max(int(round(mixed)), 0),
            attack_type="mixed",
            attack_name=None,
            inflicted_status=None,
            status_success_prob=(
                (special_rate * status_prob_expect) if status_prob_expect > 0 else 0.0
            ),
            is_crit=False,  # ★期待値モードでは crit は概念的に無いので is_crit=False
        )

    # --------------------------------------------------------
    # 乱数モード：この 1 回で通常 or スペシャルを実際に選択
    # --------------------------------------------------------
    else:
        # スペシャル攻撃を行うか判定
        if rng.random() < special_rate:
            spell_def = _choose_monster_special_spell(monster, rng=rng)

            # 何も見つからなければ通常攻撃にフォールバック
            if spell_def is None:
                res = _as_attack_result(
                    physical_damage_enemy_to_char(
                        enemy=enemy,
                        char=char,
                        rng=rng,
                        use_expectation=False,
                        attacker_is_blind=attacker_is_blind,
                        attacker_is_mini_or_toad=attacker_is_mini_or_toad,
                        target_is_mini_or_toad=target_is_mini_or_toad,
                        return_crit=True,
                        target_state=target_state,
                    )
                )
                dmg = res.damage
                crit = res.is_critical
                net_hits = res.hit_count

                return EnemyAttackResult(
                    damage=dmg,
                    attack_type="normal",
                    attack_name="Physical",
                    is_crit=crit,
                    net_hits=net_hits,  # ★ここ
                )

            power = safe_int(spell_def.get("Power", 0))
            mult = safe_int(spell_def.get("Multiplier", 1) or 1)
            acc_percent = safe_int(round((spell_def.get("Accuracy", 1.0) or 1.0) * 100))

            enemy_caster = EnemyCasterStats(
                magic_power_base=power,
                magic_multiplier=mult,
                magic_accuracy_percent=acc_percent,
            )

            attack_elems = elements_from_monster_spell(spell_def)
            rel_to_char, hit_elems = element_relation_and_hits_for_char(
                char, attack_elems
            )

            # print(f"[Debug:turn_logic/enemy_attack_to_char_with_special] {enemy_caster}, {attack_elems}, {rel_to_char}")

            dmg_spec = magic_damage_enemy_to_char(
                enemy_caster=enemy_caster,
                char=char,
                element_relation=rel_to_char,
                rng=rng,
                use_expectation=False,
                split_to_targets=1,
                attacker_is_blind=attacker_is_blind,
                target_is_mini_or_toad=target_is_mini_or_toad,
                target_state=target_state,  # ★ ここ！
            )

            # 状態異常付与判定
            status_name = _get_status_name_from_monster_spell(spell_def)
            inflicted_status: Optional[str] = None
            status_prob = 0.0
            if status_name:
                status_prob = _compute_status_success_prob_for_enemy_spell(
                    enemy_caster, char
                )
                if rng.random() < status_prob:
                    inflicted_status = status_name
                    # print(status_name, status_prob)

            # ここで spell_def を持っているので Reflectable 判定
            # 1) まずモンスター JSON の Spells 内をチェック
            reflectable_raw = spell_def.get("Reflectable")

            # 2) 無ければ spells.json 側（state.spells）から補完
            if reflectable_raw is None:
                try:
                    base_spell = state.spells.get(spell_def.get("Name", ""))
                except NameError:
                    base_spell = None  # state.spells が未セットの場合

                if base_spell is not None:
                    reflectable_raw = base_spell.get("Reflectable")

            # 3) それでも見つからなければ "No" 扱い
            is_reflectable = str(reflectable_raw or "No").strip().lower() == "yes"

            return EnemyAttackResult(
                damage=max(int(dmg_spec), 0),
                attack_type="special",
                attack_name=spell_def.get("Name"),
                inflicted_status=inflicted_status,
                status_success_prob=status_prob,
                is_crit=False,
                element_relation=rel_to_char,
                hit_elements=hit_elems,
                is_reflectable_spell=is_reflectable,
            )

        # 通常物理攻撃
        res = _as_attack_result(
            physical_damage_enemy_to_char(
                enemy=enemy,
                char=char,
                rng=rng,
                use_expectation=False,
                attacker_is_blind=attacker_is_blind,
                attacker_is_mini_or_toad=attacker_is_mini_or_toad,  # ←これも入れ忘れない
                target_is_mini_or_toad=target_is_mini_or_toad,  # ←これも
                return_crit=True,
                target_state=target_state,
            )
        )
        dmg_norm = res.damage
        crit = res.is_critical
        net_hits = res.hit_count

        return EnemyAttackResult(
            damage=dmg_norm,
            attack_type="normal",
            attack_name="Physical",
            is_crit=crit,
            element_relation="normal",
            hit_elements=[],
            is_reflectable_spell=False,
            net_hits=net_hits,  # ★ここ
        )
