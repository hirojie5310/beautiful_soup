# ui_pygame/game_loop.py
# アプリケーションの中身（OSとは無関係）ゲーム進行（主役）
# 「画面・時間・設定」だけを受け取る（ゲーム進行に最低限必要な「環境」だけ）
# screen:描画先, clock:フレーム管理, font:表示リソース（pygame依存）
# config:アプリ設定（論理名）

# ui_pygame/
#   ├─ app.py          ← pygame専用の起動ラッパ
#   ├─ game_loop.py    ← ゲーム進行（主役）
#   ├─ enemy_flow.py
#   ├─ battle_flow.py
#   ├─ victory_flow.py

from __future__ import annotations

# stdlib
import copy
from pathlib import Path
from typing import cast, Sequence, Callable

# third-party
import pygame

# ui
from ui_pygame.app_context import BattleAppConfig
from ui_pygame.battle_context import BattleContext
from ui_pygame.audio_manager import AudioManager
from ui_pygame.assets_py.portrait_cache import PortraitCache
from ui_pygame.assets_py.status_icon_cashe import StatusIconCache
from ui_pygame.render.sprites import load_enemy_sprite_images
from ui_pygame.audio.ui_se import build_ui_se
from ui_pygame.logic import (
    reset_target_flags,
    build_magic_candidates_for_member as build_magic_candidates_for_member_idx,
    build_item_candidates_for_battle as build_item_candidates_for_battle_fn,
    make_planned_action,
    get_job_commands,
)
from ui_pygame.battle_flow import run_one_battle
from ui_pygame.enemy_flow import choose_location_group_pygame
from ui_pygame.enemy_flow import choose_location_floor_pygame
from ui_pygame.victory_flow import show_victory_result_pygame

# domain / combat
from combat.models import PartyMemberRuntime, FinalCharacterStats, EquipmentSet
from combat.char_build import (
    build_party_members_from_save,
    compute_character_final_stats,
)
from combat.enemy_build import build_enemies
from combat.life_check import is_out_of_battle
from combat.input_ui import normalize_battle_command
from combat.enemy_selection import (
    build_location_index,
    pick_enemy_names,
    build_groups,
)
from combat.progression import apply_victory_rewards
from combat.save_prompt import (
    save_savedata_with_backup,
    prompt_save_progress_and_write_pygame,
)
from combat.runtime_state import init_runtime_state
from combat.magic_menu import expand_spells_for_summons, build_party_magic_lists

from system.exp_system import LevelTable
from system.cp_system import load_job_attribution

from assets.data.data_loader import load_explicit_groups

from ui_pygame.audio.ui_se import BattleSE


SAVE_PATH = Path("assets/data/ffiii_savedata.json")


def run_game_loop(
    *,
    screen,
    clock,
    font,
    config: BattleAppConfig,
) -> None:
    """
    ゲーム全体の進行を管理するメインループ
    - 敵選択
    - 戦闘
    - 勝利処理
    - セーブ確認
    """
    enemy_sprite_cache = load_enemy_sprite_images(config.enemy_sprite_dir)

    pygame.mixer.init()
    audio = AudioManager(base_dir=config.audio_dir)
    ui_se = build_ui_se(config)
    battle_ui_se = {"rareitem": ui_se["rareitem"]}

    state = init_runtime_state()

    spells_expanded = expand_spells_for_summons(state.spells)

    level_table = LevelTable("assets/data/level_exp.csv")
    job_attr = load_job_attribution("assets/data/job_attribution.csv")
    explicit_groups = load_explicit_groups("assets/data/explicit_groups.json")

    portrait_cache = PortraitCache(base_dir=config.face_dir)
    status_icon_cache = StatusIconCache(config.status_icon_dir)
    status_icon_cache.preload(
        [
            "poison",
            "blind",
            "mini",
            "silence",
            "toad",
            "confusion",
            "sleep",
            "paralysis",
            "petrification",
            "partial petrification",
            "ko",
        ]
    )

    # ===== ここまで移植 =====
    # 次に while app_running を移す
    app_running = True
    enemy_names = None  # 関数引数の初期化 ★ ここを追加
    while app_running:
        audio.play_bgm(config.bgm_enemy_select, fade_ms=500)

        # ★戦闘前のsaveを保持（差分チェック用）
        save_before = copy.deepcopy(state.save)

        party_members = build_party_members_from_save(
            save=state.save,
            weapons=state.weapons,
            armors=state.armors,
            jobs_by_name=state.jobs_by_name,
            level_table=level_table,
        )
        party_magic_lists = cast(
            Sequence[Sequence[tuple[str, int, int]]], build_party_magic_lists(state)
        )

        build_magic_fn: Callable[[int], list[tuple[str, int, int]]] = (
            lambda member_idx: build_magic_candidates_for_member_idx(
                party_magic_lists, member_idx
            )
        )

        # =========================
        # ★敵選択処理
        if enemy_names is None:
            flat_locations = build_location_index(state.monsters)
            # 存在チェック
            all_locations = {loc.location for loc in flat_locations}
            for gname, entry in explicit_groups.items():
                for m in entry["locations"]:
                    if m not in all_locations:
                        print(f"[WARN] Unknown location in group '{gname}': {m}")

            groups = build_groups(
                flat_locations,
                explicit_groups=explicit_groups,
            )

            # 装備変更後は変更を反映させるため必ず呼ぶ
            def recalc_stats_fn(
                actor: PartyMemberRuntime, weapons: dict, armors: dict
            ) -> FinalCharacterStats:
                eq = actor.equipment or EquipmentSet()
                return compute_character_final_stats(
                    base=actor.base,
                    eq=eq,
                    weapons_by_name=weapons,
                    armors_by_name=armors,
                    job_name=actor.job.name,  # ★ここがポイント
                )

            # enemy selection
            while True:
                group = choose_location_group_pygame(
                    screen,
                    font,
                    groups,
                    party_members=party_members,
                    level_table=level_table,
                    job_attr=job_attr,
                    weapons=state.weapons,
                    armors=state.armors,
                    save_dict=state.save,
                    save_path=SAVE_PATH,
                    jobs_by_name=state.jobs_by_name,
                    portrait_cache=portrait_cache,
                    status_icon_cache=status_icon_cache,
                    recalc_stats_fn=recalc_stats_fn,
                    build_magic_fn=build_magic_fn,
                    spells_by_name=state.spells,
                    items_by_name=state.items_by_name,
                    ui_se=ui_se,
                )

                selected = choose_location_floor_pygame(
                    screen,
                    font,
                    group.children,
                    ui_se=ui_se,
                )

                if selected is not None:
                    break  # 決定

            """
            selected = choose_location_pygame(
                screen,
                font,
                locations,
                party_avg_lv=party_avg_lv,
                party_members=party_members,
                level_table=level_table,  # ★追加
                job_attr=job_attr,  # ★追加
                weapons=state.weapons,  # ★追加
                armors=state.armors,  # ★追加
                save_dict=state.save,
                save_path=SAVE_PATH,  # ←あなたの実ファイルパスに合わせて
                jobs_by_name=state.jobs_by_name,
                portrait_cache=portrait_cache,  # ★追加
                status_icon_cache=status_icon_cache,  # ★追加
                recalc_stats_fn=recalc_stats_fn,  # ★追加
                build_magic_fn=build_magic_fn,
                spells_by_name=state.spells,  # ★追加（ここが元の state.spells）
                items_by_name=state.items_by_name,  # ★追加
                ui_se=ui_se,  # ★これだけ,  # ★追加
            )
            """
            enemy_names = pick_enemy_names(selected, state.monsters, k_min=2, k_max=6)

        enemies = build_enemies(
            enemy_defs_by_name=state.monsters,
            spells_by_name=state.spells,
            enemy_names=enemy_names,
        )

        # =========================
        # BattleContext を作る（ctx: 戦闘全体の依存の束（アプリ層））
        ctx = build_battle_context(
            enemies=enemies,
            party_members=party_members,
            spells_expanded=spells_expanded,
            ui_se=ui_se,
            build_magic_fn=build_magic_fn,
            state=state,
        )

        # =========================
        # 戦闘を回す
        end_reason = run_one_battle(
            screen,
            clock,
            font,
            config,
            audio,
            state,
            enemy_sprite_cache,
            status_icon_cache=status_icon_cache,  # ★追加
            ctx=ctx,
        )

        if end_reason == "quit":
            app_running = False
            break

        # =========================
        # ★戦闘後処理（勝利時）
        # =========================
        if end_reason == "enemy_defeated":
            # 事実の確定（ロジック）
            victory = apply_victory_rewards(
                party_members=party_members,
                enemies=enemies,
                state=state,
                level_table=level_table,
            )
            # 演出・表示（UI）
            show_victory_result_pygame(
                screen,
                font,
                victory,
                battle_ui_se=battle_ui_se,
            )
            # 永続化の確認（UX）差分表示 → 保存確認 → 保存
            prompt_save_progress_and_write_pygame(
                screen=screen,
                font=font,
                before_save=save_before,
                after_save=state.save,
                save_path=Path("assets/data/ffiii_savedata.json"),
                save_func=save_savedata_with_backup,  # ★ここで注入
                caption="Save updated Level/EXP to file?",
            )

        enemy_names = None


# BattleContext ファクトリ（ctx: 戦闘全体の依存の束（アプリ層）を返す）
def build_battle_context(
    *,
    enemies,
    party_members,
    spells_expanded,
    ui_se,
    build_magic_fn,
    state,
) -> BattleContext:
    battle_se = BattleSE(
        enter=ui_se.get("enter"),
        confirm=ui_se.get("confirm"),
        cancel=ui_se.get("cancel"),
        invalid=ui_se.get("invalid"),
        rareitem=ui_se.get("rareitem"),
    )

    return BattleContext(
        enemies=enemies,
        party_members=party_members,
        spells_expanded=spells_expanded,
        se=battle_se,
        normalize_battle_command=normalize_battle_command,
        reset_target_flags=reset_target_flags,
        is_out_of_battle=is_out_of_battle,
        get_job_commands=get_job_commands,
        build_magic_candidates_for_member=build_magic_fn,
        build_item_candidates_for_battle=lambda: build_item_candidates_for_battle_fn(
            state.items_by_name, state.save
        ),
        make_planned_action=make_planned_action,
    )
