# ============================================================
# enemy_build: 敵構築

# build_enemies	敵名リスト → EnemyRuntime 群を構築する
# compute_enemy_base_agility	敵JSONから「行動順決定用の擬似Agility」を計算する
# compute_enemy_final_stats	monsters.jsonの1モンスターdictからFinalEnemyStatsを作成
# ============================================================

from typing import Dict, Any, List, Iterable, Optional

from combat.models import FinalEnemyStats, EnemyRuntime, BattleActorState
from combat.runtime_state import RuntimeState
from combat.spell_repo import enrich_monster_spells


# ============================================================
# 敵最終ステータス計算
# ============================================================
# 敵名リスト → EnemyRuntime 群を構築する
def build_enemies(
    *,
    enemy_defs_by_name: Dict[str, Dict[str, Any]],
    spells_by_name: Dict[str, Dict[str, Any]],
    enemy_names: Iterable[str],
    difficulty: int = 0,
) -> List[EnemyRuntime]:
    enemies: List[EnemyRuntime] = []

    for enemy_name in enemy_names:
        try:
            raw_enemy_json = enemy_defs_by_name[enemy_name]
        except KeyError as e:
            raise KeyError(
                f"enemy_defs_by_name に '{enemy_name}' が存在しません"
            ) from e

        # ★ 純度を上げる（enrich が破壊的でも安全）
        raw_enemy_json = dict(raw_enemy_json)

        enemy_json = enrich_monster_spells(
            raw_enemy_json, spells_by_name=spells_by_name
        )

        sprite_id: Optional[str] = enemy_json.get("sprite_id")
        if isinstance(sprite_id, str):
            sprite_id = sprite_id.strip() or None
        else:
            sprite_id = None

        enemy_final = compute_enemy_final_stats(enemy_json, difficulty=difficulty)
        enemy_state = BattleActorState(hp=enemy_final.hp, max_hp=enemy_final.hp)

        # ★ボス判定：PlotBattles が存在し、空でないならボス扱い
        plot_battles = enemy_json.get("PlotBattles")
        is_boss = isinstance(plot_battles, list) and len(plot_battles) > 0

        enemies.append(
            EnemyRuntime(
                name=enemy_name,
                sprite_id=sprite_id,
                stats=enemy_final,
                state=enemy_state,
                json=enemy_json,
                is_boss=is_boss,  # ★追加
            )
        )

    return enemies


# 敵の擬似 Agilityの作成（Level + Attack 回数 + 回避率 から作る）
def compute_enemy_base_agility(monster: Dict[str, Any]) -> int:
    """
    敵 JSON から「行動順決定用の擬似 Agility」を計算する。
    - Level が高い敵ほど素早く
    - Attack.Count が多い敵は手数が多い＝素早い印象に
    - Evasion.Rate が高い敵も素早い印象に
    """
    lvl = int(monster.get("Level", 1))

    atk = monster.get("Attack") or {}
    atk_count = int(atk.get("Count") or 1)

    ev = monster.get("Evasion") or {}
    eva_rate = float(ev.get("Rate") or 0.0)  # 0.1 → 10% みたいな値

    # 適当な指標：あとで好きに調整してOK
    agi = lvl
    agi += 2 * max(0, atk_count - 1)  # 攻撃回数が多いほど +2, +4, ...
    agi += int(eva_rate * 20)  # 回避 10% → +2, 50% → +10 くらいのノリ

    return max(1, agi)


def compute_enemy_final_stats(
    monster: Dict[str, Any],
    difficulty: int = 0,
) -> FinalEnemyStats:
    """
    monsters.json の 1 モンスター dict から FinalEnemyStats を作成。
    """
    atk = monster.get("Attack", {}) or {}
    ev = monster.get("Evasion", {}) or {}
    mr = monster.get("MagicResistance", {}) or {}

    # ★ ここで擬似 Agility を計算
    agility = compute_enemy_base_agility(monster)

    return FinalEnemyStats(
        name=monster.get("name", ""),
        hp=int(monster.get("HP", 0)),
        level=int(monster.get("Level", 0)),
        job_level=int(monster.get("JobLevel", 0)),
        attack_power=int(monster.get("AttackPower", 0)),
        attack_multiplier=int(atk.get("Count") or 1),
        accuracy_percent=int(round((atk.get("Accuracy") or 0.0) * 100)),
        defense=int(monster.get("Defense", 0)),
        defense_multiplier=int(ev.get("Count") or 0),
        evasion_percent=int(round((ev.get("Rate") or 0.0) * 100)),
        magic_defense=int(monster.get("MagicDefense", 0)),
        magic_def_multiplier=int(mr.get("Count") or 0),
        magic_resistance_percent=int(round((mr.get("Rate") or 0.0) * 100)),
        agility=agility,  # ★ 追加
    )
