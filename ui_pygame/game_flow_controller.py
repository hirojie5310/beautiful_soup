# ui_pygame/game_flow_controller.py
# ゲーム進行の制御を担うアプリ層のコントローラ

from __future__ import annotations

# stdlib
import copy
from pathlib import Path
from typing import Callable, Sequence, cast

# third-party
import pygame

# ui
from ui_pygame.game_phase import GamePhase
from ui_pygame.app_context import BattleAppConfig
from ui_pygame.battle_context import BattleContext
from ui_pygame.audio_manager import AudioManager
from ui_pygame.assets_py.portrait_cache import PortraitCache
from ui_pygame.assets_py.status_icon_cashe import StatusIconCache
from ui_pygame.render.sprites import (
    load_enemy_sprite_images,
    load_party_idle_motion_images,
    load_attack_effect_frames,
)
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
from ui_pygame.gameover_flow import show_gameover_screen
from ui_pygame.game_flow_mapping import BATTLE_RESULT_TO_PHASE

# domain / combat
from combat.models import (
    PartyMemberRuntime,
    FinalCharacterStats,
    EquipmentSet,
    EnemyRuntime,
)
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
from combat.save_prompt import save_savedata_with_backup
from ui_pygame.save_prompt_adapter import prompt_save_progress_and_write_pygame
from combat.runtime_state import init_runtime_state
from combat.magic_menu import expand_spells_for_summons, build_party_magic_lists

from system.exp_system import LevelTable
from system.cp_system import load_job_attribution

from assets.data.data_loader import load_explicit_groups

from ui_pygame.audio.ui_se import BattleSE
from ui_pygame.audio.ui_bgm import BattleBGM
from ui_pygame.battle_flow import BattleResult


SAVE_PATH = Path("assets/data/ffiii_savedata.json")


class GameFlowController:
    def __init__(
        self,
        *,
        screen,
        clock,
        font,
        config: BattleAppConfig,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.font = font
        self.config = config

        self.enemy_sprite_cache = load_enemy_sprite_images(config.enemy_sprite_dir)
        self.party_motion_cache = load_party_idle_motion_images(
            config.motion_dir,
            frame_w=config.motion_frame_w,
            frame_h=config.motion_frame_h,
        )
        self.attack_effect_frames = load_attack_effect_frames(
            config.attack_effect_dir,
            frame_w=config.attack_effect_frame_w,
            frame_h=config.attack_effect_frame_h,
            frame_count=config.attack_effect_frame_count,
        )

        pygame.mixer.init()
        self.audio = AudioManager(base_dir=config.audio_dir)
        self.ui_se = build_ui_se(config)
        self.battle_ui_se = {"rareitem": self.ui_se["rareitem"]}

        self.state = init_runtime_state()
        self.spells_expanded = expand_spells_for_summons(self.state.spells)

        self.level_table = LevelTable("assets/data/level_exp.csv")
        self.job_attr = load_job_attribution("assets/data/job_attribution.csv")
        self.explicit_groups = load_explicit_groups("assets/data/explicit_groups.json")

        self.portrait_cache = PortraitCache(base_dir=config.face_dir)
        self.status_icon_cache = StatusIconCache(config.status_icon_dir)
        self.status_icon_cache.preload(
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
        self.phase: GamePhase = GamePhase.ENEMY_SELECT
        self._pending_enemy_names = None

    # メインループ
    def run(self) -> None:
        while self.phase != GamePhase.QUIT:
            if self.phase == GamePhase.ENEMY_SELECT:
                self._enter_phase(GamePhase.ENEMY_SELECT)
                self._run_enemy_select()

            elif self.phase == GamePhase.BATTLE:
                self._run_battle()

            elif self.phase == GamePhase.VICTORY:
                self._run_victory()

            elif self.phase == GamePhase.GAMEOVER:
                self._run_gameover()

    def _enter_phase(self, phase: GamePhase) -> None:
        self.phase = phase

        if phase == GamePhase.ENEMY_SELECT:
            self.audio.play_bgm(self.config.bgm_enemy_select, fade_ms=500)

    # 敵選択
    def _run_enemy_select(self) -> None:
        enemies, party_members, build_magic_fn = self.prepare_battle(
            self._pending_enemy_names
        )

        self._cached_battle = (enemies, party_members, build_magic_fn)
        self.phase = GamePhase.BATTLE

    # 戦闘
    def _run_battle(self) -> None:
        enemies, party_members, build_magic_fn = self._cached_battle
        ctx = self.build_battle_context(enemies, party_members, build_magic_fn)

        result = run_one_battle(
            self.screen,
            self.clock,
            self.font,
            self.config,
            self.audio,
            self.state,
            self.enemy_sprite_cache,
            self.party_motion_cache,
            self.attack_effect_frames,
            status_icon_cache=self.status_icon_cache,
            ctx=ctx,
        )

        if result == BattleResult.ENEMY_DEFEATED:
            self._cached_victory = (enemies, party_members)

        self.phase = self._next_phase_from_battle_result(result)

    # 勝利処理
    def _run_victory(self) -> None:
        enemies, party_members = self._cached_victory

        self.handle_victory(
            enemies=enemies,
            party_members=party_members,
            save_before=copy.deepcopy(self.state.save),
        )

        self.phase = GamePhase.ENEMY_SELECT

    # 戦闘前準備
    def prepare_battle(self, enemy_names) -> tuple[
        list[EnemyRuntime],
        list[PartyMemberRuntime],
        Callable[[int], list[tuple[str, int, int]]],
    ]:
        party_members = build_party_members_from_save(
            save=self.state.save,
            weapons=self.state.weapons,
            armors=self.state.armors,
            jobs_by_name=self.state.jobs_by_name,
            level_table=self.level_table,
        )
        party_magic_lists = cast(
            Sequence[Sequence[tuple[str, int, int]]],
            build_party_magic_lists(self.state),
        )

        build_magic_fn = lambda member_idx: build_magic_candidates_for_member_idx(
            party_magic_lists, member_idx
        )

        if enemy_names is None:
            enemy_names = self._select_enemy_names(
                party_members=party_members,
                build_magic_fn=build_magic_fn,
            )

        enemies = build_enemies(
            enemy_defs_by_name=self.state.monsters,
            spells_by_name=self.state.spells,
            enemy_names=enemy_names,
        )

        return enemies, party_members, build_magic_fn

    # 戦闘コンテキスト構築（BattleSEの導入を含む）
    def build_battle_context(
        self,
        enemies,
        party_members,
        build_magic_fn: Callable[[int], list[tuple[str, int, int]]],
    ) -> BattleContext:
        battle_se = BattleSE(
            enter=self.ui_se.get("enter"),
            confirm=self.ui_se.get("confirm"),
            cancel=self.ui_se.get("cancel"),
            invalid=self.ui_se.get("invalid"),
            rareitem=self.ui_se.get("rareitem"),
        )
        battle_bgm = BattleBGM(
            normal=self.config.bgm_battle1,
            boss=self.config.bgm_battle2,
            victory=self.config.bgm_victory,
            requiem=self.config.bgm_requiem,
        )

        return BattleContext(
            enemies=enemies,
            party_members=party_members,
            spells_expanded=self.spells_expanded,
            se=battle_se,
            bgm=battle_bgm,
            normalize_battle_command=normalize_battle_command,
            reset_target_flags=reset_target_flags,
            is_out_of_battle=is_out_of_battle,
            get_job_commands=get_job_commands,
            build_magic_candidates_for_member=build_magic_fn,
            build_item_candidates_for_battle=lambda: build_item_candidates_for_battle_fn(
                self.state.items_by_name, self.state.save
            ),
            make_planned_action=make_planned_action,
        )

    # 勝利処理
    def handle_victory(
        self,
        *,
        enemies,
        party_members,
        save_before,
    ) -> None:
        victory = apply_victory_rewards(
            party_members=party_members,
            enemies=enemies,
            state=self.state,
            level_table=self.level_table,
        )
        show_victory_result_pygame(
            self.screen,
            self.font,
            victory,
            battle_ui_se=self.battle_ui_se,
        )
        prompt_save_progress_and_write_pygame(
            screen=self.screen,
            font=self.font,
            before_save=save_before,
            after_save=self.state.save,
            save_path=SAVE_PATH,
            save_func=save_savedata_with_backup,
            caption="Save updated Level/EXP to file?",
        )

    # BattleResult から次のフェーズへ
    def _next_phase_from_battle_result(self, result: BattleResult) -> GamePhase:
        try:
            return BATTLE_RESULT_TO_PHASE[result]
        except KeyError:
            raise ValueError(f"Unhandled BattleResult: {result}")

    # 敵選択UI
    def _select_enemy_names(
        self,
        *,
        party_members,
        build_magic_fn: Callable[[int], list[tuple[str, int, int]]],
    ) -> list[str]:
        flat_locations = build_location_index(self.state.monsters)
        all_locations = {loc.location for loc in flat_locations}
        for gname, entry in self.explicit_groups.items():
            for m in entry["locations"]:
                if m not in all_locations:
                    print(f"[WARN] Unknown location in group '{gname}': {m}")

        groups = build_groups(
            flat_locations,
            explicit_groups=self.explicit_groups,
        )

        def recalc_stats_fn(
            actor: PartyMemberRuntime, weapons: dict, armors: dict
        ) -> FinalCharacterStats:
            eq = actor.equipment or EquipmentSet()
            return compute_character_final_stats(
                base=actor.base,
                eq=eq,
                weapons_by_name=weapons,
                armors_by_name=armors,
                job_name=actor.job.name,
            )

        while True:
            group = choose_location_group_pygame(
                self.screen,
                self.font,
                groups,
                party_members=party_members,
                level_table=self.level_table,
                job_attr=self.job_attr,
                weapons=self.state.weapons,
                armors=self.state.armors,
                save_dict=self.state.save,
                save_path=SAVE_PATH,
                jobs_by_name=self.state.jobs_by_name,
                portrait_cache=self.portrait_cache,
                status_icon_cache=self.status_icon_cache,
                recalc_stats_fn=recalc_stats_fn,
                build_magic_fn=build_magic_fn,
                spells_by_name=self.state.spells,
                items_by_name=self.state.items_by_name,
                ui_se=self.ui_se,
            )

            selected = choose_location_floor_pygame(
                self.screen,
                self.font,
                group.children,
                ui_se=self.ui_se,
            )

            if selected is not None:
                break

        return pick_enemy_names(selected, self.state.monsters, k_min=2, k_max=6)

    # ゲームオーバー処理
    def _run_gameover(self) -> None:
        # 例：BGM は BattleController 側ですでに requiem が鳴っている前提
        show_gameover_screen(
            screen=self.screen,
            font=self.font,
        )

        waiting = True
        while waiting:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.phase = GamePhase.QUIT
                    return

                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        # 方針①：タイトルへ戻る
                        self._reset_to_initial_state()
                        self.phase = GamePhase.ENEMY_SELECT
                        return

                    if event.key == pygame.K_ESCAPE:
                        self.phase = GamePhase.QUIT
                        return

    # ゲームオーバー時に状態を初期化
    def _reset_to_initial_state(self) -> None:
        self.state = init_runtime_state()
        self.spells_expanded = expand_spells_for_summons(self.state.spells)
