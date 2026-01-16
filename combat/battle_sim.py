# ============================================================
# battle_sim: バトル/ラウンド/ターン全体を回す関数

# simulate_one_round_multi_party	複数キャラvs複数敵の「1ラウンド分」だけを解決する関数
# simulate_one_turn_with_spell_name	1ターンシミュレーション（魔法で攻撃する場合のためのラッパ）
# simulate_one_turn_with_item_name	1ターンシミュレーション（アイテム版ラッパ関数）
# simulate_one_turn	1ターン分の攻防をシミュレートしてログを返す簡易関数（1vs1）
# simulate_battle_once	1対1（キャラ1人vs敵1体）の戦闘を、指定された物理攻撃又は魔法で決着に達するまで繰り返す
# simulate_many_battles	同一条件でsimulate_battle_onceをn_trials回繰り返して、勝率・ターン数等表示
# simulate_battle_multi_party	複数キャラvs複数敵の戦闘を、バトル終了（全滅・逃走・敵殲滅など）まで自動で進める高レベル関数
# ============================================================

from random import Random
from typing import Optional, Literal, Dict, Any, Tuple, List

from combat.enums import Status, BattleKind
from combat.models import (
    PartyMemberRuntime,
    EnemyRuntime,
    PlannedAction,
    SideTurnResult,
)
from combat.runtime_state import RuntimeState
from combat.start_of_turn import start_of_turn_for_actor
from combat.life_check import (
    is_out_of_battle,
    any_char_alive,
    any_enemy_alive,
    random_alive_char_index,
    first_alive_enemy_index,
    first_alive_char_index,
    all_enemies_defeated,
    all_chars_defeated,
)
from combat.initiative import calc_initiative
from combat.turn_logic import run_enemy_turn, run_character_turn
from combat.spell_repo import spell_from_json
from combat.magic_damage import healing_spell_kind
from combat.progression import apply_job_sp_for_command


def simulate_one_round_multi_party(
    party_members: List[PartyMemberRuntime],
    enemies: List[EnemyRuntime],
    planned_actions: List[Optional[PlannedAction]],
    state: RuntimeState,
    rng: Optional[Random] = None,
    save: Optional[dict] = None,
    spells_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
    items_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[str], SideTurnResult, list[dict]]:

    if rng is None:
        rng = Random()  # ← モジュールではなくインスタンス

    logs: List[str] = []
    final_result = SideTurnResult(end_reason="continue")

    # ★追加：eventsはターン全体で蓄積する（ループ内で初期化しない）
    events: list[dict] = []

    # =====================================
    # ① ターン開始時効果
    # =====================================
    for pm in party_members:
        start_of_turn_for_actor(
            actor_name=pm.name,
            stats=pm.stats,
            state=pm.state,
            logs=logs,
            rng=rng,
            is_enemy=False,
            enemy_json=None,
        )

    for em in enemies:
        start_of_turn_for_actor(
            actor_name=em.name,
            stats=em.stats,
            state=em.state,
            logs=logs,
            rng=rng,
            is_enemy=True,
            enemy_json=em.json,
        )

    # =====================================
    # ② 行動順リスト作成
    # =====================================
    actors: List[Tuple[str, int, int]] = []  # (side, index, initiative)

    for i, pm in enumerate(party_members):
        if is_out_of_battle(pm.state):
            continue
        init = calc_initiative(pm.stats.agility, rng)
        actors.append(("char", i, init))

    for i, em in enumerate(enemies):
        if is_out_of_battle(em.state):
            continue
        init = calc_initiative(em.stats.agility, rng)
        actors.append(("enemy", i, init))

    actors.sort(key=lambda x: x[2], reverse=True)
    print(f"[Debug:battle_sim/simulate_one_round_multi_party] {actors}")

    # =====================================
    # ③ 行動ループ
    # =====================================
    for side, idx, _ in actors:
        # 全滅チェック
        if not any_char_alive(party_members):
            logs.append("パーティは全滅した…")
            final_result.end_reason = "char_defeated"
            break

        if not any_enemy_alive(enemies):
            logs.append("敵は全滅した！")
            final_result.end_reason = "enemy_defeated"
            break

        # -----------------
        # 味方ターン
        # -----------------
        if side == "char":
            pm = party_members[idx]
            if is_out_of_battle(pm.state):
                continue

            action = planned_actions[idx]

            if pm.state.is_jumping:
                t_idx = getattr(pm.state, "jump_target_index", None)
                if (
                    t_idx is None
                    or t_idx >= len(enemies)
                    or is_out_of_battle(enemies[t_idx].state)
                ):
                    t_idx = first_alive_enemy_index(enemies)
                    if t_idx is None:
                        break

                action = PlannedAction(
                    kind="jump",
                    command="Jump",  # or "JumpDive" でもいいが kind は jump のまま
                    target_side="enemy",
                    target_index=t_idx,
                )

            if action is None:
                continue

            if action.kind == "defend":
                pm.state.temp_flags["defending"] = True
                logs.append(f"{pm.name}は防御した！")

                # ★ JobSP加算（defendはrun_character_turnを通らないためここで）
                old_jl, new_jl = apply_job_sp_for_command(
                    pm,
                    "Defend",
                    weapons=state.weapons,
                    armors=state.armors,
                    save_dict=state.save,  # ★これが必須
                )
                if new_jl != old_jl:
                    logs.append(
                        f"★ {pm.name} のジョブレベルが {old_jl} → {new_jl} に上がった！"
                    )

                continue

            logs.append(f"▶ {pm.name} の行動（{action.command}）")

            # ----- ターゲット決定 -----
            target_enemy: Optional[EnemyRuntime] = None
            target_char: Optional[PartyMemberRuntime] = None

            # ★変更：t_idx を「敵インデックス」として使う（enemy_indexの正体）
            enemy_index: Optional[int] = None

            if action.target_side == "enemy":
                # ----------------------------
                # ★ここから target_all 対応版
                # ----------------------------
                target_indices: list[int] = []

                if getattr(action, "target_all", False):
                    # 全体：生存している敵を全員対象にする
                    target_indices = [
                        i
                        for i, e in enumerate(enemies)
                        if not is_out_of_battle(e.state)
                    ]
                    if not target_indices:
                        break  # 対象がいない
                else:
                    # 単体：従来のフォールバック込み
                    if (
                        action.target_index is None
                        or action.target_index >= len(enemies)
                        or is_out_of_battle(enemies[action.target_index].state)
                    ):
                        t_idx = first_alive_enemy_index(enemies)
                        if t_idx is None:
                            break
                    else:
                        t_idx = action.target_index
                    target_indices = [t_idx]

                # 以降の「単体に対して処理する既存コード」を
                # target_indices で回す
                for enemy_index in target_indices:
                    target_enemy = enemies[enemy_index]

                    # ここから下は、元々 target_enemy/enemy_index を使っていた
                    # 「魔法適用」や「ダメージ/状態異常」や「events生成」を
                    # そのまま置いてください（= 既存処理をforの中に入れるだけ）
                    # 例：
                    #   damage = ...
                    #   events.append({"type": "damage", "enemy_index": enemy_index, "value": damage})
                    #   ...

            elif action.target_side == "ally":
                if (
                    action.target_index is None
                    or action.target_index >= len(party_members)
                    or is_out_of_battle(party_members[action.target_index].state)
                ):
                    t_idx = first_alive_char_index(party_members)
                    if t_idx is None:
                        break
                else:
                    t_idx = action.target_index
                target_char = party_members[t_idx]
            else:
                target_char = pm

            # enemy を必ず渡す（既存仕様のため）
            if target_enemy is None:
                t_idx = first_alive_enemy_index(enemies)
                if t_idx is None:
                    break
                target_enemy = enemies[t_idx]
                enemy_index = t_idx  # ★追加：回復でも「参照用」として一応入れる
            em = target_enemy

            # --- kind ごとの引数決定（あなたのまま） ---
            char_attack_kind: BattleKind = "physical"
            char_battle_command: Optional[str] = action.command
            char_weapon_hand: Literal["main", "off"] = "main"
            char_spell = None
            char_spell_json = None
            char_spell_healing_type = None
            char_spell_name = None
            char_item = None

            if action.kind in ("physical", "special", "run", "jump"):
                if action.kind == "special":
                    char_attack_kind = "special"
                elif action.kind == "run":
                    char_attack_kind = "run"
                elif action.kind == "jump":
                    char_attack_kind = "jump"  # ★追加
                else:
                    char_attack_kind = "physical"

            elif action.kind == "magic":
                if not spells_by_name or not action.spell_name:
                    logs.append(
                        "※ 魔法が選択されなかったため、通常攻撃として扱います。"
                    )
                    char_attack_kind = "physical"
                    char_battle_command = "Fight"
                else:
                    spell_name = action.spell_name
                    spell_json = spells_by_name.get(spell_name)
                    if not spell_json:
                        logs.append(
                            f"※ 魔法《{spell_name}》のデータが見つからないため、通常攻撃にフォールバックします。"
                        )
                        char_attack_kind = "physical"
                        char_battle_command = "Fight"
                    else:
                        spell = spell_from_json(spell_json)
                        healing_type = healing_spell_kind(spell_json)

                        char_attack_kind = "magic"
                        char_spell = spell
                        char_spell_json = spell_json
                        char_spell_healing_type = healing_type
                        char_spell_name = spell_name

            elif action.kind == "item":
                if not items_by_name or not action.item_name:
                    logs.append(
                        "※ アイテムが選択されなかったため、通常攻撃として扱います。"
                    )
                    char_attack_kind = "physical"
                    char_battle_command = "Fight"
                else:
                    item_name = action.item_name
                    item_json = items_by_name.get(item_name)
                    if not item_json:
                        logs.append(
                            f"※ アイテム《{item_name}》のデータが見つからないため、通常攻撃にフォールバックします。"
                        )
                        char_attack_kind = "physical"
                        char_battle_command = "Fight"
                    else:
                        char_attack_kind = "item"
                        char_item = item_json

            # =========================================
            # ★変更：HP/状態異常差分を「敵全員」で取る（AoE対応）
            # =========================================
            old_hp_map = [e.state.hp for e in enemies]
            old_status_map = [set(getattr(e.state, "statuses", set())) for e in enemies]

            # --- 実行 ---
            dmg_to_enemy, char_result = run_character_turn(
                char_name=pm.name,
                enemy_name=em.name,
                char_stats=pm.stats,
                enemy_stats=em.stats,
                enemy_json=em.json,
                char_state=pm.state,
                enemy_state=em.state,
                char_attack_kind=char_attack_kind,
                char_battle_command=char_battle_command,
                char_weapon_hand=char_weapon_hand,
                char_spell=char_spell,
                char_spell_json=char_spell_json,
                char_spell_healing_type=char_spell_healing_type,
                char_spell_name=char_spell_name,
                char_item=char_item,
                logs=logs,
                rng=rng,
                save=save,
                spells_by_name=spells_by_name,
                enemies=enemies,
                target_side=getattr(action, "target_side", "enemy"),
                target_index=getattr(action, "target_index", 0),
                party_members=party_members,
                aoe_selected_override=getattr(action, "target_all", None),
            )

            # ★ JobSP加算（行動が実行された扱い）
            old_jl, new_jl = apply_job_sp_for_command(
                pm,
                char_battle_command or "Fight",  # 最終コマンド名
                weapons=state.weapons,
                armors=state.armors,
                save_dict=state.save,  # ★これが必須
            )
            if new_jl != old_jl:
                logs.append(
                    f"★ {pm.name} のジョブレベルが {old_jl} → {new_jl} に上がった！"
                )

            # =========================================
            # ★変更：差分から dict events を生成して「蓄積」
            # =========================================
            for i, e in enumerate(enemies):
                new_hp = e.state.hp
                new_statuses = set(getattr(e.state, "statuses", set()))

                delta = old_hp_map[i] - new_hp
                if delta > 0:
                    events.append(
                        {
                            "type": "damage",
                            "enemy_index": i,
                            "value": delta,
                        }
                    )

                added = sorted(
                    list(new_statuses - old_status_map[i]), key=lambda x: str(x)
                )
                if added:
                    events.append(
                        {
                            "type": "status",
                            "enemy_index": i,
                            "names": added,
                        }
                    )

            # ★ 行動後：戦闘終了チェック
            if all_enemies_defeated(enemies):
                final_result.end_reason = "enemy_defeated"
                break

            if all_chars_defeated(party_members):
                final_result.end_reason = "char_defeated"
                break

            if char_result is not None and char_result.end_reason != "continue":
                final_result.end_reason = char_result.end_reason
                final_result.escaped = char_result.escaped
                final_result.enemy_attack_result = char_result.enemy_attack_result
                return logs, final_result, events

        # -----------------
        # 敵ターン
        # -----------------
        else:
            em = enemies[idx]
            if is_out_of_battle(em.state):
                continue

            logs.append(f"◆ {em.name} の行動")

            target_idx = random_alive_char_index(party_members, rng)
            if target_idx is None:
                break
            pm = party_members[target_idx]

            char_is_mini_or_toad = pm.state.has(Status.MINI) or pm.state.has(
                Status.TOAD
            )
            char_conf = pm.state.has(Status.CONFUSION)

            dmg_to_enemy = 0

            enemy_result = run_enemy_turn(
                char_name=pm.name,
                enemy_name=em.name,
                char_stats=pm.stats,
                enemy_stats=em.stats,
                enemy_json=em.json,
                char_state=pm.state,
                enemy_state=em.state,
                char_attack_kind="physical",
                dmg_to_enemy=dmg_to_enemy,
                char_conf=char_conf,
                char_is_mini_or_toad=char_is_mini_or_toad,
                logs=logs,
                state=state,
                rng=rng,
                party_members=party_members,
            )

            if all_enemies_defeated(enemies):
                final_result.end_reason = "enemy_defeated"
                break

            if all_chars_defeated(party_members):
                final_result.end_reason = "char_defeated"
                break

            if enemy_result.end_reason != "continue":
                final_result.end_reason = enemy_result.end_reason
                final_result.escaped = enemy_result.escaped
                final_result.enemy_attack_result = enemy_result.enemy_attack_result
                return logs, final_result, events

    return logs, final_result, events


"""
# ============================================================
# 1ターンシミュレーション（魔法で攻撃する場合のためのラッパ）
# ============================================================


def simulate_one_turn_with_spell_name(
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: Dict[str, Any],
    char_state: BattleActorState,
    enemy_state: BattleActorState,
    spell_name: str,
    spells_by_name: Dict[str, Dict[str, Any]],
    job: Optional[Job] = None,
    rng: Optional[random.Random] = None,
) -> OneTurnResult:

    if job is not None:
        allowed = allowed_spell_names_for_job(job)
        if spell_name not in allowed:
            logs = [f"{char_name}は《{spell_name}》を使えない！"]
            return OneTurnResult(
                char_state=char_state,
                enemy_state=enemy_state,
                logs=logs,
                enemy_attack_result=None,
            )

    spell_json = spells_by_name[spell_name]
    spell = spell_from_json(spell_json)

    relation = element_relation_for_monster(enemy_json, spell.elements)

    # ★ 追加: 回復魔法かどうか
    healing_type = healing_spell_kind(spell_json)

    return simulate_one_turn(
        char_name=char_name,
        enemy_name=enemy_name,
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_spell=spell,
        char_spell_json=spell_json,  # ★追加
        char_spell_relation=relation,
        char_spell_healing_type=healing_type,  # ★ 追加
        char_spell_name=spell_name,  # ★追加
        rng=rng,
    )


# ============================================================
# 1ターンシミュレーション（アイテム版ラッパ関数）
# ============================================================


def simulate_one_turn_with_item_name(
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: Dict[str, Any],
    char_state: BattleActorState,
    enemy_state: BattleActorState,
    item_name: str,
    items_by_name: Dict[str, Dict[str, Any]],
    rng: Optional[random.Random] = None,
    save: Optional[dict] = None,
) -> OneTurnResult:

    item_json = items_by_name[item_name]

    # ★消費前の数を保持
    before_qty = get_item_quantity(save, item_name) if save is not None else None

    result = simulate_one_turn(
        char_name=char_name,
        enemy_name=enemy_name,
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="item",
        char_item=item_json,
        rng=rng,
    )

    if save is not None:
        ok = consume_item_from_inventory(save, item_name)
        after_qty = get_item_quantity(save, item_name)

        if not ok:
            result.logs.append(
                f"※ {item_name} の消費に失敗しました（所持数0/未所持の可能性）。"
            )
        else:
            # ★「〜を使った！ / 飲んだ！ など」ログに残数を付け足す
            remain_suffix = f"(残り{after_qty})"

            # 「それっぽい動詞」をまとめておく
            verb_keywords = (
                "使った",
                "飲んだ",
                "投げつけた",
                "振りまいた",
                "振りかけた",
            )

            # それっぽい行があれば末尾に付ける、無ければ追記
            for i in range(len(result.logs) - 1, -1, -1):
                line = result.logs[i]
                if (item_name in line) and any(v in line for v in verb_keywords):
                    result.logs[i] = line + f" {remain_suffix}"
                    break
            else:
                # どのログにもアイテム名＋動詞がなければ、汎用ログを追加
                result.logs.append(
                    f"{char_name}は{item_name}を使った！ {remain_suffix}"
                )

    return result


# ============================================================
# 1ターンシミュレーション
# ============================================================


def simulate_one_turn(
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: Dict[str, Any],
    char_state: BattleActorState,
    enemy_state: BattleActorState,
    char_attack_kind: BattleKind = "physical",
    char_battle_command: Optional[str] = None,  # ★ジョブ側コマンドをそのまま渡せる口
    char_weapon_hand: Literal["main", "off"] = "main",
    char_spell: Optional[SpellInfo] = None,
    char_spell_json: Optional[Dict[str, Any]] = None,  # ★追加
    char_spell_relation: ElementRelation = "normal",
    char_spell_healing_type: Optional[str] = None,  # "hp" / "status" / "revive" / None
    char_spell_name: Optional[str] = None,  # ★ここを追加
    char_item: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
    save: Optional[dict] = None,  # ★ここを追加
    spells_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
) -> OneTurnResult:
    # 1ターン分の攻防をシミュレートしてログを返す簡易関数（1vs1）。
    # ・先にキャラが攻撃 or アイテム使用、その後敵が生きていれば敵が行動

    if rng is None:
        rng = random

    logs: List[str] = []

    # 1) コマンド正規化（今の if char_battle_command ... 部分を丸ごと移動）==============================

    # ★ジョブコマンドが指定されていたら攻撃種別を上書き
    if char_battle_command is not None:
        char_attack_kind = normalize_battle_command(char_battle_command)

    # 2) ターン開始処理（毒ダメージ＋開始時バフ/デバフ）==================================================

    # まずはターン開始時効果（毒など）
    start_of_turn_for_actor(
        actor_name=char_name,
        stats=char_stats,
        state=char_state,
        logs=logs,
        rng=rng,
        is_enemy=False,
        enemy_json=None,
    )
    start_of_turn_for_actor(
        actor_name=enemy_name,
        stats=enemy_stats,
        state=enemy_state,
        logs=logs,
        rng=rng,
        is_enemy=True,
        enemy_json=enemy_json,
    )

    # 3) ターン開始時点で戦闘不能なら即終了 =============================================================

    # ★ すでに戦闘不能なら何もしないで返す
    if is_out_of_battle(char_state):
        logs.append(f"{char_name}は行動不能だ…")
        return OneTurnResult(
            char_state=char_state,
            enemy_state=enemy_state,
            logs=logs,
            enemy_attack_result=None,
        )
    if is_out_of_battle(enemy_state):
        logs.append(f"{enemy_name}はすでに倒れている…")
        return OneTurnResult(
            char_state=char_state,
            enemy_state=enemy_state,
            logs=logs,
            enemy_attack_result=None,
        )

    # 4) キャラの1行動フェーズ（★ここだけが「キャラ側ロジック」）=============================================

    dmg_to_enemy, char_result = run_character_turn(
        char_name=char_name,
        enemy_name=enemy_name,
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind=char_attack_kind,
        char_battle_command=char_battle_command,
        char_weapon_hand=char_weapon_hand,
        char_spell=char_spell,
        char_spell_json=char_spell_json,
        char_spell_healing_type=char_spell_healing_type,
        char_spell_name=char_spell_name,
        char_item=char_item,
        logs=logs,
        rng=rng,
        save=save,
        spells_by_name=spells_by_name,
    )

    if char_result is not None:
        # 逃走成功 / Jump 等でこのターン終了
        return char_result

    # ★ この時点でのキャラの状態異常フラグを「敵ターン用」に再定義する
    #    （敵の攻撃計算で target_is_mini_or_toad などを使うため）
    char_is_mini_or_toad = char_state.has(Status.MINI) or char_state.has(Status.TOAD)
    char_conf = char_state.has(Status.CONFUSION)

    # 5) 敵の1行動フェーズ（★ここだけが「敵側ロジック」）================================================

    return run_enemy_turn(
        char_name=char_name,
        enemy_name=enemy_name,
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind=char_attack_kind,
        dmg_to_enemy=dmg_to_enemy,
        char_conf=char_conf,
        char_is_mini_or_toad=char_is_mini_or_toad,
        logs=logs,
        state=state,
        rng=rng,
    )


def simulate_battle_once(
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: dict,
    spells_by_name: dict | None = None,
    char_attack_kind: str = "physical",
    spell_name: str | None = None,
    max_turns: int = 100,
    rng: random.Random | None = None,
) -> tuple[str, int]:
    # 1バトル分を最後までシミュレートして結果を返す。
    if rng is None:
        rng = random.Random()

    char_state = BattleActorState(
        hp=char_stats.max_hp,
        max_hp=char_stats.max_hp,
    )
    enemy_state = BattleActorState(
        hp=enemy_stats.hp,
        max_hp=enemy_stats.hp,
    )

    for turn in range(1, max_turns + 1):
        if char_attack_kind == "magic":
            if spells_by_name is None or spell_name is None:
                raise ValueError(
                    "magic 攻撃をする場合は spells_by_name と spell_name が必要です。"
                )

            result = simulate_one_turn_with_spell_name(
                char_name=char_name,
                enemy_name=enemy_name,
                char_stats=char_stats,
                enemy_stats=enemy_stats,
                enemy_json=enemy_json,
                char_state=char_state,
                enemy_state=enemy_state,
                spell_name=spell_name,
                spells_by_name=spells_by_name,
                job=job_data,
                rng=rng,
            )
        else:
            result = simulate_one_turn(
                char_name=char_name,
                enemy_name=enemy_name,
                char_stats=char_stats,
                enemy_stats=enemy_stats,
                enemy_json=enemy_json,
                char_state=char_state,
                enemy_state=enemy_state,
                char_attack_kind="physical",
                char_weapon_hand="main",
                rng=rng,
            )

        char_state = result.char_state
        enemy_state = result.enemy_state

        char_out = is_out_of_battle(char_state)
        enemy_out = is_out_of_battle(enemy_state)

        if char_out and enemy_out:
            return "draw", turn
        elif enemy_out:
            return "char", turn
        elif char_out:
            return "enemy", turn

    return "draw", max_turns


def simulate_many_battles(
    n_trials: int,
    char_name: str,
    enemy_name: str,
    char_stats: FinalCharacterStats,
    enemy_stats: FinalEnemyStats,
    enemy_json: dict,
    spells_by_name: dict | None = None,
    char_attack_kind: str = "physical",
    spell_name: str | None = None,
    max_turns: int = 100,
    seed: int | None = None,
) -> dict:
    # 同じ条件で n_trials 回バトルを行い、勝率や平均ターン数を集計する。
    rng = random.Random(seed)

    wins_char = 0
    wins_enemy = 0
    draws = 0
    turn_list: list[int] = []

    for _ in range(n_trials):
        winner, turns = simulate_battle_once(
            char_name=char_name,
            enemy_name=enemy_name,
            char_stats=char_stats,
            enemy_stats=enemy_stats,
            enemy_json=enemy_json,
            spells_by_name=spells_by_name,
            char_attack_kind=char_attack_kind,
            spell_name=spell_name,
            max_turns=max_turns,
            rng=rng,
        )
        turn_list.append(turns)

        if winner == "char":
            wins_char += 1
        elif winner == "enemy":
            wins_enemy += 1
        else:
            draws += 1

    total = n_trials
    win_rate_char = wins_char / total if total > 0 else 0.0
    win_rate_enemy = wins_enemy / total if total > 0 else 0.0
    draw_rate = draws / total if total > 0 else 0.0
    avg_turns = sum(turn_list) / len(turn_list) if turn_list else 0.0

    return {
        "trials": total,
        "wins_char": wins_char,
        "wins_enemy": wins_enemy,
        "draws": draws,
        "win_rate_char": win_rate_char,
        "win_rate_enemy": win_rate_enemy,
        "draw_rate": draw_rate,
        "average_turns": avg_turns,
    }


def simulate_battle_multi_party(
    party_members: List[PartyMemberRuntime],
    enemies: List[EnemyRuntime],
    spells_by_name: Dict[str, Dict[str, Any]],
    items_by_name: Dict[str, Dict[str, Any]],
    save: dict,
    max_turns: int = 50,
    rng: Optional[random.Random] = None,
):
    if rng is None:
        rng = random.Random()

    for turn in range(1, max_turns + 1):
        print(f"\n=== Turn {turn} ===")

        # ---------- 離脱チェック ----------
        if not any_char_alive(party_members):
            print("パーティは全滅した…")
            break
        if not any_enemy_alive(enemies):
            print("敵は全滅した！")
            break

        # ---------- 1) 行動入力フェーズ ----------
        planned_actions: List[Optional[PlannedAction]] = [None] * len(party_members)

        for i, member in enumerate(party_members):
            if is_out_of_battle(member.state):
                continue
            planned_actions[i] = ask_action_for_member(
                member, spells_by_name, items_by_name, save
            )

        # ---------- 2) イニシアティブ計算 ----------
        actors: List[Tuple[str, int, int]] = []  # (side, index, init)

        for i, member in enumerate(party_members):
            if is_out_of_battle(member.state):
                continue
            init = calc_initiative(member.stats.agility, rng)
            actors.append(("char", i, init))

        for i, enemy in enumerate(enemies):
            if is_out_of_battle(enemy.state):
                continue
            init = calc_initiative(enemy.stats.agility, rng)
            actors.append(("enemy", i, init))

        actors.sort(key=lambda x: x[2], reverse=True)

        # ---------- 3) 行動解決フェーズ ----------
        for side, idx, _ in actors:
            if not any_char_alive(party_members):
                print("パーティは全滅した…")
                return
            if not any_enemy_alive(enemies):
                print("敵は全滅した！")
                return

            if side == "char":
                member = party_members[idx]
                action = planned_actions[idx]
                if action is None or is_out_of_battle(member.state):
                    continue

                # ターゲット（とりあえず「先頭の生存敵」に固定）
                t_idx = first_alive_enemy_index(enemies)
                if t_idx is None:
                    break
                enemy = enemies[t_idx]

                # kind に応じて simulate_one_turn 系を呼ぶ
                if action.kind == "magic":
                    result = simulate_one_turn_with_spell_name(
                        char_name=member.name,
                        enemy_name=enemy.name,
                        char_stats=member.stats,
                        enemy_stats=enemy.stats,
                        enemy_json=enemy.json,
                        char_state=member.state,
                        enemy_state=enemy.state,
                        spell_name=action.spell_name,
                        spells_by_name=spells_by_name,
                        job=member.job,
                        rng=rng,
                    )
                elif action.kind == "item":
                    result = simulate_one_turn_with_item_name(
                        char_name=member.name,
                        enemy_name=enemy.name,
                        char_stats=member.stats,
                        enemy_stats=enemy.stats,
                        enemy_json=enemy.json,
                        char_state=member.state,
                        enemy_state=enemy.state,
                        item_name=action.item_name,
                        items_by_name=items_by_name,
                        rng=rng,
                        save=save,
                    )
                elif action.kind == "defend":
                    result = simulate_one_turn(
                        char_name=member.name,
                        enemy_name=enemy.name,
                        char_stats=member.stats,
                        enemy_stats=enemy.stats,
                        enemy_json=enemy.json,
                        char_state=member.state,
                        enemy_state=enemy.state,
                        char_battle_command="Defend",
                        rng=rng,
                    )
                elif action.kind == "run":
                    result = simulate_one_turn(
                        char_name=member.name,
                        enemy_name=enemy.name,
                        char_stats=member.stats,
                        enemy_stats=enemy.stats,
                        enemy_json=enemy.json,
                        char_state=member.state,
                        enemy_state=enemy.state,
                        char_battle_command=action.command,
                        rng=rng,
                    )
                elif action.kind == "special":
                    result = simulate_one_turn(
                        char_name=member.name,
                        enemy_name=enemy.name,
                        char_stats=member.stats,
                        enemy_stats=enemy.stats,
                        enemy_json=enemy.json,
                        char_state=member.state,
                        enemy_state=enemy.state,
                        char_attack_kind="special",
                        char_battle_command=action.command,
                        rng=rng,
                        save=save,
                        spells_by_name=spells_by_name,
                    )
                else:  # physical
                    result = simulate_one_turn(
                        char_name=member.name,
                        enemy_name=enemy.name,
                        char_stats=member.stats,
                        enemy_stats=enemy.stats,
                        enemy_json=enemy.json,
                        char_state=member.state,
                        enemy_state=enemy.state,
                        char_battle_command=action.command or "Fight",
                        rng=rng,
                    )

                # ログ出力
                for line in result.logs:
                    print(line)

                # 状態更新（simulate_one_turn は char + enemy 両方を戻す）
                member.state = result.char_state
                enemy.state = result.enemy_state

                if result.end_reason != "continue":
                    # ここでは簡易的に終了扱い
                    print(f"戦闘終了: reason={result.end_reason}")
                    return

            else:  # side == "enemy"
                enemy = enemies[idx]
                if is_out_of_battle(enemy.state):
                    continue

                t_idx = first_alive_char_index(party_members)
                if t_idx is None:
                    break
                member = party_members[t_idx]

                # マルチ用に run_enemy_turn を使うならこちら
                char_is_mini_or_toad = member.state.has(
                    Status.MINI
                ) or member.state.has(Status.TOAD)
                char_conf = member.state.has(Status.CONFUSION)
                dmg_to_enemy = 0  # このターン直前のダメージが必要なら別途管理

                result_enemy = run_enemy_turn(
                    char_name=member.name,
                    enemy_name=enemy.name,
                    char_stats=member.stats,
                    enemy_stats=enemy.stats,
                    enemy_json=enemy.json,
                    char_state=member.state,
                    enemy_state=enemy.state,
                    char_attack_kind="physical",
                    dmg_to_enemy=dmg_to_enemy,
                    char_conf=char_conf,
                    char_is_mini_or_toad=char_is_mini_or_toad,
                    logs=[],
                    state=state,
                    rng=rng,
                )

                for line in result_enemy.logs:
                    print(line)

                # 状態は run_enemy_turn 内で直接書き込み済みとして扱う
                if result_enemy.end_reason != "continue":
                    print(f"戦闘終了: reason={result_enemy.end_reason}")
                    return
"""
